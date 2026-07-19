import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile } from '../src/types'

function makeFile(symbols: string[]): MultiScanResultFile {
  return {
    pattern_ids: ['bo_only', 'bbb'],
    per_pattern: {
      bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} } as any, end_node: 'bo' },
      bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} } as any, end_node: 'tb' },
    },
    scan: {
      scan_ts: '20260714T120000', start_date: '2024-01-01', end_date: '2024-06-30',
      workers: 1, scanned: symbols.length, hits: symbols.length, errors: 0,
      dataset_dir: '/d', params: 'default',
      win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20,
    },
    results: symbols.map(s => ({
      symbol: s,
      per_pattern: {
        bo_only: { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.1 },
        bbb:     { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.1 },
      },
    })),
  }
}

describe('view store · symbolQuery', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('empty query returns all rows (equivalence with legacy behavior)', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL', 'BAA', 'MSFT']))
    expect(v.symbolQuery).toBe('')
    expect(v.filteredSortedRows.map(r => r.symbol).sort()).toEqual(['AA', 'AAPL', 'BAA', 'MSFT'])
  })

  it('prefix match is case-insensitive', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL', 'BAA', 'MSFT']))
    v.setSymbolQuery('aa')
    expect(v.filteredSortedRows.map(r => r.symbol).sort()).toEqual(['AA', 'AAPL'])
  })

  it('prefix (not substring): "aa" does not match "BAA"', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL', 'BAA']))
    v.setSymbolQuery('aa')
    expect(v.filteredSortedRows.some(r => r.symbol === 'BAA')).toBe(false)
  })

  it('query is trimmed', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL']))
    v.setSymbolQuery('  aa  ')
    expect(v.filteredSortedRows.map(r => r.symbol).sort()).toEqual(['AA', 'AAPL'])
  })

  it('clearSymbolQuery restores full list', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL', 'BAA']))
    v.setSymbolQuery('aa')
    v.clearSymbolQuery()
    expect(v.symbolQuery).toBe('')
    expect(v.filteredSortedRows.length).toBe(3)
  })

  it('AND with visiblePatterns filter: pattern hidden AND query miss → hidden', () => {
    const v = useViewStore()
    // 构造:AAA 在 bo_only 命中 / bbb 不命中;BBB 在 bbb 命中 / bo_only 不命中
    const f: MultiScanResultFile = {
      pattern_ids: ['bo_only', 'bbb'],
      per_pattern: {
        bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} } as any, end_node: 'bo' },
        bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} } as any, end_node: 'tb' },
      },
      scan: {
        scan_ts: '20260714T120000', start_date: '2024-01-01', end_date: '2024-06-30',
        workers: 1, scanned: 2, hits: 2, errors: 0, dataset_dir: '/d', params: 'default',
        win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20,
      },
      results: [
        { symbol: 'AAA', per_pattern: {
          bo_only: { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.1 },
          bbb:     { summary: { matches: 0 }, analysis: { events: [], matches: [] }, max_forward_return: null },
        }},
        { symbol: 'BBB', per_pattern: {
          bo_only: { summary: { matches: 0 }, analysis: { events: [], matches: [] }, max_forward_return: null },
          bbb:     { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.2 },
        }},
      ],
    }
    v.loadScanFile(f)
    v.setPatternsAllOff()
    v.togglePattern('bo_only')  // 只 visible bo_only
    // 无 query:visiblePatterns filter 保留 AAA(bo_only 命中),丢 BBB
    expect(v.filteredSortedRows.map(r => r.symbol)).toEqual(['AAA'])
    v.setSymbolQuery('bb')  // AND:AAA 前缀不匹配 → 全丢
    expect(v.filteredSortedRows).toEqual([])
  })

  it('loadScanFile resets symbolQuery', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA']))
    v.setSymbolQuery('xx')
    expect(v.symbolQuery).toBe('xx')
    v.loadScanFile(makeFile(['CC', 'CCC']))
    expect(v.symbolQuery).toBe('')
  })

  it('clearScanFile resets symbolQuery', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA']))
    v.setSymbolQuery('xx')
    v.clearScanFile()
    expect(v.symbolQuery).toBe('')
  })

  it('setActivePattern resets symbolQuery', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL']))
    v.setSymbolQuery('aa')
    v.setActivePattern('bbb')
    expect(v.symbolQuery).toBe('')
  })
})
