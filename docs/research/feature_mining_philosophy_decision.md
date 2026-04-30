# 特征挖掘哲学 — 最终综合决策

> 研究日期：2026-04-24
> 角色：`synth-critic`（feature-mining-philosophy team，综合决策者）
> 上游输入：
> - `docs/research/feature_mining_algorithmic_philosophy.md`（algo-advocate）
> - `docs/research/feature_mining_human_like_philosophy.md`（intel-advocate）
> - `docs/research/feature_mining_via_ai_design.md`（现有完整方案）
> - `docs/explain/ai_feature_mining_plain.md`（现有通俗版）

---

## TL;DR（三条结论）

1. **用户的二分（算法 vs 高智能化）是维度混淆。** 真正要拍板的不是"哲学选 A 还是选 B"，而是**三层架构各层走什么范式**——视觉/感知层走 AI、归纳/推理层可选算法或 AI、验证层走算法。两位倡导者其实在争"归纳层"，其它层并无分歧。

2. **归纳层不必二选一，但阶段必须明确。** 现有方案（AI 归纳）应**原样推进至 MVP 跑通**，理由不是它完美，而是没有 vocabulary 就没法启动算法路径。**algo-advocate 的"AI bootstrap → 算法接管"与 intel-advocate 的"既有方案 → 高智能化"不在同一轴上**：前者是归纳引擎的**范式迁移**（LLM 推理 vs 算法搜索），后者是归纳引擎的**自主性升级**（orchestrator 喂食 vs AI 自主回看）。同时可做，但现在都不做。

3. **现有方案：保留执行 + 一处硬修正。** 不推翻不大改。硬修正是在 Phase 1 的 corpus exporter 里同时输出一份 `vocabulary_draft.md`（AI 归纳结果里出现的所有 archetype/attribute/feature 词），为未来阶段 II 铺地基。这比 algo-advocate 提议的"完整重构 primitive vocabulary + tagger + miner"便宜 90%，且是后续任一方向演化的共同前置条件。

---

## §1 用户顶层思考的评估

### 1.1 二分是否成立？

用户提问的原始形式：

- 方案 X — **高智能化**：自然语言笔记本、AI 自发回看样本、拟人分析师
- 方案 Y — **算法哲学**：严格规则、AI 只做视觉特征提取与语言适配、频率表/特征图谱/GA/马尔科夫链

**判断：这是 false dichotomy。** 二者并非同一维度上的两端。

| 真正的维度 | X 方案的位置 | Y 方案的位置 |
|---|---|---|
| 归纳结论的表征 | 自由叙事 | 结构化模式 |
| 归纳过程的驱动力 | AI 自主探索 | 算法枚举搜索 |
| AI 与算法的职责边界 | AI 通栏 | 算法通栏 |
| 归纳依赖的原子词汇 | AI 的无限词表 | 人工定义 primitive vocab |

X 其实是"AI 自主性 + 叙事表征"的复合；Y 其实是"算法主导 + 结构化表征 + 固定词表"的复合。这两个复合体各自混合了多个独立维度，用"二选一"提问会把这些维度强行绑定。

### 1.2 是否有第三条路？

**有，而且更清晰**：把流程拆成三层，每层独立选范式（详见 §2）。

### 1.3 用户"底层可封装看待"的落地盘点

| 底层需求 | 是否有可用封装 | 风险等级 |
|---|---|---|
| K 线图像感知 | Claude 原生多模态（已在现有方案使用）| 低 |
| 自然语言归纳 | Claude 原生推理 | 低 |
| 频率模式挖掘（Apriori/FP-Growth）| `mlxtend.frequent_patterns` | 低 |
| 显著性检验 + FDR | `scipy.stats` + `statsmodels` | 低 |
| 对比模式挖掘（Emerging Pattern）| 无现成包，但在 Apriori 输出上加 30 行逻辑 | 低 |
| Bootstrap / Permutation test | `scipy` + 自写 loop | 低 |
| 图挖掘（gSpan）| `gspan-mining` PyPI 冷门、质量参差 | **中** |
| HMM | `hmmlearn` | 中（小样本欠拟合）|
| GA | `DEAP` / `pygad` | **高**（过拟合制造机）|
| Claude Code Read/Glob/Grep（笔记本访问）| 原生 | 低 |
| AI primitive tagger | 无现成，需新 skill + ensemble | 中 |
| mining 流水线（TPE + 5-dim OOS）| 已有（`mining/`）| 低 |

**结论**：低风险封装足以支撑"候选 A（Apriori+对比挖掘）+ 过拟合五重防御"；高风险封装（图挖掘/HMM/GA）不建议在小样本阶段触碰。用户"底层可封装"的直觉在 Apriori 路径上成立，在 GA 路径上不成立。

---

## §2 三层架构视角（本决策的核心框架）

特征挖掘从数据到因子的完整链条，本质上是**三个独立的推理层**：

```
[Layer 1 — Perception/视觉]
    输入：原始 K 线 + 成交量
    任务：把像素/OHLC 翻译为可用结构（形态命名、primitive 命中、量化字段）
    候选范式：AI 视觉、规则检测器、AI tagger
         ↓
[Layer 2 — Induction/归纳]
    输入：Layer 1 的结构化/半结构化结果 + 正反例 label
    任务：从样本集合中抽取"区分正反例"的规律
    候选范式：AI 推理归纳、频率挖掘、对比挖掘、GA、HMM、图挖掘
         ↓
[Layer 3 — Falsification/验证]
    输入：Layer 2 产出的候选规则
    任务：在独立 OOS 样本上证伪或保留
    候选范式：统计检验（Spearman/permutation/bootstrap/FDR）+ mining TPE + 5-dim OOS
```

**每一层的范式选择是独立的**，两位倡导者其实都认同这点（只是没有显式说出来）：

- intel-advocate 在 §5 反复强调"mining/ 流水线不可替代"——这是在说 Layer 3 必须是算法。
- algo-advocate 在 §6.1 承认"cold-start 阶段 AI 哲学先行、为算法哲学铺地基"——这是在说 Layer 1 的 primitive tagging 和 vocab bootstrap 必须靠 AI。

真正的分歧只在 Layer 2。两位倡导者在 Layer 1 和 Layer 3 的立场都收敛到相同答案。

**这是一个极其重要的洞察**：用户感受到的"二元对立"之所以痛苦，是因为把三层架构折叠成了一个选择。展开成三层后，大部分"选择"其实已经被约束死了，可争论的空间远比想象中小。

---

## §3 环节级决策表

下表是本研究的**核心决策**，不和稀泥，每个环节给出明确推荐。

| 环节 | 所属层 | 推荐范式 | 理由 | 争议性 |
|---|---|---|---|---|
| 样本选择（P/N 标注）| 输入 | 人工（dev UI P/N 键 + cold-start 分位抽样）| 监督信号源头，无算法可替代 | 无 |
| K 线渲染（AI-friendly 图像）| L1 | 规则代码 | 图像生成是纯确定性渲染 | 无 |
| 三段式结构化文本导出 | L1 | 规则代码 | 已由现有方案定稿 | 无 |
| **盘整段 13 字段计算** | L1 | **规则代码（其中 5 字段新写）** | 确定性量化，AI 读数字不可靠 | 无 |
| **形态定性命名（archetype）** | L1+L2 | **AI 视觉 + 自然语言** | LLM 开放词表优势集中在此；primitive vocab 没有的形态靠 AI 兜底 | 低 |
| **Primitive 命中判定**（若未来引入）| L1 | **AI tagger + ensemble 3 次投票** | 人工定义 vocab 但判定靠 AI（规则检测器写不全）| 中 |
| **跨样本归纳（核心推理）**| L2 | **Phase 1-3 用 AI；Phase 4+ 叠加 Apriori+Emerging Pattern** | 无 vocab 时只能 AI；vocab 建好后算法提供稳定性 | **高**（本研究核心争议）|
| 中间表征（多轮 compact）| L2 | **PartialSpec YAML（现状）** | 抗 drift 护栏不能丢；intel-advocate 的叙事笔记本作为 L2 可选补强，非必须 | 中 |
| **AI 主动回看历史 K 线** | L2 | **Phase 4+ 启用；当前不引入** | 真实增量集中于模糊边界/跨样本类比，但 drift 成本不适合 MVP | 中 |
| 形态命名归一化 | L2 | 人工维护 `form_archetype_glossary.md` | 既有方案已规划（P2 第 12 条）| 无 |
| Overlap 判定（与现有 13 因子）| L2 | **Phase 1-3 AI 声明 + Phase 4+ 转定量 Jaccard** | 当前 invariant 是自然语言，无法算 Jaccard；未来若引入 primitive vector 则可定量化 | 中 |
| 候选规则 → Factor Draft 翻译 | L2→L3 | AI + 模板（现状）| 合适 | 无 |
| 显著性检验（chi-square/Fisher + FDR）| L3 | scipy + statsmodels | 两位倡导者一致 | 无 |
| Permutation test / Bootstrap | L3 | 自写 scipy loop | algo-advocate 强调不可省略，同意 | 无 |
| mining TPE 阈值优化 | L3 | 既有 `mining/` | 不动 | 无 |
| 5-dim OOS 验证 | L3 | 既有 `mining/` | 不动 | 无 |
| Hold-out 样本集 | L3 | **强制保留 20% 不参与任何挖掘** | algo-advocate 正确，现有方案未显式保留，**需补**| 低 |

**表格核心信号**：

- L1 和 L3 的所有单元格都无争议或低争议。
- L2 的争议集中在"谁主导归纳"这个核心问题上。
- **最实际的 delta 是 L3 的 hold-out**——现有方案没有显式保留完全不参与挖掘的 OOS 样本，这是一个必须立刻补上的缺口，与走哪条哲学无关。

---

## §4 与现有方案的关系：最终建议

**三选一答案：[局部调整后执行]**

### 4.1 为什么不推翻重新设计

- 现有方案（`feature_mining_via_ai_design.md`）已细化到 checklist 层、schema 层，投入沉没成本大。
- 两位倡导者都没有给出"现有方案错了"的论据，只给出"现有方案不够"的论据。
- algo-advocate 自己在 §8.1 明确"不要全盘替换"。
- intel-advocate 自己在 §6.1 明确"不是替代品，是上层升级"。
- **两位倡导者的结论都是"保留现有方案"**，这是非常强的收敛信号。

### 4.2 为什么不是完全保留执行

- algo-advocate 指出一个现有方案的真实短板：**组合过拟合防御不足**。现有方案 §6 风险表只有"mining OOS"作为 falsifier，**没有 permutation test / bootstrap / hold-out**。这三件是 L3 必需，当前缺失。
- 现有方案没有显式的 **vocabulary bootstrap 机制**——skill 每轮产出的 archetype/attribute 词没有系统性归档，未来想走算法路径时无从开始。
- 现有方案的"形态命名漂移"问题（§7.3 P2 第 12 条的 glossary）是 P2 的远期任务，但 vocabulary 归档应立刻启动（成本极低）。

### 4.3 具体的"局部调整"清单

**必须改（立刻做）**：

1. **Phase 1 corpus exporter 追加 vocabulary 归档**：每次 skill 输出 PartialSpec 时，把其中出现的所有 archetype 名、attribute 描述、invariant 短语**机械地**追加到 `docs/research/feature_library/vocabulary_draft.md`（去重）。这是为未来任一方向演化的共同前置条件。成本：半天工作。
2. **L3 补 hold-out 协议**：在 `mining/` 入口前强制保留 20% 样本完全不参与任何 skill 归纳、任何 TPE 优化。最终因子在 hold-out 上的表现是最终裁决。成本：需要在抽样器里加标记字段。
3. **L3 补 permutation test**：在 skill 产出 Factor Draft 之后、送入 `add-new-factor` 之前，跑一次 label permutation（n=100），看候选因子的 Spearman 在 null 分布下的分位。这是抗"AI 在小样本上挑出噪声规律"的硬防御。成本：需要新工具（约一周）。

**建议改（可延后但别忘）**：

4. Pre-registered hypotheses：在 skill 启动前，要求用户写下 5-10 条他/她相信的规律。skill 结束后先用这些做 confirmatory，再看 exploratory 结果。成本：SKILL.md 加一段 gate。
5. 反例池规模对称化：现有方案的反例池设计正确（high-label 但形态差），但未规定数量。建议正反例 1:1 或 1:2。

**不改（保留现状）**：

- 两层输出（Feature Spec + Factor Draft）
- PartialSpec YAML + evidence_receipts
- 三档 input_mode（text_only / hybrid_light / hybrid_full）
- SYSTEM 五条款
- 两段式 label 揭示

**不加（至少 Phase 1-3 不加）**：

- Primitive vocabulary + tagger + Apriori（algo-advocate 主张）— Phase 4+ 叠加
- 叙事笔记本 + AI 自主回看（intel-advocate 主张）— Phase 4+ 叠加
- 宏观/微观双层 skill — Phase 4+ 评估
- HMM / GA / 图挖掘 — 不引入（至少 500+ BO OOS 样本后再评估）

---

## §5 迭代收敛判据的顶层设计

用户原话：「新数据稳定验证 或 重复旧数据被确认」。这需要在两个层级分别形式化。

### 5.1 两种哲学下的收敛判据

| 环节 | 算法哲学下 | 高智能化哲学下 |
|---|---|---|
| **Layer 2 归纳内部收敛**（skill 内的多轮）| bootstrap 稳定：pattern 在 >80% 重采样里出现；permutation null 下 p<0.05；OOS 一致 | 连续两轮 PartialSpec 无 invariant 变化 + counter_evidence 已处理 |
| **Layer 3 整体验证**（skill 外的 mining）| 5-dim OOS + hold-out 表现 + Spearman 方向稳定 | 同左（两个哲学共用 Layer 3）|
| **系统级学习收敛**（跨多次 skill 调用）| vocabulary 饱和（连续 3 次 skill 无新 primitive）| cross_cutting 卡片在多次调用后稳定 |

### 5.2 现有方案已覆盖多少

现有方案在 §3.3 末定义了 L2 内部的"连续两轮无变化 → 收敛"，在 §1.4 和 §6 定义了 L3 的 mining falsifier。

**缺口**：
- L2 内部收敛判据**只有定性**（"两轮无变化"），**缺少定量**（允许多大的微调不算变化？）。
- L3 缺 permutation test 和 hold-out（§4.3 已列）。
- 系统级学习收敛**完全缺失**——没人定义"何时该停止跑 skill，转入下一个形态"。

### 5.3 推荐设计

**不在 L2 归纳环节内加新的收敛子循环**。理由：

- L2 已有多轮 compact 收敛逻辑，再套一层子循环是过度设计。
- 真正需要加强的是 L3——把 hold-out + permutation 作为 Factor Draft 进入 `add-new-factor` 前的 gate。
- 系统级收敛（何时换形态研究）由用户判断，不自动化——AI 无法判断"用户已经满意了"。

**具体三条加固**：

1. **L2 内部收敛的定量化**：定义"无变化" = 本轮 PartialSpec 相比上轮，invariant 文本 Jaccard ≥ 0.9（简单字符集相似度，不需语义理解），且 coverage_stats 数值变化 < 5%。
2. **L3 的 hold-out gate**：Factor Draft 通过 mining OOS 后，再跑一次 hold-out 测试；hold-out 上 Spearman 方向一致才算通过。
3. **系统级学习收敛由人拍板**：在 `INDEX.md` 中维护当前形态的 `research_status: active | saturated | parked`。AI 不自动切换，用户显式标注。

---

## §6 修订后的 Phase 路线图

下表对比现有方案 §7.5 与本研究的建议修订。

| Phase | 现有方案定义 | 本研究建议 | 变动类型 |
|---|---|---|---|
| **Phase 1** | 5 盘整字段 + corpus exporter（text_only 可手工试跑）| **同上 + 追加 vocabulary_draft.md 归档机制** | 保留 + 新增 1 项 |
| **Phase 2** | Dev UI P/N hook + cold-start 抽样 + skill 本体（end-to-end text_only）| **同上 + 新增 hold-out 标记 + pre-registered hypotheses gate** | 保留 + 新增 2 项 |
| **Phase 3** | AI-friendly 图像渲染，启用 hybrid_light | **同上 + 新增 permutation test 工具（在 Factor Draft → add-new-factor 之间）** | 保留 + 新增 1 项 |
| **Phase 4** | （P1 后续）feature_library 索引、PartialSpec 缓存、sparse 聚类、cluster 分叉 manifest | **重定义**：根据 Phase 1-3 结果，**二选一或并行启动**：<br>(a) algo 路径：primitive vocabulary 审核 + Apriori 候选 A + 对比挖掘<br>(b) intel 路径：archetype 卡片化 + AI 主动回看 + 双层 skill | **重新定义** |
| **Phase 5**（新增） | 无 | 若 Phase 4 路径成熟、样本 >500 BO，评估图挖掘（候选 B）；HMM/GA 永不引入除非样本 >2000 BO | 新增 |

**路线图决策说明**：

- **Phase 1-3 完全保留现有方案的骨架**，只在三处加硬防御（vocabulary 归档、hold-out、permutation）。这三处新增工作量 <1 周。
- **Phase 4 的二选一是用户在 Phase 3 跑完后的真实选择题**。现在不要提前押注。到时候的判断依据：
  - 如果 Phase 1-3 产出的 AI 归纳**在 mining OOS 上稳定通过** → 继续 intel 路径（叠加高智能化）。
  - 如果 Phase 1-3 发现 **AI 归纳漂移严重、每次跑结论都不同** → 转 algo 路径（vocabulary + Apriori）。
  - 两种情况在 Phase 3 末会有可观察的信号，不需要现在猜。
- **Phase 5 的远期目标是 BO 样本 >500 后才考虑更复杂算法**。当前数据量（几十到几百 BO）跑 GA/HMM 一定过拟合。

### Phase 1-3 新增工作的工程量粗估

| 新增工作 | 工程量 | 依赖 |
|---|---|---|
| vocabulary_draft.md 追加逻辑 | 0.5 天 | skill 产出 PartialSpec |
| Hold-out 标记字段 | 0.5 天 | cold-start 抽样器 |
| Pre-registered hypotheses gate | 0.5 天 | skill SKILL.md 加一段 |
| Permutation test 工具 | 3-5 天 | Factor Draft 已实现 |
| **合计** | **~1 周** | — |

这是本研究建议的**全部**工程增量。剩下的都是 Phase 4+ 的可选路径。

---

## §7 关键未解问题（交用户拍板）

| # | 问题 | 本研究推荐倾向 | 理由 |
|---|---|---|---|
| Q1 | Phase 4 何时启动？触发条件是什么？ | **用户在 Phase 3 末期主观决定，不设自动触发** | 过早设 threshold 只会导致不该启动时启动 |
| Q2 | Phase 4 走 algo 还是 intel？ | **取决于 Phase 3 观察到的主要痛点**。漂移严重 → algo；卡在模糊边界 → intel | 不提前押注 |
| Q3 | 是否立刻投入 vocabulary_draft.md 归档？ | **是**（0.5 天工作，零风险） | 这是任一方向演化的共同前置 |
| Q4 | 是否立刻投入 permutation test？ | **建议是**（3-5 天工作） | 现有方案最严重的 L3 短板 |
| Q5 | Hold-out 比例 20% 合适吗？ | **是**（algo-advocate §8.4 标准）| 与行业实践一致 |
| Q6 | Pre-registered hypotheses 数量 5-10 条？ | **是** | algo-advocate §8.4 标准 |
| Q7 | 叙事笔记本在 Phase 4 启用时是否替换 PartialSpec？ | **否，叠加而非替换** | PartialSpec 的 evidence_receipts 是抗 drift 护栏，不能丢 |
| Q8 | 是否写 primitive vocabulary 的正式 vocab v1？ | **Phase 4 才写**，现在只归档 draft | 成熟之前定义 vocab 是伪规则 |
| Q9 | GA / HMM / 图挖掘何时引入？ | **样本 >500 BO 后再议，当前不讨论** | 小样本下组合搜索是过拟合制造机 |
| Q10 | 宏观/微观双层 skill 是否值得做？ | **Phase 4 intel 路径启动时才做** | 当前样本少、单层 skill 够用 |

---

## §8 附录：两位倡导者的关键分歧与裁决

### 8.1 分歧 1：phasing 的起点

- **algo-advocate**：阶段 I 用 AI bootstrap vocabulary → 阶段 II 算法接管归纳主流程
- **intel-advocate**：阶段 A 既有方案（AI）→ 阶段 B 叠加高智能化（更 AI）→ 阶段 C 简化结构化

**裁决**：两者不冲突。algo 谈的是**归纳引擎的范式迁移**（LLM → 算法）；intel 谈的是**归纳引擎的自主性升级**（被喂食 → 自主回看）。两者是正交的升级维度。

- 横轴（引擎范式）：AI 推理 → 算法搜索。这是 algo 的论点所在。
- 纵轴（自主性）：orchestrator 喂食 → AI 自主操作。这是 intel 的论点所在。

当前系统位于"AI 推理 × orchestrator 喂食"象限。两位倡导者各自提议沿不同轴演化。本研究的裁决：**Phase 4 并非"二选一"，而是根据 Phase 3 的观察信号决定先沿哪个轴演化**。

### 8.2 分歧 2：PartialSpec YAML 是否该保留

- **algo-advocate**：保留，只是把"AI 提议 invariants"替换为"算法挖掘 patterns + AI 只做 tagging"
- **intel-advocate**：降级为 archetype 卡片末尾的"结构化总结段"

**裁决**：保留现状（PartialSpec 作为主中间态）。intel 的降级建议仅在其 Phase C 才成立，且依赖叙事笔记本已经跑顺。当前不改。

### 8.3 分歧 3：多轮 compact 是否必要

- **algo-advocate**：不需要多轮（"所有样本一次性进数据库，一次挖掘得到结果"）
- **intel-advocate**：需要，但从"归纳收敛"转为"批判式复盘"

**裁决**：现状保留多轮 compact。algo 的"一次挖掘"前提是 vocabulary 已建好——当前 Phase 1-3 这个前提不成立。intel 的改造属 Phase 4+。

### 8.4 分歧 4：GA 是否可用

- **algo-advocate**：candidate C（HMM/GA）"过拟合最严重"，给 ★1/5，"强烈不建议小样本阶段使用"
- **intel-advocate**：未直接讨论，但反对深度学习式黑盒

**裁决**：不引入。用户此前深度学习过拟合经历 + algo-advocate 自己的警告 + 小样本（<500 BO）现实，三条理由叠加。

### 8.5 论点是否全都成立？

- **algo-advocate "算法哲学全局通栏"不成立**——他自己在 §6.1 承认 cold-start 阶段这口号反过来。本研究采信他的诚实自我纠正。
- **intel-advocate "既有方案也是 AI driven"成立**——这是他最诚实的立论点，消解了"二元对立"的心理预设。
- **intel-advocate "drift/成本/不可复现"的三大风险成立**——这也是本研究建议 Phase 4+ 才启用高智能化的直接理由。
- **algo-advocate "组合爆炸是深度学习过拟合的统计学同胞"成立且重要**——这是本研究建议立刻补 permutation/hold-out 的理由。

### 8.6 一个两位倡导者都没讲的关键洞察

**现有方案的真正短板不在 L2 的归纳，而在 L3 的验证。** 两位倡导者花了大量篇幅争论 L2 应该怎么做，却都没注意到现有方案 §6 的风险表只把"mining OOS"作为唯一 falsifier——缺了 permutation test、缺了 hold-out、缺了 pre-registered hypotheses。这三件事**无论走哪条哲学路径都需要**，且**成本低（~1 周）**。

本研究把 §4.3 的三条硬修正提到最优先级，就是基于这个洞察。用户如果只采纳本研究的一个建议，那就是这三条。

---

## 最终一句话

**现有方案（`feature_mining_via_ai_design.md`）是正确的起点，只需在 L3 加三条硬防御（vocabulary 归档、hold-out、permutation test）就足以支撑 Phase 1-3 的 MVP 闭环；Phase 4 何去何从由 Phase 3 的观察信号决定，不提前押注 algo 或 intel 哲学；GA/HMM/图挖掘在样本量 >500 BO 前不引入。用户面对的"算法 vs 高智能化"不是二选一，而是三层架构中归纳层未来的两条升级路径，当前都不走。**

---

**文档结束。**
