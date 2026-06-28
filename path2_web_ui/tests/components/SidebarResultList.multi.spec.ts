import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import SidebarResultList from '../../src/components/SidebarResultList.vue'
import { useViewStore } from '../../src/stores/view'

const emptyAnalysis = { events: [], matches: [] }
const file = {
  pattern_ids: ['bo_only', 'bbb'],
  per_pattern: {
    bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'bo' },
    bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'tb' },
  },
  scan: { scan_ts: '20260627T120000', start_date: '2024-01-01', end_date: '2024-06-30',
          workers: 1, scanned: 2, hits: 2, errors: 0, dataset_dir: '/d', params: 'd',
          win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20 },
  results: [
    { symbol: 'AAA', per_pattern: {
      bo_only: { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.34 },
      bbb:     { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.10 },
    }},
    { symbol: 'BBB', per_pattern: {
      bo_only: { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.50 },
      bbb:     { summary: { matches: 0 }, analysis: emptyAnalysis, max_forward_return: null },
    }},
  ],
}

describe('SidebarResultList — multi-pattern', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders N column headers from pattern_ids', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const ths = w.findAll('th[data-col-pid]')
    const pids = ths.map(th => th.attributes('data-col-pid'))
    expect(pids).toEqual(['bo_only', 'bbb'])
  })

  it('renders max_forward_return per cell, null shows —', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const cells = w.findAll('td[data-cell-pid]')
    // BBB.bbb 的单元格是 null
    const bbb_bbb = cells.find(c =>
      c.element.closest('tr')?.querySelector('.sym')?.textContent === 'BBB'
      && c.attributes('data-cell-pid') === 'bbb')!
    expect(bbb_bbb.text()).toContain('—')
  })

  it('clicking column header sets sortByPid desc; second click flips asc', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const th = w.find('th[data-col-pid="bo_only"]')
    await th.trigger('click')
    expect(v.sortByPid).toBe('bo_only')
    expect(v.sortDesc).toBe(true)
    await th.trigger('click')
    expect(v.sortDesc).toBe(false)
  })

  it('cell click selects symbol but does NOT change activePatternId', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    v.setActivePattern('bbb')
    const before = v.activePatternId
    const w = mount(SidebarResultList)
    const td = w.find('td[data-cell-pid="bo_only"]')
    await td.trigger('click')
    expect(v.activePatternId).toBe(before)        // 不变
    // 切了股
    expect(v.symbol).toBeTruthy()
  })

  it('symbol cell click selects symbol', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const sym = w.find('td.sym')
    await sym.trigger('click')
    expect(v.symbol).toBeTruthy()
  })

  it('matched cells get .matched class', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    // AAA bbb matched=1 → .matched
    const c = w.findAll('td[data-cell-pid="bbb"]')
      .find(td => td.element.closest('tr')?.querySelector('.sym')?.textContent === 'AAA')!
    expect(c.classes()).toContain('matched')
  })
})
