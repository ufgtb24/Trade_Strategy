# 当前 BO 因子架构的表达能力与边界 — 分析

> 作者：tom（pattern-arch-design 团队成员）
> 任务：评估用户提出的 4 特征走势规律在现有架构下能否表达，以及方向 B 的可达上界。

---

## 1. 当前架构的表达模型（一句话）

> **每个因子是「围绕单个 BO，时间锚定在 BO 当日（含其之前 lookback 窗口）的标量特征」；模板（template）是若干因子触发位的 AND 组合；评分时刻 = BO 当日；label 锚也在 BO 当日（向后看 `max_days` 收盘最高涨幅）。**

精确补强（来自代码）：

- **数据结构**：`Breakout` dataclass 有 13 个活跃因子标量字段（`age, test, height, peak_vol, volume, overshoot, day_str, pbm, streak, drought, pk_mom, pre_vol, ma_pos`），见 `BreakoutStrategy/factor_registry.py:70-256`。
- **评分**：`BreakoutScorer.get_breakout_score_breakdown` 为每个因子返回 `FactorDetail(triggered, level, multiplier)`，总分 = `BASE × Π multiplier`（见 `BreakoutStrategy/analysis/breakout_scorer.py:253-288`）。
- **挖掘的"模板"**：`triggered ∈ {0,1}^N` 行向量编码为 N 位整数 key，按 key groupby 算 median；template = 整数 key 对应的 N 个因子触发位 AND 子集（`BreakoutStrategy/mining/threshold_optimizer.py:28-115`）。
- **trial 物化产物**：`outputs/statistics/ddma/trials/39734/all_factor.yaml` 实例显示每个因子独立保存 `thresholds + values + mode`，没有任何字段编码"因子之间的顺序、配对、跨 BO 关系"。
- **Label**：`label = (未来 max_days 收盘最高 − BO 当日收盘) / BO 当日收盘`，BO+1 起算（`BreakoutStrategy/analysis/features.py:24-52`）。**评分时刻 = BO 当日 = 因果切面**。

---

## 2. 根本约束（按四个维度逐项拆）

### 2.1 单点 vs 多点 — 不能直接表达"BO 之间的关系"

- **单 BO 实例**：`Breakout` 是"一次突破"的 dataclass。挖掘 CSV 一行对应一次 BO（`mining/data_pipeline.py:82-112`），整个 mining 流水线在"BO 集合"上做条件统计，**两个 BO 之间的距离/价格关系不存在于行内**。
- **目前已有的两个折中**：`streak`（streak_window=20 天内 BO 数）和 `drought`（距上一次 BO 的天数）由 `detector.breakout_history` 在评分时回看产生（`analysis/breakout_detector.py:632-657`），**把"多 BO 关系"压缩成 BO 当日的标量**。这是可行的，但是是**有损投影**：
  - "两个 BO 间隔 < 30 天" → 可由 `drought ≤ 30` 近似（已在用）
  - "短期内聚集 ≥ 3 个 BO" → 可由 `streak ≥ 3 in window=N` 近似（已在用）
  - **但**："第一个 BO 与最后一个 BO 之间的价差比例"、"中间是否回踩第一个 BO 的价格"、"3 个 BO 是否价格逐级抬升" — 这些需要**对一组 BO 联合建模**，无法由单个 BO 标量表达。
- **更深的问题**：当前架构的"统计单位"是 BO；用户的规律的"统计单位"是 **BO 簇 / pattern**（multi-BO 聚类形成的事件）。两者的粒度不匹配，是根因，不是因子缺失的问题。

### 2.2 时间方向 — 不能纳入"BO 之后"的特征

- **因果切面**：评分时刻 = BO 当日；`stability_score`（向后看 5 天）和 `label`（向后看 max_days）是**特例豁免**：前者是"参考输出"未参与评分；后者是 supervisor 的训练目标，本就允许 peeking。
- **regular factor 一律不能 lookforward**。如果允许 BO 之后特征参与触发判定，意味着：
  - **label 泄露**：label 自身是"未来涨幅"，"未来 N 天稳定在更高位置"在统计上与 label 强相关，会让模板 median 虚高（典型的 target leakage）。
  - **评分时刻被破坏**：现在 BO 当日就能算 quality_score 给 dev/live UI 渲染；纳入 post-BO 特征后必须**延迟到 BO+K 天**才能定分，dev 端历史回看可以接受，但 live 端的"今天发出信号"语义就崩了。
  - **数据流改造**：scanner 现在对 `valid_end_index` 之后的数据只当 label buffer，不进行因子计算；pipeline 需要拓展为"BO 当日 enrich → BO+K 复评"的两段式。
- **单点结论**：**用户规律里的特征 4（最后一个 BO 后股价稳定在更高位置）从根本上属于 post-BO 特征**，强行塞入会破坏"评分时刻 = BO 当日"和"避免 label 泄露"两个核心不变量。

### 2.3 顺序 — 只能表达"同时成立"，不能表达"先 X 后 Y"

- 模板 = bit mask 上的 AND（`threshold_optimizer.py:60-115` 的 `combo_keys = triggered @ powers` 直接位与），**没有任何顺序语义**：`age=1 AND volume=1` 和 `volume=1 AND age=1` 是同一个 key。
- 现有所有因子都是"BO 当日(+lookback)的瞬时标量"，不存在"先发生 A 再发生 B"的概念。
- 这与 new_trade 项目的 `Condition_Ind` 链式条件（顺序匹配的有限状态机）形成对比：后者在概念上是 sequence pattern matching，前者是 conjunctive query over scalars。
- **可绕过的部分**：如果"先 X 后 Y"可以通过"在 BO 当日的回看窗口里观察到的状态变化"间接表达，可以塞成因子。例如"BO 之前 N 天 MA40 几乎水平 → BO 当日仍水平/向上"是一个可以被 ma40 曲率/水平度因子表达的瞬时投影（ma_curve 因子已经是这种思路）。但**显式的 sequence**（如"先有一个 small BO，5 天后再来一个 big BO"）不行 — 因为这要求把"上一个 BO"作为状态对象保留。

### 2.4 状态 — 部分可达（"BO 之前的状态"可以投影成因子）

- "BO 之前一段时间 MA40 水平"是**纯 pre-BO 状态**，不违反因果性，**可以**写一个 `ma40_flat` 因子：`max|MA40[t-W:t]| / MA40[t]` ≤ 阈值，或者直接复用 `ma_curve_factor`（period=40, stride=5）取低绝对值组合 `gte` → `flat`。
- 但是要注意：**ma_curve 当前的 mining_mode='gte'** 表示"曲率越大越好"（用于检测拐点反转），**与"水平"语义相反**。要支持"水平"需要新增因子（如 `ma40_flatness = -|d2/MA|`，或 `ma40_slope_abs ≤ ε`），或者把 ma_curve 改成"双向距离"的距离型因子。
- "BO 之前放量"：已有 `pre_vol` 因子（突破前 window 内最大放量倍数，`features.py:911-931`），**直接对应用户规律的特征 2**。

---

## 3. 方向 B（拆成无序因子）能走多远？

把用户的 4 条规律对照现有/可新增因子表：

| # | 用户规律 | 时间方向 | 涉及实体 | 现有架构可达性 | 折中方案 |
|---|---------|---------|---------|---------------|---------|
| 1 | 短期内聚集多个 BO | pre-BO + at-BO | 多 BO | **可近似**：`streak ≥ N`（window 内 BO 数）| 已有 streak 因子，把 streak_window 调到 30 天，挖掘 `streak ≥ 3` 的阈值 |
| 2 | 放量 | at-BO（或 pre-BO） | 单 BO | **直接可达**：`volume ≥ N×` 或 `pre_vol ≥ N×` | 已有 volume + pre_vol 双因子覆盖 |
| 3 | BO 之前 MA40 水平 | pre-BO 状态 | 单 BO 当日的窗口 | **可达（需新因子）**：`ma40_flatness` 或扩展 ma_curve 到双向 | 新增 `ma_flat` 因子：`abs(MA[t]/MA[t-W] − 1) ≤ ε`，mining_mode='lte' |
| 4 | 最后一个 BO 后股价稳定在更高位置（台阶） | **post-BO**（纯未来） | 多 BO 聚合后的"事件之后" | **不可达**（违反因果切面） | 只能：a) 把它当 label 的一部分（已经隐含在 label_5_20 里）；b) 接受延迟评分改造 |

**结论 — B 方向的边界**：

- **特征 1, 2, 3 可以在现有架构下用"无序因子 AND"表达**，且只需新增 1 个 `ma_flat` 因子。
- **特征 4 根本塞不进**，因为它是"事件之后的 post-condition"。但可以观察到一件事：**用户其实关心的是"这种 4 特征同时成立的形态最终对未来 K 天的收益有正向贡献"**。如果真是这样，**特征 4 已经被 label 隐含了**：label = 未来涨幅最高，自然偏好"事件后股价站住"的样本。换句话说，把 1+2+3 编进模板，让 mining 自己挖出"这套模板的 median label 高"，等价于在 post-BO 表现上做了筛选 — 只是没有显式约束"必须形成台阶"。
- **如果用户严格要求"事件本身定义里就包含台阶"（不仅是 label 高就行）**，那就必须改造架构：要么延迟评分（改 evaluation timing），要么让 multi-BO 簇变成 evaluation unit（改 statistical unit），方向 B 无法承载。

---

## 4. 如果硬要在现有架构里塞，会破坏哪些不变量？

| 不变量 | 描述 | 被特征 4 破坏的方式 | 影响范围 |
|-------|------|-------------------|---------|
| **评分时刻 = BO 当日** | `score_breakouts_batch` 在 `enrich_breakout` 后立即评分，BO 当日就能 emit 信号 | 引入 post-BO 因子后，必须等 BO+K 天才能给出最终 quality_score | live 端：信号延迟 K 天才能下单；dev 端：参数面板的"实时评分"语义改变 |
| **Label 因果性** | label 在 BO+1..BO+max_days 收盘最高涨幅；触发因子在 BO 之前/之时 | "BO 后股价站在台阶上" 与 "label" 都看 BO 之后窗口，存在共线 → 模板 median 虚高（leak） | mining 全流程：阈值优化挑出的"赢家模板"在样本外失效；validation 的 OOS 假阳性 |
| **统计单位 = BO** | mining CSV 一行 = 一个 BO；triggered 矩阵的行索引 = BO；template 的 count = 触发该 mask 的 BO 数 | 用户规律的事件单位 = "multi-BO 簇"，需要先聚类再评分；BO 与簇是多对一关系 | 若不改单位：把同一簇里多个 BO 重复打标会污染 count 与 median；若改单位：data_pipeline / template_generator / fast_evaluate 全要重写 |
| **Per-Factor 独立性** | `triggered_matrix` 假设每个因子独立判定，AND 才能 bit-pack | 顺序模式（"先 A 后 B"）要求因子之间存在时序依赖，违反独立性 | 模板的二值化 + bit-packed 失效，N 因子 × M 顺序 = N!/(N-K)! 组合，无法在 ~1ms 内枚举 |
| **lookback 是 SSOT** | `_effective_buffer` 强制每个因子声明自己的 lookback，scanner buffer 派生 | post-BO 因子需要 "lookforward" 的对称概念，新加 `_effective_lookforward` 才能正确 buffer label window | scanner.preprocess_dataframe 的 buffer 计算、live.daily_runner 的下载量推导都要扩展 |

---

## 5. 综合判断（给 team-lead 的建议）

1. **方向 B 在"用户规律 1+2+3"的子集上完全可行**，工作量 = 新增 1 个 `ma_flat` 因子 + 调整 streak_window + 让 mining 把这三个因子组成模板。这是最低成本路径，**适合作为基线**。

2. **但方向 B 无法表达"特征 4：事件后形成台阶"**。这是一个**架构层面的本质约束**，不是"再加一个因子"能解决的。绕过路径有两条：
   - **(a) 接受隐含表达**：相信 mining 通过 label 的 median 排序会自然偏好"BO 后站得稳"的模板。这把"形态描述"降级为"统计偏好"，可能损失精度。
   - **(b) 引入"延迟评分 + 多 BO 评估单位"**：评分单位从 BO 改成 BO 簇；评分时刻从 BO 当日改成"簇结束后 K 天"。这就是方向 A（new_trade 风格）想做的事，但代价是**整个流水线的因果切面、buffer 推导、live UI 即时性**都要重新设计。

3. **方向 A 的真正价值**不在于"能表达顺序"，而在于：
   - 把**统计单位**从 BO 提升到 multi-BO 事件
   - 把**评分时刻**从瞬时变成"事件结束后"
   - 自然支持 "pre-condition + event + post-condition" 三段式表达

   如果用户未来还会出现更多类似"事件之后"特征的规律（如"突破后回踩不破均线"、"突破后量能持续放大"），那么方向 A 的一次性投入是值得的；如果只是这一条规律，方向 B + 隐含表达就够用。

4. **方向 C 的可能形态**（未在 A/B 之列的设计）：
   - **"BO 簇" 作为一等公民**：在 BreakoutDetector 之上加一层 `BreakoutClusterDetector`（按时间近邻 + 价格邻近聚类），每个 cluster 持有起止 BO 列表 + 聚合特征（`first_bo`, `last_bo`, `bo_count`, `price_step` 等）。**因子库扩展两套**：
     - "簇内特征因子"（如 `cluster_size, cluster_density_days, cluster_price_lift`）
     - "BO 当日因子"（保留现有）
   - **评分时刻仍可保持在最后一个 BO 当日**（避免 post-BO 因果性破坏），用聚合值表达"前面发生了 N 个 BO + MA 一直水平 + 都放量" — 完全是 pre/at 时段的特征。
   - 这相当于"在 BO 之上加一层抽象 unit，但不引入 lookforward"，是 A 的弱化版（不引入顺序，但引入聚合 unit），可能是性价比更高的中间形态。

---

## 6. 关键代码引用（依据）

- 因子注册表：`BreakoutStrategy/factor_registry.py:70-256`
- 评分聚合（multiplicative）：`BreakoutStrategy/analysis/breakout_scorer.py:253-288`
- 挖掘的 bit-packed AND：`BreakoutStrategy/mining/threshold_optimizer.py:28-115`
- Label 定义（BO+1 起算）：`BreakoutStrategy/analysis/features.py:24-52`
- multi-BO 关系的折中（streak/drought）：`BreakoutStrategy/analysis/breakout_detector.py:632-657`
- per-factor lookback SSOT：`BreakoutStrategy/analysis/features.py:106-143`
- trial yaml 实例：`outputs/statistics/ddma/trials/39734/all_factor.yaml:1-137`

---

**一句话总结**：当前架构是"以 BO 为评估单位、AND of pre/at-BO scalar factors、模板 = bit mask"的 conjunctive 模型；规律 1/2/3 可以靠新增因子（特别是 `ma_flat`）落入此模型；规律 4 是 post-BO 特征，与"评分时刻 = BO 当日"和"label 因果性"两个核心不变量根本冲突，方向 B 无法表达。
