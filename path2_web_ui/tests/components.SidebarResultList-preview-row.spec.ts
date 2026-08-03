// 探索态:选中股正下方出现 ↳探索 对照行(active pattern 现算值无 †、其余 pattern 空白非 —)
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import SidebarResultList from '../src/components/SidebarResultList.vue'
import { useViewStore } from '../src/stores/view'

function scanFile2(): any {
  return {
    pattern_ids: ['bbb', 'ccc'],
    per_pattern: {
      bbb: { pattern_spec: { pattern_id: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} },
             end_node: 'tb', params_snapshot: { bo: { total_window: 10 } }, stats: null },
      ccc: { pattern_spec: { pattern_id: 'ccc', topology: { nodes: [], edges: [] }, event_styles: {} },
             end_node: 'tb', params_snapshot: { bo: { total_window: 5 } }, stats: null },
    },
    scan: { scan_ts: '20260720T000000', start_date: '2025-01-01', end_date: '2025-06-01', label_horizon: 20 },
    // ACRS 在冻结扫描里 bbb 有命中 → 进 filteredSortedRows(否则不在列表、无宿主行)
    results: [{ symbol: 'ACRS', per_pattern: {
      bbb: { summary: { matches: 1 }, max_forward_return: 0.5, analysis: { events: [], matches: [] } },
    } }],
  }
}
function setupExplore(v: any) {
  v.loadScanFile(scanFile2())
  v.setActivePattern('bbb')
  v.selectSymbol('ACRS')
  ;(v as any).preview = {
    symbol: 'ACRS',
    analysis: { events: [], matches: [{ forward_return: 0.30 }, { forward_return: 0.10 }] },
    pattern_spec: { pattern_id: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} },
    scan: { label_horizon: 20 },
  }
  ;(v as any).workingCopy = { bbb: { enabled: true, baseline: {}, currentDict: {} } }
}

describe('SidebarResultList 探索态对照行', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as any)))
  })

  it('探索态+选中股+preview → 选中行下方出现 ↳探索 行:active 列现算值(无 †),其余列空白(非 —)', () => {
    const v = useViewStore()
    setupExplore(v)
    const w = mount(SidebarResultList)
    const prow = w.get('[data-testid="preview-list-row"]')
    expect(prow.text()).toContain('↳ 探索')
    // active pattern(bbb):num=2、fr=+30.0%(现算值,靠整行绿+↳探索 标示,不带 † 标记)
    expect(prow.get('[data-cell-pid="bbb"][data-cell-field="num"]').text()).toBe('2')
    const bbbFr = prow.get('[data-cell-pid="bbb"][data-cell-field="fr"]')
    expect(bbbFr.text()).toContain('+30.0%')
    expect(bbbFr.text()).not.toContain('†')
    // 其余 pattern(ccc):空白 —— 既非数字也非 —
    expect(prow.get('[data-cell-pid="ccc"][data-cell-field="num"]').text()).toBe('')
    expect(prow.get('[data-cell-pid="ccc"][data-cell-field="fr"]').text()).toBe('')
  })

  it('关探索 → 对照行消失', async () => {
    const v = useViewStore()
    setupExplore(v)
    const w = mount(SidebarResultList)
    expect(w.find('[data-testid="preview-list-row"]').exists()).toBe(true)
    v.setWorkingCopyEnabled('bbb', false)              // 回浏览态
    await w.vm.$nextTick()
    expect(w.find('[data-testid="preview-list-row"]').exists()).toBe(false)
  })
})
