import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import SidebarPatternPanel from '../../src/components/SidebarPatternPanel.vue'
import { useViewStore } from '../../src/stores/view'

const emptyAnalysis = { events: [], matches: [] }
const file = {
  pattern_ids: ['bo_only', 'bbb'],
  per_pattern: {
    bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} }, end_node: 'bo' },
    bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} }, end_node: 'tb' },
  },
  scan: { scan_ts: '20260627T120000', start_date: '2024-01-01', end_date: '2024-06-30',
          workers: 1, scanned: 1, hits: 1, errors: 0, dataset_dir: '/d', params: 'd',
          win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20 },
  results: [{ symbol: 'AAA', per_pattern: {
    bo_only: { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.1 },
    bbb:     { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.2 },
  }}],
}

describe('SidebarPatternPanel — file pattern list + visibility toggle', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('renders one checkbox per pattern from scanFile.pattern_ids', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarPatternPanel)
    const checks = w.findAll('input[type="checkbox"][data-pid]')
    const pids = checks.map(c => c.attributes('data-pid'))
    expect(pids.sort()).toEqual(['bbb', 'bo_only'])
  })

  it('all checkboxes checked initially (visiblePatterns = all)', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarPatternPanel)
    const checks = w.findAll('input[type="checkbox"][data-pid]')
    for (const c of checks) expect((c.element as HTMLInputElement).checked).toBe(true)
  })

  it('click checkbox toggles visiblePatterns membership', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarPatternPanel)
    const bo = w.find('input[data-pid="bo_only"]')
    await bo.setValue(false)
    expect(v.visiblePatterns.has('bo_only')).toBe(false)
    expect(v.visiblePatterns.has('bbb')).toBe(true)
  })

  it('shows hint when no scanFile', () => {
    const w = mount(SidebarPatternPanel)
    expect(w.text()).toContain('未加载扫描结果')
  })
})

describe('SidebarPatternPanel — v2 无三按钮', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('does NOT render 全选 / 清空 / 反选 buttons', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarPatternPanel)
    const btnTexts = w.findAll('button').map(b => b.text())
    expect(btnTexts).not.toContain('全选')
    expect(btnTexts).not.toContain('清空')
    expect(btnTexts).not.toContain('反选')
  })
})
