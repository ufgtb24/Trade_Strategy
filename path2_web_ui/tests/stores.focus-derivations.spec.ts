// Task 1 · 派生 computed 一致性测试。直接写 focusedMatchId/focusedEventId/manualExpandedNodes
// 底层 ref(而非经 focusMatch/focusEvent 等高层 action)构造前置状态,让"给定状态 → 派生是否正确"
// 与 action 内部的归属判定逻辑解耦(后者见 stores.focus-actions.spec.ts);
// 与 spec §3.2 六种交互对齐(见 docs/superpowers/specs/2026-07-09-sidebar-chart-focus-unification-design.md)。
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
    node_index: { ta: 'e_ta_1' } as any,
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

  it('focusedMatchId="m1"(直写):selected/selectedMatch/selectedMatchId 派生 + showTrace=true + highlightedEventIds 含 members', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusedMatchId = 'm1'
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

  it('focusEvent("e_bo_1") 唯一归属:selectedEventId 派生 + showTrace=false + expandedNodeIds 含 bo', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('e_bo_1')                  // e_bo_1 via anchor_field 归属 m1(唯一)
    expect(view.selectedEventId).toBe('e_bo_1')
    expect(view.selectedMatchId).toBe('m1')
    expect(view.showTrace).toBe(false)
    expect(view.expandedNodeIds.has('bo')).toBe(true)  // add 焦点 node,不折叠其他
    expect(view.markedEventIds.has('e_bo_1')).toBe(true)
  })

  it('focusEvent("e_ta_1") 唯一归属:同时驱动 match + event 焦点 + add {ta}', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('e_ta_1')
    expect(view.selectedMatchId).toBe('m1')
    expect(view.selectedEventId).toBe('e_ta_1')
    expect(view.showTrace).toBe(false)         // event 存在 → 不展 trace
    expect(view.markedMatchIds.has('m1')).toBe(true)
    expect(view.markedEventIds.has('e_ta_1')).toBe(true)
    expect(view.expandedNodeIds.has('ta')).toBe(true)
  })

  it('setPendingDisambig 单独调不自动 push manualExpandedNodes(白盒 · 外部不应直调)', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setCandidateMatches(['m1', 'm2'])
    view.setPendingDisambig('e_ta_1')
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.markedMatchIds.size).toBe(2)   // 信息层如实反映所有归属
    expect(view.markedMatchIds.has('m1')).toBe(true)
    expect(view.markedMatchIds.has('m2')).toBe(true)
    expect(view.markedEventIds.has('e_ta_1')).toBe(true)
    expect(view.expandedNodeIds.size).toBe(0)  // manual 未设 → 空集(pending 单独调不 push,
                                                //   多归属场景经 focusEvent 会 push,见 focus-actions.spec.ts)
    expect(view.highlightedEventIds.size).toBe(0)  // 视觉层:多归属不亮 group
  })

  it('toggleExpandedNode("bo"):add 到 manualExpandedNodes → expandedNodeIds 含 bo', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.toggleExpandedNode('bo')
    expect(view.selected).toBeNull()          // 派生 selected 只看 focusedMatchId(node 分支已删)
    expect(view.selectedMatchId).toBeNull()
    expect(view.expandedNodeIds.has('bo')).toBe(true)
    expect(view.expandedNodeIds.size).toBe(1)
  })

  it('多 node 同时展开:toggleExpandedNode 顺序 add(不折叠其他);再点已展开 → 折叠该行', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.toggleExpandedNode('bo')
    view.toggleExpandedNode('ta')
    expect(view.expandedNodeIds.size).toBe(2)
    expect(view.expandedNodeIds.has('bo')).toBe(true)
    expect(view.expandedNodeIds.has('ta')).toBe(true)
    view.toggleExpandedNode('bo')             // 点已展开 → 折叠 bo(用户诉求)
    expect(view.expandedNodeIds.has('bo')).toBe(false)
    expect(view.expandedNodeIds.has('ta')).toBe(true)
    expect(view.expandedNodeIds.size).toBe(1)
  })

  it('focusEvent add 焦点 node,不折叠其他已展开 node', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.toggleExpandedNode('bo')             // manual = {bo}
    view.toggleExpandedNode('ta')             // manual = {bo, ta}
    expect(view.expandedNodeIds.size).toBe(2)
    view.focusEvent('e_ta_1')                  // marker click auto → add(ta 已在,原样)
    expect(view.expandedNodeIds.has('ta')).toBe(true)
    expect(view.expandedNodeIds.has('bo')).toBe(true)  // 不再被自动折叠
    expect(view.expandedNodeIds.size).toBe(2)
  })

  it('focusEvent 焦点 node 未展开时 add 而非 replace(保留其他已展开)', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.toggleExpandedNode('bo')             // manual = {bo}
    view.focusEvent('e_ta_1')                  // ta 未展开 → add ta
    expect(view.expandedNodeIds.has('ta')).toBe(true)
    expect(view.expandedNodeIds.has('bo')).toBe(true)  // bo 保留
    expect(view.expandedNodeIds.size).toBe(2)
  })

  it('clearFocus:清 focused,但 manualExpandedNodes 保留', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusedMatchId = 'm1'
    view.toggleExpandedNode('bo')             // manualExpandedNodes = {bo}
    view.clearFocus()
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.showTrace).toBe(false)
    expect(view.expandedNodeIds.has('bo')).toBe(true)    // manual 保留
    expect(view.expandedNodeIds.size).toBe(1)
  })

  it('shiftPairPending: length ∈ {0,1,2} 三态派生', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    expect(view.shiftPairPending).toBe(false)           // length=0
    view.setShiftSelectedEvents([{ event_id: 'e_bo_1', class_id: 'BO', source: 'main' }])
    expect(view.shiftPairPending).toBe(true)            // length=1
    view.setShiftSelectedEvents([
      { event_id: 'e_bo_1', class_id: 'BO', source: 'main' },
      { event_id: 'e_ta_1', class_id: 'TA', source: 'main' },
    ])
    expect(view.shiftPairPending).toBe(false)           // length=2
  })

  it('shiftSelectedEventIds: Set 派生正确', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    expect(view.shiftSelectedEventIds.size).toBe(0)
    view.setShiftSelectedEvents([{ event_id: 'e_bo_1', class_id: 'BO', source: 'main' }])
    expect(view.shiftSelectedEventIds.has('e_bo_1')).toBe(true)
    expect(view.shiftSelectedEventIds.size).toBe(1)
    view.setShiftSelectedEvents([
      { event_id: 'e_bo_1', class_id: 'BO', source: 'main' },
      { event_id: 'e_ta_1', class_id: 'TA', source: 'main' },
    ])
    expect(view.shiftSelectedEventIds.has('e_bo_1')).toBe(true)
    expect(view.shiftSelectedEventIds.has('e_ta_1')).toBe(true)
    expect(view.shiftSelectedEventIds.size).toBe(2)
  })

  it('clearShiftSelection: 仅清 shiftSelectedEvents,不动 focus/candidate', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setShiftSelectedEvents([{ event_id: 'e_bo_1', class_id: 'BO', source: 'main' }])
    view.focusedEventId = 'e_ta_1'
    view.clearShiftSelection()
    expect(view.shiftSelectedEvents.length).toBe(0)
    expect(view.focusedEventId).toBe('e_ta_1')          // focus 未被清
  })
})
