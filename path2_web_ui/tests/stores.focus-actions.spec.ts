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
        { event_id: 'm1', start_idx: 10, end_idx: 15, node_index: { ta: 'e_ta_1' }, children: ['e_ta_1'] },
        { event_id: 'm2', start_idx: 12, end_idx: 22, node_index: { ta: 'e_ta_2' }, children: ['e_ta_2'] },
        // e_ta_2 属于 m2;e_ta_3 不属于任何 match(0 归属)
      ],
    } as any, summary: { matches: 2 } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('view store · focusMatch / focusEvent / clearFocus', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('focusMatch("m1"):focusedMatchId=m1 · focusedEventId=null · manual=null · candidates 清 · showTrace=true', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.toggleExpandedNode('bo')                  // 先 manual = {bo}
    view.toggleExpandedNode('ta')                  // 再加 ta → {bo, ta}(多展开)
    view.setCandidateMatches(['m1', 'm2'])
    view.focusMatch('m1')
    expect(view.focusedMatchId).toBe('m1')
    expect(view.focusedEventId).toBeNull()
    expect(view.manualExpandedNodes.size).toBe(0)  // focusMatch → collapse all(trace 独占)
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
    expect(view.expandedNodeIds.has('bo')).toBe(true)  // focusEvent add → 含 bo
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

  it('clearFocus 补丁: 一并清 shiftSelectedEvents', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setShiftSelectedEvents([{ event_id: 'e_bo_1', class_id: 'BO', source: 'main' }])
    view.focusedEventId = 'e_ta_1'
    view.clearFocus()
    expect(view.focusedEventId).toBeNull()
    expect(view.shiftSelectedEvents.length).toBe(0)      // shift 也被清
  })
})
