# path2_web 调试可视化架构意图

> 最后更新：2026-07-10
> 覆盖：`path2_web/`（FastAPI 后端 + 设计期评估器 + 漏检诊断投影）+ `path2_web_ui/`（Vue3 前端，含 K 线 / 拓扑 / 5 张漏检 sidebar cards）。
> 框架见 [path2.md](path2.md)，应用层见 [path2_apps.md](path2_apps.md)。

---

## 定位

path2_web 是 path2 dag pattern 的 **web 调试 / 可视化工具**：选 pattern → 全市场扫描（双端缓冲 + N 日前瞻收益 label）→ K 线真蜡烛叠事件 markers + 拓扑面板 + per-node / per-match 诊断侧栏。

两条红线贯穿前后端：

1. **后端纯投影层**：把 `path2.dag` 只读数据结构投影成 JSON，**path2 本身零 web 依赖**（不引入 JSON/HTTP）。
2. **前端类型无关渲染器**：渲染由后端下发的 class_id / event_styles / topology 数据驱动，**不硬编码任何具体事件类型或 pattern**。

→ 合起来的收益：新增 pattern（新建 path2_apps 子包）时，前后端都零改动。

---

## 后端（path2_web/）

```
discovery.py     PatternRegistry:扫 path2_apps/*/ 找 PATTERN_DAG,建 {pattern_id: module}
serialize.py     纯投影:dag 对象 → jsonable dict(投影层边界;不读文件/不起服务)
scan.py          并发扫描:每股 read_pkl → 缓冲切窗 → analyze → 窗口过滤 + label 注入 → 聚合落盘
gate_collector.py 挂 detector.on_gate 收集 GateFailure(诊断路径专用,worker 前 attach、后 detach)
diagnose.py      漏检 4 入口 derive_response(scope=nodes/time/pair/candidate)+ legacy diagnose 封装
api.py           FastAPI 路由 + SSE 扫描进度流(ScanManager) + resolve_eval_meta + Query→Response 分派
data.py          slice_window 唯一权威切片 + OHLC 序列化
config.py        configs/path2_web.yaml 读写(缺项回落默认)
app.py/main.py   create_app 组装(registry + config + router + CORS) + 无 argparse 入口
eval_runner.py   设计期通用 app 评估器三 mode(run_eval/run_regress/run_healthcheck)
```

### 投影边界（serialize.py）—— 最关键

后端与 path2 的主耦合点（另一处：scan.py 消费 `path2.eval.match_forward_returns` 算 label，见下节）。消费 path2.dag 只读结构（AnalysisResult / PatternMatch / PredicateTrace / ClauseWitness / EdgeWitness / PatternTopology / NodeDiagnostics），投影成前端 JSON。三类产物：

- `serialize_analysis` → `{events, matches}`。events 是全集（含未命中），`class_id` + 子类属性平铺（仅 tooltip）；**每 event 附 `source_tag`**（band 身份）——从 spec 权威 tag 集对 event_id 按最长前缀匹配、末级兜底 class_id；**复合事件的 `members` 不平铺进 event dict**（止 child 泄漏，结构化下钻属 future）。matches 含 node_index / children / predicate_trace。
- `serialize_pattern` → `{pattern_id, topology{nodes, edges}, event_styles}`。前端直接用 `pattern_id` / `node_id` 作显示名（无 `display_name` / `label` 字段）。**每节点附 `source_tag`**（前端据它而非解析 event_id 前缀做 band 映射）；函数顶部先 `assign_auto_source_tags`（幂等补齐）+ `_assert_injective_source_tags`（每 node 的 source_tag 须唯一，否则 band 坍缩 → 抛，挡共享实例 / 同名 source_tag 误配）。每节点带 `where_rules`（从 `W.*._Pred` 的 `.meta` 抽，组合子无 meta 跳过）；边带人读 `rule` 串；`event_styles` 缺省按 topology 出现的 class_id 用确定性调色板补齐。
- `summarize` → `{class_id: count}` ∪ `{matches: n}`（命中股计数徽章）。

### 发现 + 扫描 + 流

- **discovery**：新 app 放进 path2_apps 即被发现，后端零改；`invalidate` 弹子模块缓存供热重载。
- **scan**：worker（ProcessPool，模块级 pickle 安全）用 `module.analyze(win)` 即 `Params.default()`（UI 用默认参数）；空窗 / 0 命中跳过，异常转字符串绝不抛断整批；**结果文件自包含**——快照 `pattern_spec` 写进文件，离线可独立渲染。
- **api / SSE**：`POST /scan` 起后台线程跑阻塞扫描，进度经 `asyncio.Queue` + `call_soon_threadsafe` 投递，`GET /scan/{id}/stream` 用 EventSource 推；晚连补发末态。

### 缓冲扫描 + label（eval_meta 协议）

app 层**必需协议** `eval_meta(params) -> {end_node: str, head_buffer_trading_days: int}` 把 app 特异知识（买点 node、指标 warm-up 深度）传给 web——**类型无关红线**：web 产品代码零 `"tb"`/`63` 硬编码。**铁律**：`discovery.py::_validate_eval_meta` 在 pattern 注册时闸严格校验（缺 / 非 callable / 返回非 dict / 字段类型错 → 该 app 不入 registry、进 errors）；`api.require_eval_meta` 因此可直接抛 ValueError 不做 fallback。所有 fallback 路径已删除。

- **双端缓冲切窗**：`buf_start = start − round(head_buffer × 1.65) 日历日`、`buf_end = end + round(label_horizon × 1.65)`——首部供指标 warm-up、尾部供前瞻收益。公式与 `scripts/path2_eval_bottom_breakout_burst.py` **同源同值**（口径对拍约束）。
- **窗口过滤**：缓冲窗 analyze 后，match 按「end_node event 起点日期 ∈ [start, end]（双端含）」过滤，过滤后 0 命中不算 hit；**不按买点去重**（与 eval 脚本的有意差异——web 以 match 为展示单位）。events 全集照旧序列化（缓冲段事件是 K 线灰色层数据源），仅 `summary["matches"]` 改写为窗内数。
- **label 注入**：每保留 match 注入 `forward_return = match_forward_returns(m, end_node, win, [label_horizon])[label_horizon]`（end_node 窗内逐买点日 N 日收益均值；尾部越界 → None）。注入发生在**序列化产物上**（worker 内 dict 操作），serialize.py 保持纯投影。**键语义**：键缺失 = 非缓冲扫描（前端不显示 ret 行）、null = 尾部数据不足（显示 `—`）——前端判别依赖键缺失，勿改成"总注入 null"。
- **结果文件 scan 节**新字段：`win_start`/`win_end`（实际切窗日期）/`label_horizon`/`end_node`；非缓冲时 win_* == start/end、后两者 null。旧结果文件无这些字段，前端 `windowOf` 回退。
- `label_horizon` 默认 20：config.py DEFAULT + `ScanRequest.label_horizon` + 前端输入框三处一致。
- **多 pattern schema（`MultiScanResultFile`）**：单次 `POST /scan` 可传多 pattern_id 并行扫描；结果为每股 `StockResult{symbol, per_pattern{pid: PerPatternResult}}` 列表，`per_pattern` 顶层 `PerPatternMeta` 存每 pattern 的 spec 快照 + hits + win_*。`head_buffer` 取多 pattern 的 max，`label_horizon` 全局单值。前端 `view` store 分离**锚 pattern**（找漏检场景排序键，如 `bo`）与 **`activePatternId`**（右侧渲染的 pattern，如 `bbb`）：`SidebarResultList` 单元格点击只切股不切 active pattern；`activePatternId` 只由 `ChartArea` dropdown 显式切换。

### 设计期评估器（eval_runner.py）

通用 app 评估器，**服务设计期**（authoring-path2-app skill / `scripts/path2_eval_scan.py` 入口 / subagent 程序化复用），与 `scan.py::run_scan` 服务 web UI 是分工关系：

| 维度 | `run_scan`（web UI） | `eval_runner.*`（设计期） |
|---|---|---|
| 输出 | 完整 JSON（含 spec 快照 + events 全集 + matches）供前端渲染 | 轻量 JSON（meta + per_horizon + diff/cases），仅人读 |
| horizon | 单 `label_horizon`（注入 forward_return） | 多 horizon tuple（`(5, 10, 20)` 默认） |
| 计数单位 | **按 match**（同买点多 match 各算一次，符合"展示 match 是渲染单位"） | **按买点去重**（按 `end_node.event_id`，符合"评估对象是买点"） |

三 mode 函数（同 `module_path = "path2_apps.<id>"` 约定，从 app `__init__` 取 `analyze/Params/eval_meta`）：

- `run_eval`：全宇宙 buf_start..buf_end 双端缓冲扫描 + 窗内过滤 + 多 horizon `match_forward_returns`（复用 `path2.eval`），落 `{meta, per_horizon, results}`
- `run_regress`：读 baseline JSON（一次 eval 产物）+ 用当前 spec 重跑 + 按 `(symbol, buy_date)` 对拍，落 `added/removed/unchanged + horizon-by-horizon return diff`
- `run_healthcheck`：扫一次 + 校 `tickers_hit ∈ [MIN, MAX]` 数量级 + 目标票必中确认，落 `{ok, target_hit}`（新建 / 改 detector 后体检）

依赖 path2_web 的 `slice_window` + `_list_pkls` + `TRADING_TO_CALENDAR_RATIO`（同 scan.py 同源同公式，避免双口径）。worker 模块级（ProcessPool pickle 安全）；`param_overrides` 在 worker 内 `replace(Params.default(), **overrides)` 重建。

### 对齐铁律（data.py）

`slice_window` 是扫描 worker、`/ohlc`、`/diagnose` 三处的**唯一共用切片**，保证 `bars[i] ↔ detector 的 start_idx == i` 严格对齐——前端 markers 的 start_idx 才能落对 K 线位置。缓冲扫描下三处共用**缓冲窗**（前端经 `windowOf(scan)` 取 win_*，旧文件回退 start/end），铁律不变。日期串恒为零填充 ISO（`YYYY-MM-DD`），前端 ISO 串比较依赖此格式。

### 漏检 4 入口（diagnose.py `derive_response`）

`GET /diagnose` 用 `scope` 参数分派四档：`scope=None` 走 legacy `diagnose_symbol`（字节等价、前端旧调用不改）；`scope=nodes/time/pair` 走 `derive_response(Query, diag, spec, result)`。三档 scope=非 None 均**复刻 scan worker 套路**在端点内 `attach_and_collect(spec)` → `analyze(...)` → `detach(spec)` 拿到挂了 `gate_failures` 的 `AnalysisResult`，再交 derive。单股即时诊断可接受此重算成本。

| scope | 用户入口 | payload | 关键机制 |
|---|---|---|---|
| `nodes` | 入口 B：拓扑面板点边 | `NodesPayload{edge_id, total_pair, ok_pair, miss_reasons, example_failed_pairs}` | 直读 diag `_rel_rows`，静态图零着色降级 |
| `time` | 入口 A：K 线 brush 框选时段 | `TimePayload{frame, failed_attempts, outside_frame_attempts_count}` | 只列 `failure_event_window` 完全落入 [start_bar, end_bar] 的 attempt；跨界的记进 outside 计数（定义上不属于该时段） |
| `pair` | 入口 D：shift+click 两个 event（主副图皆可） | `PairPayload{valid, edge_id, subchecks[4], applied_swap}` \| `{stub:true}` | 4 subcheck 短路序：`feasible_window → satisfies → anchor → strict`；方向不对试 auto swap；非法 pair 落 `{stub:true}`（无边 / 只 negation / 同 node 等 5 因） |

`Caveat`（`code + message + affected_fields`）挂 Response 上明示"哪块数据没接上、为什么"，前端据此显示提示条不 crash。

### endpoint 一览

| 方法 路径 | 用途 |
|---|---|
| GET `/patterns` | 所有 pattern 静态投影（拓扑面板数据源） |
| GET `/ohlc` | K 线切片 |
| GET `/scans/{pid}` · `/scans/{pid}/{ts}` | 历史扫描列表 / 加载结果文件 |
| GET `/config` · PUT `/config` | 配置读写 |
| GET `/diagnose?scope=` | 漏检 4 入口 + legacy per-node 诊断（scope=None） |
| GET `/preview` | 单股临时 buffered+label 计算（不落盘） |
| POST `/scan` · GET `/scan/{id}/stream` | 起扫描 / SSE 进度流 |

---

## 前端（path2_web_ui/）

Vue3（Composition + `<script setup>`）+ Pinia + ECharts + Vite + TypeScript。API 基址 `VITE_API_BASE` 默认 `localhost:8000`。

### 组件树

`App` 左栏纵叠三面板（`SidebarPatternPanel` 选 pattern / `SidebarScanPanel` 扫描参数（含 label horizon 输入框）+ SSE 进度 / `SidebarResultList` 命中股列表）+ 右侧 `ChartArea`（响应式网格：顶部全局 `level` 三段控件 / `TopologyControl` 拓扑图 / `KlineChart` K 线 + 分轨 markers / `DetailSidebar` 漏斗 + 诊断 + per-match ret 行 + 5 张漏检 cards）。

**漏检 4 cards（`DetailSidebar` 内挂载）**：`CandidateStatusBar` 顶部三档 tier 徽章 / `FailedAttemptsCard` 入口 A 时段查询失败 attempts 列表 / `PairListCard` 入口 B 拓扑点边 miss_reasons 分布 + example_failed_pairs / `PairDetailCard` 入口 D shift+click 单对 event 4 subcheck 短路结果 + auto swap 提示。每张 card 独立读 `/diagnose?scope=` 返回的 Response payload，Caveat 存在时顶部显示提示条。`panels` store 管 sidebar 展开状态 + 当前 active card。

### 状态层（stores/）

- `config`：AppConfig 读写（dataset_dir / 扫描参数 / last_selected_pattern）
- `patterns`：`/patterns` 列表 + 选中 id
- `scan`：扫描执行（startScan → streamScan SSE）+ 实时进度 + 历史
- `view`（**可视化中枢 / 派生单一真相源**）：当前 scanFile / symbol、node 显隐、全局档位 `level`（matched/qualified/detected）、选股即预取的 `diag`（GET /diagnose，经 `windowOf` 与扫描/K 线同窗、带 stale-token guard）、三正交选择 `selected`（match / node 焦点）/ `selectedEventId`（强高亮、跨视图双向）/ `hoveredEventId`（弱）；computed 派生 pattern / currentAnalysis / nodeColors / `tagMap`（source_tag → band）/ `isolated`（无边 node = 流源）/ `matchedIds` / `qualifiedIds`（从 diag 派生）/ `bandKey` / `eventTier`（matched⊃qualified⊃detected 判级）。chart 与 sidebar **共读**这些 computed → 着色 / 计数不漂移

### 渲染层（render/，纯函数）

- `colors`：从 topology + event_styles 派生 node_id → 色（同 class_id 多 node_id 按序生明度变体，不硬编码具体值）；`colorOf(tier, node)` 三档配色——matched=node 本色 / qualified=深灰 / detected=浅灰
- `topology`：DAG 最长路径分层 + 自适应列距（区分 CJK / ASCII 字宽）+ 贝塞尔边，自动布局任意 DAG
- `geometry`：点 / 区间分离 + 贪心泳道 `packLanes`；`packByBand` 复用 packLanes 对每 band 独立分轨（仅依赖 start / end，无类型特判）
- `chart`：events + matches → ECharts custom series（**3-grid**：价格 / 量 / marker 副图）。marker 副图按 **band×lane** 铺（每 detector 实例一 band、band 内重叠分 lane），流源 band 渲染密度层；`level` 门控（rank：detected⊇qualified⊇matched，决定画到哪档）；色 = `colorOf(eventTier(e), nodeOfEventByBand(e))`，**零 per-class 分支**；`selectedEventId` 加最高 z highlight 描边；`tooltipResolver` 拼 diagnose clause + event raw（排 members）；可选输入 `strictWindow`（kline 系列挂双竖虚线 markLine = 严格窗边界）与 `matchLabel`（match 归属带 tooltip 显示 ret 行），缺省行为与旧调用一致。**副图分界线合成**：`composeEffectiveSubH(...)` 纯函数按 `subHeightOffset`（用户拖 divider 的相对平移量）+ 数据情况计算副图实际高度；空数据分支收窄到 `SUB_CANVAS_MIN_H`；banner 移出滚动容器（原 `BANNER_RESERVE` 0 基弃用），避免 K 线纵向压缩时 banner 抖动
- `visible`（**派生单一真相源**）：纯函数族 `isolatedNodeIds`（流源 = 无边 node）/ `deriveTagMap`（source_tag → band 序）/ `bandKeyOf` / `eventTierOf` / `qualifiedIdsOf`（从 diag 取全 clause satisfied 的 event）/ `nodeOfEventByBand` / `resolveTooltipData` / `windowOf`（结果文件实际渲染窗：win_* 回退 start/end，K 线与 diagnose 同窗的唯一取窗口径）/ `formatForwardReturn`（null → `—`，数值 → 带符号一位小数百分比）

### 契约（types.ts）

后端 `serialize.py` JSON 输出的 **TS 镜像**——Topology / TopoNode（含 `source_tag`）/ TopoEdge、SerializedPattern、EventDict（class_id + `source_tag` + 平铺属性，`isPoint()` = start==end）、MatchDict（node_index / children / predicate_trace + 可选 `forward_return`）、ClauseWitness / EdgeWitness、ScanResultFile（自包含 pattern_spec；ScanMeta 可选 `win_*`/`label_horizon`/`end_node`）、Diagnostics、`Level`/`Tier`（matched/qualified/detected）。这是前后端唯一对接面：**serialize.py 改字段必须同步 types.ts**（worker 注入的 label 字段同理）。

### 调试工作流

**三档 level 模型**：每个 event 按可追溯深度分 detected（浅灰，全集）⊇ qualified（深灰，过该 node 一元 where，数据来自预取 diagnose）⊇ matched（彩色，进 match）；全局 level 旋钮统一控 K 线 + sidebar 的天花板（与 nodeVisible 正交）。`DetailSidebar` 是**漏斗总览**：每 pattern node 一行 `detected ▸ qualified ▸ matched` 计数（点档展开候选对比表：列 = clause、单元格 = `实测 (op 阈值) ✓/✗`、行按 tier 着色、可双向选中）；**流源 node**（`isolatedNodeIds` 判，如 bo）渲染独立"原始检测 N"密度徽标、移出 matched 漏斗。pattern-vs-流源区分纯从 `topology.edges` 派生（零后端、零 per-class）。

拓扑面板是 **node 控制器**：单击节点 toggle 该 node、双击拉 per-node 诊断；**点边**触发入口 B `scope=nodes`（静态图零着色降级 = memory 里定的口径）弹 `PairListCard`。K 线点归属括号选 match → `DetailSidebar` 显 per-match `predicate_trace`（每条 where / 边的 satisfied + 实测值）+ `ret_N` 行（forward_return，与归属带悬停 tooltip 同源）。**双向高亮**：K 线 marker ↔ sidebar 候选行点击互选（`selectedEventId` 跨视图联动）。缓冲扫描下 K 线显示全缓冲窗，严格窗边界以双竖虚线标出——缓冲段事件可见（灰色层）但不进 match。

**漏检 4 入口交互**（3 web 入口 A/B/D + CLI workflow E）：
- 入口 A：K 线 brush 框选时段 → `/diagnose?scope=time` → `FailedAttemptsCard` 列框内失败 attempts（跨界的记进 `outside_frame_attempts_count` 计数）
- 入口 B：拓扑点边 → `scope=nodes` → `PairListCard` miss_reasons + example_failed_pairs
- 入口 D：shift+click 两个 event marker（**主副图皆可**，跨图支持）→ `scope=pair` → `PairDetailCard` 4 subcheck；方向反了后端 auto swap，前端展示 `applied_swap` 提示
- 入口 E（workflow scan-top-miss）：独立 CLI `scripts/scan_top_miss.py`（非 web 内），批量跑 pattern 输出 markdown 排序，走后端 `/diagnose` 复用

### 数据流

扫描落盘自包含结果文件（含 `pattern_spec` 快照）→ 前端 `open` 加载 → `view` 派生 → 类型无关渲染。前端永不直连 path2，只吃后端 JSON。
