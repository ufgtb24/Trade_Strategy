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
  view_guard?: ViewGuard                               // 带护栏扫的才有
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

/** 一根 K 线。调试视图里看图下界之前的 bar(探测器预热用,这一轮不给看)只留日期,价格与量为 null:
 *  留着它们只为让按序号定位的事件 / match 与 K 线对齐,渲染时一律不画(见 render/chart.ts 的 isPriced)。 */
export interface Bar {
  date: string; o: number | null; h: number | null; l: number | null; c: number | null
  v: number | null; rv: number | null
}
/** 有价格的 K 线(看图工作流的图窗都在看图下界之后,根根有价格) */
export interface PricedBar { date: string; o: number; h: number; l: number; c: number; v: number; rv: number }
export interface Ohlc { symbol: string; bars: Bar[] }
export interface PricedOhlc { symbol: string; bars: PricedBar[] }

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
  per_pattern: Record<string, { hits: number | null; median: number | null;
                                fp: FirstPassageRatio | null;
                                params_consistent: boolean | null }>
  // 文件里 scan 段的区间与看图范围护栏标记(缺失为 null)
  start_date?: string | null; end_date?: string | null; win_end?: string | null
  view_guard?: ViewGuard | null
  // 读了完整行情的旧扫描(区间越出本轮看图范围):命中数、中位数、首次穿越比为 null,打开会被后端拒绝
  old_scan?: boolean
}

/** 扫描时的看图范围护栏:这份扫描读的是截断副本、起点不早于 view_floor */
export interface ViewGuard { view_floor: string; train_end: string }

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

// ─── 看图工作流模式(/workflow/*):清单由命令行工具 chart_workflow 生成,标注批次由后端写盘 ───
/** card_hits:卡成立日清单(只在调试模式下用;每张点「是 / 不是」,标完才露出成立日之后的走势) */
export type WorkflowListKind = 'bigmoves' | 'contrast' | 'contrast_blind' | 'card_hits'

/** 看图工作流里的单张图事件:放大看了 / 点了买点或选了判定 / 大涨段第一次露出结果 */
export type ChartViewEvent = 'zoom' | 'annotate' | 'reveal' | 'peek'

/** 后端状态根:在哪、是不是来自环境变量(临时目录,记录不进正式账本)、能不能用、是哪种模式 */
export interface WorkflowStateInfo {
  path: string | null; from_env: boolean; env_var: string; ok: boolean; message: string | null
  mode?: 'formal' | 'debug'; mode_label?: string | null
}

/** 后端是正式模式还是看图工作流的调试模式(调试段,写调试账、不进正式账),以及生效的看图范围 */
export interface ModeInfo {
  mode: 'formal' | 'debug'
  /** 调试模式时界面顶上横幅的文字;正式模式为 null */
  label: string | null
  view_floor: string
  train_end: string
}

export interface WorkflowListMeta {
  list_id: string; kind: WorkflowListKind; title: string; created_at: string; n_items: number
  /** 后端拿不到记账类文件的家(状态根)时为 'state_root_missing':这时打不开清单、发不了标注 */
  blocked?: string
  /** blocked 时后端给的中文说明 */
  blocked_message?: string
}

export interface WorkflowSummaryRow {
  scope: string; n_hits: number; n_stocks: number; n_weeks: number
  hit_dir_mean: number | null; ctrl_dir_mean: number | null
  dir_lead: number | null; dir_noise: number | null
  hit_mag_median: number | null; ctrl_mag_median: number | null
  mag_lead: number | null; mag_noise: number | null
}

export interface WorkflowSummary {
  rows: WorkflowSummaryRow[]
  concentration: { max_week_share: number | null; max_stock_share: number | null }
  graduation: { passed: boolean; checks: Record<string, boolean> }
}

export interface WorkflowItem {
  item_id: string; symbol: string; t: string; entry_date: string
  view_start: string; view_end: string
  /** 交易所(NASDAQ / NYSE / AMEX);证券名单里没有就是 null。目前网页不用它 */
  exchange?: string | null
  /** 跨源比对(与 Nasdaq 日线逐日比涨跌幅);盲看清单没有 */
  xcheck?: WorkflowXcheck
  /** 证券类别(如「普通股」「未知（名录里查不到）」);旧清单没有这个字段 */
  sec_label?: string
  /** false = 证券名录里查不到,类别是按代码规则推断的 */
  sec_known?: boolean
  /** 盲看清单只有 decision / entry */
  marks: { decision?: string; entry?: string; up_line?: number; down_line?: number; peak_date?: string }
  /** 盲看清单只有 M;卡成立日清单为空 */
  metrics: Record<string, number | null>
  tags: string[]
  /** 卡成立日清单:标完「是 / 不是」后图窗露到哪天(标之前只到成立日 view_end) */
  reveal_end?: string
  /** 卡成立日清单:图窗里成立日之前卡也成立过的段 [起, 止](都早于成立日) */
  card_true_runs?: [string, string][]
}

/** 卡成立日清单里一张图现在的标记(后端只追加,这是最后一下;first_verdict 是第一下) */
export interface CardMark {
  mark_id: string
  verdict: 'yes' | 'no'
  reason: string
  ts: string
  first_verdict: 'yes' | 'no'
  /** 一共标过几下;大于 1 说明看过走势后改过 */
  n: number
  /** 揭开后才标:标第一下之前,这张图成立日之后的走势已经在别的清单里画出来过(不进小结统计) */
  late?: boolean
}

export interface WorkflowXcheck {
  status: 'ok' | 'mismatch' | 'unavailable'
  n_compared: number; n_missing: number
  mismatch_days: { date: string; r_ours: number; r_nasdaq: number }[]
  reason?: string; window?: [string, string]
}

export interface WorkflowGroup { key: string; title: string; item_ids: string[] }

export interface WorkflowList {
  schema: string; list_id: string; kind: WorkflowListKind; title: string; created_at: string
  train_start: string; train_end: string
  params: Record<string, any>
  summary?: WorkflowSummary
  groups: WorkflowGroup[]
  items: WorkflowItem[]
  /** 卡成立日清单:每张图现在的标记(打开清单时后端带上) */
  card_marks?: Record<string, CardMark>
}

/** 正例 / 反例 / 数据有误(用户确认行情数据有错,汇总进数据错误登记) */
export type AnnotationLabel = 'positive' | 'negative' | 'data_error'

/** 一个买点;每张图至多一个主买点(primary)。 */
export interface BuyPoint { date: string; primary: boolean }

/** 一条标注草稿(每个 item 最多一条)。标签必填;「数据有误」要框选起止;正例至少一个买点。 */
export interface Annotation {
  ann_id: string; item_id: string; symbol: string
  range_start: string | null; range_end: string | null
  buy_points: BuyPoint[]
  label: AnnotationLabel | null; note: string
  /** 点第一个买点之前,把图往右展开看过决策日之后的走势 */
  peeked_before_buy: boolean
  /** 大涨段清单:第一次露出结果(买点从无到有)时的买点;没露出过为 null */
  first_buy_points: BuyPoint[] | null
  /** 大涨段清单:露出结果之后买点改过或清除过(「看过结果后改过」) */
  changed_after_reveal: boolean
  updated_at: string
}

export interface AnnotationBatchResult { batch_id: string; path: string; n: number }

export interface AnnotationBatchMeta { batch_id: string; list_id: string; n: number; created_at: string }
