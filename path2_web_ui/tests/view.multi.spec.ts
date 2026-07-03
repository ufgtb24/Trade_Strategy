import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore, SYMBOL_SORT_KEY as _SORT_KEY } from '../src/stores/view'
import { useConfigStore } from '../src/stores/config'
import type { MultiScanResultFile } from '../src/types'

function makeFile(): MultiScanResultFile {
  return {
    pattern_ids: ['bo_only', 'bbb'],
    per_pattern: {
      bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'bo' },
      bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'tb' },
    },
    scan: {
      scan_ts: '20260627T120000', start_date: '2024-01-01', end_date: '2024-06-30',
      workers: 1, scanned: 1, hits: 1, errors: 0, dataset_dir: '/d', params: 'default',
      win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20,
    },
    results: [
      { symbol: 'AAA', per_pattern: {
        bo_only: { summary: { matches: 2 }, analysis: { events: [], matches: [] }, max_forward_return: 0.34 },
        bbb:     { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.10 },
      }},
      { symbol: 'BBB', per_pattern: {
        bo_only: { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.50 },
        bbb:     { summary: { matches: 0 }, analysis: { events: [], matches: [] }, max_forward_return: null },
      }},
      { symbol: 'CCC', per_pattern: {
        bo_only: { summary: { matches: 0 }, analysis: { events: [], matches: [] }, max_forward_return: null },
        bbb:     { summary: { matches: 0 }, analysis: { events: [], matches: [] }, max_forward_return: null },
      }},
    ],
  }
}

describe('view store — multi pattern', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loadScanFile prefers config.last_selected_pattern when in pattern_ids', () => {
    const cfg = useConfigStore()
    cfg.config!.last_selected_pattern = 'bbb'
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.activePatternId).toBe('bbb')
  })

  it('loadScanFile falls back to pattern_ids[0] when last_selected not in pattern_ids', () => {
    const cfg = useConfigStore()
    cfg.config!.last_selected_pattern = 'not_present'
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.activePatternId).toBe('bo_only')
  })

  it('pattern computed reflects activePatternId', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setActivePattern('bo_only')
    expect(v.pattern?.pattern_id).toBe('bo_only')
    v.setActivePattern('bbb')
    expect(v.pattern?.pattern_id).toBe('bbb')
  })

  it('currentAnalysis reads per_pattern[activePatternId].analysis', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.selectSymbol('AAA')
    v.setActivePattern('bo_only')
    expect(v.currentAnalysis).not.toBeNull()
  })

  it('effective triple uses preview when symbol AND pattern_id match', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.selectSymbol('AAA')
    v.setActivePattern('bo_only')
    // Mock preview state
    ;(v as any).preview = {
      symbol: 'AAA',
      analysis: { events: [{}], matches: [] },
      pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} },
      scan: {},
    }
    ;(v as any).previewEnabled = true
    expect(v.effectiveAnalysis?.events.length).toBe(1)
    // 切到 bbb → preview pattern_id 不匹配 → 退回扫描结果
    v.setActivePattern('bbb')
    expect(v.effectivePattern?.pattern_id).toBe('bbb')
  })
})

describe('view store — visibility axes', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('loadScanFile initializes visiblePatterns = all pattern_ids', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect([...v.visiblePatterns].sort()).toEqual(['bbb', 'bo_only'])
  })

  it('clearScanFile empties visiblePatterns', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.clearScanFile()
    expect(v.visiblePatterns.size).toBe(0)
  })

  it('togglePattern flips membership', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.togglePattern('bbb')
    expect(v.visiblePatterns.has('bbb')).toBe(false)
    v.togglePattern('bbb')
    expect(v.visiblePatterns.has('bbb')).toBe(true)
  })

  it('setPatternsAllOn / AllOff / invert work', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setPatternsAllOff()
    expect(v.visiblePatterns.size).toBe(0)
    v.setPatternsAllOn()
    expect(v.visiblePatterns.size).toBe(2)
    v.togglePattern('bbb')  // now {bo_only}
    v.invertPatterns()
    expect([...v.visiblePatterns]).toEqual(['bbb'])
  })

  it('visibleFields default = {num, fr} (localStorage empty)', () => {
    const v = useViewStore()
    expect([...v.visibleFields].sort()).toEqual(['fr', 'num'])
  })

  it('visibleFields loads from localStorage', () => {
    localStorage.setItem('path2_web_ui.visibleFields', JSON.stringify(['num']))
    setActivePinia(createPinia())    // re-init store
    const v = useViewStore()
    expect([...v.visibleFields]).toEqual(['num'])
  })

  it('toggleField writes localStorage', () => {
    const v = useViewStore()
    v.toggleField('fr')
    const raw = localStorage.getItem('path2_web_ui.visibleFields')
    expect(JSON.parse(raw!)).toEqual(['num'])
  })

  it('isColumnVisible AND-composes both axes', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.isColumnVisible('bbb', 'num')).toBe(true)
    v.togglePattern('bbb')
    expect(v.isColumnVisible('bbb', 'num')).toBe(false)
    v.togglePattern('bbb')
    v.toggleField('num')
    expect(v.isColumnVisible('bbb', 'num')).toBe(false)
    expect(v.isColumnVisible('bbb', 'fr')).toBe(true)
  })

  it('effectiveSortKey falls back to SYMBOL_SORT_KEY when target column hidden', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bbb_num')
    expect(v.effectiveSortKey).toBe('bbb_num')
    v.togglePattern('bbb')                        // hide bbb
    expect(v.effectiveSortKey).toBe(_SORT_KEY)
    v.togglePattern('bbb')                        // restore
    expect(v.effectiveSortKey).toBe('bbb_num')    // 自动恢复(sortByPid 值保留)
  })

  it('effectiveSortKey passes through null and SYMBOL_SORT_KEY', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.effectiveSortKey).toBe(null)         // sortByPid = null after loadScanFile
    v.setSort(_SORT_KEY)
    expect(v.effectiveSortKey).toBe(_SORT_KEY)
  })
})

describe('view store — filteredSortedRows', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('keeps rows with at least one matched cell in visible patterns (all visible)', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    // v1 fixture (from tests/view.multi.spec.ts / unionRows.spec.ts) has 3 rows:
    // AAA: bo_only matched, bbb matched
    // BBB: bo_only matched, bbb unmatched
    // CCC: both unmatched
    // All visible → filter keeps AAA + BBB (both have at least one matched)
    const symbols = v.filteredSortedRows.map(r => r.symbol).sort()
    expect(symbols).toEqual(['AAA', 'BBB'])
  })

  it('hides rows whose only matched cell belongs to a hidden pattern', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.togglePattern('bo_only')  // hide bo_only; only bbb remains visible
    // AAA: bbb matched → keep. BBB: bbb unmatched → drop. CCC: both unmatched → drop.
    const symbols = v.filteredSortedRows.map(r => r.symbol)
    expect(symbols).toEqual(['AAA'])
  })

  it('returns empty array when visiblePatterns is empty', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setPatternsAllOff()
    expect(v.filteredSortedRows).toEqual([])
  })

  it('preserves sortedRows order after filtering (does not re-sort)', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only_fr')                       // desc: BBB(0.50) > AAA(0.34) > CCC(null sinks)
    const sortedOrder = v.sortedRows.map(r => r.symbol)  // ['BBB','AAA','CCC']
    const filteredOrder = v.filteredSortedRows.map(r => r.symbol)
    // filter keeps AAA + BBB (both have at least one matched cell), drops CCC (both unmatched)
    // Order must be subsequence of sortedOrder: ['BBB','AAA']
    expect(filteredOrder).toEqual(sortedOrder.filter(s => filteredOrder.includes(s)))
    expect(filteredOrder).toEqual(['BBB', 'AAA'])
  })

  it('returns empty array when scanFile is null', () => {
    const v = useViewStore()
    // no loadScanFile call → scanFile is null
    expect(v.filteredSortedRows).toEqual([])
  })
})
