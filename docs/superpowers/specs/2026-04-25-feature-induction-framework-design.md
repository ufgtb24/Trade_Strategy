# AI 特征归纳框架 — 设计 Spec

> **日期**：2026-04-25
> **作者**：用户 + Claude（superpowers brainstorming 流程产出）
> **来源**：基于 13 项澄清决策 + agent team `rule-stats-model` 研究产出
> **关联文档**：
> - `docs/research/feature_mining_v2_unified_decision.md`（数学骨架来源）
> - `docs/research/feature_mining_unified_schema.md`（schema 细节来源）
> - `docs/research/feature_mining_stats_models.md`（候选模型对比）
> - `docs/research/feature_mining_base_rate.md`（p0 设定研究）
> - `docs/research/feature_mining_philosophy_decision.md`（三层架构 + 三条硬防御共识）
> - `docs/explain/ai_feature_mining_plain.md`（早期通俗版方案）

---

## TL;DR

1. **目标定位**：构建一个模拟研究团队工作流的 AI 框架，从用户挑选的 K 线突破样本中归纳"普遍存在的形态规律"。**与 mining 完全解耦** —— 本框架只产出"哪些规律普遍存在"，不关心"哪些规律有利于上涨"。

2. **核心机制**：三 AI 角色（Inducer / Librarian / Critic）+ **CLI Scheduler**（Python 调度器，无 LLM，用户驱动）+ 三层成本阶梯（Opus / DeepSeek / fastembed）+ Beta-Binomial 共轭后验作为唯一统计量 + multi-epoch **四机制**（Replay / Re-induction / Re-verification / Shuffled Re-induction）+ **Merge Semantics 三策略**（full / supersede-only / reject-merge）。

3. **关键统一**：消除 rule/hypothesis 二分、消除 batch/incremental 二分、消除 obs/episodes/counter 多字段。每条 feature 仅维护 `(α, β, ts)` + ObservationLog（含 `epoch_tag` + `superseded_by` 防双重计数）+ feature 级 `provenance` 字段（防 Shuffled 误升级）；P5 派生状态带；多路径塌缩 1 update 公式。

---

## §0 设计目标与定义域

### 0.1 痛点

当前选股流程中"人工总结 K 线形态"是瓶颈。live 系统匹配出的突破多是"高位冲顶"形态，与用户期望的"底部盘整 → 温和突破"不符。问题根源是：**用户能凭直觉识别"好形态 vs 差形态"，但难以语言化、更难翻译成因子代码**。

### 0.2 目标

把"形态总结"工作交给 AI（特指 Claude Code，非深度学习），让 AI：
- 看用户挑选的样本 → 归纳普遍存在的规律
- 累积证据 / 评估强度 / 自动退化弱信号
- 产出结构化的 `observed_feature` 库（机读 yaml）+ 人读自然语言摘要

### 0.3 与 mining 的关系（解耦）

| 本框架 | mining 流水线 |
|---|---|
| 任务：从用户样本归纳规律 | 任务：验证规律是否有利于上涨 |
| 输出：observed_feature 库 | 输出：阈值优化后的因子注册 |
| 不关心 label（用户挑选即 label）| 关心 label（OOS 验证）|

本框架 → `add-new-factor` skill → mining → 部署到 live。本框架是 mining 的**上游候选生成器**，不是 mining 的一部分。

### 0.4 关键设计哲学（5 条）

1. **规律不是铁律**——是"待持续验证的待定结论"，必须支持升级、降级、遗忘、争议状态
2. **用户挑选样本即监督信号**——"我认为这些走势好"本身是隐式 label，**无需额外正负样本**
3. **跨样本对比是规律涌现的本质**——这部分由 Opus 多模态承担，**不可被统计学替代**
4. **累积/评估/退化机械化**——靠 Beta-Binomial 数学严谨累加，避免 AI 自由心证导致 drift
5. **多 agent 上下文隔离**——每个角色独立 short session，状态住在文件系统

### 0.5 用户挑选 = 框架定义域（重要原则）

本框架的目标域**就是用户挑选的样本集合**，不是市场全集。所以：
- 用户挑选的非随机性**不是缺陷，而是定义域**
- 不需要"非随机抽样修正"（ρ 默认 1.0）
- 不需要 base rate p0（首选自参照判据）
- 不需要 control corpus / 反例池

类比：研究福尔摩斯小说情节的学者不需要修正"我没看狄更斯"——研究对象就是福尔摩斯小说本身。

---

## §1 顶层架构与设计哲学

### 1.1 三 AI 角色 + CLI Scheduler（"研究团队"比喻）

| 角色 | 比喻 | 职责 | AI 类型 | 上下文寿命 |
|---|---|---|---|---|
| **CLI Scheduler** (`feature-mine`) | 命令行工作台 | 接收用户命令 / chunked batch / 触发清单监控（被动提醒）/ 任务排队 / 状态汇报 | **纯 Python，无 LLM** | 单条命令生命周期 |
| **Inducer** | 记者 | 多图对比找共性 / 单图观察 → 输出 `(text, K, N, supporting_ids)` | Claude Opus 短 subagent | 单次任务 |
| **Librarian** | 编辑助理 | 机械累积 `(α, β)` / 派生 P5 / 维护 features 库 / 执行 merge-policy | **Python 脚本**（非 AI）| 无 session 概念 |
| **Critic** | 主编 | Disputed 裁决 / 拆分 / 合并 / 重写 / 抽象 | Claude Opus 短 subagent | 单次任务 |

**为什么把原 Orchestrator 降级为 Python CLI**：原 Orchestrator 的所有调度决策（mode 选择 / 触发监控 / 队列管理 / 状态汇报）都是确定性规则，AI 价值为零或负（增加不确定性、token 成本、降低可调试性）。用户场景是 ingest 驱动的，所有时机由用户命令决定，AI 编排无用武之地。详见 §8 备选 7 否决理由。

**可选 NL Adapter（Phase 4+）**：若用户希望对话式操作，可在 CLI 之上加一层 `feature-mine ask "<自然语言>"` 薄壳（一次性 Opus 调用 NL→CLI 翻译 + 用户确认 + 执行）。这是 UX 层，非调度层。本期不实现。

### 1.2 职责不可越界（硬约束）

| 工作 | 谁做 |
|---|---|
| 修改 (α, β) | **只能是 Librarian**（机械累加 / 重放）|
| 修改 text / embedding | **只能是 Librarian**（执行 Critic 建议时）|
| 决定阈值带（candidate / supported / consolidated / strong）| **派生**，无人执行 |
| 提出 split / merge / rewrite / disputed 裁决建议 | **只能是 Critic** |
| 发现新规律 / 多图对比 | **只能是 Inducer** |
| 全库 health check | **只能是 Critic** |
| 决定何时启动 batch / Replay / Reshuffle / 何时拉起 Critic | **只能是 CLI Scheduler**（基于用户命令 + 内置确定性规则）|
| 选择 merge-policy（full / supersede-only / reject-merge）| **CLI Scheduler 按命令默认 + 用户 `--merge-policy` 覆盖** |

**核心原则**：(α, β) 是缓存累积量，**ObservationLog 才是真相源**。任何修改都通过"动 ObservationLog → recompute (α, β)"完成，**绝对不允许人工"调整" (α, β)**。

### 1.3 状态持久化原则

所有状态住 `feature_library/` 文件系统：
- CLI Scheduler 是无状态进程（每条命令读文件 → 执行 → 写文件 → 退出）
- Inducer / Critic subagent 只返回结构化摘要，不在主进程残留长输出
- Librarian Python 模块是纯函数式接口（无类内可变状态，所有状态走文件系统）
- 任意时间打断 / 重启不丢任何状态

---

## §2 数据流 + 运行模式 + 触发清单 + Merge / Multi-epoch 机制

### 2.1 完整数据流

```
┌─────────────────────────────────────────────────────────────┐
│ 用户在 dev UI 按 P 键挑选样本（写入 samples/）                  │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ 用户运行 CLI 命令，例如：                                      │
│   feature-mine ingest <samples...> --batch-size 10            │
│   feature-mine reinduce --samples S03,S07                     │
│   feature-mine reshuffle --rounds 5 --strategy anti-correlated│
│   feature-mine apply-replays                                  │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ [Opus 多模态预处理] (一次性，每张新样本只跑一次)               │
│   图像 + 元数据 → nl_description.md                          │
│   存入 samples/<id>/                                         │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ [CLI Scheduler 解析命令]（确定性 Python 规则）                 │
│   - ingest --mode batch  → chunked Inducer batch              │
│   - ingest --mode incremental → 逐张走 Path V verify           │
│   - reinduce → 用户子集进 Inducer，merge-policy 默认 full      │
│   - reshuffle → anti-correlated 重组 batch，merge-policy=     │
│       supersede-only（默认），provenance lock 启用             │
│   - apply-replays → 消化 pending_replays.yaml                  │
│   命令结束后打印被动提醒（孤儿数 / health 距今天数）             │
└────────┬───────────────────┬────────────────────────────────┘
         │                   │
   incremental             batch / reinduce / reshuffle
         │                   │
         ▼                   ▼
┌──────────────┐  ┌──────────────────────────────────────────┐
│ Inducer N=1  │  │ Inducer N=8~12（多图跨样本对比，盲跑）    │
│ 产单图特征    │  │ 产候选共性特征 (text, K, N, supporting)  │
└──────┬───────┘  └────────────┬─────────────────────────────┘
       │                       │
       └────────┬──────────────┘
                ▼
┌─────────────────────────────────────────────────────────────┐
│ [Librarian 接管]（双路径 + Merge Semantics §2.5）             │
│  ┌──────────────────────┐  ┌──────────────────────────────┐ │
│  │ Path U (Unprompted)  │  │ Path V (Prompted Verif.)     │ │
│  │ candidate × old:     │  │ 单样本 × 单 feature:         │ │
│  │ L0 cosine + L1 精判  │  │ → L1 yes/no/ambiguous        │ │
│  │ + merge-policy 决策  │  │ → 转译 (K, N, C) 事件        │ │
│  │ → 转译 (K, N, C=0)   │  │ → epoch_tag + supersede 检查 │ │
│  │ → 统一 update        │  │ → 统一 update                │ │
│  └──────────────────────┘  └──────────────────────────────┘ │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ [P5 派生状态带] (Beta_lower_5pct(α, β))                       │
│   状态切换 disputed → 入 critic_review_queue（不自动跑）       │
│   provenance startswith "shuffle-" → 锁在 candidate（§2.6）   │
│   状态稳定 + 用户 promote → 走 add-new-factor (出框架)         │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 用户驱动的运行模式（四种）

所有模式都由用户 CLI 命令显式触发，**没有"自动节奏"**。CLI 在 ingest 末尾打印被动提醒（孤儿累积 / health 距今天数等），是否消费由用户决定。

| 模式 | CLI 命令 | 输入规模 | 默认 merge-policy | 产出 |
|---|---|---|---|---|
| **Cold-start / Batch** | `feature-mine ingest <samples...> --batch-size N --mode batch` | 用户输入数 → 内部 chunked 为 ⌈N/B⌉ batch | `full` | 初始 / 新 features |
| **Incremental** | `feature-mine ingest <samples...> --mode incremental` 或一张样本默认 | 1 张 / 次 | `full` | verification 强化 + 单图特征观察 + 孤儿入队 |
| **Re-induction** | `feature-mine reinduce --samples S03,S07,...` | 用户指定子集 | `full` (用户可 `--merge-policy supersede-only`) | 重挖老样本的潜在新规律；可能强化或削弱老 feature |
| **Shuffled Re-induction** | `feature-mine reshuffle --rounds 5 --strategy anti-correlated` | 整库样本 × N 轮 | `supersede-only`（强制不削弱老 feature）| 跨样本组合空间扩展 + provenance 锁防误升级 |

**`--mode auto` 解析规则**（CLI 内置）：
- 库为空 + 用户输入 ≥ 8 张 → batch
- 库为空 + 用户输入 < 8 张 → 报错"建议至少凑齐 8 张样本再 cold-start"
- 库非空 + 用户输入 1 张 → incremental
- 库非空 + 用户输入 ≥ 8 张 → batch（继续探索）
- 库非空 + 用户输入 1 < N < 8 → batch with reduced size（提示用户 "建议 ≥ 8 张获得更稳健 co-induction"）

**为什么 reshuffle 默认 `supersede-only`**：详见 §2.5；核心理由是 reshuffle 是探索模式，用户预期"挖新规律"，不应附带削弱老 feature。`full` 在 reshuffle 中会让老 feature 被 batch 邻居偶然不支持的样本拉低 P5（"邻居敏感性削弱"），违反用户直觉。

### 2.3 触发清单（被动提醒模式）

CLI Scheduler 不主动调度任何任务。所有触发条件只在 ingest / status 命令末尾**打印警告**，由用户决定是否跑对应命令。**没有任何自动执行**。

| 触发 ID | 条件 | CLI 行为 | 用户消费命令 |
|---|---|---|---|
| **T_init** | 库为空（无 features） + 用户首次 `ingest` ≥ 8 张 | CLI 自动选 batch 模式 | 自然由 `feature-mine ingest` 完成 |
| **T_orphan** | `pending/orphan_samples.yaml` 累计 ≥ 阈值（默认 20）| `[WARN] orphan_samples 累计 N 条（阈值 20），建议运行 \`feature-mine review-orphans\`` | `feature-mine review-orphans` |
| **T_period** | 自上次 batch / reshuffle 起累积新样本 ≥ 阈值（默认 30 天 + 20 张）| `[WARN] 自上次集中复盘已 N 天 / 累积 N 张样本，建议运行 \`feature-mine reshuffle\` 或 \`reinduce\`` | `feature-mine reshuffle` 或 `reinduce` |
| **T_user_review** | 用户显式请求 | n/a（用户主动）| `feature-mine review-critic --kind user_request` |
| **T_critic_disputed** | feature 状态变 disputed | 入 `critic_review_queue.yaml`，下次 ingest 末尾 `[WARN] N 条 disputed 待 review` | `feature-mine review-critic --kind disputed` |
| **T_critic_health** | 自上次 health check 起 30 天 | `[WARN] 距上次 health check N 天，建议运行 \`feature-mine review-critic --kind health\`` | `feature-mine review-critic --kind health` |
| **T_pending_replays** | `pending_replays.yaml` 非空（Critic 提议待消费）| `[ERROR] 有 N 条 Replay pending，**阻塞**新的 ingest，请先运行 \`feature-mine apply-replays\`` | `feature-mine apply-replays` |

**用户可 `--quiet` 关闭警告**，那是用户的明确选择。CLI 永远不"代为决策"。

**孤儿样本定义**：incremental 处理后，对所有老 features 都判 no/ambiguous，且单图特征观察（K=1, N=1）入库时未与任何老 features 匹配。

**Critic 永远不自动执行**：T_critic_* 只是把任务**入队列**，由用户主动 `review-critic` 拉起。这是成本控制硬约束。

**Replay 阻塞规则**：T_pending_replays 是唯一 ERROR 级别提醒（其他都是 WARN）。Critic 改了 feature 后必须 replay 老样本才能保持数学一致，强迫用户消费才能继续 ingest。

### 2.4 Path U vs Path V 在 (K, N, C) 上的语义

**Path U（Unprompted）—— 来自 Inducer 的归纳事件**
- 输入：Inducer 产出 `(text, supporting_sample_ids, K, N)`
- 转译前 **Librarian L0 cosine** 比对老 features → 应用 §2.5 Merge Semantics 决定该 candidate 是否合并入老 feature、合并几分
- 合并后等价的 `(K, N, C=0)` 事件按 §2.5 计算（可能少于 Inducer 原报告的 N-K，取决于 merge-policy）
- 每条事件携带 `epoch_tag` 字段（首次为 null，否则按 §2.6 命名）
- update：`α += K, β += (N-K)`，但 β 累加之前要走 §2.6 的 `(sample_id, feature_id, epoch_tag)` 去重 + supersede 检查

**Path V（Prompted verification）—— 单样本对单 feature 的 yes/no 判定**
- 输入：1 张样本 nl_description × 1 条老 feature 的 text → L1 DeepSeek
- 不经 Merge Semantics（已经显式指定了 (sample, feature)，无 merge 选择）
- 转译（取决于 L1 输出）：
  - L1 = `yes` → 等价于 `(K=1, N=1, C=0)` 事件
  - L1 = `no` → 等价于 `(K=0, N=1, C=1)` 事件
  - L1 = `ambiguous` → **不发事件**（不动 α, β）
- 走 supersede 检查（同 §2.6）
- update：仍然是统一公式 `α += K, β += (N-K-C) + γ·C`

**两条路径吃同一 update 公式，但 Path U 多了 Merge Semantics 前置门和 epoch_tag 去重，Path V 只有 epoch_tag 去重。**

### 2.5 Merge Semantics（Librarian L0 merge 三策略）

Path U 的 candidate 进库前，Librarian 按 cosine 阈值（默认 0.85）查找 L0 命中的老 feature。merge-policy 决定如何处理命中：

| Policy | L0 命中行为 | L0 未命中行为 | 默认场景 |
|---|---|---|---|
| **`full`** | 把 candidate 的 (K, N) 完整并入老 feature；候选 supporting_sample_ids 中已有 (sample, feature) log → 走 supersede；未在 supporting 中的 batch 样本 → 创建新 β 事件 | 新建 feature | Cold-start / Incremental ingest / Critic split-replay |
| **`supersede-only`** | 只对 candidate.supporting_sample_ids ∩ feature.observed_samples 走 supersede；**对 batch 中其他样本不创建任何 (sample, feature) 事件**（保留老 feature 不被削弱）| 新建 feature | Reshuffle（强制）；Reinduce 用户可显式选 |
| **`reject-merge`** | 整条 candidate 丢弃（不更新老的、不新建）| 新建 feature | 极少使用；当用户明确"reinduce 必须只产真新 feature"时 |

**核心区别 — full vs supersede-only**：
- `full` 是统计派立场：reshuffle batch 里的"非支持样本"是合法 i.i.d. 反对票，老 feature 削弱合理化
- `supersede-only` 是意图派立场：reshuffle / reinduction 是探索模式，用户预期挖新规律，不应附带削弱老 feature

**示例**：F-001 `observed_samples=[S03, S05, S07]`；reinduction batch `[S03, S09, S15]`；Inducer 报 candidate ≈ F-001，supporting=[S03], K=1, N=3。

| Policy | F-001 (α, β) 净变化 | 新事件 |
|---|---|---|
| `full` | α 不变（S03 supersede 替换，结论相同）；β += 2（S09, S15 反对票）| (S03, F-001, ai_induction, reinduction-X) supersede log1; (S09, F-001, ..) β=1; (S15, F-001, ..) β=1 |
| `supersede-only` | 完全不变 | 仅 (S03, F-001, ai_induction, reinduction-X) supersede log1 |
| `reject-merge` | 完全不变 | 0 事件，candidate 丢弃 |

**实现位置**：Librarian.upsert_candidate(candidate, merge_policy) — 接口契约见 §4.4。

**默认值表**：

| 调用上下文 | 默认 merge-policy | 用户可覆盖 |
|---|---|---|
| `feature-mine ingest`（cold-start / incremental）| `full` | `--merge-policy supersede-only`（少见）|
| `feature-mine reinduce` | `full`（统计严谨）| `--merge-policy supersede-only`（保护老 feature）|
| `feature-mine reshuffle` | `supersede-only`（强制默认，不允许 `full`）| 仅可改为 `reject-merge`，不允许 `full` |
| Critic split / merge → apply-replays | `full`（结构性变化必须吸收所有事件）| 不可覆盖 |

**为什么 reshuffle 禁止 `full`**：reshuffle 在固定样本集上反复重组 batch，若用 `full` 会让 batch 中"碰巧不支持某老 feature"的样本反复贡献 β，产生**虚假的反对证据复利**。这是 Beta-Binomial i.i.d. 假设在 reshuffle 场景下的隐性破坏。强制 `supersede-only` 是必要保护。

### 2.6 Multi-epoch 四机制 + epoch_tag + provenance

**问题背景**：单纯 1-epoch 训练（每张样本只评估一次）在以下场景信息利用不充分：(a) 新 feature 落库后老样本未被回扫；(b) Critic 拆/合后老样本归属未重算；(c) 原始 ingest 的 batch 组合空间覆盖率极低（N=100, B=10 时 91% 样本对从未同 batch）。但盲目 multi-epoch 会破坏 Beta-Binomial 的 i.i.d. 假设（同一观察被反复加 K 等于伪造证据）。

**解决方案**：四机制 + ObservationLog `epoch_tag` 字段 + feature 级 `provenance` 字段联防。

| 机制 | 含义 | 触发 | 默认 merge-policy |
|---|---|---|---|
| **Replay** | Critic split / merge / rewrite 后，对老样本对新 feature 重新发起 verify（必须，否则新 feature 没证据）| Critic 提议 approve → 入 `pending_replays.yaml` → 用户 `apply-replays` 消费 | `full` |
| **Re-induction** | 用户主动让老样本子集重新进 Inducer 探索新规律 | `feature-mine reinduce --samples ...` | `full`（默认）/ `supersede-only`（用户选）|
| **Re-verification** | 单样本 × 单 feature 的 L1 重判定（已隐含在 incremental Path V 中）| 自动（incremental 路径）/ 用户 `feature-mine reverify --sample S03 --feature F-001` | n/a（Path V 不经 merge）|
| **Shuffled Re-induction** | 老样本打乱重组 batch（anti-correlated 优先），提高组合可见性 | `feature-mine reshuffle --rounds N --strategy ...` | `supersede-only`（强制）+ provenance 锁 |

**ObservationLog 新增 `epoch_tag` 字段**（防双重计数）：

| 值 | 来源 |
|---|---|
| `null` | 首次评估（Cold-start / Incremental 默认）|
| `replay-after-split-{F-id}-{ts}` | Critic split 后的 Replay |
| `replay-after-merge-{F-id}-{ts}` | Critic merge 后的 Replay |
| `replay-for-new-feature-{F-id}` | 新 feature 落库后对老样本的补 verify |
| `reinduction-{batch_id}` | 用户主动 Re-induction |
| `shuffle-{round_id}-{batch_idx}` | Shuffled Re-induction |

**去重 + supersede 规则**：
- 同 (sample_id, feature_id, source, epoch_tag) 完全重复 → Librarian 拒绝写入
- 同 (sample_id, feature_id) 但 epoch_tag 不同 → 老条目标记 `superseded_by=<新条目 ID>`，仅新条目计入 (α, β) recompute
- 不同 sample 或不同 feature → 正常累加
- 唯一例外：Critic split 后两条新 feature 是不同 feature_id，同一样本对 F-001a 和 F-001b 各贡献一条事件**不算**双重计数

**Feature 级 `provenance` 字段**（防 Shuffled 误升级）：
- 记录 feature **首次诞生时的 epoch_tag** 或 `source`
- 若 `provenance` startswith `shuffle-`，则该 feature 被 **provenance 锁**：即使 P5 ≥ 0.20，状态带也强制锁定为 `candidate`，直到出现至少 1 条 `source != shuffled` 的事件后才解锁
- 防止 Shuffled 在固定样本集上过度发现导致虚假升级

**机制选择树**：

```
是 Critic split/merge 后 → 必须 Replay (full)
是新 feature 刚落库 → 自动 Replay-for-new-feature (full)
用户想"挖新规律" + 指定子集 → Re-induction (默认 full，可选 supersede-only)
用户想"扩展组合空间覆盖" → Shuffled Re-induction (强制 supersede-only + provenance 锁)
单样本单 feature 复评 → Re-verification (Path V，不经 merge)
```

**禁止事项**：
- 多视角增强（同样本生成多份 nl_description 各算一次观察）→ 破坏 i.i.d.，spec 明确禁止
- Re-induction / Reshuffle 时 archetype hint（参 §8 备选 8）共用 → epoch>0 时强制禁用 archetype hint，防止"动态 prompt → 复利偏差"

---

## §3 Beta-Binomial 数学骨架

### 3.1 每条 feature 的状态变量

```yaml
observed_feature:
  id: str
  text: str
  embedding: list[float]              # for L0
  alpha: float                        # ≥ α₀ = 0.5
  beta: float                         # ≥ β₀ = 0.5
  last_update_ts: datetime
  provenance: str | null              # 首次诞生时的 source 或 epoch_tag；若 startswith "shuffle-" 则 provenance 锁启用
  observed_samples: set[str]          # 该 feature 已经在 ObservationLog 出现过的所有 sample_id（用于 merge-policy 判定）
  observations: list[ObservationLog]  # 审计日志（含 epoch_tag + superseded_by），不直接参与决策
  # 派生（不存）：
  #   S = beta_ppf(0.05, α, β)        # P5
  #   status_band = derive(S, counter_ratio, provenance)
  #     若 provenance startswith "shuffle-" 且无 source != shuffle 的事件 → 强制 candidate
```

**先验**：`α₀ = β₀ = 0.5`（Jeffreys prior）—— 允许极端比例（0% 或 100%）出现，比均匀先验 (1, 1) 更适合"看 1-2 张样本就出强信号"的小样本场景。

### 3.2 统一 update 公式

接收一个事件 `e = (K, N, C, source, ts)`：

```python
# Step 1 — Lazy time decay since last update
days = (e.ts - feature.last_update_ts).days
decay = LAMBDA ** max(0, days)
feature.alpha = max(ALPHA_PRIOR, feature.alpha * decay)
feature.beta  = max(BETA_PRIOR,  feature.beta  * decay)

# Step 2 — Inject evidence (counter is gamma-weighted)
feature.alpha += e.K
feature.beta  += (e.N - e.K - e.C) + GAMMA * e.C
feature.last_update_ts = e.ts
```

**lazy decay**：不用每天跑全库 cron job，访问时按 `(now - last_update_ts).days` 一次性补衰减。计算等价。

### 3.3 两个独立调节维度

| 维度 | 参数 | 默认 | 含义 |
|---|---|---|---|
| **时间衰减** | λ (LAMBDA) | 0.995（半衰期 ~138d）| feature 不被持续验证就慢慢淡化 |
| **counter 权重** | γ (GAMMA) | 3 | "L1 一次明确 no" ≈ 3 张沉默样本的杀伤力 |

**ρ（抽样修正系数）**：默认 = 1.0（删掉），仅作为 source-级别的可选打折开关，主线流程不启用。理由见 §0.5。

### 3.4 派生信号 + 状态带

```python
S = scipy.stats.beta.ppf(0.05, feature.alpha, feature.beta)  # P5 ∈ [0, 1]
counter_ratio = total_C_weighted / feature.beta              # 反对证据占比
```

| P5 区间 | 状态带 | 含义（人话）|
|---|---|---|
| **< 0.05** | `forgotten` | 几乎肯定不是规律，可隐藏 |
| `[0.05, 0.20)` | `candidate` | 萌芽 / 证据不足 |
| `[0.20, 0.40)` | `supported` | 弱信号 / 待累积（≈ 旧 hypothesis）|
| `[0.40, 0.60)` | `consolidated` | 成熟规律（≈ 旧 rule）|
| `[0.60, 1.00]` | `strong` | 高置信规律 |
| any + counter_ratio > 0.3 | `disputed` | 叠加标记，触发 Critic 队列 |

**关键设计**：状态带是**派生量**，不存储。调阈值零迁移成本。

### 3.5 P5 的直觉 — "保守底气"

- 1/1（一次出场一次成功）：出场率 100%，**P5 ≈ 0.32**（样本太少，不敢说）
- 10/10：出场率 100%，**P5 ≈ 0.74**（多了，敢说真实 ≥ 74%）
- 100/100：出场率 100%，**P5 ≈ 0.97**（极有底气）
- 2/10：出场率 20%，**P5 ≈ 0.08**（很少出场，底气低）

这直接解决了用户最初指出的"2/10 比 1/1 强（颠倒）"问题：P5(1/1) > P5(2/10)。

### 3.6 解决用户提出的两大痛点

| 痛点 | Beta P5 的回答 |
|---|---|
| **N-K 沉默样本无惩罚** | N-K 直接累加进 β → 后验下界自然下降 |
| **2/10 比 1/1 强（颠倒）** | P5(1/1)=0.32 > P5(2/10)=0.08 ✅ |
| **Hypothesis 纯增量随机信号也能升级** | 真随机信号每次只有 1/N 出场率，β 累积速度远快于 α，P5 永远爬不上来 ✅ |

### 3.7 回退开关清单

| 开关 | 默认 | 启用情形 |
|---|---|---|
| `min_episodes_for_consolidation` | 1 | 调到 2 → 强制至少 2 次独立 episode 才能 consolidated（恢复旧"健壮性"约束）|
| `theta_consolidated` | 0.40 | 调高 → 更难升 consolidated |
| `theta_strong` | 0.60 | 调高 → 更难升 strong |
| `theta_forget` | 0.05 | 调低 → 稀有特征活更久 |
| `gamma` | 3 | 改为 `dict[source, float]` → 不同来源 counter 不同权 |
| `lambda` | 0.995 | 调小（如 0.99）→ 更快遗忘老形态（适合市场结构变化期）|
| `rho` | 1.0 (off) | 启用 `dict[source, float]` → 仅在确认某 source 不可信时打折 |
| `l0_cosine_threshold` | 0.85 | 调到 0.75（如 reshuffle 专用）→ 更严的 merge 判定，降低语义近亲风险 |
| `provenance_lock_unlock_min_events` | 1 | 调高（如 3）→ 要求更多 source != shuffle 的事件才能解锁 shuffle-诞生 feature |
| `cooccurrence_threshold` | 0.7 | reshuffle 终止条件，共现矩阵填充率达此值即停 |
| `default_merge_policy_reinduce` | `full` | 改 `supersede-only` → reinduction 也强制不削弱老 feature（与 reshuffle 对齐）|

---

## §4 文件系统 + 角色契约

### 4.1 文件系统骨架

```
feature_library/
├── INDEX.md                              # 自动生成，所有 features 一行摘要
├── features/
│   ├── F-001-tight-rectangle-basing.yaml # 一条 feature 一份
│   └── F-002-volume-contraction.yaml
├── samples/
│   └── BO_AAPL_20230115/
│       ├── meta.yaml                     # ticker / date / 因子原值 / 用户挑选时间
│       ├── chart.png                     # AI 友好渲染图
│       └── nl_description.md             # Opus 一次性预处理产出
├── pending/
│   ├── orphan_samples.yaml               # 被 incremental 处理但全 no/ambiguous 的样本
│   ├── critic_review_queue.yaml          # 待 Critic 审视的项（disputed / split 嫌疑 / 用户请求）
│   └── pending_replays.yaml              # Critic approve 后的 Replay 任务，CLI ingest 前阻塞检查
├── history/
│   └── 2026-04-25_episode_log.jsonl     # 每个 episode（batch / incremental / reinduce / shuffle）的事件流水
├── archived/                             # 已删除 features 的归档（保留 ObservationLog）
│   └── F-007-removed-2026-04-30.yaml
├── critic_proposals/
│   ├── pending/                          # 待 approve 的 Critic 提议
│   ├── approved/                         # 已执行的提议（留痕）
│   └── rejected/                         # 用户拒绝的提议（cooldown 用）
├── cooccurrence.yaml                     # 样本对共现矩阵（reshuffle anti-correlated 策略用）
└── archetypes/                           # Phase 4+ Critic 抽象产出（v1 不启用）
```

**`cooccurrence.yaml` 结构**（reshuffle 必备，不参与 incremental 流程）：

```yaml
last_updated: 2026-04-26T...
matrix:                       # 上三角，键为 "S03|S05" 形式
  S03|S05: 1                  # 出现在同 batch 的次数
  S03|S07: 1
  S05|S07: 2                  # 在两个 batch 同时出现过
total_samples: 100
total_pairs: 4950             # C(100, 2)
covered_pairs: 287            # 共现 ≥ 1 的对数
coverage_ratio: 0.058         # 覆盖率，reshuffle 终止条件之一（默认阈值 0.7）
```

**`pending_replays.yaml` 结构**（Critic 修改后必消费）：

```yaml
items:
  - id: replay-{F-id}-{ts}
    kind: replay-after-split | replay-after-merge | replay-for-new-feature
    target_feature_ids: [F-001a, F-001b]
    sample_ids: [S03, S05, S07, S09]      # 待重新评估的老样本
    epoch_tag: replay-after-split-F-001-{ts}
    merge_policy: full                    # 必为 full（结构性变化）
    created_ts: ...
```

### 4.2 features/<id>.yaml 字段

```yaml
id: F-001
text: "盘整期间量能相比盘整前明显收缩"     # 主描述（自然语言）
embedding: [0.123, -0.456, ...]           # for L0 cosine
alpha: 7.5
beta: 3.5
last_update_ts: 2026-04-25T14:30:00Z
provenance: ai_induction                  # 首次诞生时的 source 或 epoch_tag；若 startswith "shuffle-" 启用 provenance 锁
observed_samples: [S03, S05, S07, ...]    # 该 feature 已经在 ObservationLog 出现过的所有 sample_id 集合（merge-policy 用）
total_K: 7                                # 累计支持样本（按 N 累加）
total_N: 10                               # 累计样本（含沉默 + 反对）
total_C_weighted: 0                       # 累计 counter 加权值
observations:                             # 审计日志，每次 update append
  - id: obs-001                           # 唯一条目 ID（被 superseded_by 引用）
    ts: 2026-04-25T14:30:00Z
    source: ai_induction | user_pick | deepseek_l1 | ...
    epoch_tag: null                       # null = 首次评估；其他参 §2.6
    sample_id: S03                        # 单条目级 sample 引用（防去重失效）
    K: 1                                  # 该 sample 在该事件下贡献的 K
    N: 1                                  # 该 sample 在该事件下贡献的 N
    C: 0
    alpha_after: 7.5
    beta_after: 3.5
    signal_after: 0.42                    # P5 update 后快照
    superseded_by: null | obs-XXX          # 若被新观察覆盖，指向新条目 ID
    notes: "batch_id=B-005"
  # 单 batch 多样本 → 拆为多条 obs 条目（每条对应一个 sample），便于按 sample 做 supersede
research_status: active | saturated | parked   # 用户级状态（人工标注）
factor_overlap_declared: null | str        # Phase 4+ 与 13 因子的对应（可选）
```

**重要变化**：原 spec 一次 batch 只 append 一条聚合 obs 条目（含 supporting_ids 列表）。新版 ObservationLog 按 **(sample, feature)** 粒度展开为多条独立条目，是 supersede 机制可工作的前提（按 sample 粒度才能正确替换覆盖）。

### 4.3 Inducer 输入输出契约（统一，N=1 退化即 incremental）

**输入**：

```yaml
batch_id: str
samples:
  - id: BO_AAPL_20230115
    chart_path: ...
    nl_description: ...
goal: "find common features across these samples (N≥2) or list observed features (N=1)"
```

**输出**：

```yaml
candidate_features:
  - text: "盘整期间量能相比盘整前明显收缩"
    supporting_sample_ids: [S01, S03, S05, ...]
    K: 7
    N: 10
    notes: "..."   # 可选
```

**强制约束**：
- 不得查重（不读 features 库）
- 不得分类（不判 rule/hypothesis）
- 不得知道老 features 存在（避免 co-induction 信号污染）

### 4.4 Librarian Python 接口（非 AI）

```python
class Librarian:
    # ---- 核心 CRUD ----
    def get_or_create(text: str, embedding: list[float]) -> ObservedFeature
    def update(feature_id: str, event: Event) -> ObservedFeature
        # event = (sample_id, K, N, C, source, epoch_tag, ts, notes)
        # 内部会做 (sample_id, feature_id, source, epoch_tag) 去重 + supersede 检查（§2.6）
    def upsert_candidate(candidate: InducerCandidate, merge_policy: str) -> list[ObservedFeature]
        # Path U 入口；按 §2.5 处理 L0 命中：full / supersede-only / reject-merge
        # 返回受影响的 features 列表（原老 feature 可能被 update / 新 feature 可能被创建）
    def recompute(feature_id: str) -> ObservedFeature
        # 从 ObservationLog（含 superseded 标记）重放，重算 (α, β)
        # 跳过 superseded_by 不为 null 的条目

    # ---- L0 / L1 ----
    def lookup_by_cosine(embedding, threshold=0.85) -> list[ObservedFeature]
        # L0 筛选；reshuffle 模式下传入更严阈值 0.75（§3.7）
    def verify_yes_no(sample_nl: str, feature: ObservedFeature) -> Verdict
        # L1 调 DeepSeek，返回 yes/no/ambiguous

    # ---- 状态 / 派生 ----
    def query(filter_band: list[str] = None) -> list[ObservedFeature]
        # 派生 status_band 时考虑 provenance 锁（§2.6）
    def explain(feature_id: str) -> str
        # 回看最近 update 对 (α, β) 的贡献，包含 supersede 历史

    # ---- Replay 配套 ----
    def enqueue_replay(replay_item: ReplayItem) -> None
        # Critic 提议 approve 后入队 pending_replays.yaml
    def apply_replays() -> dict[str, list[ObservedFeature]]
        # 消化 pending_replays.yaml，调用 Inducer 重跑 + recompute；返回受影响 features

    # ---- Reshuffle 配套 ----
    def update_cooccurrence(batch_sample_ids: list[str]) -> None
        # 每 batch 进入 Inducer 前调用，更新 cooccurrence.yaml
    def get_anti_correlated_batch(batch_size: int, candidates: list[str]) -> list[str]
        # 贪心选出共现率最低的 batch_size 个 sample
    def cooccurrence_coverage() -> float
        # 共现矩阵填充率（reshuffle 终止条件之一）

    # ---- 持久化 ----
    def snapshot(path: str) -> None
        # `feature-mine reset --snapshot` / `snapshot` 命令底层
    def export_yaml(path: str) -> None
        # `feature-mine export-yaml` 命令底层，供 add-new-factor 消费
```

**关键约束**：Librarian **不调 Opus**（除非通过 `verify_yes_no` 调 DeepSeek，那也是 L1 不是 L2；Inducer 重跑由 `apply_replays` 委托给 Inducer subagent）。所有 Opus 调用都在 Inducer / Critic / preprocess 里。

### 4.5 Critic 输入输出契约

**输入**（来自 critic_review_queue.yaml 的一项）：

```yaml
review_kind: disputed | split_suspected | merge_review | user_request | health_check
target_feature_ids: [F-001, ...]
context:
  supporting_samples: [...]                # nl_descriptions + charts
  counter_samples: [...]                   # 仅 disputed 时
  rationale: "..."                         # 触发原因
```

**输出**（建议格式，由用户 approve 后由 CLI 入 `pending_replays.yaml` → Librarian 执行）：

```yaml
proposals:
  - kind: split | merge | rewrite | demote | abstract
    target: F-001
    diff:
      old_text: "..."
      new_text: "..."
      # 或 split: 两条新 feature 各自的 text + supporting_sample 划分（可重叠）
      # 或 merge: 合并后的 text + 双重计数检测策略
    rationale: "短语义解释"
```

**强制约束**：Critic **不能**直接写 features 库或动 (α, β)，**也不能改 Inducer prompt**（防 reward hacking，详见 §8 备选 8）。所有 mutation 走 用户 approve → CLI 入 `pending_replays.yaml` → 用户 `apply-replays` → Librarian 执行。

### 4.6 CLI Scheduler 不持有状态

CLI Scheduler 是无状态进程。每条命令的执行步骤：
1. 解析参数（argparse 或 Click）
2. 读相关文件系统状态（INDEX.md / pending/ / history/ / cooccurrence.yaml）
3. 用确定性 Python 规则解析 mode + merge-policy + epoch_tag
4. spawn Inducer / Critic subagent（如需要），把待 verify 的 feature 上下文显式注入 subagent prompt（subagent 不直接读 features 库）
5. 接收 subagent 输出 → 调 Librarian.upsert_candidate / update / apply_replays 等
6. 写文件（features yaml / observation log / pending 队列 / cooccurrence.yaml）
7. 打印 ingest summary + 被动提醒（§2.3）
8. 退出

**主进程 context 保持极小**（仅命令运行期，无长 session）。

### 4.7 (α, β) 修改协议

**核心原则重申**：(α, β) 是缓存累积量，**ObservationLog 才是真相源**。所有修改都通过新增带 `epoch_tag` 的条目 + supersede 老条目 → recompute 来实现，**绝不允许直接动 (α, β)**。

| Critic 动作 | 对 ObservationLog 的影响 | epoch_tag | 对 (α, β) 的影响 | 走 Replay 队列 |
|---|---|---|---|---|
| **Rewrite**（改写文字）| 不变 | n/a | 不变（重算 embedding 即可）| 否 |
| **Split**（拆为两条）| 创建新条目（每张老样本对每条新 feature 一份），老条目对 F-001 仍存在但目标 feature 失活 | `replay-after-split-{F-001}-{ts}` | 从新 log 重放，merge_policy=full | 是 |
| **Merge**（合并两条）| 把 F-005 的 obs 条目复制到 F-005m，与 F-012 的 obs 条目按 (sample_id, source) 去重合并 | `replay-after-merge-{F-005,F-012}-{ts}` | 从去重 log 重放重算（**禁止 α₁+α₂ 直接加和**）| 是 |
| **Demote**（强制降级）| **禁止**——Critic 不能"凭意见"降级 | n/a | 不变 | — |
| **Disputed 裁决 → 删除** | 老 log 归档到 `archived/`，feature 失活 | n/a | 不再使用 | 否 |
| **Disputed 裁决 → 重跑 verify** | 标记某些 ObservationLog 条目为 `superseded_by`，跑新 verify 追加带新 epoch_tag 的条目 | `replay-after-dispute-{F-id}-{ts}` | 跳过 superseded 后重放 | 是 |
| **Abstract**（archetype 卡片）| 不变 | n/a | 不变（archetype 是引用层）| 否 |

**所有"是 Replay 队列"的动作**：Critic approve 后 → Librarian.enqueue_replay() → 写入 `pending_replays.yaml` → 用户下次 `feature-mine ingest` 被阻塞 → 必须先跑 `feature-mine apply-replays` 才能继续。这是数学一致性硬约束（§2.3 T_pending_replays）。

**Split 的具体协议** —— Critic 提议必须明确指定每条新 feature 的支持样本（**可重叠，不强制互斥**）：

```yaml
proposal:
  kind: split
  target: F-001
  reason: "支持样本里有两类不同形态：长期下跌后盘整 vs 横盘震荡"
  new_features:
    - new_id: F-001a
      text: "长期下跌后的紧致盘整突破"
      assigned_samples: [S03, S05, S09, S12]   # 可与 F-001b 重叠
    - new_id: F-001b
      text: "横盘震荡末期的紧致盘整突破"
      assigned_samples: [S05, S07, S08]       # 与 F-001a 在 S05 上重叠
```

**Split 的 ObservationLog 重放需要假设沉默样本归属**（沉默样本无 ID，不知道归哪条新 feature）。两个回退选项：

- **选项 A（推荐）**：split 时让 Inducer 重新跑（看 assigned_samples + 现有 batch 重新归纳一次），用新跑的 (K, N) 取代老 log。准确但贵
- **选项 B**：用近似（按 assigned_samples 比例分 N-K）+ 标注 `approximated: true`。便宜但有偏

spec 不强制选项，留实施期决策。

**Merge 的双重计数处理**：

```yaml
proposal:
  kind: merge
  targets: [F-005, F-012]
  reason: "L1 精判等价，且 supporting_samples 重叠 ≥ 80%"
  merged:
    new_id: F-005m
    text: "盘整期量能持续低于盘整前均量"
```

执行时按 `ts + source + supporting_sample_ids 集合` 判定唯一性，去重 union 两条 log，再 recompute。**不允许 α₁+α₂ 直接加和**（同一样本会被双重计数）。

---

## §5 Trade-off / 回退开关 / Phase 路线图

### 5.1 主方案的收益

| 维度 | 收益 |
|---|---|
| 代码量 | 800-1200 行 → **200-300 行**（6 路径塌缩 1 公式）|
| 字段数 | obs/episodes/counter/prompted_yes-no 5 字段 → **(α, β, ts) 3 字段** |
| 状态机 | rule/hypothesis/candidate/disputed 多状态 → **派生，无状态机** |
| 阈值调节 | 数据 migration → **零迁移成本**（仅改 config）|
| 数学根基 | 启发式 → **共轭后验**（贝叶斯标准）|
| 兼容性 | 与 philosophy_decision 的三条硬防御**完全兼容** |
| 工程量 | ~3.5 周（Phase 0-3 MVP 闭环）|

### 5.2 已识别的代价 + 回退开关

| 代价 | 严重度 | 回退开关 | 启用方式 |
|---|---|---|---|
| episodes ≥ 2 健壮性条件被吸收 | 中 | `min_episodes_for_consolidation` | config 调到 2 |
| 单批 大N 低 K/N（如 2/30）可能误杀稀有特征 | 中 | `theta_forget` | 调到 0.02 |
| counter 来源差异被扁平化 | 低 | `gamma: dict[source, float]` | 启用 dict 形式 |
| 状态切换原因丢失 | 低 | `Librarian.explain(id)` | 默认开 |
| ρ 的"非随机抽样修正"在自参照框架下是误用 | 已修正 | ρ 默认 1.0，仅作可选开关 | 见 §3.3 |
| split 的 ObservationLog 重放需要假设沉默样本归属 | 中 | 选项 A：split 时让 Inducer 重新跑；选项 B：按比例近似 | 实施期决策 |
| Reshuffle 的"语义近亲家族"风险（新 candidate L0 接近老 feature）| 中 | reshuffle 专用 L0 阈值 0.75 + provenance 锁 | §3.7 默认开启 |
| Replay 阻塞用户连续 ingest | 低 | 用户必须先消费 pending_replays | §2.3 T_pending_replays，硬约束不可关 |
| ObservationLog 按 (sample, feature) 粒度膨胀（条目数量 = N×F 而非 N）| 中 | 每条 obs 仅 ~200 字节，N=1000 / F=50 时约 10MB，仍可控 | YAML 切 SQLite（Phase 4+ 才考虑）|
| Merge-policy 三选项增加用户认知负担 | 低 | 默认值表（§2.5）覆盖 95% 场景，新手可不指定 `--merge-policy` | 默认表已设 |

### 5.3 与现有方案的关系

| 方案 | 主方案处理 |
|---|---|
| `feature_mining_via_ai_design.md`（早期完整设计）| **多数被替代**：rule/hypothesis 二分、batch/incremental 二分、obs/episodes 启发式全部废弃 |
| `feature_mining_philosophy_decision.md`（三层架构 + 三条硬防御）| **完全保留并兼容**：vocabulary 归档 / hold-out / permutation 三条均与主方案叠加 |
| `feature_mining_v2_unified_decision.md`（agent team 综合决策）| **作为本 spec 的核心数学骨架来源** |
| `feature_mining_unified_schema.md`（unifier 产出）| **作为 schema 细节来源** |
| `feature_mining_orchestration_revisit.md`（Q1/Q2/Q3 三问复盘）| **作为本 spec v2 修订基础**：Q1 → CLI Scheduler / Q2 → Multi-epoch 四机制 / Q3 → Critic 不动 Inducer prompt |
| `feature_mining_shuffled_reinduction.md`（4th 机制深入设计）| **作为 §2.6 Shuffled 部分的设计基础**：anti-correlated 默认 / provenance 锁 / 4 cond 终止 |
| 现有 `mining/` pipeline | **完全不动**（与本框架解耦）|
| 现有 `add-new-factor` skill | **不动**（保留为下游可选出口）|
| 现有 13 因子 | **不动**（仅在 Phase 4+ 通过 `factor_overlap_declared` 字段对接）|

### 5.4 Phase 路线图

| Phase | 范围 | 内容 | 工程量 |
|---|---|---|---|
| **Phase 0** | 数据基线 | 5 个盘整字段 + chart renderer + nl_description 预处理（Opus 一次性）| 3-4 天 |
| **Phase 1** | Librarian + Inducer MVP | Beta-Binomial 核心 + L0/L1 + Inducer batch 模式 + 文件系统骨架 + ObservationLog 按 (sample, feature) 粒度展开 | 1 周 |
| **Phase 1.5** | epoch_tag + Merge Semantics + Replay 队列 | epoch_tag/superseded_by/provenance 字段 + Librarian.upsert_candidate 实现三策略 + pending_replays.yaml 队列 + apply_replays 命令 | 3-4 天 |
| **Phase 2** | CLI Scheduler + dev UI | feature-mine 命令套件（ingest / status / list / show / review-orphans / review-critic / apply-replays / reinduce / snapshot / export-yaml）+ P/N 键 hook + INDEX.md 自动生成 + 被动提醒 | 1 周 |
| **Phase 3** | Critic（核心子集）+ 三条硬防御 | Critic 接 disputed + rewrite + 用户请求 + Replay 入队 / vocabulary 归档 / hold-out / permutation | 1 周 |
| **Phase 4a** | Reshuffle Re-induction | 共现矩阵基础设施（cooccurrence.yaml）+ random / anti-correlated 两策略 + 4 cond 终止 + dry-run + L0 强化阈值 + provenance 锁生效 | ~5 天 |
| **Phase 4b**（可选）| L2 archetype hint + 进阶 Re-induction | Python 自动 archetype hint（Critic 不参与）+ 用户 reinduce 命令 supersede-only 选项 | ~3 天 |
| **Phase 4c**（可选）| Critic 高级动作 | split / merge / abstract / archetypes 抽象层 | ~5 天 |
| **Phase 4+**（按需）| NL Adapter / Coder L2.5 | `feature-mine ask` NL→CLI 翻译薄壳 / 动态编码 verifier | — |

**Phase 0-3 总工程量 ~4 周**（比原 3.5 周多 0.5 周吸收 Phase 1.5 的 epoch_tag + Merge + Replay 工程）。Phase 0-2 跑通后框架具备 MVP 闭环；Phase 3 加固防御；Phase 4a 是用户驱动的探索增量；Phase 4b/c 按需选取。

### 5.5 工程量分解（按模块）

| 模块 | 类型 | 工程量 | Phase |
|---|---|---|---|
| `feature_library/` 文件系统骨架 + INDEX.md 自动生成 | 新增 | 1 天 | P1 |
| Librarian Python 模块（Beta-Binomial + L0/L1 + ObservationLog 粒度展开）| 新增 | 3 天 | P1 |
| Inducer SKILL.md 模板（batch + single 模式）| 新增 | 2 天 | P1 |
| Librarian.upsert_candidate（三 merge-policy）+ epoch_tag/supersede 机制 | 新增 | 2 天 | P1.5 |
| pending_replays 队列 + Librarian.apply_replays + Librarian.recompute（含 supersede 跳过）| 新增 | 1.5 天 | P1.5 |
| `feature-mine` CLI 命令套件 + 被动提醒 + 模式解析 | 新增 | 4 天 | P2 |
| Dev UI P/N 键 hook + cold-start 抽样 | 修改既有 dev UI | 2 天 | P2 |
| Critic SKILL.md 模板（disputed + rewrite + user request + Replay 入队）| 新增 | 2 天 | P3 |
| Vocabulary 归档（PartialSpec 自动 append → vocabulary_draft.md）| 新增 | 0.5 天 | P3 |
| Hold-out 标记字段 + permutation test 工具 | 新增 | 4 天 | P3 |
| 共现矩阵 cooccurrence.yaml + Librarian.update_cooccurrence + get_anti_correlated_batch | 新增 | 2 天 | P4a |
| `feature-mine reshuffle` 命令 + 4 cond 终止 + dry-run + provenance 锁生效 | 新增 | 2.5 天 | P4a |
| Spec 文档 + 单元测试 | — | 持续 | 全程 |
| **合计 P0-P3** | | **~4 周** | |
| **合计 P4a** | | **~5 天** | |

### 5.6 不在本期范围（明确搁置）

- Coder subagent / L2.5（动态编码 verifier）
- Critic 的 split / merge / abstract 高级动作（Phase 4c 才做）
- archetypes/ 抽象层
- 多形态跨 archetype 类比（intel-advocate 的 cross_cutting）
- 与 13 因子 overlap 的定量化（需要 primitive vector，留 Phase 4+）
- algo 路径（Apriori / FP-Growth）
- p0 / control corpus / 反例池
- L2 archetype hint（Phase 4b 才做；Critic 不参与）
- NL Adapter（`feature-mine ask`，Phase 4+ 按需）
- Reshuffle 的 stratified-by-source-feature 策略（永远不做，违反 §4.3 信息泄露约束）

---

## §6 核心决策汇总

整合三层讨论后的决策清单（v1 → v2，"用最新结论覆盖旧结论"）：

| # | 决策项 | 对应章节 |
|---|---|---|
| 1 | 规律存储 = 纯定性 NL + embedding + verifier_prompt（可选 snippet）| §3.1, §4.2 |
| 2 | 三层成本阶梯（L0 embed / L1 DeepSeek / L2 Opus / L2.5 codify）| §1.1, §5.6 |
| 3 | 迭代节奏 = **用户驱动 CLI**（cold-start / incremental / reinduce / reshuffle 全由用户命令触发；触发清单改为被动提醒，**无任何自动调度**）| §2.2, §2.3 |
| 4 | **三 AI 角色 + CLI Scheduler**（Inducer / Librarian / Critic + `feature-mine` Python CLI 工具集；原 Orchestrator 降级为纯 Python，无 LLM）| §1.1 |
| 5 | Inducer 不查重，Librarian 做归并/强化（按 §2.5 merge-policy）| §4.3, §2.5 |
| 6 | Unprompted vs Prompted 二分（unprompted 经 merge-policy 入库；prompted 直接走 supersede 检查）| §2.4 |
| 7 | DeepSeek 非多模态 → 引入"样本 NL 描述"中间态 | §2.1 数据流 |
| 8 | L0 是 L1 的预筛 + 高置信端自动决策；reshuffle 模式下 L0 阈值更严（0.75 vs 默认 0.85）| §4.4, §3.7 |
| 9 | 反例不是框架内置（仅作另一应用场景）| §0.5 |
| 10 | 统计模型 = Beta-Binomial（统一 rule/hypothesis/batch/incremental/replay/reshuffle 多机制）| §3 |
| 11 | p0 默认不开（首选自参照判据）| §0.5, §3.3 |
| 12 | ρ 默认 1.0（用户挑选 = 框架定义域，不需要打折）| §0.5, §3.3 |
| 13 | Critic = "主编"（拆/合/重写/disputed 裁决，**不动 (α, β)**、**不动 Inducer prompt**）| §1.1, §4.5, §4.7 |
| 14 | **Multi-epoch 四机制**：Replay 必做 / Re-induction 用户触发可选 / Re-verification 隐含在 Path V / Shuffled Re-induction 用户触发可选 | §2.6 |
| 15 | **ObservationLog 按 (sample, feature) 粒度展开** + `epoch_tag` + `superseded_by` 字段防双重计数 | §2.6, §4.2 |
| 16 | **Merge Semantics 三策略**：full / supersede-only / reject-merge；reshuffle **强制 supersede-only**（防止反对票复利）| §2.5 |
| 17 | **Feature 级 `provenance` 字段** + Shuffled-诞生 feature 的 candidate 锁（直到出现至少 1 条 source != shuffle 的事件才解锁）| §2.6, §4.2 |
| 18 | **Replay 阻塞规则**：Critic 修改后必须先 `apply-replays` 才能继续 ingest（数学一致性硬约束）| §2.3, §4.7 |
| 19 | **archetype hint（Phase 4b）由 Python 维护，Critic 不参与**（防 reward hacking）；epoch>0 / shuffle 时强制禁用 archetype hint | §8 备选 8 |
| 20 | **Reshuffle 默认策略 anti-correlated** + 4 条终止条件（共现率 / 新产出衰减 / 预算 / dry-run）+ provenance 锁 | §2.6, §3.7 |
| 21 | **CLI 触发清单**：T_init / T_orphan / T_period / T_critic_health 全部改为被动提醒；T_pending_replays 是唯一 ERROR 级别（阻塞 ingest）| §2.3 |
| 22 | **删除 spec 中"每周/每月"自动节奏描述**：所有时机由用户命令决定 | §2.2, §2.3 |

---

## §7 关键未解问题（交用户实施期拍板）

| # | 问题 | 推荐倾向 | 理由 |
|---|---|---|---|
| Q1 | θ_consolidated = 0.40 是否合适？| 先用 0.40 跑 3-6 个真实归纳轮次再校准 | 真实数据驱动 |
| Q2 | γ = 3 是否过严？| 先跑一段时间，统计 L1 与人类裁决一致率，<80% 时调到 γ=2 | 用证据校准 |
| Q3 | λ = 0.995（半衰期 138 天）合理吗？| 可调整为 0.997（半衰期 230 天）或保留 0.995 | 美股形态稳定性经验 6-12 月 |
| Q4 | 多 invariant 共享样本时是否需要联合后验？| 先按独立处理，Phase 4+ 再考虑 hierarchical model | invariant <10 时独立模型够用 |
| Q5 | promotion gate（P5 ≥ θ_promote → Factor Draft）放哪一步？| Librarian 之外的独立 promotion-gate 步骤，用户主动触发 | permutation test 较贵 |
| Q6 | mining pipeline 失败的 feature 如何处理？| 标记 `mining_failed: true`，从 candidate pool 移除，但保留 ObservationLog | 失败 = falsified |
| Q7 | Phase 4+ 启用 algo 路径时新候选 invariant 如何接入？| `source='apriori_mining'` 注入 InducerOutput，Librarian 不区分来源 | Beta-Binomial 工程优势 |
| Q8 | 是否需要"feature 之间依赖"机制（如 invariant A 推论 B）？| 不在本研究范围，Phase 4+ 用单独 `feature_implication_graph.yaml` | 不污染 Librarian |
| Q9 | Split 的 ObservationLog 重放选 A（重跑）还是 B（按比例近似）？| 实施期决策，先选 B 跑通，遇到精度问题再升 A | 工程便利 |
| Q10 | 用户挑选样本的"严格度"是否需要 metadata？| Phase 4+ 才考虑 | 当前用统一 source='user_pick' |
| Q11 | Reshuffle 4 cond 终止条件是否充分？是否需要 "feature 多样性指标" 作为 cond E？| 先 4 cond 跑通 Phase 4a，实证后再加 | 工程渐进 |
| Q12 | provenance 锁解锁条件（要求至少 1 条 source != shuffle 事件）是否过严？是否要"M 轮 shuffle 持续验证后强制解锁"退路？| 不给退路，强迫用户用真新数据验证 | 安全保守 |
| Q13 | merge-policy 默认值在 reinduction 是 `full`，是否应改为 `supersede-only` 与 reshuffle 对齐？| 暂保留 `full`（统计严谨），用户可显式覆盖；`default_merge_policy_reinduce` 开关支持改默认 | 严格度选择留给用户 |
| Q14 | archetype hint（Phase 4b）的 LLM 选型：DeepSeek vs sentence-transformer + 规则模板？| 倾向 sentence-transformer + 模板（零额外 LLM 依赖，可缓存）| 控成本 |
| Q15 | NL Adapter（`feature-mine ask` 薄壳）是否在 Phase 4+ 实现？| 仅在用户明确反馈"CLI 太硬核"时再做 | YAGNI |
| Q16 | Replay 队列的并发模型：用户在 Critic 提议 pending 期间又跑 ingest 是否允许？| 推荐"必须先消费 pending replays"（已在 T_pending_replays 实现），用户可选 `--allow-pending` 宽松模式但有警告 | 数学一致性优先 |
| Q17 | Reshuffle 的成本守护：是否在 `reshuffle` 时强制显示预估 Opus token 消耗 + 确认提示？| 是。`--dry-run` 必跑；非 dry-run 模式默认 `--confirm`，需用户回车 | 防误操作 |
| Q18 | Snapshot 格式：`feature-mine reset --snapshot <path>` 的归档形态（tar.gz / git branch / 整个 feature_library/ copy）？| 推荐 tar.gz，简单 + 跨平台 | 工程便利 |
| Q19 | ObservationLog 按 (sample, feature) 粒度展开后，N=1000 / F=50 时 ~50000 条目（约 10MB），YAML 是否仍合适？| 阈值之内仍用 YAML；N≥500 触发被动提醒"建议切 SQLite" | 工程渐进 |

---

## §8 附录：路上否决的备选方案 + 理由

### 备选 1（已否决）— 保留 rule/hypothesis 二分 + 启发式阈值

留旧架构的多字段 + 二分判定。

**否决理由**：用户在统计模型质询中亲自指出了"2/10 vs 1/1 颠倒"和"hypothesis 纯增量"两个硬伤，启发式无法修复，必须上 Beta-Binomial。

### 备选 2（已否决）— 单 agent 长 session 包揽

省 multi-agent 协调成本，所有工作（归纳/累积/批判）在同一 Claude session。

**否决理由**：用户明确要求"上下文隔离 + 分工 + 节约 token"，且当 features 规模扩大后单 session 必然上下文爆炸。

### 备选 3（已否决）— 纯叙事自然语言笔记本（intel-advocate 的极致版）

不上 Beta-Binomial，所有累积都是 AI 在自然语言里说服自己。

**否决理由**：drift 风险高，无法回应"为什么这条规律算 rule"的问题。

### 备选 4（已否决）— 算法主导 + AI 模块化打工（algo-advocate 的极致版）

primitive vocabulary + Apriori / GA / 图挖掘 + AI 只做视觉特征提取与语言适配。

**否决理由**：cold-start 阶段 vocabulary 没建好，algo 路径无从启动；GA/HMM/图挖掘在小样本（<500 BO）阶段是"过拟合制造机"。Phase 4+ 当样本量足够时再评估。

### 备选 5（已否决）— 路径 1：单图特征提取 + Beta-Binomial 累积

让 Opus 单图列特征，Beta-Binomial 自己累积谁是规律。表面上省 Opus 调用。

**否决理由**：单图列出的特征太杂（噪声多、随机出现的小细节），没有跨图对比的"显著性"过滤，总特征数会爆炸（每张图 30-50 条 → L0/L1 计算成本几何膨胀）。**虚假经济**。

### 备选 6（已否决）— ρ 用作"非随机抽样修正"

ρ_user_pick = 0.4 这种默认打折值。

**否决理由**：本框架的目标域**就是用户挑选的样本集合**，"偏差"不是缺陷而是定义域。修正反而是误用。ρ 改造为可选开关，默认 1.0。

### 备选 7（已否决）— AI Orchestrator（Claude Opus 长 session 调度器）

让 Claude Opus 持续运行，自主决定 batch / incremental 时机，监控触发条件，编排 Inducer / Critic 调用。

**否决理由**：原 Orchestrator 的所有调度决策（mode 选择 / 触发监控 / 队列管理 / 状态汇报）都是确定性规则，AI 价值为零或负——增加不确定性、token 成本、降低可调试性，且与"用户驱动"的使用场景错位。改为 Python CLI Scheduler 后零 LLM 调用、即时决策、可重放。详见 `feature_mining_orchestration_revisit.md` Q1。

### 备选 8（已否决）— Critic 直接重写 Inducer prompt（L3 archetype hint）

让 Critic 看到"F-001 已 strong"后，更新 Inducer prompt 为"去找跟 F-001 不同的特征"，动态升级 Inducer 能力。

**否决理由**：违反 §4.3 Inducer 盲跑硬约束。具体风险：
- **信息泄露 / Reward hacking**：Inducer 知道库内有什么，会偏向产出"已存在 features 的近邻"
- **探索崩塌**：动态 prompt 让 Inducer 系统性偏向某些子空间
- **Critic 偏差放大**：Critic 自己不是无所不知的，"已 strong" 判断可能错位
- **统计独立性破坏**：Beta-Binomial 假定独立观察，Inducer 产出受库内容影响则独立性失效

替代方案保留：Phase 4b 的 archetype hint 是 **Python 自动维护的 high-level 抽象层摘要**（不暴露具体 feature 文本），且**Critic 不参与**生成。详见 `feature_mining_orchestration_revisit.md` Q3。

### 备选 9（已否决）— Reshuffle 用 stratified-by-source-feature 策略

让每个老 feature 选 K 张支持样本，组成 mixed batch 跑 Reshuffle Inducer。

**否决理由**：违反 §4.3 信息泄露约束——Inducer 收到的 batch 是按"feature 归属"挑选的，等价于把库内 feature 信息间接告诉 Inducer。可能让 Inducer 反推"这是什么 feature 的样本"，触发 reward hacking。Reshuffle 必须用 anti-correlated 或 random 等 feature-agnostic 策略。详见 `feature_mining_shuffled_reinduction.md` §4.1 策略 5。

### 备选 10（已否决）— 多视角增强（同样本生成多份 nl_description 各算一次观察）

对老样本用不同 prompt 重新生成多份 nl_description，每份算独立观察累加 (α, β)。

**否决理由**：破坏 Beta-Binomial i.i.d. 假设——同一物理样本被伪装成多个独立观察，等价于伪造证据。这不是 multi-epoch 的合法语义。详见 `feature_mining_orchestration_revisit.md` §2.3。允许的"重观察"路径只有 Replay / Re-induction / Reshuffle 三种，且都通过 epoch_tag + supersede 机制保护 i.i.d.。

---

## §9 一段话最终结论

**本框架用 Beta-Binomial 共轭后验作为唯一统计量**：每条 feature 仅 `(α, β, ts, provenance, observed_samples)`，update 公式 `α += K, β += (N-K-C) + γ·C`，信号 `S = Beta_P5(α, β)` 派生 5 档语义带（受 provenance 锁约束）。`rule/hypothesis` 二分、`batch/incremental` 二分、`obs/episodes/counter` 多字段全部塌缩。p0 / ρ 默认不参与（自参照判据，用户挑选即定义域）。架构上是**三 AI 角色**（Inducer 多图对比唯一新规律来源 / Librarian 机械累积 + 执行 §2.5 三 merge-policy / Critic 主编式审视语义层问题且不动 (α, β) 不动 Inducer prompt）+ **CLI Scheduler**（`feature-mine` Python 工具集，零 LLM，确定性规则，被动提醒）。**Multi-epoch 通过四机制实现**（Replay 必做 / Re-induction 用户触发 / Re-verification 自动隐含 / Shuffled Re-induction 用户触发 + provenance 锁 + anti-correlated 默认 + 强制 supersede-only），双重计数由 ObservationLog 按 (sample, feature) 粒度展开 + epoch_tag + superseded_by 联防。所有状态住 `feature_library/` 文件系统。最大代价是 epoch_tag + Merge Semantics 三策略增加少量工程复杂度，给出 §3.7 回退开关。最大收益是多路径塌缩 1 update + 状态全派生 + 用户完全控制时机 + 数学严谨防双重计数。工程量 ~4 周（Phase 0-3 MVP 闭环），Phase 4a Reshuffle ~5 天可选增强。与 `philosophy_decision` 三条硬防御完全兼容。

---

**Spec 结束。**
