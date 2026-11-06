import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import CandidateStatusBar from '../src/components/CandidateStatusBar.vue'

vi.mock('../src/api', () => ({ saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  getDiagnose: vi.fn(() => Promise.resolve(null)),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], hits: [], node_index: {} },
    summary: { events: 0, hits: 0 },
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

  it('renders nothing when candidateHitIds is empty', () => {
    const w = mount(CandidateStatusBar, { props: { hits: [] } })
    expect(w.find('.candidate-banner').exists()).toBe(false)
  })

  it('待选时只报个数 + 操作键(bracket 折叠后一行几十次 hit,圈号已无意义)', async () => {
    const view = useViewStore()
    const hits = [
      { hit_id: 'm_late',  start_idx: 50, end_idx: 60, children: [], node_index: {}, predicate_trace: null },
      { hit_id: 'm_early', start_idx: 10, end_idx: 20, children: [], node_index: {}, predicate_trace: null },
      { hit_id: 'm_mid',   start_idx: 30, end_idx: 40, children: [], node_index: {}, predicate_trace: null },
    ]
    const w = mount(CandidateStatusBar, { props: { hits } })
    view.setCandidateHits(['m_late', 'm_early'])
    await w.vm.$nextTick()
    const text = w.text()
    expect(text).toContain('candidates 2')
    expect(text).toContain('←/→')
    expect(text).toContain('Esc')
    expect(text).not.toMatch(/[①②③]/)
  })
})
