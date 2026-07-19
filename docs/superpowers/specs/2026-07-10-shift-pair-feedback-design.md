# 入口 D shift+click 等待期反馈 · 设计

**日期**:2026-07-10
**范围**:path2_web_ui · 用户友好度改进(非破坏性、纯前端)

---

## 背景

**入口 D**(shift+click 两个 event 做 pair 查询)当前时序:

| 步骤 | 动作 | 内部 state | UI 反馈 |
| --- | --- | --- | --- |
| 第 1 击 | shift+click marker | `shiftSelectedEvents.length = 1` | **无**(沉默期,用户困惑点) |
| 第 2 击 | shift+click marker | `length = 2` → `triggerPairQuery` | `PairDetailCard` 展示 4 subcheck 结果 |
| 第 3 击 | shift+click marker | 重置为 `length = 1`(新一轮) | 与第 1 击同 |

**问题**:第 1 击落下后到第 2 击前,系统在等待用户下一步,但没有任何视觉反馈——用户不知道点没点上、不知道系统在等什么。

**诉求**(用户,2026-07-10):从用户友好度出发,为这段等待期设计显示提示。

---

## 决策(brainstorm 已锁)

| # | 决策点 | 结论 |
| --- | --- | --- |
| 1 | 反馈载体 | **复用 `CandidateStatusBar` 位置**(K 线主副图 divider 与 sub-outer 之间的独立 16px 条)+ 样式(`#fbbf24` 金黄字 / `rgba(15,23,42,0.92)` 深底) |
| 2 | 图上被选中 marker | **额外加金黄描边高亮**(`#fbbf24`) |
| 3 | banner 文本 | 极简:`入口 D · 已选 1/2 — 再 shift+click 一个 event / Esc 取消` |
| 4 | 取消手势 | **Esc + 空白 click 都清**(复用 `view.clearFocus()` 现有两条路径,扩展其内部一并清 shiftSelectedEvents) |

**选择理由**(复用而非新造):
- **视线路径一致**:用户视线在 K 线图上找/点 marker,banner 在同区域最省视线切换
- **语义一致**:CandidateStatusBar 与 ShiftPairBanner 都表达「系统在等你下一步」——两种态用同一视觉语言,一次学习通用
- **样式一致**:`#fbbf24` 金黄已被系统统一用于「等待/焦点」信号(命中匹配选中态、role list 选中轮廓也已是这色)

---

## 交互设计

### state(view store)

复用现有 `shiftSelectedEvents: ref<ShiftSelectedEvent[]>`(累积器,length ∈ {0, 1, 2})。**追加**两条派生 computed + 两个 action:

```ts
// 派生
const shiftPairPending = computed<boolean>(() => shiftSelectedEvents.value.length === 1)
const shiftSelectedEventIds = computed<ReadonlySet<string>>(
  () => new Set(shiftSelectedEvents.value.map(e => e.event_id))
)

// action
function clearShiftSelection(): void { shiftSelectedEvents.value = [] }

// clearFocus 追加清 shift(单一入口 · Esc 与空白 click 走这)
function clearFocus(): void {
  focusedMatchId.value = null
  focusedEventId.value = null
  clearCandidates()
  clearShiftSelection()   // ★ 新增
}
```

**语义分层**(与 candidateMatchIds 齐平):
- `clearFocus()`:清所有临时交互态(focus + candidate + shift)——Esc / 空白 click 单一入口
- `clearShiftSelection()`:仅清 shift 累积器,职责单一(供未来其他入口调用)
- 现有 `clearDetailCard()` 已清 shiftSelectedEvents,不变

### banner(新组件)

**文件**:`src/components/ShiftPairBanner.vue`

**呈现判据**:`shiftPairPending && candidateMatchIds.size === 0`
- 显式排他 CandidateStatusBar,防两条 banner 叠加 32px
- 理论上 shift+click 走 handleShiftClick 分支,不经 focusEvent 写 candidateMatchIds;但用户可能先做多归属(candidateMatchIds 非空)再按 shift+click——排他判据兜底

**文本**:`入口 D · 已选 1/2 — 再 shift+click 一个 event / Esc 取消`

**样式**:与 CandidateStatusBar 完全等价,内联同值(不抽公共 CSS,YAGNI)

```css
.shift-pair-banner {
  height: 16px;
  line-height: 16px;
  padding: 0 8px;
  font-size: 12px;
  color: #fbbf24;
  background: rgba(15, 23, 42, 0.92);
  border-radius: 3px;
  user-select: none;
  pointer-events: none;
  flex-shrink: 0;
}
```

### banner 挂载

`KlineChart.vue` template,`CandidateStatusBar` 之后(divider 与 sub-outer 之间):

```vue
<ResizableDivider @drag="onDrag" @dragend="onDragEnd" @dblclick="onDblclick" />
<CandidateStatusBar :matches="effectiveAnalysis?.matches ?? []" />
<ShiftPairBanner />              <!-- ★ 新增 -->
<div class="sub-outer" ...>
```

排他判据 → 同时最多显示 1 条,总占 16px,不影响 subGeometry。

### marker 高亮

**`src/render/chart.ts::BandRenderInput` 追加字段**:

```ts
shiftSelectedEventIds?: ReadonlySet<string>
```

**`computeEventData` 内部**:4 种 marker series(points / intervals / price-points / satellites)统一在数据装配时判断:

```ts
if (shiftSelectedEventIds.has(ev.event_id)) {
  itemStyle.borderColor = '#fbbf24'
  itemStyle.borderWidth = 2   // 具体值实现时按视觉验证微调
}
```

- 与既有 tier 色 / highlight / focus 三通道叠加,不覆盖 tier 主色
- 空集或 undefined 时零副作用(向后兼容)

`KlineChart.vue` 传参:`shiftSelectedEventIds: view.shiftSelectedEventIds`(与 selectedEventId / candidateMatchIds / highlightedEventIds / pendingDisambigEventId 并列)

### 取消手势

**零改动路径**——`clearFocus()` §A 补丁后自然生效:
- **Esc**:`KlineChart.vue::onKeyDown` Esc 分支已调 `view.clearFocus()` → 自动清 shift
- **空白 click**:`KlineChart.ts::handleChartClick` 顶部已调 `view.clearFocus()` → 自动清 shift
- **第 3 击 shift+click**:`handleShiftClick` 现有重置为 1 元素的行为不变

---

## 边缘情况

| 场景 | 处理 |
| --- | --- |
| pair query 加载中(2 击 → PairDetailCard 出) | 不上专门 UI(YAGNI,通常几百 ms) |
| 切股 / 切 pattern | 现有 `clearDetailCard()` 已清 shiftSelectedEvents,不变 |
| 第 3 击重置 | banner 从 PairDetailCard 态短暂闪过 2 → 0 → 1,不特殊处理(自然过渡) |
| 用户已有多归属 pending(candidateMatchIds 非空)时按 shift+click | ShiftPairBanner v-if 显式排他,CandidateStatusBar 优先显示;shift 累积器仍推进(与主线焦点态解耦) |
| pair query 失败(网络 / 后端异常) | 现有 `triggerPairQuery` catch 已把 pairScopeResponse 置 null;shiftSelectedEvents 保持 [ev1, ev2] 直到用户下一动作;banner 不重新出现(length=2 不满足判据)——符合"query 已发,不再引导第 2 击"直觉 |

---

## 文件清单

**新增**:
- `src/components/ShiftPairBanner.vue`
- Playwright e2e spec:新增 `e2e/shift-pair-feedback.spec.ts`(与既有 `miss-detection-walkthrough.spec.ts` 主线走查分离,入口 D 沉默期反馈独立可读)

**修改**:
- `src/stores/view.ts` — 派生 + action + clearFocus 补丁
- `src/components/KlineChart.vue` — 挂 ShiftPairBanner + 传 shiftSelectedEventIds
- `src/render/chart.ts` — BandRenderInput 扩字段 + computeEventData marker 高亮通道

**扩展现有 vitest specs**:
- `tests/stores.focus-actions.spec.ts` — clearFocus 补丁清 shiftSelectedEvents
- `tests/stores.focus-derivations.spec.ts` — shiftPairPending / shiftSelectedEventIds 派生
- `tests/components.kline-click.spec.ts` — handleShiftClick 各步骤 store 转换 + handleChartClick 空白清 shift

**新增 vitest spec**:
- `tests/components/ShiftPairBanner.spec.ts` — v-if 判据(pending × 排他)+ 文本 + 样式类

---

## 测试与验收

### Playwright 自测(用户约束,必做)

实现完成后,启动前后端,用 playwright MCP 覆盖 5 条场景:

1. **第 1 击**:shift+click 主图任一 marker → banner 出现在 divider 下方、文本 `入口 D · 已选 1/2 — ...`、被点 marker 有金黄描边
2. **Esc**:banner 与 marker 描边同时消失
3. **空白 click**:空白位置 click → banner 与 marker 描边同时消失
4. **第 2 击**:再 shift+click 另一 marker → banner 消失、PairDetailCard 在 DetailSidebar 顶部展示(与既有入口 D 行为一致)
5. **第 3 击**:PairDetailCard 展示态下再 shift+click 一个 marker → PairDetailCard 收起、banner 出现 `已选 1/2`(重置为新一轮)

每条场景截图存证(scale="device" · resize 2560×1440 · fullPage=true 看整体或 target=selector 看细节)。

### 单元 / 组件测

- **store**:
  - `shiftPairPending` 在 length ∈ {0, 1, 2} 三态下派生正确
  - `shiftSelectedEventIds` Set 构造正确
  - `clearFocus()` 调用后 `shiftSelectedEvents` 为空
  - `clearShiftSelection()` 独立职责(不动 focus)
- **组件**:
  - `ShiftPairBanner` v-if=true 判据(pending=true × candidateMatchIds 空)
  - v-if=false 三分支:pending=false / candidateMatchIds 非空 / 兼有
  - 文本与样式类匹配
- **chart.ts**:
  - `computeEventData` 输入 `shiftSelectedEventIds` 非空时,选中 marker 数据带 borderColor='#fbbf24'
  - 输入 undefined 或空集时零副作用(既有输出不变)

### 验收标准

- 全套 vitest 绿(现 513 tests 无回归)
- vue-tsc 无错误
- build 绿
- 5 条 Playwright 场景截图证明视觉正确

---

## 未纳入(YAGNI)

- **pair query loading 反馈**:第 2 击到 PairDetailCard 之间通常几百 ms,无需专门 UI
- **banner 内 × 关闭按钮**:与 CandidateStatusBar `pointer-events: none` 惯例背离,Esc / 空白 click 已覆盖取消
- **shift+click 手势教学 tooltip**:用户诉求聚焦"过程反馈",不做首次上手教程
- **marker 高亮动画/脉动**:静态描边足够,动画增加视觉噪音
- **公共 banner CSS 抽层**:两条 banner 独立内联同值,不抽公共层(未来第三条 banner 出现时再抽)
