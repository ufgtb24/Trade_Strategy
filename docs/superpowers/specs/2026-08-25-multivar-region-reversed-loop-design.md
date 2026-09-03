# 多维稳健区调参工具链 · 设计 spec（v2：每股反转循环 + 候选长表 + 联合空间）

> 日期：2026-08-25 · 状态：定稿，待实施
> **本 spec 中所有项目内路径均相对 repo root。**
> 取代 `docs/superpowers/specs/2026-08-23-multivar-robust-region-design.md`（v1）。改动依据：
> - `docs/research/2026-08-24_multivar-region-review/final_report.md`（v1 识别器的六处不最优 + §五 替代设计）
> - `docs/research/2026-08-24_region-search-budget/final_report.md`（agent team 定论：§2 可扫性 / §4 推荐组合 / §5 lead 裁定 / §6.4 对拍清单 / §7 与 v1 的差异清单）+ `audit.md`（独立审核）
> - 仍沿用 v1 的部分：ATR 向量化、throwback ATR 算一次、scan 文件 per-match `buy_date`/`first_passage`、脚本无 argparse、不引入优化框架、不改 dag 引擎、不为旧 scan 兼容。
>
> 实施基线：分支 `worktree-tune-tools`（自 `tune_study` HEAD `004fa11` 建的 worktree）。本分支**与并行的 tb 简化分支只在 `path2/atoms/throwback_v1.py` 的 ATR 算一次那几行重叠**（Task 2），合并时由用户手动解决。

---

## 0. 目标与非目标

**目标**：给 tune-gates skill 增加「必须真扫参数的多维稳健区调参」环节，且预算从「每格一次全宇宙 scan」降为「每股一次反转循环」：

- `multivar_scan.py`：每只股票加载一次 → 沿 DAG 缓存上游流 → 对每个下游参数组合重跑**现成 detector** → 每格 solve → label 按 span 记忆化 → 输出**候选长表**（不是每格一份 scan JSON）。pattern 无关：只依赖 `PatternRegistry` + `eval_meta` + `Params.from_dict/to_dict` + `NodeSpec.consumes_stream` 拓扑 + `Params` 的 section 约定。
- `region_find.py`：长表 → 联合空间（真扫维 × where 可切维）→ 按 (股, 格, fold) 四态稀疏计数 → 功效线按格按 fold（不可评估 ≠ 坏）→ 相对每 fold 参照的增量 → fold 最小 → r=1 邻域最小 → 排序 → 按股 cluster bootstrap 联合重采样 + 选择后校正三口径 → 报告。
- bb_v1 端到端：6 维 × 4 档真扫（4096 格）× where 档联合空间**一次跑完（分钟级）**；3 维 80 格作与逐格 scan 的对拍基准。

**前置**（纯效率，精确）：ATR 每股一次（`calculate_atr` 向量化 + throwback 三版本算一次）、首穿尺度 M 每股一次、调参路径 `on_gate=None`。

**非目标**：
- 不引入 optuna / Ax / 任何优化或采样框架（含 LHS / GP）；不做 racing / 粗到细 / 主动水平集（研究定论：在本成本结构下失去落点，只作 §9 退路）。
- 不实现 bb_v1 专用的多值 `detect_multi`（L1c，345 ms/股）：tb_v1 正在另一分支简化重写，专用第二控制流现在写必然作废；通用路径（T1/T1+ 实测 24 / 16 min @8w）已把「两天」压到半小时以内。协议位留白（§3.4），需要时再上。
- 不改 `path2/dag/` 引擎；不改 feature-study；不重组 tune-gates reference.md 的非多维部分。
- 不为旧 scan 文件 / 旧长表做兼容（`.claude/rules/scan-file-no-backcompat.md`，长表同属一次性产物）。
- 不产出 `gate_failures`（反转循环无法把 gate 归属到档位；诊断仍走常规单格 scan）。

## 1. 术语与参数四类

| 类 | 定义 | 判据 | 工具处理 | bb_v1 实例 |
|---|---|---|---|---|
| **W 可切（where）** | 只出现在 `NodeSpec.where` 阈值里 | `W.attr(field, op, thr)` 的 thr 来自 `Params` 字段 | 扫描时放到机制下限（宽进），match 行记录该 field 原始值，region 阶段作**联合空间的免费轴**按列过滤 | `first_drought_min / distinct_pk_min / vol_spike_min / peak_age_min / max_day_drop_pct`（最后一个是 detector 内 emit 门、落 `day_drop` 列） |
| **F 过滤型** | 进 detector 构造，但只在 emit 处把关、不改产物几何 | detector 声明 `filter_params`（§3.4），或两档真扫严档事件集 ⊂ 松档且几何逐字段相等 | 按最松档跑一次，行带对应计数字段，事后按谓词切 | `burst.min_bos`（`breakout.py` 唯一消费点 = emit 判断 `k - head + 1 >= min_bos`；全宇宙 4400/1632/558 零差） |
| **S 结构型** | 改事件几何，上游流对它不变 | 进构造签名且不在 F | 上游流缓存后，每档重跑本级及下游 detector（现成 `detect`） | `burst.gap_max`、`tb.stop_confirm_bars`、`tb.big_rise_k` |
| **M 状态机型** | 改本级状态机，严档不是松档子集 | 同 S，只是本级无上游可缓存 | 每档重跑本级及其下游 | `bo.min_relative_height`、`bo.exceed_threshold` |

S 与 M 在通用工具里**处理方式相同**（都是「上游缓存、本级重跑」）；区别只在成本与 §9 退路的适用性。分类由 `multivar_scan` 打印供人核对，**不替人选维**。

其他术语：
- **格 / cell**：联合空间的一个坐标 = 真扫维取值 × where 维档位。**真扫格** = 只含真扫维（含 F）的坐标；**检测组合** = 真扫格去掉 F 维后的坐标（一次 detector 重跑对应一个检测组合）。
- **fold**：训练窗按时间切块，主口径按年（`"Y"` → `2024`、`2025`），半年（`"6M"` → `2024H1`…）只作诊断视图；match 落 fold 按 `buy_date`。
- **FP** = `up / (up + down + both)`（`none` 不进分母），按 match 计（与 `serialize` 现契约逐字一致：同 span 多 tb 各计一次）。
- **参照**：每 fold 一个 FP 参照值，默认 = **宽进底座格**（where 维全在机制下限 + 真扫维在 `REF_POINT`）在该 fold 的 FP；增量 Δ = 格 FP − 参照 FP。
- **HEAD_BUFFER**：训练窗前缓冲交易日数，**固定 250**（tune-gates 红线：eval_meta 自动值会漏算长历史依赖；OAT 底座即 250）。`multivar_scan` 与 `region_find` 共用同一常量并写进台账；**禁止**拿不同 head buffer 的 scan 文件与长表跨行比较（研究 §5.5）。

## 2. 组件与文件

| 文件 | 职责 | 动作 |
|---|---|---|
| `path2/calc/atr.py` | `calculate_atr` numpy 标量递推，逐值等价 | 修改 |
| `path2/atoms/throwback_v1.py` / `throwback_v0.py` / `throwback.py` | `detect` 入口算一次 ATR 序列下传；`_atr_at(atr, idx)` 读序列 | 修改（**与 tb 简化分支重叠点**） |
| `path2/eval.py` | `match_first_passage` / `random_day_first_passage` 增可选 `M` 入参（None 时内算，行为不变） | 修改 |
| `path2/atoms/breakout.py` | `BurstDetector.filter_params` 声明（§3.4） | 修改（1 行 + docstring） |
| `path2_web/serialize.py` | match dict 增 `buy_date` / `first_passage`（web scan 路径仍需；长表自带） | 修改 |
| `.claude/skills/tune-gates/multivar_scan.py` | 参数分类打印 → 设计展开 → 每股反转循环（ProcessPool 按股）→ 长表 parquet 分片 → 台账 | 新建 |
| `.claude/skills/tune-gates/multivar_core.py` | `multivar_scan` 的纯函数层（分类 / 设计 / 缓存键 / 单股反转 / 行构造），无 I/O，供单测与对拍脚本复用 | 新建 |
| `.claude/skills/tune-gates/region_find.py` | 长表 → 联合空间打分 → bootstrap / 校正 → 图 / 报告 | 新建 |
| `.claude/skills/tune-gates/region_core.py` | `region_find` 的纯函数层（聚合 / 可评估 / 增量 / 邻域最小 / bootstrap / 校正） | 新建 |
| `.claude/skills/tune-gates/SKILL.md` | 第 4 步「必须真扫参数的调参」改走反转循环；红线增删 | 修改 |
| `.claude/skills/tune-gates/reference.md` | 多维稳健区操作卡（端到端跑通**之后**写） | 新建 |
| `tests/path2/calc/test_atr_equivalence.py`、`tests/path2/test_eval_M_param.py`、`tests/path2/atoms/test_burst_filter_params.py`、`tests/path2_web/test_serialize_match_fp.py`、`tests/skills/test_multivar_core.py`、`tests/skills/test_multivar_equiv.py`、`tests/skills/test_region_core.py` | 见 §7 | 新建 |
| `docs/research/2026-08-25_multivar-bb_v1/` | 端到端产出（design / ledger / 长表分片路径 / 图 / `final_report.md`） | 新建 |

脚本约定：**无 argparse**，全部参数是 `main()` 起始处的大写常量；使用时复制到研究目录改常量（与 feature-study 工具一致）。纯函数层与 `main()` 分离。新增依赖：`pyarrow`（长表 parquet）。

## 3. `multivar_scan.py`

### 3.1 `main()` 常量（bb_v1 示例）

```python
PATTERN_ID = "bb_v1"
DATA_DIR = "datasets/pkls"                       # 相对 repo root(worktree 里用符号链接指向主目录数据,只读)
START_DATE, END_DATE = "2024-01-01", "2026-01-01"
HEAD_BUFFER = 250                                # ★ 与 region_find 共用;写台账
LABEL_HORIZON, FIRST_PASSAGE_K = 40, 5.0
PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
WORKERS = 8
TICKER_REGEX = None                              # 小样本验证时填子集正则
REF_PARAMS = "docs/research/2026-08-25_multivar-bb_v1/ref_params.json"   # 参照底座 = OAT 底座的 params_snapshot(tb: max_window 20 / judged low / rising;bo: total_window 20 / min_side_bars 6 …),不是 Params.default()
WIDE_OVERRIDES = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
                  "tb": {"max_day_drop_pct": None}}          # where 维放到机制下限
SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3],      # 真扫维(S/M/F 都在这里,工具自己分类)
             ("bo", "exceed_threshold"):    [0.001, 0.003, 0.01, 0.03],
             ("burst", "gap_max"):          [4, 8, 12, 20],
             ("burst", "min_bos"):          [1, 2, 3, 4],
             ("tb", "stop_confirm_bars"):   [0, 1, 2, 3],
             ("tb", "big_rise_k"):          [3.0, 5.0, 8.0, 12.0]}
WHERE_FIELDS = {("burst", "first_drought_min"): ("burst", "first_drought", ">="),   # where 维 → (node, 事件字段, op)
                ("burst", "distinct_pk_min"):   ("burst", "distinct_pk", ">="),
                ("burst", "vol_spike_min"):     ("burst", "max_bar_vol_ratio", ">="),
                ("burst", "peak_age_min"):      ("burst", "peak_age_max", ">="),
                ("tb", "max_day_drop_pct"):     ("tb", "day_drop", "<")}   # 毒药闸:day_drop 列由 tb 事件字段供给(见 3.3)
OUT_DIR = "docs/research/2026-08-25_multivar-bb_v1/"
SHARD_STOCKS = 200                               # 每 N 股落一个 parquet 分片(crash 安全 + 断点续跑按股)
```

`WHERE_FIELDS` 由工具从 `build_pattern(Params.default())` 的 `where` 元组自动推导（`W.attr(field, op, thr)` 的 thr 与 `Params` 字段值匹配）并打印；`main()` 里的显式表用于核对与覆盖（自动推导失败的项必须手写）。

### 3.2 行为

1. **加载与分类**：`PatternRegistry().get(PATTERN_ID)`；`Params = mod.Params`、`eval_meta = mod.eval_meta`、`build_pattern = mod.build_pattern`。对 `build_pattern(Params.default())` 的每个 `NodeSpec`：`inspect.signature(type(node.detector).__init__)` 的参数名 ↔ `Params` section 字段名匹配 → 真扫候选；`where` 阈值来源字段 → W；`getattr(type(node.detector), "filter_params", {})` → F。打印分类表（section.field → W/F/S·M/未知）。`SCAN_GRID` 里出现 W 类字段 → 报错退出（where 维不进真扫）。
2. **拓扑与缓存键**：`detector_topo_order(spec.nodes)`；节点 n 的**缓存键** = `(n.node_id, 影响 n 的 section 取值)`，影响集 = n 及其 `consumes_stream` 链上全部上游节点对应的 section 在 `SCAN_GRID` 里的维（section ↔ node 映射由 `Params.<x>_kwargs()` 或字段名匹配得到；bb_v1：bo←bo、burst←bo+burst、tb←bo+burst+tb）。F 维不进缓存键（按最松档跑）。
3. **每股 worker**（模块级函数，ProcessPool pickle 安全，骨架照抄 `_scan_ticker_multi`）：
   - `read_pickle` → `slice_window(buf_start, buf_end)`（`buf_start` 由 `HEAD_BUFFER × TRADING_TO_CALENDAR_RATIO` 得，同 `run_scan_multi`）→ volume 预筛（同 `_scan_ticker_multi` 口径）→ `lo/hi` 样本消费窗 → 每股一次：`M = rolling_atr_pct_nanmedian(...)`、随机日基线 `random_day_first_passage(..., M=M)`。
   - `config.set_runtime_checks(True)`（与 scan 同路径）；`on_gate` 不挂。
   - 枚举检测组合（`SCAN_GRID` 去掉 F 维的笛卡尔积），按拓扑序逐节点：若缓存键已存在则复用流，否则 `p = Params.from_dict(snap ∘ WIDE_OVERRIDES ∘ 组合取值)` → `spec = build_pattern(p)` → `events = list(run(node.detector, [上游流], win))` → `annotate_stream(counts, nid, events, children_of)`（`counts` 每个检测组合新建；已标注的上游流会被 `annotate_stream` 跳过，与 `stream_replay_equiv.py` 同路径）。F 维所在节点按最松档构造。
   - 对每个检测组合：`plan = compile_plan(spec)`（spec 里 where 已是宽进值）→ `sols = solve(plan, streams)` → `reify` → 每个 match：解析 `end_node` 事件（`_resolve_end_events`）；价格过滤与样本窗过滤同 `serialize_per_pattern_result`；label 按 `(end_node span 元组)` 记忆化：`match_forward_returns` / `match_forward_drawdowns` / `match_first_passage(..., M=M)`；**FP 按 match 计**（每行一份四态，label 只复用值）。
   - **行**：`symbol` + 检测组合各维取值 + F 维对应计数字段（如 `burst.count`）+ 每个 W 维的事件字段原始值（按 `WHERE_FIELDS` 从 `match.node_index[node]` 取）+ `buy_date` + `fr` + `dd` + `fp_up/fp_down/fp_both/fp_none` + `end_start_idx/end_end_idx`（对拍键）。
   - 返回 `(symbol, rows, random_fp, err)`。
4. **主进程**：`ProcessPoolExecutor(WORKERS)` 按股 `as_completed`；每 `SHARD_STOCKS` 股写一个 `OUT_DIR/longtable/part-<k>.parquet`（pyarrow）；`OUT_DIR/random_baseline.csv`（symbol × 四态）；**断点续跑按股**：启动时读已有分片的 `symbol` 集合，跳过。进度打印同 `run_scan_multi` 风格。
5. **台账** `OUT_DIR/ledger.md`：pattern、窗、HEAD_BUFFER、过滤、宽进覆盖、SCAN_GRID / WHERE_FIELDS、分类表、股数（总 / 进 detector / 有 match）、总行数、耗时（wall 与 CPU·s）、每股 p50/p90 ms、每检测组合平均 solve ms。
6. 结束打印：各真扫格（不含 where 维）在各 fold 的 count 分布（min / median / max），供校验功效线是否可达。

### 3.3 where 维作免费轴的成立条件（工具强制检查）

把 where 当长表列谓词与引擎施加 where 等价的条件：where 只读单实例自身属性（既有纪律），且 where 所在节点**不是任何 `NegationEdge` 的目标**（否则收紧 where 减少被否定事件、可能**增加** match，谓词过滤方向错）。`multivar_scan` 启动时检查 `spec.edges`，违反则报错并要求把该 where 维改为真扫维。bb_v1 无 negation 边。

`max_day_drop_pct` 特例：它是 tb detector 内的 emit 门（不是 `NodeSpec.where`），宽进 `None` 时 tb 事件需带 `day_drop` 字段供事后切——研究已实证（`_revert_max_day_drop` 精确复算，E4b）。本 spec 要求 tb 事件在 `max_day_drop_pct=None` 时仍计算并落 `day_drop` 字段（若当前事件无此字段，在 Task 2 的同一处补：只加字段、不改判据；tb 简化分支若已把它改成 where，则本条自动退化为普通 W）。

### 3.4 `filter_params` 协议（可选，小改）

```python
class BurstDetector:
    # 过滤型构造参数声明:param → (事件字段, op)。语义:构造时取该参数最松值,事后按
    # `getattr(event, field) op value` 过滤,与直接以 value 构造得到的事件集**逐事件相等**
    # (含几何与全部字段)。声明者对等价性负责(测试 tests/path2/atoms/test_burst_filter_params.py)。
    filter_params: ClassVar[dict[str, tuple[str, str]]] = {"min_bos": ("count", ">=")}
```

工具遇到 `SCAN_GRID` 里的维属于某 detector 的 `filter_params` → F 类：该维不进检测组合，按 `min(levels)` 构造，行带该字段，region 阶段按谓词归属。无声明的构造参数一律按 S/M 处理（保守、精确）。**`detect_multi` 不在本 spec 范围**（见 §0）。

### 3.5 精确性声明与已知不等价点

等价键 = `(symbol, 各节点 span, outcome, fr, dd, 四态)` + 每股按格 `match_fp_counts`；`instance_id` 的 `#idx` 与 `match_id` 不保证逐字（`annotate_stream` 桶内流序编号）。已知：bo 有状态 → HEAD_BUFFER 跨格恒定（若 `atr_window`/`total_window` 进网格，用网格内 max 作统一缓冲，此时与「每格各自 eval_meta」不逐字等价，且反转口径才是想要的口径）；`k` 与 `atr_window` 共线（同时进网格是脊不是盒，选维二选一）；`first_drought_min ≤ gap_max` 的格该闸恒真（region 报告标记）。

## 4. `region_find.py`

### 4.1 `main()` 常量

```python
LONGTABLE_DIR = "docs/research/2026-08-25_multivar-bb_v1/longtable/"
HEAD_BUFFER = 250                                  # ★ 必须与 multivar_scan 一致(从 ledger 读出核对,不一致直接退出)
SCAN_DIMS = [("bo","min_relative_height"), ("bo","exceed_threshold"), ("burst","gap_max"),
             ("burst","min_bos"), ("tb","stop_confirm_bars"), ("tb","big_rise_k")]   # 轴序
WHERE_LEVELS = {("burst","first_drought_min"): [0, 20, 40],           # where 维档位(联合空间免费轴,研究者声明、写台账)
                ("burst","distinct_pk_min"):   [1, 3, 4],
                ("burst","vol_spike_min"):     [0, 10, 15],
                ("burst","peak_age_min"):      [0, 125],
                ("tb","max_day_drop_pct"):     [None, 0.2]}
FOLD = "Y"                                         # 主口径按年;"6M" 诊断视图同时出
FOLDS = ["2024", "2025"]                           # 参与 min 的 fold
MIN_COUNT_PER_FOLD = 100                           # 功效线(按格按 fold);不达标 → 该格「不可评估」
REF_POINT = {("bo","min_relative_height"): 0.2, ("bo","exceed_threshold"): 0.003, ("burst","gap_max"): 8,
             ("burst","min_bos"): 1, ("tb","stop_confirm_bars"): 2, ("tb","big_rise_k"): 5.0}   # 参照 = 此真扫格 × where 全机制下限
NEIGHBOR_AXES = "all"                              # r=1 邻域取哪些轴:"all"(含 where 轴)| SCAN_DIMS 子集
B_BOOT, SEED = 300, 0
TOP_N = 20                                         # 报告前 N 格(按邻域最小分)
FLAG_RULES = [lambda c: "first_drought 闸恒真" if c[("burst","gap_max")] >= c[("burst","first_drought_min")] else None]  # pattern 特异标记,可空
OUT_DIR = 同 LONGTABLE_DIR 的父目录
```

### 4.2 算法

1. **读长表**（全部分片）+ `ledger.md` 的 HEAD_BUFFER 核对。`buy_date` → fold（`"Y"` 与 `"6M"` 各一列）。
2. **格归属**：联合空间 = `SCAN_DIMS` 各维档位 × `WHERE_LEVELS` 各维档位。F 维与 where 维按谓词：行属于格 c ⟺ 检测组合坐标相等 ∧ `count ≥ c.min_bos` ∧ 每个 where 维 `field op level`（`None` 档 = 不过滤）。实现为向量化：先按检测组合分组，组内对每个 (F 档 × where 档) 组合用布尔掩码累计四态与 fr。
3. **计数矩阵**：`(symbol, cell, fold)` → `(up, down, both, none, n_match, fr 列表或分位统计)`；这是 bootstrap 的唯一输入（不在原始行上重采样）。
4. **可评估**：每 (cell, fold)：`count = up+down+both+none`（按 match 计，与 tune-gates 功效线口径一致）；`count < MIN_COUNT_PER_FOLD` → 该 (cell, fold) 不可评估；任一 `FOLDS` 中的 fold 不可评估 → 该 cell **不可评估**（与「坏」分开计数）。
   > **勘误**（复审挂账 #9）：上句括注「按 match 计」是错的——实现按 §3.2「按行结构累加」执行，`count` 实卡的是买点日样本数（一个 match 跨 N 个买点日贡献 N 个首穿样本），本轮实测约为 match 数的 2.5~4 倍，且方向不保守（同一 span 内买点日强相关，不是独立观测）。本 spec 是权威定义，此处以代码实现为准；详见 `.claude/skills/tune-gates/reference.md` §8 坑 8。
5. **参照与增量**：参照格 = `REF_POINT` × where 全机制下限（每维取 `WHERE_LEVELS` 里最松档）；每 fold `Δ_f(c) = FP_f(c) − FP_f(ref)`；`s(c) = min_f Δ_f(c)`（只对可评估格）。同时保留绝对 `FP_f(c)`、`fr_median_f(c)`。
6. **邻域最小**：`s_nb(c) = min(s(c'))` over `c' ∈ N_r=1(c) ∪ {c}` 且 `c'` 可评估；`N_r=1` = 每次只在一个轴上移一档（曼哈顿距离 1），轴集 = `NEIGHBOR_AXES`；**网格边界外不存在邻居（机制边界不计边界，无 pad）**；报告 `n_eval_nb(c)`。`c` 自身不可评估 → `s_nb` 缺失。
7. **排序与推荐**：按 `s_nb` 降序，并列取 `n_eval_nb` 大者、再取离网格边界远者；推荐格 ĉ = 第一名。各维容错宽度 = 从 ĉ 沿该轴两侧连续 `s_nb > 0` 的档数。
8. **按股 cluster bootstrap**（B_BOOT 次，`SEED`）：每次以 multinomial 权重重抽 symbol → 用第 3 步矩阵按权重重算 FP → 重算 4-7 → 得 `ĉ_b`、`s_nb,b(·)`。输出：`P(ĉ_b ∈ N(ĉ) ∪ {ĉ})`（选中格稳定性）、`s_nb(ĉ)` 的百分位 CI、每格入选前 TOP_N 的频率。
9. **选择后校正三口径**（研究 §4.5 已在合成数据上校准，真实数据上三值并报、不折中）：
   - naive = `s_nb(ĉ)`；
   - optimism 校正 = naive − mean_b[`s_nb,b(ĉ_b)` − `s_nb(ĉ_b)`]（副本内 argmax 回原数据的抬高量）；
   - split-half = 按 symbol 哈希奇偶分半：一半选 ĉ_A、另一半评 `s_nb`；互换取平均。
   报告口径：optimism 校正当上界、split-half 当下界；**唯一无偏数字是同 HEAD_BUFFER 的 2026 外推窗**（外推验证不在本工具内，沿用 tune-gates 现流程）。
10. **标记**：`FLAG_RULES` 逐格求值（恒真闸等）；脊型（共线维）由研究者在选维时排除，报告只提醒。
11. **图**（matplotlib PNG）：① 每个轴过 ĉ 的一维切片（x=档位；y=`s_nb`、`s`、各 fold Δ；不可评估档画空心点）；② 每对 `SCAN_DIMS` 过 ĉ 的二维热力图（`s_nb`，不可评估格灰色、标 ĉ）；③ bootstrap 入选频率前 TOP_N 条形图。
12. **`region_report.md`**：设计与台账摘要（含 HEAD_BUFFER）、联合空间规模、可评估 / 不可评估 / 负分格计数、参照格各 fold count 与 FP、前 TOP_N 表（坐标 / 各 fold count·FP·Δ / `s` / `s_nb` / `n_eval_nb` / 标记 / bootstrap 入选频率）、推荐格与容错宽度、三口径校正值 + 稳定性、「可评估面」描述（哪些轴哪一侧可评估）、下一步：同 HEAD_BUFFER 的 2026 外推窗独立验证。**不做** permutation、τ 灵敏度、中心重跑。
13. 同时输出 `cells.csv`（每格一行，含全部数值）与 `folds_6M.csv`（半年诊断视图的 count/FP）。

## 5. 与 tune-gates 现流程的接口

- SKILL.md 第 4 步「必须真扫参数的调参」：由「围绕当前值 3-5 档、每档一次全宇宙 scan、OAT」改为「`multivar_scan` 一次反转循环出全网格 × where 联合空间 → `region_find`」；OAT 降级为选维线索与复核视图；`plateau.py` 继续服务单闸视图（可从 `cells.csv` 沿一维切片喂）。
- 红线增删（§8）。
- 可切闸的宽进扫描底座（第 2 步）不变；长表可作 feature-study 的候选来源（与 feature-study 的分界不变：本工具不做特征筛选）。

## 6. 端到端（bb_v1）

1. **对拍基准（§6.4 第 1、5 条）**：`TICKER_REGEX` 取跨字母随机 ≥ 500 股（如 `^[A-Z][A-C]`）；(a) 3 维 80 格（`stop_confirm_bars × min_bos × gap_max`，bo 单档）：长表按格聚合 vs 逐格 `engine.analyze` + `serialize_per_pattern_result`，键 `(symbol, 各节点 span, fr, 四态)` + 每股 `match_fp_counts`，**mismatch = 0**；(b) 6 维随机 64 格 + 全部角点同上；(c) 收紧 where 两套（FINAL：fd20/dpk4/vsp15/dpct0.2；B：fd20/dpk3/vsp10/dpct0.2；peak_age_min 均 0，与 OAT 底座一致）下同上（where 由引擎施加 vs 长表谓词）。
2. **fold 计数对拍（§5.3 表的口径核对）**：全宇宙长表在参照格 × FINAL where / × B where 的年折 count，必须与**当前代码用 `run_scan_multi` 在同一参数、同一 HEAD_BUFFER=250 窗口下新扫一次**得到的年折 count **逐 fold 相等**（这是同代码对拍，差异 > 0 = 口径未对齐、停下查）；同时把两者与研究 §5.3 表的 73/92（FINAL）、164/172（B）并排列出——那两组数来自 OAT 文件事后套 where，代码版本不同，允许小幅偏差，只作参考不作验收。
3. **全网格**：6 维 4096 × where 档联合空间全宇宙一次跑完；记录 wall / CPU·s（预期 T1+ ≈ 16 min @8w；不设硬阈值但 > 1 h 需解释）。
4. `region_find` → `region_report.md`；结果进 `docs/research/2026-08-25_multivar-bb_v1/final_report.md`（诚实预期：FINAL where 切片在参照格附近不可评估、gap_max ≥ 12 或 K ≤ 1 一侧可评估；B where 大部分可评估；是否有正 `s_nb` 的区域由数据说话）。
5. 之后才写 `reference.md`。

## 7. 测试

| 测试 | 内容 |
|---|---|
| `tests/path2/calc/test_atr_equivalence.py` | 新旧 `calculate_atr` 逐值 `atol=1e-12`（真实 pkl ≥3 只 × period 14/20；`len<period`；含 NaN 段）；数据缺失 skip |
| `tests/path2/test_eval_M_param.py` | `match_first_passage(..., M=预算)` 与不传 M 逐值相等；`random_day_first_passage` 同 |
| `tests/path2/atoms/test_burst_filter_params.py` | 合成 bo 流：`BurstDetector(min_bos=1)` 输出按 `count ≥ m` 过滤 == `BurstDetector(min_bos=m)` 输出，逐事件全字段相等（m∈{2,3,4}，gap_max 两档） |
| `tests/path2_web/test_serialize_match_fp.py` | 非 None `first_passage` 四态求和 == `match_fp_counts`；`first_passage_enabled=False` 恒 None；`buy_date` = end_node 起始日 |
| `tests/skills/test_multivar_core.py` | 分类（W/F/S·M）对 bb_v1 spec 的输出与 §1 表一致；where 维进 SCAN_GRID 报错；negation 目标节点的 where 维报错（合成 spec）；缓存键的影响集（bb_v1：bo←{bo}、burst←{bo,burst}、tb←{bo,burst,tb}）；设计展开的检测组合数（F 维不计）；label 记忆化命中 |
| `tests/skills/test_multivar_equiv.py` | 真实数据（缺失 skip）：`^A[A-C]`，随机 8 格 + 4 角点 + 一套收紧 where，单股反转函数输出 vs 逐格 `analyze`+`serialize` 键集相等、`match_fp_counts` 相等（固化 `repro/stream_replay_equiv.py` 思路） |
| `tests/skills/test_region_core.py` | 合成长表：(a) 已知平台（某 2 维子空间 Δ=+0.03、其余 0）+ 按股噪声 → ĉ 落在平台内、容错宽度 ≥ 平台宽度−1；(b) 全 null → bootstrap 稳定性 < 0.5 且 optimism 校正后 ≤ naive；(c) 功效线：人为把某 fold 某格 count 压到 50 → 该格「不可评估」且不作邻居；(d) 邻域最小：尖峰格（自身 +0.05、邻居 −0.02）`s_nb` = −0.02；(e) 边界格邻居数正确（无 pad）；(f) where 谓词归属与 F 谓词归属对手算样例逐格相等 |
| `multivar_scan` 冒烟 | `TICKER_REGEX="^A[A-C]"`、2×2 真扫 + 1 个 where 维 2 档 → 分片 / ledger 形状正确；第二次运行全部跳过（断点续跑） |

## 8. SKILL.md 红线改动

删除（v1 拟加、未落地）：「permutation p < 0.05 才能声称有区域」「推荐 center 必须真跑一次全量 scan」「≥5 维用 LHS」。

新增 / 改写：
- 必须真扫参数多维调参**不优化单点、不取 argmax**：推荐 = r=1 邻域最小分最高的格，容错以「邻域分仍为正的跨度」报告。
- 区域分析在**联合空间**（真扫维 × where 可切维）上做，**禁止**「宽进态找区、事后单独收紧」的两段式。
- 功效线**按格按 fold**，不达标标「不可评估」（≠ 坏、不作邻居），报计数不报比例；主口径年折。
- 增量相对**每 fold 参照**，不用绝对 τ。
- 检验 = **按股 cluster bootstrap 联合重采样**（稳定性 + CI）+ **选择后校正三口径并报**；唯一无偏数字是同 HEAD_BUFFER 的外推窗。
- **长表与逐格 analyze 的抽样对拍通过后才能读 region**（取代「中心真跑」）。
- **fold 计数 / 功效线 / 参照增量必须与网格同 HEAD_BUFFER**；不同缓冲的 scan 文件不得跨行比较。
- 不引入优化 / 采样框架；结构性省不可用（detector 全状态机、上游对下游不独立）时才走 §9 退路。
- 反转路径不产出 `gate_failures`，诊断走单格 scan。

## 9. 退路（结构性省不可用时，不在本 plan 实施）

各真扫维取 2 档跑 2^m 全因子（精确、无混杂；不用分数因子）→ 维度等价检验坍缩「随便取」的维 → 保留维补档；仅单次 scan ≥ 266 s 且补档 ≥ 3 时叠 level_comp racing。见研究 §4.4。

## 10. 风险

- **tb 简化分支并行**：本分支的 `throwback_v1.py` 改动只有 ATR 算一次 + `day_drop` 字段；简化分支落地后 bb_v1 事件集改变，本分支端到端产出的 region 结果作废、需重跑（工具本身不受影响——pattern 无关是设计目标，这正是验收点之一）。
- ATR 修复触及 `platform.py` 共用函数——等价测试兜底。
- 长表体积：全宇宙 6 维 ≈ 17.9M 行 ≈ 0.5 GB parquet；`region_find` 先聚成计数矩阵再算，不在原始行上 bootstrap。
- 多重性：4096 × where 档的联合空间里 argmax 抬高 +1～2.5 pt（合成数据下界）；三口径并报 + 外推窗兜底，报告不得只报 naive。
- 功效：收紧 where 下年折 count 可能低于 100 → 标不可评估，**不降功效线硬凑**。
- bb_v1 已判无 edge（bo_only ≈ 随机基线）：端到端可能给出「可评估面上无正 `s_nb` 区域」——这是方法的诚实读数，验收看管线、对拍与报告完整性。
