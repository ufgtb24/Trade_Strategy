import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'

vi.mock('../src/api', () => ({ saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  getDiagnose: vi.fn(() => Promise.resolve(null)),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], hits: [], node_index: {} },
    summary: { events: 0, hits: 0 },
    pattern_spec: {} as any, scan: {} as any,
  })),
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ ok: true })),
  cancelScan: vi.fn(() => Promise.resolve({ ok: true })),
}))

vi.mock('../src/stores/config', () => ({
  useConfigStore: vi.fn(() => ({ config: null, saveLastPattern: vi.fn() })),
}))

describe('view store — Task 1 (M base)', () => {
  describe('highlightedEventIds', () => {
    beforeEach(() => { setActivePinia(createPinia()) })

    it('starts empty', () => {
      const view = useViewStore()
      expect(view.highlightedEventIds.size).toBe(0)
    })
  })

  describe('view store — selectedHitId + selectHit null (Task 1 extension)', () => {
    beforeEach(() => { setActivePinia(createPinia()) })

    it('selectedHitId is null when nothing selected', () => {
      const view = useViewStore()
      expect(view.selectedHitId).toBeNull()
    })

    it('selectedHitId derives from selected.value.hitId', () => {
      const view = useViewStore()
      view.focusHit('m_abc')
      expect(view.selectedHitId).toBe('m_abc')
    })

    it('selectedHitId is null when a node is expanded (toggleExpandedNode)', () => {
      const view = useViewStore()
      view.toggleExpandedNode('node_x')
      expect(view.selectedHitId).toBeNull()
    })

    it('clearFocus() clears selection', () => {
      const view = useViewStore()
      view.focusHit('m_abc')
      view.clearFocus()
      expect(view.selectedHitId).toBeNull()
      expect(view.selected).toBeNull()
    })
  })
})

// event A 被两次 hit 用到(各买在 2、3 两天):选中它时这两次画细框
const A = { instance_id: 'a_0_1#0', node_id: 'a', instance_idx: 0, start_idx: 0, end_idx: 1, child_refs: {} }
const B2 = { instance_id: 'b_2_2#0', node_id: 'b', instance_idx: 0, start_idx: 2, end_idx: 2, child_refs: {} }
const B3 = { instance_id: 'b_3_3#0', node_id: 'b', instance_idx: 0, start_idx: 3, end_idx: 3, child_refs: {} }
function loadFixture(view: ReturnType<typeof useViewStore>): void {
  view.loadScanFile({
    pattern_ids: ['p1', 'p_other'],
    per_pattern: { p1: {
      end_node: 'b',
      pattern_spec: { pattern_id: 'p1', event_styles: {}, topology: { edges: [], nodes: [
        { node_id: 'a', render_grid: 'time', where_rules: [] },
        { node_id: 'b', render_grid: 'time', where_rules: [], is_point: true },
      ] } },
    } },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [A, B2, B3],
      hits: [
        { hit_id: 'm1', start_idx: 0, end_idx: 2, node_index: { a: A.instance_id, b: B2.instance_id }, children: [] },
        { hit_id: 'm2', start_idx: 0, end_idx: 3, node_index: { a: A.instance_id, b: B3.instance_id }, children: [] },
      ],
    }, summary: { hits: 2 } } } }],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 },
  } as any)
}

describe('view store — 细框(由选中的那条路径派生)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('starts empty', () => {
    const view = useViewStore()
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  it('选中一个 event:用到它的 hit 加细框;走进其中一次之后细框仍在;clearFocus 清掉', () => {
    const view = useViewStore()
    loadFixture(view)
    view.focusMark([A.instance_id])
    expect([...view.candidateHitIds]).toEqual(['m1', 'm2'])
    expect(view.focusedHitId).toBeNull()                 // 只选中了 event,用到它的哪一次都不算选中
    view.stepPos(1)                                      // 进到第一个买点日;那天只有一次,就是那次 hit
    expect(view.focusedHitId).toBe('m1')
    expect([...view.candidateHitIds]).toEqual(['m1', 'm2'])
    view.clearFocus()
    expect(view.candidateHitIds.size).toBe(0)
  })
})

describe('view store — Task 7 (cross-context cleanup)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  function arrange(view: ReturnType<typeof useViewStore>) {
    loadFixture(view)
    view.focusMark([A.instance_id])
    view.stepPos(1)
    expect(view.selPath.length).toBe(3)
    expect(view.candidateHitIds.size).toBe(2)
    view.focusedInstanceId = 'inst_1#0'
  }
  function expectCleared(view: ReturnType<typeof useViewStore>) {
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.selectedHitId).toBeNull()
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.pendingDisambigInstanceId).toBeNull()
    expect(view.selPath).toEqual([])
    expect(view.selInfo).toBeNull()
  }

  it('selectSymbol clears selection + highlight + selected', () => {
    const view = useViewStore()
    arrange(view)
    view.selectSymbol('NEW_TICKER')
    expectCleared(view)
  })

  it('setActivePattern clears selection + highlight + selected', () => {
    const view = useViewStore()
    arrange(view)
    view.setActivePattern('p_other')
    expectCleared(view)
  })

  it('clearScanFile clears selection + highlight + selected', () => {
    const view = useViewStore()
    arrange(view)
    view.clearScanFile()
    expectCleared(view)
  })
})
