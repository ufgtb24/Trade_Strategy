# Feature Mining Framework — 三问复盘

> **日期**：2026-04-26
> **关联 spec**：`docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md`（不修改，仅产出 delta 建议）
> **来源**：spec-revisit-v3 agent team 两轮深度讨论（scheduler / ml-method / curriculum 三专家 + lead 整合）
> **读者预设**：已读 spec，本文不重述其设计

---

## §0 触发与范围

### 0.1 用户原文 3 问

> **问题 1**：当前的调度功能包含"每周 1-2 次"，"每月 1-2 次"等论述。但是我需要的使用场景是用户控制的，灵活的：
> - 当用户有一批经过挑选的 K 线数据，那么丢进去，可以找到这批数据的 features。
> - 如果用户又有一批新的数据（多张或仅仅一张 K 线图），那么丢进去，会在已有 features 的基础上，找到新的 features 或完善已有 features。
> - 用户可以设置 batch size，当用户丢入多张 K 线图时，内部会将丢入的 K 线图分成若干批次，逐批次总结规律（利用 inducer 的按 batch 发现规律，但是 batch 不能太大，避免触碰模型能力瓶颈）。
> - 如果初始化，那么之前库中的 features 就没有了（如果需要可以选择固化到外部文件），在丢入新的数据后重零开始归纳 features。
>
> 为了实现上述由用户指定的灵活可控的训练流程，Orchestrator 是否有必要使用 AI 模型，能否用确定性的 python 规则来管理？

> **问题 2**：由于 critic 的存在，已经总结为规律的 feature 还会被变动（比如说拆分，合并）。那么是否之前用来得到原先 feature 的 K 线图还需要再次经过 pipeline 来优化新 feature？这让我联想到深度学习中，每个样本可能会被多个 epoch 重复训练，从而充分利用数据的信息量，而不是奢侈的每个数据只使用一次。那么类似的，我不禁会想，本框架中，是否应该考虑让每个 K 线图多次经过 pipeline？这样是否会让框架发现更好的 feature？

> **问题 3**：会不会有一种可能，让 critic 在训练过程中动态更新 inducer 的 prompt，从而动态升级 inducer 总结规律的能力？例如当库中的某些规律已经很巩固了，那么可以鼓励 inducer 发现库中没有的新规律。这个观点是我的不严谨的初步想法，也许在数学和逻辑上有很大 bug，或者信息泄露等作弊风险。

### 0.2 范围限定

本文**仅**针对上述三问展开分析与 delta 建议，**不**全面回顾 spec 其他部分。原 spec 不被修改 —— 文末 §5 列出 delta 清单交用户决策。

### 0.3 输出策略

- 三个独立答案 → §1 / §2 / §3
- 三问的横向耦合 → §4
- spec 的具体 delta 修订建议（必改 / 可选 / 不建议改）→ §5
- 留给用户的开放点 → §6

---

## §1 Q1 — Orchestrator 应该是 AI 还是 Python 调度器

### 1.1 现状回顾（仅关键点）

spec §1.1 把 Orchestrator 定位为 "Claude Opus 长 session"，§2.3 给出了 6 个触发条件（T_init / T_orphan / T_period / T_user_review / T_critic_disputed / T_critic_health），其中 4 个带有"自动节奏"的频次估计（每周 / 每月）。spec §4.6 已明确 Orchestrator 不持有任何 features 内容，纯调度。

### 1.2 用户场景与 spec 的偏差

用户原文勾画的是**用户驱动的 ingest 流**：

| 场景 | 期望行为 |
|---|---|
| 第一次丢一批数据 | 找到这批的 features |
| 后续追加（1 张或多张）| 在既有库基础上完善 / 新增 |
| 多张时分 batch | 用户设 `batch_size`，内部切片 |
| 初始化 | 清空库（可选 snapshot），从零开始 |

**关键偏差**：spec 的"每周 / 每月"自动触发预设了"系统按时间节奏自我演化"，但用户场景里**所有时机都由用户的 `ingest` 命令决定**。这从根本上消除了 Orchestrator 需要"判断时机"的需求。

### 1.3 三个候选方案

| 方案 | 描述 |
|---|---|
| **A（维持）** | Orchestrator = Claude Opus 长 session，按 spec §1.1 不变 |
| **B（缩减 AI 职责）** | Orchestrator 仍是 AI，但只负责自然语言交互 / 模糊指令翻译 / 摘要生成，调度逻辑下沉到 Python |
| **C（完全 Python）** | Orchestrator 降级为 Python CLI 工具集（`feature-mine ingest / status / review-orphans / ...`），AI 仅在用户主动 `feature-mine ask` 时介入做 NL→CLI 翻译（可选薄壳） |

### 1.4 现状映射 — Orchestrator 职责的 AI 必要性

| 职责 | spec 出处 | AI 必需 | 理由 |
|---|---|---|---|
| 决定走 batch / incremental / triggered batch | §2.1, §1.1 | 否 | 输入是数值条件，输出是离散模式，本质 if-else |
| 监控 6 个触发条件 | §2.3 | 否 | 全部是计数器 + 时间戳比较 |
| 把样本分给 Inducer（cold-start 抽 8~12 张）| §2.2, §5.4 | 否 | 抽样策略可参数化（FIFO / 用户指定 / 分层） |
| 把候选交给 Librarian | §2.1 | 否 | 纯结构化数据 pipeline，schema §4.3 已固化 |
| 任务排队（critic_review_queue / orphan_samples）| §2.3, §4.1 | 否 | 文件系统 + 队列 = `pending/` 目录 + JSON/YAML |
| 状态汇报给用户（INDEX.md / UI 提示）| §2.3, §4.6 | 否 | 模板化报告，从文件聚合 |
| 持久化状态 | §1.3, §4.6 | 否 | spec §4.6 已明确 Orchestrator 自己不存内容 |

**结论**：spec 中 Orchestrator 的"决策"全部是确定性规则。AI 价值为零，甚至为负（引入不确定性、增加 token 成本、降低可调试性）。

### 1.5 推荐方案：C（完全 Python）+ 可选 NL 适配薄壳

**核心命令套件**（草案）：

```
feature-mine reset [--snapshot <path>]      # 清空库（可选先归档）
feature-mine ingest <samples...> \
    --batch-size N \                        # 默认 10
    --mode {auto|batch|incremental} \       # 默认 auto
    --tag <experiment-name>                 # 可选
feature-mine status                         # 摘要
feature-mine list --band <band>             # 列 features
feature-mine show <feature-id>              # Librarian.explain(id)
feature-mine review-orphans                 # 把孤儿入 Critic 队列
feature-mine review-critic [--auto-approve] # 拉起 Critic 处理 queue
feature-mine snapshot <path>                # 备份
feature-mine export-yaml <path>             # 导出供 add-new-factor
```

**ingest 内部流程伪代码**（含 archetype-level hint，由 Q3 推导）：

```python
def ingest(samples, batch_size, mode):
    preprocess(samples)                          # Opus 一次性多模态 → nl_description.md
    effective_mode = resolve_mode(samples, batch_size, mode, library_state)

    # 关键新增：构建 archetype-level 形态空间地图（Python 纯统计 + 缓存）
    archetype_map = build_archetype_map(librarian)
    # 仅 archetype 级（"形态结构类" / "量价关系类" / ...），不含具体 feature 文本
    # 避免 co-induction 信号污染（spec §4.3）

    if effective_mode == 'incremental':
        for s in samples:
            run_incremental(s)                   # Path V × 全库 + Path U（N=1）
            if all_no_or_ambiguous(s):
                orphan_samples.append(s)
    else:
        for chunk in chunked(samples, batch_size):
            out = run_inducer_batch(chunk, context_hint=archetype_map)
            librarian.upsert(out)

    print_summary()
    check_passive_alerts()                       # 见 1.6
```

**触发清单的语义重塑**（修订 §2.3）：

| 原触发 ID | 新语义 |
|---|---|
| **T_init** | 删除"自动"语义 → 仅由 `feature-mine ingest`（首次）触发 |
| **T_orphan** | 删除"自动"语义 → 改为**被动提醒**：CLI 在每次 ingest 末尾检查 orphan 数 > 阈值（如 20）就 `[WARN]` 提示，由用户决定是否跑 `review-orphans` |
| **T_period** | 同上，改被动提醒（如自上次 batch 起 ≥ 30 天） |
| **T_critic_health** | 同上，改被动提醒 |
| **T_user_review** | 保留（本就是用户命令） |
| **T_critic_disputed** | 保留（仅"入队"语义，不自动跑，与原 spec 一致） |

### 1.6 被动提醒 vs 彻底放手 — 选前者

立场：**接受"用户控制"原则，但 CLI 在每次 `ingest` 末尾打印警告**，不自动跑、不阻塞、只显示。

```
$ feature-mine ingest *.png --batch-size 10
... ingest summary ...
[WARN] orphan_samples 累计 47 条（阈值 20），建议运行 `feature-mine review-orphans`
[WARN] 自上次 health check 已 45 天，建议运行 `feature-mine review-critic --kind health`
```

**为何不彻底放手**：用户长期不管会让库状态僵化（孤儿堆积、disputed 累积），但"打印警告"零成本、不强迫、符合奥卡姆。如果用户 `--quiet` 关警告，那是用户的明确选择。

### 1.7 Tradeoff 表（A vs C）

| 维度 | A（AI Orchestrator）| C（Python CLI）|
|---|---|---|
| 可控性 | 用户每次 ingest 要"求" Opus 判断模式，可能被 AI 自由心证 | 用户参数显式指定，结果可预测、可重放 |
| 成本 | 每次 ingest 多调 1 次 Opus（哪怕只是判模式）| 零 LLM 调用（Inducer/Critic 才算 LLM 成本）|
| 延迟 | Orchestrator 推理 + spawn subagent，多 1 次 round-trip | 本地 Python 立即决策 |
| 可调试性 | "为什么这次走了 incremental？" → 看 Opus reasoning | 看 if-else 分支即可 |
| 一致性 | 同样输入可能不同决策（Opus 温度）| 同样输入永远同样决策 |
| AI 必需价值 | 自然语言交互 / 模糊指令 / 回顾叙述 | 全部可由 `feature-mine ask` 一次性 Opus 调用补足 |

**选 A 的唯一情形**：用户希望"对话式"操作。但这是**前端体验问题**，不是调度逻辑问题，可在 Python CLI 之上加 NL→CLI translator 薄层（一次性 Opus 解析意图 → 生成 CLI 命令 → 用户确认 → 执行），不需要给 AI 调度权。

**选 B（缩减 AI）的问题**：缩减后剩下的"NL 摘要生成"和"翻译模糊指令"已经不是调度，而是 UI 层。继续叫 Orchestrator 反而让架构混乱。直接砍掉、改名"前端 NL adapter"更清晰。

### 1.8 极端方案讨论（完全取消 Orchestrator 角色）

如果连 Python 调度器也不要，让 4 件工具（CLI + Inducer + Librarian + Critic）自己组合：

| 职责 | 谁兜底 |
|---|---|
| chunked batch processing（30 张 → 拆 3×10）| **CLI 自己**（`ingest` 内部 `for chunk in chunked(...)`），属于 CLI 的 argument parsing + 循环 |
| 孤儿样本累积监控 | **Librarian**（incremental 路径返回 verdict，all-no/ambiguous 时写入 orphan）；用户主动 `review-orphans` 触发消化 |
| 任务排队（多 ingest 并发）| **文件锁 + pending 队列**（OS 级而非 agent 级）|
| 状态汇报 | CLI `status` 命令读 `INDEX.md` 即可 |

**结论**：完全取消 Orchestrator 角色**可行**。这是最简洁方案。本文以"保留 Python CLI 调度器作为 entry script"为推荐方案 —— 即"Orchestrator 角色保留，但实现降级为 Python CLI"。

### 1.9 推荐 + Phase 路线影响

**推荐**：方案 C。

- spec §1.1 中 Orchestrator 的 "Claude Opus 长 session" 定位 → 改为 "CLI 调度器（feature-mine 命令套件，纯 Python）"
- spec §2.3 触发清单语义改为"被动提醒触发"，删除"频次估计"列
- spec §5.4 Phase 2 中"Orchestrator skill（Hybrid C 节奏 + 触发监控）3 天"工程量可下降到 1.5 天，节省的预算可投入 Critic 或 dev UI 集成

---

## §2 Q2 — 是否引入 multi-epoch 重训

### 2.1 现状每张样本"用了几次"

阅读 spec 现状：

| 样本生命周期事件 | 是否触动 (α, β) |
|---|---|
| **首次进库**（cold-start batch 或 user pick）| 是 — Inducer 多图对比产 candidate_features，每个 candidate 给 (K, N) 计入 |
| **随后的 incremental 阶段**（每张新样本入库时跑 Path V）| 老样本**不被重复评估** —— Path V 是新样本对全库老 feature 的 verify，不是反过来 |
| **Critic split / merge / rewrite 后**| spec §4.7 要求 Librarian.recompute(feature_id) 从 ObservationLog 重放 (α, β)，但**老样本是否要重新过 Inducer**没有明说 |
| **Critic demote / 删除后** | (α, β) 只是变弱或归零，老样本**不再被复用** |

**结论**：spec 现状下，**每张样本对每条 feature 只被 Inducer / Path V 评估 1 次**（首次进库或首次 verify 时）。后续 feature 状态变化（split / merge / promote）不会让老样本再次"投票"。这意味着 spec 是 "**1 epoch 训练**" 模式。

### 2.2 用户提的 DL epoch 类比

DL 中 multi-epoch 的本质是**让模型在同一份数据上反复梯度下降**，因为单次前向 + 反向不足以拟合复杂模式。**前提是模型有可学习参数 + 损失函数明确**。

本框架的"模型"是什么？是 `(α, β)` 缓存量 + features 的 text/embedding。其中：

- **(α, β)**：本质是**事件计数**，不是可学习参数。multi-epoch 等价于"对同一事件反复计数" → 直接破坏统计独立性
- **text / embedding**：由 Inducer 产出 + Critic 修订，是**符号性结构**，不靠梯度更新

所以 DL 的"epoch"概念**不能直接套用**。但用户的直觉触及了一个真问题：**老样本的信息量是否被充分利用？**

### 2.3 在本框架的对应物（三个相关但不等价的机制）

| 机制 | 含义 | 触发条件 |
|---|---|---|
| **Replay** | Critic 修改某 feature（split / merge / rewrite）后，对该 feature 的历史样本重新计算 (α, β)。**不重跑 Inducer**，只走 ObservationLog 重放 + 必要时新 Path V | Critic 提议被 approve 时 |
| **Re-induction** | 让若干老样本**重新进 Inducer**，试图产生新 feature 或与新批次共归纳。**重跑 Opus** | 用户显式触发，代价高 |
| **Re-verification** | 仅对单个老样本 × 单条新 feature 跑 Path V（轻量 L1 调用） | 自动 — 每次新 feature 落库时对采样的老样本做一遍 |

**关键判断**：
- **Replay** = 必须实现（Critic 改 feature 后不重算 = 数学不一致，spec §4.7 已要求）
- **Re-induction** = 可选，用户触发，回应"DL epoch"直觉的最直接对应物
- **Re-verification** = 已隐含在 spec 的 Path V 设计里（incremental 阶段会做），不需要新增

### 2.4 双重计数风险

multi-epoch 在本框架里最大的危险：**同一物理样本对同一 feature 的多次评估，不能简单累加 (α, β)**，否则 Beta-Binomial 的 i.i.d. 假设失效，P5 失去频率派可解释性。

**解决方案 — rollback + apply 模式**（不允许累加）：

ObservationLog 新增字段 `epoch_tag: str`（**不是** `epoch_id: int`，避免被误读为可无限累加）：

- `null` — 首次评估
- `replay-after-split-{batch_id}` — Critic split 后的重放
- `replay-for-new-feature-{F-id}` — 新 feature 落库后对老样本的补 verify
- `reinduction-{batch_id}` — 用户主动 re-induction 时的 epoch

(α, β) 累加规则：

| 场景 | 处理 |
|---|---|
| 同 (sample_id, feature_id, source_kind, epoch_tag) 完全重复 | Librarian 拒绝写入 |
| 同 (sample_id, feature_id) 但 epoch_tag 不同 | **rollback + apply 模式**：找出该 (sample, feature) 上历史所有非 superseded 条目 → 标记为 `superseded_by=<新条目 ID>` → 仅新条目进入 (α, β) recompute。**效果**：同一物理样本对同一 feature 永远只持有最新判读结果 |
| 不同 sample 或不同 feature | 正常累加 |

**唯一例外**：Critic split 后两条新 feature 是**不同 feature_id**，所以同一样本对 F-001a 和 F-001b 各贡献一条事件**不算**双重计数（语义上是两次独立判断）。

### 2.5 三种机制的触发权归属（与 Q1 调度方案兼容性）

在 Q1 推荐的 Python CLI 调度下：

| 机制 | 触发模型 | 推荐选项 |
|---|---|---|
| **Replay** | 每次 Critic 动 feature 后**自动入队**（写 `pending_replays.yaml`），下次用户跑 `ingest` 前 CLI 检查队列 → 若有 pending → **阻塞**并提示 `先跑 feature-mine apply-replays`。同时保留 `feature-mine replay --feature F-001` 作为手动出口 | **入队 + 用户消费**（不自动执行） |
| **Re-induction** | 完全用户触发：`feature-mine list-reinduction-candidates` 列出候选 → 用户挑选 `feature-mine reinduce --samples S03,S07,...` | 候选启发式：(a) 至今对所有 features 均判 no/ambiguous 的孤儿样本 → 最高价值；(b) 仅命中 forgotten/candidate 状态的样本 → 次高 |
| **Re-verification** | 每次新 feature 落库时自动对采样的老样本做（已有 Path V 框架支撑） | 已隐含 |

**Re-induction 时是否复用 nl_description.md**：**复用，不重跑 Opus**。理由：
- Opus 多模态调用是最贵层，重跑成本高
- "早期描述被冻结"偏差实际很小 —— Inducer 拿到的输入是 nl_description **加** chart.png，多模态 Inducer 仍直接看图，nl_description 只是辅助文本
- 仅当用户显式 `--refresh-nl` 时才重生成（标记 `nl_version=2`，老 nl 归档不删）

### 2.6 触发场景（什么时候 multi-epoch 真的有用）

| 场景 | 哪个机制最合适 |
|---|---|
| Critic 拆分了 F-001 → F-001a + F-001b，老样本归属未知 | Replay（按 spec §4.7 选项 A：重跑 Inducer）或 Re-verification（按 Inducer 划分的 assigned_samples 跑 Path V）|
| 用户感觉"库没充分利用早期样本"（早期 batch 时 features 还很少）| Re-induction（用户主动） |
| 新 feature 刚落库，想知道老样本对它支持多少 | Re-verification（自动）|
| Critic merge 两条 feature 后，需要去重 | Replay（spec §4.7 已要求按样本 ID union）|

### 2.7 推荐 + Tradeoff

**推荐**：

1. **Replay 必做**（已是 spec §4.7 半隐含要求）+ 走 pending_replays 队列 + 用户消费机制
2. **Re-induction 可选实现**，留作 Phase 4+ 增强
3. **Re-verification 保持现状**（已在 incremental 路径实现）
4. **新增 `epoch_tag` 字段** + **rollback/apply 模式**保护 i.i.d.
5. 双重计数边界由 Librarian 统一拦截（同 (sample, feature) 仅持有最新条目）

**Tradeoff**：

| 维度 | 不引入 multi-epoch | 引入 multi-epoch（本推荐方案）|
|---|---|---|
| 数学严谨 | i.i.d. 假设保持 | 需 epoch_tag + rollback 机制保护，复杂度 +1 |
| 信息利用率 | 早期样本只评估 1 次，可能错过新 feature | 用户可触发 Re-induction，挖掘潜在价值 |
| 工程量 | 低 | Replay 必做（≤1 天）；Re-induction 可推迟到 Phase 4+ |
| 用户控制 | 一致 | Replay = 半自动（入队 + 用户消费）；Re-induction = 完全用户控制 |
| 与 Q1 兼容性 | 高 | 高 — 三机制都通过 CLI 命令暴露给用户 |

---

## §3 Q3 — Critic 是否应动态更新 Inducer prompt

### 3.1 用户设想拆解

| 维度 | 内容 |
|---|---|
| 触发 | Critic 看到 F-001 已 strong（P5 ≥ 0.60）|
| 动作 | 改写 Inducer prompt：加上"去找跟 F-001 不同的特征" |
| 期望收益 | (a) 节省 Opus tokens（避免重复产已 strong feature）；(b) 鼓励多样性；(c) 主动扩展库覆盖 |

但这与 spec **§4.3 强制约束**直接冲突：*"Inducer 不得查重（不读 features 库）；不得知道老 features 存在（避免 co-induction 信号污染）"*；以及 **§4.5 强制约束**：*"Critic 不能直接写 features 库或动 (α, β)"*。这两条约束并非偶然，是为了保证统计独立性 + 防止 reward hacking。

### 3.2 风险评估表

| 风险类别 | 严重度 | 机理 |
|---|---|---|
| **信息泄露 / Reward hacking** | **高** | Inducer 一旦知道 "F-001 = 紧致盘整 + 量缩"，下次极可能产 "紧致盘整带量价背离"（F-001 的近邻），表面新 feature 但语义高度重叠。Librarian 的 L0 cosine 可能拦不住"换名字的同一规律"，L1 DeepSeek 在语义边界处常判 ambiguous → 该 feature 反而以孤儿身份新生 → **库内出现"语义近亲家族"** |
| **统计独立性破坏** | **高** | Beta-Binomial 的合理性建立在每次观察是 i.i.d. Bernoulli 之上。若 Inducer 产出受库状态影响（"避开已 strong"），则 K/N 是**条件分布**而非独立观察 — `α += K` 在数学上不再代表"独立证据累加"。后验失去频率派可解释性。**这击中 spec §3 的数学根基** |
| **探索崩塌（Distribution drift）** | **中** | 动态 prompt 让 Inducer 系统性偏向"未覆盖子空间"。但已 strong 区域内可能还有有价值细分（F-001 = 紧致盘整，但其内部还有"下跌后" vs "上涨后"子型），将被系统性遗漏。此外，"已 strong"本身可能是早期挑选偏差产物，强化 prompt 会**冻结早期偏差** |
| **Critic 偏差放大** | **中** | Critic 对"已 strong"的判读基于当时库快照。若 Critic 早期 demote/disputed 裁决有错（spec §7 Q1/Q2 暗示阈值未校准），错误会通过 prompt 传染给 Inducer，形成正反馈 |
| **Audit 困难** | 低-中 | spec §4.7 强调"ObservationLog 是真相源、(α, β) 是缓存"。Inducer prompt 随时间漂移 → 同一 feature 多次 observation 处于不同 prompt 上下文 → recompute 时无法重现当时归纳条件 → 破坏 ObservationLog 的可重放性 |

### 3.3 文献参考

| 场景 | 成败 | 与本场景的差异 |
|---|---|---|
| Active learning（uncertainty sampling）| 成功 | 教师有客观 ground truth；学生只挑选样本，**不影响生成** |
| Curriculum learning（easy → hard）| 成功 | 任务难度有客观度量；不改变假设空间 |
| RLHF reward hacking | **失败案例** | 模型一旦学会"奖励信号偏向哪类输出"，会产 surface 满足奖励但实质退化的内容 — 与本场景 Inducer "知道库内有什么"高度同构 |
| Self-play（AlphaGo）| 成功 | 客观胜负信号 + 对抗博弈结构；本场景**没有客观真相**（用户挑选即真相，但 Inducer 看不到反向信号） |

**关键判断**：本场景缺乏"客观对抗信号" — Inducer 一旦获得库的 hint，没有任何机制惩罚"假新颖、真重复"。这正是 reward hacking 易发的土壤。

### 3.4 L1 / L2 / L3 三梯度方案对比

| 维度 | **L1（保守）** | **L2（折中）** | **L3（激进）** |
|---|---|---|---|
| Inducer prompt | 完全静态，不知道库存在 | 注入"高层摘要"（archetype 标签：盘整型 / 突破前形态 / 量价关系）| Critic 直接重写："去找跟 F-001/F-002 不同的特征" |
| 去重职责 | Librarian L0/L1 机械过滤 | Librarian + Inducer 双层 | Inducer 主动避让 + Librarian 兜底 |
| 统计独立性 | 完全保留 | 弱破坏（archetype 是粗粒度，影响有限）| 严重破坏 |
| 信息泄露 | 0 | 低（暴露 archetype 名字，不暴露具体 feature 文本）| 高 |
| Reward hacking 风险 | 0 | 低 | 高 |
| Token 节省 | 0（可能产已 strong feature → 浪费 Inducer + L0/L1 调用）| 中 | 高 |
| 库覆盖扩展 | 被动（靠 Inducer 随机性）| 主动（靠 archetype 缺口）| 主动（靠点名规避）|
| 与 spec §4.3 兼容 | 完全 | 边缘违反（"不得知道老 features 存在"）| 直接违反 |
| 可审计性 | 高 | 中（需新增 inducer_context 字段保留 hint hash）| 低（prompt 漂移破坏 replay）|

### 3.5 L2 在 "Critic 不参与" 前提下的可行性

**前提**：在 Q1 推荐的 Python CLI 调度下，Critic → Inducer 之间不再有"AI 居中协调者"。L2 方案可以由 **Python 模板根据库统计自动生成 archetype 摘要**，**Critic 完全不参与**。这切断了"Critic 主观判断 → Inducer 行为"的反馈环，是 Q1 + Q3 的天然契合点。

#### 3.5.1 archetype 摘要的生成机制

**推荐：方案 B + 缓存 + 人工审核闸**。

| 选项 | 描述 | 评价 |
|---|---|---|
| **A** | Python 扫库读 INDEX.md 中的 `feature.archetype` 字段（需要新增字段，由谁填？）| 否决：Critic 填违反 §4.5；Librarian L1 verify 时填超出其"机械"职责（§1.1）；用户手填违背"自动化累积"目标 |
| **B**（推荐）| Python 调一次轻量 LLM（如 DeepSeek），输入 strong/consolidated features 的 nl_description 列表，要求**输出抽象层标签**（"形态结构类" / "量价关系类" / "位置形态类"，不含具体规律内容）。结果**缓存到 `feature_library/archetype_map.yaml`**，触发条件命中才重生成。**首次生成需用户 approve**（一次性 cost）| 受 LLM prompt 强约束 → 强制抽象层。最不容易引入 bias。工程成本 ≈ C |
| **C** | 纯 K-means 聚类已 strong features，取每簇 centroid 的 top-1 feature 名作 archetype | **风险**：暴露具体 feature 文本（"紧致盘整 + 量缩"作为 archetype = 等价于把 F-001 直接告诉 Inducer）→ **退化为 L3** |

#### 3.5.2 注入时机与可关闭性

- **触发条件**：库内 `status_band ∈ {consolidated, strong}` 数 ≥ 5 才启用（少于 5 时空间地图本身没意义）
- **注入频次**：每次 `feature-mine ingest --batch` 注入；incremental 模式 N=1 不注入（spec §2.4 incremental 走 verify 路径，本来就不调用 Inducer 跨样本对比）
- **CLI flag**：必须加 `--no-archetype-hint`（默认 off，即默认启用）。**对照实验是 L2 的安全闸**

#### 3.5.3 可审计性补救

- **新增字段**：`ObservationLog` 增加 `inducer_context: {prompt_version_id: str, archetype_hint_hash: str | null}`
- **存储策略**：**hash + version_id**，不存全文。`archetype_map.yaml` 本身有版本（git tracked），通过 version_id 可回溯当时全文
- **replay 策略**：**按当时 hint 重放**（保留歧义）。理由：重新跑 Inducer 违背 replay 的"重现历史"语义；archetype 是 Python 确定性产物，hint 的"当时值"本身就是历史的一部分。若用户想"用最新 archetype 重新跑"，应该是显式 `--re-induce` 而非 replay

#### 3.5.4 与 Q2 multi-epoch 的耦合

**强烈推荐：multi-epoch replay 时禁用 archetype hint**（仅 epoch=0 启用）。

机理：multi-epoch 的 Replay 已经是"对同一样本重复观察 → 后验更新"，统计独立性本来就被 epoch 内复用样本破坏。若再叠加"不同 epoch 看到不同 hint"，等价于 Inducer 在 epoch 间的输出分布漂移 → reward hacking 复利效应。

**实现**：epoch>0 时 CLI 强制 `--no-archetype-hint`，不允许用户覆盖。同时 ObservationLog 的 `inducer_context.archetype_hint_hash` 在 epoch>0 记 `"disabled_replay"` 而非 null，以便审计。

### 3.6 替代设计（不动 Inducer prompt 的等价目标）

如果不实施 L2，Q3 的三个目标可以用以下"安全等价物"分别解决：

| 目标 | 替代手段 |
|---|---|
| **节省 Opus tokens** | 调高 batch 触发频次的下限（T_orphan 阈值从 8 调到 12），让 Inducer 每次产出更可能命中新 feature；或在 Librarian 端，对已 strong 的 feature 跳过 L1 verify（已饱和，不必再调）|
| **鼓励多样性** | 把"避免重复"职责**完全收归 Librarian**：用 embedding 比对，cos > 0.85 时**对 K 折半累加**（不丢弃，但减弱影响），既不扭曲 Inducer 输出分布，又抑制"近亲规律"灌水 |
| **扩展库覆盖** | 改进 cold-start 抽样：Orchestrator 优先抽**未被任何老 feature L1=yes 命中**的样本进入下一 batch（操作 sample 选择，不操作 Inducer prompt）。这是 active learning 的合法形式 |

### 3.7 推荐 + 实现路径

**推荐**：保持 spec 当前方案（**L1 等价**），即 Inducer prompt 完全静态。**但**预留 L2 实现路径作为可选增强（在 Q1 推荐的 Python CLI 调度下，L2 因"Critic 不参与"而风险显著降低，可作为 Phase 4+ 增强项）。**绝不走 L3**。

理由（按权重）：

1. **数学完整性**：Beta-Binomial 频率派可解释性是本框架最大资产之一，L3 会从根上瓦解
2. **spec §4.3 强制约束有充分理由**：是 reward hacking 的防火墙，不是设计冗余
3. **节省 token 不是核心痛点**：cold-start 后 batch 频次本来就低，优化 prompt 的边际收益小，但破坏数学根基的边际成本极大
4. **库覆盖问题有更安全的解法**：active sampling（操作样本）而非 active prompting（操作 prompt）

**安全的 L2 升级路径**（若日后真要试）：

1. **第一步（不动 spec）**：在 Librarian.update 中加 `L0 cos > 0.85 → 强制走 L1，且 K 减半累加`。可立即验证 "近亲规律泛滥" 是否真存在 —— 若 L1 持续判 yes，说明 Inducer 本来就在产相似规律，需先解决这个，再谈 prompt
2. **第二步（experimental flag）**：在 CLI 加 active sampling 策略（"挑未覆盖的样本"），dev UI 加开关，对照 baseline 跑 3-5 轮 batch，比较库覆盖度
3. **第三步（如果以上仍不够）**：才考虑 L2 — Python + DeepSeek 自动产 archetype hint，**Critic 不参与**，新增 `inducer_context` 字段保 replay 可重现
4. **绝不走 L3**：Critic → Inducer 直接 prompt 改写，违反 §1.2 职责不可越界硬约束

**用户 Q3 中"信息泄露 / 作弊风险"的直觉是准确的** — 这正是 spec 用 §4.3 / §4.5 的硬约束规避的核心问题。当前 spec 设计是经过深思的防御。

---

## §4 三问交叉影响

### 4.1 Q1 ↔ Q2 — 调度方式与 multi-epoch 的兼容性

| 主题 | Q1 推荐（Python CLI）| Q2 推荐（Replay 必做 + Re-induction 可选）|
|---|---|---|
| **Replay 触发** | CLI 在 `ingest` 前检查 `pending_replays.yaml` → 阻塞提示用户跑 `apply-replays` | 入队 + 用户消费，与 CLI 阻塞机制天然契合 |
| **Re-induction 触发** | `feature-mine list-reinduction-candidates` → 用户手动 `reinduce` | 完全用户控制，符合 Q1 哲学 |
| **冲突点** | 无明显冲突 | — |

**结论**：Q1 + Q2 是**强耦合 + 强契合**关系。Q1 提供的 CLI 命令架构是 Q2 三种机制（Replay / Re-induction / Re-verification）的自然落地容器。

### 4.2 Q2 ↔ Q3 — multi-epoch 与动态 prompt 的耦合风险

| 场景 | 风险 |
|---|---|
| epoch=0 时启用 L2 archetype hint | 可控（Python 确定性 + 抽象层 + hash 审计）|
| epoch>0 时仍启用 L2 hint | **复利风险**：每次 epoch 库已变 → archetype 可能更新 → 同一样本不同 epoch 看到不同 prompt → Inducer 输出分布漂移 → reward hacking 信号被放大 |

**结论**：Q2 + Q3 同时启用时**必须互斥**，即 epoch>0 时强制禁用 archetype hint。这是一条硬约束。

### 4.3 Q3 ↔ Q1 — 动态 prompt 的信号源归属

如果按 Q1 推荐删除 Orchestrator AI，Q3 的 L2 方案"谁来注入 archetype hint"的答案是：

- **Python CLI 自己**（在 `feature-mine ingest` 内部 spawn Inducer 前，跑一段 Python 脚本扫库 → 调 DeepSeek 一次 → 缓存 archetype_map.yaml → 注入 prompt context）
- **不需要常驻 AI 角色**
- **Critic 完全不参与**（保留 §4.5 硬约束）

**结论**：Q1 + Q3 是**解耦化关系** —— Q1 的 Python 化让 Q3 的 L2 方案变得**更安全**（Critic → Inducer 反馈环被天然切断），同时仍保留可选性。

### 4.4 三问的最优组合

| 选项 | Q1 | Q2 | Q3 | 评估 |
|---|---|---|---|---|
| **保守组合（推荐）** | C（Python CLI）| Replay 必做 + Re-induction 推迟 | L1（静态 prompt）| 工程量最小，数学严谨度最高，与 spec 偏离最小 |
| **进阶组合** | C | Replay + Re-induction 都做 | L2（archetype hint）| 信息利用率 + 库覆盖更优，但需 Phase 4+ 投入工程量 |
| **激进组合（不推荐）** | A 或 B | Replay + Re-induction + Re-induction loop | L3（Critic → prompt）| 复利风险大，违反 §4.3 / §4.5，不建议 |

**推荐最优组合**：保守组合落地为 v1（与 spec Phase 0-3 工程量基本一致），进阶组合作为 Phase 4+ 增强目标。

---

## §5 对现有 spec 的 delta 清单

> **本节仅列变动建议，不写新版正文。spec 是否修改由用户决策。**

### 5.1 必改（Q1 推荐方案 C 落地的最小修订）

| Δ ID | 章节 | 修订要点 |
|---|---|---|
| **D1** | §1.1 表头 | "Orchestrator: Claude Opus 长 session" → "Orchestrator: Python CLI 调度器（feature-mine 命令套件）"；"上下文寿命：整个 skill 运行期" → "无 session 概念" |
| **D2** | §2.2 Hybrid C 节奏 | "Cold-start batch 触发 = 用户首次启动 skill 且样本充足" → "用户首次 `feature-mine ingest` 命令"；"Triggered batch 触发 = 见 §2.3 触发清单" → "用户显式命令或被动提醒后由用户确认" |
| **D3** | §2.3 触发清单 | 删除"频次估计"列；T_init / T_orphan / T_period / T_critic_health 全部改为"被动提醒触发"语义；新增表头列"触发动作"，把所有原"启动 X"改为"打印警告，建议用户运行 X" |
| **D4** | §4.6 Orchestrator 不持有状态 | 标题保持，正文改为"CLI 调度层不持有任何 features 内容（与原设计一致），实现降级为 Python，无 session 概念" |
| **D5** | §5.4 Phase 路线图 | Phase 2 中"Orchestrator skill（Hybrid C 节奏 + 触发监控）3 天"工程量降到 1.5 天 |

### 5.2 可选（Q2 / Q3 推荐方案的可选实现）

| Δ ID | 章节 | 修订要点 | 触发条件 |
|---|---|---|---|
| **D6** | §3.1 features yaml 字段 | ObservationLog 新增 `epoch_tag: str` 字段；新增 `superseded_by: str | null` 字段 | 实施 Replay 机制时 |
| **D7** | §4.7 (α, β) 修改协议 | 新增"Replay 队列协议"小节：Critic 提议 approve 后**入队**而非立即执行；CLI 在 ingest 前检查队列阻塞 | 实施 Replay 机制时 |
| **D8** | §1.1 角色表 | 新增第 5 角色"CLI Adapter"（可选 Opus 薄壳，做 NL→CLI 翻译）；定位为"用户体验层"而非"调度层" | 用户希望对话式操作时 |
| **D9** | §3.1 features yaml 字段 | ObservationLog 新增 `inducer_context: {prompt_version_id: str, archetype_hint_hash: str | null}` 字段 | 实施 L2 archetype hint 时 |
| **D10** | §4.3 Inducer 输入契约 | 新增可选字段 `context_hint: archetype_map | null`；保留"不得查重 / 不得知道老 features"硬约束（archetype hint 是抽象层，不违反） | 实施 L2 archetype hint 时 |
| **D11** | §5.4 Phase 路线图 | Phase 4+ 新增 "L2 archetype hint + Re-induction" 工作项 | 实施进阶组合时 |
| **D12** | §1.1 角色表 + §4.4 Librarian 接口 | Librarian 新增 `update(event)` 内部检查：同 (sample, feature) 但 epoch_tag 不同 → 走 rollback/apply 模式 | 实施 Replay 机制时 |

### 5.3 不建议改

| Δ ID | 章节 | 用户可能想改但不建议 | 理由 |
|---|---|---|---|
| **N1** | §4.3 强制约束 | "不得查重 / 不得知道老 features" | 这是 reward hacking 防火墙，不能松 |
| **N2** | §4.5 强制约束 | "Critic 不能直接写 features 库或动 (α, β)" | 同上，且涉及职责不可越界硬约束 |
| **N3** | §3 Beta-Binomial 整体 | i.i.d. 假设依赖此约束 | 数学根基，多 epoch 必须靠 epoch_tag + rollback 保护，不能直接累加 |
| **N4** | §0.5 ρ = 1.0 默认 | 自参照框架定义域，不需要打折 | 已在 spec 中明确否决 |

### 5.4 修订优先级

| 优先级 | Δ 集合 | 理由 |
|---|---|---|
| **P0（v1 必做）** | D1, D2, D3, D4, D5 | Q1 是用户原文最强诉求，且工程改动最小 |
| **P1（v1.5 可做）** | D6, D7, D12 | Replay 是 Critic 修订的数学一致性必须 |
| **P2（v2/Phase 4+ 可做）** | D9, D10, D11 | L2 archetype hint 作为可选增强 |
| **P3（按需）** | D8 | 仅当用户希望对话式操作时 |

---

## §6 未解问题（留待用户决策）

1. **Q1 落地时机**：D1-D5 是否在当前 spec v1 就改，还是在 Phase 0 实施前现场决定？
2. **archetype hint 的 LLM 选型**：DeepSeek 是否合适？是否考虑用本地 sentence-transformer + 规则模板替代以彻底零 LLM 依赖？
3. **Replay 队列的并发模型**：用户在 Critic 提议 pending 期间又跑了 ingest，是否允许？还是必须先消费 pending replays 才能 ingest？（推荐"必须先消费"，但用户可能希望"宽松模式"）
4. **Re-induction 的成本守护**：是否需要 CLI 在用户跑 `reinduce` 时显示预估 Opus token 消耗 + 确认提示？
5. **被动提醒的阈值**：orphan 阈值用 20、health check 阈值用 30 天，是否合理？还是给 user config 自定义？
6. **CLI Adapter 是否实现**：D8 的 `feature-mine ask` NL→CLI 翻译薄壳，是否在 v1 就做？还是仅在用户反馈"CLI 太硬核"时再加？
7. **Re-induction 与 Re-verification 的语义边界**：当用户 `feature-mine reinduce --samples S03` 时，是只跑 Inducer 还是同时对该样本对所有老 feature 做 Path V？需要明确 CLI 语义
8. **Snapshot 格式**：`feature-mine reset --snapshot <path>` 的归档格式（tar.gz / git branch / 整个 feature_library/ copy？），需要明确以便用户做版本管理

---

**文档结束。** 三问答案的简化总结：

| 问题 | 推荐 | 一句话理由 |
|---|---|---|
| **Q1 Orchestrator 是否需要 AI** | **不需要**，Python CLI 即可 | 所有调度决策都是确定性规则，AI 价值为零或负 |
| **Q2 是否引入 multi-epoch** | **部分引入**：Replay 必做，Re-induction 可选 | DL epoch 类比不能直接套用（无可学习参数），但用户直觉触及"老样本信息利用率"真问题，用 epoch_tag + rollback 模式安全实现 |
| **Q3 Critic 是否动态更新 prompt** | **不要 L3**（Critic 直接改 prompt），可选 L2（Python 自动 archetype hint，Critic 不参与）| 用户的"信息泄露 / 作弊风险"直觉准确，spec §4.3 / §4.5 是必须保留的防火墙 |
