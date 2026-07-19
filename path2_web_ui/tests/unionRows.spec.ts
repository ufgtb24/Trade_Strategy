/**
 * unionRows / sortedRows 派生测试。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore, SYMBOL_SORT_KEY } from '../src/stores/view'
import type { MultiScanResultFile } from '../src/types'

const emptyAnalysis = { events: [], matches: [] }

function makeFile(): MultiScanResultFile {
  return {
    pattern_ids: ['bo_only', 'bbb'],
    per_pattern: {
      bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {}, debug_enabled_classes: [] }, end_node: 'bo' },
      bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {}, debug_enabled_classes: [] }, end_node: 'tb' },
    },
    scan: {
      scan_ts: '20260627T120000', start_date: '2024-01-01', end_date: '2024-06-30',
      workers: 1, scanned: 3, hits: 3, errors: 0, dataset_dir: '/d', params: 'default',
      win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20,
    },
    results: [
      { symbol: 'AAA', per_pattern: {
        bo_only: { summary: { matches: 2 }, analysis: emptyAnalysis, max_forward_return: 0.34 },
        bbb:     { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.10 },
      }},
      { symbol: 'BBB', per_pattern: {
        bo_only: { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.50 },
        bbb:     { summary: { matches: 0 }, analysis: emptyAnalysis, max_forward_return: null },
      }},
      { symbol: 'CCC', per_pattern: {
        bo_only: { summary: { matches: 0 }, analysis: emptyAnalysis, max_forward_return: null },
        bbb:     { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.20 },
      }},
    ],
  }
}

describe('unionRows / sortedRows', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('unionRows shape: cells per pattern with num/fr and matched bool', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.unionRows.length).toBe(3)
    const a = v.unionRows.find(r => r.symbol === 'AAA')!
    expect(a.cells.map(c => c.pid)).toEqual(['bo_only', 'bbb'])
    expect(a.cells[0].fr).toBeCloseTo(0.34)
    expect(a.cells[1].matched).toBe(true)
    const b = v.unionRows.find(r => r.symbol === 'BBB')!
    expect(b.cells[1].fr).toBeNull()
    expect(b.cells[1].matched).toBe(false)
  })

  it('cell.num reads summary.matches; cell.fr reads max_forward_return', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    const bbb = v.unionRows.find(r => r.symbol === 'BBB')!
    const bbbCell = bbb.cells.find(c => c.pid === 'bbb')!
    expect(bbbCell.num).toBe(0)            // summary.matches = 0
    expect(bbbCell.fr).toBe(null)          // max_forward_return = null
    expect(bbbCell.matched).toBe(false)
    const aaa = v.unionRows.find(r => r.symbol === 'AAA')!
    const aaaBo = aaa.cells.find(c => c.pid === 'bo_only')!
    expect(aaaBo.num).toBe(2)
    expect(aaaBo.fr).toBe(0.34)
    expect(aaaBo.matched).toBe(true)
  })

  it('default sortByPid is null → sortedRows preserves worker order', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.sortByPid).toBeNull()
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['AAA', 'BBB', 'CCC'])
  })

  it('sort by bo_only_fr desc puts highest fr first; null sinks last', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only_fr')
    expect(v.sortByPid).toBe('bo_only_fr')
    expect(v.sortDesc).toBe(true)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['BBB', 'AAA', 'CCC'])
  })

  it('clicking same column twice flips to asc; null still sinks last', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only_fr')
    v.setSort('bo_only_fr')
    expect(v.sortDesc).toBe(false)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['AAA', 'BBB', 'CCC'])
  })

  it('switching to another column resets to desc on that column', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only_fr')
    v.setSort('bo_only_fr')   // asc
    v.setSort('bbb_fr')
    expect(v.sortByPid).toBe('bbb_fr')
    expect(v.sortDesc).toBe(true)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['CCC', 'AAA', 'BBB'])
  })

  it('sort by symbol desc puts Z first; second click flips asc', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort(SYMBOL_SORT_KEY)
    expect(v.sortByPid).toBe(SYMBOL_SORT_KEY)
    expect(v.sortDesc).toBe(true)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['CCC', 'BBB', 'AAA'])
    v.setSort(SYMBOL_SORT_KEY)
    expect(v.sortDesc).toBe(false)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['AAA', 'BBB', 'CCC'])
  })

  it('switching between symbol and pid resets direction to desc on the new key', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort(SYMBOL_SORT_KEY)
    v.setSort(SYMBOL_SORT_KEY)   // asc
    v.setSort('bo_only_fr')
    expect(v.sortByPid).toBe('bo_only_fr')
    expect(v.sortDesc).toBe(true)
    v.setSort(SYMBOL_SORT_KEY)
    expect(v.sortByPid).toBe(SYMBOL_SORT_KEY)
    expect(v.sortDesc).toBe(true)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['CCC', 'BBB', 'AAA'])
  })

  it('union row condition: at least one pattern has matches > 0', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    // CCC bbb matched=1, BBB bo_only matched=1, AAA both >0 → all 3 in union
    expect(v.unionRows.map(r => r.symbol).sort()).toEqual(['AAA', 'BBB', 'CCC'])
  })

  it('sortedRows sorts by ${pid}_num when set', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only_num')                // AAA=2, BBB=1 → desc first: AAA, BBB
    const symbols = v.sortedRows.map(r => r.symbol)
    expect(symbols[0]).toBe('AAA')
  })

  it('sortedRows sorts by ${pid}_fr, null sinks', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    // AAA.bbb.fr=0.10, BBB.bbb.fr=null, CCC.bbb.fr=0.20 → desc, null sinks last
    v.setSort('bbb_fr')
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['CCC', 'AAA', 'BBB'])
  })

  it('sortedRows uses effectiveSortKey — hidden column → symbol order', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bbb_fr')
    v.togglePattern('bbb')                  // hide bbb → fallback __symbol__
    const symbols = v.sortedRows.map(r => r.symbol)
    // 按 symbol 字典序 desc(sortedRows 默认 desc): CCC > BBB > AAA
    expect(symbols).toEqual(['CCC', 'BBB', 'AAA'])
  })
})
