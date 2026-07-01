# path2_web Match-Event Disambig (M + M') Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一次性把 M(matched marker ↔ role events 关联可见度基础:bracket 从主图移到副图、selectedMatchId/highlightedEventIds store、双向 click 联动、tooltip 信息层兜底)+ M'(candidate 消歧机制:multi-match event 显式选 group + 候选状态栏)落地,共 26 项改动跨 5 个文件 + 1 个新组件 + 1 个 e2e 用例。

**Architecture:** Vue3 + ECharts + Pinia store(view.ts)。bracket 轴归属从 grid0 移到 grid1(与 role band 行垂直对齐);新增 store ref(`highlightedEventIds` + `candidateMatchIds` + `pendingDisambigEventId`)统一 4 路 click 进入 + 持久态 click only;视觉层借 fill alpha 通道(0.35 候选 / 0.85 已选)区分两态,stroke 通道留给 marker 组高亮琥珀色(避免撞色);多归属 click → candidate 态由 bracket click 收尾;新增 `CandidateStatusBar.vue` 组件解除候选 bracket 视窗外的沉默 click。

**Tech Stack:** Vue 3 Composition API + Pinia + ECharts 5 (custom series renderItem) + Vitest (unit) + Playwright (e2e)

**Spec:** `docs/superpowers/specs/2026-06-30-path2-web-match-event-disambig-design.md`(本 plan 唯一权威依据;研究文档 `docs/research/2026-06-30_path2-web-match-event-correlation/` 仅作 rationale 索引,实施时勿参照其改动表)。

## Global Constraints

- Vue 3 `ref` 持 `Set` **必须整体替换**才触发响应式(`.add()/.delete()` 不触发);所有 Set setter 形如 `ref.value = new Set(...)`。
- bracket renderItem 改 `children[0]`(rect)的 `style.fill` alpha,**绝不动 stroke 通道**(stroke 留给 marker 组高亮);并在 bracket 系列加 `emphasis: { disabled: true }` 防 ECharts 默认 hover 改 fill。
- bracket 三态 **互斥**(candidate 与 selected 不能同时持有);click multi-match event 必须先 `clearHighlight() + selectMatch(null) + selectEvent(null)` 再进 candidate。
- kleene role(`role_index` 值为数组)**不构成 multi-match 假阳**——`MatchDict.children` 扁平,kleene 的多个 events 各占独立位置,同一 event_id 不会在同一 match.children 中出现多次;multi-match 来源**仅**是同一 event_id 被**多个不同 match.children** 共享。
- 切上下文(切股 / 切 pattern / scan 重跑)时显式 **清四样**:`clearCandidates() + clearHighlight() + selectMatch(null) + selectEvent(null)`。
- `geometry.ts:47-51` `packBrackets` **全局 lane 保留**(bracket 跨多 band 无单一归属;ordinal ①..⑨ 全局唯一性与 sidebar 命中匹配列表的序号字面对照绑死)。
- `DetailSidebar.vue:55` 候选表行 click **保持** `selectEvent`(候选表是"未归属"诊断对比工具,反查无 match)。
- `view.ts:44` 既有 `selectedEventId` ref 保留并存(新字段并行,不删旧)。
- 联合 M+M' grid1 加高首版 `26%`(sliderShow)/`24%`(noSlider),含 candidate banner 16px;7-band 实测仍挤则加到 30%。
- 颜色常量统一:候选 `rgba(251,191,36,0.35)` / 已选 `rgba(251,191,36,0.85)` / 组高亮 marker stroke `#fbbf24` lineWidth 1.5 / 焦点 marker stroke `#ffffff` lineWidth 2.5 / pendingDisambig marker stroke `#ffffff` lineWidth 1。

## File Structure

```
path2_web_ui/
├── src/
│   ├── stores/
│   │   ├── view.ts                                修改: Task 1, 2, 7
│   │   └── __tests__/view.test.ts                 新建/扩展: Task 1, 2
│   ├── render/
│   │   └── chart.ts                               修改: Task 3, 4, 5, 9
│   ├── components/
│   │   ├── KlineChart.vue                         修改: Task 6, 7, 10
│   │   ├── DetailSidebar.vue                      修改: Task 8
│   │   ├── CandidateStatusBar.vue                 新建: Task 10
│   │   └── __tests__/
│   │       └── CandidateStatusBar.test.ts         新建: Task 10
└── e2e/
    └── match-event-disambig.spec.ts               新建: Task 11
```

**任务分解原则**:同一文件可被多 task 修改(并非"一 task 一文件"),按"独立可测试 deliverable + reviewer 可独立否决"切分。

---

## Task 1: store M 基础 — highlightedEventIds + actions

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts:44` 附近(紧贴 `selectedEventId` 声明后)+ `view.ts:209` 附近(紧贴 `selectEvent` action 后)
- Test: `path2_web_ui/src/stores/__tests__/view.test.ts`(若不存在则新建)

**Interfaces:**
- Produces:
  - `highlightedEventIds: Ref<ReadonlySet<string>>`(从 store `useViewStore()` 暴露)
  - `setHighlightedEvents(ids: string[]): void` — 整体替换为 `new Set(ids)`
  - `clearHighlight(): void` — 整体替换为 `new Set()`

- [ ] **Step 1: 写失败测试**

打开/新建 `path2_web_ui/src/stores/__tests__/view.test.ts`,在合适的 `describe` 块内追加(若文件不存在则用以下完整结构):

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../view'

describe('view store — highlightedEventIds (Task 1)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('starts empty', () => {
    const view = useViewStore()
    expect(view.highlightedEventIds.size).toBe(0)
  })

  it('setHighlightedEvents replaces with new Set (triggers reactivity)', () => {
    const view = useViewStore()
    const before = view.highlightedEventIds
    view.setHighlightedEvents(['a', 'b', 'c'])
    expect(view.highlightedEventIds.size).toBe(3)
    expect(view.highlightedEventIds.has('a')).toBe(true)
    // ref 必须整体替换:before 与 after 不应是同一 Set 实例
    expect(view.highlightedEventIds).not.toBe(before)
  })

  it('clearHighlight replaces with empty Set', () => {
    const view = useViewStore()
    view.setHighlightedEvents(['a', 'b'])
    view.clearHighlight()
    expect(view.highlightedEventIds.size).toBe(0)
  })

  it('setHighlightedEvents dedupes input (Set semantics)', () => {
    const view = useViewStore()
    view.setHighlightedEvents(['a', 'a', 'b'])
    expect(view.highlightedEventIds.size).toBe(2)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd path2_web_ui && npx vitest run src/stores/__tests__/view.test.ts -t "highlightedEventIds"`
Expected: FAIL with "view.highlightedEventIds is undefined" 或类似(因 store 尚未暴露此字段)。

- [ ] **Step 3: 实现 store 字段 + actions**

打开 `path2_web_ui/src/stores/view.ts`,在 `selectedEventId` 声明附近(line 44 邻近)加 ref;在 `selectEvent` action 附近(line 209 邻近)加两个 action。

ref 声明(加在 `const selectedEventId = ref<string | null>(null)` 之后):

```ts
const highlightedEventIds = ref<ReadonlySet<string>>(new Set())
```

action 声明(加在 `function selectEvent(...)` 之后):

```ts
function setHighlightedEvents(ids: string[]) {
  highlightedEventIds.value = new Set(ids)
}
function clearHighlight() {
  highlightedEventIds.value = new Set()
}
```

`return` 块也要把 3 个新名字加上(`highlightedEventIds, setHighlightedEvents, clearHighlight`)。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd path2_web_ui && npx vitest run src/stores/__tests__/view.test.ts -t "highlightedEventIds"`
Expected: PASS,4 个 it 全绿。

- [ ] **Step 5: 提交**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/src/stores/__tests__/view.test.ts
git commit -m "feat(view): add highlightedEventIds store for M-base group highlight"
```

---

## Task 2: store M' 增量 — candidateMatchIds + pendingDisambigEventId + actions

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts:45` 附近(紧贴 Task 1 加的 `highlightedEventIds` 之后)+ `view.ts:211` 附近(紧贴 Task 1 加的 `clearHighlight` 之后)
- Test: `path2_web_ui/src/stores/__tests__/view.test.ts`(扩展)

**Interfaces:**
- Consumes: Task 1 的 store 模式
- Produces:
  - `candidateMatchIds: Ref<ReadonlySet<string>>`
  - `pendingDisambigEventId: Ref<string | null>`
  - `setCandidateMatches(ids: string[]): void`
  - `clearCandidates(): void` — 同步清 `pendingDisambigEventId`
  - `setPendingDisambig(eid: string | null): void`

- [ ] **Step 1: 写失败测试**

在同一 test 文件追加:

```ts
describe('view store — candidate disambig (Task 2)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('starts empty', () => {
    const view = useViewStore()
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigEventId).toBeNull()
  })

  it('setCandidateMatches replaces Set; reactive integrity', () => {
    const view = useViewStore()
    const before = view.candidateMatchIds
    view.setCandidateMatches(['m1', 'm2', 'm3'])
    expect(view.candidateMatchIds.size).toBe(3)
    expect(view.candidateMatchIds.has('m1')).toBe(true)
    expect(view.candidateMatchIds).not.toBe(before)
  })

  it('setPendingDisambig sets and clears event id', () => {
    const view = useViewStore()
    view.setPendingDisambig('e123')
    expect(view.pendingDisambigEventId).toBe('e123')
    view.setPendingDisambig(null)
    expect(view.pendingDisambigEventId).toBeNull()
  })

  it('clearCandidates clears both candidateMatchIds AND pendingDisambigEventId', () => {
    const view = useViewStore()
    view.setCandidateMatches(['m1', 'm2'])
    view.setPendingDisambig('e123')
    view.clearCandidates()
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigEventId).toBeNull()
  })

  it('setCandidateMatches([]) ALSO clears pendingDisambigEventId (idempotent with clearCandidates)', () => {
    const view = useViewStore()
    view.setCandidateMatches(['m1'])
    view.setPendingDisambig('e1')
    view.setCandidateMatches([])
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigEventId).toBeNull()
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd path2_web_ui && npx vitest run src/stores/__tests__/view.test.ts -t "candidate disambig"`
Expected: FAIL — store 尚未暴露这些字段。

- [ ] **Step 3: 实现 store 字段 + actions**

在 `path2_web_ui/src/stores/view.ts` Task 1 的 `highlightedEventIds` 之后追加 ref:

```ts
const candidateMatchIds = ref<ReadonlySet<string>>(new Set())
const pendingDisambigEventId = ref<string | null>(null)
```

在 Task 1 的 `clearHighlight` 之后追加 actions:

```ts
function setCandidateMatches(ids: string[]) {
  candidateMatchIds.value = new Set(ids)
  // 边界:空输入等价 clear(避免残留 pendingDisambig)
  if (ids.length === 0) pendingDisambigEventId.value = null
}
function clearCandidates() {
  candidateMatchIds.value = new Set()
  pendingDisambigEventId.value = null
}
function setPendingDisambig(eid: string | null) {
  pendingDisambigEventId.value = eid
}
```

`return` 块加 5 个新名字(`candidateMatchIds, pendingDisambigEventId, setCandidateMatches, clearCandidates, setPendingDisambig`)。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd path2_web_ui && npx vitest run src/stores/__tests__/view.test.ts`
Expected: PASS,Task 1 + Task 2 共 9 个 it 全绿。

- [ ] **Step 5: 提交**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/src/stores/__tests__/view.test.ts
git commit -m "feat(view): add candidateMatchIds + pendingDisambigEventId store for M' disambig"
```

---

## Task 3: bracket 从 grid0 主图移到 grid1 副图(轴归属 + grid1 加高 + 字号缩小)

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts:333`(brackets 系列 yAxisIndex/xAxisIndex)、`chart.ts:296-300`(grid 数组)、`chart.ts:495-512`(`renderBracket` 圆圈 text fontSize)

**Interfaces:**
- Produces: bracket 渲染于 grid1 顶部、grid1 高度 26%/24% 含 banner 16px 空间、圆圈数字 fontSize 12

**Note:** 本 task 是纯几何 + 视觉迁移,无 store 交互,通过 web-loop 截图验收;无单元测试。

- [ ] **Step 1: 修改 brackets 系列轴归属(`chart.ts:333` 附近)**

定位 `chart.ts` 中 `brackets` 系列定义(搜 `name: 'brackets'`),把:

```ts
xAxisIndex: 0,
yAxisIndex: 1,
```

改为:

```ts
xAxisIndex: 1,
yAxisIndex: 2,
```

同时在该 series 配置中**追加** `emphasis: { disabled: true }`(防 ECharts 默认 hover 改 bracket 的 fill,与 Task 4 的 fill 三态语义打架):

```ts
emphasis: { disabled: true },
```

`renderBracket` 内 `params.coordSys.y` 自动取 grid1 顶部,几何代码无需改。

- [ ] **Step 2: 修改 grid1 高度(`chart.ts:296-300` grid 数组)**

定位 `grid: [...]` 数组,把 grid[1].height 与 grid[0].height 调整(含 banner 16px 余量):

```ts
grid: [
  { left: 56, right: 16, top: 40, height: (sliderShow ?? true) ? '64%' : '72%' },
  { left: 56, right: 16, top: (sliderShow ?? true) ? '68%' : '76%',
    height: (sliderShow ?? true) ? '26%' : '24%' },
],
```

(原 grid[0] = `'72%'`/`'80%'` 收紧到 `'64%'`/`'72%'`;grid[1] = `'18%'`/`'16%'` 加到 `'26%'`/`'24%'`;grid[1].top 同步从 `'76%'`/`'84%'` 调到 `'68%'`/`'76%'`。)

- [ ] **Step 3: 缩小 bracket 圆圈数字字号(`renderBracket` chart.ts:495-512)**

定位 `renderBracket` 函数内 ZRender text 节点,把 fontSize 从 `MARKER_FONT_SIZE + 4`(=20)改为 `12`,与 bandLabel 视觉对齐(副图 bandH 小,序号字号要缩):

```ts
{
  type: 'text',
  style: {
    text: ordinal,
    fill: '#fff',
    fontSize: 12,
    fontWeight: 'bold',
    textAlign: 'center',
    textVerticalAlign: 'middle',
    x: cx, y: cy,
  },
},
```

(具体行号在 `renderBracket` 内构造圆圈数字 text 的位置,搜 `fontSize: MARKER_FONT_SIZE + 4` 即可定位。)

- [ ] **Step 4: 实测 — web-loop 截图验收**

Run:

```bash
cd /home/yu/PycharmProjects/Trade_Strategy-align
uv run python scripts/run_path2_web.py &
sleep 6
```

用 playwright MCP 截图:导航 `http://localhost:5171` → "打开历史…" → 选 small scan result(如 `2026-06-27 04:26:15`)→ click "Open" → click 一个含 multi-match 的股票(如 `BTM`)→ 截图。

Expected:
- bracket(灰带 + 圆圈数字)出现在副图 grid1 顶部(原主图顶应空)
- 5-band 时 bandH ≈ 28px 容下 bracket 6 + 留白 4 + interval lane 2(若 7-band 挤,记录现象,可能 Task 后期加到 30%)
- 圆圈数字 12pt 字号与 bandLabel 视觉相当
- 主图 K 线纵向空间未明显挤压

清理:`pkill -f "scripts/run_path2_web.py"; rm -f .playwright-mcp/*`

- [ ] **Step 5: 提交**

```bash
git add path2_web_ui/src/render/chart.ts
git commit -m "feat(chart): move bracket from grid0 to grid1 (M #4 #13 #14)"
```

---

## Task 4: bracket renderItem 三态 fill alpha(候选 / 已选)

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts:495-512`(`renderBracket`)
- Consume: Task 1 `highlightedEventIds` / Task 2 `candidateMatchIds`(via `useViewStore()`)

**Interfaces:**
- 渲染规则:bracket rect fill 按 `selectedMatchId === match_id` > `candidateMatchIds.has(match_id)` > 默认 `#64748b` 优先级三态;不动 stroke。

**Note:** `selectedMatchId` 已在 view store 既有(spec §3.1 提到,M 基础前已存在);若实际未存在,需先在 Task 1 等价位置加(本 task 假定它存在)。

- [ ] **Step 1: 修改 `renderBracket` 接收 store ref 参数**

`renderBracket` 是纯函数 + ECharts custom renderItem 闭包模式,需通过 `buildKlineOption` 注入 store。在 `chart.ts` `buildKlineOption` 顶部增加参数(若 input 接口已有 selectedMatchId 类似字段,直接复用;否则在 `BandRenderInput` 接口追加):

```ts
export interface BandRenderInput {
  // 既有字段...
  selectedMatchId?: string | null
  candidateMatchIds?: ReadonlySet<string>
}
```

`buildKlineOption` 内构造 `renderBracket` 的闭包工厂(若现状 `renderBracket` 是顶层函数,改为 `makeRenderBracket(selectedMatchId, candidateMatchIds)` factory,以闭包持有 store snapshot):

```ts
function makeRenderBracket(
  selectedMatchId: string | null | undefined,
  candidateMatchIds: ReadonlySet<string>,
) {
  return function renderBracket(params: any, api: any) {
    // ... 既有几何代码 ...
    const matchId = (params.data && params.data.match_id) as string | undefined
    const isSelected = !!matchId && selectedMatchId === matchId
    const isCandidate = !!matchId && candidateMatchIds.has(matchId)
    const fill = isSelected
      ? 'rgba(251, 191, 36, 0.85)'      // 已选 高 alpha
      : isCandidate
        ? 'rgba(251, 191, 36, 0.35)'    // 候选 低 alpha
        : '#64748b'                      // 默认 灰
    return {
      type: 'group',
      children: [
        { type: 'rect', shape: { /* ... */ }, style: { fill /* 不动 stroke */ } },
        { type: 'text', style: { /* Task 3 已定的 fontSize 12 */ } },
      ],
    }
  }
}
```

brackets 系列内 `renderItem` 字段从 `renderBracket` 改为 `makeRenderBracket(selectedMatchId, candidateMatchIds ?? new Set())`。

- [ ] **Step 2: 在 KlineChart.vue 调用 buildKlineOption 时透传新字段**

打开 `path2_web_ui/src/components/KlineChart.vue`,找到 `buildKlineOption(bars, events, matches, {...})` 调用,在 input 对象内追加:

```ts
selectedMatchId: view.selectedMatchId,
candidateMatchIds: view.candidateMatchIds,
```

- [ ] **Step 3: 实测 — 视觉验收**

启动 web-loop(同 Task 3 Step 4 命令)+ playwright 截图。

Expected:
- 默认状态 bracket 灰色(`#64748b`),无变化
- 手动用 evaluate 注入 store 改 `selectedMatchId`:`window.__e2e.view.selectMatch('某-match-id')` → 对应 bracket fill 变琥珀高 alpha
- 手动改 `candidateMatchIds`:`window.__e2e.view.setCandidateMatches(['某-match-id','另-match-id'])` → 对应 brackets fill 变琥珀低 alpha
- selected 与 candidate 同时持有同一 match_id 时,fill 走 selected(0.85)

清理同 Task 3 Step 4。

- [ ] **Step 4: 提交**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/src/components/KlineChart.vue
git commit -m "feat(chart): bracket renderItem three-state fill alpha (M #3 / M' #19)"
```

---

## Task 5: highlight 系列三分支(group / focus / pendingDisambig)

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts:205-234`(高亮分流逻辑)、`chart.ts:417-459`(`makeRenderHighlight`)、`chart.ts:465-492`(`makeRenderPricePointHighlight`)
- Consume: Task 1 `highlightedEventIds` / Task 2 `pendingDisambigEventId` / 既有 `selectedEventId`

**Interfaces:**
- highlightData 由三类分流构成:`kind: 'group' | 'focus' | 'pendingDisambig'`
  - `group`:`highlightedEventIds.has(d.event_id)` 命中 → stroke `#fbbf24` lineWidth 1.5
  - `focus`:`selectedEventId === d.event_id` → stroke `#ffffff` lineWidth 2.5 + fill 轻染
  - `pendingDisambig`:`d.event_id === pendingDisambigEventId` → stroke `#ffffff` lineWidth 1(细弱描边)
- 优先级 focus > group > pendingDisambig(同一 marker 三态命中时,focus 覆盖 group 覆盖 pendingDisambig)

- [ ] **Step 1: 在 BandRenderInput 接口加新字段**

`chart.ts` 顶部 `BandRenderInput` 接口追加:

```ts
highlightedEventIds?: ReadonlySet<string>
pendingDisambigEventId?: string | null
```

- [ ] **Step 2: 改 highlightData 分流(`chart.ts:205-234` 附近)**

定位 `buildKlineOption` 内构造 `highlightData` / `highlightPriceData` 的逻辑,改为按三类各 push:

```ts
const highlightData: Array<{ value: number[]; event_id: string; kind: 'group' | 'focus' | 'pendingDisambig' }> = []
const highlightPriceData: Array<{ value: number[]; event_id: string; kind: 'group' | 'focus' | 'pendingDisambig' }> = []

// group 高亮(M):highlightedEventIds 命中
if (highlightedEventIds && highlightedEventIds.size > 0) {
  for (const d of pointData) {
    if (highlightedEventIds.has(d.event_id)) highlightData.push({ ...d, kind: 'group' })
  }
  for (const d of intervalData) {
    if (highlightedEventIds.has(d.event_id)) highlightData.push({ ...d, kind: 'group' })
  }
  for (const d of pricePointData) {
    if (highlightedEventIds.has(d.event_id)) highlightPriceData.push({ ...d, kind: 'group' })
  }
}

// focus 单焦点(原 M):selectedEventId 命中(优先级最高,后 push 覆盖渲染顺序)
if (selectedEventId) {
  const selPoint = pointData.find((d) => d.event_id === selectedEventId)
  if (selPoint) highlightData.push({ ...selPoint, kind: 'focus' })
  else {
    const selInterval = intervalData.find((d) => d.event_id === selectedEventId)
    if (selInterval) highlightData.push({ ...selInterval, kind: 'focus' })
    else {
      const selPricePoint = pricePointData.find((d) => d.event_id === selectedEventId)
      if (selPricePoint) highlightPriceData.push({ ...selPricePoint, kind: 'focus' })
    }
  }
}

// pendingDisambig 弱反馈(M'):pendingDisambigEventId 命中
if (pendingDisambigEventId) {
  const pd = pointData.find((d) => d.event_id === pendingDisambigEventId)
  if (pd) highlightData.push({ ...pd, kind: 'pendingDisambig' })
  else {
    const pi = intervalData.find((d) => d.event_id === pendingDisambigEventId)
    if (pi) highlightData.push({ ...pi, kind: 'pendingDisambig' })
    else {
      const pp = pricePointData.find((d) => d.event_id === pendingDisambigEventId)
      if (pp) highlightPriceData.push({ ...pp, kind: 'pendingDisambig' })
    }
  }
}
```

- [ ] **Step 3: 改 `makeRenderHighlight` 三分支(`chart.ts:417-459`)**

定位 `makeRenderHighlight` 函数(它是工厂返回 renderItem 闭包),改 style 按 kind 分流:

```ts
function makeRenderHighlight(/* ... 既有签名 ... */) {
  return function renderHighlight(params: any, api: any) {
    // ... 既有几何代码 取 x/y ...
    const kind = (params.data && params.data.kind) as 'group' | 'focus' | 'pendingDisambig'
    let style: { stroke: string; lineWidth: number; fill?: string }
    if (kind === 'focus') {
      style = { stroke: '#ffffff', lineWidth: 2.5, fill: /* role 色 +18% 亮度(沿用 M 原描述,可暂留同色) */ undefined }
    } else if (kind === 'group') {
      style = { stroke: '#fbbf24', lineWidth: 1.5 }
    } else { // pendingDisambig
      style = { stroke: '#ffffff', lineWidth: 1 }
    }
    return {
      type: /* 与既有相同的几何 type */ 'polygon',
      shape: /* 既有几何 shape */ { /* ... */ },
      style,
    }
  }
}
```

**Note(focus fill 轻染)**:M 原 spec 写 "fill +18% 亮度",首版可暂留 fill undefined 让 ECharts 复用 marker fill;若 web-loop 实测发现 focus 与 group 视觉太接近,补 fill 计算(从 role 色 RGB +18% L)。这是 Task 5 内的尾巴优化,落实施时记录。

- [ ] **Step 4: 同步改 `makeRenderPricePointHighlight`(`chart.ts:465-492`)**

同 Step 3 思路,price-point 的 highlight 三分支(只需 group / focus / pendingDisambig 的 stroke 处理;price-point 几何是圆角矩形,style 处理逻辑一致)。

- [ ] **Step 5: KlineChart.vue 透传新字段到 buildKlineOption**

打开 `KlineChart.vue`,在 `buildKlineOption({...})` input 内追加:

```ts
highlightedEventIds: view.highlightedEventIds,
pendingDisambigEventId: view.pendingDisambigEventId,
```

- [ ] **Step 6: 实测 — playwright 注入 store 验收**

启动 web-loop,加载股票(BTM 等含 multi-match):

```js
// playwright evaluate
window.__e2e.view.setHighlightedEvents(['<某 event_id>', '<另一个 event_id>'])
// → 对应 marker 加琥珀 stroke 1.5px
window.__e2e.view.selectEvent('<另一 event_id>')
// → 该 marker 加白 stroke 2.5px(focus 优先)
window.__e2e.view.setPendingDisambig('<第三 event_id>')
// → 该 marker 加白 stroke 1px(弱反馈)
```

Expected: 三态视觉可区分,优先级 focus > group > pendingDisambig 正确(同一 marker 命中多类时,focus 在最上覆盖)。

清理同 Task 3 Step 4。

- [ ] **Step 7: 提交**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/src/components/KlineChart.vue
git commit -m "feat(chart): highlight series three-branch (group/focus/pendingDisambig)"
```

---

## Task 6: 图上 click 接线(marker 分流 + brackets 候选收尾)

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue:93-105`(`chart.on('click', ...)`)
- Consume: Task 1 `setHighlightedEvents/clearHighlight` / Task 2 `setCandidateMatches/clearCandidates/setPendingDisambig` / `effectiveAnalysis.value.matches`(既有)

**Interfaces:**
- `chart.on('click', p)` 单 handler 内分流:
  - `p.seriesName === 'brackets'` → bracket click 收尾分支(候选收尾 vs 直接选)
  - `p.seriesName ∈ {points, intervals, price-points, satellites}` → marker click 分流(ms.length 0/1/>1)
  - `p === null`(空白)→ 清四样

- [ ] **Step 1: 写失败测试(component-level,vitest + jsdom)**

新建 `path2_web_ui/src/components/__tests__/KlineChart-click.test.ts`:

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../../stores/view'

describe('KlineChart click handler (Task 6)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  // 模拟 handler 提取出来便于测试:把 click handler 从 KlineChart.vue 内部抽到一个纯函数 handleChartClick(p, matches, view)
  // (Step 3 会实现这个 export)
  it('marker click with ms.length === 0 → selectEvent (M fallback)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../KlineChart')
    const matches = [{ event_id: 'm1', children: ['e_other'], ordinal: 1 }]
    handleChartClick({ seriesName: 'points', data: { event_id: 'e_solo' } }, matches, view)
    expect(view.selectedEventId).toBe('e_solo')
    expect(view.candidateMatchIds.size).toBe(0)
  })

  it('marker click with ms.length === 1 → setHighlighted + selectMatch + selectEvent', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../KlineChart')
    const matches = [{ event_id: 'm1', children: ['eA', 'eB', 'eC'], ordinal: 1 }]
    handleChartClick({ seriesName: 'intervals', data: { event_id: 'eA' } }, matches, view)
    expect(view.selectedMatchId).toBe('m1')
    expect(view.highlightedEventIds.size).toBe(3)
    expect(view.selectedEventId).toBe('eA')
    expect(view.candidateMatchIds.size).toBe(0)  // 任何分支先 clearCandidates 保守清残
  })

  it('marker click with ms.length > 1 → candidate + pendingDisambig (no selected)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../KlineChart')
    const matches = [
      { event_id: 'm1', children: ['eShared', 'eA'], ordinal: 1 },
      { event_id: 'm3', children: ['eShared', 'eB'], ordinal: 3 },
      { event_id: 'm5', children: ['eShared', 'eC'], ordinal: 5 },
    ]
    handleChartClick({ seriesName: 'points', data: { event_id: 'eShared' } }, matches, view)
    expect(view.candidateMatchIds.size).toBe(3)
    expect(view.candidateMatchIds.has('m1')).toBe(true)
    expect(view.candidateMatchIds.has('m3')).toBe(true)
    expect(view.candidateMatchIds.has('m5')).toBe(true)
    expect(view.pendingDisambigEventId).toBe('eShared')
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.highlightedEventIds.size).toBe(0)
  })

  it('idempotent: click same multi-match event twice keeps candidate', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../KlineChart')
    const matches = [
      { event_id: 'm1', children: ['eShared'], ordinal: 1 },
      { event_id: 'm2', children: ['eShared'], ordinal: 2 },
    ]
    handleChartClick({ seriesName: 'points', data: { event_id: 'eShared' } }, matches, view)
    const sizeBefore = view.candidateMatchIds.size
    handleChartClick({ seriesName: 'points', data: { event_id: 'eShared' } }, matches, view)
    expect(view.candidateMatchIds.size).toBe(sizeBefore)
    expect(view.pendingDisambigEventId).toBe('eShared')
  })

  it('bracket click on candidate match → finalize: setHighlighted + selectMatch + clearCandidates', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../KlineChart')
    const matches = [
      { event_id: 'm1', children: ['eA', 'eB'], ordinal: 1 },
      { event_id: 'm3', children: ['eA', 'eC'], ordinal: 3 },
    ]
    // 先进 candidate
    handleChartClick({ seriesName: 'points', data: { event_id: 'eA' } }, matches, view)
    expect(view.candidateMatchIds.size).toBe(2)
    // 再 click 候选中的 bracket m3
    handleChartClick({ seriesName: 'brackets', data: { match_id: 'm3' } }, matches, view)
    expect(view.selectedMatchId).toBe('m3')
    expect(view.highlightedEventIds.size).toBe(2)
    expect(view.highlightedEventIds.has('eA')).toBe(true)
    expect(view.highlightedEventIds.has('eC')).toBe(true)
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigEventId).toBeNull()
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd path2_web_ui && npx vitest run src/components/__tests__/KlineChart-click.test.ts`
Expected: FAIL with "Cannot find export `handleChartClick`" 或类似。

- [ ] **Step 3: 把 click handler 提取为可测试纯函数,实现新分流**

打开 `path2_web_ui/src/components/KlineChart.vue`,找到 `chart.on('click', ...)`(L93-105 附近),把内部逻辑提取到模块顶层 `<script setup>` 内的 export(或新建 `KlineChart.ts` sibling 模块,在 `.vue` 里 import)。

为简单起见,推荐在 `.vue` `<script setup>` 顶部定义 `export function handleChartClick(p, matches, view)`(Vue SFC `<script setup>` 不直接支持 export,需新建 `KlineChart.ts` sibling 文件):

```ts
// path2_web_ui/src/components/KlineChart.ts
import type { MatchDict } from '../types'
import type { useViewStore } from '../stores/view'

type ChartClickPayload = {
  seriesName?: string
  data?: { event_id?: string; match_id?: string }
} | null

export function handleChartClick(
  p: ChartClickPayload,
  matches: MatchDict[],
  view: ReturnType<typeof useViewStore>,
): void {
  // 空白 click → 清四样
  if (!p || !p.seriesName) {
    view.clearCandidates()
    view.clearHighlight()
    view.selectMatch(null)
    view.selectEvent(null)
    return
  }

  // brackets 分支
  if (p.seriesName === 'brackets' && p.data?.match_id) {
    const matchId = p.data.match_id
    const match = matches.find((m) => m.event_id === matchId)
    if (!match) return
    // 候选收尾:若该 bracket 在候选集中,选定 + 清候选
    // 非候选 click:照常选定 + 顺手清候选(防残留)
    view.setHighlightedEvents(match.children)
    view.selectMatch(matchId)
    view.clearCandidates()
    return
  }

  // marker 分支(points / intervals / price-points / satellites)
  const markerSeries = ['points', 'intervals', 'price-points', 'satellites']
  if (markerSeries.includes(p.seriesName) && p.data?.event_id) {
    const eventId = p.data.event_id
    const ms = matches.filter((m) => m.children.includes(eventId))

    if (ms.length === 0) {
      // M fallback:不归属任何 match 的 event(候选表样式)
      view.clearCandidates()
      view.selectEvent(eventId)
      return
    }
    if (ms.length === 1) {
      view.clearCandidates()
      view.setHighlightedEvents(ms[0].children)
      view.selectMatch(ms[0].event_id)
      view.selectEvent(eventId)
      return
    }
    // ms.length > 1:多归属 → 进 candidate(互斥清 selected)
    view.selectMatch(null)
    view.clearHighlight()
    view.selectEvent(null)
    view.setCandidateMatches(ms.map((m) => m.event_id))
    view.setPendingDisambig(eventId)
    return
  }
}
```

在 `KlineChart.vue` `<script setup>` 内 `import { handleChartClick } from './KlineChart'`,把 `chart.on('click', p => handleChartClick(p, effectiveAnalysis.value?.matches ?? [], view))` 接上。

**Note**:`view.selectMatch` 既有(spec §3.1 提到),若实际不存在,需在 Task 1 等价位置补加 `selectMatch(id: string | null)` action。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd path2_web_ui && npx vitest run src/components/__tests__/KlineChart-click.test.ts`
Expected: PASS,5 个 it 全绿。

- [ ] **Step 5: 实测 — playwright 端到端 click**

启动 web-loop 加载 BTM:
- click 一个 multi-match marker → 看 bracket 变琥珀低 alpha + 该 marker 加白 stroke 1px(pendingDisambig)
- click 候选中某 bracket → 看 bracket 变琥珀高 alpha + 候选清空 + 组成员 marker 加琥珀 stroke 1.5px
- click 主图空白 → 一切清空

清理同 Task 3 Step 4。

- [ ] **Step 6: 提交**

```bash
git add path2_web_ui/src/components/KlineChart.vue path2_web_ui/src/components/KlineChart.ts path2_web_ui/src/components/__tests__/KlineChart-click.test.ts
git commit -m "feat(KlineChart): click router for marker/bracket with candidate disambig (M #7 / M' #21 #22)"
```

---

## Task 7: Esc / 空白 click 清四样 + watch + 跨上下文清理

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue`(keydown 监听 + effectiveAnalysis watcher)
- Modify: `path2_web_ui/src/stores/view.ts`(`selectScanFile` / `selectActivePattern` / `selectSymbol` action 末尾追加清四样)

**Interfaces:**
- Esc 键(非 input 焦点)→ 清四样 = `clearCandidates() + clearHighlight() + selectMatch(null) + selectEvent(null)`
- 主图空白 click 清四样:已在 Task 6 handleChartClick 实现
- watch 数组加新 ref 触发 setOption 重渲
- 切上下文 action 末尾显式清四样

- [ ] **Step 1: 写失败测试**

在 `path2_web_ui/src/stores/__tests__/view.test.ts` 追加:

```ts
describe('view store — cross-context cleanup (Task 7)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('selectSymbol clears candidate + highlight + selected', () => {
    const view = useViewStore()
    view.setHighlightedEvents(['e1', 'e2'])
    view.setCandidateMatches(['m1'])
    view.setPendingDisambig('e1')
    view.selectMatch('m1')
    view.selectEvent('e1')
    view.selectSymbol('NEW_TICKER')
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.pendingDisambigEventId).toBeNull()
  })

  // 同样测 selectScanFile / selectActivePattern(若 store 暴露)
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd path2_web_ui && npx vitest run src/stores/__tests__/view.test.ts -t "cross-context cleanup"`
Expected: FAIL — selectSymbol 当前不清。

- [ ] **Step 3: 在 view.ts 切上下文 action 末尾追加清四样**

定位 `view.ts` 内 `selectSymbol` / `selectScanFile` / `selectActivePattern` 三个 action(若有任一不存在则忽略不存在的),各在最后追加:

```ts
clearCandidates()
clearHighlight()
selectMatch(null)
selectEvent(null)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd path2_web_ui && npx vitest run src/stores/__tests__/view.test.ts -t "cross-context cleanup"`
Expected: PASS。

- [ ] **Step 5: KlineChart.vue 加 Esc keydown 监听**

在 `<script setup>` `onMounted` 内:

```ts
function onKeyDown(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  const target = e.target as HTMLElement | null
  // 不拦 input / textarea / contenteditable 焦点
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
  view.clearCandidates()
  view.clearHighlight()
  view.selectMatch(null)
  view.selectEvent(null)
}
window.addEventListener('keydown', onKeyDown)
```

在 `onBeforeUnmount` 内 `window.removeEventListener('keydown', onKeyDown)`。

- [ ] **Step 6: KlineChart.vue 扩展 effectiveAnalysis watcher**

找到现有 watcher(触发 setOption 重渲),把 watch 数组扩展为包含 M+M' 新 ref:

```ts
watch(
  [effectiveAnalysis, () => view.selectedMatchId, () => view.highlightedEventIds,
   () => view.candidateMatchIds, () => view.pendingDisambigEventId, () => view.selectedEventId],
  () => {
    // 既有 setOption 调用,带新字段(同 Task 4 / Task 5 已在 buildKlineOption 透传)
    if (!effectiveAnalysis.value) return
    chart?.setOption(buildKlineOption(/* ... */))
  },
  { deep: false }
)
```

- [ ] **Step 7: 实测 — playwright 验收**

启动 web-loop 加载 BTM:
- 进 candidate 态(click multi-match event)→ 按 Esc → 一切清空
- 不进 input 时 Esc 生效;focus 一个 input 后 Esc 不应清(测试焦点判断)

清理同 Task 3 Step 4。

- [ ] **Step 8: 提交**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/src/components/KlineChart.vue path2_web_ui/src/stores/__tests__/view.test.ts
git commit -m "feat(view+KlineChart): Esc clears all + cross-context cleanup + watch new refs"
```

---

## Task 8: Sidebar click 接线(命中匹配行 + trace role 行)

**Files:**
- Modify: `path2_web_ui/src/components/DetailSidebar.vue:75-89, 220-242`

**Interfaces:**
- 命中匹配行 click → `setHighlightedEvents(m.children) + selectMatch(m.event_id) + clearCandidates()`
- trace role 行 click → **保持** `selectEvent` 单焦点不变(不触组高亮,不清 candidate)

- [ ] **Step 1: 修改 `selectMatchAndHighlight`(DetailSidebar.vue:237-242 附近)**

定位 `selectMatchAndHighlight` 函数(或等价的命中匹配行 click handler):

```ts
function selectMatchAndHighlight(matchId: string, children: string[]) {
  view.setHighlightedEvents(children)
  view.selectMatch(matchId)
  view.clearCandidates()           // 顺手清候选,防残留
}
```

- [ ] **Step 2: trace role 行 click 保持原样**

确认 `selectRoleEvent`(line 231-234 附近)仍是 `view.selectEvent(roleEventId(val))`,**不要追加** setHighlightedEvents/setCandidateMatches。这是 trace role 行的单焦点语义(调试 focus 单 role 的属性)。

- [ ] **Step 3: 实测 — playwright 验收**

启动 web-loop,加载 BTM,展开 sidebar:
- click sidebar 命中匹配某行 → 看 bracket 变琥珀 + 组成员 marker 加琥珀 stroke
- click trace role 某行 → 看该 role 对应 marker 加白 stroke(focus),其他 marker 不变

清理同 Task 3 Step 4。

- [ ] **Step 4: 提交**

```bash
git add path2_web_ui/src/components/DetailSidebar.vue
git commit -m "feat(DetailSidebar): match row click integrates with group highlight (M #8 #9)"
```

---

## Task 9: Tooltip — bracket 组成段 + 候选首行 + marker 归属节

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts:837-893`(`buildMarkerTooltipFormatter`)
- Consume: Task 2 `candidateMatchIds`(via view store snapshot)

**Interfaces:**
- bracket hover tooltip:候选态前置首行 `候选: click 此 bracket 选中该 group`;接 `组成 (N events):\n  role: eid (×N kleene)\n  ...`
- marker hover tooltip:末尾追加 `归属: match ① ③ ⑤`(无论单/多归属都显示)

- [ ] **Step 1: 修改 `buildMarkerTooltipFormatter` 入参与 brackets 分支**

定位 `buildMarkerTooltipFormatter`(L837-893),把 input 接口扩展接收 store snapshot 与 matches:

```ts
export function buildMarkerTooltipFormatter(
  tooltipResolver: ((eid: string) => TooltipPayload) | undefined,
  matchLabel: ((mid: string) => string | null) | undefined,
  ctx: {
    matches: MatchDict[]
    candidateMatchIds: ReadonlySet<string>
  },
) {
  return (params: any): string => {
    // ... 既有逻辑 ...
    if (params.seriesName === 'brackets' && params.data?.match_id) {
      const matchId = params.data.match_id as string
      const lines: string[] = []
      // 1. 候选态首行
      if (ctx.candidateMatchIds.has(matchId)) {
        lines.push('候选: click 此 bracket 选中该 group')
      }
      // 2. 既有 match 顶行 (matchLabel)
      const ml = matchLabel?.(matchId)
      if (ml) lines.push(ml)
      // 3. 组成段
      const match = ctx.matches.find((m) => m.event_id === matchId)
      if (match) {
        lines.push(`组成 (${match.children.length} events):`)
        for (const [roleKey, val] of Object.entries(match.role_index ?? {})) {
          if (Array.isArray(val)) {
            const first = val[0] ?? '?'
            lines.push(`  ${roleKey}: ${first} (×${val.length} kleene)`)
          } else {
            lines.push(`  ${roleKey}: ${val}`)
          }
        }
      }
      // 4. 既有 endRole event 三段属性(tooltipResolver)保留:若 bracket data.event_id 由 endRole 注入存在,
      //    append tooltipResolver(event_id) 的 identity/clauses/raw 三段渲染(沿用 M 既有逻辑,不删)
      if (tooltipResolver && params.data.event_id) {
        const payload = tooltipResolver(params.data.event_id)
        if (payload) {
          lines.push('---')
          lines.push(`<b>${payload.identity.roles.join(', ')}</b> @ ${payload.identity.dateStart}${payload.identity.dateEnd ? ` ~ ${payload.identity.dateEnd}` : ''}`)
          for (const c of payload.clauses) {
            const ok = c.satisfied ? '✓' : '✗'
            lines.push(`  ${ok} ${c.role}.${c.cid}: ${String(c.measured)} ${c.op ?? ''} ${String(c.threshold)}`)
          }
        }
      }
      return lines.join('<br/>')
    }
    // ... 既有 points/intervals/price-points/satellites 分支 ...
  }
}
```

- [ ] **Step 2: 在 marker 分支末尾追加归属节**

在 `params.seriesName ∈ {points, intervals, price-points, satellites}` 既有分支末尾(返回前)追加:

```ts
// marker 归属节:列出该 event 所属的全部 match ordinal
if (params.data?.event_id && ctx.matches.length > 0) {
  const ownedBy = ctx.matches.filter((m) => m.children.includes(params.data.event_id))
  if (ownedBy.length > 0) {
    const ords = ownedBy.map((m) => '①②③④⑤⑥⑦⑧⑨'[(m.ordinal ?? 1) - 1] ?? String(m.ordinal))
    lines.push(`归属: match ${ords.join(' ')}`)
  }
}
```

(`lines` 是该分支既有的 tooltip 行数组,Append 后返回 `lines.join('<br/>')`。)

- [ ] **Step 3: KlineChart.vue 透传 matches + candidateMatchIds 到 buildMarkerTooltipFormatter**

在 `KlineChart.vue` 调用 `buildKlineOption` 处,buildKlineOption 内调 `buildMarkerTooltipFormatter` 的位置(grep `buildMarkerTooltipFormatter` 定位),把新 ctx 对象传入:

```ts
const tooltipFormatter = buildMarkerTooltipFormatter(
  tooltipResolver,
  matchLabel,
  {
    matches: matches,
    candidateMatchIds: candidateMatchIds ?? new Set(),
  },
)
```

- [ ] **Step 4: 实测 — playwright hover 验收**

启动 web-loop,加载 BTM:
- hover 一个 bracket → tooltip 显示 "组成 (N events): role: eid ..."
- 进 candidate 态后 hover 候选 bracket → tooltip 首行 "候选: click 此 bracket 选中该 group" + 后接组成段
- hover 一个 multi-match marker → tooltip 末尾 "归属: match ① ③ ⑤"

清理同 Task 3 Step 4。

- [ ] **Step 5: 提交**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/src/components/KlineChart.vue
git commit -m "feat(tooltip): bracket composition + candidate hint + marker ownership (M #15 #16 / M' #25)"
```

---

## Task 10: CandidateStatusBar.vue 组件

**Files:**
- Create: `path2_web_ui/src/components/CandidateStatusBar.vue`
- Create: `path2_web_ui/src/components/__tests__/CandidateStatusBar.test.ts`
- Modify: `path2_web_ui/src/components/KlineChart.vue`(顶部插入 `<CandidateStatusBar />`)

**Interfaces:**
- `<CandidateStatusBar />` watch `view.candidateMatchIds`,size > 0 时显示横条 `候选: ① ③ ⑤ — click 任一 bracket 高亮 / Esc 取消`
- ordinal 从 `matches.find(m=>m.event_id===id).ordinal` 拿,1-based ①-⑨,>9 fallback 阿拉伯数字
- 位置:副图 grid1 顶部 16px banner(在 ECharts canvas 之上的 DOM 层,absolute 定位)

- [ ] **Step 1: 写失败测试**

新建 `path2_web_ui/src/components/__tests__/CandidateStatusBar.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../../stores/view'
import CandidateStatusBar from '../CandidateStatusBar.vue'

describe('CandidateStatusBar (Task 10)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('renders nothing when candidateMatchIds is empty', () => {
    const w = mount(CandidateStatusBar, { props: { matches: [] } })
    expect(w.find('.candidate-banner').exists()).toBe(false)
  })

  it('renders banner with ordinal symbols when candidate has matches', async () => {
    const view = useViewStore()
    const matches = [
      { event_id: 'm1', ordinal: 1, children: [], role_index: {} },
      { event_id: 'm3', ordinal: 3, children: [], role_index: {} },
      { event_id: 'm5', ordinal: 5, children: [], role_index: {} },
    ]
    const w = mount(CandidateStatusBar, { props: { matches } })
    view.setCandidateMatches(['m1', 'm3', 'm5'])
    await w.vm.$nextTick()
    expect(w.find('.candidate-banner').exists()).toBe(true)
    const text = w.text()
    expect(text).toContain('①')
    expect(text).toContain('③')
    expect(text).toContain('⑤')
    expect(text).toContain('click 任一 bracket')
    expect(text).toContain('Esc 取消')
  })

  it('falls back to arabic for ordinal > 9', async () => {
    const view = useViewStore()
    const matches = [{ event_id: 'm10', ordinal: 10, children: [], role_index: {} }]
    const w = mount(CandidateStatusBar, { props: { matches } })
    view.setCandidateMatches(['m10'])
    await w.vm.$nextTick()
    expect(w.text()).toContain('10')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd path2_web_ui && npx vitest run src/components/__tests__/CandidateStatusBar.test.ts`
Expected: FAIL — 组件不存在。

- [ ] **Step 3: 实现 CandidateStatusBar.vue**

新建 `path2_web_ui/src/components/CandidateStatusBar.vue`:

```vue
<template>
  <div v-if="ordinalChars.length > 0" class="candidate-banner">
    候选: {{ ordinalChars.join(' ') }} — click 任一 bracket 高亮 / Esc 取消
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import type { MatchDict } from '../types'

const props = defineProps<{ matches: MatchDict[] }>()
const view = useViewStore()
const { candidateMatchIds } = storeToRefs(view)

const ORDINAL_CHARS = '①②③④⑤⑥⑦⑧⑨'

const ordinalChars = computed<string[]>(() => {
  if (candidateMatchIds.value.size === 0) return []
  const out: string[] = []
  for (const id of candidateMatchIds.value) {
    const m = props.matches.find((mm) => mm.event_id === id)
    const ord = m?.ordinal ?? 0
    if (ord >= 1 && ord <= 9) out.push(ORDINAL_CHARS[ord - 1])
    else if (ord > 9) out.push(String(ord))
  }
  return out
})
</script>

<style scoped>
.candidate-banner {
  height: 16px;
  line-height: 16px;
  padding: 0 8px;
  font-size: 12px;
  color: #fbbf24;
  background: rgba(0, 0, 0, 0.04);
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  user-select: none;
}
</style>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd path2_web_ui && npx vitest run src/components/__tests__/CandidateStatusBar.test.ts`
Expected: PASS,3 个 it 全绿。

- [ ] **Step 5: 在 KlineChart.vue 顶部插入 `<CandidateStatusBar :matches="effectiveAnalysis?.matches ?? []" />`**

打开 `KlineChart.vue` `<template>`,在 ECharts canvas 容器之上(或副图 grid1 视觉位置对应的 DOM 层级)插入:

```vue
<template>
  <div class="kline-chart-wrap">
    <!-- ... 既有 toolbar / canvas 等 ... -->
    <CandidateStatusBar :matches="effectiveAnalysis?.matches ?? []" />
    <!-- canvas 容器 -->
    <div ref="chartEl" class="kline-canvas" />
  </div>
</template>
```

`<script setup>` import:

```ts
import CandidateStatusBar from './CandidateStatusBar.vue'
```

**Note(几何位置)**:首版直接放 ECharts canvas 之上的 DOM 流;若实测发现 banner 与 grid1 顶部不对齐,改用 `position: absolute; top: <计算 grid1 顶部 y>;` 精确定位。Task 3 已给 grid1 加高 26% 预留 banner 空间(扣 banner 16px 后净 grid1 ≈ 140px),banner 16px 与 grid1 顶部刚好相邻,简单 DOM 流即可。

- [ ] **Step 6: 实测 — playwright 验收**

启动 web-loop,加载 BTM:
- 默认无 candidate → banner 不显示
- click multi-match event 进 candidate → banner 出现 "候选: ① ③ ⑤ — click 任一 bracket 高亮 / Esc 取消"
- click 候选 bracket 收尾 → banner 消失

清理同 Task 3 Step 4。

- [ ] **Step 7: 提交**

```bash
git add path2_web_ui/src/components/CandidateStatusBar.vue path2_web_ui/src/components/__tests__/CandidateStatusBar.test.ts path2_web_ui/src/components/KlineChart.vue
git commit -m "feat(CandidateStatusBar): banner for candidate disambig (M' #26)"
```

---

## Task 11: E2E 冒烟测试(playwright)

**Files:**
- Create: `path2_web_ui/e2e/match-event-disambig.spec.ts`

**Interfaces:**
- 端到端验证 M+M' 主要交互路径(click 多归属 → candidate → 收尾 / 单归属 → 直接 selected / Esc 清空 / 切股清空)

- [ ] **Step 1: 新建 e2e 用例**

新建 `path2_web_ui/e2e/match-event-disambig.spec.ts`:

```ts
import { test, expect } from '@playwright/test'

const SCAN_FILE_ROW_TEXT = '2026-06-27 04:26:15'  // 小扫描结果,实测可换
const MULTI_MATCH_TICKER = 'BTM'                    // 含 multi-match event 的股票

test.beforeEach(async ({ page }) => {
  await page.goto('http://localhost:5171/')
  await page.getByRole('button', { name: '打开历史' }).click()
  await page.locator(`tr:has-text("${SCAN_FILE_ROW_TEXT}")`).click()
  await page.getByRole('button', { name: 'Open' }).click()
  await page.locator(`td.sym:text-is("${MULTI_MATCH_TICKER}")`).click()
})

test('multi-match event click enters candidate, banner shows', async ({ page }) => {
  // 用 window.__e2e.view 找一个 multi-match event(实施时根据真实数据补具体 event_id)
  const banner = page.locator('.candidate-banner')
  await expect(banner).toBeHidden()
  // 触发:click 某 multi-match marker
  await page.evaluate(() => {
    // 实施时根据 __e2e.view.scanFile + matches 找一个 multi-match event_id
    // 此处占位:用 setCandidateMatches 模拟进入 candidate 态
    const view = (window as any).__e2e?.view
    const matches = (window as any).__e2e?.chart?.()?.getOption?.()?.series?.find((s: any) => s.name === 'brackets')?.data ?? []
    if (matches.length >= 2) {
      view?.setCandidateMatches([matches[0].match_id, matches[1].match_id])
      view?.setPendingDisambig('<占位 event_id>')
    }
  })
  await expect(banner).toBeVisible()
  await expect(banner).toContainText('候选')
})

test('Esc clears candidate', async ({ page }) => {
  await page.evaluate(() => {
    const view = (window as any).__e2e?.view
    view?.setCandidateMatches(['m1', 'm2'])
  })
  await expect(page.locator('.candidate-banner')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.candidate-banner')).toBeHidden()
})

test('switch ticker clears candidate', async ({ page }) => {
  await page.evaluate(() => {
    const view = (window as any).__e2e?.view
    view?.setCandidateMatches(['m1', 'm2'])
  })
  await expect(page.locator('.candidate-banner')).toBeVisible()
  // 切到另一只股
  await page.locator('td.sym:text-is("ALTO")').click()
  await expect(page.locator('.candidate-banner')).toBeHidden()
})
```

**Note**:第一个 test 的真实 multi-match event 触发需根据扫描结果数据补 event_id;占位逻辑用 `setCandidateMatches` 直接模拟。实施者实测后用真 click event_id 替换。

- [ ] **Step 2: 启动 web-loop 跑 e2e**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy-align
uv run python scripts/run_path2_web.py &
sleep 6
cd path2_web_ui
npx playwright test e2e/match-event-disambig.spec.ts
```

Expected: 3 个 test 全绿。

- [ ] **Step 3: 清理 web-loop**

```bash
pkill -f "scripts/run_path2_web.py"
rm -f .playwright-mcp/*
```

- [ ] **Step 4: 提交**

```bash
git add path2_web_ui/e2e/match-event-disambig.spec.ts
git commit -m "test(e2e): match-event disambig smoke tests"
```

---

## Final Verification(全部 task 完成后)

- [ ] **跑全套单元测试**

```bash
cd path2_web_ui && npx vitest run
```

Expected: 全绿,包括 Task 1/2/6/7/10 新增的全部 it。

- [ ] **跑 vue-tsc 类型检查**

```bash
cd path2_web_ui && npx vue-tsc --noEmit
```

Expected: 无错误。

- [ ] **跑 build**

```bash
cd path2_web_ui && npm run build
```

Expected: 成功,无 warning。

- [ ] **web-loop 实测 §6.2 三项验证**

启动 web-loop 加载 BTM:
1. **markArea z 序兼容**:candidate fill alpha 0.35 / selected fill alpha 0.85 与 markArea(灰 0.15)叠加后视觉差异是否清晰可分辨 → 截图记录
2. **grid1 加高 26% + banner 16px 容量**:5-band 与 7-band(若有)各场景下 bandH + interval + bracket + banner 不重叠;若 7-band 仍挤,Task 3 grid1 加到 30% 复测
3. **pendingDisambig 描边可见**:`stroke=white lineWidth=1` 在副图 marker 上是否可见;若白边在 matched 态浅色 marker 上对比不足,Task 5 改 `lineWidth: 1.5` 或换 `stroke: #000` 黑边复测

清理同 Task 3 Step 4。

- [ ] **playwright 端到端冒烟(BTM)**

启动 web-loop,加载 BTM:
- multi-match event click → candidate banner 出现 + bracket 琥珀低 alpha + marker 白 stroke 1px
- candidate 中 click bracket → banner 消失 + bracket 琥珀高 alpha + 组成员 marker 琥珀 stroke 1.5px
- click 主图空白 → 一切清空
- Esc → 一切清空(在 candidate 态 / selected 态各试)
- 切股 → 一切清空
- 切 pattern → 一切清空
- sidebar 命中行 click → 等价于 bracket click
- sidebar trace role 行 click → 单焦点(只该 marker 白 stroke,不触组高亮)

清理 + commit 任何遗留:

```bash
pkill -f "scripts/run_path2_web.py"
rm -f .playwright-mcp/*
git status   # 确认无 stash
```
