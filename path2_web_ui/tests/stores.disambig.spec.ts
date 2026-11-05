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

describe('view store — Task 2 (M\' candidate disambig)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('starts empty', () => {
    const view = useViewStore()
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  it('setCandidateHits replaces Set', () => {
    const view = useViewStore()
    const before = view.candidateHitIds
    view.setCandidateHits(['m1', 'm2'])
    expect(view.candidateHitIds.size).toBe(2)
    expect(view.candidateHitIds.has('m1')).toBe(true)
    expect(view.candidateHitIds).not.toBe(before)
  })

  it('setPendingDisambig sets and clears', () => {
    const view = useViewStore()
    view.setPendingDisambig('inst_x#0')
    expect(view.pendingDisambigInstanceId).toBe('inst_x#0')
    view.setPendingDisambig(null)
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  it('clearCandidates clears both', () => {
    const view = useViewStore()
    view.setCandidateHits(['m1'])
    view.setPendingDisambig('inst_x#0')
    view.clearCandidates()
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  it('setCandidateHits([]) clears pendingDisambig', () => {
    const view = useViewStore()
    view.setPendingDisambig('inst_x#0')
    view.setCandidateHits([])
    expect(view.pendingDisambigInstanceId).toBeNull()
  })
})

describe('view store — Task 7 (cross-context cleanup)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('selectSymbol clears candidate + highlight + selected', () => {
    const view = useViewStore()
    view.setCandidateHits(['m1'])
    view.setPendingDisambig('inst_1#0')
    view.focusedHitId = 'm1'   // 直写:避免 focusHit 内部 clearCandidates() 提前清掉上面的 arrange
    view.focusedInstanceId = 'inst_1#0'
    view.selectSymbol('NEW_TICKER')
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.selectedHitId).toBeNull()
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  it('setActivePattern clears candidate + highlight + selected', () => {
    const view = useViewStore()
    view.setCandidateHits(['m1'])
    view.setPendingDisambig('inst_1#0')
    view.focusedHitId = 'm1'   // 直写:避免 focusHit 内部 clearCandidates() 提前清掉上面的 arrange
    view.focusedInstanceId = 'inst_1#0'
    view.setActivePattern('p_other')
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.selectedHitId).toBeNull()
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  it('clearScanFile clears candidate + highlight + selected', () => {
    const view = useViewStore()
    view.setCandidateHits(['m1'])
    view.setPendingDisambig('inst_1#0')
    view.focusedHitId = 'm1'   // 直写:避免 focusHit 内部 clearCandidates() 提前清掉上面的 arrange
    view.focusedInstanceId = 'inst_1#0'
    view.clearScanFile()
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.selectedHitId).toBeNull()
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.pendingDisambigInstanceId).toBeNull()
  })
})
