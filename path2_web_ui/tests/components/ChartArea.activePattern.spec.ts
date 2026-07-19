import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import ChartArea from '../../src/components/ChartArea.vue'
import { useViewStore } from '../../src/stores/view'

// jsdom does not implement ResizeObserver; stub it so KlineChart mounts without error
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const file = {
  pattern_ids: ['bo_only', 'bbb'],
  per_pattern: {
    bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} }, end_node: 'bo' },
    bbb:     { pattern_spec: { pattern_id: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} }, end_node: 'tb' },
  },
  scan: { scan_ts: '20260627T120000', start_date: '2024-01-01', end_date: '2024-06-30',
          workers: 1, scanned: 1, hits: 1, errors: 0, dataset_dir: '/d', params: 'd',
          win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20 },
  results: [],
}

describe('ChartArea — active pattern dropdown', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders select with one option per pattern_id', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(ChartArea)
    const sel = w.find('select[data-role="active-pattern"]')
    expect(sel.exists()).toBe(true)
    const opts = sel.findAll('option')
    expect(opts.map(o => o.attributes('value'))).toEqual(['bo_only', 'bbb'])
  })

  it('change select calls setActivePattern', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(ChartArea)
    const sel = w.find('select[data-role="active-pattern"]')
    await sel.setValue('bbb')
    expect(v.activePatternId).toBe('bbb')
  })
})
