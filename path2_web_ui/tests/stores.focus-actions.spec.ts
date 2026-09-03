// Task 8 · focusMatch / focusEvent(单入口 instance_id)/ clearFocus + autoFollowLevel 单元测。
// 与 spec §5「focusEvent 单入口:focusEvent(instanceId: string)」逐行对齐。
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile, MatchDict, EventDict, SerializedPattern } from '../src/types'

// 基础 fixture:1 pattern · 2 nodes(bo/ta)· 1 edge · ta 3 实例(2 归属 1 无) · matches 2
function makeFixture(): MultiScanResultFile {
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: { pattern_spec: {
      pattern_id: 'p1',
      topology: {
        nodes: [
          { node_id: 'bo', render_grid: 'price', where_rules: [] },
          { node_id: 'ta', render_grid: 'time', where_rules: [] },
        ],
        edges: [{ src: 'bo', dst: 'ta', kind: 'TemporalEdge', rule: '', anchor_field: 'anchor_bo_id' }],
      },
      event_styles: {},
    } as any } as any },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [
        { instance_id: 'bo_10#0', node_id: 'bo', instance_idx: 0, start_idx: 10, end_idx: 10, child_refs: {} },
        { instance_id: 'ta_12_15#0', node_id: 'ta', instance_idx: 0, start_idx: 12, end_idx: 15,
          anchor_bo_id: 'bo_10#0', child_refs: {} },
        { instance_id: 'ta_20_22#0', node_id: 'ta', instance_idx: 1, start_idx: 20, end_idx: 22,
          anchor_bo_id: 'bo_10#0', child_refs: {} },
        { instance_id: 'ta_30_32#0', node_id: 'ta', instance_idx: 2, start_idx: 30, end_idx: 32,
          anchor_bo_id: 'bo_10#0', child_refs: {} },
      ],
      matches: [
        { match_id: 'm1', start_idx: 10, end_idx: 15, node_index: { ta: 'ta_12_15#0' }, children: ['bo_10#0', 'ta_12_15#0'] },
        { match_id: 'm2', start_idx: 12, end_idx: 22, node_index: { ta: 'ta_20_22#0' }, children: ['bo_10#0', 'ta_20_22#0'] },
        // ta_30_32#0 不属于任何 match(0 归属)
      ],
    } as any, summary: { matches: 2 } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('view store · focusMatch / focusEvent(单入口)/ clearFocus', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('focusMatch("m1"):focusedMatchId=m1 · 实例焦点清 · manual=null · candidates 清 · showTrace=true', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.toggleExpandedNode('bo')                  // 先 manual = {bo}
    view.toggleExpandedNode('ta')                  // 再加 ta → {bo, ta}(多展开)
    view.setCandidateMatches(['m1', 'm2'])
    view.focusMatch('m1')
    expect(view.focusedMatchId).toBe('m1')
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.manualExpandedNodes.size).toBe(0)  // focusMatch → collapse all(trace 独占)
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.showTrace).toBe(true)
  })

  it('focusEvent 单入口:按 instance_id 直选(1 归属)→ focusedMatchId + focusedInstanceId', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('ta_12_15#0')
    expect(view.focusedMatchId).toBe('m1')
    expect(view.focusedInstanceId).toBe('ta_12_15#0')
    expect(view.selectedInstanceId).toBeNull()
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigInstanceId).toBeNull()
    expect(view.showTrace).toBe(false)
  })

  it('focusEvent 0 归属:ta_30_32#0 → selectedInstanceId 聚焦 · match 不设', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('ta_30_32#0')
    expect(view.focusedMatchId).toBeNull()
    expect(view.selectedInstanceId).toBe('ta_30_32#0')
    expect(view.focusedInstanceId).toBeNull()
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.markedEventIds.has('ta_30_32#0')).toBe(true)
  })

  it('focusEvent 0 归属(anchor 不在 node_index):bo_10#0 → 只聚焦实例(Task 5 契约延续)', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    // 归属判定只按 match.node_index 精确引用;bo_10#0 是 anchor(仅经 anchor_field 反查、
    // 不在 node_index 中)→ 0 归属 → 只聚焦实例,不再弹待选择
    view.focusEvent('bo_10#0')
    expect(view.focusedMatchId).toBeNull()
    expect(view.selectedInstanceId).toBe('bo_10#0')
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigInstanceId).toBeNull()
    expect(view.markedEventIds.has('bo_10#0')).toBe(true) // 信息层聚焦实例
    expect(view.expandedNodeIds.has('bo')).toBe(true)    // focusEvent add → 含 bo
  })

  it('clearFocus:双清 + candidates 清', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusMatch('m1')
    view.clearFocus()
    expect(view.focusedMatchId).toBeNull()
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.showTrace).toBe(false)
  })

  it('level auto-follow:选 detected 实例 + level=matched → setLevel("detected")', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('matched')
    // ta_30_32#0 是 0 归属 → tier=detected(不在 matchedIds,若也不在 qualifiedIds 则 detected)
    view.focusEvent('ta_30_32#0')
    expect(view.level).toBe('detected')
  })

  it('level auto-follow:选 matched 实例 + level=matched → level 不动', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('matched')
    view.focusEvent('ta_12_15#0')                  // 1 归属 · matched
    expect(view.level).toBe('matched')
  })

  it('focusMatch 不触发 level auto-follow', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('matched')
    view.focusMatch('m1')
    expect(view.level).toBe('matched')
  })

  it('clearFocus 补丁: 一并清 shiftSelectedEvents', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setShiftSelectedEvents([{ instance_id: 'bo_10#0', node_id: 'BO', source: 'main' }])
    view.focusedInstanceId = 'ta_12_15#0'
    view.clearFocus()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.shiftSelectedEvents.length).toBe(0)      // shift 也被清
  })
})

// ── Task 8(marker 实例绑定):focusEvent 单入口分级语义 ──────────────────────────
// 归属 = match.node_index 值(instance_id 字符串)精确引用计数 0/1/≥2
//   0 → 只聚焦实例;1 → 直选 match;≥2 → pendingDisambig(真共享实例)
function makeDualEntryFixture(events: EventDict[], matches: MatchDict[]): MultiScanResultFile {
  const pattern: SerializedPattern = {
    pattern_id: 'p1',
    topology: {
      nodes: [
        { node_id: 'burst', render_grid: 'time', where_rules: [] },
        { node_id: 'tb', render_grid: 'time', where_rules: [] },
      ],
      edges: [],
    },
    event_styles: {},
  } as any
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: { pattern_spec: pattern } as any },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events, matches,
    } as any, summary: { matches: matches.length } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('view store · focusEvent 单入口(Task 8 实例绑定)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('focusEvent 按 instance_id 直选分属实例(不再待选择)', () => {
    // APCX 形态:两 match 的 node_index 分别引用 tb_v1_293#0/#1(各属一个 match)
    const m0 = { match_id: 'bb@0-3#burst:burst_0_2|tb:tb_v1_293', start_idx: 0, end_idx: 3,
                 node_index: { burst: 'burst_0_2#0', tb: 'tb_v1_293#0' },
                 children: ['burst_0_2#0', 'tb_v1_293#0'], predicate_trace: null } as MatchDict
    const m1 = { match_id: 'bb@0-3#burst:burst_0_2|tb:tb_v1_293b', start_idx: 0, end_idx: 3,
                 node_index: { burst: 'burst_0_2#1', tb: 'tb_v1_293#1' },
                 children: ['burst_0_2#0', 'tb_v1_293#0'], predicate_trace: null } as MatchDict
    const events: EventDict[] = [
      { instance_id: 'tb_v1_293#0', node_id: 'tb', instance_idx: 0, start_idx: 12, end_idx: 15, child_refs: {} } as any,
      { instance_id: 'tb_v1_293#1', node_id: 'tb', instance_idx: 1, start_idx: 20, end_idx: 22, child_refs: {} } as any,
      { instance_id: 'burst_0_2#0', node_id: 'burst', instance_idx: 0, start_idx: 8, end_idx: 8, child_refs: {} } as any,
    ]
    const view = useViewStore()
    view.loadScanFile(makeDualEntryFixture(events, [m0, m1]))
    view.focusEvent('tb_v1_293#0')
    expect(view.focusedMatchId).toBe(m0.match_id)          // 直选 match A
    expect(view.focusedInstanceId).toBe('tb_v1_293#0')
    expect(view.pendingDisambigInstanceId).toBeNull()       // 不再弹待选择
    view.focusEvent('tb_v1_293#1')
    expect(view.focusedMatchId).toBe(m1.match_id)          // 直选 match B
  })

  it('focusEvent 真共享:同一 instance_id 被两 match 引用 → 待选择', () => {
    const m0 = { match_id: 'bb@0-3a', start_idx: 0, end_idx: 3,
                 node_index: { tb: 'tb_s#0' }, children: ['tb_s#0'], predicate_trace: null } as MatchDict
    const m1 = { match_id: 'bb@0-3b', start_idx: 0, end_idx: 3,
                 node_index: { tb: 'tb_s#0' }, children: ['tb_s#0'], predicate_trace: null } as MatchDict
    const events: EventDict[] = [
      { instance_id: 'tb_s#0', node_id: 'tb', instance_idx: 0, start_idx: 12, end_idx: 15, child_refs: {} } as any,
    ]
    const view = useViewStore()
    view.loadScanFile(makeDualEntryFixture(events, [m0, m1]))
    view.focusEvent('tb_s#0')
    expect(view.pendingDisambigInstanceId).toBe('tb_s#0')
    expect(view.candidateMatchIds.size).toBe(2)
    expect(view.focusedMatchId).toBeNull()
  })
})
