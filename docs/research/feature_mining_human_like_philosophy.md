# 高智能化（拟人化）特征挖掘哲学 — 深度分析

> 研究日期：2026-04-24
> 角色：`intel-advocate`（高智能化哲学倡导者 + 严格自我批评者）
> 对照基准：`docs/research/feature_mining_via_ai_design.md`、`docs/explain/ai_feature_mining_plain.md`
> 决策目标：替用户在"结构化归纳（既有方案）"vs"拟人化分析师（本方案）"之间做顶层判断

---

## 0. Executive Summary

**结论（三句话）**：

1. 既有方案本质上是**"AI 作为归纳引擎"的工作流**——外部 orchestrator 分批喂样本、结构化 YAML 做中间态、SYSTEM 条款强约束输出形态。AI 的工作空间被压缩成"一轮 prompt 的 context window"。

2. 用户所说的"高智能化"哲学，真正的增量不是"用更多 AI"——而是**扩大 AI 的自主操作空间**：让 AI 把整个样本 corpus（及其历史 K 线目录）当作**可随机访问的外部世界**，在里面"游走、回看、对比、推翻"，并把思考沉淀成**叙事性的自然语言笔记本**而非结构化 PartialSpec。

3. 这个 delta **不是零-一的方法论革命**，而是**推理形态的范式偏移**——从"多轮归纳收敛"→"分析师式循环调查"。它有真实的独特价值（尤其在形态的"模糊边界"和"跨样本类比"上），但也带来无法忽视的 drift / 成本 / 可复现性代价。**推荐做法不是二选一，而是把高智能化哲学定位成既有方案之上的 P2 可选升级**，在 MVP 跑通并产出 feature_library 后再启用。

**关键判断表**：

| 维度 | 既有方案（结构化归纳） | 高智能化哲学（拟人分析师） | 真正增量 |
|---|---|---|---|
| 中间态 | PartialSpec YAML（evidence receipts、overlap_kind、counter_evidence） | 自然语言笔记本（按形态分类的卡片 + 跨样本叙事） | ⭐⭐ 中 |
| 驱动力 | 外部 orchestrator 分批投喂 | AI 主动检索、回看、重访样本 | ⭐⭐⭐ 高 |
| 结论形式 | 可机器解析的 YAML 条目 + Factor Draft | 叙事性 memo + 末尾的因子草案 | ⭐ 低 |
| 推理形态 | 收敛式归纳（每轮精炼不变量） | 发散+收敛交替（批判→回看→修正→再批判） | ⭐⭐ 中 |
| 失败模式 | 漏掉模糊形态 / 被 SYSTEM 条款限制 | drift、context 爆炸、不可复现 | — |
| 工程成本 | 中（skill + schema + 5 字段计算） | 高（+ 大 corpus 目录管理 + 笔记本索引） | — |

---

## 1. 诚实区分：既有方案已经用的 AI vs 用户说的"更极致拟人化"

这是本节最重要的判断——**不要把前者当成后者的胜利**。

### 1.1 既有方案里 AI 已经做的事

读完 `feature_mining_via_ai_design.md` §3.3 和 §3.4 后，客观列表：

- ✅ 多轮 dense 归纳（不是单轮 prompt）
- ✅ 自然语言 invariant（不是纯数值阈值）
- ✅ Overlap_kind 分类（在现有 13 因子上做推理）
- ✅ Counter_evidence 保留（两轮之间抗遗忘）
- ✅ 两段式 label 揭示 + self-correct（盲猜再揭示）
- ✅ 负例区分性推理（不能只描述正例共性）
- ✅ 两层输出：自然语言 spec + 结构化因子草稿
- ✅ AI 在 prompt 里被赋予"交易员/分析师"的角色设定（通过 SYSTEM prompt）

**换句话说：既有方案已经是"AI as hypothesizer"**。Claude 不是在做"数据预处理+阈值打标"那种机械工作，而是在做**语言化归纳**。SYSTEM 5 条款也明确了"AI 不能用 label 反向拟合"这种分析师式的方法论纪律。

### 1.2 用户说的"更极致拟人化"的真正锚点

结合用户提的几个词（自然语言笔记本、批判式复盘、自发回看历史 K 线、拟人分析师式工作流、宏观/微观双层 skill），真正的哲学偏移只在三个点上：

**偏移 1：中间态从"结构化契约"变成"自由叙事"**
- 既有：`PartialSpec` YAML，每条 invariant 必须声明 `overlap_kind`、`evidence_receipts`、`coverage_stats`。强制结构化是"抗 drift 护栏"。
- 新：一本 Markdown 笔记本，按形态或话题分章节，AI 用自由文字写"我观察到 X，但 S012 是个反例，让我回去再看看……"。

**偏移 2：驱动力从"外部喂食"变成"AI 自主操作"**
- 既有：`scripts/export_formation_corpus.py` 批量导出 → skill 每轮把 BATCH_k 拼进 prompt。AI 永远只看到当前 batch，看不见 corpus 全貌。
- 新：corpus（及渲染好的 K 线图）以**目录树**形式存在，AI 用 `Read`/`Glob`/`Grep` 工具自主访问。"我想重新看看 S012 的盘整段放大图" → AI 自己去读。"最近两轮我提到的矩形形态，我想回去把过去所有笔记本里涉及矩形的章节都串起来" → AI 自己去 grep。

**偏移 3：推理形态从"收敛式归纳"变成"批判式复盘"**
- 既有：每轮产出一版更精炼的 PartialSpec，目标是**收敛**。到 convergence 就停。
- 新：显式鼓励 AI **自我批判**——"我上一轮的假设 H3 在新样本上站不住，回去找 3 个老样本验证一遍，写一段反思"。这是分析师写研报时的真实工作流，不是归纳的工作流。

### 1.3 一句话：这不是"从 0 到 1 给系统加 AI"，而是"把 AI 的笼子再打开一格"

既有方案把 Claude 关在 orchestrator 的笼子里。高智能化哲学是**让 Claude 从"被喂数据的归纳员"升级为"有自己工位、有自己笔记本、可以自主调档案的分析师"**。

这才是用户说的"高智能化"真正的锚点。不要被"既有方案也叫 AI driven"这件事模糊化。

---

## 2. Delta 的具体化：可实现层面的拆解

### 2.1 Delta 1 — 自然语言笔记本 vs 结构化 PartialSpec

#### 2.1.1 笔记本应该长什么样？

**不推荐**：一本线性 Markdown 文件，一轮一个章节（"## Round 1"、"## Round 2"……）。这只是把 YAML 换成散文，工程上没意义。

**推荐组织方式：按形态原型（archetype）分卡片 + 跨形态索引**：

```
docs/research/feature_library/
├── INDEX.md                         # 宏观视图：所有已识别 archetype 的短摘要
├── archetypes/
│   ├── tight_rectangle_basing.md   # 一个 archetype 一张卡片
│   ├── u_bottom_breakout.md
│   ├── high_altitude_spike.md      # 反例原型也独立成卡
│   └── flat_top_consolidation.md
├── cross_cutting/
│   ├── volume_rhythm_observations.md   # 跨 archetype 的量能节奏观察
│   └── position_context_notes.md       # 位置属性（底部/中段/高位）的离散观察
└── review_log/
    ├── 2026-04-25_session1_raw.md      # 原始会话笔记（链式思考留底）
    └── 2026-04-25_session1_summary.md
```

**关键设计**：
- **每张 archetype 卡片**包含：核心叙事（3-5 段）、样本证据列表（`[S007, S012, S031]`，用 corpus 内的稳定 ID）、反例对照（high_altitude_spike 卡片中明确链接到 tight_rectangle_basing 作为"对照组"）、**开放问题区**（"我还不确定 S012 是否真的属于这里"）、**候选因子草案**（末尾附，还没正式落地）。
- **Cross-cutting 笔记**专门放那些"不属于任何单一 archetype、但在多个 archetype 中反复出现"的观察。这是拟人化分析师**最独特的能力**——跨样本类比推理（§5.1 展开）。
- **Review log** 保留原始对话轨迹，防止事后无法追溯"这条结论是怎么来的"。

#### 2.1.2 为什么不是一锅 Markdown？

因为**笔记本会膨胀到超过 Claude context**。如果笔记本是一个 5000 行的 md，每次会话都要 Read 全文，很快就撑爆 context。卡片化 + 索引 + 按需 Read 是唯一可持续的方式。

**这也恰好是 AI 自主操作能力的用武之地**——Claude 根据当前任务决定"我需要读 archetypes/tight_rectangle_basing.md 和 cross_cutting/volume_rhythm_observations.md"，而不是全盘加载。

#### 2.1.3 笔记本 vs PartialSpec：真正损失的是什么？

| 能力 | PartialSpec YAML | 叙事笔记本 | 影响 |
|---|---|---|---|
| 可机器解析 | ✅（schema 强制） | ❌（需要再跑一遍 AI 抽取） | 下游 Factor Draft 生成多一步 |
| 抗 drift 护栏 | ✅（evidence_receipts 必填） | ⚠️（靠 AI 自律） | 需要额外机制补偿 |
| 人读友好 | ⚠️（YAML 可读但呆板） | ✅（叙事流畅） | + |
| 跨章节关联 | ❌（YAML 条目间无语义链接） | ✅（自然语言链接自然） | + |
| 版本化 diff | ✅（YAML diff 清晰） | ⚠️（散文 diff 易误导） | - |

**真正损失：抗 drift 护栏**。PartialSpec 的 `evidence_receipts: [S001:0.92, S003:0.87]` 强迫 AI 每条规律必须指向具体样本。取消结构化后，AI 完全可以写"多数样本都显示 X 趋势"这种无 evidence 的断言。这是最大的具体风险（§4.1 展开）。

### 2.2 Delta 2 — AI 主动回看 / 重访历史 K 线

**这是整个高智能化哲学最有价值的增量**，也是最值得认真实现的点。

#### 2.2.1 可行性：Claude Code Read 工具够不够？

**够**，但需要 corpus 组织到位。工程层面的必要条件：

1. **每个 BO 样本有稳定 ID 与目录**：
```
corpus/
├── S001/
│   ├── meta.json           # BO 元数据（ticker 脱敏、label、13 因子值）
│   ├── segment_text.md     # 结构化三段式文本
│   ├── detail.png          # 2560×1440 detail 图
│   ├── zoom.png            # consolidation zoom
│   └── overview.png        # 长周期位置背景（可选）
├── S002/
│   └── ...
└── index.json              # 全部样本的扁平列表
```

2. **Claude 的工具链**：
   - `Read corpus/S012/detail.png` — 直接读 PNG（多模态）
   - `Glob corpus/*/meta.json` — 快速枚举
   - `Grep "label_5_20" corpus/*/meta.json` — 条件筛选（虽然粗糙）
   - `Read corpus/index.json` — 一次性索引

3. **Claude 的操作语言**（在 SKILL.md 里写清楚）：
```
当你需要回看某个样本：Read corpus/<ID>/segment_text.md 与 detail.png。
当你需要找"label > 0.5 的所有样本"：Read corpus/index.json 自己过滤。
当你想对照新老观察：Read docs/research/feature_library/archetypes/<archetype>.md。
```

**结论：工具链完全够用**。Claude Code 原生的 Read/Glob/Grep 就是"分析师的档案柜钥匙"。

#### 2.2.2 自发回看的两种具体场景

**场景 A：验证假设**
> "我刚才写了'矩形盘整持续 40-80 根'，但记忆里 S007 很典型，我要回去重新 Read corpus/S007/detail.png 确认它的持续天数。"

**场景 B：发现异常后追溯**
> "新一批样本里 S042 明显不属于我已有的任何 archetype，我要回去 Grep 看看在旧笔记本里是否已经有类似的未归类观察。"

#### 2.2.3 回看的风险：AI 可能"越看越乱"

Claude 的注意力是有限的。如果每轮都允许自由回看，**context 会被反复读入的图像和笔记填爆**。必须加限制：

- **每轮回看预算**：显式限定"本轮最多回看 5 个样本，再访问 2 个老笔记本章节"。
- **写入前 commit**：每次想回看前，AI 必须先把当前思考写到笔记本的 `WIP:` 段。防止回看后"之前的思考全忘了"。
- **回看要留 audit trail**：每次 Read corpus 都在 review_log 里记一笔"why I re-read S012: validating range duration claim"。

### 2.3 Delta 3 — 自由叙事与"没有结构化权重"的摇摆风险

既有方案里 `overlap_kind` 强制把 invariant 分成 duplicate / refinement / orthogonal，这本身是一种**决策权重**（duplicate 必须 drop）。叙事笔记本没有这种硬约束——AI 可以"觉得有点像又有点不像"地模糊描述。

**防摇摆的机制设计**（不完全取消结构化，只是下沉）：

1. **笔记本末尾保留"结构化总结段"**：每张 archetype 卡片的最后一段必须是一个**精简版 PartialSpec**（3-5 条核心规律 + 每条的 sample_refs）。叙事在上面铺陈，结论在下面收敛。这样既保留叙事的探索性，又保留结构化的纪律性。
2. **双角色交替**：SKILL.md 里要求 AI 在每张卡片里演两个角色——"observer"写叙事，"auditor"写反思。auditor 的职责就是审查叙事里的模糊描述："你说'大多数样本量能收缩'，具体是哪几个？量能收缩的阈值是多少？"
3. **外部不变量**：即使叙事自由，**总有一个硬性约束**——每条结论必须能指向 ≥2 个样本 ID。这个约束既有方案也有，新方案不能丢。

### 2.4 Delta 4 — 宏观/微观双层 skill 的边界

用户提到"宏观/微观双层 skill 拆分"，这是一个**哲学落地的工程关键**。

#### 2.4.1 两个 skill 的职责划分

**宏观 skill `synthesize-archetypes`**（"研究主管"视角）：
- 输入：用户意图（"这批突破我想研究是否有新形态"）+ 已有 feature_library 状态
- 工作流：
  1. 读 INDEX.md + 最近的 review_log → 形成**当前知识地图**
  2. 决定研究计划（研究哪个 archetype 分支？开一条跨形态线索？）
  3. 调度微观 skill（"请微观 skill 对 S007 做深挖"）
  4. 汇总微观 skill 的产出，写入 cross_cutting/ 笔记 或 更新 archetype 卡片
- 输出：更新后的 INDEX.md、updated archetype 卡片、下一步研究计划

**微观 skill `deep-dive-sample`**（"一线分析师"视角）：
- 输入：一组小规模样本 ID（1-5 个）+ 当前研究上下文（一段文字，从宏观 skill 传入）
- 工作流：
  1. Read 指定样本的所有资料（segment_text + detail + zoom）
  2. 在样本级别做深度观察（形态命名、数值交叉验证、异常点标记）
  3. 写一个**证据卡**（evidence card），包含：样本 ID、形态归类、核心观察（3-5 bullet）、与宏观假设的对齐/冲突
- 输出：一张 evidence card 到 corpus/<ID>/evidence_cards/<timestamp>.md

#### 2.4.2 通信契约

**文件系统作为外部工作记忆**——两层 skill 之间**不通过 prompt 传递长内容**，全部走文件：

```
宏观 skill                           微观 skill
   │                                     │
   ├──调用──> "deep-dive S007, S012"      │
   │   (+ 传入 1-2 行研究上下文)          │
   │                                     ├─ Read corpus/S007/*
   │                                     ├─ Read corpus/S012/*
   │                                     ├─ Write corpus/S007/evidence_cards/...
   │                                     └─ Write corpus/S012/evidence_cards/...
   │                                     │
   │<──返回──────────────────────────────┤
   │   (一行 summary + 指向 evidence_cards 的路径)
   │
   ├─ Read corpus/S007/evidence_cards/xxx.md
   ├─ Read corpus/S012/evidence_cards/xxx.md
   └─ Write archetypes/<archetype>.md （更新叙事）
```

**为什么这个设计重要**：
- **Context 预算解耦**：微观 skill 每次调用都是独立 context，不会污染宏观 skill 的 context。宏观只读 evidence_cards（每张 ~200 tok）的精华。
- **并行化潜力**：宏观 skill 可以一次派发 N 个微观调查（虽然当前只有 Claude Code 单 session 执行，但文件路径天然支持后续扩展）。
- **审计可回放**：所有证据卡都留档，事后可以追溯"archetype X 的结论是基于哪些证据卡"。

这个契约本质上是在模仿**真实研究团队的运作**：主管写大纲、分析师做一手调查、中间靠共享文档柜通信。这是"拟人化"在工程层面最有价值的一次落地。

#### 2.4.3 边界何时失效？

- **样本数 < 10 时**：两层拆分是 overkill，直接用单层归纳（回退到既有方案）。
- **首次冷启动**：宏观 skill 没有 INDEX.md 可读时，先退化为"初始化 INDEX.md"模式，从零开始。
- **微观 skill 被过度调用**：如果宏观 skill 一次派发 30 个微观调查，成本爆炸。必须在宏观 skill 的 SKILL.md 里限死"单次最多 5 个微观深挖"。

---

## 3. Drift / 上下文爆炸 / 成本 / 可复现性：诚实的风险盘点

### 3.1 Drift（最严重）

**具体风险场景**：
- AI 在叙事笔记本里写"S007 的盘整是 55 根"，下一轮复盘时把它"顺手"改成"约 40-60 根"，过几轮后又变成"短于一个月"。从具体到模糊的滑移，没有 PartialSpec 的 evidence_receipts 就很难察觉。
- 同一个 archetype 的定义在不同章节里微妙不一致。用户在 review 时发现两处描述打架，但很难追溯哪个是对的。

**为什么结构化方案不容易 drift**：YAML schema 强制每条 invariant 带数值范围+样本 ID，任何修改都是显式 diff。

**叙事方案的缓解手段**（必须全部启用）：
1. **archetype 卡片末尾的"结构化总结段"**（§2.3.1）—— 把硬约束留在笔记本内部
2. **卡片元数据 frontmatter**：每张卡片带 `last_modified_samples: [S007, S012]` 字段，改动时强制更新
3. **定期"auditor pass"**：每 3-5 轮运行一次专门的 audit 子任务，让 AI 扫描所有 archetype 卡片 + evidence_cards，标出自相矛盾处

**即使加了这些，drift 也比既有方案更容易**。这是哲学选择的代价，不是可以完全消除的工程问题。

### 3.2 上下文爆炸

**场景**：
- 一本 archetype 卡片累积到 500 行（10 轮归纳后），每次 Read 它就占 ~4k tokens
- Evidence cards 累积到几百张，Grep 的结果本身就很长
- 宏观 skill 为了"了解全局"可能读入 INDEX.md + 5-6 张 archetype 卡片 + 20 张 evidence cards = 轻松突破 50k tokens

**缓解**（必须在 SKILL.md 里写死）：
1. **按需加载**：除非任务需要，不读完整 archetype 卡片，只读 frontmatter + 末尾结构化段
2. **Compact 的责任**：每 N 轮由 AI 主动 compact 自己的笔记本（archetype 卡片超过 300 行就必须压缩）
3. **Hard cap**：宏观 skill 单次读入 tokens < 40k。超过则强制"先 compact 再继续"。

### 3.3 成本

**相对既有方案的增量成本**（Opus，粗估）：

| 场景 | 既有方案 tokens | 高智能化 tokens | 增量 |
|---|---|---|---|
| 单次 skill 调用（5-10 样本 × 3 轮归纳）| ~500k input | ~800k-1.2M input | +60%~140% |
| 完整研究 session（3 个 archetype 迭代）| ~1.5M input | ~3M-5M input | +100%~230% |
| 首次冷启动建 INDEX | ~0（N/A） | ~200k 一次性 | 新增 |

**成本膨胀的来源**：
- AI 主动回看样本 → 重复读入同一张图（Claude Code 不做图像缓存）
- 笔记本增长后 Read 成本持续上升
- 双层 skill 之间有 handshake overhead（虽然 evidence_cards 压缩过，但 Read 总有成本）

**应对**：
- 把高智能化定位为**低频深度工具**（每周 1-2 次、每次 30-60 分钟研究），不是每天跑
- 在 P0-P1 先跑既有方案，积累 feature_library。高智能化做在**已有 archetype 基础之上的 refinement**，不做冷启动
- Sonnet 降级不适用（多模态能力差距大），必须用 Opus

### 3.4 不可复现性

**具体问题**：
- AI 第一次研究矩形形态得出"持续 40-80 根"的结论
- 两周后用户再跑一次，AI 读了之前的笔记本 + 相同样本，得出"持续 35-70 根"
- 两个结论都"合理"，但用户无法复现确定性

**结构化方案里这个问题轻得多**：YAML 是离散的，两次运行要么相同要么明显不同。

**缓解（部分，不彻底）**：
- 所有研究输出带 seed（当前样本 ID 列表 + 当前 feature_library 状态的 hash）
- 结论 diff 时强制 AI 解释"为什么这次和上次不同"（是新样本改变了结论，还是我自己摇摆？）

**坦率说**：如果用户目标是"产出可复现的确定规律"，高智能化方案不是正确选择——它更适合"探索未知形态、产生假说、启发人类思考"的阶段。

---

## 4. 独特价值：这些东西是否真的只能靠高智能化？

这是本节对自己最严格的拷问——**如果既有结构化方案也能做，那高智能化就是 over-engineering**。

### 4.1 形态识别的模糊性

**问题**：真实的形态不是离散的。"矩形盘整"和"对称三角形"之间有连续谱，"U 底"和"W 底"有时会互相渗透。

**结构化方案的局限**：YAML schema 鼓励 AI 把样本硬塞进某个 archetype。当 S042 介于两种形态之间时，AI 倾向于"选一个"而非"保留模糊"。

**拟人化方案的优势**：
> "S042 在前 30 根看像矩形盘整，但后 20 根振幅开始收缩，像是在从矩形转向三角形。这种形态学上的**过渡态**在 S007、S019 上也出现过。可能是一个有意义的子 archetype——'矩形-三角过渡盘整'。"

**判断**：✅ 真实增量。这种叙事式的"模糊边界观察"在 YAML schema 里很难自然表达（`archetype` 字段是单选）。而这些模糊带恰恰是**人类直觉的优势领域**，也是用户最想捕捉的东西。

### 4.2 跨样本类比推理

**问题**：因子发现的关键往往是"看到 A 场景里的 X 现象和 B 场景里的 Y 现象其实是同源的"。

**例子**：
- 矩形盘整的"量能先收缩后放大"
- U 底的"最低点附近成交量塌缩"
- 旗形的"旗杆放量，旗面缩量"
- 这三者**共享"蓄势-释放"的底层韵律**，但各自的形态表征不同

**结构化方案的局限**：每个 archetype 独立归纳，跨 archetype 的共性需要用户（而非 AI）后期手工合并。

**拟人化方案的优势**：cross_cutting/volume_rhythm_observations.md 就是专门给 AI 写"跨形态观察"的地方。AI 可以 Grep 多个 archetype 卡片里的量能描述，合成一个**跨形态不变量**（"成交量的二阶结构——先收缩后扩张——可能比任何单一形态更有普适性"）。

**判断**：✅ 真实增量。这种**跨语境类比**是 LLM 的核心强项，不应被结构化 schema 压抑。

### 4.3 新规律的"涌现"

**问题**：用户希望发现**未在现有 13 因子框架中预设的**形态规律。

**结构化方案的局限**：SYSTEM 条款要求 AI 声明 `overlap_kind` 时必须对现有 13 因子做比较。这本质上是**在现有因子空间的"边缘"寻找 refinement 或 orthogonal**，很难跳出整个框架看问题。

**拟人化方案的优势**：在 cross_cutting 笔记里允许 AI 写"我注意到……这似乎不属于现有任何因子类别"而不必立刻分类。涌现的规律可以**先描述再分类**。

**判断**：⚠️ 部分增量。这个点可以**通过改写既有方案的 SYSTEM 条款**部分实现（放宽 `overlap_kind` 强制），不一定需要整套拟人化。但"允许规律先模糊后清晰"确实在自由叙事环境里更自然。

### 4.4 与形态直觉的对齐度

**问题**：交易员写形态笔记是这样的——"这个盘整很紧，但它在高位，所以不信任"。语气里有**权衡**、**直觉**、**风险意识**，不是一条条的规律。

**结构化方案的局限**：PartialSpec 的原子是 invariant（"规律"），不是"判断"。AI 被迫把"我觉得不对"翻译成具体阈值，会丢失元信息。

**拟人化方案的优势**：叙事笔记天然承载这种元信息。"这条规律我不太确定，需要更多样本"、"这个观察和 S012 冲突，但我倾向于相信 S012 是异类"。这些元信息对用户 review 时极其重要。

**判断**：✅ 真实增量，但主要**对人类 review 流程有价值**，对下游 `mining/` 验证流程无直接价值（mining 只吃具体阈值）。

### 4.5 哪些"优势"其实是假的？

**伪优势 1：AI 更聪明**
既有方案和高智能化用的都是同一个 Claude Opus 4.7。智力没有差别。差别在**工作空间**和**自主性**，不是智力。

**伪优势 2：更少人工**
恰恰相反——高智能化产出的是**需要人类深度阅读的散文**。review 成本更高，不是更低。既有方案的结构化 YAML 更容易快速扫查。

**伪优势 3：更好的因子**
最终因子质量由 `mining/` 的 OOS 验证决定。两套方案产出的 Factor Draft 在同一个 falsifier 下没有先天差异。差异在于**能发现的假设范围**（高智能化可能产出既有方案想不到的假设）。

---

## 5. 与既有方案的整合策略

### 5.1 不是二选一——是渐进叠加

**阶段 A（对应既有方案的 Phase 1-3）**：纯既有方案。Corpus exporter、PartialSpec、多轮归纳、skill 封装。**MVP 优先**，因为它风险可控、产出可落地。

**阶段 B（对应既有方案的 Phase 4+）**：在 feature_library 有 3-5 个 archetype 后，**叠加**高智能化哲学：
- 新增 cross_cutting 目录，让 AI 做跨 archetype 观察
- 升级 skill 支持"回看模式"（AI 可以主动 Read corpus）
- 引入宏观 skill 作为 orchestrator（微观 skill 沿用既有 induce-formation-feature）

**阶段 C（长期）**：当拟人分析师工作流稳定后，考虑**简化**既有方案——把 PartialSpec 降级为 archetype 卡片末尾的"结构化总结段"，不再作为多轮归纳的核心中间态。

### 5.2 硬边界：不要做的事

- ❌ **不要在 P0 就引入高智能化**。冷启动阶段没有笔记本积累，优势出不来，成本先来。
- ❌ **不要让 AI 完全脱离结构化**。总要保留 archetype 卡片末尾的结构化段，不然 Factor Draft 生成会回到原始的 free-form 散文，下游 `add-new-factor` 无法对接。
- ❌ **不要忽视 drift 审计**。必须有定期 auditor pass，否则笔记本会慢慢腐烂。
- ❌ **不要期望高智能化替代 mining 验证**。它是更好的 hypothesizer，不是更好的 falsifier。mining 流水线不可替代。

### 5.3 工程最小改动清单（如果将来决定启用）

在既有方案的基础上：

1. **Corpus 目录结构**（新）：`corpus/<SID>/` 布局，每个样本独立目录
2. **笔记本目录结构**（新）：`docs/research/feature_library/archetypes/*.md` + `cross_cutting/*.md`
3. **宏观 skill**（新）：`.claude/skills/synthesize-archetypes/SKILL.md`
4. **微观 skill**（改既有）：`induce-formation-feature` 改造成"单样本/小样本深挖模式"，输出格式从 PartialSpec 改成 evidence_card
5. **Auditor 子流程**（新）：定期运行的一致性审计
6. **INDEX.md 自动维护**（新）：每次 skill 运行后更新

**估算工程量**：比既有方案 Phase 1-3 **增加 ~40%**（约 1-2 周额外开发）。性价比只有在 feature_library 有实质积累后才显现。

---

## 6. 最终判断（不做稻草人、不过度美化）

### 6.1 高智能化哲学的真实地位

**不是**：
- 既有方案的替代品
- 冷启动的首选
- 能产出更好因子的方法

**是**：
- 既有方案的上层升级
- 探索模糊形态和跨样本类比的独特工具
- **对人类研究体验**（不是对下游 mining 验证）有独立价值

### 6.2 用户做决策时的判别问题

问自己这些问题：

1. **我现在卡在哪？**
   - 如果卡在"连第一批形态规律都没有" → 既有方案（Phase 1-3）
   - 如果卡在"已有几个 archetype 但隔着隔阂无法融会贯通" → 值得升级到高智能化

2. **我愿意为 review 投入多少时间？**
   - 如果希望 AI 产出"即读即用"的规律 → 既有方案
   - 如果愿意像读研报一样花 30 分钟消化叙事 → 高智能化

3. **我最关心什么？**
   - 因子落地速度 + 可复现性 → 既有方案
   - 发现未知形态 + 深度理解 → 高智能化

4. **成本预算？**
   - Opus token 敏感 → 既有方案
   - 可以接受 2-3 倍成本换深度 → 高智能化

### 6.3 一句话结论

**高智能化哲学是"把 AI 从归纳员升级为分析师"的范式偏移，它的独特价值集中在形态模糊性、跨样本类比、规律涌现三个点上；代价是 drift、成本、可复现性。正确的用法不是替代既有方案，而是在既有方案跑通后的 P2 阶段叠加使用，让 AI 在自己搭建的笔记本和 corpus 目录里做拟人化的深度研究。**

用户最终的决策应该基于：**是否已有 feature_library 积累**（有 → 可升级）+ **研究目标是否偏探索**（是 → 可升级）+ **是否愿意承担 ~2x 成本和 drift 风险**（是 → 可升级）。任一不满足，留在既有方案里继续 MVP 验证更明智。

---

## 附录 A — 关键术语速查（本方案专用）

| 术语 | 含义 |
|---|---|
| Archetype 卡片 | 一个形态原型对应一张 Markdown 卡片，存于 `archetypes/` |
| Cross-cutting 笔记 | 跨 archetype 的观察（如量能节奏），存于 `cross_cutting/` |
| Evidence card | 微观 skill 对单样本的深挖证据，存于 `corpus/<ID>/evidence_cards/` |
| INDEX.md | feature_library 的全局知识地图 |
| 宏观 skill | `synthesize-archetypes`，研究主管视角 |
| 微观 skill | `deep-dive-sample`（或改造版 induce-formation-feature），一线分析师视角 |
| Auditor pass | 定期一致性审计子任务，扫查笔记本自相矛盾处 |
| 回看预算 | 每轮 AI 允许主动 Read corpus 的样本数上限 |
| 结构化总结段 | archetype 卡片末尾的硬约束部分，保留 PartialSpec 风格 |

## 附录 B — 与既有方案的对照速查

| 既有方案概念 | 高智能化对应 | 关系 |
|---|---|---|
| PartialSpec YAML | archetype 卡片末尾的结构化段 | 降级保留 |
| Multi-round compact | 研究 session（由宏观 skill 编排） | 包含 |
| Batch / NegBatch | 宏观 skill 派给微观 skill 的样本列表 | 抽象化 |
| SYSTEM 5 条款 | archetype 卡片的 frontmatter 约束 + auditor pass | 分散 |
| Factor Draft | 不变，仍是最终产出之一 | 不变 |
| `add-new-factor` skill | 不变 | 不变 |
| `mining/` 流水线 | 不变，仍是 falsifier | 不变 |

---

**文档结束。**
