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
      bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'bo' },
      bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'tb' },
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

  it('unionRows shape: cells per pattern with max_ret and matched bool', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.unionRows.length).toBe(3)
    const a = v.unionRows.find(r => r.symbol === 'AAA')!
    expect(a.cells.map(c => c.pid)).toEqual(['bo_only', 'bbb'])
    expect(a.cells[0].max_ret).toBeCloseTo(0.34)
    expect(a.cells[1].matched).toBe(true)
    const b = v.unionRows.find(r => r.symbol === 'BBB')!
    expect(b.cells[1].max_ret).toBeNull()
    expect(b.cells[1].matched).toBe(false)
  })

  it('default sortByPid is null → sortedRows preserves worker order', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.sortByPid).toBeNull()
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['AAA', 'BBB', 'CCC'])
  })

  it('sort by bo_only desc puts highest max_ret first; null sinks last', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only')
    expect(v.sortByPid).toBe('bo_only')
    expect(v.sortDesc).toBe(true)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['BBB', 'AAA', 'CCC'])
  })

  it('clicking same column twice flips to asc; null still sinks last', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only')
    v.setSort('bo_only')
    expect(v.sortDesc).toBe(false)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['AAA', 'BBB', 'CCC'])
  })

  it('switching to another column resets to desc on that column', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only')
    v.setSort('bo_only')   // asc
    v.setSort('bbb')
    expect(v.sortByPid).toBe('bbb')
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
    v.setSort('bo_only')
    expect(v.sortByPid).toBe('bo_only')
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
})
