import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import CandidateStatusBar from '../src/components/CandidateStatusBar.vue'

vi.mock('../src/api', () => ({
  getDiagnose: vi.fn(() => Promise.resolve(null)),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], matches: [], node_index: {} },
    summary: { events: 0, matches: 0 },
    pattern_spec: {} as never, scan: {} as never,
  })),
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as never)),
  deleteScan: vi.fn(() => Promise.resolve({ ok: true })),
  cancelScan: vi.fn(() => Promise.resolve({ ok: true })),
}))

vi.mock('../src/stores/config', () => ({
  useConfigStore: vi.fn(() => ({ config: null })),
}))

describe('CandidateStatusBar (Task 10)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('renders nothing when candidateMatchIds is empty', () => {
    const w = mount(CandidateStatusBar, { props: { matches: [] } })
    expect(w.find('.candidate-banner').exists()).toBe(false)
  })

  it('renders banner with start_idx-sorted ordinals (not raw matches order)', async () => {
    const view = useViewStore()
    // Matches deliberately NOT in start_idx order — ensures ordinal is sorted by start_idx
    const matches = [
      { event_id: 'm_late',  start_idx: 50, end_idx: 60, children: [], node_index: {}, predicate_trace: null },
      { event_id: 'm_early', start_idx: 10, end_idx: 20, children: [], node_index: {}, predicate_trace: null },
      { event_id: 'm_mid',   start_idx: 30, end_idx: 40, children: [], node_index: {}, predicate_trace: null },
    ]
    const w = mount(CandidateStatusBar, { props: { matches } })
    // Subscribe to all three — start_idx sort: m_early=①, m_mid=②, m_late=③
    view.setCandidateMatches(['m_late', 'm_early', 'm_mid'])
    await w.vm.$nextTick()
    const text = w.text()
    expect(text).toContain('① ② ③')
    expect(text).toContain('候选')
    expect(text).toContain('click 任一 bracket')
    expect(text).toContain('Esc 取消')
  })

  it('subset of candidates produces non-sequential ordinals', async () => {
    const view = useViewStore()
    const matches = [
      { event_id: 'm_late',  start_idx: 50, end_idx: 60, children: [], node_index: {}, predicate_trace: null },
      { event_id: 'm_early', start_idx: 10, end_idx: 20, children: [], node_index: {}, predicate_trace: null },
      { event_id: 'm_mid',   start_idx: 30, end_idx: 40, children: [], node_index: {}, predicate_trace: null },
    ]
    const w = mount(CandidateStatusBar, { props: { matches } })
    // Candidate set is {m_early, m_late} (skip m_mid) → expected ① ③
    view.setCandidateMatches(['m_late', 'm_early'])
    await w.vm.$nextTick()
    const text = w.text()
    expect(text).toContain('① ③')
  })

  it('falls back to arabic for ordinal > 9', async () => {
    // 10 matches, candidate is the 10th by start_idx (start_idx: 100, i=9)
    const matches = Array.from({ length: 10 }, (_, i) => ({
      event_id: `m${i}`,
      start_idx: (i + 1) * 10,
      end_idx: (i + 1) * 10 + 5,
      children: [] as string[],
      node_index: {} as Record<string, string>,
      predicate_trace: null,
    }))
    const w = mount(CandidateStatusBar, { props: { matches } })
    const view = useViewStore()
    view.setCandidateMatches(['m9'])  // 10th by start_idx (i=9, start_idx=100) → ordinal 10
    await w.vm.$nextTick()
    expect(w.text()).toContain('10')
  })
})
