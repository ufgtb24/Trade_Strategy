// spec §7 后端 JSON 契约的 TS 镜像。字段名与后端严格一致。

export interface WhereRule { clause_id: string; op: string | null; threshold: unknown }
export interface TopoNode {
  node_id: string; class_id: string
  source_tag: string
  render_grid?: 'price' | 'time'
  where_rules: WhereRule[]
}
export interface TopoEdge { src: string; dst: string; kind: string; rule: string; anchor_field?: string | null }
export interface Topology { nodes: TopoNode[]; edges: TopoEdge[] }
export interface SerializedPattern {
  pattern_id: string
  topology: Topology; event_styles: Record<string, string>
  debug_enabled_classes: string[]        // ★ v4 契约 C · 挂了 debug_break 的 class_id 列表(拓扑序 · 去重)
}

export interface EventDict {
  class_id: string; event_id: string; start_idx: number; end_idx: number
  source_tag: string
  child_refs: Record<string, string[]>
  referenced_points?: Array<[number, number, string]>
  [attr: string]: unknown
}

export interface ClauseWitness {
  satisfied: boolean; measured: unknown; op: string | null
  threshold: unknown
}
export interface MeasuredKindAware { kind: string; value: unknown; label: string }
export interface EdgeWitness { satisfied: boolean; measured: MeasuredKindAware; src: string; dst: string }
export interface PredicateTrace {
  where_results: Record<string, Record<string, ClauseWitness>>
  edge_results: Record<string, EdgeWitness>
}
export interface MatchDict {
  event_id: string; start_idx: number; end_idx: number
  node_index: Record<string, string>
  children: string[]
  predicate_trace: PredicateTrace | null
  forward_return?: number | null
}
export interface Analysis { events: EventDict[]; matches: MatchDict[] }

// ── 多 pattern schema ───────────────────────────────────────────────
export interface PerPatternResult {
  summary: Record<string, number>            // {class_id: count} ∪ {matches: n}
  analysis: Analysis
  max_forward_return: number | null
}
export interface PatternStats {
  count: number
  mean: number | null
  min: number | null
  q25: number | null
  median: number | null
  q75: number | null
  max: number | null
  win_rate: number | null
}
export interface PerPatternMeta {
  pattern_spec: SerializedPattern
  end_node: string
  stats?: PatternStats
}
export interface ScanMeta {
  scan_ts: string; start_date: string; end_date: string; workers: number
  scanned: number; hits: number; errors: number; dataset_dir: string; params: string
  win_start: string; win_end: string                  // 必有(非 optional)
  label_horizon: number                                // 必有(非 optional)
  partial?: boolean
}
export interface StockResult {
  symbol: string
  per_pattern: Record<string, PerPatternResult>        // key = pattern_id
}
export interface MultiScanResultFile {
  pattern_ids: string[]
  per_pattern: Record<string, PerPatternMeta>          // key = pattern_id
  scan: ScanMeta
  results: StockResult[]
}

export interface Bar { date: string; o: number; h: number; l: number; c: number; v: number; rv: number }
export interface Ohlc { symbol: string; bars: Bar[] }

export interface AttrRow {
  event_id: string; start_idx: number; end_idx: number
  clauses: Record<string, ClauseWitness>
}
export interface RelRow { src: string; kind: string; total_src: number; ok_count: number; ok_src_ids: string[] }
export interface NodeDiag { attr: AttrRow[]; rel: RelRow[] }
export interface Diagnostics {
  symbol: string; pattern_id: string; nodes: Record<string, NodeDiag>; note: string
}

// ─── Sprint 1 Task 8:scope-based /diagnose 路由(§3.1)── scope=nodes 载荷 ──────
export interface Caveat { code: string; message: string; affected_fields?: string[] }
export interface PairFailure {
  src_event_id: string; dst_event_id: string
  subcheck_stage: string
  measured: Record<string, unknown> | null
  threshold: unknown
  edge_kind: string
}
export interface NodesPayload {
  edge_id: string; total_pair: number; ok_pair: number
  miss_reasons: Record<string, number>
  example_failed_pairs: PairFailure[]
  per_pair?: PairFailure[] | null
}
export interface NodesScopeResponse { scope: 'nodes'; payload: NodesPayload; caveats: Caveat[] }

// ─── Sprint 2 Task 15/18:scope=time 载荷(入口 A · brush 时段查询) ───────────
export interface GateFailure {
  failure_event_window: [number, number]
  start_idx: number; gate_idx: number
  anchor_bar: number; class_id: string; gate_name: string
  measured: MeasuredKindAware
  threshold: unknown
  op: string | null
  threshold_param: string | null
  evaluation_lookback: [number, number] | null
  symbol: string
  code_location: string          // ← 手二·后端 __post_init__ 自动填, '' 表示未定位
}
export interface TimePayload {
  frame: [number, number]
  failed_attempts: GateFailure[]
}
export interface TimeScopeResponse { scope: 'time'; payload: TimePayload; caveats: Caveat[] }

// ─── Sprint 2 Task 17/18:scope=pair 载荷(入口 D · shift+click 跨图 pair 查询) ──
export interface SubCheck {
  channel: string; passed: boolean
  measured: MeasuredKindAware | null
  threshold: unknown
  reason: string | null
}
export interface PairPayload {
  src_event_id: string; dst_event_id: string
  applied_swap: boolean
  original_first_click: string; original_second_click: string
  valid: boolean; invalid_reason: string | null
  edge_id: string | null; edge_kind: string | null
  subchecks: SubCheck[] | null
  hint?: Record<string, unknown> | null
}
// payload 与 {stub:true} 联合:api.py 尚未 recompute+attach AnalysisResult(Task 17 遗留 systemic
// gap,见 task-17-report.md)时端点诚实降级为 stub dict,前端须能分辨(见 DetailSidebar pairPayloadValid)。
export interface PairScopeResponse { scope: 'pair'; payload: PairPayload | { stub: true }; caveats: Caveat[] }

export interface ScanProgress { scanned: number; total: number; hits: number; errors: number }
export interface ScanDone {
  type: 'done'; hits: number; errors: number; total: number
  pattern_ids?: string[]; scan_ts?: string; error?: string | null
  cancelled?: boolean
  partial?: boolean
}

export interface ScanHistoryEntry {
  scan_ts: string
  pattern_ids: string[]                                 // 新增
  hits: number | null
  total: number | null
  size: number
  partial: boolean
}

export interface AppConfig {
  dataset_dir: string
  scan: { start_date: string; end_date: string; workers: number; ticker_regex: string | null; label_horizon?: number }
  last_selected_pattern: string
}

export function isPoint(e: { start_idx: number; end_idx: number }): boolean {
  return e.start_idx === e.end_idx
}

export type Level = 'matched' | 'qualified' | 'detected'
export type Tier = Level
