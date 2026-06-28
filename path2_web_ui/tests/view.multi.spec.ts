import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
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
        bo_only: { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.1 },
        bbb:     { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.2 },
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
    expect(v.effectivePattern?.pattern_id).toBe('bo_only')
    // 切到 bbb → preview pattern_id 不匹配 → 退回扫描结果
    v.setActivePattern('bbb')
    expect(v.effectivePattern?.pattern_id).toBe('bbb')
  })
})
