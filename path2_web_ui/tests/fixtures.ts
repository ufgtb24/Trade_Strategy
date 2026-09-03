import type { SerializedPattern, Analysis, MultiScanResultFile, Diagnostics } from '../src/types'

export const PATTERN: SerializedPattern = {
  pattern_id: 'bottom_burst',
  topology: {
    nodes: [
      { node_id: 'down',
        where_rules: [{ clause_id: 'drawdown', op: '>=', threshold: 0.30 }] },
      { node_id: 'side', where_rules: [] },
      { node_id: 'bo', render_grid: 'price',
        where_rules: [{ clause_id: 'first_drought', op: '>=', threshold: 60 }] },
      { node_id: 'tb', where_rules: [] },
    ],
    edges: [
      { src: 'down', dst: 'bo', kind: 'TemporalEdge', rule: 'before · gap∈[1,120]' },
      { src: 'side', dst: 'bo', kind: 'ContainmentEdge', rule: 'contains' },
      { src: 'bo', dst: 'tb', kind: 'TemporalEdge', rule: 'gap=1' },
    ],
  },
  // 样式键 = node_id(Task 5 静态层改按 node_id setdefault)
  event_styles: { down: '#f59e0b', side: '#f59e0b', bo: '#2563eb', tb: '#16a34a' },
  debug_enabled_nodes: ['tb'],        // debug 断点启用的 node_id 列表
}

/** 含父子关系的拓扑(PATTERN + burst/tb_seg;bo 被 burst members 槽引用、tb_seg 由 tb 物化)。 */
export const PATTERN_WITH_SUB: SerializedPattern = {
  ...PATTERN,
  topology: {
    ...PATTERN.topology,
    nodes: [
      ...PATTERN.topology.nodes,
      { node_id: 'burst', where_rules: [] },
      { node_id: 'tb_seg', where_rules: [],
        produced_by: 'tb', child_slot: 'segments',
        parent_refs: [['tb', 'segments']] as [string, string][] },
    ].map((n) => n.node_id === 'bo'
      ? { ...n, parent_refs: [['burst', 'members']] as [string, string][] } : n),
  },
}

export const ANALYSIS: Analysis = {
  events: [
    { instance_id: 'down_1_6#0', node_id: 'down', instance_idx: 0, start_idx: 1, end_idx: 6,
      regime: 'down', drawdown: 0.42, child_refs: {} },
    { instance_id: 'side_4_12#0', node_id: 'side', instance_idx: 0, start_idx: 4, end_idx: 12,
      regime: 'sideways', child_refs: {} },
    { instance_id: 'bo_9#0', node_id: 'bo', instance_idx: 0, start_idx: 9, end_idx: 9,
      drought: 88, vol_ratio: 3.2, child_refs: {} },
    { instance_id: 'bo_11#0', node_id: 'bo', instance_idx: 0, start_idx: 11, end_idx: 11,
      drought: 2, vol_ratio: 2.1, child_refs: {} },
    { instance_id: 'tb_16#0', node_id: 'tb', instance_idx: 0, start_idx: 16, end_idx: 16,
      child_refs: {} },
    { instance_id: 'bo_20#0', node_id: 'bo', instance_idx: 0, start_idx: 20, end_idx: 20,
      child_refs: {} }, // 未匹配
  ],
  matches: [
    { match_id: 'm1',
      start_idx: 1, end_idx: 16,
      node_index: { down: 'down_1_6#0', side: 'side_4_12#0', bo: 'bo_9#0', tb: 'tb_16#0' },
      children: ['down_1_6#0', 'side_4_12#0', 'bo_9#0', 'bo_11#0', 'tb_16#0'],
      predicate_trace: {
        where_results: { down: { drawdown: { satisfied: true, measured: 0.42, op: '>=', threshold: 0.30 } } },
        edge_results: { 'down→bo': { satisfied: true, measured: { kind: 'gap', value: 8, label: 'gap' }, src: 'down_1_6#0', dst: 'bo_9#0' } },
      } },
  ],
}

export const SCAN_FILE: MultiScanResultFile = {
  pattern_ids: ['bottom_burst'],
  per_pattern: {
    bottom_burst: { pattern_spec: PATTERN, end_node: 'tb' },
  },
  scan: {
    scan_ts: '20260603T120000', start_date: '2025-01-01', end_date: '2025-12-31',
    workers: 8, scanned: 100, hits: 1, errors: 0, dataset_dir: '/x', params: 'default',
    win_start: '2025-01-01', win_end: '2025-12-31', label_horizon: 20, first_passage_k: 2,
  },
  results: [
    { symbol: 'AAPL', per_pattern: {
      bottom_burst: {
        summary: { down: 1, side: 1, bo: 3, tb: 1, matches: 1 },
        analysis: ANALYSIS,
        max_forward_return: null,
      },
    }},
  ],
}

export const DIAG: Diagnostics = {
  symbol: 'AAPL', pattern_id: 'bottom_burst',
  nodes: {
    down: { attr: [{ instance_id: 'down_1_6#0', node_id: 'down', start_idx: 1, end_idx: 6,
                     clauses: { drawdown: { satisfied: true, measured: 0.42, op: '>=', threshold: 0.30 } } }], rel: [] },
    bo: { attr: [], rel: [{ src: 'down', kind: 'TemporalEdge', total_src: 3, ok_count: 1, ok_src_ids: ['down_1_6#0'] }] },
  },
  note: '单 node 局部诊断;通过不代表能凑成完整匹配',
}
