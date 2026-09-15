# tune-gates 参考卡：口径、布局、实证坑与校准状态（pattern 无关）

> 给 Claude 读。操作流程、停点与状态处理见 `SKILL.md`；bb_v1 的真实数字与案例在 `apps/bb_v1/notes.md`。本卡自足。

## 0. 何时读

- 动手扫描、一致性验证、筛选、联合识别之前：§1、§2、§10、§11。
- 要解释分辨力、功效线或某个数字的来历：§7、§8、§9。
- 断点续跑、半截状态、确认窗扫描：§11、§12。
- 记裁定、查账本：§13。

## 1. 背景设定

- **研究声明是窗口级的**：`apps/<app>/windows/<window>/study.py`（`tune.install` 生成）+ 同目录 `classification.json`（`tune.install` / `tune.setup` 生成）；app 级只留 `notes.md`。
  - 声明项 = `study_io.STUDY_NAMES`（`APP_MODULE`、`BASE_YAML`、`WIDE_OVERRIDES`、`SCAN_GRID`、`WHERE_LEVELS`、`REF_POINT`、`TIGHT_WHERES`）+ 可选 `DESIGN`（`"grid"` | `"screen"`，缺省 grid）；加载时忽略多余的名字。模板 `apps/_template/study.py`。
  - 键写法：`SCAN_GRID` / `WHERE_LEVELS` / `TIGHT_WHERES` 用 (section, field) 元组键；`REF_POINT` 用 "section.field" 点号键。
  - 筛选与联合要两份声明共存、各自的指纹互不作废，所以声明按窗口放。
- **工作点**（`REF_POINT`）= 正式参数（`params.yaml`，未套放开值）在全部轴档位上的落点，由 `install` 自动推出，不手写。新窗口覆盖检测参数与闸的全部轴（分类表 `ref_point_scope == "all"`）；只覆盖检测参数的旧窗口不能筛选、不能联合识别。
- **扫描底座** = `BASE_YAML` ⊕ `WIDE_OVERRIDES`，展开成分类表的 `ref_params`。底座比较靠的是值：不在网格里的参数在全部检测组合中都取这份底座的值，改一个数字就换了整张长表评估的世界。where 类参数在放开值里要放到机制下限——不紧于档位里的最松档，否则更松那几档的买点在扫描时就被拦掉，事后切不出来（准入机械拒绝）。
- **宽进点** = 检测参数取工作点值、闸全关；优势检查与筛选的第二个比较点。
- **口径单源**：扫描把 `study_io.RUN_CALIBER`（app、买点起止、首部缓冲、标签前瞻期、首次穿越边界宽度、价格与量能过滤、study / source / base / ruler 四个指纹、`label_mode`）写进 `longtable/run_meta.json`；一致性验证、筛选、联合识别都从那里读，不重复传。同一窗口续扫时任一项不同即拒绝——长表跨多轮续跑才扫完全宇宙，中途换了检测代码或底座，已扫与后扫的股票就混了两种配置。`ticker_regex` 不进口径（小正则试跑后放开全宇宙续扫是支持用法），但写进 run_meta 供状态推导算应扫全集。
- **尺子指纹**（`ledger.ruler_fingerprint`）= `ledger.RULER_FILES`（`path2/eval.py`、`path2/calc/atr.py`、`edge_core.py`、`inference.py`）的哈希；任一变了，所有判定都要重做。
- **账本** `docs/sample_usage/<app>.jsonl`：git 跟踪、只追加、永不删；产物先写完、记录最后写（`ref` 带产物 sha256，`ledger.append` 校验）；读盘只容忍截断的尾行。环境变量 `TUNE_LEDGER_DIR` 可改目录（冒烟与单测用）。记录类型见 §13。
- **可再生性**：`study_io.check_regenerable(longtable_dir)` 六条链核「当前代码能否重新产出这份长表」，其中链 6 核长表记录的底座指纹 == 分类表现在记录的（重建分类表会把底座溯源接回来，只核分类表会假阳）。True 只表示没发现不可再生的证据，已知盲区见 docstring。

## 2. 一致性验证：为什么每个窗口都要验

**入口红线**（`screen.check_consistency`，`tune.screen` 与 `tune.find` 都调）：窗口目录下 `compare_longtable.log` 存在、结论行 `mismatch=0`，且日志首行记录的 study 指纹与尺子指纹与现在相同；任一不满足即人话拒绝。确认窗扫描不要求。

扫描结果与逐格调引擎的等价性**不是工具单独的性质，是工具与 app 的联合性质**。工具代码是确定性的，但等价性还依赖三件属于 app 的事，换 app、改拓扑、加新轴都会重新打开：

1. **`filter_params` 是 app 作者的一句声明，工具静态验不了**：detector 声明「该参数只控制发不发射、不改变事件字段」，工具据此把它踢出检测组合、改成事后按字段谓词切。若 emit 闸实际还改了事件字段，这个声明就是假的，只有真跑两边比才知道。
2. **where 当列谓词的等价性依赖边拓扑**：若某 node 是 `NegationEdge` 的 dst，收紧 where 会让被否定的事件变少、反而增加 match，事后按行过滤补不出来（`check_predicate_axes` 挡住能静态识别的部分，挡不住的仍需实测）。
3. **流缓存的影响集是对着这个 app 的参数探出来的**：`classify` / `influence_dims` 在运行时判定哪个参数影响哪个 detector；参数若经探针看不见的路径（共享对象、模块级默认值）影响 detector，缓存会复用本该失效的流。残留的假设是「consumes 链与 detector node 集不随参数取值变」：预置流的键必须 ⊆ 当前 spec 的 detector node 集，越界即报错；「预置流与本次 params 同源」只能靠工具自己的缓存键正确。

能被守卫拦住的静默分歧应尽量变成守卫（negation × 过滤型维、宽集去重命中都已改成命中即 raise）；最难消掉的是第 1 条的语义声明。

### 2.1 验证的是什么

**Step A（逐格 vs 引擎）**：`tune.compare` 按股票并行（`workers`），抽样 = 扫描范围内（run_meta 的 `ticker_regex`，排除 `filtered_symbols.csv`）命中 `cmp_ticker_regex` 的股票 × 研究设计展开的检测组合里的随机格、角点与收紧 where 套（数量由 `cmp_n_random_cells`、`cmp_n_tight_cells` 控制，种子 `cmp_seed`）。比较长表按格谓词聚合的结果与直接调 `engine.analyze()` + serialize 的结果：比较键为 bound 节点 span + fr 12 位小数 + 四态多重集 + 每股 `match_fp_counts`；四态按买点事件回填（serialize 只给同一买点事件的第一条 match 填四态）。红线 `mismatch=0`，不得靠放宽比较键、放宽容差、跳过样本、缩小股票集达成。

**股票覆盖红线**（`compare_longtable.MIN_SYMBOLS` = 500）：真正比过的股票 ≥500 只，或扫描范围内的股票全部比过（小范围试扫）。抽到的股票不够时验证直接拒绝执行、旧日志不动；结论行在 `mismatch=` 之后记下比过 / 抽到 / 扫描范围三个股数，`screen` / `find` 入口按它复核，缺这三个数的日志一律要求重做。全宇宙扫描用默认抽样范围约抽到一千只出头。

**教训**：先起验证这个长跑任务、再读筛选或识别结果；入口已机械拦住，但别因为识别便宜就想先看一眼。

并行不改变它只是抽样：比较项数相对联合空间总格数的占比很小，全暴力跑完整个联合空间要数十天量级。一致性验证是花百分之几的代价，买一次「快路径没说谎」的证明。

## 3. WORKERS 怎么定（实测定标，扫描与验证通用）

**结论：瓶颈是 CPU 拓扑，不是内存。** 别按「核多就多开」或「保守开 8」拍脑袋。

定标（`bench_workers.py`，i7-14700K = 8 P 核 + 12 E 核 / 28 逻辑线程，`^A[A-C]` 108 只，load≈4.8 非空载；内存口径 PSS——进程池 fork 后大量页写时复制共享，直接加 RSS 会重复计数）：

| WORKERS | 扫描 wall | 相对 W=8 | 验证 wall | 相对 W=8 |
|---:|---:|---:|---:|---:|
| 4 | 33.8s | 0.65× | 266.6s | 0.64× |
| 8 | 21.9s | 1.00× | 170.9s | 1.00× |
| 12 | 17.0s | 1.29× | 141.1s | 1.21× |
| **16** | 14.1s | **1.55×** | 122.5s | **1.40×** |
| **20** | 13.1s | **1.67×** | 113.9s | **1.50×** |
| 24 | 13.7s | 1.60× | 116.4s | 1.47× |
| 26 | 12.9s | 1.70× | 115.6s | 1.48× |

- **拐点在 16~20**：W=8→16 还有 40~55% 收益，16→20 只剩约 7.6%，24 起持平甚至倒退。大小核混合：前 8 个 worker 各占一个 P 核，第 9~20 个落到 E 核（单线程约 P 核一半），再往上只能吃超线程，而 detector / solve 纯 CPU 密集。
- **内存不是约束**：每多一个 worker 约加 35 MB。
- **默认取 16**（`Settings.workers`）；机器空闲可上调到 20，与别的会话共用时 16 更稳。空载机器拐点可能略右移，要压榨就在目标机器上重跑 `bench_workers.py`。

## 4. 参数分类与准入

- **分类**（`multivar_core.classify` 探针）：W = 纯 where 阈值；F = 过滤型（detector 的 emit 闸，事后按字段谓词切，不进检测组合）；D = 构造参数（改了必须重新检测）；E = 只改边的参数（暂不支持进网格）。`SCAN_GRID` 放 D / F，`WHERE_LEVELS` 放 W。**分类以探针为准，不凭参数名猜。**
- **检测组合**（`study_io.design_combos`）：grid = D 维档位笛卡尔积；screen = 工作点 + 每个 D 维单独翻到其他档 + 任意两个一起翻（N 个三档参数时 1 + 2N + 4·C(N,2)）。格数 ≠ 检测组合数；张量仍是笛卡尔形状，未展开的格为空。
- **逐档合法性**（`grid_propose.level_rows`）：每档 `Params.from_dict(strict)` + `build_pattern`；换档后买点 node 变了 → 尺子；首部缓冲需求超出本窗 → 剔除；与别的档 detector 状态和 where 表全等 → 等价档。
- **准入**（`grid_propose.admission`，机械闸 3）：
  - 尺子参数、非法档、首部缓冲不够的档 → 拒绝；
  - 检测参数：`stage="screen"` 时每维 ≤3 档、含正式值、无等价档（等价的翻转恒为零，白占多重比较名额）；
  - 谓词类（W / F）按 feature-study 判定分三类（`grid_propose.axis_verdicts` 读账本 `verify`，判定之后代码或标签定义变过 → 作废）：确实有用 → 可多档；在役未审定 → 档位恰为 [最松档, 正式值]；未在役且未审定 → 拒绝；
  - W 维在放开值里不得比最松档紧。
- **选维**：共线维二选一；机制合理值（窗口长度 / 基线口径等超参数）不进网格。

## 5. 联合识别与复核要点

- **可评估**：每折四态总数 ≥ 功效线、每折买点事件数 ≥ `min_segments_floor`、且不是退化格（闸类轴上紧档计数与相邻松档全等）。功效线取自最近一次优势检查实测（§8）。不可评估 ≠ 坏：不作邻居、不作墙，报计数不报比例。
- **打分与排序**：参照格 = 工作点；每格每折相对参照格的首次穿越率差取各折最差者 → r=1 邻域最小（只在可评估格之间）→ `region_core.rank_cells` 的键排序。候选格 = 移动的参数 ⊆「一起调」参数的格，联合网格外的单翻转 / 两两翻转格由筛选扫描补上（两表同名检测组合是同一批行，工作点格计数逐位自检）。
- **校正读法**：按股 bootstrap 连筛选一起重做（每个副本先按同一组股票权重重挑「一起调」的参数，股票权重按 symbol 名对齐两张表），optimism = 副本选中格在副本上的邻域分 − 同一格在原样本上的邻域分的均值。按股 bootstrap 只含个股噪声、不含同期行情噪声，所以它是真实外推损失的**下界**。对半分验证在联合网格内照报。朴素分数单独为正不下结论，几条证据方向一致才读成稳健。
- **产物**：`cells.npz`（联合网格全量格张量，带 `count_unit`）、`cells.csv`（候选格排名前 `region_find.CSV_TOP` 行，含筛选补充格）、`region_report.md`。按坐标查任意一格走 `tune.cell`（张量直接索引、每次记账），不读 CSV 捞。
- **旧产物**：没有 `count_unit` 键的 `cells.npz` 读成 `"row(legacy)"`（逐行口径，同一段买点可能重复计数），只作参照。研究声明变过（网格变了）的 `cells.npz` 拒绝查询。

## 6. 坑（通用教训；bb_v1 的具体数字见 `apps/bb_v1/notes.md` §8）

1. **验证夹具的字面代码不能直接信**：`dict(a, **b)` 要求 `b` 的键是字符串，两侧都是元组键 dict 时直接 `TypeError`。改法：用 `{**a, **b}`。引用一段对照脚本之前先跑通。
2. **参数名不能告诉你它属于哪类**：读起来像 where 阈值的百分比参数可能是 detector 内部 emit 闸（F），塞进 `WHERE_LEVELS` 会被 `classify()` 拒绝。一律以分类输出为准。
3. **比较键不能写死含孤立 node**：不进求解集的 node 在长表里没有列，取键直接 `KeyError`。比较键只取实际进求解集的 node。
4. **对照侧可能缺股票级前置过滤**：直接调引擎没有扫描那层股票级过滤，被整支过滤的股票会在引擎侧跑出 match、长表侧恒 0——是取数范围漏了过滤，不是被测对象分歧。先验地从股票池排除 `filtered_symbols.csv` 里的股票。
5. **对照脚本自造的保守边界可能多余**：自带一道比生产更严的「窗口切片行数过短则跳过」会漏股票；判据对齐生产代码实际用的边界（只跳空窗口）。
6. **没有 mismatch 可查时，坑在夹具自己**：长表与引擎逐格一致时，排查耗时大多花在参照侧写错，上面 1~5 条都是这类。
7. **格级全量产物是 `cells.npz`，不是 CSV**：联合空间一大，全网格逐格建 dict 再写全量 CSV 既吃内存又巨大，而全量 CSV 没有读取点。全量落 npz，CSV 只写前 `CSV_TOP` 格。
8. **先认清计数单位**：功效线卡的是每折全部 bar 数，可评估另要求每折买点事件数 ≥ `min_segments_floor`；同一段买点内的 bar 强相关，所以按股去簇的设计效应进功效线。逐行口径会把被多个前缀共享的同一段买点重复计数，方向不保守——现在一律买点事件口径（§9）。**跨折归属**：行按买点 node 起点日（`buy_date`）落折，跨年份的买点事件整段记进起点日所在年，与 serialize 生产口径同源；边界附近年份的计数可能因此略有偏移。
9. **一个门槛流经子样本流程时，等效严格度会变**：对半分验证把门槛原样套在两个半样本上，每格计数天然约为全样本一半，等效门槛翻倍，可能让某条证据单独翻转、看起来像分歧。敏感性分析改门槛前，先查它还流经哪些子样本流程。
10. **排期**：一致性验证是瓶颈，识别是分钟级、明显快于扫描和验证。
11. **内存随规模放大，先算「最终多少行、谁会同时拿着它们」**（这几处都在网格小时安全、网格大了才现形）：
    - 扫描主进程：一次性提交全宇宙会让 Future 持有每股结果直到本轮结束。改为有界提交（滑动窗口 `wait(FIRST_COMPLETED)` + 按完成数补投），峰值只随 `shard_stocks` 走。
    - 验证端与识别端不 `concat` 整张长表：验证端逐片读、逐片按 `cmp_ticker_regex` 过滤、只读用得到的列；识别端 `region_core.prepare_shards` 逐片离散化再拼接。
    - 扫描收尾的台账不读数据：累计行数读 parquet 元数据（不能用 `run_stats.jsonl` 的行数加总——被杀掉的轮次写了分片却没活到写统计），格 × 折分布逐片 `groupby` 再累加。
    - 长表落盘前收缩列类型（字符串 → category、`buy_date` → datetime64、整数 `downcast`；`seg_id` 固定 int64）。**浮点列一律不动**：真扫维浮点列参与精确相等匹配，`fr` 被一致性验证按 12 位小数逐字比较，where 维浮点列走不等式，收窄都会出错。
    - 已有分片可原地转换列类型（逐片读 → 收缩 → 写新目录 → 逐列比对值相同 → 替换），**别忘了一并搬 `longtable/run_meta.json`**，它是口径的单一来源。

## 7. 校准状态

- **设计效应与定向占比没有默认值**：功效线、噪声地板、联合可行性一律取本窗优势检查实测值（`edge` 记录的分辨力），没有实测就拒绝，不回退常数。
- **买点保留比例先验** `budget.R_BAR_DETECT_PRIOR = 0.85`：只在 bb_v1 上标定过；只许用于筛选之前的估算，由它算出的分辨力 / 可行性标「估计」；筛选之后用实测保留比例。
- **口径推导量由口径算，不写死**：时间窗宽 = `inference.time_window_days(label_horizon)`；窗数由数据跨度算；多重比较族大小 m = 实际对比数（优势检查时是预估，标「预估」）。
- **bb_v1 标定例**（仅供量级对照）：p = 0.5、deff = 5、s_dec = 0.62 → n_pl ≈ 3.29/δ²，δ = 2 点约每折 8233 个 bar。
- **尚无跨 app 实战校准的阈值**：筛选 q = 0.10；交互兜底 |z| ≥ 2；年交互与探针旗标 |z| > 2；时间窗异质性 p < 0.05；换池旗标 ≥ δ/2；刚过线 = 幸存但 q 值 > 阈值的一半；优势检查覆盖率提醒 < 80%；层内基线定向日 ≥ 20；紧档保留买点 30%~70%；预期把握 < 50% 时开窗前问；幸存者偏差 π = 0.3、偏差 > 1 点降为暂定。

## 8. 功效线与分辨力（`budget.py`、`edge_core.resolution`）

δ 与 n_pl、floor 的输入输出用比例（0.02 = 2 点）。

| 量 | 公式 | 说明 |
|---|---|---|
| SE_level | 工作点格两年合并的按股线性化 SE（`inference.level_se`） | 买点事件口径 |
| 设计效应 deff | (SE_level / √(r(1−r)/ΣD))² | D = 定向 bar |
| 定向占比 s_dec | ΣD / ΣN | N = 全部 bar（含 none） |
| SE_flip | SE_level·√((1−r̄)/r̄) | r̄ = 改动后买点保留比例：闸类直接数 bar；检测参数筛选前取先验（估计） |
| 筛选分辨力 x_screen | (z_BH(m, q) + 0.84)·SE_flip | m = 对比族大小，q = `screen_fdr_q` |
| 单个预写改动 x_single | 2.8·SE_flip | 双侧 5% + 80% 功效 |
| 两个及以上参数同改 | x_single × 1.7 | `budget.delta_needed_for_joint`；≤ δ 才可行 |
| 功效线 n_pl | 1.96·p(1−p)·deff / (1.2·s_dec·δ²) | 每折所需全部 bar 数；`find` 取 ceil |
| 噪声地板上界 floor | 1.4·√(p(1−p)·deff / (1.2·n_bars_per_fold·s_dec)) | 按每折 bar 数算（直接用合并 bar 数会低估 √折数 倍）；恰在功效线上时 floor = δ |
| 优势检查 Δ | 格首次穿越率 − Σ_s w_s·基线_s | 层 s = 同一交易日 × 当日横截面 ATR%(20) 三分位；w_s = 格内去重后定向 bar 的层占比；pattern 与基线各自按股 multinomial bootstrap（B = `b_boot`），CI = ±1.96·SE |
| 删了不亏 | est − 1.645·se ≥ −δ | 工作点「关 − 开」原始差 |
| 预期把握的窗口 SE | 训练 SE·√(训练买点事件 / 窗口买点事件) | 窗口计数来自无标签扫描；假定每个买点事件的 bar 数与训练期相同 |

## 9. 计数口径：买点事件口径

- **买点事件** = 买点 node 解析出的事件区间组（「买点」一词指 K 线根，所以单位不直接叫买点）。**买点事件键**：长表有 `seg_id`（span_key 的 int64 稳定哈希）用它；否则买点 node 是单个事件且 start / end 两列都在 → 用这两列；都不满足 → 报错（`study_io.segment_cols`）。
- **同一检测组合内，同一买点事件只计一次**；任一前缀行过该格全部闸，就算这个买点事件过闸；估计量按买点 bar 合并比例。聚合在 `region_core` 里逐分片做（组内帕累托约简 + 包含-排斥，逐位精确）；`region_core.stock_sums` 给每股 U / D / N，筛选、验证、feature-study 共用。
- **写盘时不去重**：同一买点事件各前缀行的闸字段不同，写盘去重会丢掉「任一前缀过闸」需要的信息，只能在聚合时去重。
- **逐行口径**是旧产物的计数方式：长表每行都带满额四态，同一买点事件被多个前缀共享时重复计数。
- 一致性验证与 path2_web 同口径：serialize 只给同一买点事件的第一条 match 填四态。

## 10. 输出目录布局

```
outputs/tune_gates/<app>/
├── edge/                                  优势检查(单配置扫描,只许训练期)
│   ├── bars/part-NNNN.parquet             每个 match 的每个样本 bar 一行:symbol, t, date, M, c0_atr_pct, 四态, seg_id, 闸字段
│   ├── baseline/part-NNNN.parquet         逐日基线(与 bars 同号)
│   ├── run_meta.json                      口径 + 放开值 + 指纹;与本次不同 → 拒绝续跑(restart=True 清空重扫)
│   ├── shards_committed.csv               分片提交清单
│   ├── filtered_symbols.csv / empty_symbols.csv
│   └── edge_report.md
├── <window>/                              筛选窗口或联合窗口
│   ├── longtable/part-NNNN.parquet        候选长表:symbol、检测参数列、闸字段列、bound 节点 start/end、buy_date、
│   │                                      fr、dd、fp_up/down/both/none、fold_Y、fold_6M、seg_id、M、c0_atr_pct
│   ├── longtable/run_meta.json            口径与四个指纹(单一来源)
│   ├── baseline/part-NNNN.parquet         逐日基线(完整标签模式)
│   ├── segments/part-NNNN.parquet         买点事件表(延迟标签模式):symbol, seg_id, span_key
│   ├── labels/part-NNNN.parquet           延迟标签(正式验证时现算,与 segments 同号)
│   ├── shards_committed.csv
│   ├── filtered_symbols.csv / empty_symbols.csv
│   ├── run_stats.jsonl                    每轮运行统计(只追加)
│   ├── ledger.md                          扫描台账(每次扫描覆写)
│   ├── compare_longtable.log              一致性验证日志:首行 study 与尺子指纹,结论行 mismatch=N
│   ├── screen_<工作点哈希前 8 位>/         筛选:report.md、contrasts.csv、probes.csv、fc_drafts.md、result.json
│   └── cells.npz / cells.csv / region_report.md     联合识别
└── confirm_<backward|forward>_<扫描声明哈希前 8 位>/   确认窗扫描(延迟标签模式)
    ├── longtable/ segments/ labels/ shards_committed.csv …
    └── <清单哈希前 12 位>_<backward|forward>.json      validate 结果

apps/<app>/windows/<window>/{study.py, classification.json}   窗口声明(确认窗扫描的声明同名,由系统生成)
docs/sample_usage/<app>.jsonl                                  样本使用账本
outputs/feature_study/<app>/<window>/<闸子族哈希前 12 位>/      闸子族 plan.json、verdicts.json / verdicts_<确认窗>.json
```

长表 parquet 需要 `pyarrow`；`outputs/` 在 gitignore 下，纯本地产物。

## 11. 分片提交、done 集与续跑

- **分片同号**：同一批股票在各目录（长表 / 基线 / 买点事件表；优势检查是 bars / 基线）的分片号一致。各目录分片都写完后往 `shards_committed.csv` 追加分片名，这一步才算提交（`multivar_scan.write_shard` / `commit_shard`）。
- **续跑先清孤儿**：续跑开始先删不在提交清单里的分片（`multivar_scan.drop_uncommitted`，经 `prepare_resume`），再算 done 集——否则基线片已落盘、长表片没写的那批股票会经基线进 done 集，长表行永久丢失。
- **done 集四来源**：已提交长表分片的 symbol ∪ 已提交基线分片的 symbol ∪ `filtered_symbols.csv`（空窗口 / 量能未达标）∪ `empty_symbols.csv`（进了 detector 但既无长表行也无基线行）。异常不计入 done，下次自动重试。
- **有分片却没有提交清单**：口径记录有新口径键（`label_mode`、`ruler_fingerprint`）→ 第一批提交之前被打断，判断不了完整性，只能清掉重扫；没有新口径键 → 旧格式扫描结果，不能续扫，要用只能重扫（读取仍可用）。
- **读取方不查提交清单**：region_core 分片读取、一致性验证、筛选、联合识别、feature-study 取数、定范围读优势检查样本分布都直接 glob 分片。完整性由状态推导保证：有未提交分片、已完成股票 ≠ 应扫全集、一致性验证日志没有结论行、延迟标签没补全 → 先续跑，下游不放行。只有延迟标签的两个函数（`compute_deferred_labels`、`read_with_labels`）只认已提交分片。
- **应扫全集** = run_meta 的 `ticker_regex`（缺键时退回 Settings 的 `ticker_regex` 并注明）在数据目录里命中的股票。

## 12. 标签模式与确认窗扫描

- **`label_mode="full"`**：扫描时算好 fr / dd / 四态，写逐日基线。先过确认窗守卫：没开局核对 → 原样拒绝；扫描区间（连同其后的标签窗）碰到确认窗 → 自动改走 deferred 并打印原因。
- **`label_mode="deferred"`**：只写长表（不含标签值）与 `segments/`，不算任何标签，也不写逐日基线（基线同样是标签）；不过守卫。
- **补算**：`multivar_scan.compute_deferred_labels(app, window, cfg, *, manifest_hash, confirm_window)` 先过守卫（purpose="validate"，带清单与要打开的那一段），不放行一个标签都不算；逐股按 run_meta 同口径重切窗口，对买点事件表里每个买点事件用 `path2.eval.spans_first_passage` 现算四态，写 `labels/`；已有 labels 分片的整片跳过，某片有股票失败则该片不落盘。
- **读**：`multivar_scan.read_with_labels(longtable_dir, columns)` 逐片按 (symbol, seg_id) 接上四态列；没有提交清单、同号 labels 分片缺失、任一行找不到标签 → ValueError（标签没补全就读，计数会静默偏少）。
- **确认窗扫描窗口名** = `confirm_<backward|forward>_<冻结的扫描声明哈希前 8 位>`（`tune.CONFIRM_PREFIX`）。扫描声明冻结进清单：底座、放开值同训练窗口；检测参数只扫清单各配置用到的取值；闸的档位同训练窗口（闸字段列都要在，feature-study 才能在确认窗上检闸）。`preregister` 按它装窗口声明（照抄冻结清单，不经参数准入）并做无标签扫描，数每个配置格的买点事件（换算窗口误差）；`validate` 续扫后核对冻结后检测代码与尺子没变，再补算标签、按买点事件口径汇总（整段合成一折）。

## 13. 账本记录与裁定取值

| kind | 写入方 | 烧不烧 |
|---|---|---|
| `open` | `tune.open_round`：训练窗、两段确认窗、数据起止 | 否 |
| `ruling` | `tune.record_ruling` | 否 |
| `edge` | `tune.edge` | 否，计次 |
| `select` | `tune.screen` / `tune.find` / `tune.cell`，每次调用一条（`data.tool`） | 烧涉及的轴 |
| `preregister` | `tune.preregister`（调参验证清单，带确认窗扫描声明）、`fs.plan(in_round=False)`（轮外闸清单）；确认窗守卫判「清单是否最新」只在调参验证清单之间比，轮外闸清单不挡开窗 | 否 |
| `extrapolate` | `tune.validate`，每段一条 | 该段对清单内假设用尽 |
| `decide` | `tune.adopt`（带 `selects_on` / `provisional` / `depends_on`） | — |
| `discover` | `tune.record_discovery`：研究发现、筛选草稿确认登记之后（必须关联登记条目；改闸 / 删闸定案之前必须有） | 烧该条目的轴 |
| `verify` | `fs.close` | 计次 |
| `reconcile` | `fs.reconcile` | 计次 |

「烧」= 该窗的标签（买点区间 + 其后 `label_horizon` 个交易日）参与过这条轴的假设提出、取值挑选或做不做的决定；重叠判定一律把标签后缀算进窗口。轴名：参数轴 `section.field`，不对应参数的特征 `feature:<特征名>`。

**裁定取值约定**（topic ∈ `ledger.RULING_TOPICS`）：

| topic | value | 备注 |
|---|---|---|
| `delta` | 正数，单位点 | `resolve_delta` 取最近一条 |
| `ranges` | 用户定的档位范围，本 skill 约定写 {参数键: [档位…]} | 与 `delta` 两条齐了，定范围阶段才算完成 |
| `mechanism` | 机制复核结论，本 skill 约定写 {参数键: 用户的判断} | 只在最近一次筛选之后记的才算 |
| `delete_gate` | {参数键: 关闸值}；空 dict 或 None = 决定不删 | 非空之后要在新工作点上重算筛选 |
| `adoption_rule` | 采纳规则，目前只有 `"default"` | |
| `power_notified` | 必带 `manifest_hash` | 告知预期把握之后记 |
| `open_low_power` | 必带 `manifest_hash`；本 skill 约定 value 写确认窗名 | 把握不足一半、用户同意照样打开 |
| `veto` | 整体否决；理由写 note | 与 `decide` 一样收尾一轮 |
| `expand_range` | 扩大范围重扫，本 skill 约定写 {参数键: [新档位…]} | 算又挑一次 |
