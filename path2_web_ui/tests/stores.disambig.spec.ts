import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'

vi.mock('../src/api', () => ({
  getDiagnose: vi.fn(() => Promise.resolve(null)),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], matches: [], role_index: {} },
    summary: { events: 0, matches: 0 },
    pattern_spec: {} as any, scan: {} as any,
  })),
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ ok: true })),
  cancelScan: vi.fn(() => Promise.resolve({ ok: true })),
}))

vi.mock('../src/stores/config', () => ({
  useConfigStore: vi.fn(() => ({ config: null })),
}))

describe('view store — Task 1 (M base)', () => {
  describe('highlightedEventIds', () => {
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

  describe('view store — selectedMatchId + selectMatch null (Task 1 extension)', () => {
    beforeEach(() => { setActivePinia(createPinia()) })

    it('selectedMatchId is null when nothing selected', () => {
      const view = useViewStore()
      expect(view.selectedMatchId).toBeNull()
    })

    it('selectedMatchId derives from selected.value.matchId', () => {
      const view = useViewStore()
      view.selectMatch('m_abc')
      expect(view.selectedMatchId).toBe('m_abc')
    })

    it('selectedMatchId is null when a role is selected (kind=role)', () => {
      const view = useViewStore()
      view.selectRole('node_x')
      expect(view.selectedMatchId).toBeNull()
    })

    it('selectMatch(null) clears selection', () => {
      const view = useViewStore()
      view.selectMatch('m_abc')
      view.selectMatch(null)
      expect(view.selectedMatchId).toBeNull()
      expect(view.selected).toBeNull()
    })
  })
})
