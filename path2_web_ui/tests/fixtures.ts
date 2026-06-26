import type { SerializedPattern, Analysis, ScanResultFile, Diagnostics } from '../src/types'

export const PATTERN: SerializedPattern = {
  pattern_id: 'bottom_breakout_burst',
  display_name: '底部反转突破爆发',
  topology: {
    nodes: [
      { node_id: 'down', class_id: 'trend', label: '下跌段', source_tag: 'trend0',
        where_rules: [{ clause_id: 'drawdown', op: '>=', threshold: 0.30 }] },
      { node_id: 'side', class_id: 'trend', label: '横盘段', source_tag: 'trend1', where_rules: [] },
      { node_id: 'bo', class_id: 'bo', label: '突破点串', source_tag: 'bo',
        render_grid: 'price',
        where_rules: [{ clause_id: 'first_drought', op: '>=', threshold: 60 }] },
      { node_id: 'tb', class_id: 'tb', label: '回踩确认', source_tag: 'tb', where_rules: [] },
    ],
    edges: [
      { src: 'down', dst: 'bo', kind: 'TemporalEdge', rule: 'before · gap∈[1,120]' },
      { src: 'side', dst: 'bo', kind: 'ContainmentEdge', rule: 'contains' },
      { src: 'bo', dst: 'tb', kind: 'TemporalEdge', rule: 'gap=1' },
    ],
  },
  event_styles: { trend: '#f59e0b', bo: '#2563eb', tb: '#16a34a' },
}

export const ANALYSIS: Analysis = {
  events: [
    { class_id: 'trend', event_id: 'down1', source_tag: 'trend0', start_idx: 1, end_idx: 6, regime: 'down', drawdown: 0.42 },
    { class_id: 'trend', event_id: 'side1', source_tag: 'trend1', start_idx: 4, end_idx: 12, regime: 'sideways' },
    { class_id: 'bo', event_id: 'bo9', source_tag: 'bo', start_idx: 9, end_idx: 9, drought: 88, vol_ratio: 3.2,
      referenced_points: [[5, 12.5, 'pk0'], [7, 13.0, 'pk1']] },
    { class_id: 'bo', event_id: 'bo11', source_tag: 'bo', start_idx: 11, end_idx: 11, drought: 2, vol_ratio: 2.1 },
    { class_id: 'tb', event_id: 'tb16', source_tag: 'tb', start_idx: 16, end_idx: 16 },
    { class_id: 'bo', event_id: 'boX', source_tag: 'bo', start_idx: 20, end_idx: 20 }, // 未匹配
  ],
  matches: [
    { event_id: 'm1', start_idx: 1, end_idx: 16,
      role_index: { down: 'down1', side: 'side1', bo: 'bo9', tb: 'tb16' },
      children: ['down1', 'side1', 'bo9', 'bo11', 'tb16'],
      predicate_trace: {
        where_results: { down: { drawdown: { satisfied: true, measured: 0.42, op: '>=', threshold: 0.30 } } },
        edge_results: { 'down→bo': { satisfied: true, measured: 8, src: 'down1', dst: 'bo9' } },
      } },
  ],
}

export const SCAN_FILE: ScanResultFile = {
  pattern_id: 'bottom_breakout_burst',
  pattern_spec: PATTERN,
  scan: { scan_ts: '20260603T120000', start_date: '2025-01-01', end_date: '2025-12-31',
          workers: 8, scanned: 100, hits: 1, errors: 0, dataset_dir: '/x', params: 'default' },
  results: [
    { symbol: 'AAPL', summary: { trend: 2, bo: 3, tb: 1, matches: 1 }, analysis: ANALYSIS },
  ],
}

export const DIAG: Diagnostics = {
  symbol: 'AAPL', pattern_id: 'bottom_breakout_burst',
  roles: {
    down: { attr: [{ event_id: 'down1', start_idx: 1, end_idx: 6,
                     clauses: { drawdown: { satisfied: true, measured: 0.42, op: '>=', threshold: 0.30 } } }], rel: [] },
    bo: { attr: [], rel: [{ src: 'down', kind: 'TemporalEdge', total_src: 3, ok_count: 1, ok_src_ids: ['down1'] }] },
  },
  note: '单 role 局部诊断;通过不代表能凑成完整匹配',
}
