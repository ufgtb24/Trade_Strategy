# 替代 Pattern 架构调研

> 立题：BO 因子框架（A 方案）与 `Condition_Ind` 链式条件（B 方案）能否被某种第三类架构显著超越？目标规律由四要素组成：
>
> 1. **Multi-BO**：短期内聚集多个 breakout（事件聚类）
> 2. **放量**：聚集事件伴随成交量放大
> 3. **事件前 MA40 几乎水平**：状态前提
> 4. **事件后台阶**：最后一个 BO 之后股价稳定在更高水位（事件**后**的非因果验证）
>
> 这四要素同时跨越「事件 / 时间 / 顺序 / 状态」四个维度，且第 4 条引入**事后窗口**（pattern 的判定锚点不在最后一个事件 bar，而是其后 N 根 bar）。

调研基于 `context7` 的 Apache Flink 1.19 与 hmmlearn 文档实证；其他方向 (STL、SAX、SPADE) 走概念性评估。

---

## 0. 基线复盘：A 方案 vs B 方案

### A 方案（当前 BO 因子 + 模板挖掘）
- **抽象**：把每个 BO 当成独立样本，所有特征是「BO 之前 / 之时」的标量；模板 = 多个标量阈值的 AND 组合；OOS 评分 = 命中样本 label 的中位数。
- **优点**：与挖掘流水线（`mining/`）天然契合 — bit-packed 触发矩阵 + Optuna TPE + Bootstrap CI（详见 `.claude/docs/modules/数据挖掘模块.md`）。
- **痛点**：
  - 无显式「事件序列」概念。Multi-BO 必须降维为「最近 N 天 BO 数」这种标量因子，损失顺序与时间间隔信息。
  - 第 4 条「台阶」是**事后**（look-ahead）信号，会与 `label` 抢同一段未来数据，因此**不能写成 BO 触发因子**，只能在 mining 阶段当作额外验证（容易被遗忘）。
  - MA40 水平是状态前提，但 BO 因子天然是「BO 那一刻」的快照，描述「过去 X 天斜率 ≈ 0」需要每个状态都派生标量因子，组合维度膨胀。

### B 方案（`Condition_Ind` 链式 indicator）
- **本质**（确认自 `screener/state_inds/base.py`）：每个子条件是带 `valid` line 的 indicator；外层 `Condition_Ind.next()` 检查每个子条件是否在过去 `exp` 根 bar 内为真（`last_meet_pos`），并按 `must`（必选）/`min_score`（择优）聚合。`causal=True` 时只用 `valid[-1]`，避免未来泄漏。
- **优点**：
  - 一阶引入了「时间窗口」语义（`exp`），这是 A 方案没有的。
  - indicator 可任意嵌套，写出「过去 X 天满足 cond1，且最近 Y 天内 cond2 触发」之类的复合判据。
- **痛点**：
  - **无序列约束**：`exp` 只表达「曾在窗口内为真」，**无法表达「先 A 再 B」**。Multi-BO 的事件聚类、台阶之类的强顺序约束写不出来。
  - 没有 quantifier（不能直接说「至少 3 次 BO」），需要用 `Duration` 之类指标的副作用近似。
  - 与挖掘流水线脱钩：每个 indicator 是命令式 Python，不能像 BO 因子那样被 bit-packed 矩阵评估。
  - 状态分散在多个 indicator 的实例字段里，不易做组合枚举。

A 与 B 处于不同 trade-off 上：A 重「批量挖掘 + 标量阈值」，B 重「时间窗口 + 流式判据」。两者都未直接命中目标规律所需的 *event sequence + temporal quantifier + post-event window* 的组合表达力。

---

## 1. CEP — Complex Event Processing（Flink CEP / Esper EPL / Siddhi）

### 模型本质
事件流上的 NFA（非确定有限自动机）。模式由命名 condition + 序列连接子（strict / relaxed contiguity）+ quantifier + within 时间窗组成；引擎在线匹配并发射结果。

### 表达用户的四要素（Flink CEP，Java 风格示意，本身可在 Python 项目中借鉴 API 设计）
```java
Pattern.<Bar>begin("flat_ma40")
    .where(b -> b.maSlope40Abs() < eps)            // 条件 3: MA40 水平（前置状态）
.next("bo_cluster")                                // strict contiguity → relaxed via followedByAny
    .where(b -> b.isBO() && b.volRatio() > 1.5)    // 条件 1+2: 放量 BO
    .timesOrMore(2, Duration.ofDays(15))           // quantifier: 15 天内 ≥ 2 次
.followedBy("step_up")
    .where(b -> b.closeMin().minOver(10) > b.preBOResistance())  // 条件 4: 后续 N 天台阶
    .within(Duration.ofDays(20));
```
关键事实出处：
- `times(int from, int to, Duration windowTime)`、`timesOrMore`、`oneOrMore` 等 quantifier API（Flink 1.19 docs `cep` 页）。
- strict（`next`）/ relaxed（`followedBy`）/ non-deterministic relaxed（`followedByAny`）三档连接子（同一来源）。
- `within(Time.seconds(10))` 整体时间窗（同一来源）。

`Condition_Ind` 的 `exp + must` 大致等价于 CEP 的 *within + must-match*，但 CEP 多出了 quantifier、connector 类型、方向（顺序）三件套。

### 优势
- 一类完整覆盖事件 + 时间 + 顺序的代数结构，几乎 1:1 命中目标规律的描述。
- 文献（金融领域多年使用 EPL 写技术形态）证明语言层面对「先 A 再 B 再 C」表达自然。
- pattern 是「文本级 DSL」，可被参数化生成 → 跟 mining 衔接的入口存在（穷举 quantifier 上下界、within 上下界、condition 阈值）。

### 代价
- Flink CEP / Esper / Siddhi 都是 JVM 系。生态成本高于现有纯 Python 栈。
- 「事件后窗口」（条件 4）需要把 `step_up` 也建模为事件并放进序列里，其谓词依赖未来 bar 的聚合（MIN over next 10 bars） — 这在流式模型里要么用「延迟匹配」，要么把判定锚点后移 N 根 bar。Flink CEP 的 `within` 可控总跨度，但**事后聚合谓词**仍需要在 MEASURES 里手写。
- 与现有 bit-packed 评估完全不兼容：CEP 是 NFA 状态机，挖掘要换成「pattern 模板生成 + 事件流回放」的两阶段，吞吐显著下降。
- 引擎厂商绑定：Flink CEP 的 `Pattern` API、Esper 的 EPL、Siddhi 的 SQL-like 语法不互通。

### 关键限制
- NFA 在 quantifier + relaxed contiguity 组合下可能爆出指数级状态数（Flink 文档明确警告 `PATTERN (A B+ C)` 若 B 没界限会内存炸裂）。
- 「负向条件」（pattern 中**不能**出现 X）在 CEP 里 awkward，需要 `notFollowedBy`，并不所有引擎都支持。

---

## 2. 正则化事件序列匹配 — `MATCH_RECOGNIZE`（SQL:2016）/ SASE+

### 模型本质
SQL:2016 标准子句，把「行流」当字符串，pattern 写成正则（`A B+ C{1,5} D?`），DEFINE 段定义每个 pattern variable 的谓词，MEASURES 段抽取每次匹配的衍生量。Oracle / Trino / Flink SQL / Snowflake 全部实现。

### 表达用户的四要素（Flink SQL 风格）
```sql
SELECT *
FROM Bars
MATCH_RECOGNIZE (
  PARTITION BY symbol
  ORDER BY ts
  MEASURES
    FIRST(BO.ts) AS first_bo_ts,
    LAST(BO.ts)  AS last_bo_ts,
    COUNT(BO.*)  AS bo_count,
    AVG(STEP.close) AS step_avg_close,
    LAST(BO.resistance) AS bo_resistance
  ONE ROW PER MATCH
  AFTER MATCH SKIP PAST LAST ROW
  PATTERN (FLAT{5,} (BO ANY*?){2,5} STEP{10,})       -- 5+ 根水平 MA → 2~5 个 BO（中间允许任意） → 10+ 根台阶
  DEFINE
    FLAT AS ABS(FLAT.ma40_slope) < 0.0005,
    BO   AS BO.is_bo = TRUE AND BO.vol_ratio > 1.5,
    STEP AS STEP.low > LAST(BO.resistance)            -- 事后判定
);
```
关键事实出处（Flink 1.19 docs `match_recognize` 页）：
- `PATTERN (A B+ C* D)` 等正则风格语法、quantifier `*`、`+`、`?`、`{n,m}`。
- `MEASURES` 中 `FIRST` / `LAST` / `AVG` 与 `LAST(B.price, 1)` 这种带偏移的逻辑访问 — 可以实现「上一个匹配 row 的属性」。
- `ONE ROW PER MATCH` + `AFTER MATCH SKIP PAST LAST ROW` 控制重叠匹配。
- 官方明确给出「连续下跌 + 反弹」（V 型）金融示例（query：partition by symbol, pattern `(START_ROW PRICE_DOWN+ PRICE_UP)`），证明此结构在金融领域成熟。

### 优势（vs CEP API）
- **声明式 SQL**，对挖掘最友好：模式中所有 quantifier 上下界、DEFINE 中阈值都是字面量，可被自动模板化和搜索。
- 与 Flink CEP 在引擎层共享 NFA，但表达层是 SQL — 把它**当作 DSL 借鉴**比直接上 Flink 更现实（参考实现：自己写一个轻量解析器 + 在 pandas 上回放，pattern 数量不大时性能足够）。
- `MEASURES` 段天然提供「事后聚合」入口（`AVG(STEP.close)` 等），把第 4 条台阶直接写进 DEFINE 而不需要单独算 label。

### 代价
- 标准实现都是 SQL 引擎（Flink SQL / Trino / Oracle / Snowflake），离线 backtest 可用 DuckDB（注：DuckDB 已有 `MATCH_RECOGNIZE` 的实验支持，但成熟度需自查），流式仍需引擎。
- 同样存在「贪心匹配 vs reluctant 匹配」「无界 quantifier 风险」等正则陷阱（Flink 文档明确给出反例）。
- mining pipeline 需要重写：bit-packed 矩阵不再适用，要改成「per-symbol 流回放 + 命中统计」，单次 trial 评估代价上升约 1~2 个数量级（pattern 越复杂越严重）。

### 关键限制
- SQL:2016 的负向匹配（`PERMUTE`、`exclusion`）仅部分引擎实现，Flink 已知不支持。
- DEFINE 里的「跨 pattern variable 引用」语义（如 `STEP.low > LAST(BO.resistance)`）取决于引擎；自研解释器要小心实现一致。

---

## 3. 时序逻辑（LTL / MTL / STL — Signal Temporal Logic）

### 模型本质
公式逻辑，对「整段信号」做 *true / false* 或 *鲁棒度（robustness）* 评价。原子命题是连续值约束（`x > c`），算子包括：
- `□_[a,b] φ`（Always over [a, b]）
- `◇_[a,b] φ`（Eventually over [a, b]）
- `φ U_[a,b] ψ`（Until）

STL 在自动驾驶 / 控制 / 数字孪生用于「在 t=5..10 内速度始终 < 30 且最终到达终点」类时空约束。

### 表达用户的四要素（STL 公式示意）
设原子命题：
- `flat_ma40 := |slope(MA40)| < ε`
- `bo := is_BO ∧ vol_ratio > 1.5`
- `step := close > resistance_lvl`

四要素公式（以「最后一个 BO」为锚点 t=0）：
```
φ_pre   := □_[-20, 0] flat_ma40                      -- 状态条件 3
φ_event := (◇_[-15, 0] bo) ∧ (count_[-15, 0](bo) ≥ 2)  -- 条件 1+2（聚集 + 放量隐含在 bo 谓词里）
φ_post  := □_[1, 10] step                             -- 条件 4 台阶（事后窗口）
Φ       := φ_pre ∧ φ_event ∧ φ_post
```
- 标准 LTL/MTL 不直接含「计数」算子（`count ≥ 2`），需要用 STL 扩展（PSTL/Counted-STL）或把「2 次 BO」拆成「∃ t1 < t2 in window: bo(t1) ∧ bo(t2)」。
- Robustness 语义把布尔满足度变成实数距离 — 天然给挖掘流水线提供「连续可优化」的目标。

### 优势
- 在「事件前后双向时间窗」上语法最干净（`□_[-20, 0]` 与 `□_[1, 10]` 一目了然）。
- Robustness（实数语义）允许阈值 ε、c 用 SGD / Optuna 联合优化（PSTL 文献的 STL Inference 任务即此场景）。
- 与可解释性强：公式可直接打印作为「策略说明」，对策略文档友好。

### 代价
- Python 生态薄弱：`rtamt`、`stlpy`、`MoonLight` 是研究级工具，文档化程度差（`context7` 未索引到 rtamt 直接条目，需要凭借论文 / 项目 README 入门）。
- 「计数」与「序列」需要扩展，纯 STL 不够用。
- 与 mining 流水线衔接代价：要把每个公式参数（窗口宽度、阈值）暴露为可搜索维度。Optuna 兼容，但 bit-packed 矩阵失效。
- 学习曲线陡：开发者需要会读 STL 公式 + robustness 半环。

### 关键限制
- 多事件 ordering 表达不直接（不像 `MATCH_RECOGNIZE` 那样原生）。
- 与「BO 是离散事件」的语义存在阻抗 — STL 偏好连续信号；硬把布尔流灌进去会损失它的实数 robustness 优势。

---

## 4. HMM / FSM / 多状态隐变量模型

### 模型本质
把走势看作隐状态序列，bar-level 观测（returns、volume、volatility）由各状态的发射分布生成。`hmmlearn.GaussianHMM` 提供拟合（Baum-Welch）+ 解码（Viterbi）API（文档证据：`model.fit(X)` → `model.predict(X)` / `model.decode(X, algorithm='viterbi')`）。

### 表达用户的四要素
- 把状态先验设为 4-5 个：`accumulation`（横盘 + MA 平）、`breakout_active`（聚集 BO + 放量）、`step_up`（高位整理）、`reversion` 等。
- 用 Viterbi 解码每根 bar 的隐状态。
- 用「**状态序列正则**」做形态匹配：`accumulation+ → breakout_active{2,} → step_up{10,}`。注意，这一层正则通常需要在 HMM 之上再叠一层 — 仍然是正则匹配（回到第 2 类）。

### 优势
- **从数据自动发现状态**，不需要人工设计「水平 MA40」「放量阈值」等阈值，部分降低 mining 工作量。
- 概率语义：每个 bar 给出后验，可做软筛选（top-K 概率最高的 step_up 起点）。
- 适合「噪声大、人工特征难以全部列举」的场景。

### 代价
- 需要标注或半监督，否则训练出来的状态语义不可控（你期望的 `step_up` 不一定对应某个状态 → 必须做事后映射，常用 KMeans 残差对照）。
- 隐状态数量是超参数，敏感。
- HMM 的一阶马尔可夫假设过弱：「最后一个 BO 之后台阶」需要 longer-range memory，纯 HMM 弱于 HSMM（Hidden Semi-Markov，引入持续时间分布）或 LSTM/CRF。
- 与现有 mining 流水线兼容性最差：评估指标（命中样本 label 中位数）与 HMM 的对数似然不是同一目标，要桥接需要额外管线。

### 关键限制
- HMM 给的是「软标签」，把它作为最终交易信号容易出现「状态转移瞬时跳变」噪声。
- 若状态自由训练，无法保证产出可解释的策略 — 而本项目的核心叙事正是「人能讲清楚的形态」。

---

## 5. （简评）Sequence Pattern Mining（SPADE / GSP / PrefixSpan / SPMF）

把 K 线序列离散化为符号事件流（如 `BO_HighVol`、`MA_Flat`、`StepUp`），然后用频繁序列挖掘算法找「频次高 & 与 label 相关」的子序列。优点：和当前 mining 「自动找模板」哲学最像，能直接发现 Multi-BO 之类聚集模式；缺点：标准算法只挖序列存在性，不挖「事件间时间间隔」（GSP 有 sliding-window 扩展，但不广泛实现），也不挖事后窗口；与 `MATCH_RECOGNIZE` 相比表达力更弱、自动化更强。可作为 mining 阶段的「pattern 候选生成器」，找出后再用 CEP/MATCH_RECOGNIZE 校验。

## 6. （简评）SAX + Motif Matching

对每根 bar 计算窗口均值并 z-score → 用 alphabet 离散化为字符串 → 用 string-matching / motif discovery 找形态。优势是把 30 年 string algorithm 文献迁移过来，找「重复出现的形态片段」非常快；缺点是把「BO」这种事件信号压回连续值再离散化，丢失大量信息（量价、相对阻力位等），表达「Multi-BO + 台阶 + 放量」的复合语义需要堆 alphabet 维度，组合爆炸。适合作为「形态相似度搜索」的辅助工具，不适合作为主策略表达层。

## 7. （简评）End-to-end ML（CNN / Transformer over candlestick patches）

直接把 K 线窗口作为 image / token 序列喂给模型，让模型自己学「水平 MA40 + 多 BO + 放量 + 台阶」的复合模式。优势是无需手工写 pattern；缺点是：(a) 训练样本少（你能标 1000 个这种规律的样本吗？）、(b) 解释性差（不能告诉用户「为什么这只股票被选出」）、(c) 与现有 OOS / Bootstrap 验证、Trial 物化、可读 YAML 模板这些「工程基线」彻底冲突。属于另一种 paradigm，不应作为本框架的演化路径，而是平行实验。

---

## 调研结论

### 横向定位（按四维度抽象的覆盖度）

| 架构 | 事件 | 时间窗 | 顺序 | 状态前提 | 事后窗口 | 与 mining 流水线契合 |
|------|:----:|:----:|:----:|:----:|:----:|:----:|
| A 当前 BO 因子 | ✕ 单事件视角 | 弱（lookback 标量） | ✕ | ▲（事件前 OK） | ✕ | ★★★★★ |
| B `Condition_Ind` | ▲ | ✓（exp） | ✕ | ✓ | ✕ | ★ |
| 1 CEP (Flink/Esper/Siddhi) | ✓✓ | ✓✓（within） | ✓✓ | ✓ | ▲（需 MEASURES） | ★ |
| 2 `MATCH_RECOGNIZE` | ✓✓ | ✓✓ | ✓✓ | ✓ | ✓（DEFINE 跨 var） | ★★★ |
| 3 STL/MTL | ▲（连续偏好） | ✓✓✓（双向窗最干净） | ▲ | ✓✓ | ✓✓✓ | ★★ |
| 4 HMM/HSMM | ▲（隐状态） | ▲ | ▲ | ▲ | ✕ | ★ |
| 5 SPADE/PrefixSpan | ✓ | ▲ | ✓ | ✕ | ✕ | ★★★（候选生成） |
| 6 SAX+motif | ▲ | ✓ | ✓ | ▲ | ▲ | ★ |
| 7 End-to-end ML | n/a | n/a | n/a | n/a | n/a | ✕（替代而非演化） |

### 排序与建议

**首选：MATCH_RECOGNIZE 风格的正则化事件匹配（架构 2）**

理由：
1. 在四要素覆盖上是 7 类中最完整的，特别是 **`DEFINE` 段允许跨 pattern variable 引用** 这一条，让「事后台阶」可以直接写成 `STEP.low > LAST(BO.resistance)`，而不用拆成 BO 因子 + 独立 label 验证两条管线。
2. 是 7 类中**唯一的声明式 DSL**，模式中所有数值参数（quantifier 上下界、阈值）可以模板化、可被搜索 — 这一点对当前 mining 流水线（Optuna + bit-packed）的衔接路径最短：自研一个轻量「pattern 解释器 + pandas 回放器」即可，不必引入 Flink JVM 栈。
3. SQL:2016 标准 + Flink/Trino/Oracle/Snowflake 多家实现 = 概念稳定、未来可外包给成熟引擎，技术债小。

**次选：CEP 范式（架构 1），但只借鉴 API 不引入 JVM 引擎**

CEP 的 connector 类型（strict / relaxed / non-deterministic relaxed）是比 `MATCH_RECOGNIZE` 更细粒度的工具。如果未来发现「relaxed contiguity」需要更精细控制，可以把这个语义吸收到自研 DSL 中。

**互补：HMM 状态先验（架构 4）作为「条件 3 自动化」的工具**

「MA40 几乎水平」可以替换为 HMM 学到的「accumulation 状态后验 > 0.7」，把人工阈值变为数据驱动。但不要让 HMM 当 backbone — 它作为 *预处理 / 特征提取*，不是 *策略表达层*。

**STL（架构 3）放在第二阶段**

STL 在「事后窗口」和「鲁棒度可微分」两点上是 7 类最优雅的，但 Python 工具链尚不成熟、学习曲线陡；可以作为长期方向预留位置，等 `MATCH_RECOGNIZE` 风格落地、规律复杂度继续上升时再切。

### 是否有 `Condition_Ind` 的「超集」？

**有，但不是同一维度上的超集，而是表达力的真包含**。`Condition_Ind` 的 `(must, exp, causal)` 三元组可以一比一映射到 `MATCH_RECOGNIZE` 的 `(mandatory pattern variable, within window, ORDER BY ts ascending)`：

| `Condition_Ind` | `MATCH_RECOGNIZE` |
|---|---|
| `cond['must']=True` | pattern variable 出现在 PATTERN 中（不带 `?` quantifier） |
| `cond['must']=False, min_score=k` | 用 `PERMUTE` 或多 PATTERN UNION（部分引擎）|
| `cond['exp']=N` | `within INTERVAL N` 或 `{1,N}` quantifier |
| `cond['causal']=True` | `ORDER BY ts` 默认就是因果 |
| 跨条件顺序 | PATTERN 序列连接子（B 方案没有） |
| 事件计数 | quantifier `{n,m}`（B 方案没有） |
| 事后窗口 | DEFINE 中跨 variable 引用（B 方案没有） |

所以 `MATCH_RECOGNIZE`（以及背后的 NFA）是 `Condition_Ind` 在表达能力上的真超集 — 任何 `Condition_Ind` 写得出的判据，`MATCH_RECOGNIZE` 都能写出；反之不真。

### 一句话总结

> 现有规律的本质是「事件 + 时间 + 顺序 + 双向时间窗」四维联合，在所有候选中，**正则化事件序列匹配（`MATCH_RECOGNIZE` 风格）** 是覆盖度最高且对现有 mining pipeline 改造代价最低的架构。建议路径是：自研一个轻量 pandas-based pattern interpreter，对 `MATCH_RECOGNIZE` 子集（PATTERN 正则 + DEFINE 跨变量 + MEASURES 聚合）做实现，挖掘端把 quantifier 上下界与阈值列表化后接入 Optuna；HMM 可作为「flat MA」类前置状态自动发现的辅助；STL 留作第二阶段。CEP 厂商引擎（Flink/Esper/Siddhi）不必直接引入，只借鉴 API 设计。
