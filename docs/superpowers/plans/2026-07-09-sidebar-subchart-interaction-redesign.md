# Sidebar 与副图交互重设计 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec**：`docs/research/2026-07-09_sidebar-subchart-interaction-redesign/final_report.md`（本 plan 与 spec 语义等价，spec 是设计裁决权威、plan 是实施顺序 + 具体代码）

**Goal**：让 sidebar 与副图/主图的选中/联动语义统一（Q1-Q4）；四处 click site 提取通用入口 `selectEventBy`；`expandedNode` 从组件本地态上提 store 让 chart 侧可驱动；level 自适应"只下调不上调"；命中匹配列表在多归属场景下多行同步高亮（Q3.2 补丁）。

**Architecture**：修修补补 + 提取入口。现有 `selected: {kind:'match'|'role',...} | null` 与 `selectedEventId: string | null` 双 ref 承载正交信息（match 容器上下文 vs 具体 event 焦点），**保留不 unify**。新增 `selectEventBy(eid, triggerCandidateQuery)` dispatcher 承担 A(marker click) + B(sidebar candidate row) 两处入口的通用选中；C(trace role) 与 D(match row) 保持独立各 2-3 行。dispatcher 副效应内嵌 `setExpandedNode`（Q1 联动）+ `autoLowerLevelIfNeeded`（Q4）。DetailSidebar 模板改造：候选表从"独立区域"改为"funnel-row 内嵌"（Q1），trace v-if 加 `selectedEventId===null` 合取（Q3），match-row 高亮判据扩展 `|| candidateMatchIds.has(...)`（Q3.2 补丁）。

**Tech Stack**：Vue3 + Pinia + TypeScript + ECharts + Vitest + `@vue/test-utils`。Playwright（`@playwright/test`）已装。**本 plan 不涉及后端 Python 改动。**

## Global Constraints

- **Implementer 一律 `sonnet`；Reviewer（spec/quality/final holistic）一律 `opus`**（用户 CLAUDE.md 硬约束）
- **一步到位**：无 legacy 兼容层、无 dual-write、无 feature flag（用户 CLAUDE.md 硬约束）
- 每 task 结束跑 **四 gate**：
  1. `cd path2_web_ui && npx vitest run <affected .spec.ts>`
  2. `cd path2_web_ui && npx vue-tsc --noEmit`
  3. `cd path2_web_ui && npm run build`
  4. 主 repo `pytest`（本 plan 不动后端，只需 baseline 无回归）
- **Q5 out-of-scope**：`level=matched` 时 bo marker 消失是数据层独立 bug，用户已独立修复，**不入本 plan**
- **Disambig 源 marker 视觉标记不改**：实证 `chart.ts:80/108/229-237` + `chart.ts:638/678` 已有 `kind: 'pendingDisambig'` 白底琥珀实心边分支，不新增 `PENDING_MARKER_STROKE` 补丁
- **Level 只下调、永不上调**（Q4 决策）
- **命中匹配列表常驻股票级 match 全集**；multi-match（`selectedMatch=null` 但 `candidateMatchIds` 非空）时对应多行同步 selected class（Q3.2 补丁）
- **C(trace role) + D(match row) 保持独立**（不 fold 进 dispatcher，论据见 spec §2.2）
- **中文注释、界面英文**（项目规范）；反对过度设计（第一性原理 + 奥卡姆剃刀）
- 单 session 无监管跑完（遵守 `.claude/rules/plan-execution.md`）
- 遵守 `.claude/rules/tool-call-discipline.md`（工具调用纪律）

## File Structure

- **Modify**：`path2_web_ui/src/stores/view.ts`（+~70 LOC：`expandedNode` state + `setExpandedNode` + `autoLowerLevelIfNeeded` + `selectEventBy` dispatcher + 4 处 reset 追加清 expandedNode + import `matchedIds as matchedIdsOf` + `roleOfEventByBand`）
- **Modify**：`path2_web_ui/src/components/KlineChart.ts`（marker 分支 L93-129 压缩为 `view.selectEventBy(eid, true)`）
- **Modify**：`path2_web_ui/src/components/DetailSidebar.vue`（模板 candidate 表 inline 到 funnel-row 内嵌 + expandedNode 从组件 ref 上提 store + `selectCandidateRow` 改 `selectEventBy(eid, false)` + `selectMatchRow` 补 `selectEvent(null)` + trace v-if 加合取项 + match-row class binding 判据扩展）
- **New Test**：`path2_web_ui/tests/stores.selectEventBy.spec.ts`（dispatcher/level helper/expandedNode 单测）
- **Modify Test**：`path2_web_ui/tests/components.kline-click.spec.ts`（marker 分支 fold 后等价断言）
- **New Test**：`path2_web_ui/tests/components.detail-sidebar.spec.ts`（candidate 表 inline 结构 + click handler 等价 + trace v-if 分流 + match-row 多行高亮）

---

## Task 1: view.ts 状态 + dispatcher 三合一（`expandedNode` + `autoLowerLevelIfNeeded` + `selectEventBy`）

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts`
- Test: `path2_web_ui/tests/stores.selectEventBy.spec.ts`（新建）

**Interfaces:**
- Consumes：现有 `effectivePattern`（含 `topology.edges` 与 `topology.nodes`）、`effectiveAnalysis`（含 `matches` 与 `events`）、`level`、`selected`、`selectedEventId`、`candidateMatchIds`、`pendingDisambigEventId`、`isolated`、`tagMap`、`eventTier`、以及现有 actions `selectMatch` / `selectEvent` / `setLevel` / `setCandidateMatches` / `setPendingDisambig` / `clearCandidates` / `triggerCandidateQuery`。从 `../render/visible` 新 import `matchedIds as matchedIdsOf` + `roleOfEventByBand`
- Produces：
  - state：`expandedNode: Ref<string | null>`
  - actions：
    - `setExpandedNode(id: string | null): void`
    - `autoLowerLevelIfNeeded(eid: string): void`（只下调不上调）
    - `selectEventBy(eid: string, triggerCandidateQuery?: boolean): void`（`triggerCandidateQuery` 默认 `false`；`true` 时内部会 `void triggerCandidateQuery(eid)`）
  - 4 处 reset action（`loadScanFile` / `clearScanFile` / `selectSymbol` / `setActivePattern`）追加清 `expandedNode` 一行

- [ ] **Step 1: 新建测试文件、写 dispatcher 单测 RED**

Create `path2_web_ui/tests/stores.selectEventBy.spec.ts`：

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile } from '../src/types'

// 极简 fixture：1 stock / 1 pattern / 3 nodes(bo isolated + burst + tb) / 1 match
// 覆盖 dispatcher 三分支需要:多归属场景由 2 个 match 共享同一 bo event 触发
function buildFixture(): MultiScanResultFile {
  return {
    scan: { win_start: '2024-01-01', win_end: '2024-06-30', label_horizon: 20 } as any,
    pattern_ids: ['bbb'],
    per_pattern: {
      bbb: {
        pattern_spec: {
          pattern_id: 'bbb',
          topology: {
            nodes: [
              { node_id: 'bo', source_tag: 'bo', render_grid: 'price' },
              { node_id: 'burst', source_tag: 'burst', render_grid: 'time' },
              { node_id: 'tb', source_tag: 'tb', render_grid: 'time' },
            ],
            edges: [{ src: 'burst', dst: 'tb', kind: 'TemporalEdge', anchor_field: 'anchor_bo_id', rule: {} as any }],
          },
          event_styles: {},
        } as any,
      },
    },
    results: [{
      symbol: 'AAPL',
      per_pattern: {
        bbb: {
          summary: { matches: 2 },
          analysis: {
            events: [
              { class_id: 'bo',    event_id: 'bo_1',    start_idx: 10, end_idx: 10, source_tag: 'bo', child_refs: {} },
              { class_id: 'bo',    event_id: 'bo_2',    start_idx: 20, end_idx: 20, source_tag: 'bo', child_refs: {} },
              { class_id: 'burst', event_id: 'burst_1', start_idx: 8,  end_idx: 12, source_tag: 'burst', child_refs: { members: ['bo_1'] } },
              { class_id: 'burst', event_id: 'burst_2', start_idx: 8,  end_idx: 22, source_tag: 'burst', child_refs: { members: ['bo_1'] } },  // 共享 bo_1 → 多归属
              { class_id: 'tb',    event_id: 'tb_1',    start_idx: 30, end_idx: 32, source_tag: 'tb', child_refs: {}, anchor_bo_id: 'bo_1' },
              { class_id: 'tb',    event_id: 'tb_2',    start_idx: 40, end_idx: 42, source_tag: 'tb', child_refs: {}, anchor_bo_id: 'bo_1' },
            ],
            matches: [
              { event_id: 'match_1', start_idx: 8, end_idx: 32, role_index: { burst: 'burst_1', tb: 'tb_1' }, children: ['burst_1', 'tb_1'], predicate_trace: {} },
              { event_id: 'match_2', start_idx: 8, end_idx: 42, role_index: { burst: 'burst_2', tb: 'tb_2' }, children: ['burst_2', 'tb_2'], predicate_trace: {} },
            ],
          } as any,
        },
      },
    }],
  } as any
}

describe('selectEventBy dispatcher', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('ms=0(unmatched event) → selectMatch(null) + selectEvent(eid) + clearCandidates', () => {
    const view = useViewStore()
    view.loadScanFile(buildFixture())
    view.setActivePattern('bbb')
    // bo_2 未被任何 burst.members 引用 → 不进任何 match
    view.selectEventBy('bo_2', false)
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBe('bo_2')
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigEventId).toBeNull()
  })

  it('ms=1(single-match) → selectMatch + selectEvent + clearCandidates', () => {
    const view = useViewStore()
    view.loadScanFile(buildFixture())
    view.setActivePattern('bbb')
    // burst_1 只属 match_1(burst_2 属 match_2)
    view.selectEventBy('burst_1', false)
    expect(view.selectedMatchId).toBe('match_1')
    expect(view.selectedEventId).toBe('burst_1')
    expect(view.candidateMatchIds.size).toBe(0)
  })

  it('ms>1(multi-attribution) → candidate 分歧流,selectedMatch/selectedEvent 皆 null', () => {
    const view = useViewStore()
    view.loadScanFile(buildFixture())
    view.setActivePattern('bbb')
    // bo_1 同时被 burst_1.members 与 burst_2.members 引用 → 归属 match_1 + match_2 两个
    view.selectEventBy('bo_1', false)
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.candidateMatchIds.size).toBe(2)
    expect(view.candidateMatchIds.has('match_1')).toBe(true)
    expect(view.candidateMatchIds.has('match_2')).toBe(true)
    expect(view.pendingDisambigEventId).toBe('bo_1')
  })

  it('副效应:ms<=1 时自动展开 event 所在 role', () => {
    const view = useViewStore()
    view.loadScanFile(buildFixture())
    view.setActivePattern('bbb')
    view.selectEventBy('burst_1', false)
    expect(view.expandedNode).toBe('burst')
  })

  it('副效应:ms=1 且 event 在 isolated node(bo)时不展开 role(bo 无 pattern edge)', () => {
    const view = useViewStore()
    view.loadScanFile(buildFixture())
    view.setActivePattern('bbb')
    view.setExpandedNode('burst')                    // 预置某个展开
    view.selectEventBy('bo_2', false)                // bo_2 是 unmatched(ms=0),bo 是 isolated
    expect(view.expandedNode).toBe('burst')          // isolated 时不覆盖既有 expandedNode
  })

  it('triggerCandidateQuery=false 时 activeDetailCard 不变', () => {
    const view = useViewStore()
    view.loadScanFile(buildFixture())
    view.setActivePattern('bbb')
    view.selectEventBy('burst_1', false)
    expect(view.activeDetailCard).toBeNull()
  })
})

describe('autoLowerLevelIfNeeded', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('level > event tier → setLevel(event tier)', () => {
    const view = useViewStore()
    view.loadScanFile(buildFixture())
    view.setActivePattern('bbb')
    view.setLevel('matched')                          // RANK=2
    // burst_1 是 matched(在 match_1.children 里) → RANK=2,不下调
    view.autoLowerLevelIfNeeded('burst_1')
    expect(view.level).toBe('matched')
  })

  it('level=matched + event tier=detected(qualifiedIds/matchedIds 皆不含)→ 下调到 detected', () => {
    const view = useViewStore()
    view.loadScanFile(buildFixture())
    view.setActivePattern('bbb')
    view.setLevel('matched')
    // bo_2 未进 matchedIds 也未在 qualifiedIds(极简 fixture 无 diag) → tier='detected'
    view.autoLowerLevelIfNeeded('bo_2')
    expect(view.level).toBe('detected')
  })

  it('永不上调:level=detected 时点 matched event 保持 detected', () => {
    const view = useViewStore()
    view.loadScanFile(buildFixture())
    view.setActivePattern('bbb')
    view.setLevel('detected')                         // RANK=0
    view.autoLowerLevelIfNeeded('burst_1')            // burst_1 tier=matched(RANK=2)
    expect(view.level).toBe('detected')               // 不上调
  })
})

describe('expandedNode state + reset 联动', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('setExpandedNode / 初值', () => {
    const view = useViewStore()
    expect(view.expandedNode).toBeNull()
    view.setExpandedNode('burst')
    expect(view.expandedNode).toBe('burst')
    view.setExpandedNode(null)
    expect(view.expandedNode).toBeNull()
  })

  it.each(['loadScanFile', 'clearScanFile', 'selectSymbol', 'setActivePattern'])(
    '%s 应清 expandedNode', (actionName) => {
      const view = useViewStore()
      view.loadScanFile(buildFixture())
      view.setExpandedNode('burst')
      if (actionName === 'loadScanFile')       view.loadScanFile(buildFixture())
      else if (actionName === 'clearScanFile') view.clearScanFile()
      else if (actionName === 'selectSymbol')  view.selectSymbol('AAPL')
      else if (actionName === 'setActivePattern') view.setActivePattern('bbb')
      expect(view.expandedNode).toBeNull()
    })
})
```

- [ ] **Step 2: 运行 test 验证 RED**

```bash
cd path2_web_ui && npx vitest run tests/stores.selectEventBy.spec.ts
```

Expected：`expandedNode` / `setExpandedNode` / `autoLowerLevelIfNeeded` / `selectEventBy` **都不存在** → 全部 FAIL。

- [ ] **Step 3: 修改 view.ts 加 state 与 import**

在 `path2_web_ui/src/stores/view.ts` 顶部 import 段（现有 import `bandKeyOf, eventTierOf` 那行附近）追加：

```typescript
import {
  deriveTagMap, isolatedNodeIds,
  bandKeyOf, eventTierOf, windowOf,
  matchedIds as matchedIdsOf,   // 新增
  roleOfEventByBand,            // 新增
} from '../render/visible'
```

（如现有 import 已含 `matchedIds`——它是 computed 名 collision，要看 line 12-14 的实际 import 列表；如无则新增）。

在 state 段 line 65 附近（现有 `const selectedEventId = ref<string | null>(null)` 下面）追加：

```typescript
  // Q1 联动:sidebar 角色漏斗内嵌候选表的展开态,从组件本地 ref 上提到 store,
  // 让 chart click(dispatcher 副效应)也能驱动 sidebar 展开哪个 role
  const expandedNode = ref<string | null>(null)
```

- [ ] **Step 4: 4 处 reset action 追加清 expandedNode**

在以下 4 个 action 中的现有 `pendingDisambigEventId.value = null` 后面各加一行：

- `loadScanFile`（L195-216 附近）
- `clearScanFile`（L217-233 附近）
- `selectSymbol`（L234-246 附近）
- `setActivePattern`（L247-256 附近）

追加：

```typescript
    expandedNode.value = null
```

- [ ] **Step 5: 在 setPendingDisambig 后新增 3 个 actions**

在现有 `setPendingDisambig` 之后（L317 附近）追加：

```typescript
  function setExpandedNode(id: string | null) { expandedNode.value = id }

  /** Q4 联动:selectEventBy 副效应,只下调不上调。
   *  论据:上调=隐藏其他 marker(消失意外),下调=扩张可见范围(涌现意外)。
   *  用户 Q4 显式请求"调整 level",禁用态方向直接排除。 */
  function autoLowerLevelIfNeeded(eid: string): void {
    const events = effectiveAnalysis.value?.events ?? []
    const e = events.find(x => x.event_id === eid)
    if (!e) return
    const t = eventTier(e)
    const RANK: Record<Level, number> = { matched: 2, qualified: 1, detected: 0 }
    if (RANK[level.value] > RANK[t]) setLevel(t)
  }

  /** 统一选中入口(Q2 复用):A(marker click)与 B(sidebar candidate row)共走此 dispatcher。
   *  ms=0 → 单选 event;ms=1 → 单选 match+event;ms>1 → 进 disambig 中间态。
   *  副效应:自动展开 role(Q1 联动) + 自动下调 level(Q4)。 */
  function selectEventBy(eid: string, triggerCandidateQueryFlag: boolean = false): void {
    const matches = effectiveAnalysis.value?.matches ?? []
    const events  = effectiveAnalysis.value?.events  ?? []
    const edges   = effectivePattern.value?.topology.edges ?? []
    const ms = matches.filter(m => matchedIdsOf([m], events, edges).has(eid))

    if (ms.length === 0) {
      clearCandidates(); selectMatch(null); selectEvent(eid)
    } else if (ms.length === 1) {
      clearCandidates(); selectMatch(ms[0].event_id); selectEvent(eid)
    } else {
      selectMatch(null); selectEvent(null)
      setCandidateMatches(ms.map(m => m.event_id))
      setPendingDisambig(eid)
    }
    // 副效应 1:ms<=1 且 event 有 non-isolated role → 自动展开该 role
    const e = events.find(x => x.event_id === eid)
    if (e && ms.length <= 1) {
      const nodeId = roleOfEventByBand(e, tagMap.value.tagToNodes, tagMap.value.tagList)
      if (nodeId && !isolated.value.has(nodeId)) setExpandedNode(nodeId)
    }
    // 副效应 2:level 自动下调
    autoLowerLevelIfNeeded(eid)

    if (triggerCandidateQueryFlag) void triggerCandidateQuery(eid)
  }
```

- [ ] **Step 6: return object 追加新导出**

在 return 段中（现有 `setCandidateMatches, clearCandidates, setPendingDisambig` 附近）追加：

```typescript
    expandedNode,
    setExpandedNode, autoLowerLevelIfNeeded, selectEventBy,
```

- [ ] **Step 7: 运行 test 验证 GREEN**

```bash
cd path2_web_ui && npx vitest run tests/stores.selectEventBy.spec.ts
```

Expected：全部 PASS。

- [ ] **Step 8: 四 gate**

```bash
cd path2_web_ui && npx vitest run       # 全 vitest 无回归
cd path2_web_ui && npx vue-tsc --noEmit  # 类型无错
cd path2_web_ui && npm run build         # build 绿
cd /home/yu/PycharmProjects/Trade_Strategy && pytest -x --tb=no -q 2>&1 | tail -3   # baseline 无回归
```

Expected：vitest 全绿、vue-tsc 静默、build 成功、pytest 保持 baseline（本 plan 不动后端）。

- [ ] **Step 9: Commit**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/tests/stores.selectEventBy.spec.ts
git commit -m "feat(view): 引入 selectEventBy dispatcher + expandedNode 上提 + level 自适应"
```

---

## Task 2: KlineChart.ts marker 分支 fold 到 `selectEventBy(eid, true)`

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.ts:93-129`
- Test: `path2_web_ui/tests/components.kline-click.spec.ts`

**Interfaces:**
- Consumes：Task 1 提供的 `view.selectEventBy(eid, triggerCandidateQuery)`
- Produces：marker 分支代码从 ~35 LOC 压到 3 LOC；bracket 分支与 empty click 分支**不动**

- [ ] **Step 1: RED · 修改现有 kline-click 测试**

在 `path2_web_ui/tests/components.kline-click.spec.ts` 里定位描述 marker 分支的 test 段（现有测试断言 `ms.length === 0/1/>1` 三分支后 view store 状态）。**保持既有断言不变**（selectEventBy 复用同一语义），追加一条新断言验证 fold 后仍触发 `triggerCandidateQuery`：

```typescript
it('marker click 后触发 triggerCandidateQuery(activeDetailCard=candidate)', () => {
  const view = useViewStore()
  view.loadScanFile(seedFullFixture())  // 复用现有 fixture
  view.setActivePattern('bbb')
  // 模拟 fetch getCandidateDiagnose 成功 → activeDetailCard='candidate'
  vi.spyOn(view, 'triggerCandidateQuery').mockResolvedValue()
  handleChartClick(
    { seriesName: 'points', data: { event_id: 'burst_1' } },
    view.effectiveAnalysis!.matches, view,
  )
  expect(view.triggerCandidateQuery).toHaveBeenCalledWith('burst_1')
})
```

- [ ] **Step 2: 运行 test 验证既有 3 分支 PASS 且新 test RED**

```bash
cd path2_web_ui && npx vitest run tests/components.kline-click.spec.ts
```

Expected：3 分支既有 test 仍 PASS（因为现有实现语义等价），新 spy 断言 RED（因为需要 fold 后才能通过 spy 拦截）。

- [ ] **Step 3: 修改 `KlineChart.ts` marker 分支 fold**

在 `path2_web_ui/src/components/KlineChart.ts` 替换 L93-129（现有 marker 分支的 4 段 if-else + `triggerCandidateQuery` + `matchedIdsOf` filter）为：

```typescript
  // ── marker 分支(points / intervals / price-points / satellites)─────
  if (MARKER_SERIES.includes(p.seriesName) && p.data?.event_id) {
    // A · 统一 dispatcher(Task 1),triggerCandidateQuery=true 保留既有 marker click 触发
    // scope=candidate 查询的语义;dispatcher 内嵌 ms=0/1/>1 三分支 + 副效应(expandedNode/level)
    view.selectEventBy(p.data.event_id, true)
    return
  }
```

同时删除模块顶部现有的 `import { matchedIds as matchedIdsOf } from '../render/visible'`（fold 后此 import 不再被使用；vue-tsc gate 会抓到 unused import）。

- [ ] **Step 4: 运行 test 验证 GREEN**

```bash
cd path2_web_ui && npx vitest run tests/components.kline-click.spec.ts
```

Expected：全部 PASS。

- [ ] **Step 5: 四 gate**

```bash
cd path2_web_ui && npx vitest run
cd path2_web_ui && npx vue-tsc --noEmit
cd path2_web_ui && npm run build
cd /home/yu/PycharmProjects/Trade_Strategy && pytest -x --tb=no -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/components/KlineChart.ts path2_web_ui/tests/components.kline-click.spec.ts
git commit -m "refactor(kline-click): marker 分支 fold 到 selectEventBy dispatcher"
```

---

## Task 3: DetailSidebar.vue candidate 表 inline + expandedNode 从组件迁移到 store

**Files:**
- Modify: `path2_web_ui/src/components/DetailSidebar.vue`
- Test: `path2_web_ui/tests/components.detail-sidebar.spec.ts`（新建）

**Interfaces:**
- Consumes：Task 1 提供的 `view.expandedNode` + `view.setExpandedNode`
- Produces：DetailSidebar 组件本地 `expandedNode` ref **删除**（由 store 提供）；候选表段落**从 funnel-row 之后独立块移到 funnel-row 内嵌**（Q1）；`toggleExpand` 改调 `view.setExpandedNode`

- [ ] **Step 1: RED · 新建 DetailSidebar 组件测试**

Create `path2_web_ui/tests/components.detail-sidebar.spec.ts`：

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import DetailSidebar from '../src/components/DetailSidebar.vue'
import { useViewStore } from '../src/stores/view'
import { seedFullFixture } from './fixtures'  // 复用现有 fixture 助手

describe('DetailSidebar candidate 表 inline', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('expandedNode=null 时不渲染任何 candidate-table-wrap', () => {
    const view = useViewStore()
    view.loadScanFile(seedFullFixture())
    view.setActivePattern('bbb')
    view.setExpandedNode(null)
    const w = mount(DetailSidebar)
    expect(w.findAll('.candidate-table-wrap')).toHaveLength(0)
  })

  it('expandedNode="burst" 时 candidate 表 inline 在 burst funnel-row 下面', () => {
    const view = useViewStore()
    view.loadScanFile(seedFullFixture())
    view.setActivePattern('bbb')
    view.setExpandedNode('burst')
    const w = mount(DetailSidebar)
    // funnel-row 下面就地嵌 candidate-table-wrap(非独立段落)
    const burstRow = w.findAll('.funnel-row').find(r => r.text().includes('burst'))
    expect(burstRow).toBeDefined()
    // inline 判据:candidate-table-wrap 是 burst funnel-row 的子孙(同一 v-for 内嵌)
    expect(burstRow!.find('.candidate-table-wrap').exists()).toBe(true)
  })

  it('toggleExpand 点 funnel-row 后 view.expandedNode 变化(store 驱动)', async () => {
    const view = useViewStore()
    view.loadScanFile(seedFullFixture())
    view.setActivePattern('bbb')
    const w = mount(DetailSidebar)
    const burstRow = w.findAll('.funnel-row').find(r => r.text().includes('burst'))!
    await burstRow.trigger('click')
    expect(view.expandedNode).toBe('burst')
    await burstRow.trigger('click')
    expect(view.expandedNode).toBeNull()
  })
})
```

注：`seedFullFixture` helper 应该已在 `path2_web_ui/tests/fixtures.ts`（前期任务已建）。若不含 3-node bbb 拓扑，实施时按 Task 1 里 fixture 补齐 helper。

- [ ] **Step 2: 运行 test 验证 RED**

```bash
cd path2_web_ui && npx vitest run tests/components.detail-sidebar.spec.ts
```

Expected：候选表**位于 funnel-row 之后独立段**（现有实现），inline 判据全部 FAIL；`view.expandedNode` **不存在**（若 Task 1 已合入则存在，测试基于 Task 1 完成后）；`toggleExpand` 现在改的是**本地** `expandedNode` ref → store 无变化 → FAIL。

- [ ] **Step 3: DetailSidebar.vue 模板改造**

在 `path2_web_ui/src/components/DetailSidebar.vue`：

3.1 · 删除 line 195 组件本地 `expandedNode` ref：

删掉 `const expandedNode = ref<string | null>(null)`（同时删掉 `ref` import 里若不再需要）。

3.2 · 在 storeToRefs 解构里追加 `expandedNode`（现 line 184-188 附近）：

```typescript
const {
  selected, selectedMatch, effectivePattern, effectiveAnalysis,
  diag, isolated, matchedIds, qualifiedIds, roleColors,
  selectedEventId, selectedMatchId, candidateMatchIds,       // 追加 selectedMatchId + candidateMatchIds
  scanFile, effectiveScan, expandedNode,                     // 追加 expandedNode
  activeDetailCard, timeScopeResponse, pairScopeResponse, candidateScopeResponse,
} = storeToRefs(view)
```

3.3 · `toggleExpand` 改调 store action（现 line 197）：

```typescript
function toggleExpand(nodeId: string) {
  view.setExpandedNode(view.expandedNode === nodeId ? null : nodeId)
}
```

3.4 · 候选表**从独立段移到 funnel-row 内嵌**：

- 删除 line 76-113 整个"候选表:展开 pattern role 行时显示"段落（含 `<template v-if="expandedNode && diag">` 到 `</template>` 收尾）
- 在 funnel-row v-for 内部（line 44-74 的 `<div class="funnel-row">`）**关闭 div** 之前追加内嵌候选表 wrap：

```html
      <span class="expand-icon">{{ expandedNode === node.node_id ? '▲' : '▼' }}</span>
    </template>
  </div>
  <!-- Q1 · inline 候选表:仅当此 role 展开且 non-isolated 时嵌入 -->
  <div
    v-if="expandedNode === node.node_id && diag && !isolated.has(node.node_id)"
    class="candidate-table-wrap"
  >
    <div class="candidate-table-title">{{ expandedNode }} 候选</div>
    <table class="candidate-table" v-if="expandedRoleAttr.length">
      <thead>
        <tr>
          <th>事件</th>
          <th v-for="cid in expandedClauseIds" :key="cid">{{ cid }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in expandedRoleAttr"
          :key="row.event_id"
          class="attr-row"
          :class="{ 'attr-row--selected': selectedEventId === row.event_id }"
          @click="selectCandidateRow(row.event_id)"
        >
          <td class="cell-id" :style="{ borderLeft: `5px solid ${leftColor(row)}`, paddingLeft: '6px' }">seg@{{ row.start_idx }}-{{ row.end_idx }}</td>
          <td v-for="cid in expandedClauseIds" :key="cid" class="cell-clause">
            <template v-if="row.clauses[cid]">
              <PendingIcon v-if="clausePendingReason(row.clauses[cid])" :reason="clausePendingReason(row.clauses[cid])!" />
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
```

注：`expandedRoleAttr` / `expandedClauseIds` / `selectCandidateRow` / `leftColor` / `clausePendingReason` / `fmtValue` / `PendingIcon` 全部保持既有（这些是当前文件里已定义的 computed / method / import）。

3.5 · 因为 funnel-row 与其后候选表现在同属一个循环 iteration，外面必须用 template wrap（Vue 不允许 `v-for` 同时输出两个根元素）—— 把整块包在 template 里：

```html
<template v-for="node in effectivePattern.topology.nodes" :key="node.node_id">
  <div class="funnel-row" :class="{ 'funnel-row--selected': expandedNode === node.node_id && !isolated.has(node.node_id) }"
       @click="!isolated.has(node.node_id) && toggleExpand(node.node_id)">
    <!-- ... 既有 funnel-row 内部 ... -->
  </div>
  <div v-if="expandedNode === node.node_id && diag && !isolated.has(node.node_id)"
       class="candidate-table-wrap">
    <!-- ... 上一节的 candidate 表 ... -->
  </div>
</template>
```

- [ ] **Step 4: 运行 test 验证 GREEN**

```bash
cd path2_web_ui && npx vitest run tests/components.detail-sidebar.spec.ts
```

Expected：全部 PASS。

- [ ] **Step 5: 四 gate**

```bash
cd path2_web_ui && npx vitest run
cd path2_web_ui && npx vue-tsc --noEmit
cd path2_web_ui && npm run build
cd /home/yu/PycharmProjects/Trade_Strategy && pytest -x --tb=no -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/components/DetailSidebar.vue path2_web_ui/tests/components.detail-sidebar.spec.ts
git commit -m "refactor(sidebar): candidate 表 inline + expandedNode 上提 store"
```

---

## Task 4: DetailSidebar.vue click handler + v-if 补丁（B/D 迁移 + trace 隐显 + match-row 多行高亮）

**Files:**
- Modify: `path2_web_ui/src/components/DetailSidebar.vue`
- Test: `path2_web_ui/tests/components.detail-sidebar.spec.ts`（追加）

**Interfaces:**
- Consumes：Task 1 的 `view.selectEventBy` + `view.candidateMatchIds` + `view.selectedMatchId`
- Produces：
  - B · `selectCandidateRow(eventId)` 从"clearCandidates + selectEvent"改调 `view.selectEventBy(eventId, false)`
  - D · `selectMatchRow(matchId)` 追加一行 `view.selectEvent(null)`
  - trace section v-if 追加合取项 `selectedEventId === null`
  - match-row `--selected` class binding 判据扩展为 `selectedMatchId === m.event_id || candidateMatchIds.has(m.event_id)`（Q3.2 补丁多行亮）

- [ ] **Step 1: RED · 追加 4 类断言到 components.detail-sidebar.spec.ts**

```typescript
describe('DetailSidebar click handler + v-if 分流', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('B · 点候选行(unmatched)等价 view.selectEventBy(eid,false):ms=0 分支', async () => {
    const view = useViewStore()
    view.loadScanFile(seedFullFixture())
    view.setActivePattern('bbb')
    view.setExpandedNode('bo')  // 假设 bo 也允许展开(实际 isolated 时是走不到,这里用 non-isolated role)
    const w = mount(DetailSidebar)
    // 找 candidate 表里 bo_2(unmatched)行 → 点击
    // ...(具体查找方式按 fixture 实际渲染调整)
    // 断言:等价 selectEventBy 单入口调用后的状态
    // 关键断言:selectedEventId=bo_2, selectedMatchId=null, candidateMatchIds.size=0
  })

  it('D · 点 match 行 → selectedMatchId 变 + selectedEventId 清 null', async () => {
    const view = useViewStore()
    view.loadScanFile(seedFullFixture())
    view.setActivePattern('bbb')
    view.selectEvent('burst_1')                      // 预置一个 event focus
    const w = mount(DetailSidebar)
    const match1Row = w.findAll('.match-row').at(0)!
    await match1Row.trigger('click')
    expect(view.selectedMatchId).toBe('match_1')
    expect(view.selectedEventId).toBeNull()         // Q3 关键:D 补 selectEvent(null)
  })

  it('trace section 仅在 selected.kind=match 且 selectedEventId=null 时显示', async () => {
    const view = useViewStore()
    view.loadScanFile(seedFullFixture())
    view.setActivePattern('bbb')
    view.selectMatch('match_1')
    view.selectEvent(null)
    const w1 = mount(DetailSidebar)
    expect(w1.find('.match-trace').exists()).toBe(true)   // trace 显

    view.selectEvent('burst_1')                            // 用户点了 event marker
    await w1.vm.$nextTick()
    expect(w1.find('.match-trace').exists()).toBe(false)  // trace 隐(Q3 分流)
  })

  it('Q3.2 补丁 · multi-match 时命中匹配列表多行同步 --selected', async () => {
    const view = useViewStore()
    view.loadScanFile(seedFullFixture())
    view.setActivePattern('bbb')
    view.selectEventBy('bo_1', false)                     // bo_1 多归属 → candidateMatchIds={match_1, match_2}
    const w = mount(DetailSidebar)
    const selectedRows = w.findAll('.match-row--selected')
    expect(selectedRows).toHaveLength(2)
  })
})
```

- [ ] **Step 2: 运行 test 验证 RED**

```bash
cd path2_web_ui && npx vitest run tests/components.detail-sidebar.spec.ts
```

Expected：4 类断言全部 FAIL（现有实现未匹配）。

- [ ] **Step 3: DetailSidebar.vue click handler 三处改动**

3.1 · `selectCandidateRow`（现 line 316-320 附近）：

```typescript
function selectCandidateRow(eventId: string) {
  // B · 统一走 dispatcher(Task 1);triggerCandidateQuery=false 保持 sidebar 侧不弹 overlay
  view.selectEventBy(eventId, false)
}
```

3.2 · `selectMatchRow`（现 line 323-326 附近，含 `expandedNode.value = null` 等副效应）：

```typescript
function selectMatchRow(matchId: string) {
  view.selectMatch(matchId)
  view.clearCandidates()
  view.selectEvent(null)                              // Q3 · D 补 selectEvent(null):转 match-only 态使 trace 显
  nextTick(() => traceEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}
```

（若原实现有 `expandedNode.value = null`：删掉——`expandedNode` 已上提 store，需要清则调 `view.setExpandedNode(null)`；本 task 判定不需要清 —— sidebar D 点击是"切换到 match 视角"，用户已展开的候选表不应无因果关闭。若既有测试有此行为断言，去掉此断言）。

- [ ] **Step 4: DetailSidebar.vue trace v-if 补合取项**

现 line 134：

```html
<div v-if="selected?.kind === 'match' && selectedMatch" ref="traceEl" class="match-trace">
```

改为：

```html
<div v-if="selected?.kind === 'match' && selectedMatch && selectedEventId === null" ref="traceEl" class="match-trace">
```

- [ ] **Step 5: DetailSidebar.vue match-row class binding 判据扩展**

现 line 122：

```html
:class="{ 'match-row--selected': selected?.kind === 'match' && (selected as any).matchId === m.event_id }"
```

改为（Q3.2 补丁）：

```html
:class="{ 'match-row--selected':
  (selected?.kind === 'match' && (selected as any).matchId === m.event_id)
  || candidateMatchIds.has(m.event_id)
}"
```

- [ ] **Step 6: 运行 test 验证 GREEN**

```bash
cd path2_web_ui && npx vitest run tests/components.detail-sidebar.spec.ts
```

Expected：全部 PASS。

- [ ] **Step 7: 四 gate**

```bash
cd path2_web_ui && npx vitest run
cd path2_web_ui && npx vue-tsc --noEmit
cd path2_web_ui && npm run build
cd /home/yu/PycharmProjects/Trade_Strategy && pytest -x --tb=no -q 2>&1 | tail -3
```

- [ ] **Step 8: Commit**

```bash
git add path2_web_ui/src/components/DetailSidebar.vue path2_web_ui/tests/components.detail-sidebar.spec.ts
git commit -m "feat(sidebar): B/D click handler 迁移 dispatcher + trace 隐显 + match-row 多行亮"
```

---

## Task 5: E2E 手工验证（Playwright / dev server）

**Files:**
- 不改代码；用 `browser_resize(2560, 1440)` + `scale="device"` 截图证据

**Interfaces:**
- Consumes：Task 1-4 全部落地后的 dev 环境
- Produces：`docs/superpowers/plans/2026-07-09-sidebar-subchart-interaction-redesign-e2e.md`（可选 · 截图 + 验证 checklist）

- [ ] **Step 1: 启动 dev server（前后端）**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy && uv run python scripts/run_path2_web.py &
```

（后台运行 · 前后端一起起）

- [ ] **Step 2: 加载已有 scan（用户有 fresh scan 就用；否则先跑一次 scan）**

- [ ] **Step 3: 逐问验证 checklist**

Q1 · 点角色漏斗 xx role
- [x] 候选表出现在 xx role 行**下面**（不是独立段落）
- [x] 其他 role 折叠状态不动
- [x] 再点一次 xx role → 候选表折叠

Q2 · sidebar 点候选行 vs 副图点 marker
- [x] 分别点 sidebar 里 event row 和副图对应 marker → view store 状态完全等价（`selectedMatchId` / `selectedEventId` / `candidateMatchIds`）
- [x] 副图旧 marker focus 边随选新 marker 消失、旧 group 高亮随消失（清旧 = dispatcher 内 clearCandidates + selectMatch(null) 自动完成）

Q3 · 副图分流
- [x] 点副图 bracket → sidebar 显示"命中匹配 + 匹配 trace"（现状）
- [x] 点副图 matched event marker → sidebar 自动展开该 event 所属 role 候选表 + 选中该 event 行 + 匹配 trace **隐藏**；命中匹配列表里对应 match row 高亮
- [x] 点 sidebar 命中匹配列表里的 match 行 → 副图 bracket 被选中（琥珀实心边）+ sidebar trace 展开（等价点副图 bracket）
- [x] 点副图 unmatched event marker → sidebar 展开候选表 + 选中该 event 行；匹配 trace 与命中匹配列表无对应高亮

Q4 · Level 自适应
- [x] level=matched 下点 sidebar 里 detected event → level 下调到 detected、其他 detected marker 全部涌现
- [x] level=detected 下点 sidebar 里 matched event → level **保持 detected**（不上调、不改）

Q3.2 补丁 · 多归属高亮
- [x] 点副图多归属 event marker → sidebar 命中匹配列表**多行**同步亮起；chart 里多个 candidate bracket 画琥珀虚线边
- [x] 点其中一个亮起的 match row → 转 match-only 态；其他亮起的 match row 熄灭

- [ ] **Step 4: 截图证据**

按项目约定：`browser_resize(2560, 1440)` 前置；`scale="device"`；每问一张 fullPage 截图 + 关键组件 element-level 截图。

- [ ] **Step 5: 清理 Playwright 缓存**

如本回合用了 Playwright MCP：

```bash
rm -rf .playwright-mcp/*
```

- [ ] **Step 6: 关闭 dev server**

- [ ] **Step 7: Commit（e2e 记录，可选）**

如产出了 `-e2e.md` 记录：

```bash
git add docs/superpowers/plans/2026-07-09-sidebar-subchart-interaction-redesign-e2e.md
git commit -m "test(e2e): 交互重设计端到端验证记录"
```

---

## Self-Review

**1. Spec coverage**：
- Q1（候选表 inline） → Task 3 ✓
- Q2（sidebar 点击等价副图）→ Task 1（dispatcher）+ Task 2（marker fold）+ Task 4（B 迁移）✓
- Q3（bracket vs event marker 分流 + matched event 隐 trace） → Task 4（trace v-if 加合取）+ 副效应 expandedNode 自动展开（Task 1 dispatcher 内嵌）✓
- Q3.2 补丁（多归属命中匹配列表多行亮）→ Task 4 match-row class 判据扩展 ✓
- Q4（level 只下调） → Task 1 `autoLowerLevelIfNeeded` 内嵌 dispatcher ✓
- Q5（数据层 bug） → out-of-scope（用户已修）
- Disambig 源 marker 视觉标记 → 保留现有实心边（Global Constraints 明确不改）
- C(trace role)/D(match row) 独立 → 保留（Task 4 D 只补 selectEvent(null)，不 fold）

**2. Placeholder scan**：
- 无 "TBD"/"TODO"/"implement later"/"handle edge cases"（scan 通过）
- 每步含具体 diff / 具体命令 / 具体断言（scan 通过）

**3. Type consistency**：
- `selectEventBy(eid, triggerCandidateQueryFlag?: boolean)` 签名在 Task 1 定义、Task 2 与 Task 4 消费 ✓
- `expandedNode: Ref<string | null>` Task 1 定义、Task 3/4 通过 storeToRefs 消费 ✓
- `setExpandedNode(id: string | null)` Task 1 定义、Task 3 消费（toggleExpand 内）✓
- `autoLowerLevelIfNeeded(eid: string)` Task 1 定义、内嵌于 selectEventBy 副效应、无外部消费 ✓
- `candidateMatchIds: ReadonlySet<string>` 现有 state（Task 1 不改），Task 4 消费于 match-row class binding ✓
- `selectedMatchId` computed 现有、Task 4 消费 ✓

**4. Task 依赖顺序**：
- Task 2/3/4 都消费 Task 1 的新 store API → Task 1 必须先落
- Task 3 修改模板结构（候选表位置）与 Task 4 修改 click handler / v-if / class binding **同文件**但**不同片段**，可分开走 —— Task 3 先落让 Task 4 的模板断言基于新结构
- Task 5 依赖 1-4 全绿

**5. 潜在坑**：
- `matchedIds` name collision：view.ts 的 return 里已有 computed `matchedIds`，import 必须用 `as matchedIdsOf`（Task 1 Step 3 已给 pattern）
- Vue3 `<template v-for>` 内嵌两块（funnel-row + candidate-wrap）：需用 template 外壳，否则 Vue 报单根警告（Task 3 Step 3.5 给了 template wrap）
- vitest fixture `seedFullFixture` 若不存在，Task 3 Step 1 可直接把 Task 1 里的 buildFixture 提到 `tests/fixtures.ts` 复用

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-09-sidebar-subchart-interaction-redesign.md`.**

**推荐执行方式（用户 CLAUDE.md 硬约束）：subagent-driven-development**
- Implementer 一律 `sonnet`；Reviewer（spec/quality/final holistic）一律 `opus`
- 每 task 结束 spec + quality 双审 approve 后 fix commit 落地
- 全 plan 结束跑 final whole-branch review（`opus`）
- 单 session 无监管跑完（`.claude/rules/plan-execution.md`）

**可粘贴到新 session 执行命令**（见下一条消息代码块）
