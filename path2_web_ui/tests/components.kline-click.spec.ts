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

describe('KlineChart click handler (Task 6)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('marker click with ms.length === 0 → selectEvent (M fallback)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [{ event_id: 'm1', children: ['e_other'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null }]
    handleChartClick({ seriesName: 'points', data: { event_id: 'e_solo' } }, matches, view)
    expect(view.selectedEventId).toBe('e_solo')
    expect(view.candidateMatchIds.size).toBe(0)
  })

  it('marker click with ms.length === 1 → setHighlighted + selectMatch + selectEvent', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [{ event_id: 'm1', children: ['eA', 'eB', 'eC'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null }]
    handleChartClick({ seriesName: 'intervals', data: { event_id: 'eA' } }, matches, view)
    expect(view.selectedMatchId).toBe('m1')
    expect(view.highlightedEventIds.size).toBe(3)
    expect(view.selectedEventId).toBe('eA')
    expect(view.candidateMatchIds.size).toBe(0)
  })

  it('marker click with ms.length > 1 → candidate + pendingDisambig (no selected)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [
      { event_id: 'm1', children: ['eShared', 'eA'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null },
      { event_id: 'm3', children: ['eShared', 'eB'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null },
      { event_id: 'm5', children: ['eShared', 'eC'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null },
    ]
    handleChartClick({ seriesName: 'points', data: { event_id: 'eShared' } }, matches, view)
    expect(view.candidateMatchIds.size).toBe(3)
    expect(view.candidateMatchIds.has('m1')).toBe(true)
    expect(view.candidateMatchIds.has('m3')).toBe(true)
    expect(view.candidateMatchIds.has('m5')).toBe(true)
    expect(view.pendingDisambigEventId).toBe('eShared')
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBeNull()
    expect(view.highlightedEventIds.size).toBe(0)
  })

  it('idempotent: click same multi-match event twice keeps candidate', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [
      { event_id: 'm1', children: ['eShared'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null },
      { event_id: 'm2', children: ['eShared'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null },
    ]
    handleChartClick({ seriesName: 'points', data: { event_id: 'eShared' } }, matches, view)
    const sizeBefore = view.candidateMatchIds.size
    handleChartClick({ seriesName: 'points', data: { event_id: 'eShared' } }, matches, view)
    expect(view.candidateMatchIds.size).toBe(sizeBefore)
    expect(view.pendingDisambigEventId).toBe('eShared')
  })

  it('bracket click on candidate match → finalize: setHighlighted + selectMatch + clearCandidates', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [
      { event_id: 'm1', children: ['eA', 'eB'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null },
      { event_id: 'm3', children: ['eA', 'eC'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null },
    ]
    // 先进 candidate
    handleChartClick({ seriesName: 'points', data: { event_id: 'eA' } }, matches, view)
    expect(view.candidateMatchIds.size).toBe(2)
    // 再 click 候选中的 bracket m3
    handleChartClick({ seriesName: 'brackets', data: { match_id: 'm3' } }, matches, view)
    expect(view.selectedMatchId).toBe('m3')
    expect(view.highlightedEventIds.size).toBe(2)
    expect(view.highlightedEventIds.has('eA')).toBe(true)
    expect(view.highlightedEventIds.has('eC')).toBe(true)
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigEventId).toBeNull()
  })

  // 同一时刻只允许一个 marker 处于「当前被选中」:bracket 琥珀填充 与 event 琥珀边缘 不共存。
  // 场景:先点单归属 event marker(ms.length===1 分支 selectedEventId='eA') → 再点另一 bracket m2 →
  // 期望 selectedEventId 被清,否则原 marker 的 focus 琥珀边留守,与新 bracket 的琥珀填充并存。
  it('bracket click 清 selectedEventId(防前次 marker focus 琥珀边遗留)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [
      { event_id: 'm1', children: ['eA', 'eB'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null },
      { event_id: 'm2', children: ['eC', 'eD'], start_idx: 0, end_idx: 1, role_index: {}, predicate_trace: null },
    ]
    // 步骤 1:点 eA(单归属 m1),此时 selectedEventId='eA' + selectedMatchId='m1'
    handleChartClick({ seriesName: 'points', data: { event_id: 'eA' } }, matches, view)
    expect(view.selectedEventId).toBe('eA')
    expect(view.selectedMatchId).toBe('m1')
    // 步骤 2:切换点 bracket m2,期望焦点整体切换 —— selectedMatchId → 'm2' 且 selectedEventId → null
    handleChartClick({ seriesName: 'brackets', data: { match_id: 'm2' } }, matches, view)
    expect(view.selectedMatchId).toBe('m2')
    expect(view.selectedEventId).toBeNull()
  })
})
