# Feature Mining — Base Rate (p0) 设定研究

> 研究日期：2026-04-25
> 角色：base-rate-analyst（rule-stats-model team）
> 关联文档：
> - `docs/research/feature_mining_via_ai_design.md` — AI 驱动的形态特征挖掘总方案
> - `docs/research/feature_induction_workflow_detail.md` — 多轮 compact 流程附件
> - 平行研究：stats-modeler 的累积统计模型（Beta/LLR/Wilson/PMI 候选）
> 范围：本文不依赖具体统计模型选型，单独锁定"随机基线频率 p0"的设计问题。

---

## 0. 摘要（Executive Summary）

**结论**：在用户挑选样本天然有偏的设定下，**直接使用市场全体突破样本的 base rate 作 p0 是错的**。会让所有候选 invariant 的"显著性"被系统性高估，导致 stats-modeler 输出的累积证据虚高、形态归纳产生伪因子。

**推荐方案（分阶段）**：

| 阶段 | 推荐 |
|---|---|
| **冷启动**（用户标注 < 30 正例）| **方案 (d) 自参照模型** + **方案 (e) LLM 估 p0 的简化版**（下文§4.1）二选一：以 Beta 后验或 Wilson 下界给出"K/N 强度"判据，**不与 p0 比较**。p0 留空，后期补。 |
| **稳态**（用户已标 ≥ 30 正例 + ≥ 20 反例）| **方案 (b) 改良版**：从**广义市场基线**（同 regime / 同价区 / 同 sector 匹配的所有突破样本，不只限于用户挑过的）估计 per-feature p0，并用**用户反例池**做 *bias-correction* 校准（§5）。每个特征的 p0 独立估计 + Bayesian 平滑。 |

**与 stats-modeler 的兼容**：
- Beta 后验、Wilson 下界 → **冷启动期可不带 p0**（自参照）→ 稳态期可加 p0 比较（`P(p > p0)`），平滑过渡
- 累积 LLR、PMI → **必须 p0**：冷启动用一个鲁棒的"宽 prior"（§4.4 给出 default 值），稳态切换到估计版 p0

**关键洞察（biased sampling 的诊断）**：用户的"挑出来的好形态"≠ "随机突破"。正确的对比基准不是"市场所有突破"，而是 **"在用户的 label-criterion 下、规模和环境匹配的突破"**。这一差异在前 50 个样本内可以达到 2-5x 的 p0 偏差。

---

## 1. 问题陈述

### 1.1 p0 是什么

在 stats-modeler 的候选模型中：
- **累积 LLR**：log-likelihood ratio = log(p_hat / p0)，p0 是零假设下"特征出现的随机概率"
- **PMI**：log(P(feature ∩ outcome) / (P(feature) × P(outcome)))，分母里的边缘概率充当 p0
- **Beta 后验比较**：可写成 `P(p > p0 | K, N)`，p0 是显著阈值
- **Wilson 下界**：可不依赖 p0（输出区间），但若要做"是否高于随机"的判据，仍需 p0

**p0 的语义**：在没有特征 X 的情况下，X 在样本里出现的"应有"基线频率。用于回答："观测到 K/N=k/n 是否真的反常？"

### 1.2 用户样本的有偏性 (biased sampling)

用户的样本不是随机抽样，而是**主动挑选自认为的"理想形态"**。这意味着：

1. 用户挑的样本子集 `S_user` 中，所有 `label_5_20` 都偏高（已确认信号）
2. 任何**真正普遍的市场规律**（如"突破日放量"），它在 `S_user` 里出现频率必然高于在所有 BO 上的频率，因为：
   - 高 label 与"放量"两件事在市场层面就高度相关（confounder）
   - 用户主动挑"看着像"的样本，会更倾向于"放量明显"的（视觉偏见）
3. 反过来，若**直接用市场全体突破的 base rate 作 p0**，则：
   - 在 `S_user` 上观测到 `K/N` 高于 p0，会被错误归因为"形态特异规律"，
   - 实际只是"用户挑的样本天然 enrich 了所有正向特征"

**直观例子**：假设市场所有突破中 60% 都"突破日放量"（市场基线 p0 = 0.6）。用户挑了 30 个高 label 突破，其中 28 个放量（K/N = 0.93）。
- 用 market p0 = 0.6 → 严重显著（Beta(28,2) vs 0.6 的 P(p > p0) ≈ 0.999），LLR 累积巨大
- **真相**：高 label 突破中放量比例本来就 ≈ 0.92。用户的 0.93 ≈ 噪声，**不能称之为"形态规律"**

### 1.3 双重抽样偏差

更细致地，bias 至少有两层：

| Bias 类型 | 来源 | 量级（经验估计） |
|---|---|---|
| **Outcome bias** | 用户挑高 label 的样本 → 任何与 label 相关的特征都 enrich | p0 偏移可达 1.5-3x |
| **Visual selection bias** | 用户被"明显"的形态吸引（清晰度、可读性、心理舒适度） | p0 偏移 1.2-2x |

总偏移：在最差情况下，特征在 `S_user` 中的出现频率可达市场基线的 3-5 倍。

### 1.4 基线频率的"特征"是什么

p0 的对象是"特征 X 的发生事件"。在本项目中，AI 归纳产出的 invariant 具有以下分布：

| Invariant 类型 | 特征事件示例 | p0 估计成本 |
|---|---|---|
| **离散布尔型** | "突破日放量 ≥ 2x 20d avg" | 低（直接计数） |
| **连续阈值型** | "盘整 stability < 0.03" | 中（先选阈值） |
| **多条件合取** | "盘整 ≥ 30 根 AND 振幅 ≤ 15%" | 高（条件组合稀疏） |
| **形态级（图像）** | "矩形盘整 + U 底" | 极高（无可计算定义） |

p0 设计必须分类型。多条件合取和形态级是难点。

### 1.5 不可解决的根本困难

> **"理想 p0" = 在用户所定义的 label-criterion 下，'除特征 X 之外其他条件随机'的子集中 X 的出现频率。**

这个理想几乎不可达：
- 用户的 label-criterion 没有完整定义（部分隐含在视觉偏好里）
- "其他条件随机"在 confounded 的金融数据里很难实现（一切都相关）

因此**所有方案都是次优近似**。我们要做的是选**偏差最小、计算最便宜**的近似。

---

## 2. 候选方案对比（含问题里指定的 a–f + 新增 g/h）

### 2.1 全方案对比表

> Bias risk 评估：相对市场真值的系统性偏离方向；越接近 0 越好。
> 计算成本：相对一次性预处理的工程量与实际跑 mining pipeline 的开销估算（低=分钟级、中=小时级、高=多小时/需补数据）。

| 方案 | 实施方式 | 适用阶段 | Bias 风险 | 计算成本 | 推荐度 |
|---|---|---|---|---|---|
| **(a) 全局固定 p0**（如 0.1） | 单一常数 | 测试用 | **极高**（不区分特征频率差异） | 极低 | ❌ 不推荐 |
| **(b) 历史所有 BO 估每个 feature 的 p0** | 跑全样本 BO，per-feature 计数 | 稳态 | 中（Outcome bias 仍在） | 中 | ⚠ 需修正才推荐 |
| **(b')** = (b) + bias-correction | (b) + 用户反例池作 confounder calibration | 稳态 | 低 | 中-高 | ✅ **稳态主选** |
| **(c) 不同特征类别用不同 p0** | 按 category（resistance/breakout/context）分组 | 兼容方案 | 中（粒度不够） | 低 | △ 作 (b) 退化版 |
| **(d) 自参照（无 p0）** | 用 K/N 自身（Beta posterior mean / Wilson lb） | **冷启动** | 0（不与基线比） | 极低 | ✅ **冷启动主选** |
| **(e) LLM 估 p0** | 让 Claude 看 N 个随机突破估每特征频率 | 冷启动备选 | 中（LLM hallucination） | 中-高 | △ 简化版可用 |
| **(f) Corpus 内估 p0** | p0 = 用户挑选样本中的特征均值 | — | **极高**（信号会自抵消） | 极低 | ❌ 反模式 |
| **(g) 反例池作 p0** ★ 新提 | p0 = 反例中特征出现频率 | 稳态强化 | 低（部分校准 outcome bias） | 中 | ✅ 与 (b') 联用 |
| **(h) Permutation null** ★ 新提 | 对每特征做 shuffle 测试 | 验证用 | 极低 | 高 | △ 不作主路径 |

### 2.2 逐方案细评

#### (a) 全局固定 p0（拒绝）

**为何拒绝**：
- "放量" base rate 可能是 0.55，"盘整 50+ 根" 可能是 0.04，二者相差 14 倍
- 单一 p0 会让前者长期"不显著"、后者长期"超显著"，模型崩塌

**唯一可用场景**：单元测试 / 协议验证。

#### (b) 历史所有 BO 估 p0（需修正）

**实施**：
1. 从 `datasets/pkls/` 跑一次全市场 BO 检测（已有 pipeline）
2. 对每个候选 invariant，计算其在 ~5万-20万 BO 上的发生频率 → 这是 p0_market
3. 喂给 stats model

**优点**：每个特征独立 p0，粒度合适。

**致命缺陷**：忽略了 §1.2 所述的 outcome bias。即便特征在市场上很普遍，用户挑选的高 label 子集里频率仍会更高，导致显著性虚高。

**修正方案 (b')**：**条件化 p0** — 不取所有 BO 的边缘频率，而是取"在与用户样本同等 label-criterion / regime / 价区的子集中"的频率：

```
p0_for_feature_X = P(X | label_5_20 ∈ user_target_quartile, regime, price_tier)
```

具体步骤：
1. 计算用户正例的 label 区间（如 top quartile 边界）
2. 取所有市场 BO 中 label 落在同一区间的子集 `S_market_high`
3. 计算 X 在 `S_market_high` 中的频率 → p0_X

**实施成本**：中（需要全市场 label 计算缓存，约 1-3 小时一次的预处理）。
**bias 风险**：低 — 仍残留视觉选择偏差，但已消除 outcome bias 的主要部分。

#### (c) 按 feature category 用不同 p0

把因子分为 `resistance / breakout / context`，每组用一个 p0（如 0.5/0.4/0.2）。

**评价**：粒度太粗。"突破日放量"和"突破日跳空"都属 breakout 但 base rate 差几倍。
**用途**：可作为 (b)/(b') 不可用时的极低成本退化方案；或作为 (b) 的 prior 平滑系数（见 §6.4）。

#### (d) 自参照模型（无 p0）— 冷启动主选

**核心理念**：放弃"特征是否显著高于基线"这个判据，改用"特征在样本内的累积证据强度"判据。

**适用统计模型**：
- **Beta 后验均值**：直接用 `(K+α)/(N+α+β)`，配合不确定度（posterior variance）报告
- **Wilson 下界**：给 K/N 一个鲁棒下界（如 95% CI lower），不需要与 p0 比
- **Conjunction probability**：多 invariant 时报告联合后验

**判据示例**："此 invariant 在 30 样本上后验均值 0.92, 95% CI 下界 0.78 → 强证据" ——直接强度判据，无需 p0。

**优点**：
- 不犯 biased-sampling 的错（因为根本不与"基线"比）
- 在样本量小时是最稳健的（p0 估计误差大于 K/N 误差时，自参照反而更可信）

**缺点**：
- 不能告诉用户"这是否比'随机突破'更频繁" —— 但**这恰恰不是冷启动该问的问题**。冷启动该问的是"这个特征在我标的高质量样本里有多稳健"。
- 与累积 LLR 模型不兼容（LLR 内在依赖 p0）

**结论**：**强烈推荐冷启动主路径**。让 stats-modeler 在 ≤30 样本时用纯 K/N 判据。

#### (e) LLM 估 p0（成本高，简化版可行）

原版：让 Claude 看 1000 个随机突破估每特征频率 → 不切实际（token 成本爆炸 + AI 数数不准）。

**简化版（推荐）**：
1. 对每个 candidate invariant，让 Claude 看 30-50 个**结构化样本**（不需要图，因为只算频率）
2. Claude 回报"在此 30 个里有几个满足该 invariant"
3. 用 Beta(2,2) prior 做 Bayesian smoothing：p0_llm = (k+2) / (n+4)

**为何简化版可用**：
- AI 不需要看市场全部，只需看一个**有限的随机抽样**
- 抽样池可以是市场所有 BO 的 random sample（不限于用户标过的）
- 最终 p0 是 LLM 计数 + Beta smoothing 的混合

**适用阶段**：冷启动、且 stats model 必须用 LLR/PMI（否则用 (d)）。
**Bias 风险**：依赖 LLM 计数准确度。但因 invariant 是 well-defined 的（如"突破日 RV ≥ 2"），LLM 数数的误差远小于其他类任务。
**成本**：每特征 ~5-10k tokens × 候选特征数。在 5-15 个 invariant 时可控。

#### (f) 用户 corpus 内估 p0（反模式，**禁用**）

如果 p0 = 用户样本中特征出现率，那么：
- K/N ≈ p0 是 trivial 的（同分布抽样 → 相等）
- 任何 invariant 都"接近基线" → 显著性恒为 0

**这会让模型完全失效**。除非用作"自检"判据（"如果某 invariant 出现率竟然显著高于 corpus 内均值，说明它过度集中在某些子集" → 用作 split 信号）。

**结论**：禁用作 main p0；可作为辅助诊断信号。

#### (g) 反例池作 p0（新提议，强烈推荐与 (b') 联用）

`feature_mining_via_ai_design.md` §3.4 已设计了反例池：
- **主反例池**：`label_5_20` top quartile \ 正例池（高 label 但形态用户没选）

**关键洞察**：这些反例和正例都是高 label。如果某特征在正例 corpus 里出现频率显著高于反例 corpus，那么这个差异**已经控制了 outcome bias**（两组都是高 label）。

**实施**：
- p0 = `mean(feature_X in negative_corpus)`
- 假设 feature 真值在两组都是 p_true
  - 正例：p_true + outcome_bias + visual_bias
  - 反例：p_true + outcome_bias（无 visual_bias，因为反例是用户没选的）
- 比较时差值 ≈ visual_bias —— 这正是"形态级"差异的来源

**优点**：
- 自带 outcome bias 校准
- 与 §3.4 反例池设计天然契合
- 与方案 (b')/§3.4 协作时更鲁棒

**缺点**：
- 反例样本量小（20-40），p0 估计方差大
- 需 Bayesian smoothing（用 (b') 的 p0_market_high 作 prior）

**推荐用法**：与 (b') 做 **shrinkage estimator**（§6.2），冷启动期向 prior 收缩，稳态期向反例频率收敛。

#### (h) Permutation null（理论清晰但成本高）

对每个 invariant：
1. 随机 shuffle "label" 标签（保留特征值）
2. 重新计算 invariant 在 top quartile 的频率
3. Repeat N=1000 → 得到 null distribution
4. p0 = null distribution mean

**评价**：
- 理论上最 sound
- 但 mining pipeline 已经在做 OOS 验证 + bootstrap，permutation 与之重复
- 成本太高，不适合做主路径

**用途**：当某 invariant 极其重要（例如准备升级为正式因子）时，做最终"金标"验证。不是 base-rate 的常规来源。

---

## 3. Biased Sampling 的修正策略

### 3.1 三种修正路径对比

| 修正策略 | 思路 | 适用 | 评价 |
|---|---|---|---|
| **Importance sampling 修正** | 对样本加权 w(s) = p_market / p_user 估计 base rate | 数学上严密 | ❌ 需要知道 sampling weights → 用户的"挑选"无显式概率，不可行 |
| **Stratified base rate** | 按 confounder（label-bin / regime / price_tier）分层估 p0 | 部分可行 | ✅ 即 (b') 的实施核心 |
| **Control corpus 法** | 构造与正例 matched 的 control 池，base rate 取自 control | 见 §3.3 | ✅ **强烈推荐**，与 §3.4 反例池设计契合 |

### 3.2 为什么不用 Importance Sampling

IS 的关键前提：**知道 sampling 概率**。用户挑选不是显式概率，是隐式视觉偏好。即便用 logistic regression 反推 propensity score：
- 特征空间高维，IPW 极易爆炸
- 所有 invariant 候选互相 confound，propensity 模型本身就是要学的对象

**结论**：放弃 IS。用 control corpus 法（§3.3）替代。

### 3.3 Control Corpus 设计（推荐主路径）

**对应 §3.4 中的反例池**：

```
control = label_5_20 ∈ user_target_label_quartile
       \ user_positive_picks
       (matched on regime / price_tier / 时间段)
```

**关键属性**：
- 与正例同 label level → 控制 outcome bias
- 是用户**没选**的样本 → 控制 visual selection bias
- 规模匹配 → 控制 size confounder

**与 base rate 的关系**：
- p0 = `P(feature | control)`，即 (g) 方案
- 与 corpus 内频率 `P(feature | positive)` 比较 → 直接得到"形态级"判别力

**Matching 的具体维度**（按重要性排序）：
1. label_5_20 区间（必需）
2. price tier（用 §`price_tier_analysis.py` 的现有分桶）
3. 大盘 regime（如 SPY 趋势/震荡，可选）
4. sector（次要）
5. 时间段（避免 regime drift，可选）

**Control 池构建策略**：
- 当用户挑出 30 正例后，从 `S_market_high`（label-matched 池）中按上述维度做 stratified random sampling
- 反例数 = 正例数 × 1.0~1.5（不少于 20）

### 3.4 三种偏差合成时的处理

实践中，bias-correction 不可能完美。建议**显式承认**残留偏差，并在统计模型中体现：
- p0 报告**点估计 + 95% CI**（基于 control corpus 样本量的 Beta 后验）
- 下游 stats model 用 p0 的不确定度做 robust LLR / robust Bayes
- 详见 §5

---

## 4. Per-feature 独立 p0 vs 全局 p0

### 4.1 直觉与现实

直觉：**应该 per-feature 独立**。
- "突破日放量 ≥ 2x"：市场 base rate ≈ 0.5
- "盘整 50+ 根"：≈ 0.05
- "U 底形态 + 缩量收口 + 三浪上升"：≈ 0.005

误差 14 倍 vs. 100 倍，单一 p0 必然崩塌。

但 per-feature 的代价：
- 每个特征都要算一次 p0 → 计算成本 × N_features
- 每个 p0 都有估计噪声（因为 control 池只有 ~30 样本）
- 当 invariant 是 "X AND Y AND Z" 时，p0 在 control 池里可能是 0/30，无法估计

### 4.2 推荐折中：**Hierarchical Bayesian p0**

按 §4.3 的分层结构估 p0：

```
Level 1 (全局)：p0_global ≈ 0.15  (默认 prior，所有特征共享)
Level 2 (类别)：p0_category[c] ~ Beta(α_c, β_c)，c ∈ {resistance, breakout, context}
                                     从全市场所有 BO 估，按 category 分组
Level 3 (特征)：p0_feature[f] ~ Beta(α_f, β_f)，
                              prior 来自 Level 2，posterior 来自 control corpus 频率
```

**计算实现**：
```python
# Beta-Binomial conjugate update
α_prior = p0_category[c] * pseudo_count   # pseudo_count=20 推荐
β_prior = (1 - p0_category[c]) * pseudo_count

# control corpus 观测：control 中 k 个样本满足特征，n 个总数
α_post = α_prior + k_control
β_post = β_prior + (n_control - k_control)

p0_feature = α_post / (α_post + β_post)   # posterior mean
```

**优点**：
- 单个 control 池小、噪声大时 → 向 category prior 收缩，鲁棒
- 当 control 池足够大、信号清晰 → 向 control 经验频率收敛
- 显式处理 0/30 这种 boundary case（不会得到 p0=0）

**缺点**：
- 实现略复杂
- 类别分组要预先定义（用 §3.6 的 category 字段）

### 4.3 简化版（Phase 1 落地）

如果 hierarchical Bayes 实现成本过高，**最低可行版**：
1. 每个 feature 独立从 control corpus 估 p0
2. 用 fixed Beta(2, 8) prior（隐含 p0 ≈ 0.2）做 smoothing
3. 单 feature 公式：`p0 = (k + 2) / (n + 10)`

这是 "Laplace smoothing + 弱 prior" 版本，工程简单、效果可接受。
后续若有信号衰减，再升级到 hierarchical Bayes。

### 4.4 Cold Start 默认值（必须）

**stats-modeler 的 LLR/PMI 在冷启动期需要可用的 p0**。建议默认值：

| Invariant 类型 | Cold-start p0 默认 | 来源 |
|---|---|---|
| 离散布尔（"放量"） | 0.30 | 经验值 |
| 连续阈值（"stability < ε"，ε 取 quartile） | 0.25 | 25% 自然分位 |
| 多条件合取（2 项 AND） | 0.10 | 边际概率乘积估计 |
| 多条件合取（3+ 项 AND） | 0.04 | 同上 |
| 形态级 | **不可用 → 改用 (d)** | — |

冷启动时所有特征用上表 default p0，外加 Beta(2, 8) 的不确定度。30+ 样本后切到方案 (b')+(g)。

---

## 5. p0 不确定性的下游传播

### 5.1 不确定性来源

p0 的估计误差在多个层面：

| 层级 | 误差来源 | 量级 |
|---|---|---|
| Sampling | control 池有限 (n_control) | σ_p0 ≈ √(p0(1-p0)/n_control) |
| Selection bias 残留 | matching 不完美 | bias ≈ 0.05-0.15（不可减） |
| Definition fuzz | invariant 定义模糊 | bias ≈ 0.02-0.10 |

n_control = 30 时，σ_p0 ≈ 0.08（对 p0 = 0.3 而言），不可忽略。

### 5.2 Robust 统计判据

**stats-modeler 的下游模型应当假设 p0 = p0_hat ± σ_p0**，而非 p0 = p0_hat：

#### 对累积 LLR

不再是 `LLR = K * log(p1/p0) + (N-K) * log((1-p1)/(1-p0))`，
而是 **lower-bound LLR**：
```
LLR_lb = min over p0 ∈ [p0_hat - 2σ, p0_hat + 2σ] of LLR(p1, p0_realized)
```
即取最不利的 p0 计算 LLR，给出保守证据。

#### 对 Beta 后验

`P(p > p0)` 改为 **integrated over p0 distribution**：
```
P_robust = ∫ P(p > p0_realized) × Beta(p0_realized | α_p0, β_p0) d_p0_realized
```

这个积分有 closed form（双 Beta），计算便宜。

#### 对 Wilson 下界

Wilson 不直接依赖 p0，但若用作"是否高于 p0"判据：
```
"hypothesis accepted" iff Wilson_lb_95% > p0_upper_bound_95%
```
即用 Wilson 下界 vs. p0 上界比较，要求 strict improvement。

### 5.3 决策规则建议

| 阶段 | 判据 |
|---|---|
| 冷启动 | Wilson lb > 0.5（自参照硬阈值） |
| 稳态弱信号 | P(p > p0_upper_95) ≥ 0.7（保守 robust Bayes） |
| 稳态强信号 | LLR_lb ≥ 4 nats（保守 LLR） |

这套设计**让 p0 误差不会致命** — 真正脆弱的 invariant 在 robust 化后会自然失败。

---

## 6. 冷启动方案

### 6.1 Phase 0（≤ 10 样本）

**不做统计判据**。完全依赖 AI 归纳本身的判断 + spot-check。
- p0 = N/A
- stats-modeler：跳过显著性检验，只做"K/N + 样本量"展示
- 等待样本积累

### 6.2 Phase 1（10-30 样本）

**自参照（方案 d）+ 极保守 prior**：
- p0 = N/A 或 default 表（§4.4）
- stats-modeler 推荐：Wilson 下界判据，hard threshold 0.5
- 不允许新因子进入 mining pipeline 前用户至少 attestate 30 正例

### 6.3 Phase 2（30+ 正例 + 20+ 反例）

**Bias-corrected estimation（方案 (b')+(g)）**：
- 自动构建 control corpus（§3.3 流程）
- per-feature 独立估 p0，用 hierarchical Bayes（§4.2）
- stats-modeler：robust LLR / robust Bayes 全部启用

### 6.4 Phase 转换条件

stats-modeler 应在 **每次 mining run 启动时**判定阶段：

```python
def determine_phase(n_positive, n_negative):
    if n_positive < 10:
        return "phase_0"
    if n_positive < 30 or n_negative < 20:
        return "phase_1"
    return "phase_2"

def get_p0_strategy(phase):
    if phase == "phase_0":
        return None    # no stats judgment
    if phase == "phase_1":
        return DEFAULT_P0_TABLE  # §4.4
    return "control_corpus_hierarchical"  # §3.3 + §4.2
```

---

## 7. 与不同统计模型的兼容性矩阵

| 模型 | p0 是否必需 | 冷启动 (Phase 1) | 稳态 (Phase 2) | 推荐用法 |
|---|---|---|---|---|
| **Beta 后验均值** | 否（自参照） | 用 Beta posterior + uncertainty | 同冷启动 + 可叠加 P(p > p0) 判据 | 主推 — 平滑过渡 |
| **Beta 后验 P(p > p0)** | 是 | 用 §4.4 默认 p0 + 大不确定度 | 用 (b')+(g) + robust 积分 (§5.2) | 主推 — 概率语义清晰 |
| **Wilson 下界** | 否（区间报告） | Wilson lb > 0.5 硬阈值 | Wilson lb > p0_upper_95 | 推荐 — 鲁棒、低假设 |
| **累积 LLR** | **必需** | §4.4 默认 p0；LLR ≥ 6 高阈值 | (b')+(g) + LLR_lb ≥ 4 | 慎用，对 p0 敏感 |
| **PMI** | **必需**（边际概率即 p0） | §4.4 默认 p0；高阈值 | (b')+(g) + 不确定度积分 | 与 LLR 类似 |
| **TF-IDF / BM25 类** | 边际作 IDF | 用 §4.4 默认 | 用 control corpus | 用作辅助 ranking，不作主判据 |

**核心结论给 stats-modeler**：
1. **Beta 后验 + Wilson 下界**是最 p0-friendly 的 → 在 Phase 0/1 可不依赖 p0
2. **LLR / PMI** 必须有 p0 → 冷启动用 §4.4，稳态切 (b')+(g)
3. 多模型并行报告时，Beta + Wilson 主推（不容易因 p0 错误而崩塌），LLR 作辅助证据

---

## 8. 推荐方案（最终）

### 8.1 推荐架构（一句话）

> **p0 = Hierarchical Bayesian estimate from a label-matched control corpus, with the user's negative pool as the primary "control"; cold-start uses self-referential models (Wilson lb / Beta posterior) bypassing p0 entirely.**

### 8.2 完整 pipeline（与 stats-modeler 对接）

```
┌─────────────────────────────────────────────────────────────────┐
│  1. 收 corpus (positive + negative，§3.4)                       │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. determine_phase()                                            │
│      - phase_0：跳过统计，纯 AI 归纳 + 用户 spot-check            │
│      - phase_1：默认 p0 表 (§4.4) + 自参照模型                    │
│      - phase_2：control corpus + hierarchical Bayes              │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼  (phase_2 only)
┌─────────────────────────────────────────────────────────────────┐
│  3. 构 control corpus (§3.3)                                    │
│      - 从全市场 BO 中按 label / price_tier / regime stratified  │
│      - 用户的 negative pool 优先入选                             │
│      - target n_control = max(30, n_positive)                   │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. per-feature p0 estimation (§4.2 hierarchical Bayes)         │
│      - Level 2 prior：market-wide BO category 频率              │
│      - Level 3 posterior：control corpus 频率                    │
│      - 输出 (p0_hat, σ_p0) tuple                                │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. 喂 stats-modeler，使用 robust 判据 (§5.2)                    │
│      - 多模型并行报告（Beta/Wilson/LLR/PMI）                      │
│      - 每个判据带 p0 不确定度                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 8.3 工程落地清单（P0 → P2）

| Priority | Item | Effort |
|---|---|---|
| P0 | 实现 `determine_phase()` + Phase 0/1 路径（默认 p0 表 + 自参照模型） | 0.5 天 |
| P0 | per-invariant Beta-Binomial conjugate p0 estimator (§4.3 简化版) | 0.5 天 |
| P1 | control corpus 构建器（label/price_tier matching） | 1 天 |
| P1 | hierarchical Bayes p0（§4.2 完整版） | 1 天 |
| P1 | stats-modeler 的 robust 判据接口（接收 (p0_hat, σ_p0) 元组） | 0.5 天 |
| P2 | 全市场 BO 缓存（驱动 Level 2 prior 估计） | 1 天预处理 |
| P2 | per-feature p0 报告 + 不确定度可视化（in mining report） | 0.5 天 |

### 8.4 与 §`feature_mining_via_ai_design.md` §3.4 的协同

- §3.4 已设计正例 / 主反例 / 次反例池 — 直接复用作 control corpus
- 主反例池天然实现"label-matched control" → 是 (g) 方案的现成数据源
- 次反例池可作 Level 2 prior 的"中分位"分布估计（更稳健）

无 schema 修改需求。仅在 `feature_induction_workflow_detail.md` §6 的"falsifier chain"前增加一步"p0 estimation"。

### 8.5 失败模式与监控

| 失败模式 | 监控信号 | 处理 |
|---|---|---|
| Control corpus 太小（< 20） | n_control 监控 | 自动降级 phase_2 → phase_1 |
| p0 估计为 0 或 1（boundary） | p0 ∈ {0, 1} 警告 | hierarchical Bayes 防 boundary，回退 prior |
| 所有 invariant 都"显著"（信号过强） | top-k 显著性聚集 | 怀疑 bias 未校准 → 检查 control 配比 |
| 所有 invariant 都"不显著"（信号过弱） | top-k 显著性 < 阈值 | corpus 太异质 → 触发 split |
| p0 跨轮次抖动 | σ(p0_round_k) > 0.05 | corpus 不稳定 → 暂停归纳 |

---

## 9. 关键风险与缓解

| 风险 | 量级 | 缓解 |
|---|---|---|
| Visual selection bias 不可校准 | 中 | 在 robust 判据中显式承认；用形态级 invariant 配合外部经济解释（domain knowledge）作二次校验 |
| Control corpus 与 positive 不真 matched | 高 | matching 维度要明确写入 mining report；用 mining pipeline 的 OOS 验证作最终背书 |
| Phase 1 的 default p0 表过保守 → 错过弱信号 | 中 | 保守是好事 — 弱信号本来就该等样本积累；定期 review default 表 |
| Hierarchical Bayes 实现复杂 → 工程出错 | 中 | 先上 §4.3 简化版（Laplace smoothing），稳定后再升级 |
| p0 估计被用户挑选偏好"反向利用" | 低 | mining pipeline OOS 验证是最终防线 — 任何 p0 设计错误都会在 OOS 上显现 |

---

## 10. 与 stats-modeler 的协议接口（建议）

stats-modeler 在选择最终统计模型时，可参考下述接口约定 — 让 base-rate 设计与具体模型解耦：

```python
@dataclass
class P0Estimate:
    feature_key: str
    point_estimate: float        # p0_hat
    sigma: float                 # σ_p0（不确定度）
    n_control: int               # 估计基样本量
    method: Literal['default_table', 'control_corpus', 'hierarchical_bayes']
    confidence_interval: tuple[float, float]  # 95% CI


@dataclass
class StatsJudgment:
    feature_key: str
    K: int                       # 正例 corpus 中 feature 出现次数
    N: int                       # 正例 corpus 总数
    p0: P0Estimate | None        # None for self-referential models
    posterior_mean: float        # Beta posterior mean
    wilson_lb: float             # Wilson 95% lower bound
    llr_lb: float | None         # robust LLR lower bound (if p0 available)
    pmi_lb: float | None         # robust PMI lower bound (if p0 available)
    decision: Literal['accept', 'reject', 'undecided']
```

stats-modeler 的工作就是从 `K, N, P0Estimate` 计算上述 fields；本研究保证 `P0Estimate` 的可信度。

---

## 11. 关键术语速查

| 术语 | 含义 |
|---|---|
| p0 | 零假设下特征出现的随机基线频率 |
| Outcome bias | 用户选高 label 样本带来的特征频率偏移 |
| Visual selection bias | 用户视觉偏好带来的特征频率偏移 |
| Control corpus | 与 positive corpus matched 的反例池，用于 base rate 估计 |
| Self-referential model | 不依赖 p0 的统计模型（Beta posterior, Wilson lb） |
| Robust judgment | 在 p0 不确定度下的保守判据 |
| Hierarchical Bayes p0 | 按 全局 → category → feature 三层估计的 p0 模型 |
| Phase 0/1/2 | 按样本量阶段化 p0 策略（≤10 / 10-30 / 30+） |

---

## 附录 A：数学推导（关键公式）

### A.1 Beta-Binomial conjugate update

```
prior:       p ~ Beta(α, β)
observation: K of N samples have feature
posterior:   p ~ Beta(α + K, β + N - K)
posterior mean = (α + K) / (α + β + N)
posterior var  = ((α+K)(β+N-K)) / ((α+β+N)² (α+β+N+1))
```

### A.2 Wilson 95% lower bound

```
p_hat = K / N
z = 1.96
denom = 1 + z² / N
center = (p_hat + z² / (2N)) / denom
margin = (z / denom) * sqrt(p_hat (1-p_hat) / N + z² / (4N²))
wilson_lb = center - margin
```

### A.3 LLR with p0 uncertainty (robust lower bound)

```
LLR(p1, p0) = K log(p1/p0) + (N-K) log((1-p1)/(1-p0))
LLR_lb = min over p0 ∈ [p0_hat - 2σ_p0, p0_hat + 2σ_p0] of LLR(p1_hat, p0)

# Closed form: LLR is monotonic in p0 for p1 > p0, so
LLR_lb = LLR(p1_hat, p0_hat + 2σ_p0)   # 取 p0 上界
```

### A.4 Robust Beta P(p > p0)

```
joint distribution: p ~ Beta(α_p, β_p), p0 ~ Beta(α_p0, β_p0), independent
P_robust = ∫∫ I(p > p0) × Beta(p; α_p, β_p) × Beta(p0; α_p0, β_p0) dp dp0

# Numerical: 双 Beta 卷积，scipy.stats.beta + numerical integration
```

### A.5 Hierarchical Bayes（极简）

```
Level 1: p0_global ~ Beta(2, 8)  # weak prior, mean=0.2
Level 2: p0_category[c] | data_c ~ Beta(2 + k_c, 8 + n_c - k_c)
Level 3: p0_feature[f] | data_f, c(f) ~ Beta(α(p0_category[c(f)], 20), β(...))
                                          + control corpus observation
```

其中 `α(p, s) = p × s, β(p, s) = (1-p) × s`，s=20 是 pseudo-count。

---

**文档结束。**
