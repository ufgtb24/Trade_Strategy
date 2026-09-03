// spec §7 后端 JSON 契约的 TS 镜像。字段名与后端严格一致。

export interface WhereRule {
  clause_id?: string; op?: string | null; threshold?: unknown
  kind?: string; field?: string | null; key?: string
  children?: WhereRule[]
}
export interface TopoNode {
  node_id: string
  solve?: boolean               // 求解参与标志(solve=False 只显示;前端 level 门控免疫判据,Task 6 serialize 契约)
  render_grid?: 'price' | 'time'
  materialize_keys?: string[]
  where_rules: WhereRule[]
  produced_by?: string | null   // 子结构 node 的物化来源父 node_id(独立 node 缺省/None)
  child_slot?: string | null    // 子结构 node 在父 children 中的 slot 名(独立 node 缺省/None)
  parent_refs?: [string, string][]  // 被哪些父的 children 引用:[父 node_id, slot 名] 全量(独立 node 也收录)
}
export interface TopoEdge { src: string; dst: string; kind: string; rule: string; anchor_field?: string | null }
export interface Topology { nodes: TopoNode[]; edges: TopoEdge[] }
export interface SerializedPattern {
  pattern_id: string
  topology: Topology; event_styles: Record<string, string>
  // ★ v4 契约 C · 挂了 debug_break 的 node_id 列表(拓扑序 · 去重)
  debug_enabled_nodes: string[]
}

export interface EventDict {
  instance_id: string            // 唯一实例键 = span_id(node_id, start, end) + "#" + instance_idx(恒含 #idx)
  node_id: string                // 物化来源 node(band 分组键)
  instance_idx: number           // 桶 (node_id, start, end) 内按流序从 0 起的序号
  start_idx: number; end_idx: number; confirm_idx?: number
  child_refs?: Record<string, string[]>   // 全实例化引用:{slot: [instance_id]}
  ref_ids?: Record<string, string[]>      // 引用型槽(ref_slots 协议):{slot: [instance_id]}
  [attr: string]: unknown        // 其余属性平铺(旧身份字段体系已消灭,见 instance_id/node_id/instance_idx)
}

export interface ClauseWitness {
  satisfied: boolean; measured: unknown; op: string | null
  threshold: unknown
  label?: string | null
  children?: ClauseWitness[]
}
export interface MeasuredKindAware { kind: string; value: unknown; label: string }
export interface EdgeWitness { satisfied: boolean; measured: MeasuredKindAware; src: string; dst: string }
export interface PredicateTrace {
  where_results: Record<string, Record<string, ClauseWitness>>
  edge_results: Record<string, EdgeWitness>
}
export interface FirstPassageCounts { up: number; down: number; both: number; none: number }
// per-pattern 集合级统计:ratio = up/(up+down),both/none 排除分母(后端已算好,前端只展示);null=分母为 0
export interface FirstPassageStats extends FirstPassageCounts {
  n_bars: number
  ratio: number | null
  random_up: number; random_down: number; random_both: number; random_none: number
  random_n: number
  random_ratio: number | null
  k: number                    // 几何对称单参数(波动率标准化阈值 = k × σ)
}
// per-pattern 首次穿越方向比例对(命中集 vs 随机基线);null = 分母为 0(全 both/none)
export interface FirstPassageRatio {
  ratio: number | null
  random_ratio: number | null
}

export interface MatchDict {
  match_id: string               // 唯一 match 键(含 node_index 组合位)
  start_idx: number; end_idx: number
  node_index: Record<string, string>      // nid -> instance_id 字符串(全实例化引用)
  children: string[]                       // instance_id 列表
  predicate_trace?: PredicateTrace | null
  forward_return?: number | null
  // per-match forward_drawdown(T1 注入,与 forward_return 并列;null=窗口内未触底,undefined=老 scan file 无此字段)
  forward_drawdown?: number | null
  // 按买点聚合锚:leaf 事件 instance_id(同 leaf 可被多 match 共享,多对一确认)
  leaf?: string
}
export interface Analysis { events: EventDict[]; matches: MatchDict[] }

// ── 多 pattern schema ───────────────────────────────────────────────
export interface PerPatternResult {
  summary: Record<string, number>            // {node_id: count} ∪ {matches: n}
  analysis: Analysis
  max_forward_return: number | null
  // per-symbol-per-pattern 最差下行(T1 注入,聚合用 min;null=无 match,undefined=老 scan file)
  min_forward_drawdown?: number | null
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
  // per-pattern 全局 drawdown 分布(T1 注入,与 stats 同 shape 的 PatternStats;undefined=老 scan file)
  stats_drawdown?: PatternStats
  // per-pattern 首次穿越集合级统计(T3 注入;单组(几何对称单 k);undefined=老 scan file 或 first_passage_enabled=False)
  first_passage_stats?: FirstPassageStats
  // Task 3:参数快照落盘字段。三者仅当调用方传入 pattern_params_dicts[pid] 时才存在,老 scan file 没有。
  params_snapshot?: Record<string, any>
  params_hash?: string
  params_provenance?: string
}
export interface ScanMeta {
  scan_ts: string; name?: string; start_date: string; end_date: string; workers: number
  scanned: number; hits: number; errors: number; dataset_dir: string
  params?: string                                      // legacy 字段;Task 3 起新 scan 不再落盘,仅老 scan file 可能仍带
  params_schema_version?: number                       // Task 3 新增
  note?: string | null                                 // Task 3 新增(扫描备注,可为 null)
  win_start: string; win_end: string                  // 必有(非 optional)
  label_horizon: number                                // 必有(非 optional)
  first_passage_k: number                              // 几何对称单 k(波动率标准化阈值 = k × σ)
  partial?: boolean
}
export interface StockResult {
  symbol: string
  per_pattern: Record<string, PerPatternResult>        // key = pattern_id
  // 随机日基线首次穿越计数(T3 注入;单组;undefined=老 scan file 或 first_passage_enabled=False)
  random_first_passage?: { n_sampled: number; counts: FirstPassageCounts }
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
  instance_id: string; node_id: string
  start_idx: number; end_idx: number
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
  // ★ wire 字段名沿用后端旧名,值已是 instance_id(前端只读值,不当作身份键)
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
  anchor_bar: number; node_id: string; gate_name: string   // node_id 值 = 物化来源 node(Task 1)
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
  /** 该 pattern 全部 node 的 node_id 全集(后端从 spec.nodes 提取,与 gate 过滤契约面一致)。
   * 下拉选项锚:区间内无失败的 node 置灰可见。可选——旧后端/测试 fixture 缺失时前端
   * 回退到 failed_attempts 实际提取(退化为"所见即所败")。 */
  all_nodes?: string[]
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
  pattern_ids?: string[]; scan_ts?: string; name?: string; error?: string | null
  cancelled?: boolean
  partial?: boolean
}

export interface ScanHistoryEntry {
  scan_ts: string
  name: string
  pattern_ids: string[]                                 // 新增
  hits: number | null
  total: number | null
  size: number
  partial: boolean
  // history 列表聚合:每 pattern 的 match 数 + forward_return 中位数(无 match → null)
  // + 首次穿越方向比例对(fp 必填——显式标注的 fixture 会挡漏字段;null=该 pattern 无 first_passage 数据)
  // + 参数结构一致性(快照 vs 当前默认;false=当时代码与当前不同;null=无法判断:无快照或 pid 无 app)
  per_pattern: Record<string, { hits: number; median: number | null;
                                fp: FirstPassageRatio | null;
                                params_consistent: boolean | null }>
}

export interface AppConfig {
  dataset_dir: string
  scan: { start_date: string; end_date: string; workers: number; ticker_regex: string | null
          label_horizon?: number
          first_passage_k?: number
          price_min?: number | null; price_max?: number | null; volume_min?: number | null }
  last_selected_pattern: string
}

// ─── Task 6/7:GET /params_diff 载荷(scan 内嵌快照 vs 该次扫描实际所用参数文件当前
// 内容的字段级 diff;锚由 params_provenance 决定,不总是 params.yaml) ───────
export interface ParamsDiffEntry { path: string; snapshot: any; current: any }
export interface ParamsDiffResp { has_snapshot: boolean; match: boolean; diffs: ParamsDiffEntry[]
                                  anchor_file?: string   // 该次扫描实际所用参数文件(缺省 params.yaml)
                                  anchor_missing?: boolean }   // 锚参数文件被删:/params_diff 返回 200 标记,前端显灰"?"dot

// ─── Task 9:Working Copy 探索态状态机(per-pid)。spec = docs/research/2026-07-20_params-profiles-dev-modes ───
export interface WorkingCopySlot {
  enabled: boolean                       // true=探索态(视图源=WC) false=浏览态(dict 保留)
  baseline: Record<string, any>          // fork 时的 snapshot(diff 基准/重置目标)
  currentDict: Record<string, any>
}

export function isPoint(e: { start_idx: number; end_idx: number }): boolean {
  return e.start_idx === e.end_idx
}

export type Level = 'matched' | 'qualified' | 'detected'
export type Tier = Level
