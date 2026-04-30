# Feature Mining — 多模式样本与 mode 发现职能归属

> **日期**：2026-04-26
> **作者**：mode-discovery agent team（lead 整合 scope-arch / clustering / workflow 三专家两轮研讨）
> **关联 spec**：`docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md`（不修改，仅产出 delta 建议）
> **前置研究**：
> - `docs/research/feature_mining_v2_unified_decision.md`（Beta-Binomial 统一骨架 + §0.3 解耦原则定型）
> - `docs/research/feature_mining_orchestration_revisit.md`（CLI 调度 + 被动提醒哲学）
> - `.claude/docs/modules/数据挖掘模块.md`（mining 模块当前实现状态）
>
> **读者预设**：已读上述文档，本文不重述其设计

---

## §0 触发与范围

### 0.1 用户原文

> 1. 如果用户提供的 K 线集合包含不同模式的股票，每种模式由特定的 feature 集合构成，类似于 mining 模块得到的组合模板。那么本框架是否能够发挥类似于模板挖掘的功能。
> 2. 之前的预设是用户提供正样本，而我认为这种正样本应该包含隐含的条件，即这些正样本应该具有某些特定的 feature 组合。不然总结出的 feature 可能过于宽泛。
> 3. 那么如果用户提供了不同模式的股票集合，每个模式由特定的 feature 组合构成。是否应该让本框架发挥发现模式的功能。这是否可行？是否有必要？还是说最好让用户坚持提供单一模式的股票集合，以便更准确地总结出该模式的特征？

### 0.2 范围

- **本文聚焦**：feature-induction 框架是否应承担"样本异质性 / 多 mode 发现"职责
- **不在范围**：mining 模块自身的 template 挖掘算法改进（已成熟）
- **不修改**：spec 主文档、`feature_mining_orchestration_revisit.md`、`feature_mining_shuffled_reinduction.md`
- **产出形式**：本文 + spec delta 建议清单（§5），不实现任何代码

### 0.3 三专家分工

| 角色 | 关注面 | 主要贡献 |
|---|---|---|
| **scope-arch**（边界专家）| 框架 vs mining 职责分工、§0.3 解耦原则、§0.5 定义域哲学 | Q-vocab/Q-combo 切分、C 选项的"破坏性同构"诊断、A/B 推荐 |
| **clustering**（算法专家）| mode 发现的 5 种算法、信噪比量化、与 spec 数学骨架兼容性 | 5 算法对比表、Beta-Binomial 稀释量化（CH 罕见子结构 P5 比较）、HDBSCAN 决策树 R0-R7 |
| **workflow**（用户体验）| CLI 接口、用户体验矩阵、archetype vs template 命名 | 三类用户矩阵、archetype 命名建议、`--strict-archetype` flag、3 个新 CLI 子命令 |

### 0.4 三轮交互摘要

- **轮 1**：3 专家各自独立分析（scope-arch 推 B；clustering 量化稀释问题、推 pre-induction 聚类；workflow 提"mode/template 命名冲突"诊断）
- **轮 2**：lead 追问（scope-arch §0.3 修订与 mining 存续；clustering K 决策树与建议权；workflow 默认行为与回退开关）
- **轮 3**：clustering 给出 R0-R7 决策树 + 推荐 (b) 报警拍板；workflow 给出 archetype 命名 + `--archetype` / `--strict-archetype` CLI；scope-arch 强化 A+B 推荐
- **共识**：A 兜底 + B 在 Phase 4+ 评估；C 永远拒绝（违反 §0.3/§0.5/§备选 4/5/7/8）；命名采用 archetype 区隔 mining template

---

## §1 用户问题诊断

### 1.1 用户洞察的内核

用户的关键直觉：**"正样本应包含隐含的特定 feature 组合条件"**。这指向一个深层观察——**Inducer 的 multi-image 对比机制要求样本在某种"应共有的特征"上同质**。如果 batch 内样本来自多个隐含 mode，跨样本对比时 Inducer 倾向于找各 mode 都共享的"最大公约数"（往往是宽泛特征如"价格在区间内盘整"），而 mode-specific 的窄信号会被双重过滤掉：

1. **Inducer K≥2 门槛**（spec §备选 5 同款约束）：mode-specific feature 在单 batch 内出现次数不够，Inducer 不报候选
2. **Beta-Binomial 沉默样本累 β**：即便偶尔出现，β 累积速度 > α → P5 落入 forgotten 带

### 1.2 三个可分离子问题

用户原文实际混合了三个**性质不同**的问题，必须先切分才能正确处置：

| 编号 | 子问题 | 性质 | 已有 spec 应对 |
|---|---|---|---|
| **Q-narrow** | 总结出的 feature 过于宽泛 | feature 描述粒度 | Critic split + reinduce（§4.5 / §2.6）|
| **Q-mode** | 多 mode 样本被混挖会失败 | 样本层异质性 | **无**（spec 默认假设单一定义域）|
| **Q-template** | 框架能否输出 mode-tagged feature 组合（类似 template）| 输出 schema 边界 | **明确不输出**（§0.3 解耦） |

混淆这三者会导致错误结论。三者的正确分工：
- **Q-narrow** → 现有机制充分，本研究**不再处理**（详见 §6 回顾）
- **Q-mode** → 本研究核心，§2 / §4 详谈
- **Q-template** → §0.3 已永久划归 mining，本研究**不动**

### 1.3 量化证据：混合 mode 的稀释代价

clustering 专家给出的具体场景（100 张样本：30 cup-and-handle / 40 head-and-shoulders / 30 consolidation，B=10，Jeffreys prior，θ_candidate=0.05）：

| Feature 类型 | 单一 mode 投放下 P5 | 混合 mode 投放下 P5 | 状态变化 |
|---|---|---|---|
| 跨 mode 强信号（"突破日大量"）| ~0.74 strong | ~0.74 strong | 不变（但语义宽泛 → 价值低）|
| CH 杯柄信号（mode 内 30/30）| ~0.90 strong | ~0.31 supported | **降级 2 档** |
| CH 子结构（mode 内 10/30）| ~0.40 consolidated | < 0.05 forgotten | **永久丢失** |
| CH 罕见子结构（mode 内 5/30）| ~0.18 candidate | ≪ 0.05 forgotten | **永久丢失** |

**关键结论**：用户的直觉**是对的**——没有 mode 约束的混合投放会让 mode-specific 弱信号永久丢失。这不是 Inducer 能力问题，是统计稀释问题。

### 1.4 当前 spec 对此盲点的意识程度

scope-arch 专家分析：spec §0.5"用户挑选即定义域"是**哲学**，不是**操作约束**。spec 默认假设"用户挑选 = 单一定义域"，但**没有显式机制保证或验证此假设**。当用户实际挑选含多 mode 时：

- spec **沉默接受**（A 选项默认行为）
- 用户**无任何反馈**知道自己挑错（沉默错误）
- 反馈周期：要等 add-new-factor → mining OOS lift 偏低，才反推回到挑选阶段（**周期数周**）

**结论**：spec 当前对"用户可能挑错"这个边缘情形是**盲点**。本研究的核心价值是把这个盲点显性化，并给出合理处置（B 方案 Phase 4+ 评估）。

---

## §2 三个候选方案

### 2.1 方案 A：用户责任（强制单一 mode 投放，含 --archetype 命名空间设计）

**机制**：用户在 dev UI 挑选阶段自行确保单一形态；不同 mode 分批投放；CLI 引入 `--archetype <name>` 命名空间隔离不同 mode 的 features。

**CLI 草案**（workflow 专家）：

```bash
# 显式 archetype：用户已知 mode，命名空间隔离
feature-mine ingest *.png --archetype cup-handle --batch-size 10
# → features/<archetype>/F-001.yaml；不跑 T_heterogeneity 检测（用户已声明）

# 严格 archetype：用户主动签订契约
feature-mine ingest *.png --strict-archetype cup-handle --batch-size 10
# → 若内部 silhouette > 0.55 则 ERROR 阻塞（用户声明单 archetype 后框架帮把关）
```

**`--tag` vs `--archetype` 的语义区分**（workflow 关键洞察）：
- `--tag exp-2026-04`：审计 metadata（实验名/批次号），不影响存储结构
- `--archetype cup-handle`：命名空间分区，参与 features 库结构 — 同名 candidate 在不同 archetype 下视为不同 feature
- 两者**正交保留**

**优点**：
- 0 工程量（命名空间是文件系统事）
- 完全保留 §0.3 解耦
- 完全保留 §0.5 定义域哲学
- mining 职能完整
- 显式控制，符合专家用户心智模型

**缺点**：
- **沉默错误**（最大缺点）：用户判断错误时无任何反馈
- 学习曲线高：初学者需先懂"什么是 archetype"才能用
- 误投损失检测责任链长：用户 → mining 验证 OOS 偏低 → 反推 mode 错配（周期数周）

### 2.2 方案 B：框架辅助（被动提醒 + helper，检测异质性）

**机制**：框架在 ingest 启动前对样本做轻量异质性检测（fastembed nl_description embedding + HDBSCAN）→ 若发现潜在多 mode → 打印 [SUGGEST] / [WARN] 提示用户拆分 → **不做实质聚类、不修改 feature schema、不修改 (α, β)**。

**异质性信号候选**（clustering + scope-arch 整合）：

| 信号 | 计算 | 阈值（需实证）|
|---|---|---|
| **样本 nl_description embedding 离散度** | fastembed → cosine 距离方差 | silhouette ≥ 0.30 触发 SUGGEST |
| **L0 归属冲突率** | candidate 在 batch 内对老 feature 的归属判断"分裂"比例 | > 30% |
| **Inducer K/N 比异常** | 同 batch 多 candidate 的 K/N 普遍极低 | < 0.30 |

**检测时机**（clustering 第 3 轮关键修订）：**ingest 启动前阻塞**而非"末尾打印"。理由：聚类决策一旦走错就要 rollback 整个 epoch，不能事后补救。

**新增 CLI 子命令**（workflow 提议）：

```bash
# 事前 preview：不入库，零成本探查
feature-mine preview *.png
# → "30 张样本可能含 2-3 cluster (silhouette=0.58)，代表样本 [S03,S15,S27]"

# 后查：当前 archetype 库或最近一次 batch
feature-mine analyze-archetypes [--last-batch | --library | --archetype <name>]

# 反向工具：检查某 feature 内部异质（feature 内 archetype 分裂）
feature-mine cohesion <feature-id>
```

**优点**：
- 守住 §0.3 解耦（不输出组合，不看 label）
- 守住 §0.5 定义域（用户仍是定义域唯一定义者）
- 与 §2.3 触发清单"被动提醒模式"哲学一致（融入零侵入）
- 工程量轻（fastembed + HDBSCAN ~1-2 天）
- mining 职能完整
- 对三类用户都"无害"（workflow UX 矩阵）

**缺点**：
- 阈值需要实证校准（首批 ingest 缺历史分布参考）
- 仍可能漏报（用户挑了两组接近但不同的形态，silhouette < 0.30）
- 仍可能误报（同质样本被切成假性多 mode）

### 2.3 方案 C：框架接管（自动 mode 聚类 + 多套库）

**机制**：样本聚类（如 KMeans / HDBSCAN on chart embedding）→ 每 cluster 独立 induction → feature 携带 `mode_tag` → 输出 mode-tagged feature 集合 → Librarian 库结构按 mode 分目录。

**5 种聚类算法对比**（clustering 专家详细评估）：

| 算法 | 输入 | 计算成本 | 可解释性 | 与 spec 兼容性 | 推荐度 |
|---|---|---|---|---|---|
| **A. 视觉 embedding 聚类**（CLIP/DINOv2 → HDBSCAN）| chart.png | 中（CLIP-ViT-B ~50ms × N，CPU 可跑）| 低（embedding 不可解释）| 高（不动 spec 角色，仅 CLI 加 `--cluster`）| ★★★★ |
| **B. Feature presence 向量聚类**（先一遍 Inducer 出宽泛 features → 0/1 向量 → KMeans）| samples + 第一遍 Inducer 输出 | 高（先付一次完整 Opus 多模态成本）| 高（cluster 用 features 列表命名）| 中（与 multi-epoch 哲学冲突，需丢弃首轮 (α,β)）| ★★★ |
| **C. LLM 自反思**（Opus 一次看 N 张图回答"几种 archetype"）| chart.png + 一次 Opus 调用 | 极高（N>20 触发上下文崩塌 + 计费乘性增长）| 高（自然语言可读）| 低（违反 §1.1 三角色分工，是 spec §备选 7 已否决的"AI Orchestrator"变形）| ★★ |
| **D. 频繁项集挖掘**（Apriori/FP-Growth on `observed_samples`）| 跑过若干轮后的 sample × feature 二分图 | 低（FP-Growth 开销可忽略）| 高（feature 组合 → 样本群映射）| 高（features 库 ≥ 20 时可用，反向跑）| ★★★ |
| **E. 共现图 + 社群发现**（用 spec 已有 `cooccurrence.yaml` 跑 Louvain / spectral）| `cooccurrence.yaml` 共现矩阵 | 极低（networkx Louvain 秒级）| 中（社群无语义需事后看代表样本）| 极高（**零基础设施新增**——共现矩阵已为 reshuffle 服务而存在）| ★★★★ |

clustering 专家推荐：A 主路径 + E 辅助 + D 高级路径（按工程演进顺序）。

**致命问题**（scope-arch 专家诊断）：

1. **违反 §0.3 解耦**：mode = "feature 共现的 cluster"，与 mining template 在输出空间上**实质同构**，框架变成 mining 的上位替代。mining 的核心组合搜索（threshold_optimizer Step 3）被吃掉，仅剩"单 mode 内阈值微调"残骸。
2. **违反 §0.5 定义域哲学**：mode 发现假设"用户挑选包含多个隐藏定义域"，与"用户挑选即定义域"的 §0.5 前提**直接对立**。这不是技术问题，是哲学根基冲突。
3. **破坏 Beta-Binomial 数学严谨性**：cluster 边界本身是估计量（含噪声 + 含先验依赖）。一旦 (α, β) 在切分后的子样本集上累积，i.i.d. 假设被破坏，P5 失去校准意义。这与 §2.6 整套 i.i.d. 防御机制（epoch_tag / supersede / provenance 锁）的设计目标背道而驰。
4. **触发 reward hacking**：若 cluster 信息回灌给 Inducer，违反 §4.3 Inducer 盲跑硬约束（详见 spec §备选 8 否决理由）。
5. **C 选项实质上是 spec §备选 4/5/7/8 的组合**（详见 §3.3）。
6. **工程量数周**：聚类算法选型 + schema 改造（feature 加 mode_tag，ObservationLog 加 mode_membership）+ Critic 加 split-by-mode 动作 + Replay 机制重做 + Merge Semantics 三策略全部要扩展为 mode-aware。

### 2.4 三选项一览表

| 维度 | A. 用户责任 | B. 框架辅助 | C. 框架接管 |
|---|---|---|---|
| 新增机制 | `--archetype` 命名空间 | 异质性检测 + SUGGEST/WARN | 聚类算法 + per-cluster Inducer + mode-tagged schema + 跨 mode merge |
| §0.3 解耦原则 | 无影响 | 无影响 | **严重违反**（吃掉 mining 核心）|
| §0.5 定义域原则 | 一致 | 一致（用户最终决定）| **冲突**（自动判定 mode）|
| Beta-Binomial i.i.d. | 安全（archetype 内同质）| 安全（不动 (α,β)）| **破坏**（cluster 边界含噪声）|
| 误用风险 | **沉默错误**（最大）| 阈值实证期可能误报/漏报 | reward hacking + 探索崩塌 |
| 工程量 | 0 | ~1-2 天 | **数周（1.5x 现有 spec）** |
| mining 存在意义 | 完整 | 完整 | **退化为单 mode 阈值微调** |
| 用户认知负担 | 自我形态分组（高，需懂 archetype）| 中（按 SUGGEST 提示反应）| 低表面 / 高隐性（"mode_3 是什么？"）|
| 与现有触发清单融合度 | n/a | 高（§2.3 模式同构）| 低（需新指令分支）|

### 2.5 三方案 × 三类用户 UX 矩阵（workflow 专家）

| 用户类型 | A. 用户责任 | B. 框架辅助 | C. 框架接管 |
|---|---|---|---|
| **初学者** | ❌ 强迫做 mode 决策；不会分类就用错 | ✅ 默认无感，出错时被警告 | ⚠️ 黑盒；用户看到"mode_3"不懂含义 |
| **专家** | ✅ 显式控制，符合心智模型 | ✅ 可 `--quiet` 跳过提醒 | ❌ 框架代决策反而碍事，需 `--no-auto-mode` |
| **系统集成方** | ✅ 显式 `--archetype` 易脚本化 | ✅ 退出码语义稳定（WARN 不阻塞）| ⚠️ 自动决策破坏可重放性 |
| **学习曲线** | 高 | 低 | 中 |
| **误用代价** | 高（沉默错误）| 低（被警告）| 高（错聚类隐藏更深）|

**关键洞察**：A 把决策推给用户但不提供工具；B 提供工具但不强迫；C 替用户决策但用户不易察觉。**B 是唯一对三类用户都"无害"的方案**。

---

## §3 与现有 mining 模块的关系

### 3.1 mining 模块职能精确刻画

scope-arch 专家给出的 mining 4 步流水线本质：

| Step | 算法 | 性质 |
|---|---|---|
| Step 1 | data_pipeline：JSON → DataFrame，peak 聚类重建特征 | 数据准备 |
| Step 2 | factor_diagnosis：Spearman 单因子方向诊断 + 非单调检测 | 单因子方向 |
| Step 3 | threshold_optimizer：**二值化触发矩阵 + bit-packed 模板穷举** + Greedy Beam Search + Optuna TPE 联合搜索 + Bootstrap 稳定性验证 | **组合搜索 + 阈值优化** |
| Step 4 | template_validator：5 维度 OOS 验证 + 可选情感筛选 | 验证 |

**mining 的本质**：**后验型 supervised 阈值搜索**，组合空间 = 2^13 × 阈值离散网格。**输入 feature 集合已固定**（13 个，写死在 `factor_registry.py`），label 已知。mining **不发现 feature**，而是在已知 feature 池上做"哪个子集 + 哪组阈值能最大化 top-K 模板的 label median"的最优化。

### 3.2 互补 / 重叠 / 冲突

| 关系类型 | 内容 | 涉及方案 |
|---|---|---|
| **互补**（A/B 下成立）| feature-induction 输出 vocabulary（unsupervised, label-blind, 在 archetype 内）→ add-new-factor 编码 → mining 输出 template（supervised, label-aware, 全市场扫描）。两层串行，不竞争 | A、B |
| **重叠** | feature-induction 的 mode 输出（mode = feature 共现 cluster）和 mining 的 template 输出（template = factor 子集组合）在输出空间**实质同构**，只差一个 "label-aware" 修饰词 | C 触发 |
| **冲突** | C 选项下 mining 的核心组合搜索（Step 3）被 feature-induction 吃掉。mining 退化为"单 mode 内 13 维阈值微调"——核心算法（threshold_optimizer）失去存在意义 | C 触发 |

### 3.3 C 选项与 spec §8 已否决备选的同构关系

scope-arch 专家观察：C 选项的失败模式与 spec §8 已否决备选高度同构：

| spec §8 已否决 | 失败模式 | C 选项的对应失败 |
|---|---|---|
| 备选 4（algo 主导）| 小样本（<500 BO）阶段 GA / HMM / 图挖掘是"过拟合制造机" | 小样本聚类（<100 BO）的 cluster 边界完全是噪声 |
| 备选 5（单图特征 + Beta 累积）| 没有跨图对比的"显著性"过滤，特征数爆炸 | mode-tagged feature 数 = N_modes × 平均 feature 数，库爆炸 |
| 备选 7（AI Orchestrator）| 调度决策是确定性规则，AI 价值为零或负 | mode 切分是"用户挑选意图"的派生，自动聚类的 AI 价值为零或负 |
| 备选 8（Critic 重写 Inducer prompt）| 信息泄露 / reward hacking / 探索崩塌 | mode 信息回灌 Inducer 同样 reward hacking / 探索崩塌 |

**结论**：C 选项实际上是**多个已否决备选的组合**，按 spec 演化逻辑应直接拒绝。

### 3.4 若硬选 C，§0.3 该如何修订（scope-arch 二轮反直觉论证）

scope-arch 专家给出一个**反直觉**的判断：**单向耦合（"框架知道 mining template，mining 不知道框架"）反而比"彻底废除"破坏更大**。

| 修订路径 | 表面影响 | 实际副作用 |
|---|---|---|
| **A. 彻底废除 §0.3** | 失去一句叙述性原则 | 只要工程上保持"framework → mining"单向数据流（无回流），分层架构仍可维持。代价是失去一个文档化的不变量提示 |
| **B. 单向耦合（framework 看 mining）** | 听起来比"废除"温和 | **实质性反向回流**：(1) 触发 §备选 8 reward hacking（Inducer 知道 mining 已有什么 → 偏向产出近邻）；(2) mining template 变化时（如 Optuna 重跑）必须 invalidate framework mode 缓存，跨模块状态依赖；(3) 评估难度爆炸——任何 framework 输出回归测试都要 stub mining |

**结论**：C 真要做就**彻底废除 §0.3**（坦诚承认两层合一），别走"单向耦合"中间态。但更合理的是 C 本身被否决（详见 §5.3 R-1）。

### 3.5 mining 4 步在 C 选项下的存续（scope-arch 二轮）

| Step | 当前职能 | C 下的命运 | 存留判断 |
|---|---|---|---|
| **data_pipeline** | JSON → DataFrame + peak 聚类重建 | **保留**。物理数据准备与 mode 无关，per-mode 重跑即可 | ✅ 完整 |
| **factor_diagnosis** | Spearman 单因子方向 + 非单调检测 | **退化但保留**。每个 mode 内重做方向诊断（同一因子不同 mode 方向可能反转，这反而是 C 的"卖点"）| ⚠️ per-mode 复制 |
| **threshold_optimizer** | 二值化 + bit-packed 模板穷举 + Beam + Optuna TPE | **核心被吃掉**。组合搜索（"哪些 factor 子集"）已被 framework 的 mode 切分预先决定；剩下的只是"给定 mode 的固定 factor 子集，调每个 factor 的连续阈值"——退化为单纯的连续优化（Optuna 仍有用，但 Beam Search 失业）| ❌ 失去主算法 |
| **template_validator** | OOS + 5 维度判定 + 可选 sentiment | **保留且更必要**。OOS 验证、Bootstrap CI、sentiment 筛选与 mode 划分正交，反而需要 per-mode 各跑一次 | ✅ 完整 |

**净影响**：mining 失去**核心组合搜索（threshold_optimizer Step 3 的 Beam Search 部分）**，保留"per-mode 阈值微调 + 验证"。

### 3.6 mining 是否应被 feature-induction 吸收为 promotion gate（scope-arch 二轮）

scope-arch 判断：**仍值得独立存在**，但定位从"template 生成器"降为"per-mode validator + 阈值微调器"。

| 立场 | 论证 |
|---|---|
| **支持独立**（推荐）| (1) mining 持有 label-aware 验证管道（OOS / Bootstrap / sentiment）—— framework 始终 label-blind，吸收会污染 §0.3 残留语义；(2) 独立模块便于 add-new-factor 这种纯人工 promotion 路径继续存在（不经过 framework）；(3) 测试边界清晰 |
| **支持吸收**（不推荐）| 模块间通信成本上升、双方都要 per-mode loop、文档维护负担翻倍 |

**决策本质**：两层架构在功能压缩下是否仍优于一层？scope-arch 倾向**仍优**——label-aware 与 label-blind 的边界值得保留为模块边界。

### 3.7 命名冲突诊断（workflow 专家）

| 维度 | mining 的 **template** | feature-induction 的待命名概念 |
|---|---|---|
| **本质** | 数值因子的二值触发组合 | 样本子集的语义共性分群 |
| **操作层** | 已编码的 13 个数值因子 | 自然语言 feature 描述 |
| **目标** | 最大化 OOS label lift | 提高 feature 共识度 |
| **数学** | bit-packed 评估 + Optuna TPE | Beta-Binomial P5 + 文本聚类 |
| **粒度** | 因子级（同一批样本可命中多 template）| 样本级（一个样本属一个 group）|

**化解策略**（workflow 强烈推荐）：feature-induction 改用 **`archetype`**（原型），mining 保留 **`template`**。

**为什么 archetype 是最佳选择**：
- 不与 sklearn / 统计的 "mode of distribution" 冲突
- 中英术语区隔明确（archetype/原型 vs template/模板）
- CLI 体感好（`--archetype` 4 音节）
- 比 cohort（医学/统计太重）/ pattern_class（太长）/ mode（口语模糊）更精准

类比：
- template = 同一群病人按"治疗方案命中"分组（多治疗方案是常态）
- archetype = 同一群病人按"病种"分组（多病种通常意味着诊断室搞错了）

---

## §4 推荐 + tradeoff

### 4.1 决策：A 兜底 + B 在 Phase 4+ 评估；C 永久拒绝

**默认行为**（workflow 第 2 轮明确）：CLI 默认走 B（被动提醒），用户可显式 `--archetype` 升级到 A 命名空间隔离。

**理由综合**：

1. **守住 §0.3 解耦**（scope-arch 关键论证）：A 风险是用户在不知情下污染库；C 直接吃掉 mining；B 是中间地带——只做"信号"不做"决策"，与 §2.3 触发清单"被动提醒模式"哲学一致。

2. **避免哲学根基冲突**（scope-arch 三专家共识）：C 选项需要用户接受"我可能不知道自己挑了几种 mode"——与"用户挑选即监督信号"（§0.4 #2）+ "用户挑选即定义域"（§0.5）的核心定位矛盾。本框架 §0.4 第 2 条原话："用户挑选样本即监督信号"——意味着用户已有明确意图，框架应当信任而非二次解读。

3. **mining 存在意义不变**（架构判断）：mode 发现属于 supervised template mining 的语义范畴（"哪些 feature 共现 + 这组共现是否带来 label 提升"），应留给下游 mining 在 feature 已稳定后再做。**用户在 dev UI 阶段做"形态分组"，比在框架内做 unsupervised cluster 更可靠**——用户挑选时的形态意图是显性的，事后聚类是猜测。

4. **clustering 量化证据指向 pre-induction 聚类**（如必须做）：clustering 专家已证明 post-induction 聚类无法救回 mode-specific 弱信号（第一轮已被混合稀释污染）。如未来真的进入 C，必须 pre-induction，但这等于"自动判定 archetype"，回到哲学冲突。

5. **B 方案的技术可行性已验证**（clustering 给出 R0-R7 决策树）：
   - 默认 HDBSCAN（min_cluster_size=8）+ silhouette ≥ 0.30 双重门
   - K_max cap = max(3, ⌊N/16⌋)
   - 全 noise 时**绝不静默降级**（必须 WARN）
   - 推荐 (b)：报警 + 用户拍板（不自动执行 cluster，不强制 exit 1）

### 4.2 tradeoff 详细对比

| 决策维度 | A | B | C |
|---|---|---|---|
| **代价**（实施成本）| 0（命名空间是文件系统事）| ~1-2 天（fastembed + HDBSCAN + SUGGEST 文案 + 3 新 CLI 子命令）| 数周（1.5x spec 总工程量）|
| **代价**（哲学）| 把"用户必须懂 archetype"的隐式预设变显式 | 接受"框架可能误报/漏报"的容忍度 | 与 §0.3/§0.5 根本冲突（不可接受）|
| **代价**（可重放性）| 高（用户显式 `--archetype`）| 高（仅打印不动状态）| 低（自动聚类破坏同输入同输出）|
| **收益**（防止稀释）| 高（archetype 内同质）| 中（依赖用户响应 SUGGEST）| 高（但代价不可接受）|
| **收益**（用户体验）| 专家友好，初学者障碍 | 全用户友好 | 表面友好，隐性高 |
| **收益**（与 mining 协作）| 完整 | 完整 | 破坏 |
| **适用场景** | 有明确 archetype 意图的专家用户、CI 集成 | 默认通用场景、初学者、混合用户 | 无明确适用场景（已否决）|

### 4.3 用户场景适用性矩阵

| 场景 | 推荐方案 | CLI 模式 |
|---|---|---|
| 用户首次接触框架，不确定自己挑得纯不纯 | B（默认）| `feature-mine ingest *.png` → 看 SUGGEST 决定 |
| 用户已有形态学认知，明确知道这批是 cup-handle | A（显式）| `feature-mine ingest *.png --archetype cup-handle` |
| 用户挑得很严，要求框架帮把关 | A 严格模式 | `feature-mine ingest *.png --strict-archetype cup-handle`（silhouette > 0.55 则 ERROR）|
| 系统集成方在 CI 脚本里跑 | A（显式）| `--archetype` + `--quiet` 屏蔽 SUGGEST 输出 |
| 老库已有数据，事后想验证是否纯 | B 后查 | `feature-mine analyze-archetypes --library` |
| 怀疑某 feature 跨 archetype 混了 | B 反查 | `feature-mine cohesion <feature-id>` |

### 4.4 B 方案落地决策树（clustering 专家 R0-R7）

```
def decide_clustering(samples, user_explicit_archetype=None):
    N = len(samples)

    # R0: 用户显式声明 archetype - 跳过检测
    if user_explicit_archetype is not None:
        return ARCHETYPE_FORCED(name=user_explicit_archetype)

    # R1: 样本太少
    if N < 24:
        return WARN_AND_SINGLE(
            msg="样本 < 24，聚类无统计意义。如确信多 archetype，请用 --archetype 显式指定")

    # 跑 HDBSCAN(min_cluster_size=8)
    labels = hdbscan(embeddings)
    K = count_clusters(labels)
    noise_ratio = count_noise(labels) / N
    sil = silhouette_score(...) if K >= 2 else None
    K_max = max(3, N // 16)

    # R2: 全 noise → 显式 WARN，绝不静默降级
    if K == 0:
        return WARN_AND_SINGLE(
            msg=f"[WARN] 未发现结构（{N} 张全归 noise）。可能：(a) 同质 (b) embedding 不敏感。"
                f"如疑虑多 archetype：--archetype <name> 强制 / 或先 ingest 一轮再用 reshuffle 验证")

    # R3: K=1 + 大量 noise
    if K == 1 and noise_ratio > 0.3:
        return WARN_AND_SINGLE(
            msg=f"[WARN] 1 主簇 + {noise_ratio:.0%} 离群。离群可能是少数 archetype。"
                f"建议 review-orphans 或 --archetype 强制")

    # R4: K=1 干净
    if K == 1:
        return SINGLE(msg="样本同质，单 batch ingest")

    # R5: 2 ≤ K ≤ K_max + silhouette 良好
    if 2 <= K <= K_max and sil >= 0.3:
        return SUGGEST_AND_BLOCK(  # 阻塞 ingest，等用户拍板
            k=K, silhouette=sil,
            msg=f"[SUGGEST] 检测到 K={K} archetype 簇 (sil={sil:.2f})。"
                f"运行 --archetype <name> 分批 ingest / --archetype none 拒绝建议继续")

    # R6: K > K_max
    if K > K_max:
        K2 = retry_hdbscan(min_cluster_size=12)
        if K2 <= K_max and sil_K2 >= 0.3:
            return SUGGEST_AND_BLOCK(k=K2, ...)
        return WARN_AND_SINGLE(
            msg=f"[WARN] 检测到 K={K} 过多，疑似碎片化。建议先单 batch ingest 看 features")

    # R7: K ≥ 2 但 silhouette < 0.3
    return WARN_WITH_HINT(
        msg=f"[WARN] 边界模糊（K={K}, sil={sil:.2f}）。建议 dev UI 手工 archetype tag")
```

**关键设计原则**（clustering 第 3 轮）：
- **R5 是唯一阻塞 ingest 的分支**（聚类决策一旦走错就要 rollback 整个 epoch）
- 其他分支只 WARN，不阻塞
- 默认走"报警 + 用户拍板"模式（不选自动建议执行，不选强制 exit 1）

---

## §5 对 spec 的 delta 建议（按必改/可选/不建议改三档）

### 5.1 必改（0 项）

**无**。本研究的核心结论是"不要修订 spec 主体"。这是有意识的保守——A 方案 0 工程量、B 方案 Phase 4+ 评估，均不需要现在改 spec。

### 5.2 可选（5 项，建议 Phase 4+ 启动时再评估）

| # | 修订项 | 位置 | 内容 | 触发条件 |
|---|---|---|---|---|
| **D-1** | 新增 `--archetype` CLI 子选项 | spec §1.1 / §2.2 CLI 定义 | `feature-mine ingest <samples> --archetype <name>` 命名空间分区，与 `--tag` 正交 | A 方案启动时 |
| **D-2** | 新增 `--strict-archetype` CLI flag | spec §1.1 CLI | 用户主动签订契约，silhouette > 0.55 则 ERROR 阻塞 | A 方案严格模式启动时 |
| **D-3** | §5.6 增列搁置项 | spec §5.6（不在本期范围）| "样本异质性自动检测（multi-archetype discovery）：B 方案 Phase 4+ 评估，C 方案永远不做（违反 §0.3 / §0.5）" | 现在即可加（仅文档说明）|
| **D-4** | §7 新增 Q20 | spec §7（开放问题）| "样本异质性提醒阈值（embedding 离散度阈值 / silhouette 门槛）如何设定？" | B 方案启动前实证后回答 |
| **D-5** | 新增触发 ID `T_heterogeneity` | spec §2.3 触发清单 | ingest 启动前 `detect_multi_archetype()` 返回 SUGGEST_AND_BLOCK 时打印 SUGGEST 阻塞 ingest | B 方案启动时 |

### 5.3 不建议改（3 项，明确反对）

| # | 反对修订项 | 理由 |
|---|---|---|
| **R-1** | 修订 §0.3 解耦原则（如改成单向耦合或废除）| C 选项才需要这种修订；A/B 不破坏 §0.3。**关键洞察**（scope-arch 二轮）：若硬选 C，"单向耦合"反而比"彻底废除"破坏更大（详见 §3.4），且会触发下方 7 项结构性副作用 — 证明 C 不是"小动 §0.3"而是**整套架构重构**。修订 §0.3 等于打开 C 的口子，应永久拒绝 |
| **R-2** | 修订 §0.5 定义域哲学 | 本研究的所有方案都建立在"用户挑选即定义域"基础上。B 方案是"提醒用户检视定义域"，不是"框架代定义" |
| **R-3** | 把 mining 吸收为 feature-induction 的 promotion gate | scope-arch 二轮明确判断（详见 §3.6）：mining 仍值得独立存在。理由：(1) mining 持有 label-aware 验证管道，吸收会污染 §0.3 残留语义；(2) 独立模块便于 add-new-factor 这种纯人工 promotion 路径继续存在；(3) 测试边界清晰。即使 C 下 threshold_optimizer 失去主算法（详见 §3.5），data_pipeline + factor_diagnosis + template_validator 三步仍有独立工程价值 |

### 5.3.1 C 选项的 7 项结构性副作用清单（scope-arch 二轮）

若用户坚持 C，必须同步处理以下 7 项变更（任何一项缺失都导致 spec 内部不一致）：

1. **§0.3 表格删除或重写**（详见 §3.4 推荐"彻底废除"）
2. **§0.5 "用户挑选即定义域" 需重新解释**（"定义域 = 多个 sub-定义域"）
3. **§3 Beta-Binomial i.i.d. 假设**要在 per-mode 层重新论证
4. **§2.6 Replay / Reshuffle** 全部 mode-aware 化（cluster 边界变更等同 schema 变更）
5. **§4.2 feature schema 加 mode_tag**、ObservationLog 加 mode_membership
6. **§1.1 Critic 新增 split-by-mode 动作类**，Inducer prompt 模板加 per-mode 子模板
7. **mining 入口契约**改为 (per-mode CSV, mode_id) 元组接收

**判断**（scope-arch 原话）：这 7 项副作用证明 C 不是"小动 §0.3"，而是**整套架构重构**。若用户坚持 C，正确做法不是"打补丁解耦"，而是**重启一次完整 brainstorming 流程**重新设计两层关系。

### 5.4 命名建议（独立 delta，建议同步进 spec）

workflow 专家强烈推荐：**feature-induction 用 `archetype`，mining 保留 `template`**。

| 原 | 改 |
|---|---|
| `--tag <experiment>` | 保留（审计 metadata，与 archetype 正交）|
| 新增 `--archetype <name>` | 命名空间分区 |
| spec 中泛指"mode" / "形态" 处 | 统一改为 `archetype`（避免与 sklearn/统计 mode 冲突）|

---

## §6 未解问题

### 6.1 关键未解问题（按优先级）

| # | 问题 | 谁回答 | 倾向 / 待实证 |
|---|---|---|---|
| **Q-MD-1** | B 方案的 silhouette 阈值是绝对值（0.30）还是相对值（历史 P75）？| 用户 + Phase 4+ 实证 | clustering 倾向 0.30 起步；累积 ≥ 5 次 ingest 后切相对值 |
| **Q-MD-2** | SUGGEST 阻塞 ingest 时是否记录到 `pending/heterogeneity_alerts.yaml`？| Phase 4+ 实施时决定 | 倾向是（便于事后批量处置）|
| **Q-MD-3** | `--strict-archetype` 的 silhouette ERROR 阈值（0.55）合理吗？| 用户 + Phase 4+ 实证 | 经验值，需 5-10 次 ingest 校准 |
| **Q-MD-4** | `--archetype` 命名空间是 feature_library 子目录还是 feature 级 tag 字段？| 用户决定 | workflow 倾向子目录（物理隔离）；scope-arch 倾向 tag 字段（可跨 archetype 共享 feature）|
| **Q-MD-5** | Phase 4+ 评估 B 方案时，是否同时考虑"feature 侧"信号（feature embedding 离散度）补充"样本侧"信号？| Phase 4+ 实施时 | 是，更多信号源更稳健 |
| **Q-MD-6** | 若 B 方案 Phase 4+ 落地后效果好，是否考虑把 archetype 信息（仅 ID 不含 cluster 内容）回灌给 Inducer？| **绝不**回灌 | 违反 §备选 8 + §4.3 盲跑约束，无论效果如何都不开口子 |

### 6.2 未在本研究覆盖的衍生问题

- **多 archetype 库的合并/拆分**：如果用户先按 archetype A ingest，后来发现某些样本应归 archetype B，怎么迁移？（需要 reshuffle 机制扩展为 cross-archetype）
- **archetype 间 feature 共享**：是否允许某些 feature（如"突破日大量"）跨 archetype 共享？scope-arch 第一轮提到"cross-mode-verify 机制"但未深入。
- **archetype 作为 mining 输入**：mining 是否应感知 archetype 边界（如"在 cup-handle archetype 下挖最优 template"）？这是 mining 模块的扩展，不在本研究范围。
- **archetype 与 dev UI 的集成**：dev UI 挑选阶段是否新增 archetype 字段？workflow 专家建议是，但这是 dev 模块的工程，不在本研究范围。

---

## §7 一段话最终结论

本框架与 mining 的解耦（§0.3）+ "用户挑选 = 定义域"（§0.5）共同决定了框架不应承担 mode 发现职能。用户的核心洞察"正样本应有隐含 feature 组合条件"是**对的**——clustering 量化证据显示混合 mode 投放会让 mode-specific 弱信号永久丢失（CH 罕见子结构 P5 从 0.18 candidate 降到 < 0.05 forgotten）。但解决方案不是让框架"猜 mode"（C 方案，违反 §0.3/§0.5/§备选 4/5/7/8），而是 **A 兜底（CLI 引入 `--archetype` 命名空间，0 工程量）+ B 在 Phase 4+ 评估（被动 SUGGEST 提醒，~1-2 天工程，clustering R0-R7 决策树落地）**；命名上把 feature-induction 概念定为 **`archetype`** 与 mining `template` 区隔，避免认知冲突。本期 spec 主体无需修订，仅 §5.6 增列搁置项 + §7 新增 Q20 即可。

---

## 附录 A：研究产出与参考清单

### A.1 本研究产出

- 本文档：`docs/research/feature_mining_mode_discovery.md`

### A.2 参考文档

- 主 spec：`docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md`（§0.3 / §0.4 / §0.5 / §1.1 / §2.2 / §2.3 / §2.6 / §4.3 / §4.5 / §5.6 / §7 / §8 备选 4/5/7/8）
- mining 模块：`.claude/docs/modules/数据挖掘模块.md`
- Beta-Binomial 骨架：`docs/research/feature_mining_v2_unified_decision.md`
- CLI 调度哲学：`docs/research/feature_mining_orchestration_revisit.md`
- Reshuffle 机制：`docs/research/feature_mining_shuffled_reinduction.md`

### A.3 三专家轮次贡献

| 专家 | 第 1 轮 | 第 2 轮 | 第 3 轮 |
|---|---|---|---|
| **scope-arch** | 三方案对比表 + Q-narrow/Q-mode/Q-template 切分 + 推 B + §备选 4/5/7/8 同构诊断 | §0.3 修订路径（"彻底废除"vs"单向耦合"反直觉论证）+ mining 4 步存续表（threshold_optimizer 被吃 / 其余三步保留）+ 7 项结构性副作用清单 | — |
| **clustering** | 5 算法对比 + Beta-Binomial 稀释量化（CH 罕见子结构 P5 比较）+ pre/post-induction 数学影响 | — | R0-R7 决策树 + 推 (b) 报警拍板 + R5 阻塞 ingest |
| **workflow** | UX 矩阵 + template/mode 命名冲突诊断 + 默认 B 推荐 + `--archetype` 命名建议 | — | 默认 B + `--strict-archetype` flag + 3 新 CLI 子命令（preview / analyze-archetypes / cohesion）+ archetype 命名定型 |

---

**文档结束。**
