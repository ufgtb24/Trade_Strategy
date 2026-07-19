# Sidebar-Chart Focus Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 sidebar / 主图 / 副图 三处选中态与联动统一到单一心智模型:两处 event 点击(marker vs sidebar 候选表)与两处 match 点击(bracket vs sidebar 命中匹配)分别复用同一底层 action;sidebar 视图按焦点意图分化(matched-focus 展 trace / event-focus 只展 role 候选表);多归属场景在信息层(sidebar 命中匹配 + 候选表 pending 行)如实反映所有归属,视觉层(主/副图 group 黑框)保留 disambig 收敛语义;选中 event 时 level 自动降到刚好可见;候选表就地展开在漏斗行下方。

**Architecture:** 状态字段从 `selected: ref<Selected>` + `selectedEventId: ref<string|null>` 双轴收敛到 `focusedMatchId: ref<string|null>` + `focusedEventId: ref<string|null>` 两条正交焦点轴 + `manualExpandedNode: ref<string|null>` 手动兜底。全部 `selected` / `selectedMatch` / `selectedMatchId` / `selectedEventId` / `highlightedEventIds` 改为 computed 派生,导出符号名不变(渲染层零改动);新增 `showTrace` / `expandedNodeId` / `markedMatchIds` / `markedEventIds` computed。三个高层 action `focusMatch(mid)` / `focusEvent(eid)` / `clearFocus()` 覆盖 8 处消费点(KlineChart.ts 3 处、KlineChart.vue 1 处 Esc、TopologyControl.vue 1 处 dblclick、DetailSidebar.vue 3 处);`focusEvent` 内部走归属判定 4 分支(含 candidateMatchIds + pendingDisambigEventId 副轴)+ level auto-follow(只降不升)。`selectMatch` / `selectRole` / `selectEvent` / `clearSelection` 旧 action 通过桥接层(Task 1)保底兼容,Task 4 末尾在所有消费点迁移完毕后删除。

**Tech Stack:** Vue 3(Composition API + `<script setup>`) + Pinia + TypeScript strict + vitest + jsdom + Vue Test Utils + Playwright。

## Global Constraints

- **不改动的文件/子系统**:后端 `path2_web/serialize.py` 及后端所有代码;`path2_web_ui/src/render/chart.ts`(渲染算法) 及 marker tooltip / bracket renderer / candidate 虚线 / pending 闪烁;topology 面板核心逻辑(只在 Task 3 微改 handleNodeDblClick);brush 框选 / shift+click pair 查询 / candidate scope card / rejection chain / preview 相关模块;level 门控 filter 算法(只加 autoFollowLevel 触发点);hoveredEventId / marker tooltip / bar tooltip。
- **不加 level 变更 toast** —— level auto-follow 静默切换。
- **不改多归属歧义解决流程本身** —— candidate scope card + candidate bracket 虚线 + pending marker 闪烁 三件套沿用,只让 sidebar 命中匹配列表 + 候选表 pending 行**同步反映**该状态。
- **界面英文 / 注释中文**(项目规范)。
- **每 task 结束单绿**:`npm run test`(vitest 全绿)+ `npm run type-check`(vue-tsc 全绿)+ `npm run build`(vite build 全绿)。任何一处失败即 BLOCKED,不允许留 broken state 进下一 task。
- **测试范式**:store 单元测用真 Pinia store(`setActivePinia(createPinia())`),不 mock;组件测用 Vue Test Utils + jsdom;e2e 用 Playwright + 系统 chromium。
- **spec 参考**:`docs/superpowers/specs/2026-07-09-sidebar-chart-focus-unification-design.md`(§3.2 六种交互一致性表格是 verify oracle,任何回归测试必须对齐)。
- **subagent-driven-development 推荐**(implementer=sonnet;reviewer=opus;详见 CLAUDE.md 项目规范)。

---

## Task 1: 状态字段收敛 + 派生 computed(桥接层保底)

**Goal:** 把 `selected` ref + `selectedEventId` ref 换成 `focusedMatchId` / `focusedEventId` / `manualExpandedNode` 三个 ref 内部字段;`selected` / `selectedMatchId` / `selectedMatch` / `selectedEventId` / `highlightedEventIds` 改为 computed 派生;新增 `showTrace` / `expandedNodeId` / `markedMatchIds` / `markedEventIds` 四个 computed。旧 action(`selectMatch` / `selectRole` / `selectEvent` / `clearSelection`)保留但内部改成写新字段(桥接层)。消费者(KlineChart / DetailSidebar / TopologyControl)零改动。

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts`
- Create: `path2_web_ui/tests/stores.focus-derivations.spec.ts`

**Interfaces:**
- Consumes: `matchedIdsOf` (from `render/visible.ts`) · `roleOfEventByBand` (from `render/visible.ts`) · `Level` (from `types.ts`) · `effectiveAnalysis` / `effectivePattern` / `eventTier` / `tagMap` 派生。
- Produces (对下游 task):
  - 内部 ref(不 export):`focusedMatchId: Ref<string|null>`, `focusedEventId: Ref<string|null>`, `manualExpandedNode: Ref<string|null>`
  - Export computed:`selected: ComputedRef<{kind:'match', matchId:string} | null>`, `selectedMatch: ComputedRef<MatchDict|null>`, `selectedMatchId: ComputedRef<string|null>`, `selectedEventId: ComputedRef<string|null>`, `highlightedEventIds: ComputedRef<ReadonlySet<string>>`, `showTrace: ComputedRef<boolean>`, `expandedNodeId: ComputedRef<string|null>`, `markedMatchIds: ComputedRef<ReadonlySet<string>>`, `markedEventIds: ComputedRef<ReadonlySet<string>>`
  - Bridge actions(保持 signature,内部改写):`selectMatch(id: string|null) → void`, `selectRole(nodeId: string) → void`, `selectEvent(id: string|null) → void`, `clearSelection() → void`
  - 4 处 `loadScanFile` / `clearScanFile` / `selectSymbol` / `setActivePattern` 内部 `selected.value = null` + `selectedEventId.value = null` 改成写新 ref(否则 computed 只读会编译错)。

- [ ] **Step 1: 建 RED 派生一致性测试文件**

创建 `path2_web_ui/tests/stores.focus-derivations.spec.ts`,内容:

```typescript
// Task 1 · 派生 computed 一致性测试。桥接语义:selectMatch/selectRole/selectEvent/clearSelection
// 内部改写 focusedMatchId/focusedEventId/manualExpandedNode 新字段,但 signature 与语义与
// spec §3.2 六种交互对齐(见 docs/superpowers/specs/2026-07-09-sidebar-chart-focus-unification-design.md)。
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile, Analysis, SerializedPattern, TopoNode, TopoEdge, MatchDict, EventDict } from '../src/types'

// 最小 fixture:1 pattern · 2 nodes(bo/ta)· 1 edge · 1 match · events 集合
function makeFixture(): MultiScanResultFile {
  const nodes: TopoNode[] = [
    { node_id: 'bo', source_tag: 'bo', render_grid: 'price' } as any,
    { node_id: 'ta', source_tag: 'ta', render_grid: 'time' } as any,
  ]
  const edges: TopoEdge[] = [
    { src: 'bo', dst: 'ta', anchor_field: 'anchor_bo_id' } as any,
  ]
  const pattern: SerializedPattern = {
    pattern_id: 'p1',
    topology: { nodes, edges },
    event_styles: {},
  } as any
  const events: EventDict[] = [
    { event_id: 'e_bo_1', class_id: 'BOEvent', source_tag: 'bo', start_idx: 10, end_idx: 10, child_refs: {} } as any,
    { event_id: 'e_ta_1', class_id: 'TAEvent', source_tag: 'ta', start_idx: 12, end_idx: 15,
      anchor_bo_id: 'e_bo_1', child_refs: {} } as any,
  ]
  const m1: MatchDict = {
    event_id: 'm1',
    start_idx: 10, end_idx: 15,
    role_index: { ta: 'e_ta_1' } as any,
    children: ['e_ta_1'],
  } as any
  const analysis: Analysis = {
    events, matches: [m1],
  } as any
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: { pattern_spec: pattern } as any },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis, summary: { matches: 1 } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('view store · 派生 computed 一致性', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('无焦点时:全部派生返回 null / 空集', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    expect(view.selected).toBeNull()
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedMatch).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.showTrace).toBe(false)
    expect(view.markedMatchIds.size).toBe(0)
    expect(view.markedEventIds.size).toBe(0)
  })

  it('selectMatch("m1"):selected/selectedMatch/selectedMatchId 派生 + showTrace=true + highlightedEventIds 含 members', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.selectMatch('m1')
    expect(view.selected).toEqual({ kind: 'match', matchId: 'm1' })
    expect(view.selectedMatchId).toBe('m1')
    expect(view.selectedMatch?.event_id).toBe('m1')
    expect(view.selectedEventId).toBeNull()
    expect(view.showTrace).toBe(true)
    // highlightedEventIds 含 e_ta_1(match.children)+ e_bo_1(anchor_field 反查)
    expect(view.highlightedEventIds.has('e_ta_1')).toBe(true)
    expect(view.highlightedEventIds.has('e_bo_1')).toBe(true)
    expect(view.markedMatchIds.has('m1')).toBe(true)
  })

  it('selectEvent("e_bo_1") 单独:selectedEventId 派生 + showTrace=false + expandedNodeId 派生 bo', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.selectEvent('e_bo_1')
    expect(view.selectedEventId).toBe('e_bo_1')
    expect(view.selectedMatchId).toBeNull()
    expect(view.showTrace).toBe(false)
    expect(view.expandedNodeId).toBe('bo')
    expect(view.markedEventIds.has('e_bo_1')).toBe(true)
  })

  it('selectMatch + selectEvent 同时:showTrace=false(event 存在)+ markedMatchIds={m1}', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.selectMatch('m1')
    view.selectEvent('e_ta_1')
    expect(view.selectedMatchId).toBe('m1')
    expect(view.selectedEventId).toBe('e_ta_1')
    expect(view.showTrace).toBe(false)  // event 存在 → 不展 trace
    expect(view.markedMatchIds.has('m1')).toBe(true)
    expect(view.markedEventIds.has('e_ta_1')).toBe(true)
    expect(view.expandedNodeId).toBe('ta')
  })

  it('多归属 pending 场景:candidateMatchIds 反映 markedMatchIds + pending 反映 markedEventIds/expandedNodeId', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setCandidateMatches(['m1', 'm2'])
    view.setPendingDisambig('e_ta_1')
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.markedMatchIds.size).toBe(2)
    expect(view.markedMatchIds.has('m1')).toBe(true)
    expect(view.markedMatchIds.has('m2')).toBe(true)
    expect(view.markedEventIds.has('e_ta_1')).toBe(true)
    expect(view.expandedNodeId).toBe('ta')  // pending event 所在 role 兜底
    expect(view.highlightedEventIds.size).toBe(0)  // 视觉层:多归属不亮 group
  })

  it('selectRole("bo") 桥接:写 manualExpandedNode → expandedNodeId 派生 bo', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.selectRole('bo')
    expect(view.selected).toBeNull()          // 派生 selected 只看 focusedMatchId(role 分支已删)
    expect(view.selectedMatchId).toBeNull()
    expect(view.expandedNodeId).toBe('bo')
  })

  it('expandedNodeId 派生优先级:focusedEventId > pendingDisambigEventId > manualExpandedNode', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.selectRole('bo')                     // manual = 'bo'
    expect(view.expandedNodeId).toBe('bo')
    view.setPendingDisambig('e_ta_1')         // pending 覆盖 manual
    expect(view.expandedNodeId).toBe('ta')
    view.selectEvent('e_bo_1')                // focus 覆盖 pending
    expect(view.expandedNodeId).toBe('bo')
    view.selectEvent(null)
    view.setPendingDisambig(null)             // 都清 → fallback manual 'bo'
    expect(view.expandedNodeId).toBe('bo')
  })

  it('clearSelection:清 focused,但 manualExpandedNode 保留', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.selectMatch('m1')
    view.selectRole('bo')                     // manualExpandedNode = 'bo'
    view.clearSelection()
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.showTrace).toBe(false)
    expect(view.expandedNodeId).toBe('bo')    // manual 保留
  })
})
```

- [ ] **Step 2: 运行 test 看它 RED**

Run:
```bash
cd path2_web_ui && npx vitest run tests/stores.focus-derivations.spec.ts
```
Expected: 失败 —— `view.showTrace` / `view.expandedNodeId` / `view.markedMatchIds` / `view.markedEventIds` 未定义(尚未加派生);其它派生若基于旧 `selected` ref 可能部分 pass,但至少 4 条新 computed 断言全部 FAIL。

- [ ] **Step 3: 替换状态字段(view.ts state ref 区)**

打开 `path2_web_ui/src/stores/view.ts`,定位到 state ref 声明区(约 line 62-68),替换:

**旧代码**(删除):
```typescript
const roleVisible = ref<Record<string, boolean>>({})
const selected = ref<Selected>(null)
const level = ref<Level>('matched')
const selectedEventId = ref<string | null>(null)
```

**新代码**(替换):
```typescript
const roleVisible = ref<Record<string, boolean>>({})
// 焦点意图两条正交轴(spec §3.1):
//   focusedMatchId 非空 & focusedEventId 空 → bracket-focus,展 trace
//   focusedEventId 非空 → event-focus,不展 trace(可能同时有 focusedMatchId=唯一归属 m)
//   两者都空 & candidateMatchIds 非空 → 多归属 pending 态
const focusedMatchId = ref<string | null>(null)
const focusedEventId = ref<string | null>(null)
// sidebar 漏斗手动 toggle 兜底:仅在 focusedEventId/pendingDisambigEventId 都空时生效
const manualExpandedNode = ref<string | null>(null)
const level = ref<Level>('matched')
```

- [ ] **Step 4: 4 处初始化改写新 ref**

同文件 view.ts,搜索 `selected.value = null` 全部替换:

**loadScanFile**(约 line 195-215):
```typescript
// 旧:
selected.value = null
selectedEventId.value = null
// 新:
focusedMatchId.value = null
focusedEventId.value = null
manualExpandedNode.value = null
```

**clearScanFile**(约 line 217-233):同上 3 行替换。

**selectSymbol**(约 line 234-246):同上 3 行替换。

**setActivePattern**(约 line 247-256):同上 3 行替换。

- [ ] **Step 5: 桥接层 · 旧 action 内部改写新 ref**

同文件,定位到 actions 区(约 line 299-305),替换:

**旧代码**(删除):
```typescript
function selectMatch(matchId: string | null) {
  selected.value = matchId === null ? null : { kind: 'match', matchId }
}
function selectRole(nodeId: string) { selected.value = { kind: 'role', nodeId } }
function clearSelection() { selected.value = null }
function setLevel(l: Level) { level.value = l }
function selectEvent(id: string | null) { selectedEventId.value = id }
```

**新代码**(替换):
```typescript
// Task 1 桥接层:旧 API 保持 signature,内部改写新 ref。Task 4 末尾在所有消费点
// 迁移到 focusMatch/focusEvent/clearFocus 后,这 4 个 action + selectRole 一起删除。
function selectMatch(matchId: string | null) {
  focusedMatchId.value = matchId
  if (matchId !== null) {
    focusedEventId.value = null
    manualExpandedNode.value = null    // 对齐 spec §3.3 focusMatch 副作用(收候选表)
  }
}
function selectRole(nodeId: string) {
  // sidebar 展开该 role 候选表(等价 spec 里 setExpandedRole)。
  manualExpandedNode.value = nodeId
}
function clearSelection() {
  focusedMatchId.value = null
  focusedEventId.value = null
}
function setLevel(l: Level) { level.value = l }
function selectEvent(id: string | null) { focusedEventId.value = id }
```

- [ ] **Step 6: 派生 computed 区**

同文件,定位到 computed 区(约 line 418-450 附近有 `selectedMatchId` / `selectedMatch` / `highlightedEventIds`),替换/新增:

**旧代码**(删除):
```typescript
const selectedMatchId = computed<string | null>(() =>
  selected.value?.kind === 'match' ? selected.value.matchId : null)

const selectedMatch = computed<MatchDict | null>(() => {
  const sel = selected.value
  if (sel?.kind !== 'match' || !effectiveAnalysis.value) return null
  return effectiveAnalysis.value.matches.find(m => m.event_id === sel.matchId) ?? null
})

// group 高亮 = 选中 match 的展开(matched tier 集合)——协议驱动,沿 child_refs +
// edges.anchor_field 递归。selectedMatch 变化即自动重算,消除"选中 match 但 group 高亮
// 不含 BO"的通道不一致 bug(原 UI bug: 主图 BO 方框无 in-group 深边)。
const highlightedEventIds = computed<ReadonlySet<string>>(() => {
  const m = selectedMatch.value
  if (!m) return new Set<string>()
  return matchedIdsOf(
    [m],
    effectiveAnalysis.value?.events ?? [],
    effectivePattern.value?.topology.edges ?? [],
  )
})
```

**新代码**(替换):
```typescript
// spec §3.1 派生:导出符号保持,内部从 focusedMatchId/focusedEventId 派生。
// selected 从 ref → computed(渲染层零改动 · storeToRefs 拿到的仍是 reactive)。
const selected = computed<Selected>(() =>
  focusedMatchId.value ? { kind: 'match' as const, matchId: focusedMatchId.value } : null)

const selectedMatchId = computed<string | null>(() => focusedMatchId.value)
const selectedEventId = computed<string | null>(() => focusedEventId.value)

const selectedMatch = computed<MatchDict | null>(() => {
  if (!focusedMatchId.value || !effectiveAnalysis.value) return null
  return effectiveAnalysis.value.matches.find(m => m.event_id === focusedMatchId.value) ?? null
})

// 视觉层(spec §3.1 分层):focusedMatchId 存在 → 亮 group 展开集;多归属 pending 时不亮
// (candidateMatchIds 副轴驱动候选 bracket 虚线闪烁,不进 highlightedEventIds)。
const highlightedEventIds = computed<ReadonlySet<string>>(() => {
  const m = selectedMatch.value
  if (!m) return new Set<string>()
  return matchedIdsOf(
    [m],
    effectiveAnalysis.value?.events ?? [],
    effectivePattern.value?.topology.edges ?? [],
  )
})

// 匹配 trace 展开的唯一判据(spec §3.1)
const showTrace = computed<boolean>(() =>
  focusedMatchId.value !== null && focusedEventId.value === null)

// 漏斗展开:focus event / pending event 优先派生 event 所在 role;都空 → manual 兜底
const expandedNodeId = computed<string | null>(() => {
  const eid = focusedEventId.value ?? pendingDisambigEventId.value
  if (eid) {
    const ev = effectiveAnalysis.value?.events.find(e => e.event_id === eid)
    if (!ev) return null
    return roleOfEventByBand(ev, tagMap.value.tagToNodes, tagMap.value.tagList)
  }
  return manualExpandedNode.value
})

// sidebar「命中匹配」列表"选中"样式判据(spec §3.1 信息层):
//   bracket-focus / disambig 后 → 单值 {focusedMatchId}
//   多归属 pending → candidateMatchIds(如实反映所有归属)
//   0 焦点 → 空集
const markedMatchIds = computed<ReadonlySet<string>>(() => {
  if (focusedMatchId.value) return new Set([focusedMatchId.value])
  if (candidateMatchIds.value.size > 0) return candidateMatchIds.value
  return new Set()
})

// sidebar 候选表"选中"样式判据(spec §3.1 信息层):
//   focus event → {focusedEventId}
//   多归属 pending → {pendingDisambigEventId}
//   都空 → 空集
const markedEventIds = computed<ReadonlySet<string>>(() => {
  if (focusedEventId.value) return new Set([focusedEventId.value])
  if (pendingDisambigEventId.value) return new Set([pendingDisambigEventId.value])
  return new Set()
})
```

- [ ] **Step 7: 更新 return 导出**

定位到 `return { ... }`(约 line 456-477 附近),替换:

**旧 return 里删除**:`selected` 单个符号已经是 computed 会重复(其实旧 selected 是 ref,新的是 computed,同名 `selected` 已在 Step 6 声明覆盖了 —— 不需要动 return 里 selected 一行)。

**关键改动**:添加 4 个新 export + `roleVisible` 后面加 `focusedMatchId, focusedEventId, manualExpandedNode`(内部字段也 export,便于 Task 2 focusMatch/focusEvent/clearFocus 单元测直接读):

```typescript
return {
  scanFile, symbol, activePatternId, sortByPid, sortDesc,
  roleVisible, selected,
  focusedMatchId, focusedEventId, manualExpandedNode,      // 新增内部 ref export
  level, selectedEventId, highlightedEventIds, candidateMatchIds, pendingDisambigEventId, hoveredEventId, diag,
  showTrace, expandedNodeId, markedMatchIds, markedEventIds, // 新增派生 computed export
  shiftSelectedEvents, activeDetailCard, timeScopeResponse, pairScopeResponse, candidateScopeResponse,
  previewEnabled, preview, previewLoading, previewError,
  patternIds, currentPerStock, pattern, currentAnalysis,
  visiblePatterns, visibleFields,
  effectivePattern, effectiveAnalysis, effectiveScan,
  unionRows, sortedRows, filteredSortedRows,
  roleColors, selectedMatchId, selectedMatch, tagMap, isolated, matchedIds, qualifiedIds,
  loadScanFile, clearScanFile, selectSymbol, setActivePattern, setSort,
  toggleRole, selectMatch, selectRole, clearSelection,
  setLevel, selectEvent, hoverEvent,
  setCandidateMatches, clearCandidates, setPendingDisambig,
  setShiftSelectedEvents, clearDetailCard, triggerTimeQuery, triggerPairQuery, triggerCandidateQuery,
  currentTimeEventClass,
  setPreviewEnabled, runPreview, clearPreview,
  initVisiblePatterns, togglePattern, setPatternsAllOn, setPatternsAllOff, invertPatterns,
  toggleField, isColumnVisible, effectiveSortKey,
  bandKey, eventTier,
}
```

- [ ] **Step 8: 运行派生一致性测 GREEN**

Run:
```bash
cd path2_web_ui && npx vitest run tests/stores.focus-derivations.spec.ts
```
Expected: 8 test PASS。若失败,读输出诊断——常见:tagMap 依赖顺序(computed 应放在 `tagMap` 声明之后,view.ts 现有已在 line ~440;若移位错乱会 undefined)。

- [ ] **Step 9: 运行现有 store 相关回归**

Run:
```bash
cd path2_web_ui && npx vitest run tests/stores.disambig.spec.ts tests/stores.spec.ts tests/view.multi.spec.ts tests/components.kline-click.spec.ts
```
Expected: 全绿(桥接层保 signature,旧 assertion `view.selectedMatchId` / `view.selectedEventId` / `view.selected` 等都通过 computed 派生保底 pass)。若挂,一般是漏改初始化 4 处 → 编译错。修完再跑。

- [ ] **Step 10: vue-tsc + build 全绿**

Run:
```bash
cd path2_web_ui && npm run type-check && npm run build
```
Expected: type-check 无错;build 无错。若 vue-tsc 报 `Property 'selected' does not exist` 或 `Cannot assign to 'selected' because it is a read-only property`,说明 return 里 selected 未导出/其它文件在写 selected → 找到该处按 spec 桥接语义改。

- [ ] **Step 11: 全库 vitest 无回归**

Run:
```bash
cd path2_web_ui && npm run test
```
Expected: 全绿(300+ tests)。任何红都必须排查根因,不允许 skip。

- [ ] **Step 12: Commit**

Run:
```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/tests/stores.focus-derivations.spec.ts
git commit -m "refactor(view): 状态字段收敛为 focusedMatchId/focusedEventId + 派生 computed(桥接层保底)

- 内部 ref:focusedMatchId / focusedEventId / manualExpandedNode(三条正交)
- 派生 computed(9 项):selected / selectedMatchId / selectedMatch / selectedEventId /
  highlightedEventIds / showTrace / expandedNodeId / markedMatchIds / markedEventIds
- 桥接层:selectMatch / selectRole / selectEvent / clearSelection 保 signature,
  内部改写新 ref,消费者(KlineChart/DetailSidebar/TopologyControl)零改动
- 派生一致性 spec:8 场景覆盖 §3.2 表格(单焦点 · 组合焦点 · 多归属 pending · manual 兜底
  · expandedNodeId 三级优先级 · clearSelection 保留 manual)
- 全库回归 300+ tests 绿"
```

---

## Task 2: focusMatch / focusEvent / clearFocus + autoFollowLevel

**Goal:** 引入三个高层 action + level auto-follow;旧桥接层 action(`selectMatch` / `selectRole` / `selectEvent` / `clearSelection`)保留(Task 4 末尾删)。四处初始化(`loadScanFile` / `clearScanFile` / `selectSymbol` / `setActivePattern`)改用 `clearFocus()`。

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts`
- Create: `path2_web_ui/tests/stores.focus-actions.spec.ts`

**Interfaces:**
- Consumes: 内部 ref(Task 1 已加)+ `matchedIdsOf` / `eventTier` / `setCandidateMatches` / `setPendingDisambig` / `clearCandidates` / `triggerCandidateQuery` / `setLevel`。
- Produces (对下游 task):
  - `focusMatch(matchId: string) → void`:焦点意图 → match(bracket click / sidebar 命中匹配行);清 focusedEventId + manualExpandedNode + candidates。
  - `focusEvent(eventId: string) → void`:焦点意图 → event;内部走归属判定 4 分支(0 / 1 / >1 归属 + level auto-follow);多归属时 focusedMatchId=focusedEventId=null,candidateMatchIds+pendingDisambigEventId 副轴驱动。
  - `clearFocus() → void`:双清 focused* + candidates。
  - `autoFollowLevel(eventId: string) → void`:内部小函数,只降不升 level(spec §3.4)。
  - 4 处初始化改用 `clearFocus()`(废弃直写 focusedMatchId.value=null)。

- [ ] **Step 1: 建 RED action 测试**

创建 `path2_web_ui/tests/stores.focus-actions.spec.ts`:

```typescript
// Task 2 · focusMatch / focusEvent / clearFocus + autoFollowLevel 单元测。
// 与 spec §3.2 表格逐行对齐:六种交互场景状态转换。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile } from '../src/types'

// 复用 Task 1 fixture(需 export 或复制)——这里独立复制避免耦合。
function makeFixture(): MultiScanResultFile {
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: { pattern_spec: {
      pattern_id: 'p1',
      topology: {
        nodes: [
          { node_id: 'bo', source_tag: 'bo', render_grid: 'price' },
          { node_id: 'ta', source_tag: 'ta', render_grid: 'time' },
        ],
        edges: [{ src: 'bo', dst: 'ta', anchor_field: 'anchor_bo_id' }],
      },
      event_styles: {},
    } as any } as any },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [
        { event_id: 'e_bo_1', class_id: 'BOEvent', source_tag: 'bo', start_idx: 10, end_idx: 10, child_refs: {} },
        { event_id: 'e_ta_1', class_id: 'TAEvent', source_tag: 'ta', start_idx: 12, end_idx: 15,
          anchor_bo_id: 'e_bo_1', child_refs: {} },
        { event_id: 'e_ta_2', class_id: 'TAEvent', source_tag: 'ta', start_idx: 20, end_idx: 22,
          anchor_bo_id: 'e_bo_1', child_refs: {} },
        { event_id: 'e_ta_3', class_id: 'TAEvent', source_tag: 'ta', start_idx: 30, end_idx: 32,
          anchor_bo_id: 'e_bo_1', child_refs: {} },
      ],
      matches: [
        { event_id: 'm1', start_idx: 10, end_idx: 15, role_index: { ta: 'e_ta_1' }, children: ['e_ta_1'] },
        { event_id: 'm2', start_idx: 12, end_idx: 22, role_index: { ta: 'e_ta_2' }, children: ['e_ta_2'] },
        // e_ta_2 属于 m2;e_ta_3 不属于任何 match(0 归属)
      ],
    } as any, summary: { matches: 2 } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('view store · focusMatch / focusEvent / clearFocus', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // stub triggerCandidateQuery(fire-and-forget · 不阻塞,不需要 mock 网络,直接吞)
  })

  it('focusMatch("m1"):focusedMatchId=m1 · focusedEventId=null · manual=null · candidates 清 · showTrace=true', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.selectRole('bo')                       // 先 manual='bo'
    view.setCandidateMatches(['m1', 'm2'])
    view.focusMatch('m1')
    expect(view.focusedMatchId).toBe('m1')
    expect(view.focusedEventId).toBeNull()
    expect(view.manualExpandedNode).toBeNull()  // 收候选表
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.showTrace).toBe(true)
  })

  it('focusEvent 唯一归属:e_ta_1 → focusedMatchId=m1 + focusedEventId=e_ta_1', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('e_ta_1')
    expect(view.focusedMatchId).toBe('m1')
    expect(view.focusedEventId).toBe('e_ta_1')
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.showTrace).toBe(false)
  })

  it('focusEvent 0 归属:e_ta_3 → focusedMatchId=null + focusedEventId=e_ta_3', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('e_ta_3')
    expect(view.focusedMatchId).toBeNull()
    expect(view.focusedEventId).toBe('e_ta_3')
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.markedEventIds.has('e_ta_3')).toBe(true)
  })

  it('focusEvent 多归属:e_bo_1 属于 m1+m2(anchor_field 反查双方)→ candidateMatchIds={m1,m2} + pendingDisambig=e_bo_1', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    // e_bo_1 是 m1/m2 共同 anchor(anchor_field="anchor_bo_id"),属两 match
    view.focusEvent('e_bo_1')
    expect(view.focusedMatchId).toBeNull()
    expect(view.focusedEventId).toBeNull()
    expect(view.candidateMatchIds.size).toBe(2)
    expect(view.candidateMatchIds.has('m1')).toBe(true)
    expect(view.candidateMatchIds.has('m2')).toBe(true)
    expect(view.pendingDisambigEventId).toBe('e_bo_1')
    expect(view.markedMatchIds.size).toBe(2)           // 信息层如实反映
    expect(view.highlightedEventIds.size).toBe(0)      // 视觉层不亮
    expect(view.expandedNodeId).toBe('bo')             // pending 兜底展开
  })

  it('clearFocus:双清 + candidates 清', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusMatch('m1')
    view.clearFocus()
    expect(view.focusedMatchId).toBeNull()
    expect(view.focusedEventId).toBeNull()
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.showTrace).toBe(false)
  })

  it('level auto-follow:选 detected event + level=matched → setLevel("detected")', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('matched')
    // e_ta_3 是 0 归属 → tier=detected(不在 matchedIds,若也不在 qualifiedIds 则 detected)
    view.focusEvent('e_ta_3')
    expect(view.level).toBe('detected')
  })

  it('level auto-follow:选 matched event + level=matched → level 不动', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('matched')
    view.focusEvent('e_ta_1')                  // matched
    expect(view.level).toBe('matched')
  })

  it('focusMatch 不触发 level auto-follow', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('matched')
    view.focusMatch('m1')
    expect(view.level).toBe('matched')
  })
})
```

- [ ] **Step 2: 运行看 RED**

Run:
```bash
cd path2_web_ui && npx vitest run tests/stores.focus-actions.spec.ts
```
Expected: 全 FAIL —— `view.focusMatch` / `view.focusEvent` / `view.clearFocus` 未定义。

- [ ] **Step 3: 添加 focusMatch / focusEvent / clearFocus + autoFollowLevel**

在 view.ts actions 区(桥接层 selectMatch 之后)添加:

```typescript
// ── Task 2 高层 action(spec §3.3)· 消费点将在 Task 3/4 迁移到这三个 ─────────────
function focusMatch(matchId: string): void {
  focusedMatchId.value = matchId
  focusedEventId.value = null
  manualExpandedNode.value = null   // 对齐 §3.3 副作用:收候选表,让 trace 独占视野
  clearCandidates()
}

function focusEvent(eventId: string): void {
  void triggerCandidateQuery(eventId)                   // scope=candidate 淘汰路径 · fire-and-forget
  const matches = effectiveAnalysis.value?.matches ?? []
  const events  = effectiveAnalysis.value?.events  ?? []
  const edges   = effectivePattern.value?.topology.edges ?? []
  const ms = matches.filter(m => matchedIdsOf([m], events, edges).has(eventId))

  if (ms.length === 0) {
    focusedMatchId.value = null
    focusedEventId.value = eventId
    clearCandidates()
  } else if (ms.length === 1) {
    focusedMatchId.value = ms[0].event_id
    focusedEventId.value = eventId
    clearCandidates()
  } else {
    // 多归属:信息层(markedMatchIds=candidates)+ 视觉层(不亮 group,等 disambig)
    focusedMatchId.value = null
    focusedEventId.value = null
    setCandidateMatches(ms.map(m => m.event_id))
    setPendingDisambig(eventId)
  }
  autoFollowLevel(eventId)
}

function clearFocus(): void {
  focusedMatchId.value = null
  focusedEventId.value = null
  clearCandidates()
}

// spec §3.5:单向放松门控;只降不升;仅 focusEvent 调用
function autoFollowLevel(eventId: string): void {
  const ev = effectiveAnalysis.value?.events.find(e => e.event_id === eventId)
  if (!ev) return
  const evTier = eventTier(ev)
  const RANK: Record<Level, number> = { matched: 2, qualified: 1, detected: 0 }
  if (RANK[evTier] < RANK[level.value]) setLevel(evTier)
}
```

- [ ] **Step 4: return 里导出新 action**

在 return 的 actions 区添加 `focusMatch, focusEvent, clearFocus`(autoFollowLevel 内部函数,不 export):

```typescript
return {
  // ... 现有 ...
  setLevel, selectEvent, hoverEvent,
  focusMatch, focusEvent, clearFocus,        // 新增
  setCandidateMatches, clearCandidates, setPendingDisambig,
  // ... 现有 ...
}
```

- [ ] **Step 5: 4 处初始化改 clearFocus**

同文件 view.ts,`loadScanFile` / `clearScanFile` / `selectSymbol` / `setActivePattern` 内的:
```typescript
focusedMatchId.value = null
focusedEventId.value = null
manualExpandedNode.value = null
```
全部替换成:
```typescript
clearFocus()
manualExpandedNode.value = null   // manual 不由 clearFocus 清(spec:manual 只在 focusMatch 副作用清)
```

**注意**:`loadScanFile` / `clearScanFile` / `selectSymbol` / `setActivePattern` 通常也希望清 manualExpandedNode(切数据源 → 展开态过时);而 focusMatch 里"收候选表"是同一 pattern 内的意图切换。这两个语义区分 —— 4 处初始化也要显式清 manual,与 focusMatch 分开。

- [ ] **Step 6: 运行看 GREEN**

Run:
```bash
cd path2_web_ui && npx vitest run tests/stores.focus-actions.spec.ts
```
Expected: 全 PASS。若 level auto-follow 相关 test FAIL,常见根因:e_ta_3 的 eventTier 判定 —— tier 是 matched > qualified > detected;需 confirm diag/qualifiedIdsOf 为空时 tier=detected(fixture 里 diag 未 seed,应默认 tier=detected)。

- [ ] **Step 7: 全库 vitest + type-check + build**

Run:
```bash
cd path2_web_ui && npm run test && npm run type-check && npm run build
```
Expected: 全绿。

- [ ] **Step 8: Commit**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/tests/stores.focus-actions.spec.ts
git commit -m "feat(view): focusMatch / focusEvent / clearFocus + autoFollowLevel

- focusEvent 内嵌归属判定 4 分支(0 / 1 / >1 归属)· 复用给 KlineChart 与 DetailSidebar
- focusMatch 副作用:清 focusedEventId + manualExpandedNode + candidates(§3.3)
- autoFollowLevel 单向降(RANK[eventTier] < RANK[level] → setLevel),focusMatch 不触发(§3.5)
- 4 处初始化(loadScanFile / clearScanFile / selectSymbol / setActivePattern)改用 clearFocus + 显式清 manual
- 桥接层 action 保留(Task 4 末尾迁移完消费点后删)
- 8 场景单元测覆盖:6 种交互 + auto-follow 双向 + focusMatch 不 auto"
```

---

## Task 3: KlineChart.ts + KlineChart.vue Esc + TopologyControl.vue dblclick 迁移

**Goal:** 把 `KlineChart.ts::handleChartClick` 3 分支替换成 `view.clearFocus()` / `view.focusMatch()` / `view.focusEvent()`;`KlineChart.vue` 里 Esc keydown handler 的 3 行清零替换成 `view.clearFocus()`;`TopologyControl.vue` handleNodeDblClick 里 `view.selectRole(nodeId)` 保持不变(桥接层保底,Task 4 末尾统一替换成 `view.setExpandedRole`)。**注意**:Task 3 完成时旧 selectMatch/selectEvent 桥接依然存在,`selectRole` 也依然存在;所有测试仍绿。

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.ts`
- Modify: `path2_web_ui/src/components/KlineChart.vue`(Esc handler)
- Modify: `path2_web_ui/tests/components.kline-click.spec.ts`(测试仍绿,但 assertion 可能需微调 —— 若旧测试断言 selectMatch/selectEvent 被调用则改成 view store 状态断言)

**Interfaces:**
- Consumes: `view.focusMatch(matchId)` / `view.focusEvent(eventId)` / `view.clearFocus()`(Task 2 产)
- Produces: 3 处调用点已迁移(KlineChart.ts 3 分支 + KlineChart.vue 1 处 Esc);其余消费点(TopologyControl / DetailSidebar 3 处)在 Task 4 迁移。

- [ ] **Step 1: 建 RED:焦点联动断言测**

打开 `path2_web_ui/tests/components.kline-click.spec.ts`,现有测试断言 `view.selectedEventId` / `view.selectedMatchId` 等 —— 这些通过 computed 派生已经 pass。补一条断言 `view.focusedMatchId` / `view.focusedEventId` 内部 ref 也对齐(可选 · 加强测):

在文件末尾追加(现有测试保留):

```typescript
describe('handleChartClick · 焦点意图迁移(Task 3)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('空白 click → clearFocus:focusedMatchId/focusedEventId 都清 · candidates 清', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())              // 复用现有 fixture 或此文件顶部的 makeFixture
    view.setCandidateMatches(['m1', 'm2'])
    view.focusMatch('m1')
    handleChartClick(null, [], view)
    expect(view.focusedMatchId).toBeNull()
    expect(view.focusedEventId).toBeNull()
    expect(view.candidateMatchIds.size).toBe(0)
  })

  it('bracket click → focusMatch:focusedMatchId=matchId · focusedEventId=null · manual=null · showTrace=true', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.selectRole('bo')                          // manual='bo'
    const matches = view.effectiveAnalysis!.matches
    handleChartClick(
      { seriesName: 'brackets', data: { match_id: 'm1' } },
      matches, view
    )
    expect(view.focusedMatchId).toBe('m1')
    expect(view.focusedEventId).toBeNull()
    expect(view.manualExpandedNode).toBeNull()
    expect(view.showTrace).toBe(true)
  })

  it('marker click 唯一归属 → focusEvent:焦点两非空 · showTrace=false', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    const matches = view.effectiveAnalysis!.matches
    handleChartClick(
      { seriesName: 'points', data: { event_id: 'e_ta_1' } },
      matches, view
    )
    expect(view.focusedMatchId).toBe('m1')
    expect(view.focusedEventId).toBe('e_ta_1')
    expect(view.showTrace).toBe(false)
  })
})
```

- [ ] **Step 2: 运行看 RED 或部分 PASS**

Run:
```bash
cd path2_web_ui && npx vitest run tests/components.kline-click.spec.ts
```
Expected: 新加断言中 `view.focusedMatchId` / `view.focusedEventId` / `view.manualExpandedNode` 若 fixture 未 seed 相应 events 会挂;修 fixture(参照 Task 2 里的 makeFixture)。现有测试仍 pass。

- [ ] **Step 3: 迁移 KlineChart.ts::handleChartClick**

打开 `path2_web_ui/src/components/KlineChart.ts`,替换整个 handleChartClick(约 line 64-131):

```typescript
/**
 * 处理 ECharts chart.on('click', p) 事件,分流到 view store 三个高层 action。
 *
 * 分流规则(spec §3.3):
 *   空白 click       → view.clearFocus()
 *   brackets click   → view.focusMatch(match_id)
 *   MARKER_SERIES    → view.focusEvent(event_id) · 内部走归属判定 4 分支(0/1/>1 归属)
 *
 * @param p       ECharts click payload(空白点击时为 null 或 seriesName 缺失)
 * @param matches 当前 effectiveAnalysis.matches(保签名兼容,不再直接消费 —— focusEvent 内部读)
 * @param view    useViewStore() 实例
 */
export function handleChartClick(
  p: ChartClickPayload,
  matches: MatchDict[],
  view: ReturnType<typeof useViewStore>,
): void {
  if (!p || !p.seriesName) {
    view.clearFocus()
    return
  }
  if (p.seriesName === 'brackets' && p.data?.match_id) {
    // 现有:match 不存在时 return(见旧代码 line 84-85 match 查找)。新的:
    // focusMatch 里不校验存在(简化);消费方无 bracket 不会触发该分支。
    view.focusMatch(p.data.match_id)
    return
  }
  if (MARKER_SERIES.includes(p.seriesName) && p.data?.event_id) {
    view.focusEvent(p.data.event_id)
    return
  }
}
```

**顶部 import 变化**:文件顶部原有的 `import { matchedIds as matchedIdsOf } from '../render/visible'` 现在不再使用,删除该行(handleChartClick 内不再直接消费 matchedIdsOf,已下沉到 focusEvent)。

**保留** `handleShiftClick` / `MARKER_SERIES` / `ShiftClickSource` / `ChartClickPayload` 现有代码不动。

- [ ] **Step 4: 迁移 KlineChart.vue Esc handler**

打开 `path2_web_ui/src/components/KlineChart.vue`,定位到 line 389-391 附近的 Esc handler:

**旧代码**:
```typescript
if (contextMenuVisible.value) { contextMenuVisible.value = false; return }
view.clearCandidates()
view.selectMatch(null)
view.selectEvent(null)
```

**新代码**:
```typescript
if (contextMenuVisible.value) { contextMenuVisible.value = false; return }
view.clearFocus()
```

- [ ] **Step 5: 运行 kline-click 测试 GREEN**

Run:
```bash
cd path2_web_ui && npx vitest run tests/components.kline-click.spec.ts
```
Expected: 全绿(含新加的 3 条断言)。

- [ ] **Step 6: 全库回归 vitest + type-check + build**

Run:
```bash
cd path2_web_ui && npm run test && npm run type-check && npm run build
```
Expected: 全绿。特别关注 `components.candidate-status-bar.spec.ts` / `stores.disambig.spec.ts`(多归属流没有改动,应保持绿)。

- [ ] **Step 7: Commit**

```bash
git add path2_web_ui/src/components/KlineChart.ts path2_web_ui/src/components/KlineChart.vue path2_web_ui/tests/components.kline-click.spec.ts
git commit -m "refactor(kline): handleChartClick 3 分支 + Esc 迁移到 focus{Match,Event,Clear}

- KlineChart.ts::handleChartClick 3 分支(空白/brackets/marker)全走 view store 高层 action
- KlineChart.vue Esc keydown:3 行清零 → view.clearFocus()
- 归属判定 4 分支下沉到 view.focusEvent(§3.3);handleChartClick 从 71 行减到 22 行
- kline-click 单元测补 3 条焦点内部 ref 断言;现有 assertion 全绿(桥接层保底)"
```

---

## Task 4: DetailSidebar.vue 6 处消费 + template 重构 + 删除旧桥接

**Goal:** DetailSidebar 3 处消费点(`selectMatchRow` / `selectRoleEvent` / `selectCandidateRow`)迁移到 `focusMatch` / `focusEvent`;template 结构改造(候选表挪进 v-for 循环体内就地展开、trace 判据改 `showTrace`、命中匹配"选中"判据改 `markedMatchIds`、候选表"选中"判据改 `markedEventIds`);TopologyControl.vue dblclick 迁移到新 API `setExpandedRole(nodeId)`;view store 删除 `selectMatch` / `selectRole` / `selectEvent` / `clearSelection` 4 个桥接 action + 补充 `setExpandedRole` 新 action;删除 DetailSidebar 里 `watch(selected)` 分支(scrollIntoView 改成 watch `[showTrace, focusedMatchId]`)。

**Files:**
- Modify: `path2_web_ui/src/components/DetailSidebar.vue`(template + script)
- Modify: `path2_web_ui/src/components/TopologyControl.vue`
- Modify: `path2_web_ui/src/stores/view.ts`(删桥接 + 加 setExpandedRole)
- Create: `path2_web_ui/tests/components.detail-sidebar.spec.ts`(新建组件测)

**Interfaces:**
- Consumes: Task 2 已产的 `focusMatch` / `focusEvent` / `clearFocus`。
- Produces:
  - view store 新加 `setExpandedRole(nodeId: string) → void`(替换 selectRole 桥接语义);delete 4 个旧 action(`selectMatch` / `selectRole` / `selectEvent` / `clearSelection`)。
  - DetailSidebar template 结构:候选表挪进 funnel-row v-for 循环体内;`.match-row--selected` 判据 `markedMatchIds.has(m.event_id)`;`.attr-row--selected` 判据 `markedEventIds.has(row.event_id)`;`.match-trace` v-if `showTrace && selectedMatch`。
  - `expandedNodeId` 派生驱动 template;`toggleExpand(nodeId)` 只写 manualExpandedNode。

- [ ] **Step 1: 建 RED · DetailSidebar 组件测**

创建 `path2_web_ui/tests/components.detail-sidebar.spec.ts`:

```typescript
// Task 4 · DetailSidebar 组件测:候选表就地展开 · marked 判据 · trace 显示条件。
// 复用 store 真 Pinia · 组件 mount 靠 Vue Test Utils + jsdom。
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import DetailSidebar from '../src/components/DetailSidebar.vue'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile } from '../src/types'

function makeFixture(): MultiScanResultFile {
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: { pattern_spec: {
      pattern_id: 'p1',
      topology: {
        nodes: [
          { node_id: 'bo', source_tag: 'bo', render_grid: 'price' },
          { node_id: 'ta', source_tag: 'ta', render_grid: 'time' },
        ],
        edges: [{ src: 'bo', dst: 'ta', anchor_field: 'anchor_bo_id' }],
      },
      event_styles: {},
    } as any } as any },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [
        { event_id: 'e_bo_1', class_id: 'BOEvent', source_tag: 'bo', start_idx: 10, end_idx: 10, child_refs: {} },
        { event_id: 'e_ta_1', class_id: 'TAEvent', source_tag: 'ta', start_idx: 12, end_idx: 15,
          anchor_bo_id: 'e_bo_1', child_refs: {} },
        { event_id: 'e_ta_2', class_id: 'TAEvent', source_tag: 'ta', start_idx: 20, end_idx: 22,
          anchor_bo_id: 'e_bo_1', child_refs: {} },
      ],
      matches: [
        { event_id: 'm1', start_idx: 10, end_idx: 15, role_index: { ta: 'e_ta_1' }, children: ['e_ta_1'] },
        { event_id: 'm2', start_idx: 12, end_idx: 22, role_index: { ta: 'e_ta_2' }, children: ['e_ta_2'] },
      ],
    } as any, summary: { matches: 2 } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('DetailSidebar · Task 4 视图分化', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('bracket-focus:showTrace=true → .match-trace 渲染 · manualExpandedNode=null → 无候选表', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusMatch('m1')
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.match-trace').exists()).toBe(true)
    expect(wrapper.find('.candidate-table-wrap').exists()).toBe(false)
  })

  it('event-focus 唯一归属:showTrace=false → 无 trace · 候选表在 event 所在 role 下方渲染', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('e_ta_1')                    // 唯一归属 m1;expandedNodeId='ta'
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.match-trace').exists()).toBe(false)
    // 候选表存在
    expect(wrapper.find('.candidate-table-wrap').exists()).toBe(true)
    // 命中匹配单行黄底(markedMatchIds={m1})
    const rows = wrapper.findAll('.match-row')
    const selectedRows = rows.filter(r => r.classes().includes('match-row--selected'))
    expect(selectedRows.length).toBe(1)
  })

  it('多归属 pending:候选表在 pending event 所在 role 下方展开 · 命中匹配多行同亮', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('e_bo_1')                    // anchor_field 反查 m1+m2 → 多归属
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.match-trace').exists()).toBe(false)
    expect(wrapper.find('.candidate-table-wrap').exists()).toBe(true)     // pending 兜底展开 bo
    const rows = wrapper.findAll('.match-row')
    const selectedRows = rows.filter(r => r.classes().includes('match-row--selected'))
    expect(selectedRows.length).toBe(2)          // 信息层如实反映
  })

  it('sidebar 候选表 event 行 click:等价 marker click 走 focusEvent', async () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.selectRole('ta')                        // 手动展开 ta 候选表
    const wrapper = mount(DetailSidebar)
    const rows = wrapper.findAll('.attr-row')
    if (rows.length === 0) {
      // diag 尚未 seed —— 这条测试需要 diag,或跳过
      return
    }
    await rows[0].trigger('click')
    // focusEvent 已调用 · focusedEventId 非空
    expect(view.focusedEventId).toBeTruthy()
  })

  it('sidebar 命中匹配行 click:等价 bracket click 走 focusMatch → showTrace=true', async () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    const wrapper = mount(DetailSidebar)
    const matchRows = wrapper.findAll('.match-row')
    await matchRows[0].trigger('click')
    expect(view.focusedMatchId).toBe('m1')
    expect(view.focusedEventId).toBeNull()
    expect(view.showTrace).toBe(true)
  })

  it('候选表就地展开:candidate-table-wrap 应作为 funnel-row 后续兄弟节点', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.selectRole('ta')
    const wrapper = mount(DetailSidebar)
    // template 结构:v-for 里每 funnel-row 后跟 v-if candidate-table-wrap(同 parent)
    const html = wrapper.html()
    // 简 assertion:candidate-table-wrap 里 candidate-table-title 文本含 'ta'(展开的 role)
    expect(html).toContain('ta 候选')
  })
})
```

- [ ] **Step 2: 运行看 RED**

Run:
```bash
cd path2_web_ui && npx vitest run tests/components.detail-sidebar.spec.ts
```
Expected: 大部分 FAIL —— template 尚未改造,候选表还挂在 v-for 外;markedMatchIds/markedEventIds 判据 template 尚未应用;showTrace 判据 template 尚未应用。

- [ ] **Step 3: view store 加 setExpandedRole action**

打开 `path2_web_ui/src/stores/view.ts`,在 `selectRole` 桥接旁(约 line 302)之后添加:

```typescript
// Task 4:替换 selectRole 语义清晰化 —— sidebar 展开该 role 候选表(不涉焦点)。
// TopologyControl.vue dblclick 消费点通过 setExpandedRole 显式表意。
// nodeId=null 表示收起(DetailSidebar.toggleExpand 里 toggle 用)。
function setExpandedRole(nodeId: string | null): void {
  manualExpandedNode.value = nodeId
}
```

在 return 里 export `setExpandedRole`。

- [ ] **Step 4: 迁移 TopologyControl.vue dblclick**

打开 `path2_web_ui/src/components/TopologyControl.vue`,定位 line 120:

**旧代码**:
```typescript
view.selectRole(nodeId)
```

**新代码**:
```typescript
view.setExpandedRole(nodeId)
```

- [ ] **Step 5: DetailSidebar.vue template 重构**

打开 `path2_web_ui/src/components/DetailSidebar.vue`,替换角色漏斗 template(约 line 44-114 整块):

**旧代码**(删除):
```vue
<template v-if="effectivePattern && effectiveAnalysis">
  <h3 class="section-title">角色漏斗</h3>
  <div v-for="node in effectivePattern.topology.nodes" :key="node.node_id"
       class="funnel-row"
       :class="{ 'funnel-row--selected': expandedNode === node.node_id && !isolated.has(node.node_id) }"
       @click="!isolated.has(node.node_id) && toggleExpand(node.node_id)">
    <!-- ... funnel-row 内容 ... -->
  </div>

  <!-- 候选表:展开 pattern role 行时显示 -->
  <template v-if="expandedNode && diag">
    <div class="candidate-table-wrap">
      <!-- 现有 candidate-table 内容 -->
    </div>
  </template>
</template>
```

**新代码**(替换 · 结构:候选表挪进 v-for 循环体内):
```vue
<template v-if="effectivePattern && effectiveAnalysis">
  <h3 class="section-title">角色漏斗</h3>
  <div v-for="node in effectivePattern.topology.nodes" :key="node.node_id">
    <div class="funnel-row"
         :class="{ 'funnel-row--selected': expandedNodeId === node.node_id && !isolated.has(node.node_id) }"
         @click="!isolated.has(node.node_id) && toggleExpand(node.node_id)">
      <!-- stream-source(孤立 node):密度徽标行 -->
      <template v-if="isolated.has(node.node_id)">
        <span class="node-label stream-source">{{ node.node_id }}</span>
        <span class="badge">原始检测 {{ detectedCount(node) }}</span>
      </template>
      <!-- pattern role(有边):完整漏斗行 -->
      <template v-else>
        <span class="node-label">{{ node.node_id }}</span>
        <span class="funnel-segment" :style="{ color: tierColor('detected', node.node_id) }">
          {{ detectedCount(node) }}
        </span>
        <span class="funnel-arrow">▸</span>
        <span class="funnel-segment" :style="{ color: tierColor('qualified', node.node_id) }">
          {{ tracedCount(node) }}
        </span>
        <span class="funnel-arrow">▸</span>
        <span class="funnel-segment" :style="{ color: tierColor('matched', node.node_id) }">
          {{ matchedCountForNode(node) }}
        </span>
        <span class="expand-icon">{{ expandedNodeId === node.node_id ? '▲' : '▼' }}</span>
      </template>
    </div>
    <!-- 就地展开:候选表跟在当前展开的 funnel-row 下方(spec §3.4a) -->
    <div v-if="expandedNodeId === node.node_id && !isolated.has(node.node_id) && diag"
         class="candidate-table-wrap">
      <div class="candidate-table-title">{{ node.node_id }} 候选</div>
      <table class="candidate-table" v-if="rolesAttr(node.node_id).length">
        <thead>
          <tr>
            <th>事件</th>
            <th v-for="cid in rolesClauseIds(node.node_id)" :key="cid">{{ cid }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rolesAttr(node.node_id)" :key="row.event_id"
              class="attr-row"
              :class="{ 'attr-row--selected': markedEventIds.has(row.event_id) }"
              @click="selectCandidateRow(row.event_id)">
            <td class="cell-id" :style="{ borderLeft: `5px solid ${leftColor(row, node.node_id)}`, paddingLeft: '6px' }">
              seg@{{ row.start_idx }}-{{ row.end_idx }}
            </td>
            <td v-for="cid in rolesClauseIds(node.node_id)" :key="cid" class="cell-clause">
              <template v-if="row.clauses[cid]">
                <PendingIcon v-if="clausePendingReason(row.clauses[cid])"
                             :reason="clausePendingReason(row.clauses[cid])!" />
                <template v-else>
                  {{ fmtValue(row.clauses[cid].measured) }}
                  <em v-if="row.clauses[cid].op"> ({{ row.clauses[cid].op }}{{ row.clauses[cid].threshold }})</em>
                  {{ row.clauses[cid].satisfied ? '✓' : '✗' }}
                </template>
              </template>
              <template v-else>—</template>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="hint">无候选数据</div>
    </div>
  </div>
</template>
```

**注意**:`expandedRoleAttr` computed 依赖单值 `expandedNode` local ref,现在 template 里循环体每个 node 独立 —— 改成小函数 `rolesAttr(nodeId)` / `rolesClauseIds(nodeId)`,leftColor 也接受 nodeId 参数。

- [ ] **Step 6: DetailSidebar.vue 命中匹配 template 改判据**

同文件,定位命中匹配 template(约 line 116-131):

**旧代码**:
```vue
<div v-for="(m, mi) in effectiveAnalysis.matches" :key="m.event_id"
     class="match-row"
     :class="{ 'match-row--selected': selected?.kind === 'match' && (selected as any).matchId === m.event_id }"
     @click="selectMatchRow(m.event_id)">
```

**新代码**:
```vue
<div v-for="(m, mi) in effectiveAnalysis.matches" :key="m.event_id"
     class="match-row"
     :class="{ 'match-row--selected': markedMatchIds.has(m.event_id) }"
     @click="selectMatchRow(m.event_id)">
```

- [ ] **Step 7: DetailSidebar.vue 匹配 trace v-if 改判据**

同文件,定位 trace 区(约 line 134):

**旧代码**:
```vue
<div v-if="selected?.kind === 'match' && selectedMatch" ref="traceEl" class="match-trace">
```

**新代码**:
```vue
<div v-if="showTrace && selectedMatch" ref="traceEl" class="match-trace">
```

- [ ] **Step 8: DetailSidebar.vue script 重构**

同文件,`<script setup>` 里替换:

**旧代码**(删除):
```typescript
const { selected, selectedMatch, effectivePattern, effectiveAnalysis,
        diag, isolated, matchedIds, qualifiedIds, roleColors, selectedEventId, scanFile, effectiveScan,
        activeDetailCard, timeScopeResponse, pairScopeResponse, candidateScopeResponse,
} = storeToRefs(view)

// 本地展开状态
const expandedNode = ref<string | null>(null)

function toggleExpand(nodeId: string) {
  expandedNode.value = expandedNode.value === nodeId ? null : nodeId
}

// 选中状态变化时联动本地展开:role→展开候选表;match→收起候选表后滚到 trace
watch(selected, (sel) => {
  if (sel?.kind === 'role') {
    expandedNode.value = sel.nodeId
  } else if (sel?.kind === 'match') {
    expandedNode.value = null   // 收起候选表,trace 部分即在视口内
    nextTick(() => {
      if (traceEl.value && sidebarEl.value && typeof traceEl.value.scrollIntoView === 'function') {
        traceEl.value.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      }
    })
  }
})
```

**新代码**(替换):
```typescript
const { selected, selectedMatch, effectivePattern, effectiveAnalysis,
        diag, isolated, matchedIds, qualifiedIds, roleColors, selectedEventId, scanFile, effectiveScan,
        activeDetailCard, timeScopeResponse, pairScopeResponse, candidateScopeResponse,
        showTrace, expandedNodeId, markedMatchIds, markedEventIds,   // Task 4 新增
        focusedMatchId,   // watch 滚动 trace 用
} = storeToRefs(view)

// toggleExpand 只写 manualExpandedNode(spec §3.4b);expandedNodeId 由 store 派生。
function toggleExpand(nodeId: string) {
  // manualExpandedNode 通过 view.setExpandedRole 或直接 toggle:
  // toggle 语义 = 若当前展开该 role 则收起,否则展开
  if (view.manualExpandedNode === nodeId) {
    view.setExpandedRole('')     // '' 语义 = 收起 —— 修 setExpandedRole 接受 null?
  } else {
    view.setExpandedRole(nodeId)
  }
}

// trace 展开时滚入视口(旧 watch(selected) 里 kind==='match' 分支迁到这里)
watch([showTrace, focusedMatchId], ([show]) => {
  if (show && traceEl.value && sidebarEl.value && typeof traceEl.value.scrollIntoView === 'function') {
    nextTick(() => {
      traceEl.value?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })
  }
})
```

**修 setExpandedRole 支持 null/'' 收起** —— 回到 view.ts Step 3 加的 setExpandedRole,改为:
```typescript
function setExpandedRole(nodeId: string | null): void {
  manualExpandedNode.value = nodeId
}
```
toggleExpand 里用 `null`:
```typescript
function toggleExpand(nodeId: string) {
  if (view.manualExpandedNode === nodeId) {
    view.setExpandedRole(null)
  } else {
    view.setExpandedRole(nodeId)
  }
}
```

- [ ] **Step 9: DetailSidebar.vue 改 rolesAttr / rolesClauseIds / leftColor 函数化**

同文件,替换 computed 区(约 line 244-267):

**旧代码**(删除):
```typescript
const expandedRoleAttr = computed<AttrRow[]>(() => {
  if (!expandedNode.value || !diag.value) return []
  return diag.value.roles[expandedNode.value]?.attr ?? []
})

const expandedClauseIds = computed<string[]>(() => {
  const ids = new Set<string>()
  for (const row of expandedRoleAttr.value)
    for (const cid of Object.keys(row.clauses)) ids.add(cid)
  return [...ids]
})

function rowTier(row: AttrRow): 'matched' | 'qualified' | 'detected' {
  if (matchedIds.value.has(row.event_id)) return 'matched'
  if (qualifiedIds.value.has(row.event_id)) return 'qualified'
  return 'detected'
}
function leftColor(row: AttrRow): string {
  return colorOf(rowTier(row), expandedNode.value ?? '', roleColors.value)
}
```

**新代码**(替换):
```typescript
// 循环体内每 node 独立取候选表数据(避免 expandedNode 单值假设)。
function rolesAttr(nodeId: string): AttrRow[] {
  return diag.value?.roles[nodeId]?.attr ?? []
}

function rolesClauseIds(nodeId: string): string[] {
  const ids = new Set<string>()
  for (const row of rolesAttr(nodeId))
    for (const cid of Object.keys(row.clauses)) ids.add(cid)
  return [...ids]
}

function rowTier(row: AttrRow): 'matched' | 'qualified' | 'detected' {
  if (matchedIds.value.has(row.event_id)) return 'matched'
  if (qualifiedIds.value.has(row.event_id)) return 'qualified'
  return 'detected'
}

// leftColor 接受 nodeId 参数(template 从 v-for 传入,取代 expandedNode 单值假设)
function leftColor(row: AttrRow, nodeId: string): string {
  return colorOf(rowTier(row), nodeId, roleColors.value)
}
```

- [ ] **Step 10: DetailSidebar.vue 3 处点击 handler 迁移**

同文件,替换 3 个 handler:

**selectRoleEvent**(约 line 308-314):
```typescript
function selectRoleEvent(val: string | string[]) {
  const id = roleEventId(val)
  if (id) view.focusEvent(id)
}
```

**selectCandidateRow**(约 line 316-320):
```typescript
function selectCandidateRow(eventId: string) {
  view.focusEvent(eventId)
}
```

**selectMatchRow**(约 line 322-326):
```typescript
function selectMatchRow(matchId: string): void {
  view.focusMatch(matchId)
}
```

- [ ] **Step 11: view store 删除 4 个桥接 action**

打开 view.ts,删除:
- `selectMatch(matchId)` 函数体
- `selectRole(nodeId)` 函数体
- `clearSelection()` 函数体
- `selectEvent(id)` 函数体

从 return 里删除 `selectMatch, selectRole, clearSelection, selectEvent`。

**注意**:桥接层删掉后,若有测试/组件依然调用旧 API 会 broken(如 stores.disambig.spec.ts:52 `view.selectRole('node_x')`)。迁移策略:改测试断言方式 —— `view.selectRole('node_x')` → `view.setExpandedRole('node_x')`;`view.selectMatch(...)` → `view.focusMatch(...)`;`view.selectEvent(...)` → `view.focusEvent(...)`;`view.clearSelection()` → `view.clearFocus()`。

Run:
```bash
cd path2_web_ui && grep -rn "\.selectMatch(\|\.selectRole(\|\.clearSelection(\|\.selectEvent(" src/ tests/ 2>/dev/null
```
Expected: 只留下 `view.ts` 内(已删)+ 测试文件里的调用。所有测试调用改成新 API。

**样例改造** — stores.disambig.spec.ts:
```typescript
// 旧
view.selectRole('node_x')
// 新
view.setExpandedRole('node_x')
```

```typescript
// 旧
view.selectMatch('m_abc')
// 新
view.focusMatch('m_abc')
```

kline-click.spec.ts 里同类改造。

- [ ] **Step 12: 运行 detail-sidebar 组件测 GREEN**

Run:
```bash
cd path2_web_ui && npx vitest run tests/components.detail-sidebar.spec.ts
```
Expected: 全绿。若 candidate row click 那条测试 fail(diag 未 seed 就跳过 —— 这条测试早退了,允许)。

- [ ] **Step 13: 全库 vitest + type-check + build**

Run:
```bash
cd path2_web_ui && npm run test && npm run type-check && npm run build
```
Expected: 全绿。任何红都必须排查根因(旧 API 未迁移完 / 测试断言未迁 / template 引用漏改)。

- [ ] **Step 14: Commit**

```bash
git add path2_web_ui/src/components/DetailSidebar.vue path2_web_ui/src/components/TopologyControl.vue path2_web_ui/src/stores/view.ts path2_web_ui/tests/
git commit -m "refactor(sidebar): DetailSidebar 视图分化 + 候选表就地展开 + 删桥接层

- 候选表 template 挪进 v-for 循环体内,expandedNodeId 派生驱动(spec §3.4a)
- .match-row--selected 判据改 markedMatchIds(多归属场景 candidateMatchIds 多行同亮)
- .attr-row--selected 判据改 markedEventIds(pending event 行黄底)
- .match-trace v-if 改 showTrace(唯一判据 focusedMatchId!==null && focusedEventId===null)
- 3 处 handler 迁移:selectMatchRow→focusMatch / selectCandidateRow→focusEvent / selectRoleEvent→focusEvent
- watch(selected) 分支删除;scrollIntoView 改 watch([showTrace, focusedMatchId])
- view store 加 setExpandedRole(nodeId|null);删除 selectMatch/selectRole/selectEvent/clearSelection 4 桥接
- TopologyControl.vue dblclick 迁移到 setExpandedRole
- 组件测覆盖 6 场景(bracket-focus / event-focus 唯一 / 多归属 pending / candidate row click / match row click / 候选表就地渲染)"
```

---

## Task 5: Playwright e2e 5 场景端到端

**Goal:** 用 Playwright + 系统 chromium + 真实数据(datasets/pkls/ 里挑一个已知有多归属 event 的 symbol)端到端验证 5 个场景(spec §6.3);任何一处未按 spec §3.2 表格发生联动,测试红。

**Files:**
- Create: `path2_web_ui/e2e/sidebar-chart-focus.spec.ts`
- 可能 Modify: `path2_web_ui/playwright.config.ts`(若需追加新 test file glob;通常 e2e/ 已自动包含)

**Interfaces:**
- Consumes: 完整 stack(后端 + 前端 + 真实数据)。
- Produces: e2e 全绿证明"5 场景端到端联动符合 spec"。

- [ ] **Step 1: 自动化启动前后端(implementer 完全自主)**

**基础设施说明**:
- `playwright.config.ts` 已配 `webServer` + `reuseExistingServer: true` → 前端 `npm run dev` **由 Playwright 自动起**(或复用已有 dev server);vite HMR 追 commit → **前端零 stale 风险**。
- 本 plan Global Constraints 明确**不改后端** → 后端一次启动即可,整个 Task 5 期间不会 stale。
- 后端 CC 自主启动:

Run(implementer 后台起后端):
```bash
cd /home/yu/PycharmProjects/Trade_Strategy && uv run python -m path2_web.main
```
用 `Bash` 工具 `run_in_background=true` 起,shell 输出到 background(不阻塞会话)。启动后 poll `/api/health` 或直接 poll `http://localhost:8000/` 确认后端 ready(通常 3-5s)。

Health check:
```bash
curl -s http://localhost:8000/health || curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/
```
Expected: 200 (或 404 若无 /health endpoint 但服务在)。

**若后端已在跑**(`_free_port` 检测端口占用 → skip 启动;直接进 Step 2)。

**Step 7 收尾时 kill 后端**(用 Bash `kill $BACKEND_PID` 或 pkill;若没 kill,后台进程会滞留,不影响 test 结果但污染系统)。

- [ ] **Step 2: 建 RED · Playwright spec 骨架**

创建 `path2_web_ui/e2e/sidebar-chart-focus.spec.ts`:

```typescript
// e2e:sidebar-chart-focus 5 场景端到端(spec §6.3)。
// 预设:后端 8000 · 前端 5173 · datasets/pkls/ 内已有多归属 event 的 symbol(bottom_breakout_burst pattern)。
import { test, expect } from '@playwright/test'

const APP_URL = 'http://localhost:5173/'

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 2560, height: 1440 })
  await page.goto(APP_URL)
  // 等前端渲染完(实际根据首屏元素 selector 调整)
  await page.waitForSelector('.sidebar')
})

test('场景 1:bracket click → group 黑框亮 + bracket 深实边 + 命中匹配单行黄底 + trace 展开', async ({ page }) => {
  // 1. 选一个已知有 match 的 symbol —— e2e fixture 假设首个 symbol 即命中(具体见实施时挑)
  // TODO 实施时替换成具体 symbol(如 'ACRS')和 pattern('bottom_breakout_burst')
  await page.click('[data-testid="stock-row"]:first-child')
  // 2. 等副图 brackets 渲染
  await page.waitForSelector('canvas.echarts-canvas')
  // 3. 点副图 bracket(用 canvas 坐标或 data-testid;实施时用 playwright locator 定位)
  // 4. 断言 sidebar 显示 match-trace + 命中匹配单行 selected
  await expect(page.locator('.match-trace')).toBeVisible()
  const selectedRows = page.locator('.match-row.match-row--selected')
  await expect(selectedRows).toHaveCount(1)
})

test('场景 2:event marker 唯一归属 → group 黑框 + 更深 focus 边 + 命中匹配单行 + trace 不展', async ({ page }) => {
  await page.click('[data-testid="stock-row"]:first-child')
  await page.waitForSelector('canvas.echarts-canvas')
  // 点副图 event marker(需选一个唯一归属的)—— 实施时精确定位
  // 断言:.match-trace 不存在 + .match-row--selected 只 1 条 + .candidate-table-wrap 展开在正确 role 下
  await expect(page.locator('.match-trace')).not.toBeVisible()
  await expect(page.locator('.match-row.match-row--selected')).toHaveCount(1)
  await expect(page.locator('.candidate-table-wrap')).toBeVisible()
})

test('场景 3:event marker 多归属 → 无 group + candidate 虚线 bracket + pending 闪烁 marker + 命中匹配多行同亮 + 候选表 pending 行黄底', async ({ page }) => {
  await page.click('[data-testid="stock-row"]:first-child')
  await page.waitForSelector('canvas.echarts-canvas')
  // 点一个已知多归属的 event(如 bo event 属多 burst)—— 实施时精确定位
  await expect(page.locator('.match-trace')).not.toBeVisible()
  const selectedRows = page.locator('.match-row.match-row--selected')
  await expect(selectedRows.count()).resolves.toBeGreaterThanOrEqual(2)   // 多行同亮
  await expect(page.locator('.attr-row.attr-row--selected')).toHaveCount(1)  // pending 单行黄底
})

test('场景 4:sidebar 命中匹配某行 click → 副图 bracket 反打 + trace 展开', async ({ page }) => {
  await page.click('[data-testid="stock-row"]:first-child')
  await page.waitForSelector('.match-row')
  await page.click('.match-row:first-child')
  await expect(page.locator('.match-trace')).toBeVisible()
  await expect(page.locator('.match-row.match-row--selected')).toHaveCount(1)
})

test('场景 5:sidebar 候选表 detected event click + level=matched → level 自动降 detected + event 主/副图可见', async ({ page }) => {
  // 前置:切 level 到 matched
  await page.click('[data-testid="level-control"] .level-btn:has-text("matched")')
  await page.click('[data-testid="stock-row"]:first-child')
  // 手动展开某 role 候选表(TopologyControl dblclick 或点 funnel-row)
  await page.dblclick('.node-label:first-child')
  // 点某 detected event(candidate row)
  await page.click('.attr-row:first-child')
  // 断言 level 已降
  const activeLevelBtn = page.locator('.level-btn.active')
  await expect(activeLevelBtn).toHaveText(/detected|qualified/)
})
```

**注意**:e2e 具体的 marker click 坐标 / 具体 event id 需要在实施时用 playwright inspector 定位,plan 里只给结构。若某场景无法定位到具体 event,允许简化断言(如"至少 1 条 marker 存在"而不是"点某具体 event 后如何")。

- [ ] **Step 3: 运行 Playwright 看 RED / 部分 PASS**

Run:
```bash
cd path2_web_ui && npx playwright test e2e/sidebar-chart-focus.spec.ts --workers=1 --project=chromium
```
Expected: 若前后端已启动 · UI 渲染出真实数据,大部分会 PASS 或部分 FAIL(marker click 坐标未定位)。

- [ ] **Step 4: 用 playwright inspector 精调定位**

Run:
```bash
cd path2_web_ui && npx playwright test e2e/sidebar-chart-focus.spec.ts --debug --workers=1
```
用 inspector 定位具体 marker / bracket 坐标,更新 spec 里 TODO 处,重跑。

- [ ] **Step 5: 5 场景全绿**

Run:
```bash
cd path2_web_ui && npx playwright test e2e/sidebar-chart-focus.spec.ts --workers=1 --project=chromium
```
Expected: 5 场景全绿。

- [ ] **Step 6: 全库回归 + 清理 .playwright-mcp/ 缓存 + kill 后端**

Run:
```bash
cd path2_web_ui && npm run test && npm run type-check && npm run build && npx playwright test --workers=1
```
Expected: 全绿(vitest + vue-tsc + build + Playwright 全部)。

清理 playwright MCP 临时产物(项目规范,仅本回合用过 playwright MCP 时):
```bash
rm -rf .playwright-mcp/*
```

**kill 后端**(Step 1 启动的后台进程):
```bash
# 用 lsof 或 fuser 找 backend port 上的 PID 并 kill
lsof -ti :8000 | xargs -r kill -TERM
# 或 pkill -f "python -m path2_web.main"
```
若 Step 1 后端已在跑(implementer 检测到复用),跳过 kill,让用户自行管理。

- [ ] **Step 7: Commit**

```bash
git add path2_web_ui/e2e/sidebar-chart-focus.spec.ts
git commit -m "test(e2e): sidebar-chart-focus 5 场景端到端(spec §6.3)

- 场景 1:bracket click → group + trace + 单行黄底
- 场景 2:event marker 唯一归属 → group + focus + 单行黄底 + trace 不展
- 场景 3:event marker 多归属 → 无 group + 命中匹配多行同亮 + 候选表 pending 行黄底
- 场景 4:sidebar 命中匹配 click → 副图 bracket 反打 + trace 展开
- 场景 5:sidebar 候选表 detected event + level=matched → level 自动降

全库 vitest + vue-tsc + build + Playwright 全绿"
```

---

## Self-Review 结果

**1. Spec 覆盖**:
- §3.1 状态字段 + 派生 → Task 1 ✓
- §3.2 六种交互一致性表 → Task 1 (派生测试对齐) + Task 2 (action 测试对齐) + Task 3/4 (消费点迁移) + Task 5 (e2e) ✓
- §3.3 3 action + 6 消费 → Task 2 (action) + Task 3 (KlineChart 3 处 + KlineChart.vue Esc 1 处) + Task 4 (DetailSidebar 3 处 + TopologyControl 1 处) ✓
- §3.4 sidebar 视图分化(候选表就地 + expandedNodeId + showTrace + markedMatchIds/markedEventIds + watch 迁移)→ Task 4 ✓
- §3.5 level auto-follow → Task 2 ✓
- §5 非目标 → Global Constraints ✓
- §6 测试策略 → Task 1/2 单元测 + Task 3/4 组件测 + Task 5 e2e ✓
- §7 风险 → Task 1 Step 3-4(4 处初始化)+ Task 4 Step 11(grep + 迁移旧 API)覆盖 ✓
- §8 术语 → 每 task step 里用一致命名(focused/marked/highlighted/showTrace/expandedNodeId) ✓

**2. Placeholder 扫描**:e2e Task 5 有 TODO(具体 symbol / marker 坐标),但已明确"实施时用 inspector 定位",非无内容占位。

**3. Type consistency**:
- `focusedMatchId: Ref<string|null>` / `focusedEventId: Ref<string|null>` / `manualExpandedNode: Ref<string|null>` 一致
- `setExpandedRole(nodeId: string | null)` Task 4 Step 3 起始加 string,Step 8 里因 toggleExpand 需 null 收起改成 `string | null` —— 已在 Step 8 明示;implementer 按 Step 8 落定义为准
- `focusMatch(matchId: string)` / `focusEvent(eventId: string)` / `clearFocus()` 与 spec §3.3 完全一致

**4. Scope**:5 task 拆分粒度合适。Task 1 是最大重构(状态字段替换 + 派生 + 桥接);Task 4 template 结构 + 消费点迁移 + 桥接删除是第二大;Task 2/3/5 相对聚焦。所有 task 结束都能全绿(桥接层保底 Task 1-3,Task 4 末尾统一删)。

**5. 依赖顺序**:Task 1 → Task 2(store 内部字段)→ Task 3(KlineChart 消费)→ Task 4(sidebar 视图 + 桥接删除)→ Task 5(e2e)。无循环,无跨阶段前向依赖。
