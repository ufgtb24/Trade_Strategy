# path2_web_ui 股票代码搜索功能设计

> 日期:2026-07-14
> 范围:仅前端(path2_web_ui/),零后端改动
> 目标:在 `SidebarResultList` 加前缀式股票代码过滤 + 全局字符转发(打开 UI 后直接键入代码即定位)

---

## 一、动机

当前 `SidebarResultList` 一次扫描能出数千行,用户想找某只股(输入代码定位)需要滚屏或手动切排序键——低效。加一个前缀搜索框,同时让"打开 UI 后直接键入代码"无需先点搜索框(自动 focus + 字符转发),让"输代码=定位股"是最自然的一步操作。

## 二、锁定决策

| 维度 | 决策 | 理由 |
|---|---|---|
| 匹配语义 | **前缀 + 大小写不敏感** | 股票代码检索行业惯例(Bloomberg/TradingView);列表长时最快锁定 |
| 输入框位置 | **面板顶部独立一行、`.preview-bar` 之上** | 与临时计算/逆算/列头 sticky 均不相互干扰 |
| 生效方式 | **实时过滤**(输入即刷) | 与现有 `sortedRows → filteredSortedRows` 派生 pipeline 同构;数据量下 O(N × \|q\|) 完全够跑 |
| 全局字符转发 | **启用**,非 input focus 时按 `[a-zA-Z0-9.\-]` 单字符键自动 `input.focus()` | 一步操作;`.` `-` 覆盖 BRK.B / TSM-A 类代码 |
| 与 `visiblePatterns` filter | **AND** | 只显示某几个 pattern 且搜前缀 → 取交集 |
| `KlineChart` 字母 B(入口 A brush toggle) | **改为 Shift+B** | 最小侵入;伯仁不变;不吞字符流 |
| 搜索框 focus 时 ArrowUp/Down | **仍切当前选中股**(去 `SidebarResultList` 原输入框守卫) | 新交互下 input 常态 focus,方向键在 input 里无意义,应继续行使切股职责 |
| 持久化 | **不持久化**(session 内),切 pattern / open 扫描结果时清 | 避免旧 query 遗留误过滤新数据 |

## 三、数据流与派生链

```
unionRows  →  sortedRows  →  filteredSortedRows
                                     ├── 既有:row.cells.some(c => visiblePatterns.has(c.pid) && c.matched)
                                     └── 新增 AND:q === '' || row.symbol.toLowerCase().startsWith(q)
```

- 空 query 短路 `true`(全通过)。
- `q` 值一次 `trim().toLowerCase()` 缓存在 computed 顶层,避免每行重复计算。

## 四、组件改动清单

### A. `stores/view.ts`

- 新增 state:`symbolQuery: string`(初始 `''`)。
- 新增 action:`setSymbolQuery(q: string)` / `clearSymbolQuery()`。
- `filteredSortedRows` 尾追前缀 filter(见 §三)。
- 在 `open(scanFile)` / `selectPattern(pid)` action 内部调 `clearSymbolQuery()`——切数据源时清 query。
- 导出:`symbolQuery` 加入 return 对象。

### B. `components/SidebarResultList.vue`

模板顶部新增 `<div class="search-bar">`(在 `.preview-bar` 之上),包含:

- `<input ref="searchInputEl" type="text" :value="symbolQuery" @input="onInput" placeholder="搜索 symbol…" spellcheck="false" autocomplete="off" />`
  - `onInput(e)` = `view.setSymbolQuery((e.target as HTMLInputElement).value)`;不用 `.trim` 修饰符(空格立刻断前缀更符合直觉,由 computed 内部 trim)
- 右侧数量提示 `<span class="count">{{ filteredSortedRows.length }} / {{ sortedRows.length }}</span>`
- 右侧清空按钮 `<button v-if="symbolQuery" class="clear" @click="onClear">×</button>`(点击 → 清 + 保持 focus)

`scanFile == null` 时整个 `.search-bar` 隐藏(同 `hint` 分支)。

修改现有 `onArrowKey` 守卫:去掉 `t.closest('input, textarea, ...)` 分支——搜索框 focus 也切股;保留 IME `isComposing` 守卫。

修改现有 `onDocKey`(Esc 关字段菜单)扩容:若 `document.activeElement === searchInputEl.value`:
- `symbolQuery` 非空 → `clearSymbolQuery()`;
- `symbolQuery` 已空 → `searchInputEl.value.blur()`;
- 优先级高于字段菜单关闭。

### C. 全局字符转发(挂在 `SidebarResultList.vue` 的 `onMounted`)

```
document.addEventListener('keydown', onGlobalCharKey, true) // capture 阶段
```

`onGlobalCharKey` 守卫序:

1. `scanFile.value == null` → return(列表未渲染)
2. `e.ctrlKey || e.metaKey || e.altKey` → return
3. `e.isComposing` → return
4. 活动元素守卫(避开对话框内焦点):
   - `const ae = document.activeElement`
   - `if (ae !== document.body && ae !== null && !listEl.value?.contains(ae)) return`
   - 即"焦点在 body 或列表面板内"才劫持;焦点在其他面板 / 对话框内一律放行
5. `e.key.length !== 1 || !/^[a-zA-Z0-9.\-]$/.test(e.key)` → return
6. 若 activeElement 已是 searchInputEl → return(浏览器默认输入生效)
7. 命中:
   - `searchInputEl.value?.focus()`
   - `view.setSymbolQuery(view.symbolQuery + e.key)`(手工追加,浏览器不会把此次 keydown 的默认 action 重新 route 到新 focus 的 input,必须手工写)
   - `e.preventDefault()`(阻拦其他 window keydown handler,如页面滚动 / 组件级快捷键)

`onBeforeUnmount` 里 `removeEventListener('keydown', onGlobalCharKey, true)`。

### D. `components/KlineChart.vue`

`onKeyDown` 里现有分支:

```
if ((e.key === 'b' || e.key === 'B') && !e.ctrlKey && !e.metaKey && !e.altKey) { toggleBrush() ... }
```

改为:

```
if (e.key === 'B' && e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) { toggleBrush() ... }
```

(shift 语义下 `e.key === 'B'`;单字符 `b` 分支彻底移除。)

输入框守卫保留(和字符转发的守卫双重保险)。若组件模板 / tooltip 内有 "B" 键提示,一并改为 "Shift+B"。

## 五、边界

1. **无匹配时的选中股**:`view.symbol` 不因 filter 变空而重置——K 线不切走;仅列表可见性变化。用户按 Esc / × 恢复。
2. **query 非空但选中股不在结果里**:`.active` 高亮的行不在 `visibleRows` 中不渲染;右侧 K 线继续显示旧选中股。
3. **切 pattern / open 扫描结果**:`clearSymbolQuery()` 自动清 query。
4. **对话框(ScanConfigDialog / ScanResultDialog)打开时**:焦点在对话框内可 focus 元素,§四.C 的活动元素守卫(`listEl.contains(ae)` 判定)自动放行。
5. **中文输入法**:`e.isComposing` 已守卫;组字中不劫持。
6. **粘贴**:全局不劫持 `paste`;搜索框内粘贴走 input 默认。
7. **数量提示**:`{{ filteredSortedRows.length }} / {{ sortedRows.length }}`——分母是"排序后"数量(=当前 pattern 可见性 filter 前的全集,即 unionRows.length 等价——因排序不改数量,直接用 sortedRows.length 语义清楚)。

## 六、验收测试

### 单元(`vitest`,`stores/view.spec.ts`)

- `symbolQuery = 'AA'` → `filteredSortedRows` 只保留 symbol 以 AA/aa 开头
- `symbolQuery = ''` → `filteredSortedRows` 等价于旧行为
- `visiblePatterns` filter × `symbolQuery` filter = AND(构造混合行验证)
- `clearSymbolQuery()` 恢复完整列表
- `open()` / `selectPattern()` 触发后 `symbolQuery === ''`

### 组件(`vitest`,`SidebarResultList.spec.ts`)

- `scanFile == null` → 搜索框 DOM 不存在
- 面板 mounted 后,`document.body.focus()` → 派发 `keydown` key='a' → `searchInputEl` 拿到 focus 且 store `symbolQuery === 'a'`(依赖 jsdom keydown → input 默认输入链是否 fireable;若 jsdom 不模拟,则拆两步:守卫触发 focus / 手工写入 store)
- 焦点在 `searchInputEl` 时派发 `keydown` key='ArrowDown' → `view.selectSymbol` 被调、参数为 sorted-filtered 下一行 symbol
- 焦点在 `searchInputEl` + `symbolQuery = 'aa'` 时按 Esc → `symbolQuery === ''`
- 焦点在 `searchInputEl` + `symbolQuery = ''` 时按 Esc → `searchInputEl` blur

### E2E(Playwright,一条 smoke)

- 启动 UI,加载扫描结果
- 键入 `AA` → 列表只剩前缀 AA 的股,数量提示同步
- 按 ↓ → 选中下一行,K 线更新
- 按 Esc → 列表恢复完整
- K 线获得焦点 → `Shift+B` → brush 光标态激活(回归入口 A)
- 面板焦点在 body → 按 `B`(不加 Shift)→ 搜索框拿到 `b`、brush 不激活

## 七、非目标

- **模糊 / 子串搜索**:显式排除;用户可用前缀多字符收窄
- **持久化到 config**:显式排除;session 内即用即弃
- **多字段搜索**(如按公司名):非目标——列表只有 symbol 一个稳定键
- **正则**:非目标——过重

## 八、影响面

- 后端零改动
- 前端改动:1 store 文件 + 2 组件文件(SidebarResultList / KlineChart)
- 测试:新增 view store spec 段、SidebarResultList 组件 spec、1 条 E2E smoke
