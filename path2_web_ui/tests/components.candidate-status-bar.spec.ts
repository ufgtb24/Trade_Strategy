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

  it('同一天的几次 hit:选中其中一次时写 hit k/n;当家行是 hits 行才写 ←/→;只有一次的那天不出', async () => {
    const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}) =>
      ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })
    const T13 = ev('today', 13, 13), T14 = ev('today', 14, 14)
    const P0 = ev('plateau', 0, 13, 0, { today: [T13.instance_id] })
    const P1 = ev('plateau', 0, 13, 1, { today: [T13.instance_id] })
    const P2 = ev('plateau', 0, 14, 0, { today: [T14.instance_id] })
    const hit = (id: string, p: any) => ({ hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx,
      node_index: { plateau: p.instance_id }, children: [p.instance_id, ...Object.values(p.child_refs).flat()] })
    const hits = [hit('h0', P0), hit('h1', P1), hit('h2', P2)]
    const view = useViewStore()
    view.loadScanFile({
      pattern_ids: ['p1'],
      per_pattern: { p1: { end_node: 'plateau.today', pattern_spec: { pattern_id: 'p1', event_styles: {}, topology: { edges: [], nodes: [
        { node_id: 'plateau', render_grid: 'time', where_rules: [] },
        { node_id: 'today', render_grid: 'time', where_rules: [], solve: false, is_point: true },
      ] } } } },
      results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: { events: [T13, T14, P0, P1, P2], hits }, summary: { hits: 3 } } } }],
      scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 },
    } as any)
    const w = mount(CandidateStatusBar, { props: { hits: hits as any } })
    expect(w.find('[data-testid="same-day-hits"]').exists()).toBe(false)
    view.focusHit('h0')
    await w.vm.$nextTick()
    expect(w.find('[data-testid="same-day-hits"]').text()).toMatch(/hit 1\/2\s*←\/→/)
    view.stepFocus(1)
    await w.vm.$nextTick()
    expect(w.find('[data-testid="same-day-hits"]').text()).toContain('hit 2/2')
    view.focusHit('h2')
    await w.vm.$nextTick()
    expect(w.find('[data-testid="same-day-hits"]').exists()).toBe(false)
  })
})
