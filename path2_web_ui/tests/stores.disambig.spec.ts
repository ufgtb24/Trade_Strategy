import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'

vi.mock('../src/api', () => ({
  getDiagnose: vi.fn(() => Promise.resolve(null)),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], matches: [], node_index: {} },
    summary: { events: 0, matches: 0 },
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

    // Task 3:highlightedEventIds 从 ref+setter 改为 computed(依赖 selectedMatch,协议驱动
    // 沿 child_refs/anchor_field 展开)。setHighlightedEvents/clearHighlight 已不存在——
    // 协议派生行为见 tests/components.kline-click.spec.ts 末尾专项测试。
  })

  describe('view store — selectedMatchId + selectMatch null (Task 1 extension)', () => {
    beforeEach(() => { setActivePinia(createPinia()) })

    it('selectedMatchId is null when nothing selected', () => {
      const view = useViewStore()
      expect(view.selectedMatchId).toBeNull()
    })

    it('selectedMatchId derives from selected.value.matchId', () => {
      const view = useViewStore()
      view.focusMatch('m_abc')
      expect(view.selectedMatchId).toBe('m_abc')
    })

    it('selectedMatchId is null when a node is expanded (toggleExpandedNode)', () => {
      const view = useViewStore()
      view.toggleExpandedNode('node_x')
      expect(view.selectedMatchId).toBeNull()
    })

    it('clearFocus() clears selection', () => {
      const view = useViewStore()
      view.focusMatch('m_abc')
      view.clearFocus()
      expect(view.selectedMatchId).toBeNull()
      expect(view.selected).toBeNull()
    })
  })
})

describe('view store — Task 2 (M\' candidate disambig)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('starts empty', () => {
    const view = useViewStore()
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigEventId).toBeNull()
  })

  it('setCandidateMatches replaces Set', () => {
    const view = useViewStore()
    const before = view.candidateMatchIds
    view.setCandidateMatches(['m1', 'm2'])
    expect(view.candidateMatchIds.size).toBe(2)
    expect(view.candidateMatchIds.has('m1')).toBe(true)
    expect(view.candidateMatchIds).not.toBe(before)
  })

  it('setPendingDisambig sets and clears', () => {
    const view = useViewStore()
    view.setPendingDisambig('evt_x')
    expect(view.pendingDisambigEventId).toBe('evt_x')
    view.setPendingDisambig(null)
    expect(view.pendingDisambigEventId).toBeNull()
  })

  it('clearCandidates clears both', () => {
    const view = useViewStore()
    view.setCandidateMatches(['m1'])
    view.setPendingDisambig('evt_x')
    view.clearCandidates()
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigEventId).toBeNull()
  })

  it('setCandidateMatches([]) clears pendingDisambig', () => {
    const view = useViewStore()
    view.setPendingDisambig('evt_x')
    view.setCandidateMatches([])
    expect(view.pendingDisambigEventId).toBeNull()
  })
})

describe('view store — Task 7 (cross-context cleanup)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('selectSymbol clears candidate + highlight + selected', () => {
    const view = useViewStore()
    view.setCandidateMatches(['m1'])
    view.setPendingDisambig('e1')
    view.focusedMatchId = 'm1'   // 直写:避免 focusMatch 内部 clearCandidates() 提前清掉上面的 arrange
    view.focusedEventId = 'e1'
    view.selectSymbol('NEW_TICKER')
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.pendingDisambigEventId).toBeNull()
  })

  it('setActivePattern clears candidate + highlight + selected', () => {
    const view = useViewStore()
    view.setCandidateMatches(['m1'])
    view.setPendingDisambig('e1')
    view.focusedMatchId = 'm1'   // 直写:避免 focusMatch 内部 clearCandidates() 提前清掉上面的 arrange
    view.focusedEventId = 'e1'
    view.setActivePattern('p_other')
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.pendingDisambigEventId).toBeNull()
  })

  it('clearScanFile clears candidate + highlight + selected', () => {
    const view = useViewStore()
    view.setCandidateMatches(['m1'])
    view.setPendingDisambig('e1')
    view.focusedMatchId = 'm1'   // 直写:避免 focusMatch 内部 clearCandidates() 提前清掉上面的 arrange
    view.focusedEventId = 'e1'
    view.clearScanFile()
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.pendingDisambigEventId).toBeNull()
  })
})
