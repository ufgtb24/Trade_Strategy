# Condition_Ind 与 BO 因子框架 — 重叠/冗余精确映射

> 隶属 condition-ind-eval 团队，承接主报告 §2.1 / §2.2 / §2.4。
> 本文不重复主报告对两套架构的总体定位，只做"概念逐项对照 + 重叠是否冗余"的细颗粒分析。

---

## A. 概念层映射表

| 维度 | BO 因子框架 | Condition_Ind | 关系 |
|------|------|------|------|
| **事件 / 评估单位** | "一次突破" — `Breakout` dataclass，由 `BreakoutDetector` 在某根 K 线上触发后 enrich 出来；mining 中 `factor_analysis_data.csv` 一行=一个事件（`breakout_scorer.py:253-288`） | "一根 K 线" — `Condition_Ind` 是 backtrader Indicator，每根 bar `next()` 调用一次（`base.py:40-55`），输出的是逐根 bar 上的 `valid` line | **冲突**。BO 是事件离散化（稀疏），Condition_Ind 是 bar-stream 稠密；两者的"行"不在同一时间轴 |
| **单一原子条件** | factor — `FactorInfo` dataclass，含 key/方向/默认阈值/lookback 等元数据（`factor_registry.py:32-67`） | cond — dict `{ind, exp, must, causal}` 包裹的另一个 `Condition_Ind` 子类（`base.py:24-34`） | **互补**。BO 的 factor 是"在一个事件上算一个标量"；Condition_Ind 的 cond 是"在每根 bar 上判断一个布尔/数值"。BO factor 的"原子性"在事件粒度，Condition_Ind 的"原子性"在 bar 粒度 |
| **阈值** | 多档阈值数组 `default_thresholds=(t1,t2,t3)` + 对应乘数 `default_values=(v1,v2,v3)`，由 `BreakoutScorer._compute_factor` 映射成 level（`factor_registry.py:72-81`、scorer `_compute_factor`） | 没有显式阈值字段；阈值硬编码进每个 cond 子类（如 `Vol_cond.params.vol_threshold`、`MA_BullishAlign.min_slope_pct`），在 `__init__` 中用 backtrader 的 `bt.And/bt.If` 表达式构造布尔 line | **互补**。BO 把阈值外置（YAML 可调、Optuna 可搜索）；Condition_Ind 把阈值内置（要改阈值要改类参数或重新实例化）。这正是 BO 能跑 mining、Condition_Ind 不能的根因 |
| **时间窗口** | `lookback`（per-factor，存在 `FeatureCalculator._effective_buffer` SSOT，`features.py:107-143`）；语义是"算 factor 时回看多少根 bar 算一个标量" | `exp`（per-cond，`base.py:48`）；语义是"cond 在过去 `exp` 根内任意一根满足即视为当前仍有效"。生产代码扩展了 `keep`（连续保持）、`keep_prop`（保持比例，见 `wide_scr.py:50` 的 `keep:40, keep_prop:0.7`） | **互补但易混淆**。BO `lookback` 是"窗口内聚合一次"（标量化），Condition_Ind `exp` 是"窗口内任一帧满足即可"（OR-over-time）。前者输出标量进 mining，后者输出布尔进上层组合 |
| **触发判定** | `level > 0` 即触发；多档 level 用于乘数大小，挖掘只看 binary `triggered`（`threshold_optimizer.py:48-56`）。NaN→不触发（`build_triggered_matrix` 显式处理） | bar t 上 `last_meet_pos[i]` 距 `len(self)` ≤ `cond['exp']` → `scores[i]=1`；must 全 1 + sum(scores)≥min_score → `valid[0]=signal[0]`（`base.py:43-55`） | **互补**。BO 是"事件横截面上的多因子布尔向量"，Condition_Ind 是"一根 bar 上的多 cond 时间窗布尔向量" |
| **组合（AND/OR）** | bit-packed AND only — `triggered @ powers` 编码为整数 key，每种 key 即一个 AND 模板（`threshold_optimizer.py:82-90`）；显式 OR 不支持（隐式 OR 由"枚举多个高 median 模板"承担） | AND（must 全 True 必需）+ "至少 N 个" 软门槛（min_score）+ 嵌套（cond.ind 又是 Condition_Ind 子类）；不支持 XOR / 显式 OR | **重叠 + 互补**。两者都以 AND 为主，但 BO 是"事件级 AND-of-scalars"、Condition_Ind 是"bar 级 AND-of-temporal-windows"。Condition_Ind 的"min_score"在 BO 框架里没有等价物 |
| **评分输出** | 乘法聚合 — `total = base_score × Π factor.multiplier`（`breakout_scorer.py:276-280`）；mining 用 median(label) 作为模板优劣度 | 仅二值 `valid` line（`base.py:51-53`），不输出连续分数；上层 `SCR Analyzer` 自行决定怎么用（`wide_scr.py:94-100`） | **冲突**。BO 评分是连续乘数序列，最终给一个可比的"质量分数"；Condition_Ind 只输出布尔信号是否触发。Condition_Ind 缺一层"分数化"，因此天然不与"挖最优模板"的工作流契合 |
| **嵌套层级** | 不支持 — factor 是平的，FACTOR_REGISTRY 里 15 个 factor 全部在同一层；模板也是平的（一个模板 = AND of factors） | **支持** — `cond['ind']` 本身可以是另一个 `Condition_Ind`，例如 `wide_scr.py:48-54` 的 `flat_conv` 用 `Result_ind(conds=[ma_conv, narrow, ascend])`，再被 `vol_cond.conds[0]` 引用 | **Condition_Ind 独有**。这是它在主报告 §2.4 里被标 ✓✓ 的能力之一。BO 框架完全没有"复合谓词复用"的层级 |
| **状态持久化** | `BreakoutDetector` 维护 `active_peaks` + cache（`突破扫描模块.md:8`）；评分本身无状态 | `Condition_Ind` 维护 `last_meet_pos[i]`、`scores[i]`、状态机（如 `BreakoutPullbackEntry` 的 `state` ∈ {none, breakout, pullback, pending_stable, end}，`functional_ind.py:53-203`） | **互补**。BO 的状态在 detector 层（峰值），Condition_Ind 的状态在每个 cond 层（满足时刻 + 状态机）。Condition_Ind 内置"状态机"建模能力，BO 框架没有 |
| **流式 vs 批处理** | 增量友好（`add_bar`），但 mining 端是批处理（拿一个 CSV 跑 Optuna）；live 端 `daily_runner` 调 detector 增量 | 必须流式（backtrader 框架强制 `next()` 逐 bar 调用）；离线"重放"等价于流式跑完一遍 | **重叠**。两者本质都能流式，但 BO 框架把"事件级表达"与"流式 detector"分离开了，所以批处理评估极快（fast_evaluate ~1ms）。Condition_Ind 没分离，每次评估都要重新跑一遍 |

---

## B. 重叠点的精确分析（哪些是冗余，哪些是表面相似）

只有两处概念在表面上有重叠，逐一拆解：

### B.1 时间窗口：`lookback` vs `exp` — **不冗余**

表面看都叫"时间窗口"，但语义完全不同：

- **BO `lookback`**：在事件 t 的当下，回看 `[t-lookback, t]` 这 `lookback+1` 根 bar，**聚合**出一个标量（max / 累计涨幅 / 斜率等）。例：`pre_vol` 取窗口内最大放量倍数（`features.py:912`），**输出是单个 float**。
- **Condition_Ind `exp`**：每根 bar 上检查"过去 `exp` 根内是否有任一帧满足 cond"，**等价于 OR-over-time**。`base.py:48` 的 `len(self) - last_meet_pos[i] <= cond['exp']`。**输出是布尔**。

**能否互相表达**：
- 用 `exp` 模拟 `lookback`：可以，但只能拿到"窗口内是否触发过"的布尔信息，丢失"窗口内最强的程度"，会把 5x 放量和 10x 放量混为一类，失去 mining 的阈值梯度。
- 用 `lookback` 模拟 `exp`：可以，且更灵活 — 在 BO 框架里写一个新 factor `xxx_in_window`，内部用 `np.any(window_signal)` 即得 OR-over-time。**这是 §3.4 主报告所谓"窗口聚合因子"的本质**。

**结论**：`exp` 的功能可以被 BO 框架的"新增窗口聚合 factor"完全吸收（即主报告 Stage 2 中间形态做的事），而不是反过来。

### B.2 组合 AND：bit-packed AND vs must-全 True — **不冗余**

- BO 的 AND 在**事件横截面**上：一个事件的 N 个 factor triggered 向量做位与，编码成模板 key。**所有 factor 在同一 t 上各自是布尔判定**。
- Condition_Ind 的 AND 在**时间维**上：cond i 的"过去 `exp_i` 根内满足过"和 cond j 的"过去 `exp_j` 根内满足过"做与运算。**每个 cond 在自己的时间窗内是 OR-over-time**。

**能否互相表达**：
- BO 的事件级 AND 不能直接编码"先 X 后 Y"或"X 在过去 5 天内 + Y 在当下"这种跨时点关系（已被主报告 §2.1 列为 BO 不能做的事）。
- Condition_Ind 的"AND of OR-over-time"不能直接编码"恰好 N 次"（min_score 是 ≥ 不是 =）和"严格顺序"（exp 是无序窗口）。

**结论**：两套 AND 在不同时间维度运作，**不冗余**。Condition_Ind 的 AND 比 BO 多出"软同时性"语义；BO 的 AND 比 Condition_Ind 多出"挖出来的阈值可被 Optuna 调"。

---

## C. 各自的独有能力

### C.1 BO 框架独有（Condition_Ind 完全没有）

| 能力 | 来源 | Condition_Ind 缺什么 |
|------|------|---------|
| **bit-packed AND 模板挖掘** | `threshold_optimizer.fast_evaluate` (`threshold_optimizer.py:60-115`) — `triggered @ powers` 编码组合 key，~1ms 评估上千模板 | 没有"事件级触发矩阵"概念，无法用 bitmask 枚举组合 |
| **Optuna TPE 阈值搜索** | `pipeline.py` Step 3，连续阈值空间 + warm start | 阈值硬编码进类参数，没有"离散化输入 + 连续优化"的接口 |
| **Bootstrap CI 稳定性验证** | template_validator 五维度 + `stability = 1 - ci_width / median` | 无"评分→stat→CI"的流水线 |
| **批量打分（vector ready）** | `BreakoutScorer.get_breakout_score_breakdown` 每事件 O(N_factor) | bar-by-bar 流式，要 vectorize 得绕开 backtrader |
| **三态 unavailable 语义** | `FactorDetail.unavailable` + `Optional[float]`（`突破扫描模块.md:34-35`） | 只有 True/False/NaN，无"语义化的不可用" |
| **Per-factor lookback SSOT** | `FeatureCalculator._effective_buffer` (`features.py:107-143`) | 各 cond 自管 minperiod，无统一 buffer 派生 |
| **mining 流水线的接口契约** | `factor_diag.yaml` → `filter.yaml` → `all_factor.yaml` 三层（`数据挖掘模块.md:160-173`） | 没有"挖参数"流水线 |
| **NaN 感知** | `data_pipeline` 不 `.fillna(0)`，`build_triggered_matrix` 用 `~np.isnan(raw)` mask（`数据挖掘模块.md:130-142`） | NaN 处理散落在各 cond 子类，无统一策略 |
| **元数据驱动 UI** | `FactorInfo.description / unit / display_transform` 直接驱动 ParamEditor 与 tooltip | 无元数据层，UI 只能硬编码读取 |

### C.2 Condition_Ind 独有（BO 框架完全没有）

| 能力 | 来源 | BO 框架缺什么 |
|------|------|---------|
| **嵌套层级 / 谓词复用** | `cond.ind` 可以是另一个 `Condition_Ind`，`wide_scr.py:48-88` 的 `flat_conv` 被 `vol_cond.conds[0]` 引用 | 模板就是平的 AND-of-factors，无法把"3 个 factor 的子组合"作为单元再次组合 |
| **OR-over-time（exp 软同时性）** | `base.py:48`，`exp=20` 表示"过去 20 根内任一帧满足即视为当前仍有效" | 无原生支持，只能用"窗口聚合 factor"近似 |
| **状态机建模** | `BreakoutPullbackEntry.state` 的 5 状态机（`functional_ind.py:53-203`） | 无 — BO 检测是无状态的横截面快照 |
| **流式订阅 / live-friendly** | backtrader Indicator 天然流式，每根 bar 自动 `next()` | BO 也支持增量但是粗粒度（per-bar add，per-event score） |
| **indicator-as-first-class** | 任何指标（`MA_Slope` / `Vol_cond` / `Narrow_bandwidth`）都是 `Condition_Ind` 子类，统一接口 | factor 不是一等公民，是 dataclass + `_calculate_xxx` 方法对，没有"因子作为对象互相组合"的能力 |
| **`min_score` 软门槛** | `base.py:50` `sum(self.scores)>=self.p.min_score` | 模板 = 严格 AND，没有"满足 N 个就行"的中间形态 |
| **生产扩展属性**（`keep`、`keep_prop`、`exp_cond`、`relaxed`） | `wide_scr.py:50-53` | 无对应概念 |

---

## D. 整合可能性

### D.1 最自然的接入点 — "窗口聚合因子"的内部实现

**结论**：把 Condition_Ind 缩成 `BO factor 的内部实现选项`，而非独立架构。

理由：
1. BO 框架对外契约是"事件级标量 factor + AND 模板挖掘"，这个契约非常稳，下游（mining、scorer、UI、live）全靠它；改契约成本极高。
2. Condition_Ind 真正不可被 BO factor 表达的核心能力，只有 (a) 嵌套谓词复用 (b) OR-over-time 软同时性 (c) 状态机建模。
3. 这 3 项都可以"包"在一个 BO factor 内部 — 例如：
   - 新 factor `composite_setup`，其计算函数内部跑一个 ChainCondition 链，最终输出一个布尔（或 0/1/2 的强度等级）
   - 这个 factor 的 `lookback` 由 ChainCondition 内部 cond 的最大 `exp` 派生（注册到 `_effective_buffer`）
   - 输出仍然是 `Optional[float]`，与现有 `FactorDetail.unavailable` 三态机制无缝衔接
   - 仍然走 mining bit-packed → 仍然能被 Optuna 搜索阈值（虽然内部嵌套 cond 的常数仍硬编码，需要专门暴露才能搜）

**这等价于主报告 §4 Stage 2 的"`ChainCondition` + `post_event_lookforward` 因子"中间形态**。

### D.2 整合的最小粒度

**最小**：仅引入一个轻量级 `ChainCondition` Python class，约 80-150 行：
- 接口：`ChainCondition(conds=[(predicate_fn, window, must, mode)]).evaluate(df, idx) -> bool | float`
- 用途：让需要"软同时性 + 嵌套"的 factor 在内部调它，而不是直接搬整个 `Condition_Ind`（避免引入 backtrader 依赖）
- 对外不暴露：mining 流水线、scorer、UI 都看不到 ChainCondition，它只是某些 factor 的私有实现

**进一步收益但成本陡增的扩展**（不建议作为最小整合）：
- 把 ChainCondition 输出的"内部 cond 触发位"也暴露给 mining → 等于把 BO 模板从 "AND of N flat factors" 升级为 "AND of (N flat factors ∪ M nested cond bits)"。但这需要改 `triggered_matrix` 编码、改 `factor_diag.yaml` schema、改 `decode_templates` 输出格式 — 主报告 Stage 3 走 MR 的固定成本。

### D.3 不应整合的部分

- **不要照搬 backtrader Indicator 框架** — 它强制流式 `next()` 调用，与 BO 的"批量事件评分"工作流冲突；纯 Python class 即可。
- **不要引入 `Condition_Ind` 的 `valid` line 概念** — BO 框架是事件级离散化，不需要逐 bar 维护一条 line。

---

## 一句话总结

> BO 框架和 Condition_Ind **几乎不重叠**：前者是"事件级 AND-of-scalars + 离线 mining 流水线"，后者是"bar 级 AND-of-temporal-windows + 嵌套谓词复用"，二者在时间轴和评估单位上正交。**唯一表面重叠的"时间窗"和"AND"在语义上完全不同，不互冗余。** 整合的最优路径不是替代，而是把 Condition_Ind 的"嵌套 + 软同时性 + 状态机"能力压缩成一个轻量级 `ChainCondition`，作为某些复合 factor 的私有实现 — 这就是主报告 Stage 2 中间形态的本质。
