// spec §7 后端 JSON 契约的 TS 镜像。字段名与后端严格一致。

export interface WhereRule { clause_id: string; op: string | null; threshold: unknown }
export interface TopoNode {
  node_id: string; class_id: string; label: string
  source_tag: string
  render_grid?: 'price' | 'time'   // 新增:渲染轴声明,缺省视同 'time'
  where_rules: WhereRule[]
}
export interface TopoEdge { src: string; dst: string; kind: string; rule: string }
export interface Topology { nodes: TopoNode[]; edges: TopoEdge[] }
export interface SerializedPattern {
  pattern_id: string; display_name: string
  topology: Topology; event_styles: Record<string, string>
}

// event:固定四字段 + 子类属性平铺(仅 tooltip 用)
export interface EventDict {
  class_id: string; event_id: string; start_idx: number; end_idx: number
  source_tag: string
  referenced_points?: Array<[number, number, string]>   // 新增:(bar_idx, price, label) 三元组数组
  [attr: string]: unknown
}

export interface ClauseWitness {
  satisfied: boolean; measured: unknown; op: string | null
  threshold: unknown
}
export interface EdgeWitness { satisfied: boolean; measured: number; src: string; dst: string }
export interface PredicateTrace {
  where_results: Record<string, Record<string, ClauseWitness>>
  edge_results: Record<string, EdgeWitness>           // key = "src→dst"
}
export interface MatchDict {
  event_id: string; start_idx: number; end_idx: number
  role_index: Record<string, string>
  children: string[]
  predicate_trace: PredicateTrace | null
  forward_return?: number | null                      // 仅缓冲+label 扫描存在;null=尾部数据不足
}
export interface Analysis { events: EventDict[]; matches: MatchDict[] }

export interface ScanMeta {
  scan_ts: string; start_date: string; end_date: string; workers: number
  scanned: number; hits: number; errors: number; dataset_dir: string; params: string
  // 缓冲扫描新增(旧结果文件无 → 全 optional)
  win_start?: string; win_end?: string
  label_horizon?: number | null; end_role?: string | null
}
export interface StockResult { symbol: string; summary: Record<string, number>; analysis: Analysis }
export interface ScanResultFile {
  pattern_id: string; pattern_spec: SerializedPattern; scan: ScanMeta; results: StockResult[]
}

export interface Bar { date: string; o: number; h: number; l: number; c: number; v: number; rv: number }
export interface Ohlc { symbol: string; bars: Bar[] }

export interface AttrRow {
  event_id: string; start_idx: number; end_idx: number
  clauses: Record<string, ClauseWitness>
}
export interface RelRow { src: string; kind: string; total_src: number; ok_count: number; ok_src_ids: string[] }
export interface RoleDiag { attr: AttrRow[]; rel: RelRow[] }
export interface Diagnostics {
  symbol: string; pattern_id: string; roles: Record<string, RoleDiag>; note: string
}

export interface ScanProgress { scanned: number; total: number; hits: number; errors: number }
// B 实际 SSE done 二形:成功带 pattern_id/scan_ts;失败 = {type:done, error, hits:0, errors:0, total:0}(带 error 键)
export interface ScanDone {
  type: 'done'; hits: number; errors: number; total: number
  pattern_id?: string; scan_ts?: string; error?: string | null
  cancelled?: boolean
  partial?: boolean              // save 路径下后端透传
}

export interface ScanHistoryEntry {
  scan_ts: string
  hits: number | null
  total: number | null
  size: number      // bytes
  partial: boolean               // Task 1 后端总返回(旧文件 → false)
}

export interface AppConfig {
  dataset_dir: string
  scan: { start_date: string; end_date: string; workers: number; ticker_regex: string | null; label_horizon?: number }
  last_selected_pattern: string
}

// 几何自描述:点 ⟺ start==end
export function isPoint(e: { start_idx: number; end_idx: number }): boolean {
  return e.start_idx === e.end_idx
}

export type Level = 'matched' | 'qualified' | 'detected'
export type Tier = Level
