# Spec — path2_web matched marker ↔ role events 关联可见度增强(M + M' 一并实施)

> **状态**:design 已批准(2026-06-30 user approval),待 writing-plans。
> **范围**:**一并实施 M(matched-marker 关联可见度基础:bracket 从主图移到副图、selectedMatchId/highlightedEventIds store、双向 click 联动、tooltip 信息层兜底)+ M'(candidate 消歧机制:multi-match event 显式选 group)**;含 critic v3 三个 P0/P1 必收口 + 三个 brainstorm 拍板细节。
> **前置**:无。当前代码 bracket 仍在 grid0 主图顶,本 spec 是一次性把 M + M' 落地的完整 plan(总计 M 改动 16 项 + M' 增量 10 项,部分 M' 条目与 M 条目合并实施,详 §4)。

---

## 0. 必读上下文(实施前)

1. **现状交互图谱**:`docs/research/2026-06-30_path2-web-match-event-correlation/current_interaction_map.md`(mapper 整理,4 条现有交互路径 + 高亮机制 + 数据 join 钥匙 + grid1 几何冲突盘点;含全部 file:line 引用)
2. **完整方案演进史**:`docs/research/2026-06-30_path2-web-match-event-correlation/final_report.md` §1.1(M)+ §1.2(M')
3. **critic v3 评审**:`docs/research/2026-06-30_path2-web-match-event-correlation/critic_review_v3_m_prime.md`(P0/P1 必收口 + 11 条次要 finding)

本 spec 已并入 critic v3 全部 P0/P1 必收口 + 三个 brainstorm 拍板细节,可作为唯一实施依据;研究文档作为 rationale 索引备查。

---

## 1. 目标与用户问题

### 1.1 用户问题

bracket 移到 grid1 后与 role band 行垂直对齐,这只是把"水平时间对齐"做对;还要回答用户三个核心问题:

| Q | 问题 | M 的回答 | M' 的回答 |
|---|---|---|---|
| ① | match 由哪些 events 组成? | 1 click bracket → 全 group 同色描边 | 同 |
| ② | event 属于哪个 match?(单归属) | 1 click event → bracket 自身亮色 + 反查 | 同 |
| ③ | event 属于哪几个 match?(**多归属共享 event**) | first match 视觉 + tooltip 文字兜底 | **候选态高亮全部 N 个 bracket,用户视觉一眼看出归属数与位置(代价:多归属 event→match 路径 1 click 变 2 click;单归属与原 M 一致)** ★ |
| ④ | 在 ① ③ ⑤ 中切换查看 | 各 bracket 直接 click | 同(不依赖 event candidate 路径) |

### 1.2 设计原则

**"不可预期才有信息"**(用户原则):多归属是 event 与 match 之间的真实结构差异,应被用户感知到。把它平展成"first match 直接亮"是抹平信息。

**"用户操作必有即时回执"**(critic 红线):click 后被点元素必须有视觉反馈;不能让用户怀疑"我按了什么都没发生"。

---

## 2. 交互设计

### 2.1 触发与四路统一

trigger = **click only**(无 hover、无键盘;hover 走 tooltip 只读信息层)。四路 click 统一汇入同一组 store 变更:

1. **图上 click bracket** — 直接拿 `match_id` → `setHighlightedEvents(match.children) + selectMatch(match_id)`
2. **图上 click marker**(point / interval / price-point) — 反查 `const ms = matches.filter(m => m.children.includes(event_id))`
3. **sidebar 命中匹配行 click** — 拿 `match.event_id`,同 (1)
4. **sidebar trace role 行 click** — **保留**单焦点 `selectEvent(eid)` 语义,**不**触发组高亮(支持调试场景下 focus 单 role 看属性)

### 2.2 状态机

三态 **互斥**(任意时刻只能持有 [空闲] / [candidate] / [selected] 之一):

```
[空闲]
  ├── click bracket                            → [selected]                  单 group 高亮
  ├── click single-match event (ms.length=1)   → [selected]                  同 M
  ├── click multi-match event (ms.length>1)    → [candidate: N brackets]     先 clearSelected 再进
  ├── click no-match event (ms.length=0)       → 原 selectEvent 单焦点        M fallback
  └── Esc / 空白 click                          → 不变

[candidate]
  ├── click 候选中某 bracket                    → [selected] + clearCandidate
  ├── click 非候选 bracket                      → [selected] + clearCandidate (改主意)
  ├── click 同一 multi-match event              → 保持(幂等,重算 setCandidate 同 Set)  ★拍板 #1
  ├── click 另一 multi-match event              → 重算 candidate
  ├── click single-match event                  → clearCandidate 进 [selected]
  ├── click no-match event                      → clearCandidate 进原 selectEvent 单焦点
  └── Esc / 空白 click                          → 回 [空闲]

[selected]
  └── 同上各种切换;切换前自动清前一个 selected
```

**互斥规则的理由**:
- 避免渲染优先级争议(同一 bracket 同时是已选 + 候选时,fill 用哪个值?)
- 避免状态机迁移条目数翻倍(每条 candidate 路径都要分"已选与否"两支)
- 若用户实测后强烈要求"看 ① 同时探索 ③⑤ 是否包含某共享 event",升 v2.5 active set 多选(见 §6)

**幂等 click**(拍板 #1):点同一 multi-match event 二次 = 重算 `setCandidateMatches(ids)`,Vue ref 整体替换 → 相同 Set 内容不会触发额外 UI 变化;语义 = "我还在看这个 event 的归属,不要解除"。不做 toggle 清空(与 Esc 重叠且语义不顺)。

### 2.3 视觉编码(critic v3 必收口 #1:全 fill alpha,不占 stroke 通道)

**bracket 三态**(只动 `children[0]`(rect)的 `style.fill`,不动 stroke,不动 `children[1]`(text)):

| 态 | fill | stroke | 说明 |
|---|---|---|---|
| 未选 | `#64748b` 灰 | 无 | 现状 |
| 候选(新) | `rgba(251,191,36,0.35)` 琥珀低 alpha | 无 | "我是候选,等你 click" |
| 已选 | `rgba(251,191,36,0.85)` 琥珀高 alpha(≈实色) | 无 | 同 M |

candidate 与 selected **色相同根(琥珀)、靠 alpha 梯度区分**(0.35 vs 0.85);用户视线"先扫到候选轮廓再点准目标"顺畅。

**关键**:bracket 三态都**不占 stroke 通道**,留给 marker 组高亮的琥珀 stroke(M)。这是 critic v3 P0 必收口 #1 的核心——避免 candidate 的 stroke 与 M group highlight 的 stroke 同色同粗共存时无法区分。

**marker 状态**:

| marker 态 | 视觉 | 渲染机制 |
|---|---|---|
| 未命中 | 原 itemStyle.color(role 色) | 现状 |
| 组高亮(已选 match 的 children) | 琥珀 `#fbbf24` stroke 1.5px | `highlight` 系列 `kind='group'` 分支 |
| 焦点单选(`selectedEventId === eid`) | 白 stroke 2.5px + fill +18% 亮度 | `highlight` 系列 `kind='focus'` 分支 |
| **multi-match 待消歧反馈(新)** | **永久弱白 stroke 1px,直到 candidate 清空** | `highlight` 系列新加 `kind='pendingDisambig'` 分支(拍板 #3) |
| 组高亮 + 焦点单选共存 | 白 stroke 覆盖琥珀 stroke + 内填轻染 | 同 M |
| 组高亮 + pendingDisambig 共存 | 琥珀 stroke 1.5px 优先(已选状态下不应再有 candidate,互斥;但代码兜底先 focus > group > pendingDisambig) | 优先级顺序 |

**multi-match marker 反馈**(拍板 #3 永久弱描边):

理由——状态类反馈契合 candidate 持续态。用户在 candidate 期间随时能指认"我点的是哪个 event"(对照 ① ③ ⑤ 哪个 bracket 在它的水平位置上下出现)。0.3s 闪烁是事件类反馈,瞬时;candidate 期间后期用户会忘"我点的是哪个 event"。工程成本:复用既有 `highlight` 系列加 `kind='pendingDisambig'` 第三分支(stroke white 1px),不引入额外动画机制。

### 2.4 tooltip(拍板 #2:P5 段保留)

**bracket hover tooltip**:

非候选态:原 M `buildMarkerTooltipFormatter` `seriesName === 'brackets'` 分支的"组成 (N events): role: eid (×N kleene)"段(M #15)。

候选态:**前置首行**`候选: click 此 bracket 选中该 group`,之后接 M 的"组成"段(M #15)。判定写在 `buildMarkerTooltipFormatter` `seriesName === 'brackets'` 分支头:

```ts
if (view.candidateMatchIds.has(match_id)) {
  lines.unshift('候选: click 此 bracket 选中该 group')
}
```

**marker hover tooltip**:

原 M 末尾段"归属:match ① ③ ⑤"**保留**(拍板 #2)。理由——hover 不点也能看;候选 bracket 在 zoom 视窗外时是 #25 状态栏之外的第二层文字兜底;零额外成本(已在 M 改动 #16)。

实现细节同 M #16:`matches.filter(m => m.children.includes(event_id))` 拿 ordinal 列表,push "归属:match ① ..."。单归属也会显示(不做"仅多归属才显示"的分支,避免逻辑分支增加,且 M 现状已是无差别显示)。

### 2.5 候选状态栏(critic v3 必收口 #2 子条款 — 新组件)

新 Vue 组件 `path2_web_ui/src/components/CandidateStatusBar.vue`,watch `view.candidateMatchIds`:

- `size === 0`: 隐藏(`v-show="false"`)
- `size > 0`: 显示横条 `候选: ① ③ ⑤ — click 任一 bracket 高亮 / Esc 取消`(ordinal 从 `matches.find(m=>m.event_id===id).ordinal` 拿,1-based ①-⑨;>9 fallback 阿拉伯数字)

**位置**:副图 grid1 顶部 16px banner。**联合 M+M' 算式**:grid1 加高到 26%(sliderShow)/ 24%(noSlider),banner 16px 含在内(详 #13 + §6.2 实测承诺 #2)。

**承担**:
1. **候选 bracket 在 zoom 视窗外时的可达性兜底**——用户能看到当前是 candidate 态(不用猜)
2. **教学**——首次见候选机制的用户立刻知道下一步该做什么(状态栏文字明示动作)
3. **解除沉默 click 的第二层反馈**——marker 永久弱描边在 grid1,banner 在 grid1 顶部,空间相邻可对照

### 2.6 持久态与清空

candidate / selected / highlightedEventIds 都 **持久至下次操作**(click 替换 / Esc 清空 / 主图空白 click 清空)。

**跨上下文清理**(critic v3 F1.3):切股 / 切 pattern / scan 重跑时,store 显式调用 `clearCandidates() + clearHighlight() + selectMatch(null)`,避免残留。

---

## 3. 数据模型与 store

### 3.1 新 store 字段(`path2_web_ui/src/stores/view.ts`)

紧贴现有 `selectedEventId`(view.ts:44) / `selectedMatchId`(view.ts:205 邻近)之后,新增两个 ref:

```ts
// 紧贴 selectedEventId 之后
const highlightedEventIds = ref<ReadonlySet<string>>(new Set())  // M 已加
const candidateMatchIds = ref<ReadonlySet<string>>(new Set())    // M' 新加

// 紧贴 selectEvent / selectMatch 之后
function setHighlightedEvents(ids: string[]) {
  highlightedEventIds.value = new Set(ids)         // 整体替换触发响应式
}
function clearHighlight() {
  highlightedEventIds.value = new Set()
}
function setCandidateMatches(ids: string[]) {
  candidateMatchIds.value = new Set(ids)
}
function clearCandidates() {
  candidateMatchIds.value = new Set()
}
```

**Vue 3 ref 持 Set 必须整体替换**——`.add()` / `.delete()` 不触发响应式(critic v3 F3.3)。所有 setter 用 `ref.value = new Set(...)`,清空也是 `new Set()` 不是 `null`(避免类型分歧)。

`ReadonlySet` 是 TypeScript 类型声明,运行时无意义;ids 数组有重复时 Set 自然去重,语义幂等。

### 3.2 数据 join 通道(复用现有契约)

- `MatchDict.children: string[]`(types.ts:33-39)= 该 match 的全部组成 event_id(扁平)
- `MatchDict.role_index: Record<string, string | string[]>`= role → event_id(string|string[],kleene 时为数组)

**multi-match 反查**:`const ms = matches.filter(m => m.children.includes(event_id))`

**kleene 不构成 multi-match 假阳**(critic v3 F1.2):`children` 是扁平,kleene role 的多个 events 各占一行,**同一 event_id 不会在同一 match.children 中出现多次**;multi-match 来源**仅**是同一 event_id 被**多个不同 match.children** 共享。

---

## 4. 改动清单(file:line)

> 本表 **完整覆盖 M + M' 全部 26 项改动**(M 基础 #1-16 + M' 增量 #17-26)。**冲突合并规则**:`#3 / #5 / #6 / #7 / #10 / #11 / #12 / #15` 在联合实施时按 M' 扩展行为准(M 行末尾标 `→ 实施按 #X`),实施者读 #X 描述即可,M 行只看 file:line 与意图。

### 4.A M 基础改动(#1-16:bracket 移到副图 + store + 双向联动 + tooltip)

| # | 改动点 | 文件:行 | 改什么 |
|---|---|---|---|
| 1 | 新 store 字段 `highlightedEventIds` | `view.ts:44` 附近 | `highlightedEventIds = ref<ReadonlySet<string>>(new Set())`。Vue 3 ref 持 Set **必须整体替换**才触发响应式(`.add()` 不触发) |
| 2 | 新 store actions | `view.ts:209` 附近 | `setHighlightedEvents(ids: string[]) { highlightedEventIds.value = new Set(ids) }` / `clearHighlight() { highlightedEventIds.value = new Set() }` |
| 3 | bracket renderItem 选中态 | `chart.ts:495-512` | M 原方案 `selectedMatchId 命中 → fill #fbbf24 + z=12` → **实施按 #19**(改用 alpha fill,critic v3 必收口 #1) |
| 4 | **brackets 系列轴归属(bracket 从 grid0 主图顶移到 grid1 副图的核心改动)** | `chart.ts:333`(brackets 系列定义) | `yAxisIndex: 1` → `yAxisIndex: 2`(改挂 grid1 marker 轴);`xAxisIndex: 0` → `xAxisIndex: 1`。`renderBracket` 内 `params.coordSys.y` 自动取 grid1 顶部,几何代码保留(详 mapper map.md Q4) |
| 5 | 高亮分流改 filter(支持组高亮) | `chart.ts:205-234` | `pointData.filter(d => highlightedEventIds.has(d.event_id))` 三类(point/interval/price-point)各 push;**保留**原 selectedEventId 单焦点 push 不变 → **实施按 #20**(同时再加 pendingDisambig 第四 push) |
| 6 | highlight renderItem 多分支 | `chart.ts:417-459`(`makeRenderHighlight`)+ `chart.ts:465-492`(`makeRenderPricePointHighlight`) | M 原方案 `kind: 'group' \| 'focus'` → **实施按 #20** 扩为 `kind: 'group' \| 'focus' \| 'pendingDisambig'` 三分支 |
| 7 | 图上 click 接线 | `KlineChart.vue:93-105` | M 原方案 brackets 分支 + marker 反查 first match 单一路径 → **实施按 #21**(marker)+ **#22**(brackets) |
| 8 | sidebar 命中匹配行 click | `DetailSidebar.vue:75-89, 237-242` | `selectMatchAndHighlight` 改为 `setHighlightedEvents(m.children) + selectMatch(m.event_id)` |
| 9 | sidebar trace role 行 click | `DetailSidebar.vue:97-113, 220-234` | **保持** `selectEvent` 单焦点语义不变(调试场景下 focus 单 role 看属性) |
| 10 | Esc 键清空 | `KlineChart.vue` 顶层 / mount hook | `window.addEventListener('keydown', e => { if (e.key === 'Escape' && !isInputFocused(e.target)) { 清四样 } })`,需判 input/textarea 焦点不拦 → **实施按 #23**(清四样 = clearHighlight + selectMatch(null) + selectEvent(null) + clearCandidates) |
| 11 | 主图空白 click 清空 | `KlineChart.vue:93-105` | click handler 加空白分支 → **实施按 #21 / #23**(主图空白 click 走 click handler 空白分支后清四样) |
| 12 | setOption 重渲触发 | `KlineChart.vue` `effectiveAnalysis` watcher | 扩展 watch 数组加入 M+M' 全部新 ref → **实施按 #24** |
| 13 | grid1 几何加高 | `chart.ts:296-300`(grid 数组) | **联合 M+M' 实测算式(含 #26 banner 16px)**:首版起步值 `grid[1].height: '18%' → '26%'`(sliderShow)/`'16%' → '24%'`(noSlider);grid0 `top`/`height` 同步收紧;若 7-band 实测仍挤,加到 30%。**实测承诺见 §5.2 #2** |
| 14 | bracket 字号缩小(配合移到副图后视觉) | `chart.ts:495-512` 圆圈 text style | 原 `MARKER_FONT_SIZE+4=20` → `12`,与 bandLabel 视觉对齐(副图 bandH 小,序号字号要缩) |
| 15 | P5 tooltip bracket 段(组成 N events) | `chart.ts:837-893`(`buildMarkerTooltipFormatter`) | `seriesName === 'brackets'` 分支:从 `matchById.get(match_id).role_index` 拿 role → eid(string \| string[]),数组类型显式标 `(×N kleene)`,push 到 "组成" 段 → **实施按 #25**(加候选态首行前置) |
| 16 | P5 tooltip 归属节(归属:match ① ③ ⑤) | `chart.ts:837-893` 同上 | `seriesName ∈ {points, intervals, price-points, satellites}` 分支末尾:`matches.filter(m => m.children.includes(event_id))` 拿 ordinal 列表,push "归属:match ①..."。**保留**(brainstorm 拍板 #2),作为 candidate 态 #26 状态栏之外的第二层文字兜底 |

**M 部分不改**:
- `geometry.ts:47-51` `packBrackets` 全局 lane **保留**(bracket 跨多 band 无单一归属;ordinal ①..⑨ 全局唯一性破不得 — 与 sidebar 序号字面对照绑死)
- `DetailSidebar.vue:55` 候选表行 click 保持 `selectEvent`(候选表是"未归属"诊断对比工具,反查无 match)
- `view.ts:44` 既有 `selectedEventId` ref 保留并存(不改 set,新字段并行)

### 4.B M' 增量改动(#17-26:candidate 消歧 + 状态栏)

| # | 改动点 | 文件:行 | 改什么 |
|---|---|---|---|
| 17 | 新 store 字段(2 个) | `path2_web_ui/src/stores/view.ts:45` 附近(紧贴 M #1 `highlightedEventIds` 之后) | `candidateMatchIds = ref<ReadonlySet<string>>(new Set())` + `pendingDisambigEventId = ref<string \| null>(null)` |
| 18 | 新 store actions(2 组) | `view.ts:211` 附近(紧贴 M #2 `setHighlightedEvents` 之后) | `setCandidateMatches(ids: string[]) { candidateMatchIds.value = new Set(ids); if (ids.length === 0) pendingDisambigEventId.value = null }` / `clearCandidates() { candidateMatchIds.value = new Set(); pendingDisambigEventId.value = null }` / `setPendingDisambig(eid: string \| null) { pendingDisambigEventId.value = eid }`。clearCandidates 内**同步清** pendingDisambig,避免残留 |
| 19 | bracket renderItem 加候选/已选 fill 分支 | `path2_web_ui/src/render/chart.ts:495-512`(`renderBracket`) | 修改 `children[0]`(rect)的 `style.fill`:`selectedMatchId === match_id` → `rgba(251,191,36,0.85)`;`else if candidateMatchIds.has(match_id)` → `rgba(251,191,36,0.35)`;else → 原 `#64748b`。**不动 stroke,不动 children[1]**(text)。优先级 selected > candidate > 默认。需 `emphasis: { disabled: true }`(防 ECharts 默认 hover 改 fill,见 §5.3) |
| 20 | highlight 系列 pendingDisambig 分支 | `chart.ts:417-459`(`makeRenderHighlight`)+ `chart.ts:205-234`(highlightData 分流) | data 加 `kind: 'group' \| 'focus' \| 'pendingDisambig'` 第三分支;pendingDisambig → `stroke: white, lineWidth: 1`(细于 group 1.5px,弱于 focus 2.5px)。highlightData 分流:若 `pendingDisambigEventId` 非 null,拿对应 point/interval/price-point 数据 push 一条 `kind='pendingDisambig'`。 |
| 21 | marker click 分流 | `path2_web_ui/src/components/KlineChart.vue:93-105`(`chart.on('click', ...)`) | 改 points/intervals/price-points/satellites 分支为:`const ms = matches.filter(m => m.children.includes(event_id))`;**任何分支都先 `clearCandidates()` 保守清残**,再进具体处理:`ms.length === 0` → `selectEvent(event_id)`(M fallback);`ms.length === 1` → `setHighlightedEvents(ms[0].children) + selectMatch(ms[0].event_id) + selectEvent(event_id)`(同 M);`ms.length > 1` → `selectMatch(null) + clearHighlight() + selectEvent(null)`(先清单焦点)+ `setCandidateMatches(ms.map(m => m.event_id)) + setPendingDisambig(event_id)`(进 candidate)。**kleene 不构成 multi-match 假阳**(children 扁平,见 §3.2)。 |
| 22 | bracket click 收尾分支 | `KlineChart.vue:93-105`(brackets 分支) | `if (candidateMatchIds.has(p.data.match_id))` → 「候选收尾」:`setHighlightedEvents(match.children) + selectMatch(match.event_id) + clearCandidates()`;否则原路径(同 M)+ 顺手 `clearCandidates()`(防残留)。 |
| 23 | Esc / 空白 click 清候选 | `KlineChart.vue` keydown handler + click handler 空白分支(M #10 #11 基础上) | 追加 `clearCandidates()`(其内含清 pendingDisambigEventId,见 #18)。 |
| 24 | setOption 重渲触发 + 跨上下文清理 | `KlineChart.vue` `effectiveAnalysis` watcher + `view.ts` `selectScanFile` / `selectActivePattern` / `selectSymbol` action 末尾 | (a) watch 数组加入 `view.candidateMatchIds, view.pendingDisambigEventId`;(b) 切上下文的三个 action 末尾显式 `clearCandidates() + clearHighlight() + selectMatch(null) + selectEvent(null)`,防残留 |
| 25 | bracket tooltip 候选态首行 | `chart.ts:837-893`(`buildMarkerTooltipFormatter`) `seriesName === 'brackets'` 分支头 | `if (view.candidateMatchIds.has(match_id)) lines.unshift('候选: click 此 bracket 选中该 group')`;无论候选与否后续都接 M #15 的"组成 N events"段。 |
| **26** | **候选态状态栏组件**(critic v3 必收口 #2 子条款) | 新文件 `path2_web_ui/src/components/CandidateStatusBar.vue` + `KlineChart.vue` 顶部插入 `<CandidateStatusBar />` | watch `view.candidateMatchIds`,size > 0 时显示横条 `候选: ① ③ ⑤ — click 任一 bracket 高亮 / Esc 取消`(ordinal 从 `matches.find(m=>m.event_id===id).ordinal` 拿,1-based ①-⑨,>9 fallback 阿拉伯数字);位置=副图 grid1 顶部 16px banner。组件本身约 30 行 Vue。 |

**不改动**:
- `geometry.ts:47-51` `packBrackets` 保持全局 lane(M 已确认,critic v2 已接受 designer 反驳)
- `DetailSidebar.vue:55` 候选表行 click 保持 `selectEvent`(M 同)
- `view.ts:44` `selectedEventId` ref 保留并存
- M 既有 #1-16 实施(不在本 spec 重复)

---

## 5. 错误处理与边界

### 5.1 数据校验
- multi-match 反查 `matches.filter(...)` 总会返回数组(空数组 = no match,落 ms.length===0 分支),不会抛
- `setCandidateMatches([])` 等价 `clearCandidates()`,前端兜底:#18 内若 ids 为空数组,直接走 `clearCandidates()` 避免 ID 列表显示空

### 5.2 候选 bracket 在 zoom 视窗外
- #25 状态栏组件兜底(总是可见,无论 zoom 状态如何)
- bracket 自身在窗外,用户从状态栏知道当前候选数与序号,可手动 zoom 找过去再 click
- v2.5 增量:dataZoom slider 上加候选 tick 标记(本 spec 不做)

### 5.3 候选态期间 hover/tooltip
- 候选 bracket hover 必须 **preview-only**(可加临时弱高亮预览,但**不动** `highlightedEventIds`),只在 click 确认时才落定
- 实现:tooltip 是 ECharts 内置只读层,不会写 store;但要确认 bracket renderItem 不响应任何 hover state(`emphasis: { disabled: true }`),防止 ECharts 默认 emphasis 修改 fill

### 5.4 切上下文残留
- 切股 / 切 pattern / scan 重跑 三个 action 末尾显式四清(见 #23)
- 测试:在 candidate 态切股,新股加载后 store 应是 [空闲]

### 5.5 kleene role 反查
- `children` 扁平,kleene 多 event 各占独立位置,不构成 multi-match 假阳
- spec/实施时 #20 旁加注释说明此前提,避免审到误读

---

## 6. 测试与验证

### 6.1 单元 / 组件测试
- view.ts:
  - `setCandidateMatches([a,b,c])` → `candidateMatchIds.value` 是 Set{a,b,c}
  - `setCandidateMatches([])` → 等价 clearCandidates(测试边界 #5.1)
  - 切股 action 后 candidate / highlight / selected 全清
- KlineChart.vue 模拟 click(可用 jsdom + vitest):
  - click multi-match event → store 进入 candidate 态、selected 被清、pendingDisambig 写入
  - 同 event 二次 click → store 不变(幂等)
  - candidate 中 click 候选 bracket → 进 selected、candidate 清
- CandidateStatusBar.vue:
  - candidateMatchIds size = 0 → 不渲染
  - size > 0 → 显示对应 ordinal 文字

### 6.2 web-loop 实测(critic v3 + M 共三项)
1. **markArea z 序兼容**:candidate fill alpha 0.35 / selected fill alpha 0.85 与 markArea(灰 0.15)叠加后视觉差异是否清晰可分辨
2. **grid1 加高 + status banner 容量(联合 M+M' 含 #26 banner)**:起步值 grid1 = 26%(sliderShow)/ 24%(noSlider),viewport 600px 时 grid1 ≈ 156px / 144px,扣 banner 16px 后净 ≈ 140px / 128px,5-band 时 bandH ≈ 28 / 25.6px,需容 bracket 6px + 留白 4px + interval lane 2×(7+2)=18px = 28px;5-band 临界,7-band 必挤 → 实测调到 30%(必要时 interval lane 限 1)。 |
3. **multi-match marker pendingDisambig 描边**:`stroke=white lineWidth=1` 在副图 marker 上是否可见(与原 marker fill 对比度);若白边在 matched 态浅色 marker 上对比不足,fallback 改 `lineWidth: 1.5` 或换 `stroke: #000` 黑边。

### 6.3 端到端冒烟(playwright)
- 加载 BTM 这类有 multi-match 的扫描结果
- click multi-match event marker → 看 candidate banner 出现、bracket 变琥珀低 alpha
- click 其中一个 candidate bracket → 看 candidate banner 消失、selected bracket 变琥珀高 alpha、组成员 marker 加琥珀 stroke
- click 主图空白 → 全部清空
- 切股票 → 全部清空

---

## 7. 不进首版 / v2.5 增量(参考)

| 方案 | 启用条件 | 互斥性 |
|---|---|---|
| hover 软高亮(P4) | M' 落地实测后用户明确反馈"频繁 click 太累" | 与 M' 共存(加 hoverHighlightedEventIds 第四层) |
| dataZoom slider 候选 tick | 用户实测"屏外候选 click 不便"(状态栏不够) | 与 M' 共存 |
| bracket 3-5 色编码(P8 简化) | bracket 总数稳定 ≤5 | **与 M' bracket fill 琥珀冲突**,选一 |
| active set 多选(Shift+Click) | 用户需"已选 ① 同时探索 ③⑤ 共享 event" | 需扩 selectedMatchIds 单→set + candidate 并存规则重写 |
| 键盘 j/k 巡视(P7) | 重度键盘党 + 配状态栏 hint | 与 M' 并存 |

---

## 8. 残留未决事项

无。三个 brainstorm 拍板(幂等 click / P5 保留 / pendingDisambig 永久弱描边)+ critic v3 三 P0/P1 必收口已全部并入,无悬而未决项。

若实施时发现 spec 与 mapper 文档 / final_report 冲突,以 **mapper(代码 file:line)** 为最终事实;spec 若需更新,实施 task 末尾起 follow-up issue。

---

## 9. 引用文档

- `docs/research/2026-06-30_path2-web-match-event-correlation/current_interaction_map.md`
- `docs/research/2026-06-30_path2-web-match-event-correlation/final_report.md`(§1.1 M / §1.2 M')
- `docs/research/2026-06-30_path2-web-match-event-correlation/critic_review_v3_m_prime.md`
- `docs/research/2026-06-30_path2-web-match-event-correlation/designer_proposals_v1.md`(v1 八方案 + v2 拍板)
- `docs/research/2026-06-30_path2-web-match-event-correlation/critic_scores_v1.md` / `critic_review_v2.md`(critic 两轮历史)
