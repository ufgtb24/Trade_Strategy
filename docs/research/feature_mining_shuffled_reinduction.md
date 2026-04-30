# Feature Mining — Shuffled Re-induction（打乱重组 batch）深化研究

> **日期**：2026-04-26
> **关联 doc**：`docs/research/feature_mining_orchestration_revisit.md` §2 Q2 三机制论
> **关联 spec**：`docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md`
> **触发问题**：用户对原 doc Q2 的深化质询 —— "Re-induction 只覆盖了未充分挖掘的样本（孤儿 / 用户标注），那么对已充分挖掘的样本，是否也有必要以新组合方式重新进入 Inducer？"
> **本文不修改任何既有 doc 或 spec，仅产出 delta 建议。**

---

## §0 触发与范围

### 0.1 用户原问拆解

用户的质询包含三层递进观察：

1. **观察**：原 doc Q2 的 Re-induction 触发候选启发式只覆盖了 "孤儿样本 / forgotten/candidate 命中样本"（[原 doc §2.5]），即"挖得不充分"的子集
2. **猜想**：对"已挖得充分"的样本，**重新组合 batch** 后让 Inducer 再看一遍，是否也能产生新规律？
3. **机理**：原始 ingest 时样本 A,B,C 在同一 batch、D,E,F 在另一 batch；A 与 D **从未同 batch 出现**过 → Inducer 没机会做"两图对比"。打乱后 A,D 同 batch → 揭示该跨 batch feature

这三层共同指向一个核心问题：**Inducer 的 co-induction 信号（多图对比产共性）受 batch 组合限制，原始 ingest 的 batch 划分实际上是一种隐式信息瓶颈**。

### 0.2 范围

- 仅讨论"打乱重组 batch"机制的定位、价值、风险、设计
- 仅在 [原 doc §2] 已定义的三机制基础上扩展，不重写 §2
- 不动 [spec §3] Beta-Binomial、不动 [spec §4.3] Inducer 输入契约（仅追加可选维度）
- 与 [原 doc §1 Q1] 的 Python CLI 哲学保持兼容
- 与 [原 doc §3 Q3] 的 archetype hint 互斥规则保持一致

### 0.3 关键术语

- **打乱重组（Shuffled Re-induction / Combinatorial Re-batching）**：对已 ingest 的老样本，按某种策略**重新分配到新 batch** 后再次进入 Inducer
- **共现率（co-occurrence rate）**：N 张样本中任意两张曾出现在同一 batch 的概率
- **共现矩阵**：N×N 二元矩阵，`M[i,j] = 1` 当且仅当 sample i 与 sample j 至少同 batch 出现过一次
- **batch 邻居（batch neighbor）**：与某样本同 batch 出现过的其他样本集合

---

## §1 机制定位与命名

### 1.1 与既有三机制的本质区分

[原 doc §2.3] 已定义三机制 + 一禁用机制：

| 机制 | 是否重跑 Opus Inducer | batch 组合是否变化 | 触发样本范围 |
|---|---|---|---|
| **Replay** | 否（仅 ObservationLog 重放）| — | Critic 修改某 feature 涉及的样本 |
| **Re-induction** | 是 | 默认不变（用户挑哪些就跑哪些）| 用户指定子集（典型：孤儿）|
| **多视角增强**（已禁用）| 是 | — | 同一样本多份 nl_description |
| **打乱重组（本文新提）** | 是 | **主动改变（核心特征）** | **全库已 ingest 样本**（默认）|

**最关键的区分维度是"batch 组合是否被主动改变"**：

- Re-induction 即便用户每次挑"不同的子集"，本质仍是"按预定子集 → 自然分 batch"，不是"为了制造新邻居关系而精心安排 batch"
- 打乱重组的**核心目的**是制造新的"样本 × 样本"邻居关系，从而产生新的 co-induction 信号

### 1.2 命名建议

**推荐作为第 4 机制独立命名**，理由：

1. **触发语义不同**：Re-induction 是"我怀疑这些样本没挖到东西"；打乱重组是"我想看看新组合下能否涌现新规律"。前者样本驱动，后者组合驱动
2. **算法不同**：Re-induction 不需要 batch 分配策略；打乱重组的核心算法**就是** batch 分配策略（5 种候选见 §4.1）
3. **风险曲线不同**：Re-induction 的风险主要是 epoch_tag 双重计数（已被 [原 doc §2.4] 解决）；打乱重组叠加了"组合空间膨胀 → 过拟合训练集"的新风险
4. **与 archetype hint 的互斥逻辑同构但路径独立**：epoch>0 时禁用 hint 是 [原 doc §4.2] 已定的硬约束；打乱重组也应纳入这条规则

**命名候选**：

- `Shuffled Re-induction`（保留"re-induction"的家族关系）—— **推荐**
- `Combinatorial Re-batching`（强调组合维度）—— 备选
- `Cross-batch Re-induction` —— 不推荐，"cross-batch"已在 [spec §4.3 co-induction 信号] 暗指"同 batch 内"，易混淆

下文统一用 **Shuffled Re-induction**。

### 1.3 与 Re-induction 的边界（系统性 vs 机会性）

用户在原问中也意识到边界模糊："如果用户每次 reinduce 都指定不同子集，效果是否等同打乱重组？"

**判断**：行为可能等同，但**意图与效果保证完全不同**。

| 维度 | Re-induction（用户挑子集）| Shuffled Re-induction |
|---|---|---|
| 用户意图 | "我怀疑 S03/S07/S12 没挖到" | "我想最大化覆盖率，看看老库还能挖出什么" |
| 子集选择依据 | 用户启发式（带主观偏差）| 算法策略（覆盖率 / 分层 / 反相关）|
| 批组合保证 | 无 | 有（如 anti-correlated 策略保证不重复采样老对）|
| 终止条件 | 用户感觉够了 | 算法收敛信号（共现矩阵填充率 / 新 feature 产出率）|
| 可复现性 | 低（同一意图下不同次操作可能挑不同样本）| 高（给定 random seed + 策略，可重放）|

**结论**：Shuffled Re-induction 是 Re-induction 的"**系统性 + 算法化**"超集。可视为 Re-induction 的一个**严格子模式**，但因为它需要专属算法 + 终止条件 + CLI 表达，独立命名更清晰。

---

## §2 价值判断 —— 组合可见性增益的量化论证

### 2.1 共现率公式

对 N 张样本、batch_size = B、按不重叠 batch 分配的原始 ingest：

- 每张样本只属于 1 个 batch
- 该样本的 batch 邻居数 = B - 1
- 全库共有 N × (N-1) / 2 个无序样本对
- 同 batch 出现的样本对数 = ⌈N/B⌉ × C(B, 2) ≈ N × (B-1) / 2
- **共现率 = (B - 1) / (N - 1)**

代入典型参数（按 [spec §2.2] cold-start batch 8~12 张推断 B=8 / B=10 / B=12）：

| N | B | 共现率 | 未共现率 |
|---|---|---|---|
| 30 | 8 | 24.1% | 75.9% |
| 50 | 8 | 14.3% | 85.7% |
| 50 | 10 | 18.4% | 81.6% |
| 100 | 8 | 7.1% | 92.9% |
| 100 | 10 | 9.1% | 90.9% |
| 100 | 12 | 11.1% | 88.9% |
| 200 | 10 | 4.5% | 95.5% |
| 500 | 10 | 1.8% | 98.2% |

**关键观察**：N 在 100 量级（用户原始数据规模上限）时，**91% 的样本对从未同 batch 出现**。这意味着 91% 的潜在跨样本 feature 在原始 ingest 中**根本没机会**被 Opus Inducer 注意到。

### 2.2 跨样本 feature 占比的估算

设 Π 为"全库潜在 feature 中需要至少 K 张样本才能涌现的比例"（K 取决于该 feature 的统计稀有度）。

[spec §3] 的 Inducer 输出契约要求 `(text, K, N, supporting_sample_ids)`，其中 K ≥ 2 是 Inducer 内部显著性门槛（单图独有的特征会被 Inducer 视为噪声跳过，详见 [spec §备选 5 否决理由]）。

设 Π_K=2 为"恰好需要 2 张样本同时出现才被 Inducer 报为 candidate" 的 feature 占比。这个值无法先验确定，但可以用一个**保守估算**：

- 假设全库真实潜在 feature 数为 F_total
- 其中 60% 是"单 batch 内可见的强信号"（Inducer 一眼看出，如经典 cup-and-handle）→ 不依赖跨 batch
- 30% 是"跨多 batch 才显著的中度信号"（如某种少见的盘整变体） → 受共现率影响
- 10% 是"必须 ≥ 3 张才显著的弱信号" → 受共现率显著影响

那么受共现率影响的 feature 占比 ≈ 40%。

**机会损失估算**（N=100, B=10）：

- 91% 未共现率 × 40% 受影响 feature ≈ **36% 潜在 feature 在原始 ingest 中被遗漏**

这是一个**很大的数字**，足以证明 Shuffled Re-induction 在理论上有显著价值。

> 注：这是上限估算。实际损失会因 (a) Inducer 在 N=2 时的稳健性低、(b) 部分跨 batch feature 在多次单独的小 K/N 事件累积后仍可被 P5 检测出来 而被打折。但即使打 1/3 折，仍有 ~12% 潜在收益空间。

### 2.3 与 [spec co-induction 信号] 的关联

[spec §4.3] 强制约束 "Inducer 不得查重 / 不得知道老 features 存在（避免 co-induction 信号污染）"。这条约束的直觉是：**co-induction 信号是 Inducer 在一个 batch 内通过"两图同时显现某共性"产生的判读，污染会让 Inducer 把库内已知的 feature 名字"挪用"过来当新发现**。

**Shuffled Re-induction 不破坏这条约束**：

- Inducer 仍然不读 features 库，不知道 F-001 / F-002 是什么
- Inducer 仍然只看本 batch 内的 K 张图 + nl_description
- 改变的只是"哪些样本进入同一 batch" —— 这是**外部调度决策**，对 Inducer 内部认知是透明的

**Shuffled Re-induction 实际上是在"补全"co-induction 信号的覆盖率**：原始 ingest 的 ⌈N/B⌉ 个 batch 是 batch 全空间 C(N, B) 的极小采样（N=100, B=10 时 C(100,10) ≈ 1.7×10^13，原始 ingest 只采了 10 个），打乱重组就是在这个巨大空间里追加采样。

### 2.4 再论"Re-induction 子集 vs Shuffled Re-induction"的差别

回到 §1.3 的边界讨论。如果用户每次 Re-induction 都"挑不同 8 张"，理论上多次 Re-induction 也能逐步覆盖 C(N, 8) 空间。但有两个本质障碍：

1. **机会性 vs 系统性**：用户挑选有强主观偏差，会反复采样某些"看着有意思"的样本，造成共现矩阵的局部高密 + 整体低覆盖
2. **没有终止信号**：用户不知道何时该停。Shuffled Re-induction 通过"共现矩阵填充率"提供了客观停止条件

**所以 Shuffled Re-induction = Re-induction 在"组合空间覆盖"维度上的算法化升级**。

### 2.5 价值判断结论

- 理论收益：N=100 量级时，最多 ~36% 潜在 feature 被原始 ingest 遗漏，**Shuffled Re-induction 有强理论动机**
- 实际收益：受 Inducer 跨 batch 时的稳健性、新 feature 与老 feature 的语义独立性影响，可能打 1/3~1/2 折，仍是 **~12-18% 潜在增量**
- 与 spec 兼容：不破坏 [spec §4.3] 约束（Inducer 仍盲跑）
- 与 [原 doc Q1] 兼容：可作为 CLI 命令暴露
- 与 [原 doc Q2 三机制] 兼容：通过 epoch_tag + rollback 模式（[原 doc §2.4]）防双重计数

**因此：理论上值得引入。但需要严格的风险控制**（详见 §3）。

---

## §3 风险评估

### 3.1 风险 1：统计独立性的二阶破坏

[原 doc §2.4] 的 epoch_tag + rollback 模式已经处理了"同 (sample, feature) 多次 ObservationLog 条目"的双重计数 —— **同一物理样本对同一 feature 永远只持有最新判读结果**。

但 Shuffled Re-induction 引入了一个**二阶问题**：**新发现的 feature F-new 与老 feature F-old 在样本上的 yes/no 高度相关时，两条 feature 的 (α, β) 是"独立观察"还是"伪造的多样性"？**

举例：

- F-old："盘整期量缩"（已 strong，由原始 ingest 产出）
- 打乱后某 batch (A, D, X) 中 Inducer 发现 F-new："盘整期成交量呈对数型衰减"
- F-new 与 F-old 在所有样本上 yes/no 完全一致（语义子集）
- L0 cosine 0.83（卡在阈值 0.85 灰色地带），未被 dedup 拦下

此时：
- F-old 的 (α, β) 受样本 A, D, X 影响
- F-new 的 (α, β) 也受样本 A, D, X 影响
- 两条 feature 都通过 P5 派生 status，可能都被认定为 strong

**但实际上这只是同一规律的两个表述**，库内出现"语义近亲家族"。

**类比 [spec §4.7] split**：split 后两条 feature 允许共享样本，但 split 是 Critic **基于明确语义差异**（如"长期下跌后" vs "横盘震荡末期"）划分的，**两条 feature 在样本上 yes/no 应该有显著差异**（否则不构成 split 的理由）。Shuffled Re-induction 产生的"语义近亲"则没有这种保证。

**缓解方案**（多层）：

1. **强制 L0 收紧**：Shuffled Re-induction 产出 candidate 时，与老 features 的 cosine 阈值从 0.85 降到 0.75（更严格的去重），落入 [0.75, 0.85] 灰色地带的强制走 L1 二次确认
2. **L1 等价性检测**：L1 (DeepSeek) 收到 (F-new, F-old, samples) → 反向 prompt "这两条规律在这些样本上的判读是否实质等价？" → 等价则 merge 而非新增
3. **新 feature 的 P5 推迟提升**：Shuffled 产出的 feature 默认带 `provenance: shuffled` 标签，P5 阈值带的提升需要**额外的非 shuffled 来源支持**（如下一轮原始 ingest 或 incremental 命中）才允许进 strong

### 3.2 风险 2：Reward Hacking 风险

如果 Inducer 知道"这批是打乱的 / 我之前看过这些样本"，可能会刻意挖一些奇怪的组合性 feature 来"显得有产出"。

**防御方案**：

1. **盲跑**：Inducer prompt 必须不包含任何关于"这是 shuffle batch / 之前看过 / 有几个 epoch" 的信息。Inducer 把每个 batch 当作独立的多图对比任务
2. **样本的 nl_description 复用既有版本**：不刷新 nl_description，避免"第二次看时描述变化 → Inducer 推断这是重看"
3. **prompt 模板与原始 batch 完全一致**：goal 字段还是 `"find common features across these samples"`，不加任何"探索新组合"的暗示
4. **审计字段**：ObservationLog 的 `inducer_context` 字段（如果实现 [原 doc D9]）记录 `epoch_tag = shuffle-r3-b2`，但这个只用于 audit，不在 Inducer prompt 中

### 3.3 风险 3：过拟合到训练样本集

Shuffled Re-induction 在固定样本集上反复挖掘 → 挖到的 feature 越多 → 在新样本上泛化越差？

**这是真风险还是错觉**？分析：

- **不是错觉**：组合空间膨胀确实可能让 Inducer 找到一些"在这 N 张图上恰好同时成立"但在 N+1 张全新图上不成立的偶然规律
- **本框架的天然缓解机制**：
  - **lazy decay**（[spec §3.2]）：feature 不被新样本持续验证就慢慢淡化（λ=0.995, 半衰期 138d）。即使 Shuffled 挖到偶然规律，新数据进来不验证它就会自然衰减
  - **counter 的强权重**（[spec §3.3] γ=3）：新样本明确 no 时 β 累积速度快，能压住 false positive
  - **[spec §备选 6] 否决了"非随机抽样修正"**：但这也意味着框架默认接受"训练样本即定义域"，泛化责任完全交给用户控制样本来源

**结论**：过拟合风险**真实但有缓解**。需要在 CLI 层面做以下硬约束：

- Shuffled Re-induction 不应在用户标注样本数 < 阈值（如 30）时启用 —— 小样本下组合膨胀比例最大，过拟合最严重
- 鼓励用户在 Shuffled 之后**立刻 ingest 新样本**做"压力测试"（incremental 路径自动触发对所有 features 的 Path V 验证）

### 3.4 风险 4：L0 dedup 失效场景

如 §3.1 举例，新 candidate 与老 feature embedding 相似度刚好 0.83（阈值 0.85 附近）→ 灰色地带 → 可能误入库。

**专用方案**（与 §3.1 第 1 点一致）：

- Shuffled Re-induction 产出的 candidate **专用**更严的 cosine 阈值（如 0.75）
- 落入 [0.75, 0.85] 强制走 L1
- L1 prompt 显式询问"是否实质等价于已有规律 F-X"（这次允许 Inducer 之外的 L1 知道老 features —— 不污染 Inducer，符合 [spec §4.3]）

### 3.5 风险 5：成本爆炸

Shuffled Re-induction 是**纯 Opus 多模态调用**，是三层成本阶梯（[spec §1.1]）的最高层。

**单次成本估算**：
- 1 个 batch (B=10 张图) → 1 次 Opus 多模态调用
- N=100 全洗牌 = 10 个 batch = 10 次 Opus 调用
- 1 次 Opus 多模态调用 ≈ 假设 50K tokens（10 张图 + 系统 prompt + 输出 candidate）
- 10 个 batch = 500K tokens

**多轮成本估算**（10 轮 reshuffle）：
- 100 次 Opus 调用 = 5M tokens
- 按 Opus 4 当时定价（$15/M input, $75/M output）粗略估算 = $75-$300 / 10 轮

**成本控制方案**：

1. **CLI 必须提供 `--dry-run`**：先估算 token 消耗 + 调用次数，用户确认后再真跑
2. **CLI 必须提供 `--max-cost-tokens` 硬上限**：超过即停止
3. **优先 anti-correlated 策略**（§4.1）：避免重复采样已覆盖的样本对，把每次调用的"新组合贡献"最大化
4. **smart skip**：每个 batch 跑完后立即检查产出，如果 K 轮连续 0 新 feature → 提前终止

### 3.6 风险汇总

| 风险 | 严重度 | 是否可控 | 缓解机制 |
|---|---|---|---|
| 语义近亲（Π独立性二阶破坏） | **高** | 是 | 收紧 L0 阈值 + L1 等价性检测 + provenance 标签延后提升 |
| Reward hacking | 中-高 | 是 | Inducer 盲跑 + nl_description 不刷新 + prompt 模板一致 |
| 过拟合训练集 | 中 | 部分 | lazy decay + counter γ=3 + 小样本时禁用 + 鼓励后续 ingest 验证 |
| L0 dedup 失效 | 中 | 是 | Shuffled 专用更严阈值 + 强制 L1 二次确认 |
| 成本爆炸 | 中-高 | 是 | dry-run + max-cost-tokens + anti-correlated 策略 + smart skip |

**所有风险均可工程化缓解**，但需要 §4 的设计配套。

---

## §4 设计方案

### 4.1 五种打乱策略对比

| 策略 | 描述 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|
| **1. Random** | numpy.random.shuffle 后切 batch | 实现最简单 | 可能反复采样已覆盖的样本对，效率低 | baseline / 对照实验 |
| **2. Anti-correlated** | 维护共现矩阵 M，每个 batch 优先选"M 内未配对过"的样本组合（贪心或 IP 求解）| 最大化新组合贡献，每个 Opus 调用价值最高；天然提供终止条件（M 填满）| 需维护共现矩阵；贪心可能局部最优；问题复杂度高 | **推荐默认** |
| **3. Stratified by P5-band** | 从 strong / consolidated / candidate 各抽几张组成 batch | 跨成熟度交叉，可能让"已 strong feature 的样本"启发"对 candidate feature 的新理解" | 需先有较成熟的 P5 分布（要求库已运转一段时间）；跨 band 组合的语义价值未经验证 | 库已有 ≥ 5 条 strong + ≥ 5 条 candidate 时 |
| **4. Stratified by archetype** | 从不同形态类别（盘整型 / 突破前 / 量价关系...）各抽一些 | 跨类型交叉，可能涌现"形态间组合规律" | 依赖 archetype 已知（[原 doc Q3] L2 方案）；如果未启用 L2，本策略不可用 | 仅在 [原 doc D9-D11] 已实施时可用 |
| **5. Stratified by source feature** | 每个 feature 选 K 张支持样本，组成 mixed batch | 主动构造"feature 之间的对比" | **存在信息泄露风险**：选 sample 的依据是"它支持哪条 feature" → Inducer 看到的样本组成本身就编码了 feature 标签 → 严重违反 [spec §4.3] | **禁用** |

**推荐默认策略**：**Anti-correlated**

**理由**：
- 与"组合可见性"理论价值（§2）完全对齐 —— 每次调用都最大化新邻居关系
- 提供天然客观终止信号（共现矩阵填充率）
- 不依赖任何外部条件（如 archetype 已建立 / P5 已成熟）
- 与 [原 doc Q3] L2 方案 (archetype hint) 解耦，避免互锁

**Anti-correlated 算法草案**（贪心，非最优但工程可行）：

```python
def anti_correlated_batches(
    sample_ids: list[str],
    batch_size: int,
    cooccurrence_matrix: dict[tuple[str, str], int],  # 历史共现计数
    n_batches: int,
) -> list[list[str]]:
    """贪心地组建若干 batch，每个 batch 内尽量选历史共现少的样本组合"""
    batches = []
    available = set(sample_ids)
    for _ in range(n_batches):
        if len(available) < batch_size:
            available = set(sample_ids)  # 重置
        # Step 1: 随机选种子
        seed = random.choice(list(available))
        batch = [seed]
        available.discard(seed)
        # Step 2: 贪心追加 batch_size - 1 张
        for _ in range(batch_size - 1):
            best, best_score = None, float('inf')
            for cand in available:
                # 与 batch 内现有样本的总共现次数（越小越好）
                score = sum(cooccurrence_matrix.get(tuple(sorted([cand, b])), 0) for b in batch)
                if score < best_score:
                    best, best_score = cand, score
            batch.append(best)
            available.discard(best)
        batches.append(batch)
        # 更新共现矩阵
        for i in range(len(batch)):
            for j in range(i+1, len(batch)):
                pair = tuple(sorted([batch[i], batch[j]]))
                cooccurrence_matrix[pair] = cooccurrence_matrix.get(pair, 0) + 1
    return batches
```

### 4.2 终止条件

Shuffled Re-induction 必须有**多重客观终止条件**（任一命中即停）：

| 终止条件 | 默认值 | 含义 | 适用场景 |
|---|---|---|---|
| **Cond A**：共现矩阵填充率 ≥ θ_cov | θ_cov = 0.7 | 70% 的样本对已至少同 batch 出现过一次 | 主要终止条件 |
| **Cond B**：连续 K 轮新 feature 产出率 < 1 | K=3 | 3 轮没有新 feature 涌现 → 信号枯竭 | 收敛检测 |
| **Cond C**：累积 Opus token 消耗 ≥ max_cost_tokens | 200K（用户配置）| 成本守门员 | 经济条件 |
| **Cond D**：用户配置 max_rounds 已达 | 5（默认）| 硬上限 | 防止失控 |

**实现细节**：

- 每轮结束时计算 4 个 cond，打印当前状态："cond A: 0.42 / 0.7, cond B: 1 / 3 rounds without new, cond C: 87K / 200K tokens, cond D: 3 / 5 rounds"
- 任一命中即停，输出"由 cond X 终止"
- 用户可用 `--ignore-cond {a,b,c,d}` 禁用某些条件（不推荐，但保留出口）

### 4.3 盲跑要求（防 reward hacking）

**强制约束**（与 [spec §4.3] 一致）：

1. **Inducer prompt 不变**：和原始 batch ingest 的 prompt 模板完全一致，不加 "this is a shuffled batch" 等任何提示
2. **nl_description 复用**：不刷新（与 [原 doc §2.5 Re-induction 复用 nl_description] 同源）
3. **batch_id 命名脱敏**：CLI 内部叫 `shuffle-r3-b2`，但传入 Inducer 的 batch_id 字段应该是 `B-{global_counter}` 或类似常规命名
4. **Inducer subagent 上下文最小化**：仅注入 batch 内的 (chart_path, nl_description) 列表 + 通用 goal，不注入任何元数据

### 4.4 L0 dedup 强化

**专用更严阈值**：

```yaml
# config/shuffled_reinduction.yaml
l0_cosine_threshold:
  default: 0.85           # 既有 ingest 路径用
  shuffled: 0.75          # Shuffled 产出 candidate 时用
l1_force_grey_zone: [0.75, 0.85]   # Shuffled candidate 落此区间强制走 L1
l1_equivalence_check_prompt_template: |
  对比规律 A 和 规律 B，在以下样本上的判读是否实质等价（即都判 yes 或都判 no）？
  - 实质等价 → 输出 EQUIV
  - 实质不同 → 输出 DIFFERENT
  - 难以判断 → 输出 AMBIG
  规律 A: {feature_old.text}
  规律 B: {candidate_new.text}
  样本 nl_description:
  ...
```

L1 输出 `EQUIV` → 不新增 feature，但把 candidate 的 supporting_samples 作为对 F-old 的 Path V 事件累加（增强 F-old 的 α），变相提升 Shuffled 的产出价值。

### 4.5 Provenance 标签 + 延后提升

新增 feature yaml 字段：

```yaml
provenance:
  origin: original | shuffled | reinduction | replay
  origin_round: int | null         # shuffled 时为该轮编号
  promotion_lock: bool             # shuffled 产出默认 true
```

**提升锁规则**：

- `provenance.origin = shuffled` 时，feature 的 status_band 计算使用更严的 P5 阈值（θ_consolidated 从 0.40 提到 0.50, θ_strong 从 0.60 提到 0.70）
- 直到该 feature 收到至少 1 条 `source != shuffled` 的 ObservationLog（即被原始 ingest 或 incremental 验证）→ `promotion_lock = false`，恢复正常阈值

**理由**：Shuffled 产出的 feature 在被新数据独立验证之前，统计上"未受外界冲击"，应保守对待。

### 4.6 epoch_tag 命名

延续 [原 doc §2.4] 的 epoch_tag 命名规范，新增：

- `shuffle-{round_id}-{batch_idx}` —— 如 `shuffle-r3-b2`
- 与 `replay-after-split-{batch_id}` / `reinduction-{batch_id}` 并列

ObservationLog 的 `inducer_context.archetype_hint_hash` 在 Shuffled 时**强制为 "disabled_shuffle"**（详见 §5.2）。

### 4.7 CLI 接口

```
feature-mine reshuffle \
    --rounds 5 \                                  # 最大轮数（cond D）
    --batch-size 10 \                             # 每个 batch 大小
    --strategy {random|anti-correlated|stratified-band} \  # 默认 anti-correlated
    --max-cost-tokens 200000 \                    # cond C
    --cov-threshold 0.7 \                         # cond A
    --no-progress-rounds 3 \                      # cond B
    --include-bands {strong,consolidated,candidate,supported,forgotten}* \   # 默认全部
    --exclude-samples S03,S07 \                   # 黑名单
    --dry-run                                     # 仅估算成本，不真跑
```

**dry-run 输出示例**：
```
[Shuffled Re-induction Plan]
  Strategy: anti-correlated
  Total samples available: 87 (after filters)
  Planned rounds: 5
  Planned batches per round: 8 (= ceil(87/10))
  Total Opus calls: 40
  Estimated tokens: 40 * 50K = 2M (input+output)
  Estimated cost: ~$80 USD (Opus 4 pricing as of 2026-04)
  Stop conditions:
    A. Coverage threshold: 0.7 (current: 0.18)
    B. No-progress rounds: 3
    C. Max tokens: 200,000  ← will stop here at ~5 batches
    D. Max rounds: 5
  Conflict warning: cond C will likely trigger before cond A — increase --max-cost-tokens or accept partial coverage
```

### 4.8 工程量估算

| 子任务 | 工程量 |
|---|---|
| 共现矩阵存储（feature_library/cooccurrence.yaml）+ 增量更新 | 0.5 天 |
| 5 种策略实现（核心是 anti-correlated 贪心）| 1 天 |
| 终止条件评估器（4 cond）| 0.5 天 |
| L0 强化 + L1 等价性检测 | 0.5 天 |
| Provenance 字段 + 延后提升锁 | 0.5 天 |
| CLI 接口 + dry-run | 1 天 |
| 单元测试 + 集成测试 | 1 天 |
| **合计** | **5 天** |

可放入 [spec §5.4 Phase 4+]，作为可选增强项。

---

## §5 与 Q1 / Q3 的耦合

### 5.1 与 Q1（Python CLI 调度）的耦合

完美契合 [原 doc §1] 推荐的 Python CLI 哲学：

- 完全用户触发：`feature-mine reshuffle ...`
- 调度逻辑全部 Python 确定性（共现矩阵贪心 + 终止条件评估）
- 没有"系统自动决定何时 reshuffle"的需求

**唯一新增的库结构**：

- `feature_library/cooccurrence.yaml`（增量维护）

```yaml
# feature_library/cooccurrence.yaml
schema_version: 1
last_updated: 2026-04-26T...
total_pairs: 4950          # C(100, 2)
covered_pairs: 891         # 至少同 batch 1 次
coverage_ratio: 0.180      # 派生
matrix:
  S01-S02: 1               # 共现次数
  S01-S05: 2
  ...
```

**写入时机**：
- 每次 `feature-mine ingest` 后追加（按本次的 batch 划分更新）
- 每轮 Shuffled Re-induction 后追加

**对 [原 doc Q1] 的影响**：仅在 [原 doc D5] 工程量上多 0.5 天（共现矩阵基础设施）。其他改动可全部沉淀到 Phase 4+。

### 5.2 与 Q3（archetype hint）的耦合

[原 doc §4.2 Q2 ↔ Q3] 已确立硬约束："epoch>0 时强制禁用 archetype hint"。Shuffled Re-induction **完全继承**该约束：

- Shuffled 触发的 Inducer 调用，CLI 强制 `--no-archetype-hint`，不允许用户 override
- ObservationLog 的 `inducer_context.archetype_hint_hash` 字段在 Shuffled 时记 `"disabled_shuffle"`，与 epoch>0 的 `"disabled_replay"` 形成一致命名族

**为何这条约束对 Shuffled 同样适用？**

- archetype hint 把库现状告诉 Inducer，Shuffled 又让同样的样本反复进 Inducer → 二者叠加 = Inducer 在不同轮次看到不同 hint → 输出分布漂移 → reward hacking 复利
- 这是 [原 doc §4.2] 已识别的复利风险，机理在 Shuffled 上完全同构

### 5.3 与 Q2 既有机制（Replay / Re-induction）的执行顺序

在一次 `feature-mine ingest` 周期内，三/四机制的推荐顺序：

1. **Step 1：Replay**（如果 pending_replays 非空，CLI 阻塞等用户消费 —— [原 doc §2.5]）
2. **Step 2：Ingest**（用户的本次正常 ingest）
3. **Step 3：Re-induction**（用户主动，覆盖怀疑挖不充分的孤儿）
4. **Step 4：Shuffled Re-induction**（用户主动，探索新组合空间）

**为什么 Shuffled 在最后**：

- Replay 必须先做，否则 (α, β) 数学不一致
- Ingest 必须做，否则没有新数据
- Re-induction 优先于 Shuffled，因为 Re-induction 处理的是"明确没挖到"的子集，价值密度高
- Shuffled 是探索性增量，价值密度较低，放最后

**强烈建议**：CLI 在 Shuffled 执行前显示提示："建议先确认 pending_replays 已消费、本次 ingest 已完成、孤儿样本已 review"。

### 5.4 与 [原 doc §2.7 推荐表] 的关系

原推荐表（[原 doc §2.7]）有 5 行：

1. Replay 必做
2. Re-induction 可选实现
3. Re-verification 保持现状
4. 新增 epoch_tag 字段 + rollback 模式
5. 双重计数边界由 Librarian 统一拦截

**应在第 2 条后追加第 2b 条**：

> **2b. Shuffled Re-induction 可选实现，留作 Phase 4+ 增强**。默认策略 anti-correlated；通过 `feature-mine reshuffle` CLI 触发；强制盲跑 + 强制禁用 archetype hint + 专用更严 L0 阈值 + provenance 提升锁。终止条件以 4 cond 任一命中为准。

---

## §6 推荐与等级

### 6.1 是否引入 — Conditional Yes

**是否引入 Shuffled Re-induction？答案：Conditional Yes。**

| 条件 | 是否满足时引入 |
|---|---|
| **库已有 ≥ 30 张样本 + ≥ 5 条 strong/consolidated feature** | 必要条件 — 否则组合空间小，过拟合风险大 |
| **[原 doc Q1] 推荐方案 C（Python CLI）已落地** | 必要条件 — 必须有 CLI 容器承载 |
| **[原 doc §2.4] epoch_tag + rollback 模式已实施** | 必要条件 — 否则会出现双重计数 |
| **用户主动触发** | 必要条件 — 永不自动跑 |
| **dry-run 成本预估满足用户预算** | 必要条件 — 否则永远只跑 dry-run |

**所有必要条件满足时**，Shuffled Re-induction 是**有价值的探索增量机制**。

### 6.2 命名定位

**作为第 4 机制独立命名**：`Shuffled Re-induction`，不归并到 Re-induction 子模式。

**理由汇总**（与 §1.2 一致）：算法独立、风险曲线独立、CLI 命令独立、终止条件独立。归并会让原 Re-induction 的"用户选样本"语义被冲淡。

### 6.3 必做 / 可选 / 禁止 矩阵

| 场景 | 做法 |
|---|---|
| **必做** | dry-run 必须先跑；anti-correlated 策略必须作为默认；epoch_tag 命名必须唯一；盲跑必须强制；archetype hint 必须互斥；provenance 提升锁必须启用 |
| **可选** | random / stratified-band 策略；用户配置共现率阈值；多轮自动检查终止条件 |
| **禁止** | stratified-by-source-feature 策略（违反 [spec §4.3]）；自动调度 Shuffled（必须用户触发）；< 30 样本时启用；epoch>0 时启用 archetype hint |

### 6.4 默认参数推荐

| 参数 | 默认值 | 选择理由 |
|---|---|---|
| `strategy` | anti-correlated | §4.1 论证 |
| `rounds` | 5 | 实证不足，先取保守值；与 [原 doc Q2 推迟到 Phase 4+] 节奏一致 |
| `batch_size` | 10 | 与 [spec §2.2] cold-start batch 8~12 张默认值对齐 |
| `cov_threshold` | 0.7 | 共现 70% 时多数潜在跨 batch feature 已被采样 |
| `no_progress_rounds` | 3 | 经验值，3 轮无产出说明信号枯竭 |
| `max_cost_tokens` | 200K | 约 4 个 batch 的 Opus 调用，控制单次操作成本 |
| L0 cosine 阈值（Shuffled 专用）| 0.75 | 比 default 0.85 更严，降低语义近亲风险 |

### 6.5 Phase 路线建议

| Phase | 包含范围 |
|---|---|
| **Phase 4a** | 共现矩阵基础设施 + random + anti-correlated 策略 + 4 cond + dry-run + L0 强化 + provenance 锁 |
| **Phase 4b**（可选）| stratified-band 策略 + L1 等价性检测的精细化 |
| **永不**（Phase ∞）| stratified-by-source-feature 策略（违反硬约束） |

**Phase 4a 工程量约 5 天**（详见 §4.8）。

### 6.6 与 [原 doc §2.7 推荐表] 的最终融合

更新后的推荐表（在原 5 条基础上插入 2b）：

| # | 推荐 | 优先级 |
|---|---|---|
| 1 | Replay 必做 | P1 |
| 2 | Re-induction 可选实现 | P2 |
| **2b** | **Shuffled Re-induction 可选实现，作为 Re-induction 的算法化超集** | **P3（Phase 4+）** |
| 3 | Re-verification 保持现状 | P0（已存在）|
| 4 | 新增 epoch_tag 字段 + rollback 模式 | P1 |
| 5 | 双重计数边界由 Librarian 统一拦截 | P1 |

---

## §7 对原 doc 的 delta 建议

> **本节仅列变动建议，不修改 `feature_mining_orchestration_revisit.md`。是否合并由用户决策。**

### 7.1 必改（如果决定引入 Shuffled Re-induction 到 spec）

| Δ ID | 章节 | 修订要点 |
|---|---|---|
| **R1** | §2.3 三机制对比表 | 增加第 4 行 "Shuffled Re-induction"：含义="老样本进 Inducer，batch 组合主动改变"，触发条件="用户显式 `feature-mine reshuffle`"，注解=见 §2.x（新增）|
| **R2** | §2.5 触发权归属表 | 增加第 4 行 "Shuffled Re-induction"：触发模型="完全用户触发"，推荐选项="dry-run 默认；anti-correlated 默认；专用 L0 阈值 0.75" |
| **R3** | §2.6 触发场景表 | 增加新行 "用户已挖了几轮，怀疑老样本之间还有未发现的跨 batch 规律" → "Shuffled Re-induction" |
| **R4** | §2.7 推荐 + Tradeoff | §6.6 已给出修订后表格，原表插入 2b 行 |

### 7.2 可选（如果想让 doc 更完整）

| Δ ID | 章节 | 修订要点 |
|---|---|---|
| **R5** | §4.2 Q2 ↔ Q3 风险表 | 在原 "epoch>0 时禁用 archetype hint" 行下追加 "Shuffled Re-induction 时禁用 archetype hint"（同条硬约束的扩展应用）|
| **R6** | §5.2 可选 delta 表 | 新增 D13: features yaml 新增 `provenance` 字段；新增 D14: feature_library/cooccurrence.yaml 文件；新增 D15: §4.4 Librarian 接口新增 `update_cooccurrence(batch_samples)` 方法 |
| **R7** | §5.4 修订优先级 | P3 行下追加 "Shuffled Re-induction 整套 → Phase 4+ 单独工程" |
| **R8** | §6 未解问题 | 追加 Q9: Shuffled Re-induction 的最优终止条件组合（4 cond 是否充分？是否需要"feature 多样性指标"作为 cond E？）|

### 7.3 不建议改

| Δ ID | 章节 | 理由 |
|---|---|---|
| **R9** | §2.4 epoch_tag + rollback 模式 | Shuffled 完全复用此机制，无需修改 |
| **R10** | §3.5 L2 archetype hint 安全升级路径 | Shuffled 不影响这条路径；二者互斥已在 §4.2 处理 |
| **R11** | §4 三问交叉影响整体结构 | Shuffled 加入后仍是"Q1+Q2 强契合，Q2+Q3 必须互斥，Q1+Q3 解耦"的格局，无需重写 |

### 7.4 修订优先级

| 优先级 | Δ 集合 | 理由 |
|---|---|---|
| **R-P0**（如要落地）| R1, R2, R3, R4 | 核心机制定义 |
| **R-P1**（建议同步）| R5, R6 | 与既有约束 + schema 一致性 |
| **R-P2**（按需）| R7, R8 | 路线图与开放问题 |

---

## §8 未解问题

1. **Π_K=2 的真实分布如何测**？§2.2 用了"60/30/10"启发式估算受影响 feature 占比。第一次 Shuffled Re-induction 跑完后，可以从"原始 ingest 没产出 / Shuffled 才产出"的 feature 比例反推真实 Π，校准估算
2. **共现矩阵规模的硬上限**？N=1000 时矩阵有 ~50 万对，YAML 序列化可能慢。是否要切到 SQLite？建议 N ≥ 500 时再考虑
3. **Anti-correlated 贪心的次优性是否可接受**？§4.1 给的算法是简单贪心。理论上整数规划（IP）可达全局最优，但单次求解时间可能超过 Opus 调用本身。是否值得？
4. **多次 reshuffle 的样本生命周期管理**？例如某条 feature 被 Shuffled-r2 创建、Shuffled-r4 又"重新发现"。两次发现是否算同一 feature 的两次观察？epoch_tag 不同，但 candidate 文本可能高度相似 —— 是否触发 L1 等价性检测？建议：一律走 L1，等价则归并
5. **Provenance 提升锁的解锁条件是否过严**？要求"至少 1 条 source != shuffled 的事件"才解锁，可能导致 Shuffled 产出的 feature 永远停在 candidate 状态（如果用户只跑 Shuffled 不再 ingest）。是否要给"M 轮 shuffle 持续验证后强制解锁"的退路？倾向于保守 —— 不给退路，强迫用户用真新数据验证
6. **与 [spec §备选 5] 的对比**："单图 Inducer + 让 Beta-Binomial 自己累积" 已被否决（虚假经济）。Shuffled Re-induction 是否会面临类似批评 —— "把同样的图反复给 Inducer，让它从噪声中找规律"？答：本质不同，Shuffled 仍是多图对比（B=10，比单图能力强），且 anti-correlated 策略避免重复采样
7. **是否需要"按 feature 子集"的局部 Shuffled**？用户可能想"我只想看看 F-001 / F-002 的支持样本能不能产 F-001a / F-002a 这样的细分"。这其实是 [原 doc §2.6] Critic split 触发场景的子集，可由 `feature-mine reshuffle --include-features F-001,F-002` 实现。但要注意：把 sample 选择限定到几条 feature 的 supporting_samples 上，会引入信息泄露风险（接近 §4.1 策略 5），需要专门评估
8. **CLI 是否提供"自动循环"模式**？类似 `feature-mine reshuffle --auto-until-cond`，自动反复跑直到任一 cond 终止。倾向于不提供，违反 [原 doc Q1] 用户驱动哲学

---

## §9 一段话最终结论

**Shuffled Re-induction（打乱重组 batch）是 Re-induction 的算法化超集，应作为第 4 机制独立命名引入。** 理论价值来源于"组合可见性增益"：N=100, B=10 时 91% 样本对从未同 batch 出现，最多 36% 潜在 feature 被原始 ingest 遗漏。但叠加了"语义近亲家族"、reward hacking、过拟合训练集、L0 dedup 失效、成本爆炸等新风险。所有风险均可通过工程化方案缓解：anti-correlated 策略 + 4 cond 终止 + 盲跑 + Shuffled 专用更严 L0 阈值 + L1 等价性检测 + provenance 延后提升锁 + dry-run。完全契合 [原 doc Q1] Python CLI 哲学；继承 [原 doc §4.2] "epoch>0 / shuffle 时禁用 archetype hint" 硬约束。Conditional Yes 引入：库 ≥ 30 样本 + Q1 已落地 + epoch_tag 已实施 + 用户触发 + dry-run 通过。归类 Phase 4+，工程量 ~5 天，作为 [原 doc §2.7 推荐表] 第 2b 条。**不修改既有 spec 主文档与 orchestration_revisit doc，仅以本文产出 delta 建议供决策。**

---

**文档结束。**
