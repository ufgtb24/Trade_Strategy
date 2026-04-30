# Feature Mining v2 — 统一决策（统计骨架）

> 决策日期：2026-04-25
> 角色：`base-rate-analyst`（综合 task #1/#2/#3 产出，承担最终决策）
> 上游输入：
> - `docs/research/feature_mining_stats_models.md`（task #1，stats-modeler 产出，推荐 Beta-Binomial）
> - `docs/research/feature_mining_base_rate.md`（task #2，本作者产出，p0 双阶段方案）
> - `docs/research/feature_mining_philosophy_decision.md`（前置 brainstorming 共识：三层架构）
> - `docs/research/feature_mining_via_ai_design.md`（现有完整方案）
> - `docs/research/feature_induction_workflow_detail.md`（多轮 compact 流程）
> 范围：本文是 task #4 的最终交付物。task #3（统一 schema）合入此文档（§3）一并交付，不再单独成文。

---

## TL;DR（三条核心决策）

1. **统计模型**：**Beta-Binomial 共轭后验（Jeffreys prior）+ 时间衰减 λ + counter 加权 γ + 抽样修正 ρ**。每个特征状态仅 `(α, β, t)`，O(1) 增量更新。信号强度 `S = Beta_P5(α, β)`，单一连续值同时承担"成熟度"语义。
2. **基线频率 p0**：**冷启动期不依赖 p0**（Beta P5 是自参照判据，不需要与 p0 比较）。仅在用户明确启用 LLR/PMI 等 p0-依赖判据时才走 §4 的 control corpus + hierarchical Bayes。**首选不开 p0**。
3. **统一 schema**：**只有一种实体 `observed_feature`**，状态由 P5 阈值带（candidate / supported / consolidated / disputed / forgotten）派生而非存储。`rule/hypothesis` 二分、`batch/incremental` 二分、`independent_observations/episodes/counter_observations/prompted_yes-no` 全部塌缩为 `(α, β)` 两个 sufficient statistics。6 路径表（source × target）塌缩为 **1 条 update 路径**。

**最大代价**：用户原始 brainstorming 中"episode 数 ≥ 2 才能升级"这个**额外健壮性条件**在统一后失去显式表达，需通过 `pseudo_count` 隐式表达（详见 §6）。这是单一最大的表达力损失，给出回退开关。

**最大收益**：所有"什么时候算 rule、什么时候降级、batch vs incremental 怎么处理、counter 怎么算、新数据怎么累加"这类问题，**都退化为同一个 `update(α, β, e)` 公式 + 一个 `quantile(0.05)` 查询**。代码、UI、心智模型一次性简化。

---

## §1 推荐数学模型（采纳 task #1）

### 1.1 模型定义（最终形式）

每个特征 `f` 维护状态 `(α_f, β_f, t_f)`：

- `α_f`：累积支持证据（伪计数）
- `β_f`：累积反对证据（伪计数）
- `t_f`：上次更新时间戳

**先验**：`α₀ = β₀ = 0.5`（Jeffreys prior）

**更新公式**（接收事件 `e = (K, N, C, t, source)`）：

```
# Step 1 — Lazy time decay (since last update)
days = (t - t_f).days
decay = λ ** days                    # λ = 0.995, half-life ~138 d
α_f = max(α₀, α_f * decay)
β_f = max(β₀, β_f * decay)

# Step 2 — Sampling-aware injection
ρ = sampling_rho(source)             # user_pick=0.4, cold_start=0.7, random=1.0
α_f += ρ * K
β_f += ρ * ((N - K - C) + γ * C)     # γ = 3
t_f = t
```

**信号强度**：

```
S(f) = scipy.stats.beta.ppf(0.05, α_f, β_f)    # Beta P5 = 95% lower bound
```

### 1.2 为什么是 Beta-Binomial（而非 Wilson / LLR / SPRT / PMI）

引用 task #1 §8.1 的七大性质评分（满分 35）：

| 候选 | 评分 | 决定性差异 |
|---|---|---|
| **A. Beta-Binomial** | **34** | 时间衰减自然、counter 整合自然、与 p0 解耦、可解释性最强 |
| B. LLR | 31 | 必须先指定 `p0, p1`；与本研究 p0 决策（首选不依赖 p0）冲突 |
| C. Wilson | 27 | 衰减不自然、counter 整合需"膨胀 N"破坏精确性 |
| D. SPRT | 27 | "决策即终止"哲学不匹配可逆判定 |
| E. PMI | 17 | 需全局边际，不适合 incremental |

**关键决定性因素（与 task #2 协同）**：Beta-Binomial 的 P5 是**自参照判据**——"我至少有 95% 把握，特征真实命中率不低于 S"。这个语义**不依赖 p0**。冷启动期 p0 不可信时，Beta P5 仍然是数学上严谨的判据。LLR/PMI 没有这个性质。

### 1.3 信号强度的 5 档语义带

`S = Beta_P5(α, β) ∈ [0, 1]` 通过下表映射到状态语义（**仅 UI 与汇报使用，不参与 update 逻辑**）：

| 状态 | P5 阈值带 | 语义 | UI 颜色建议 |
|---|---|---|---|
| `candidate` | `[0.00, 0.10)` | 新鲜假设 / 证据不足 | 灰 |
| `supported` | `[0.10, 0.30)` | 弱信号 / 待累积 | 蓝 |
| `consolidated` | `[0.30, 0.60)` | 已成熟规律 | 绿 |
| `strong` | `[0.60, 1.00]` | 高置信规律 | 深绿 |
| `disputed` | 任何带 + counter > 0.3 × β | 有效证据但反对显著 | 黄（与 P5 带正交叠加） |
| `forgotten` | `S < 0.05 且 N_total < 3` | 几乎肯定不是规律 | 隐藏 |

**关键设计**：阈值带不是判定门槛，是**显示语义**。所有 update 都用同一公式，状态只是 P5 的连续刻度的人类可读切片。如果用户不喜欢"3 档"也可以换成 7 档 / 10 档 / 渐变色——这是表现层选择，不是数学模型选择。

`disputed` 状态独立判据：当 `counter_total / β_total > 0.3` 时叠加 `disputed` 标记。这是把 `counter` 信息 **额外**暴露给用户的方式（β 已经吸收了 counter 但不可见，所以加一层显式标记）。

### 1.4 衰减/counter/抽样三个调节维度的语义

| 维度 | 参数 | 推荐起点 | 调大效果 | 调小效果 |
|---|---|---|---|---|
| 时间衰减 | λ | 0.995（half-life ~138d）| λ→1：永不遗忘 | λ↓：快速遗忘 |
| Counter 权重 | γ | 3 | γ↑：DeepSeek 否决更狠 | γ=1：与沉默样本同权 |
| 抽样修正 | ρ | user=0.4 / cold=0.7 / rand=1.0 | ρ→1：更相信用户 | ρ↓：更怀疑用户偏差 |

每个维度都是**正交的旋钮**，用户可独立调节。这是 Beta 模型的工程友好性。

---

## §2 推荐 p0 方案（采纳 task #2）

### 2.1 决策：**首选不开 p0**

由于本研究最终统计模型是 Beta P5（自参照判据），**默认配置下 p0 不参与任何决策**。这是最简洁、最鲁棒的选择，避免了 biased sampling 带来的 p0 估计困难。

### 2.2 何时需要 p0？

仅在用户**主动启用**以下场景之一时才需要：

1. **辅助报告**：用户希望同时看到 LLR / PMI 等"显著性"语义判据（多模型并行报告，提升可信度）
2. **Sanity check**：用户在 mining UI 上手动比较 Beta P5 与 LLR 是否一致
3. **下游 mining pipeline 接入**：若 `mining/` 流水线某些 step 需要 p0（如 chi-square test），由 mining 模块自行决定

**只在这些 opt-in 场景下激活 p0 估计**。Librarian 主路径完全不依赖。

### 2.3 启用后的 p0 估计协议（task #2 摘要）

**Phase 0**（< 10 正例）：跳过统计判据；UI 只显示 K/N。

**Phase 1**（10-30 正例）：用 task #2 §4.4 的"默认 p0 表"+ 大不确定度。

**Phase 2**（30+ 正例 + 20+ 反例）：从 label-matched control corpus 估每特征 hierarchical Bayesian p0。control corpus 直接复用 §3.4 主反例池。

详见 `docs/research/feature_mining_base_rate.md` §3-§5。

### 2.4 p0-Beta 协同原则

如果同时报告 Beta P5 和 LLR（用 estimated p0），**两者结论应一致**。若不一致：
- Beta P5 高、LLR 低 → 通常是 p0 估计过低（control corpus 偏差）
- Beta P5 低、LLR 高 → 通常是 p0 估计过高（visual bias 残留）

不一致信号**有诊断价值**，应在 UI 中显式提示，而非简单平均。

---

## §3 统一 Schema（task #3 合并交付）

### 3.1 实体定义：`observed_feature`

```yaml
observed_feature:
  # ===== Identity =====
  feature_id: str                   # UUID 或 hash(description)
  description: str                  # 一句话自然语言描述
  archetype: str | null             # 形态原型名（可选，用于 §3.4 索引）

  # ===== Sufficient Statistics（核心，不可缺）=====
  alpha: float                      # ≥ α₀ = 0.5
  beta: float                       # ≥ β₀ = 0.5
  last_update_ts: datetime          # for lazy decay

  # ===== Provenance / 观察日志 =====
  observations: list[ObservationLog]   # 每次 update 的留痕（见 §3.2）
  total_K: int                       # Σ K_i across observations（便于 sanity check）
  total_N: int                       # Σ N_i
  total_C: int                       # Σ C_i

  # ===== Derived（不存储，运行时计算）=====
  # signal_S = scipy.stats.beta.ppf(0.05, alpha, beta)
  # status_band = derive_band(signal_S, total_C / max(beta, 1))
  # mean = alpha / (alpha + beta)

  # ===== Optional / Phase 4+ =====
  overlap_with_existing: list[str]   # 现有 13 因子 key
  overlap_kind: 'duplicate' | 'refinement' | 'orthogonal' | null
  factor_draft: dict | null          # Layer B 8 字段；仅当成熟到可生产因子时非 null
  research_status: 'active' | 'saturated' | 'parked'   # 系统级学习状态
```

### 3.2 ObservationLog（观察事件留痕）

```yaml
ObservationLog:
  ts: datetime                      # 事件发生时间
  source: 'ai_induction' | 'user_pick' | 'cold_start' | 'random' | 'deepseek_l1'
  K: int                            # 支持样本数（≥ 0）
  N: int                            # batch 大小（≥ 1）
  C: int                            # counter 数（≥ 0）
  rho_applied: float                # 实际使用的 ρ（用于回溯）
  gamma_applied: float              # 实际使用的 γ
  alpha_after: float                # update 后的 α 快照
  beta_after: float                 # update 后的 β 快照
  signal_after: float               # update 后的 P5
  notes: str | null                 # 可选注释（如 spec round_id、用户挑选 reason）
```

**为什么保留 ObservationLog**：
- (α, β) 是 sufficient statistic，理论上不需要原始事件序列
- 但**人类需要可追溯性**：用户回顾"这个特征是怎么从 candidate 升到 consolidated 的"时，必须能看到 update 序列
- 也是抗错的最后防线：若发现 γ/ρ 设错了，可以从 log 重新累加

存储成本：每特征每事件 ~200 字节，几年内不会有规模问题。

### 3.3 状态语义带是 Derived 而非 Stored

**核心设计原则**：`status_band`（candidate / supported / consolidated / strong / disputed / forgotten）**不在 schema 中存储**，由 `signal_S` 实时映射。

理由：
- 阈值带是显示层选择，未来可能调整。如果存储则每次调整都要 migrate
- 单一来源真理（α, β）保证 schema 不会出现"alpha 显示这是 consolidated，但 status 字段说是 candidate"这样的不一致

实现上，UI 层调用 `derive_band(signal_S, counter_ratio)` 即可。

### 3.4 Inducer 的统一输出契约

**无论 batch size、无论是 incremental 单样本，Inducer 输出格式一致**：

```yaml
inducer_output:
  feature_id: str                    # 已有特征 ID 或 new
  description: str
  K: int
  N: int
  C: int
  source: enum
  ts: datetime
  notes: str | null
```

这是 §3.2 ObservationLog 的子集（去掉 `*_applied` 和 `*_after` 字段，那些由 Librarian 计算）。

**incremental = batch size 1 的特例**：N=1 时 K∈{0,1}, C∈{0,1}, K+C ≤ 1。无需特殊处理。

### 3.5 Librarian 的统一更新逻辑

**单一函数处理所有事件**：

```python
def librarian_update(feature: ObservedFeature, event: InducerOutput, config: LibrarianConfig) -> ObservedFeature:
    # 1. Lazy time decay
    days = (event.ts - feature.last_update_ts).days
    decay = config.lambda_decay ** max(0, days)
    feature.alpha = max(config.alpha_prior, feature.alpha * decay)
    feature.beta  = max(config.beta_prior, feature.beta  * decay)

    # 2. Compute effective injection (sampling-aware)
    rho = config.rho_for_source(event.source)
    gamma = config.gamma
    alpha_inc = rho * event.K
    beta_inc  = rho * ((event.N - event.K - event.C) + gamma * event.C)

    # 3. Update statistics
    feature.alpha += alpha_inc
    feature.beta  += beta_inc
    feature.total_K += event.K
    feature.total_N += event.N
    feature.total_C += event.C
    feature.last_update_ts = event.ts

    # 4. Append observation log
    feature.observations.append(ObservationLog(
        ts=event.ts, source=event.source, K=event.K, N=event.N, C=event.C,
        rho_applied=rho, gamma_applied=gamma,
        alpha_after=feature.alpha, beta_after=feature.beta,
        signal_after=scipy.stats.beta.ppf(0.05, feature.alpha, feature.beta),
        notes=event.notes,
    ))

    return feature
```

**核心要点**：
- 一段函数处理 batch / incremental / counter 三类事件
- `K=0, C=0, N=N_total` 是"主动注入反例"事件（从 task #1 §12.3 第 1 条）
- `K=0, C=N` 是"DeepSeek 全否决"事件
- `K=1, N=1, C=0` 是"用户单点确认"事件

所有特例都是同一公式的特例，无 if/else 分支。

### 3.6 6 路径表的塌缩

之前 brainstorming 中讨论的"source × target"路径（来自人/AI、目标 rule/hypothesis、incremental/batch 等）的二分组合可能多达 6+ 条。在统一 schema 下：

| 旧路径 | 新表示 | 备注 |
|---|---|---|
| `(AI batch) → rule` | `librarian_update(source='ai_induction', N>1)` | 阈值由 P5 决定，非路径决定 |
| `(AI batch) → hypothesis` | 同上 | 同上 |
| `(AI incremental) → rule` | `librarian_update(source='ai_induction', N=1)` | 同上 |
| `(AI incremental) → hypothesis` | 同上 | 同上 |
| `(user pick) → rule` | `librarian_update(source='user_pick', ...)` | ρ 自动调整 |
| `(counter) → demote` | `librarian_update(C>0)` 触发 disputed 标记 | 不必单独路径 |

**6 路径塌缩为 1 条 update 路径**。源/目标差异通过 `source` 参数和 `(K, N, C)` 比例自然表达，不需要分支。

### 3.7 与之前 brainstorming 共识字段的兼容映射

| 旧字段（brainstorming） | 新表示 | 处理方式 |
|---|---|---|
| `independent_observations` | 替换为 `total_N` | 在 ObservationLog 中可还原 |
| `episodes` | **隐式吸收**于 (α, β) 的累积 | 见 §6 损失说明 |
| `counter_observations` | 替换为 `total_C` + `gamma_applied` | 完整还原 |
| `prompted_yes` | 等价于 `K` 增量；无需独立字段 | source='user_pick' 标记 |
| `prompted_no` | 等价于 `C` 增量；source='user_pick' 标记 | 完整还原 |
| `obs >= 2 AND episodes >= 2 → rule` | `S >= 0.30` 派生为 `consolidated` | 不再用启发式阈值 |

**真正的功能损失**（见 §6 详述）：
- "**至少 2 次独立 episode**"这个**多次独立观察的健壮性**条件，没有 1:1 对应字段
- `(α, β)` 看到 `K=10, N=10, episodes=1` 与 `K=2, N=2, episodes=5` 区别不大（都是后者偏弱、但 P5 大致相当）

补救方案见 §6.2 的"pseudo_count"开关。

---

## §4 现有方案的具体改动清单

### 4.1 改 Inducer 输出契约

**当前方案**（`feature_mining_via_ai_design.md` §3.5 Layer B）输出 `factor_draft` 8 字段。

**新增**：每次 PartialSpec round 输出时，对每个 invariant 同时输出一个 InducerOutput（§3.4 schema）：

```yaml
# Each round produces both:
partial_spec: {...}  # 原现状
observation_events: list[InducerOutput]   # NEW，喂给 Librarian
```

**改动**：
- `induce-formation-feature` skill 的 `templates/feature_library_output.md` 在产出 PartialSpec 同时产出 InducerOutput 列表
- 每个 invariant 的 `K, N` 来自 PartialSpec 的 `coverage_stats.positives_explained` / `samples_seen_positive`
- `C` 来自 `counter_evidence` 长度

**工程量**：0.5 天（修改 skill 模板）。

### 4.2 改 Librarian 逻辑

**当前**：尚未实现独立的 Librarian 模块（按 brainstorming 共识，是新增组件）。

**新增**：实现 `BreakoutStrategy/feature_library/librarian.py`（建议路径），核心是 §3.5 的 `librarian_update` 函数 + 一个简单的 KV 持久化（YAML 文件 per feature）。

**接口契约**：
```python
class Librarian:
    def get_or_create(feature_id: str, description: str) -> ObservedFeature: ...
    def update(feature_id: str, event: InducerOutput) -> ObservedFeature: ...
    def query(filter_band: list[str] | None = None) -> list[ObservedFeature]: ...
    def stats(feature_id: str) -> dict: ...   # signal_S, mean, band, total_K, total_N, ...
```

**工程量**：1-2 天（含简单 YAML 持久化 + 单元测试）。

### 4.3 改实体 schema

**当前**：`feature_library/<form_name>.md` 是 Layer A + Layer B 的人读文档。

**新增**：每个 feature 同时维护一份 `feature_library/<form_name>/<feature_id>.yaml`（机读，§3.1 schema），Layer A/B 的人读 markdown 不变。

**关系**：
- 人读 markdown 是 archetype 级别（一个形态产出多个 feature）
- 机读 yaml 是 feature 级别（每个 invariant 一个 yaml）

**改动**：`induce-formation-feature` skill 的 `templates/` 增加 yaml schema validator。

**工程量**：0.5 天。

### 4.4 改 6 路径表

如 §3.6 所述：6 路径塌缩为 1 条 `librarian_update`。如果之前的 brainstorming 文档中存在显式的"6 路径表"，应**删除**（不再有意义）。

### 4.5 之前 brainstorming 共识的修订

| 共识项 | 状态 | 说明 |
|---|---|---|
| `feature_mining_philosophy_decision.md` §4.3 三条硬修正（vocabulary 归档、hold-out、permutation）| **保留** | 与 v2 不冲突，照常推进 |
| `feature_mining_philosophy_decision.md` §6 Phase 路线图 | **保留**，但 Phase 2 增加 Librarian 实现 | Phase 1 corpus exporter / Phase 2 dev UI + skill 主体 + **Librarian** / Phase 3 图像 |
| `feature_mining_via_ai_design.md` §3.4 反例池设计 | **保留并强化** | 既是 Inducer 反例输入、又是 control corpus（如 task #2） |
| `feature_mining_via_ai_design.md` §3.5 两层输出（Feature Spec + Factor Draft）| **保留** | Layer B 进入 `add-new-factor` 的前置仍是"P5 ≥ θ_promote"，θ 推荐 0.30 |
| `feature_mining_via_ai_design.md` §3.6 SKILL.md frontmatter | **保留** | 不动 |
| `feature_mining_induction_workflow_detail.md` §2.5 PartialSpec schema | **保留** | PartialSpec 是 Inducer 中间态，与 Librarian 解耦 |
| **rule / hypothesis 二分** | **废弃** | 替换为 P5 连续刻度 + 状态语义带（§1.3） |
| **batch / incremental 二分** | **废弃** | 单一公式，N=1 是退化 |
| `obs >= 2 AND episodes >= 2 → rule` 启发式 | **废弃** | 替换为 `P5 >= 0.30 → consolidated` |
| **counter / sentiment / DeepSeek L1 三类反对证据**的独立处理 | **统一** | 全部走 `(K, N, C, source)` event。source 字段保留区分 |

### 4.6 改动清单汇总

| 改动项 | 类型 | 工程量 | 优先级 |
|---|---|---|---|
| 新增 Librarian 模块 | 新增 | 1-2 天 | P0 |
| 修改 Inducer 输出契约（增 InducerOutput）| 修改 | 0.5 天 | P0 |
| 新增机读 yaml schema | 新增 | 0.5 天 | P0 |
| 修改 skill 模板（产出 InducerOutput）| 修改 | 0.5 天 | P0 |
| 状态语义带 UI 显示 | 新增 | 0.5 天 | P1 |
| 反例自动注入机制（task #1 §12.3 第 1 条）| 新增 | 0.5 天 | P1 |
| Hold-out / permutation / vocabulary 归档 | 新增 | 1 周 | P0（前置共识）|
| **总工程量** | | **~2 周** | — |

---

## §5 最终架构图

```
┌─────────────────────────────────────────────────────────────────┐
│  AI 归纳 (induce-formation-feature skill)                        │
│  - 多轮 compact loop 不变                                         │
│  - 输出 PartialSpec（不变） + InducerOutput[]（新增）              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Librarian.update(feature_id, event)                             │
│  - Lazy time decay                                               │
│  - Sampling-aware injection (ρ, γ)                               │
│  - Append ObservationLog                                          │
│  - Update (α, β, t)                                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  ObservedFeature 库（feature_library/<form>/<id>.yaml）           │
│  - sufficient stats: (α, β)                                      │
│  - signal_S = Beta_P5(α, β) (derived)                            │
│  - status_band = derive(signal_S) (derived)                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Promotion gate: signal_S >= θ_promote (default 0.30)            │
│  - 通过 → Layer B Factor Draft → add-new-factor skill            │
│  - + Hold-out 验证 (philosophy_decision §4.3 第 2 条)             │
│  - + Permutation test (philosophy_decision §4.3 第 3 条)          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  既有 mining/ pipeline (TPE + 5-dim OOS)                         │
│  - 完全不变                                                       │
│  - OOS 验证作为最终 falsifier                                     │
└─────────────────────────────────────────────────────────────────┘
```

**关键属性**：
- Librarian 是新增的"中间状态管理层"，介于 Inducer（AI skill）与 Promotion gate（mining）之间
- 上游：从 PartialSpec 中机械产出 InducerOutput
- 下游：当 P5 跨越 θ_promote 时触发 Factor Draft 生产
- 横向：与既有 mining pipeline 解耦（mining 不知道 Librarian 存在）

---

## §6 统一带来的代价（诚实承认）

### 6.1 损失项 1：episode 数语义被吞掉（最大代价）

**之前**：用户的 brainstorming 共识包含 `episodes >= 2 → rule` 这个**多次独立观察**的健壮性条件。

**现在**：Beta-Binomial 把所有观察当作伯努利试验累加，**不区分**"5 次 K=2/N=2 vs 1 次 K=10/N=10"——后者甚至略弱（因为 §1.4 ρ 已经把单次大 batch 折扣）。

**问题**：用户可能希望"哪怕 P5 已经达到 0.30，也要求至少 2 次独立 episode 才升级 consolidated"。这是**抗"单次大 batch 偶然命中"**的工程直觉。

**回退开关**（推荐保留）：

```python
# In LibrarianConfig:
min_episodes_for_consolidation: int = 1   # default 1 = no extra gate
                                           # set to 2 if user wants the old episode safeguard
```

`librarian.derive_band(feature)` 实现时：
```python
def derive_band(feature, config):
    S = scipy.stats.beta.ppf(0.05, feature.alpha, feature.beta)
    n_episodes = len(feature.observations)
    if S >= 0.30 and n_episodes < config.min_episodes_for_consolidation:
        return 'supported'  # 强制降一档，等待第二次独立观察
    return _band_from_S(S)
```

`min_episodes` 是**显示层**开关，不影响 (α, β)。用户可随时调，零迁移成本。

### 6.2 损失项 2：单批"大 N、低 K/N"的判别力不足

**情形**：某 invariant 在 1 个 batch 上看到 K=2, N=30，C=0。

**当前模型**（ρ=0.4）：α += 0.8, β += 11.2 → P5 ≈ 0.03 → forgotten

**直觉是否正确**：
- 如果用户认为"2/30 太低，应该忘掉" → 当前模型正确
- 如果用户认为"2/30 是有信号的、只是稀有" → 当前模型过严，会**误杀稀有特征**

**回退开关**：可调整 `forget_threshold`（默认 0.05）到 0.02 让稀有信号有更长存活期。但从原理看，2/30 在伯努利意义上确实弱。

### 6.3 损失项 3：counter / sentiment / DeepSeek L1 来源差异被"扁平化"

**之前**：用户可能希望"DeepSeek 的 counter 与人类的 counter 权重不同"。

**现在**：所有 counter 都进入同一个 `C` 字段，靠 `source` 参数和 `gamma` 调权。如果用户希望"DeepSeek counter 用 γ=3，人类 counter 用 γ=10"，需要扩展为 `gamma_by_source: dict[str, float]`。

**回退开关**：
```python
class LibrarianConfig:
    gamma: float | dict[str, float] = 3   # 单值 or by-source dict
```

实现时根据 `event.source` 查表。0.5 天工作即可加入。

### 6.4 损失项 4：状态切换的"原因"丢失

**之前**：rule → hypothesis 降级有显式原因（如"counter > X"）。

**现在**：状态切换是 P5 阈值越界，**为什么越界**需要查 ObservationLog。

**补救**：`Librarian.explain(feature_id)` 输出最近 5 个 update 的影响（α/β 变化贡献）。例如：
```
Feature 'tight_consolidation_breakout':
  Recent state: consolidated → supported (P5 dropped 0.32 → 0.27)
  Cause: 2026-04-20 event (source=ai_induction, K=1, N=10, C=0) injected
         large β=3.6 vs small α=0.4 → P5 drop -0.05
  Other factors: none
```

实现成本：0.5 天（基于 ObservationLog）。

### 6.5 不损失但需说明的项

| 项目 | 说明 |
|---|---|
| **可解释性** | 不仅没损失，反而增强（Beta P5 比 obs/episodes 二分有更明确的概率含义） |
| **抗 drift** | PartialSpec 的 evidence_receipts 不变，归纳过程的抗 drift 机制完全保留 |
| **与 mining pipeline 兼容** | 完全保留（Librarian 与 mining 解耦） |
| **与 add-new-factor 兼容** | 完全保留（promotion gate 通过后输出标准 Factor Draft）|

---

## §7 调节开关清单（用户拍板用）

如果用户在使用中发现某些 feature 升级太快/太慢/状态不符直觉，调节优先级：

### 7.1 第一档：调阈值（最常用，零迁移成本）

| 开关 | 默认 | 调高效果 | 调低效果 |
|---|---|---|---|
| `theta_consolidated` | 0.30 | 更难升级 consolidated | 更容易 |
| `theta_strong` | 0.60 | 更难达到 strong | 更容易 |
| `theta_forget` | 0.05 | 更快遗忘 | 更慢遗忘 |
| `disputed_counter_ratio` | 0.30 | 更难标 disputed | 更容易 |

阈值是显示层选择，调任意次都不需要重算 (α, β)。

### 7.2 第二档：调 ρ / γ / λ（影响 update，需要审慎）

| 开关 | 默认 | 调整原因 |
|---|---|---|
| `gamma`（counter 权重）| 3 | 若 DeepSeek L1 误判频繁 → 调小；若可靠 → 调大 |
| `rho_user_pick` | 0.4 | 用户挑选偏差越大 → 调小 |
| `rho_cold_start` | 0.7 | cold-start 抽样多保守 → 调小 |
| `lambda_decay` | 0.995 | 形态会过时（市场结构变） → 调小（更快遗忘） |

调整后**新事件**按新参数累积；**历史事件**已经按旧参数固化在 (α, β) 中。如要"重算历史"，从 ObservationLog 回放即可（成本：每特征 < 1 ms）。

### 7.3 第三档：开启 episode 数 gate（§6.1）

```python
config.min_episodes_for_consolidation = 2   # 默认 1，启用后需 2 次独立观察
```

这是回退到旧 brainstorming 共识的最直接开关。零迁移成本。

### 7.4 第四档：启用 p0 辅助（§2.2）

仅在用户希望"看到 LLR / PMI 显著性"时打开。需要 task #2 的 control corpus 协议（Phase 2 才能用）。

### 7.5 第五档：source-by-source γ（§6.3）

```python
config.gamma = {'deepseek_l1': 3, 'user_pick': 8, 'random': 1}
```

如果用户想"人类否决比 DeepSeek 更重"，启用 dict 形式即可。

---

## §8 关键未解问题（列给用户拍板）

### 8.1 阈值校准的 Q&A

**Q1：θ_consolidated = 0.30 是否合适？**
- 我们的依据：`5 次 K=8/N=10 累积 → P5 ≈ 0.42（在 ρ=0.7 下）`、`1 次 K=10/N=10 → P5 ≈ 0.32`
- 用户主观判断：你觉得"P5=0.30 是 consolidated"舒适吗？还是该提到 0.40？
- **建议**：先用 0.30 跑 3-6 个真实归纳轮次，看具体哪些特征升级、是否符合直觉，再决定调到 0.35 / 0.40

**Q2：γ=3 是否过严？**
- 一次 DeepSeek 否决 ≈ 3 个沉默样本
- 反例：如果 DeepSeek 经常误判 no（已知 LLM 在边缘案例上不稳定），γ=3 会过度惩罚
- **建议**：先跑一段时间，统计 DeepSeek L1 与最终人类裁决的一致率。一致率 < 80% 时考虑 γ↓2

**Q3：λ=0.995（半衰期 138 天）合理吗？**
- 美股形态学的"形态稳定性"经验数据：~6-12 个月（ETF 周期）
- λ=0.995 对应 ~4.5 个月半衰期，略偏快
- **建议**：可调整为 λ=0.997（半衰期 ~230 天）或保留 0.995 作为"积极遗忘"配置

### 8.2 多特征独立性的 Q&A

**Q4：多个 invariant 共享一个样本时，是否需要联合后验？**
- 当前设计：每个 feature 独立 (α, β)
- 风险：若两个 invariant 高度相关（如"tight range"和"low slope"），它们会共享 (K, N) → 实际是一次观察被算两次
- **建议**：先按独立处理，到 Phase 4+ 再考虑 hierarchical model（每个 invariant 上面套一个 archetype-level prior）。在 invariant <10 时独立模型够用

### 8.3 与 mining pipeline 的协同

**Q5：promotion gate 的"hold-out + permutation"放在哪一步？**
- 选项 A：Librarian 内置（每次 P5 越线就跑）
- 选项 B：单独一个 promotion-gate 步骤（用户主动触发）
- **推荐 B**：Librarian 只管累积，promotion 是独立动作。理由：permutation test 较贵，每次 update 跑会拖慢 skill；批量决定更经济

**Q6：mining pipeline 失败的 feature 如何处理？**
- 选项 A：标记 `mining_failed: true`，从 candidate pool 移除
- 选项 B：让其继续累积新证据，下次重试
- **推荐 A**：失败 = falsified，应进入"墓地"而非循环。但保留 ObservationLog 供事后审视

### 8.4 系统级问题

**Q7：当 Phase 4+ 启用 algo 路径（Apriori 等）时，新候选 invariant 如何接入 Librarian？**
- 答：与 AI 归纳同样接口，`source='apriori_mining'` 注入 InducerOutput。Librarian 不区分 invariant 来源，只看 (K, N, C)
- 这是 Beta-Binomial 的工程优势——任何"K of N 支持 + C 反对"的事件都可以无缝接入

**Q8：是否需要"feature 之间的依赖"机制（如 invariant A 推论 invariant B）？**
- 答：**不在本研究范围**。这属于 reasoning-layer 的工作，超出 Librarian 的"特征状态管理"职责
- Phase 4+ 若引入，建议用单独的 `feature_implication_graph.yaml` 而非污染 Librarian schema

---

## §9 与 philosophy_decision 共识的最终关系

`feature_mining_philosophy_decision.md` 的核心结论：
> 现有方案（`feature_mining_via_ai_design.md`）是正确的起点，只需在 L3 加三条硬防御（vocabulary 归档、hold-out、permutation test）就足以支撑 Phase 1-3 的 MVP 闭环。

**v2 决策与之的关系**：

| philosophy_decision 项 | v2 决策处理 |
|---|---|
| L1（视觉/感知层）不变 | 完全保留（图渲染 + 三段式 + 5 盘整字段） |
| L2（归纳层）不变（Phase 1-3 用 AI）| 完全保留（PartialSpec / 多轮 compact）|
| L3（验证层）三条硬防御 | 完全保留（vocabulary / hold-out / permutation） |
| **rule/hypothesis/episodes 启发式** | **本 v2 替换为 Beta-Binomial 统一刻度** |
| **batch/incremental 二分** | **本 v2 塌缩为单一 update 公式** |
| **counter 处理** | **本 v2 通过 γ 加权统一注入 β** |
| Phase 路线图 | Phase 2 增加 Librarian 实现（~2 周）|

**核心信号**：v2 不替换 philosophy_decision 的任何决策，而是**给它的"中间表征"层（介于 Inducer 与 Promotion gate 之间）提供数学骨架**。philosophy_decision 没有形式化"特征如何累积成熟"，v2 填补了这个空缺。

---

## §10 一段话最终结论

**Librarian 用 Beta-Binomial 共轭后验作为唯一统计量**：每个特征 `(α, β, t)`，`update(K, N, C, source, t) → α+=ρK, β+=ρ((N-K-C)+γC)`，信号 `S = Beta_P5(α, β)` 派生为 5 档语义带。`rule/hypothesis` 二分、`batch/incremental` 二分、`obs/episodes/counter` 多字段全部塌缩。p0 默认不参与（首选自参照判据）；如启用，按 task #2 双阶段方案（冷启动用默认表，稳态用 control corpus）。最大代价是"episode 数 gate"的隐式吸收，给出显式 `min_episodes_for_consolidation` 开关回退。最大收益是 6 路径表塌缩为 1 条 `librarian_update` 公式。工程增量 ~2 周（Librarian 模块 + skill 模板修改 + UI 状态带），与 philosophy_decision 已规划的 Phase 1-3 共识完全兼容。

---

**文档结束。**
