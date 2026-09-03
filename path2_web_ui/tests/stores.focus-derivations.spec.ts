// Task 8 · 派生 computed 一致性测试。直接写 focusedMatchId/selectedInstanceId/
// focusedInstanceId/manualExpandedNodes 底层 ref(而非经 focusMatch/focusEvent 等高层
// action)构造前置状态,让"给定状态 → 派生是否正确"与 action 内部的归属判定逻辑解耦
// (后者见 stores.focus-actions.spec.ts)。
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile, Analysis, SerializedPattern, TopoNode, TopoEdge, MatchDict, EventDict } from '../src/types'

// 最小 fixture:1 pattern · 2 nodes(bo/ta)· 1 edge · 1 match · events 集合(实例化契约)
function makeFixture(): MultiScanResultFile {
  const nodes: TopoNode[] = [
    { node_id: 'bo', render_grid: 'price', where_rules: [] } as any,
    { node_id: 'ta', render_grid: 'time', where_rules: [] } as any,
  ]
  const edges: TopoEdge[] = [
    { src: 'bo', dst: 'ta', kind: 'TemporalEdge', rule: '', anchor_field: 'anchor_bo_id' } as any,
  ]
  const pattern: SerializedPattern = {
    pattern_id: 'p1',
    topology: { nodes, edges },
    event_styles: {},
  } as any
  const events: EventDict[] = [
    { instance_id: 'bo_10#0', node_id: 'bo', instance_idx: 0, start_idx: 10, end_idx: 10, child_refs: {} } as any,
    { instance_id: 'ta_12_15#0', node_id: 'ta', instance_idx: 0, start_idx: 12, end_idx: 15,
      anchor_bo_id: 'bo_10#0', child_refs: {} } as any,
  ]
  const m1: MatchDict = {
    match_id: 'm1',
    start_idx: 10, end_idx: 15,
    node_index: { ta: 'ta_12_15#0' } as any,
    children: ['bo_10#0', 'ta_12_15#0'],
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
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
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
    expect(view.selectedMatch?.match_id).toBe('m1')
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.showTrace).toBe(true)
    // highlightedEventIds 含 ta_12_15#0(node_index 引用);bo_10#0 经 anchor_field 反查,
    // 但高亮用 expandAnchor=false(避免共享 leaf 反向污染),故 bo_10#0 不进高亮集
    expect(view.highlightedEventIds.has('ta_12_15#0')).toBe(true)
    expect(view.highlightedEventIds.has('bo_10#0')).toBe(false)
    expect(view.markedMatchIds.has('m1')).toBe(true)
  })

  it('focusEvent("bo_10#0") 0 归属(anchor 不在 node_index):selectedInstanceId 派生 + match 不设 + expandedNodeIds 含 bo', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    // 归属判定只按 match.node_index 精确引用;bo_10#0 仅经 anchor_field 反查、不在
    // node_index 中 → 0 归属 → 只聚焦实例(match 不设)
    view.focusEvent('bo_10#0')
    expect(view.selectedInstanceId).toBe('bo_10#0')
    expect(view.selectedMatchId).toBeNull()
    expect(view.showTrace).toBe(false)
    expect(view.expandedNodeIds.has('bo')).toBe(true)  // add 焦点 node,不折叠其他
    expect(view.markedEventIds.has('bo_10#0')).toBe(true)
  })

  it('focusEvent("ta_12_15#0") 唯一归属:同时驱动 match + 实例焦点 + add {ta}', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('ta_12_15#0')
    expect(view.selectedMatchId).toBe('m1')
    expect(view.focusedInstanceId).toBe('ta_12_15#0')
    expect(view.showTrace).toBe(false)         // 实例焦点存在 → 不展 trace
    expect(view.markedMatchIds.has('m1')).toBe(true)
    expect(view.markedEventIds.has('ta_12_15#0')).toBe(true)
    expect(view.expandedNodeIds.has('ta')).toBe(true)
  })

  it('setPendingDisambig 单独调不自动 push manualExpandedNodes(白盒 · 外部不应直调)', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setCandidateMatches(['m1', 'm2'])
    view.setPendingDisambig('ta_12_15#0')
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.markedMatchIds.size).toBe(2)   // 信息层如实反映所有归属
    expect(view.markedMatchIds.has('m1')).toBe(true)
    expect(view.markedMatchIds.has('m2')).toBe(true)
    expect(view.markedEventIds.has('ta_12_15#0')).toBe(true)
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
    view.focusEvent('ta_12_15#0')             // marker click auto → add(ta 已在,原样)
    expect(view.expandedNodeIds.has('ta')).toBe(true)
    expect(view.expandedNodeIds.has('bo')).toBe(true)  // 不再被自动折叠
    expect(view.expandedNodeIds.size).toBe(2)
  })

  it('focusEvent 焦点 node 未展开时 add 而非 replace(保留其他已展开)', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.toggleExpandedNode('bo')             // manual = {bo}
    view.focusEvent('ta_12_15#0')             // ta 未展开 → add ta
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
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.showTrace).toBe(false)
    expect(view.expandedNodeIds.has('bo')).toBe(true)    // manual 保留
    expect(view.expandedNodeIds.size).toBe(1)
  })

  it('shiftPairPending: length ∈ {0,1,2} 三态派生', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    expect(view.shiftPairPending).toBe(false)           // length=0
    view.setShiftSelectedEvents([{ instance_id: 'bo_10#0', node_id: 'BO', source: 'main' }])
    expect(view.shiftPairPending).toBe(true)            // length=1
    view.setShiftSelectedEvents([
      { instance_id: 'bo_10#0', node_id: 'BO', source: 'main' },
      { instance_id: 'ta_12_15#0', node_id: 'TA', source: 'main' },
    ])
    expect(view.shiftPairPending).toBe(false)           // length=2
  })

  it('shiftSelectedEventIds: Set 派生正确', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    expect(view.shiftSelectedEventIds.size).toBe(0)
    view.setShiftSelectedEvents([{ instance_id: 'bo_10#0', node_id: 'BO', source: 'main' }])
    expect(view.shiftSelectedEventIds.has('bo_10#0')).toBe(true)
    expect(view.shiftSelectedEventIds.size).toBe(1)
    view.setShiftSelectedEvents([
      { instance_id: 'bo_10#0', node_id: 'BO', source: 'main' },
      { instance_id: 'ta_12_15#0', node_id: 'TA', source: 'main' },
    ])
    expect(view.shiftSelectedEventIds.has('bo_10#0')).toBe(true)
    expect(view.shiftSelectedEventIds.has('ta_12_15#0')).toBe(true)
    expect(view.shiftSelectedEventIds.size).toBe(2)
  })

  it('clearShiftSelection: 仅清 shiftSelectedEvents,不动 focus/candidate', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setShiftSelectedEvents([{ instance_id: 'bo_10#0', node_id: 'BO', source: 'main' }])
    view.focusedInstanceId = 'ta_12_15#0'
    view.clearShiftSelection()
    expect(view.shiftSelectedEvents.length).toBe(0)
    expect(view.focusedInstanceId).toBe('ta_12_15#0')   // focus 未被清
  })
})
