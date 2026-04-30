# 特征挖掘的算法哲学 — 候选主干设计与诚实对比

> 研究日期：2026-04-24
> 作者：`algo-advocate`（feature-mining-philosophy team 成员）
> 立场：深度倡导者 + 严格自我批评者。目标不是"打赢 AI 哲学"，而是把算法哲学讲清楚，然后诚实承认它的局限。
> 姊妹文档：`docs/research/feature_mining_via_ai_design.md`（"AI 哲学"完整版）+ `docs/explain/ai_feature_mining_plain.md`（通俗版）。

---

## 0. Executive Summary（3 分钟读完版）

**算法哲学的核心主张**：把"特征挖掘"放在**严格规则驱动的算法骨架**上。算法负责**全局、组合、搜索、打分**；AI 只在两个窄口上打工 —— **把 K 线渲染的像素/轨迹翻译成可枚举的 primitive**（视觉特征提取），以及**把用户/分析师的语言翻译成结构化 spec**（语言→结构适配）。AI 不做"归纳不变量"这一核心推理步骤，这步由算法（频率统计、图挖掘、GA、HMM 等）完成。

**最诚实的结论（不站队）**：

1. 算法哲学能**彻底消灭 3 种纯 AI 路径的病症**：
   - 语言歧义与"形态命名漂移"（AI 每次给"杯柄"起不同名字）
   - Label 反向拟合（SYSTEM 条款只是社交契约，算法则从结构上杜绝）
   - 推理不可复现（同一批样本，今天和明天 AI 可能产出不同 invariants）

2. 算法哲学有**2 个致命短板**，且其中 1 个会以新形式**重演深度学习过拟合的老毛病**：
   - **Primitive 词表问题**：算法再聪明，也只能在你喂给它的 primitive 词表里组合。如果词表里没有"V 底反转"这类概念，GA/图挖掘再跑一万代也发明不出来。这个门槛比 AI 哲学高得多。
   - **组合爆炸 + 多重比较陷阱**：频率统计、GA、图挖掘本质都是在巨大组合空间里捞"显著模式"。样本量 ~100~300 时，**几乎必然会捞到一堆在训练集上显著、OOS 立刻崩的模式**。这就是深度学习过拟合的统计学同胞。你之前用 DL 过拟合的病，在 GA+频率统计下会以"看起来不像黑盒所以更危险"的面貌重演。

3. 算法哲学的**正确用法是嵌入、不是替换**：
   - 保留 AI 哲学的 **Phase 1 语料管道**（三段式 + AI-friendly 图像）
   - 保留 AI 哲学的 **PartialSpec 中间表征**，但把"AI 归纳不变量"替换为**"AI 把样本翻译成 primitive 序列 → 算法在 primitive 序列上跑频率/图/GA"**
   - 保留 AI 哲学的 **mining falsifier**（它就是算法）
   - 新增：**primitive vocabulary SSoT** + **过拟合防御层**（permutation test、样本 bootstrap、pre-registered 假设）

4. **不对称结论**：**对 "发现全新形态"，算法哲学更弱；对 "把已知形态规则化、可审计化、可组合化"，算法哲学完胜**。用户痛点（"底部盘整 vs 高位冲顶"）恰好是后者——你**已经知道你想要什么形态**，只是要把这个先验稳定地编码为可执行规则。所以算法哲学在此场景下很有价值。

---

## 1. 算法哲学的第一性原理

### 1.1 重述用户的原话

- 原则：**基于严格规则**
- AI 角色：**底层视觉特征提取 + 语言→结构化适配**
- 算法角色（举例，不限于）：**频率表 / 特征关系图谱 / 特征权重 / 遗传算法 / 马尔科夫链**
- 全局架构：**算法通栏全局，AI 模块化打工**

### 1.2 对比 AI 哲学的核心架构分工

| 环节 | AI 哲学（现方案） | 算法哲学 |
|---|---|---|
| 样本选择 | 用户 + cold-start 分位抽样 | 同 |
| 语料导出（三段式 + 图像）| 代码（纯工程） | 同 |
| **形态识别（定性）** | AI 看图，命名（"矩形盘整"） | **AI 打 primitive tag**（candles=[doji, hammer, ...] / zones=[range_box, v_bottom, ...]），**不命名形态** |
| **数值量化** | 结构化文本直接提供 | 同 |
| **跨样本归纳（核心推理）** | **AI 输出 PartialSpec invariants** | **算法**：频率表 / Apriori / 图挖掘 / GA / HMM |
| 输出 Factor Draft | AI 直接写 YAML | **算法**从挖掘结果自动生成 YAML；AI 只润色 cn_name 等人读字段 |
| 经验 falsifier | `mining/` TPE + OOS | 同 |

**关键差异**：在 AI 哲学里，"归纳不变量"是一次 LLM 前向推理；在算法哲学里，"归纳不变量"是一次**可复现、有封闭形式、可单步追溯的算法执行**。AI 的输入变得更窄、更机械（打 tag），AI 的输出也不再是最终结论。

### 1.3 第一性原理的诊断

"特征挖掘"本质是 **从样本集合 S 中发现稳定、可泛化、可执行的映射 f：Pattern → Label**。

- **AI 哲学**假定：LLM 的归纳能力足以从 <50 个样本里提炼正确的 f。这是一个**信任 LLM 推理**的赌注。
- **算法哲学**假定：LLM 对抽象归纳不可信（容易幻觉、无法复现），但对**感知 + 翻译**可信。把"推理"交还给算法，让 LLM 只做它擅长的感知环节。

两种哲学的分歧是**对 LLM 能力边界的估计不同**，不是关于算法有效性的分歧。

---

## 2. 三套候选算法主干（具体化）

为了让讨论落地，下面给出 3 套完整的算法主干。每套都**用得起现成工具**（sklearn / networkx / mlxtend / hmmlearn / DEAP），不需要自己造轮子。

### 候选 A — 频繁模式挖掘 + 对比分析（Frequent Pattern Mining + Contrast Mining）

#### 核心数据结构

1. **Primitive vocabulary**（SSoT，人工定义 + 可扩展，约 30~80 项）。例：
   - Candle 级：`doji, hammer, engulf_bull, engulf_bear, long_upper_wick, long_lower_wick, narrow_range, wide_range`
   - Zone 级：`range_box_detected, ascending_triangle, descending_wedge, v_bottom, rounded_bottom, tight_coil, distribution`
   - Volume 级：`vol_dryup, vol_surge, vol_climax`
   - Position 级：`near_52w_high, at_52w_low, above_ma200, below_ma50`
   - Factor 级（直接来自现有 13 因子的 level 离散化）：`level_drought_hi, level_pre_vol_lo, ...`

2. **Sample as itemset**：每个 BO 样本 → 一个 primitive 的**集合**（不含顺序）。例：`S001 = {range_box_detected, vol_dryup, touches_lower_2x, near_52w_low, level_drought_hi}`。

3. **Two-class itemset database**：`D⁺`（正例 itemsets）、`D⁻`（反例 itemsets）。

#### 迭代机制

Step 1：跑 **Apriori / FP-Growth**（mlxtend 现成），分别得到 `D⁺` 和 `D⁻` 上 support ≥ θ 的频繁 itemset 集合 `F⁺`、`F⁻`。

Step 2：**Contrast / Emerging Pattern Mining**：筛选 `growth_rate = support⁺ / support⁻` > ρ（典型 ρ=3~5）且 `support⁺ ≥ θ_min` 的 itemsets。这就是**"正例独有的形态"**。

Step 3：**chi-square / Fisher exact 显著性检验**（scipy.stats），FDR 校正（Benjamini-Hochberg）。

Step 4：剩下的 Emerging Patterns 每一条 → 自动转化为 Factor Draft 候选。

#### 监督信号

- 正反例的 **class label**（不是连续的 `label_5_20` 值，而是"用户钦点 P"或"用户钦点 N"）。避免 label 反向拟合的关键：**只用 binary，不用 label 数值**。

#### AI 的模块化边界

- **输入端**：AI 看每个样本的图 + 文，输出"这个样本命中了 vocabulary 中的哪些 primitive"（一个 bool 向量）。这是**视觉特征提取**的窄口。
- **输出端**：算法挖出 Emerging Pattern `{range_box, vol_dryup, touches_lower_2x}`后，AI 只负责把它翻译成人读的 cn_name 和 Factor Draft YAML 模板填充。这是**语言→结构化**的窄口。

#### 已有工具可用性

| 需求 | 现成工具 | 投入 |
|---|---|---|
| Apriori / FP-Growth | `mlxtend.frequent_patterns` | 极低 |
| Chi-square / Fisher | `scipy.stats` | 零 |
| FDR 校正 | `statsmodels.stats.multitest` | 零 |
| Primitive tagger UI | 现有 HoverState + P/N 键盘 hook 的延伸 | 中等（需新开发） |

#### 优点

- 极简、可复现、可单步调试。每条挖出的 pattern 可以**直接指出是哪些样本支持**。
- 与现有 13 因子**自然兼容**（因子 level 直接是 primitive）。
- 统计学严谨（显著性 + FDR）。

#### 致命弱点

- **语义扁平化**：itemset 不含顺序，丢失"盘整在前、突破在后"这种时序结构。`{range_box, breakout_vol_surge}` 和 `{breakout_vol_surge, range_box}` 等价，但前者是正例典型、后者毫无意义（顺序颠倒不可能出现，但这是为了说明 itemset 的表达力问题）。
- **Primitive 词表瓶颈**（见 §4.1）—— 词表里没的东西，永远挖不出来。

---

### 候选 B — 时序图 / 特征关系图谱 + 图挖掘（Graph Mining on Temporal Feature Graph）

#### 核心数据结构

1. **Per-sample Temporal Feature Graph** `G_i = (V, E)`：
   - 顶点 `V`：样本内出现的 primitive 实例（带时间戳 t 和位置信息）。例：`v1 = (range_box_detected, t=[−55,−5])`, `v2 = (vol_dryup, t=[−30,−10])`, `v3 = (breakout_vol_surge, t=0)`。
   - 边 `E`：时序或空间关系。例：`v1 before v3`（Allen's interval algebra：before, during, overlaps, meets），`v2 during v1`, `v3 triggers_from_edge v1.upper`。

2. **Cross-sample graph union**：把所有正例的 `G_i` 对齐（以 BO 为 t=0 锚点）→ 统计每条**边**的出现频率 → **关系频率图谱**。

3. **Subgraph patterns**：用 **gSpan / SUBDUE**（图挖掘算法，Python 有 `gspan-mining` / `networkx` 手写）挖掘频繁子图。

#### 迭代机制

Step 1：对每个样本构建 `G_i`（AI 打 primitive tag + 时间戳；时间戳直接来自数据结构，不需要 AI 读）。

Step 2：对 `G⁺ = {G_i : i ∈ positives}` 和 `G⁻` 分别跑 frequent subgraph mining，频率阈值 θ=0.6（即至少 60% 正例命中）。

Step 3：**对比子图**：正例频繁但反例罕见的子图 → 候选形态规则。

Step 4：每条子图 → Factor Draft（需要一次 AI 翻译：把图结构翻成人读的 cn_name + 实现逻辑）。

#### 监督信号

- 与候选 A 相同（正反 binary）。可选加入 label 连续值作为**节点权重**（但要小心反向拟合）。

#### AI 的模块化边界

- **输入端**：AI 打 primitive tag 同候选 A，**此外还要标注时间区间**（例：「`range_box_detected` 覆盖 `[t-55, t-5]`」）。这个标注其实可以由算法从 `Breakout.consolidation_range` 直接派生，不一定需要 AI。
- **输出端**：AI 把频繁子图翻译成 cn_name + pseudo_code。

#### 已有工具可用性

| 需求 | 现成工具 | 投入 |
|---|---|---|
| NetworkX 图表示 | `networkx` | 零 |
| 频繁子图挖掘 | `gspan-mining`（PyPI 有，较冷门）或自己写图同构 + frequency | 中等 |
| Allen's interval algebra | 自己实现（逻辑简单，~50 行）| 低 |

#### 优点

- **保留时序**：解决候选 A 的最大痛点。"盘整在突破前"是一个结构性约束，图谱天然支持。
- **关系频率图谱可视化**很直观：可以在 dev UI 里画出来（"在 90% 正例中，`range_box before breakout_vol_surge` 这条边都出现"）。
- **可扩展**到多因子关系研究（与现有 13 因子交叉做边权）。

#### 致命弱点

- **算法工具冷门**：`gspan-mining` 库质量参差，自己写频繁子图挖掘工作量不小。
- **组合爆炸严重**：子图数量随节点数指数增长。30 个 primitive × 5 种时序关系，候选子图数能上百万。没有强剪枝就跑不动。
- **Primitive 词表瓶颈**同样存在。

---

### 候选 C — 马尔科夫链 / HMM + 遗传算法混合（Sequence Modeling + GA Search）

#### 核心数据结构

1. **Primitive sequence**（保留顺序，丢失并发）：每个样本 → 以 BO 为终点的 primitive 序列。例：`S001 = [near_52w_low, range_start, vol_dryup, tight_coil, range_end, breakout_vol_surge]`（按时间升序）。

2. **HMM / VLMC**（Variable-Length Markov Chain）：在 `D⁺` 上训练一个 HMM 或 VLMC，学"从正例序列生成的概率分布"。同理在 `D⁻` 上训练。每个样本 x 的判别信号 = `log P(x|HMM⁺) − log P(x|HMM⁻)`。

3. **GA individual**：一个 individual 是一条**规则** `R = (must_have_subset, order_constraints, numeric_ranges)`。例：
   ```
   R_42 = {
     must_have: [range_box, vol_dryup, breakout_vol_surge],
     order: [range_box precedes breakout_vol_surge],
     numeric: {range_duration_bars in [30, 80], breakout_vol_ratio >= 2.0}
   }
   ```
   Fitness = `precision⁺ × recall⁺ − λ × complexity(R)`。

#### 迭代机制

两种模式（可并用或二选一）：

**模式 C1 — HMM 主导**：
- 用 HMM 的 log-likelihood 差作为**形态评分**。
- 从 HMM 的状态转移矩阵中抽取"高概率路径"→ 规则。
- 适合**量化打分**，但规则可解释性一般。

**模式 C2 — GA 主导**：
- 初始化 population（100 个随机规则）。
- 每代计算 fitness，tournament selection → crossover → mutation（改 must_have 集合 / 改 numeric range）。
- 跑 50~200 代，收敛到一组高 fitness 规则。
- 适合**直接输出可执行规则**，但极易过拟合（GA 是无监督搜索的典型过拟合源）。

#### 监督信号

- 二分类 label（正反）+ 可选连续 `label_5_20`。

#### AI 的模块化边界

- **输入端**：AI 打 primitive tag + 时间顺序（实际上时间顺序可由算法派生，AI 只需打 tag）。
- **输出端**：AI 把 GA 胜出的 top-k 规则翻成 Factor Draft。

#### 已有工具可用性

| 需求 | 现成工具 | 投入 |
|---|---|---|
| HMM | `hmmlearn` | 低 |
| VLMC | 自己实现或 `vlmc` PyPI 包 | 中等 |
| GA | `DEAP` 或 `pygad` | 低 |

#### 优点

- **时序最强**：HMM 天然建模状态转移，GA 的 order_constraints 能显式编码"盘整→突破"这种先后。
- **规则可执行**：GA 直接产出`must_have + numeric_ranges`，**几乎就是 Factor Draft 的雏形**。
- **与现有 TPE 优化器生态契合**：GA 和 TPE 都是 metaheuristic，思想相近。

#### 致命弱点（最严重的过拟合风险集中在此）

- **GA 是过拟合制造机**：你给它 50 个样本 + 一个巨大搜索空间 + fitness 信号，它**一定**会找到一条把训练集解释得近乎完美的规则。这条规则在 OOS 上的泛化能力**通常极差**。
- **HMM 小样本诅咒**：50 个样本训 HMM，状态数一多就欠拟合，少了就退化成频率表。
- **黑盒化风险**：HMM 的状态转移矩阵不如 Apriori 结果直观，容易把"规则"变成"模型"，而你明确说过不要深度学习的黑盒——HMM 是同一类病。

---

### 候选 D — 因子权重 + 原型距离（Prototype + Weighted Distance）—— 作为补充

（用户原话中有"特征权重"，这里给出一个**轻量级补充**主干，适合作为候选 A/B/C 的下游打分模块。）

#### 核心数据结构

1. 把每个样本表示为**高维 primitive bag-of-features 向量** `x ∈ {0,1}^|vocab|`（或连续：每个 primitive 的强度分数）。
2. 正例质心 `μ⁺`、反例质心 `μ⁻`。
3. **加权欧氏距离**：`d(x, μ) = √Σ w_k (x_k − μ_k)²`，权重 `w_k` 由 **mutual information** 或 **logistic regression L1 coef** 给出。

#### 迭代机制

- 每轮加入新样本 → 更新 μ⁺/μ⁻ → 用 bootstrap 估计 w_k 的稳定性 → 稳定的 top-k primitive 形成"形态指纹"。
- 用 nearest-prototype 分类做快速 sanity check：正例应大多数命中 μ⁺。

#### 优点

- 思路极简，10 行代码。
- 特征权重天然可解释（w_k 高 = 重要的 primitive）。
- 可以做成 dev UI 的**实时工具**（用户每新标一个样本，权重实时更新）。

#### 缺点

- 严重依赖 primitive 词表的线性可分性。如果正例是两种子形态（cluster），质心会在它们中间，形成"伪原型"。
- 不是独立的完整方案，只适合作为 A/B/C 的结果汇总层。

---

## 3. 算法哲学能解决纯 AI 路径的哪些病症

下面逐条对照 AI 哲学方案中已知的弱点。

### 3.1 病症 1：形态命名漂移（AI 每次给"杯柄"起不同名字）

**AI 哲学现状**：靠 `form_archetype_glossary.md` 人工维护名字表（见现方案 §7.3 P2 第 12 条），但每次调用 skill，AI 仍可能产生新的 archetype 名。

**算法哲学**：**根本消灭**这个问题。算法输出的是**primitive 组合的 ID**（例：pattern_id="A∧B∧C" with canonical sort），名字只是事后人读的 label。不会漂移。

**评价**：算法哲学完胜。

### 3.2 病症 2：Label 反向拟合

**AI 哲学现状**：SYSTEM 条款 4 + 两段式 label 揭示协议（盲猜再揭示）—— 这是**社交契约**，不是结构保证。一个有点偷懒的 LLM call 仍可能违反。

**算法哲学**：**结构性杜绝**。候选 A/B 的主信号是 binary class label，连续 label 值不进入挖掘主流程（只作为可选权重，且可以完全关闭）。算法对"高 label 样本的共性"没有天然偏好 —— 它看的是 primitive 共现。

**评价**：算法哲学完胜。

### 3.3 病症 3：推理不可复现

**AI 哲学现状**：同一批样本两次调用 skill，输出的 PartialSpec 可能显著不同（LLM 的本性）。这对"系统性地迭代因子库"是很大的麻烦。

**算法哲学**：**完全可复现**。给定 primitive tags 和算法超参数，输出是 deterministic 的。

**评价**：算法哲学完胜。

### 3.4 病症 4：overlap_with_existing 的主观判定

**AI 哲学现状**：要求 AI 自己判 duplicate/refinement/orthogonal。这是一个**判断题**，AI 判错的几率不小。

**算法哲学**：把"overlap"变成**可计算的统计量**。例：新规则 R 与现有因子 F 在正例集合上的覆盖 Jaccard 相似度 > 0.8 → duplicate；重叠覆盖 0.3~0.8 → refinement；< 0.3 → orthogonal。定量判定，无争议。

**评价**：算法哲学完胜（但需要注意 threshold 是经验参数）。

### 3.5 病症 5：反例池设计的微妙性

**AI 哲学现状**：反例必须是"high-label 但形态差"，否则 AI 会学成"区分涨不涨"而不是"区分形态好坏"。这是**非常微妙的 prompt 工程**。

**算法哲学**：反例池设计同样微妙，**但一旦定好就稳定执行**。算法不会"不小心漂移"。

**评价**：平手，但算法哲学的稳定性略优。

### 3.6 病症 6：多轮 compact 的信息损失

**AI 哲学现状**：PartialSpec 的 evidence_receipts 机制设计了抗遗忘，但仍然有 AI 在 Round N 沉默丢掉 Round 1 的 counter_evidence 的风险。

**算法哲学**：**不需要多轮 compact**。所有样本一次性进数据库，一次挖掘得到结果。没有 "AI 看了后面忘前面" 的问题。**但**这要求 primitive tagging 的一次性完成——下面会说这本身是个挑战。

**评价**：算法哲学部分胜。

### 小结

| 病症 | AI 哲学 | 算法哲学 | 算法哲学的胜势 |
|---|---|---|---|
| 形态命名漂移 | 社交契约缓解 | 结构消灭 | ★★★ |
| Label 反向拟合 | 社交契约 + 两段式 | 结构消灭 | ★★★ |
| 不可复现 | 本质不可复现 | 完全可复现 | ★★★ |
| overlap 判定 | AI 主观 | 定量计算 | ★★ |
| 反例池设计 | prompt 微妙 | 稳定执行 | ★ |
| 多轮 compact | 抗遗忘协议 | 无需多轮 | ★ |

算法哲学在**已知病症的治理**上全面占优。这是它最强的论据。

---

## 4. 算法哲学的致命短板（诚实刺痛篇）

下面是作为"最严格自我批评者"必须讲清楚的 4 点。每一点都会让我这个倡导者内伤。

### 4.1 Primitive 词表的天花板问题（最严重）

**问题陈述**：算法挖掘只能在 vocabulary 里组合。vocabulary 里没有的概念，**挖一百万年也发明不出来**。

**具体情景**：假设你的痛点是"底部盘整 vs 高位冲顶"。如果你的 vocab 里有 `{range_box, near_52w_low, near_52w_high}`，算法会很快挖出"正例有 range_box + near_52w_low、反例有 near_52w_high"。但如果你的 vocab 里**没有** `near_52w_low` 这个 primitive —— 因为你一开始没想到要加 —— 那算法就抓瞎了。

**与 AI 哲学的对比**：AI 哲学在这方面**更灵活**。AI 看图能自发地说出"这个样本位于过去 2 年低点附近"，哪怕你没在 prompt 里预先定义这个概念。这是 LLM 的**无限词表**优势。

**缓解方案**：
1. **Vocabulary bootstrap by AI**：先用 AI 哲学跑 1~2 轮归纳，把 AI 提到的所有 archetype/feature/attribute 词人工审核进 vocabulary。然后算法哲学接管。这是**AI → 算法 的 vocabulary 发现 pipeline**。
2. **人工保底**：用户每次看到 dev UI 里算法挖不出的样本，手工加新 primitive。这对用户有持续心智负担。

**评价**：这是算法哲学**最硬的短板**。无法完全解决，只能缓解。结论：**算法哲学不适合"从零发现未知形态"，适合"把已知形态系统化"**。

### 4.2 组合爆炸 + 多重比较的过拟合陷阱（深度学习过拟合的新形式）

**问题陈述**：用户之前用深度学习过拟合过。直觉上"算法 = 白盒 = 不会过拟合"，**这是彻底的错觉**。

**具体机制**：
- Apriori / Emerging Pattern：30 个 primitive → 2^30 ≈ 10 亿个候选 itemset。在 ~100 样本上跑，**一定**会找到一些在训练集上 growth_rate=∞（反例全不命中）的 pattern。这些 pattern 多数是噪声巧合。
- GA：搜索空间更大（规则 = primitive 集合 × numeric ranges × order），过拟合更严重。GA 的 fitness 曲线几乎一定是单调上升，但 OOS 性能曲线通常 U 型（先上升后下降）。
- 图挖掘 gSpan：同样的巨大候选空间。

**这就是深度学习过拟合的统计学同胞**。只是：DL 过拟合的是网络权重，算法哲学过拟合的是 pattern 选择。两者都是"在有限样本上探索巨大假设空间"。

**缓解（必须严肃做，不做就是灾难）**：
1. **Pre-registered hypotheses**：在看数据之前，先写下 5~10 个你认为应该成立的规则。然后用算法只**验证**（不搜索）这些规则。这叫 **confirmatory analysis**，不会过拟合。搜索模式（exploratory analysis）的结果**必须**用另一批 hold-out 样本验证。
2. **Bonferroni / FDR 严格控制**：不是可选，是必需。候选 pattern 数量 >1000 时，单个 pattern 的 α=0.05 毫无意义。
3. **Permutation test**：把 label 随机打乱，重跑挖掘。看 null 分布下的"最显著 pattern"强度。如果你的 pattern 强度不显著高于 null，**它就是噪声**。
4. **Bootstrap 稳定性**：pattern 必须在 >80% 的 bootstrap 重采样里都出现，才算稳定。
5. **强依赖 mining/ OOS falsifier**：和 AI 哲学一样，最终经验检验是 `mining/` 的 5-dim OOS。**这条在两个哲学下都是救命稻草**。

**不诚实的说法**：说"算法哲学不会过拟合"是错的。正确说法是"算法哲学的过拟合**可以用统计工具直接检测和防御**，而 AI 哲学的过拟合只能靠 SYSTEM 条款+人工 review"。

### 4.3 Primitive Tagging 的质量瓶颈

**问题陈述**：整套算法哲学的**输入**都依赖 AI 把每个样本打成准确的 primitive tag。如果 AI 在这一步出错（例：把一个 `v_bottom` 误打成 `rounded_bottom`），**后面的算法再严谨也没用**。

**与 AI 哲学的对比**：AI 哲学里，AI 的错误可以在多轮 compact 中被 counter-evidence 修正。算法哲学里，一次 tagging 错误会污染所有下游频率统计。

**缓解**：
1. 每个 primitive 配置**多个 AI call 做 ensemble**（3 次投票），对 tagger 做冗余。token 成本上升 3 倍。
2. Dev UI 支持**人工复核 tag**：对算法挖出的关键 pattern，让用户手动验证几个 sample 的 tag 是否正确。
3. **限制 vocabulary 大小**：30~50 个 primitive 比 100+ 更可靠（AI 选项少，错误率低）。

**评价**：可以缓解，但 AI tagger 的错误率是系统误差，永远不会归零。

### 4.4 时序编码的表达力问题

**问题陈述**：候选 A（Apriori）丢时序。候选 B（图挖掘）工具不成熟。候选 C（HMM/GA）过拟合严重。**没有一个候选在"时序表达力 × 过拟合风险 × 工具成熟度"三维度上是帕累托最优**。

**实际影响**：用户想要的"底部盘整 → 温和突破"这个因果序列，**候选 A 表达不出**（会把"盘整 + 突破"退化成无序 itemset）。必须用候选 B 或 C，但 B 难实现、C 易过拟合。

**缓解**：用**弱时序编码**—— 在候选 A 的 vocabulary 里加入带时序前缀的 primitive，例：`pre_bo_range_box`, `pre_bo_vol_dryup`, `at_bo_vol_surge`。这样 Apriori 可以隐式使用时序信息而不需要真的时序建模。但这会让 vocabulary 膨胀 2~3 倍，加剧 4.2 的过拟合问题。

**评价**：有 workaround，但不优雅。

---

## 5. 算法哲学 vs AI 哲学 —— 诚实对比矩阵

| 维度 | AI 哲学 | 算法哲学 | 裁决 |
|---|---|---|---|
| 形态发现（未知形态）| 强（LLM 开放词表） | 弱（vocab 瓶颈） | AI 胜 |
| 形态系统化（已知形态的规则化）| 中（社交契约可失守）| 强 | **算法胜** |
| 可复现 | 弱 | 强 | **算法胜** |
| 可审计 | 中（PartialSpec + evidence_receipts） | 强（每个 pattern 可追溯） | **算法胜** |
| Label 反向拟合防御 | 中（协议） | 强（结构） | **算法胜** |
| 过拟合控制 | 弱（靠 mining OOS） | **弱**（组合爆炸，只是过拟合换了形式） | 平手（都必须靠 OOS 兜底） |
| 工具成熟度（现成）| 极高（Claude Code 本身）| 中（Apriori 低门槛，gSpan/GA 有门槛） | AI 胜 |
| 开发成本（首次）| 中（skill + UI）| **高**（vocab + tagger + 挖掘 + 过拟合防御）| AI 胜 |
| 维护成本（长期）| 中（每次跑都消耗 LLM token） | 低（算法定型后几乎零成本） | **算法胜** |
| 调试能力 | 弱（LLM 不透明）| 强 | **算法胜** |
| 与现有 mining/ 集成 | 直接对接 | 直接对接（现有因子即 primitive）| 平手 |
| 用户参与深度 | 中（只需挑正反例）| 高（要定 vocab、review tag）| AI 胜 |
| Cold-start 能力 | 强（AI 自带先验知识）| 弱（vocab + primitive tagger 都要建）| AI 胜 |
| 解决用户核心痛点（底部盘整 vs 高位冲顶） | **可解** | **可解且更稳定** | 算法略胜 |

**总结**：算法哲学在**稳定性、可审计、长期维护**上完胜；AI 哲学在**灵活性、cold-start、开发速度**上完胜。

---

## 6. 关于"算法通栏全局，AI 模块化打工" — 这口号对吗？

用户的口号很有力度，但我作为倡导者也要诚实批评：**这口号在 cold-start 阶段是错的，在成熟阶段才对。**

### 6.1 Cold-start 阶段（vocab 还没建好时）

vocabulary 是整个算法哲学的地基。**地基怎么建？**
- 方案 1：用户人工列 primitive —— 工作量巨大，容易漏。
- 方案 2：**AI 先跑一轮 AI 哲学的 induction**，把 AI 产出的 archetype / feature / attribute 词汇全部采集，人工审核进 vocab。

方案 2 明显更优。所以在 cold-start，**AI 哲学先行、为算法哲学铺地基**。这时候是"AI 通栏全局，算法模块化打工"，反过来。

### 6.2 成熟阶段（vocab 稳定后）

vocab 积累到 50~80 项、覆盖了用户关心的主要形态空间后，算法哲学接管主流程。AI 退回到"打 tag + 润色输出"的窄口。这时候才是用户口号的正确形态。

### 6.3 推荐的演化路径

```
Phase 0（现有系统）：13 因子，人工设计
  ↓
Phase 1（AI 哲学 MVP）：跑 3~5 次 skill，产出 20~40 个 archetype / invariant
  ↓ [vocabulary bootstrap：AI 产物 → 人工审核 → vocab v1]
Phase 2（混合哲学）：算法挖掘在 vocab v1 上跑；AI 继续并行跑 skill，发现 vocab 遗漏
  ↓
Phase 3（算法哲学主导）：vocab v2 稳定；AI 只做 tagging + 输出翻译
```

**这个演化路径的关键洞察**：两种哲学不是对立的，是**时间先后**的。用户当前处于 Phase 0 末期，准备进入 Phase 1。**现在就讨论 Phase 3 的完整算法哲学实施，是提前 18 个月的优化**。

---

## 7. 算法哲学需要替换还是嵌入 AI 方案的哪些环节？（具体映射）

下面是把算法哲学细节映射到现方案的落地建议。

### 7.1 保留不动的环节（AI 哲学已做对的）

| AI 哲学环节 | 保留理由 |
|---|---|
| Phase 1 语料管道（5 盘整字段 + 三段式 + AI-friendly 图像） | 算法哲学同样需要这些语料，且工程质量已经很高 |
| 用户 P/N 标注 UI（dev UI keyboard hook） | 监督信号来源，两哲学共用 |
| Cold-start label 分位抽样器 | 共用 |
| `mining/` 经验 falsifier | 共用，不可替代 |
| `add-new-factor` skill | Factor Draft 落地管道共用 |

### 7.2 替换的环节（AI 哲学弱、算法哲学强）

| AI 哲学环节 | 替换为 |
|---|---|
| PartialSpec 中的 "invariants 由 AI 自由提议" | **算法自动提议 candidate patterns + AI 只做 primitive tagging** |
| SYSTEM 条款中的 "overlap_with_existing AI 判定" | **Jaccard / 覆盖度定量计算** |
| 多轮 compact 协议（Round 1/2/3...） | **单轮全批挖掘**（挖掘算法一次性看所有样本）|
| 两段式 label 揭示协议 | **结构性移除 label 连续值**（只保留 binary），不再需要揭示协议 |

### 7.3 新增的环节（算法哲学独有）

| 新环节 | 位置 | 作用 |
|---|---|---|
| **Primitive Vocabulary SSoT** | 新增 `BreakoutStrategy/analysis/primitive_vocabulary.py` | 30~80 个 primitive 的定义 + 算子（如何判定某 primitive 在某样本上命中） |
| **Primitive Tagger** | 新增 skill `tag-bo-primitives`（类似 `induce-formation-feature` 结构） | AI 看样本 → 输出 primitive 命中向量 |
| **Pattern Miner** | 新增 `BreakoutStrategy/analysis/pattern_mining.py` | 依赖 `mlxtend` / `scipy`，实现 Apriori + Emerging Pattern + 显著性检验 |
| **过拟合防御层** | 新增 `BreakoutStrategy/analysis/overfit_defense.py` | Permutation test + bootstrap + FDR，对每个候选 pattern 打 confidence 分 |
| **Pattern → Factor Draft translator** | 新增工具（可走 AI skill 或纯模板） | 把 pattern 翻译成 8-field Factor Draft YAML |

### 7.4 核心替换图示

```
AI 哲学：
  样本 → [三段式 + 图像] → AI [多轮归纳] → PartialSpec → Factor Draft
                             ↑ 这里是 LLM 推理黑盒 ↑

算法哲学（嵌入版）：
  样本 → [三段式 + 图像] → AI [primitive tagger, 窄口] → primitive vectors
         → Pattern Miner [Apriori/GA/图挖掘] → candidate patterns
         → Overfit Defense [perm test + FDR + bootstrap] → validated patterns
         → AI [pattern → Factor Draft translator, 窄口] → Factor Draft
                             ↑ 只在这两个窄口用 AI ↑
```

---

## 8. 推荐最终策略（综合裁决）

以下是我作为倡导者 + 自我批评者的**综合建议**，用户最终可以直接基于这个做决策。

### 8.1 不做全盘替换

**不要**把现有 `docs/research/feature_mining_via_ai_design.md` 的 AI 哲学方案整体推翻换成算法哲学。理由：
- AI 哲学方案已细致到 checklist 层，投入大；
- Cold-start 阶段 AI 哲学更高效；
- 算法哲学在 vocab 未建时是空转。

### 8.2 按阶段渐进嵌入

推荐的落地次序：

**阶段 I — 先跑 AI 哲学 MVP（0~3 个月）**
- 按现有 `feature_mining_via_ai_design.md` §7.5 Phase 1~2 落地；
- 每次 skill 调用产生的 archetype 词、attribute 词、invariant 短语 **全部归档**到 `docs/research/feature_library/vocabulary_draft.md`；
- 跑 3~5 轮，积累 30~50 个候选 primitive。

**阶段 II — Vocabulary 审核 + 算法哲学 MVP（3~6 个月）**
- 人工审核 vocabulary_draft.md → 出 `primitive_vocabulary.py` v1（先锁定 30 项左右）；
- 实现 **Primitive Tagger skill**（ensemble 3 次 AI call）；
- 实现 **候选 A（Apriori + Emerging Pattern）**—— 这是最简单、工具最成熟的算法主干；
- 实现 **过拟合防御层**（permutation test + FDR）；
- 并行：AI 哲学 skill 继续跑，发现 vocabulary 遗漏。

**阶段 III — 算法哲学扩展（6~12 个月，视阶段 II 效果决定是否投入）**
- 根据 vocabulary 是否稳定、primitive tagger 精度是否达标 （> 90%）决定是否投入更复杂的候选 B/C；
- 候选 C（GA）只在"已有稳定 vocab + 足够 OOS 样本（>500 BO）"后启用；
- 候选 B（图挖掘）作为研究型探索，不进主 pipeline。

### 8.3 候选主干的选择优先级

| 候选 | 优先级 | 理由 |
|---|---|---|
| **A（Apriori + Emerging Pattern + 对比挖掘）** | ★★★★★ | 工具最成熟、过拟合最可控、实现最简；阶段 II 首选 |
| D（原型 + 权重）| ★★★ | 作为 A 的下游打分层，几乎零成本 |
| B（图挖掘）| ★★ | 时序表达力最强但工程门槛高；长期研究型目标 |
| C（HMM/GA）| ★ | 过拟合风险最大，**强烈不建议在小样本阶段使用** |

### 8.4 不能省的三条防线

无论走哪条路径，**以下三件事不可妥协**：

1. **Pre-registered hypotheses**：阶段 II 开始前，先人工写下你相信的 10 条形态规则。算法跑完后先用这 10 条做 confirmatory，再看 exploratory 结果。
2. **`mining/` OOS falsifier**：任何 pattern → factor 必须跑 5-dim OOS。这是最后一道闸。
3. **Hold-out sample set**：阶段 II 开始前保留 20% 样本完全不参与任何挖掘。最终 pattern 必须在 hold-out 上也成立。

---

## 9. 回到用户的核心痛点

用户痛点：`live` 里匹配的多是"高位冲顶"，想要"底部盘整 → 温和突破"。

**两种哲学对此痛点的具体解法**：

- **AI 哲学**：AI 看图能一眼说出"这些正例都位于 52 周低点附近，反例位于 52 周高点附近"→ 产出"position_at_low" invariant → Factor Draft。**优点**：快。**缺点**：下次跑可能叫 "basing_at_support_zone"，名字漂移。

- **算法哲学**：vocab 里预设 `near_52w_low` / `near_52w_high` → Apriori 挖出 `{range_box, near_52w_low} → high label` 是正例 Emerging Pattern。**优点**：稳定、可审计。**缺点**：vocab 里必须**预先**有 `near_52w_low` —— 这需要第一次 AI 哲学运行帮你发现这个词。

**结论**：对这个具体痛点，**算法哲学理论上更优**（更稳定），**但需要 AI 哲学先行铺 vocab**。所以回到 §8.2 的阶段 I → II 演化。

---

## 10. 最终诚实结论（一段话）

算法哲学**对已经知道目标形态的场景（用户当前情况）**能提供更强的稳定性、可审计性、抗 label 反向拟合能力，应当**作为 AI 哲学的下游接力方案**在阶段 II 引入。**但不应替换 AI 哲学在 cold-start 和 vocabulary bootstrap 上的作用**。算法哲学最大的幻觉是"白盒 = 不会过拟合"，实际上 Apriori/GA 的组合爆炸会以**深度学习过拟合的统计同胞**的形式再度上演，必须用 permutation test + FDR + bootstrap + pre-registered hypotheses + OOS hold-out 五重防御严肃对抗。用户原话中的口号"算法通栏全局，AI 模块化打工"是**长期愿景**，不是**当前应立即执行的架构**。分阶段演化才是正解。

---

## 附录 A：与 feature_mining_via_ai_design.md 的具体章节映射

| AI 哲学章节 | 算法哲学建议 |
|---|---|
| §2.1.1 三档 input_mode | 算法哲学阶段 II 只用 `text_only` 模式（图像只给 tagger，不给挖掘算法） |
| §2.2 skill 流程 | 新增并列 skill `mine-bo-patterns`，与 `induce-formation-feature` 共存 |
| §3.1 三段式结构化 | 保留，但算法哲学只用 Seg 2 (consolidation_json) + Seg 3 (factors_and_levels) |
| §3.3 多轮 compact 协议 | 算法哲学**不使用**多轮 compact |
| §3.4 正/反例池 | 保留（两哲学共用） |
| §3.5 Layer A 自然语言输出 | 算法哲学版：由 pattern_id + 人工命名或 AI 翻译生成 |
| §3.5 Layer B Factor Draft | 算法哲学版：从 pattern 自动生成 YAML 模板，AI 只填 cn_name |
| §6 风险表 | 算法哲学风险表见本文 §4（组合爆炸 + vocab 瓶颈 + tagger 错误 + 时序弱） |

---

**文档结束。**
