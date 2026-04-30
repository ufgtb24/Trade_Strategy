# 特征挖掘统一实体 Schema — Rule/Hypothesis 二分塌缩

> 研究日期：2026-04-25
> 角色：`unifier`（rule-stats-model team）
> 上游输入：
> - `docs/research/feature_mining_stats_models.md`（stats-modeler，Beta-Binomial 模型）
> - `docs/research/feature_mining_base_rate.md`（base-rate-analyst，**仅参考冷启动部分**）
> - `docs/research/feature_mining_via_ai_design.md`（既有方案）
> - `docs/research/feature_mining_philosophy_decision.md`（synth-critic 综合决策）
> 任务：把"rule / hypothesis"二分塌缩为单一实体 `observed_feature`，统一其状态、更新逻辑与 Inducer 输出契约。

---

## 0. 摘要（Executive Summary）

### 0.1 核心结论

1. **取消 rule/hypothesis 二分**：所有归纳产物都是同一种实体 `observed_feature`，状态由共轭后验 `(α, β)` 与衍生统计量驱动，无独立 hypothesis pool 与 rules library。
2. **状态语义带（status band）非门槛**：`candidate / supported / consolidated / disputed / forgotten` 仅是基于 P5 的 UI 展示分组，不参与判定、不触发状态机迁移、不改变更新动作。
3. **Inducer 单一输出契约**：无论 batch size 多少，输出 `(text, supporting_sample_ids, K, N)`；single-sample 是 N=1 的退化情形。
4. **Librarian 单一更新动作**：观察事件 → α += ρ·K, β += ρ·(N - K)；counter 事件 → β += γ·ρ。
5. **6 路径表塌缩为 3 类原子动作**：(A) create_new + apply_observation；(B) apply_decay + apply_observation；(C) apply_decay + apply_counter。
6. **诚实代价**：用户失去"hypothesis 升 rule"的离散仪式感，但获得连续刻度（P5）；旧字段中 `prompted_yes/no` 保留为辅助审计信号，不进 (α, β)。

### 0.2 一句话刻画

**所有特征都是 `observed_feature`。证据强度由 Beta(α, β) 驱动；P5 = Beta_lower_5pct(α, β) 是唯一连续刻度；状态带只是 P5 的可视分箱。Inducer 只报告事实，Librarian 只做加法。**

### 0.3 与硬约束的对齐

| 用户硬约束 | 本设计如何 honor |
|---|---|
| **无负样本** | (α, β) 只接受正向事件（K=支持）与 counter 事件（β 增量），不引入"从总体抽负样本"的 p₀ 估计 |
| **无 p₀ 估计** | P5 是后验下分位数，不与 p₀ 比较；状态带阈值（0.05/0.20/0.40）是先验直觉而非显著性 |
| **自参照累积证据** | 单个 feature 的 (α, β) 只随该 feature 自身被观察的事件累加，不和市场基线/反例池做相对比较 |

---

## §1 设计哲学澄清

### 1.1 旧方案二分在哪里破裂

既有方案（`feature_mining_via_ai_design.md`）隐含了 hypothesis/rule 二分：
- **Hypothesis 语义**：skill 单次产出的 invariant，落 PartialSpec
- **Rule 语义**：通过 `mining/` 验证后落 `factor_registry.FACTOR_REGISTRY` 的 invariant

这个二分是**仪式性**的：升级 = 跑过 mining + OOS，标志是用户跑 `add-new-factor`，无统计判据。stats-modeler §9.3 给出了 P5 ≥ 0.40 → rule 的数学化方案；但用户审稿时拒绝了基于 p₀ 的"显著性"语义、把"反例池"踢出主框架。这意味着：

- **不能把 "P5 ≥ 0.40 ⇒ rule" 写成系统门槛**——会让人误以为 P5 触线那一刻特征发生了相变
- **应当把状态完全连续化**——P5 就是一个数；UI 关心数本身，不是它落在哪个区间

### 1.2 真正的塌缩是什么

**Librarian 视角下，每个特征只是 (α, β) 一对参数 + 元数据。**

- 没有"hypothesis pool"：所有特征都在唯一 features 库里，地位平等
- 没有"升级"：α += K, β += N-K 只是普通累加，从不触发"状态变更"
- 没有"降级"：时间衰减是 lazy 的、连续的，不存在"从 rule 退回 hypothesis"的离散瞬间
- 没有"显著性 vs 基线"：P5 是自参照后验下界，"95% 把握真值不低于 P5"是它唯一语义

UI 可显示分箱（"看起来像 rule / 还在 candidate / 已 forgotten"），但这是**展示层**，不是**模型层**。

### 1.3 三条不变量

| 不变量 | 定义 | 后果 |
|---|---|---|
| **I1 — 单一实体** | 不存在 hypothesis_pool 表与 rules_library 表的分离 | 6 路径塌缩为 3 类操作 |
| **I2 — 自参照证据** | (α, β) 只由 feature 自身被观察的事件累加 | base-rate-analyst 稳态 p₀ 方案被排除 |
| **I3 — 连续刻度** | 状态由 P5 ∈ [0, 1] 单调表达 | 状态带是 P5 的展示分箱，无状态机 |

---

## §2 统一实体 Schema（YAML）

### 2.1 实体定义

```yaml
# Both "hypothesis-like" and "rule-like" features share this exact shape.
# Differences are only in the values of (α, β) and derived P5.
observed_feature:
  # --- IDENTITY ---
  id: str                       # stable hash of (text, archetype_class)
  text: str                     # natural-language statement of the feature
  archetype_class: str | null   # optional grouping tag from L1 vision pass
  embedding: list[float]        # 768/1024-dim vector for similarity / dedup

  # --- POSTERIOR STATE (the core) ---
  alpha: float                  # Beta posterior shape α; init = 0.5 (Jeffreys)
  beta: float                   # Beta posterior shape β; init = 0.5 (Jeffreys)
                                # invariant: alpha >= 0.5, beta >= 0.5 (decay floor)

  # --- AUDIT TRAILS (do not enter (α, β); kept for replay & UI) ---
  supporting_episodes: list[Episode]
  counter_episodes: list[CounterEpisode]
  prompted_yes_count: int       # auxiliary quality signal (see §7)
  prompted_no_count: int        # auxiliary quality signal (see §7)

  # --- TIMING (drives lazy decay) ---
  created_at: datetime
  last_updated_at: datetime
  last_decay_applied_at: datetime

  # --- METADATA ---
  factor_overlap: list[OverlapEntry] | null
                                # {factor_key, kind ∈ duplicate|refinement|orthogonal}
  research_status: str          # active | saturated | parked  (manual annotation only)

  # NOTE — there is NO field called:
  #   state / is_rule / is_hypothesis  — status is derived from P5
  #   significance / p_value           — no p₀ in main framework
  #   p0_estimate / n_control          — no base-rate concept
```

### 2.2 子结构

```yaml
Episode:
  event_id: str                 # ULID for replay ordering
  timestamp: datetime
  source_kind: str              # skill_dense_round | skill_label_reveal |
                                # user_attest | live_promotion | incremental_n1
  K: int                        # support count in this event
  N: int                        # batch size
  rho: float                    # sampling correction in [0, 1]
  alpha_delta: float            # = ρ·K (what entered α)
  beta_delta_silent: float      # = ρ·(N - K) (what entered β)
  sample_ids: list[str]         # the K supporting sample identifiers
  notes: str | null

CounterEpisode:
  event_id: str
  timestamp: datetime
  source_kind: str              # deepseek_l1_no | user_reject | live_failure
  rho: float
  gamma: float                  # counter weighting; default 3
  beta_delta: float             # = γ·ρ (what entered β)
  sample_id: str | null
  reason: str | null

OverlapEntry:
  factor_key: str               # one of 13 active factors in FACTOR_REGISTRY
  kind: str                     # duplicate | refinement | orthogonal
  declared_at: str              # event_id where AI declared it
```

### 2.3 字段必要性

| 字段 | 必要性 | 用途 |
|---|---|---|
| `id`, `text` | 必需 | 跨 round / skill 调用稳定标识；人读 + AI 重读 |
| `archetype_class` | 推荐 | UI 聚类；不影响 (α, β) |
| `embedding` | 必需 | similarity dedup；塌缩 6 路径表的工程基础 |
| `alpha`, `beta` | 必需 | 全部决策与 UI 展示来源 |
| `supporting_episodes`, `counter_episodes` | 必需 | 审计、replay、调试 |
| `prompted_yes/no_count` | 推荐 | UI 质量信号；不进 (α, β) |
| 三个 timestamp | 必需 | lazy decay 必需 |
| `factor_overlap` | 推荐 | 由 skill SYSTEM 条款 2 强制声明；用于 dedup |
| `research_status` | 必需 | 用户显式标 active/saturated/parked，AI 不自动设置 |

### 2.4 旧字段被吸收的路径

| 旧字段 | 新归宿 |
|---|---|
| `state` / `is_rule` / `is_hypothesis` | **删除**——状态由 P5 派生 |
| `significance_vs_p0`, `p_value`, `p0_estimate`, `n_control` | **删除**——无 p₀ 比较 |
| `independent_observations` | 吸收为 `α - α₀` |
| `episodes_count` | 吸收为 `len(supporting_episodes)` |
| `counter_observations` | 吸收为 `Σ(ce.beta_delta for ce in counter_episodes)` |
| `hypothesis_pool` / `rules_library` 表 | 合并为单一 features 表 |
| 6 状态转换 | 由 P5 连续值表达 |

---

## §3 P5：唯一连续刻度

### 3.1 主指标 — Beta P5

**P5(f) = quantile(Beta(α_f, β_f), 0.05)**

语义："给定当前累积证据，95% 把握特征 f 的真实命中率不低于 P5"。

**计算**：`scipy.stats.beta.ppf(0.05, alpha, beta)`，单样本 < 1ms，无需缓存。

**数值表**（来自 stats-modeler §2.4，Jeffreys prior α₀=β₀=0.5）：

| (α, β) | 解释 | mean | P5 |
|---|---|---|---|
| (0.5, 0.5) | 仅先验 | 0.50 | 0.025 |
| (1.5, 0.5) | 1/1 | 0.75 | 0.32 |
| (2.5, 8.5) | 2/10 | 0.23 | 0.08 |
| (5.5, 5.5) | 5/10 | 0.50 | 0.27 |
| (10.5, 0.5) | 10/10 | 0.95 | 0.83 |
| (50.5, 50.5) | 50/100 | 0.50 | 0.42 |

**为何选 P5 而不是 mean**：mean = α/(α+β) 对样本量不敏感（1/2 与 50/100 同为 0.50）；P5 同时编码"中心位置"与"证据规模"，重复观察 → P5 自然提升，无需额外 episodes 字段。

### 3.2 副指标 — posterior_mean

**posterior_mean(f) = α_f / (α_f + β_f)** ——UI tooltip 的"中心估计"，不参与判定。

### 3.3 状态语义带（UI 展示分箱）

**强调：以下分箱由 (α, β) 实时派生，不持久化、不触发动作。**

```python
def derive_status_band(feature) -> str:
    alpha, beta = feature.alpha, feature.beta
    p5 = scipy.stats.beta.ppf(0.05, alpha, beta)

    counter_beta = sum(ep.beta_delta for ep in feature.counter_episodes)
    silent_beta  = sum(ep.beta_delta_silent for ep in feature.supporting_episodes)
    counter_ratio = counter_beta / (counter_beta + silent_beta + 1e-9)

    # disputed overrides P5 if counters are loud
    if counter_ratio > 0.30 and len(feature.counter_episodes) >= 2:
        return "disputed"
    if p5 < 0.05:  return "forgotten"
    if p5 < 0.20:  return "candidate"
    if p5 < 0.40:  return "supported"     # hypothesis-level
    return "consolidated"                 # rule-level
```

### 3.4 阈值合理性讨论

#### 3.4.1 为何 consolidated 起点是 0.40 而不是 0.50

- 0.50 在直觉上对应"过半"，但要求过苛
- 5/10 累积一次后 (2.5, 2.5)，P5 ≈ 0.21 → supported
- 5/10 累积 6 次后 (12.5, 12.5)，P5 ≈ 0.40 → 进入 consolidated
- "60% 命中率重复 6 次才到 rule" 符合"高置信"直觉
- 若改用 0.50，需要 K/N 显著高于 50% 或累积更多次，过保守
- **建议保留 0.40**

#### 3.4.2 为何 supported 起点是 0.20

- 0.20 对应"约 1/5"，是"边际有效"的常见统计直觉
- 1/1（一次）→ P5 ≈ 0.32 → supported（不会一次就 consolidated，合理）
- 2/2（两次）→ P5 ≈ 0.55 → consolidated（2/2 极强，合理）
- 0.20 与 0.05 间距给"弱信号"留观察空间
- **建议保留 0.20**

#### 3.4.3 为何 forgotten 是 0.05 而不是 0.10

- 0.05 与 P5 的"95% 后验下界"语义自洽
- 0.5/9.5（仅先验后 9 沉默）→ P5 ≈ 0.005 → forgotten
- **建议保留 0.05**

#### 3.4.4 disputed 阈值（counter_ratio > 0.30）

- counter 已 γ=3 加权，0.30 ratio ≈ counter 数量占总反对样本数 ≈ 12%
- 增加 `len(counter_episodes) >= 2` 硬约束，避免单个孤立 counter 把 candidate 错标 disputed
- disputed 只是 UI 警告标签，不阻止 (α, β) 继续更新
- **建议保留 0.30 + 最小 2 counter**

### 3.5 阈值可调

阈值放在 `configs/feature_mining.yaml`，不写死代码。所有数值均为先验直觉，应在使用 3-6 个月后基于真实数据校准。

---

## §4 Inducer 的统一输出契约

### 4.1 单一 schema

```yaml
inducer_output:
  text: str                     # natural-language statement
  supporting_sample_ids: list[str]
  K: int                        # = len(supporting_sample_ids)
  N: int                        # batch size; in single-sample mode N=1, K∈{0,1}
  archetype_class: str | null
  factor_overlap_declared: list[OverlapEntry]  # required by skill SYSTEM rule 2
  source_kind: str              # passed through to Episode.source_kind
  rho_recommended: float | null # inducer may recommend ρ; final decided by Librarian
```

**Inducer 不分类、不判定、不打标签——它只报告事实**："在这 N 个样本中有 K 个满足以下文本陈述。"

### 4.2 三种典型情形

| 情形 | N | K | source_kind |
|---|---|---|---|
| Skill dense round | 12 | 9 | `skill_dense_round` |
| Skill label-reveal phase-2 | 12 | 7 | `skill_label_reveal` |
| Single-sample（live UI 钉选）| 1 | 1 | `live_promotion` |

**关键性质**：single-sample 不是独立模式，只是 N=1 的退化情形。Librarian 用同一公式处理所有情形，无 `if N == 1: ...` 分支。

### 4.3 与既有 PartialSpec 的对接

旧 PartialSpec 中 `clusters[].invariants[]` 每条展开为一个 `inducer_output`：

```yaml
# 旧（既有方案 §3.3）
invariants:
  - statement: "contraction ratio decreases monotonically over last 3 sub-ranges"
    evidence_receipts: [S001:0.92, S003:0.87, S007:0.95]

# 新
inducer_outputs:
  - text: "contraction ratio decreases monotonically over last 3 sub-ranges"
    supporting_sample_ids: [S001, S003, S007]
    K: 3
    N: 12
    source_kind: "skill_dense_round"
    rho_recommended: 0.4
```

**变化点**：
- `evidence_receipts` 中的 confidence score（0.92 等）**不再使用**——AI 自报置信度与 (α, β) 无对接
- `K, N` 显式化，不依赖 `len(sample_refs)` 推断
- `factor_overlap_declared` 从 invariant 内移到顶层

---

## §5 Librarian 的统一更新逻辑

### 5.1 三类原子动作

```python
class Librarian:
    def upsert_feature_from_observation(self, output, now) -> Feature:
        """Single entry point for positive observations.
        1. Find existing feature matching `output.text` (embedding cosine).
           - If match: apply update to that feature.
           - If no match: create new feature, then apply update.
        2. Apply lazy decay up to `now`.
        3. Apply observation: α += ρ·K, β += ρ·(N-K).
        4. Append Episode; update timestamps.
        """

    def record_counter_event(self, feature_id, sample_id, rho, now) -> Feature:
        """1. Apply lazy decay.
           2. β += γ·ρ.
           3. Append CounterEpisode; update timestamps.
        """

    def get_feature(self, feature_id, now) -> Feature:
        """Read with lazy decay applied."""
```

**没有第四个动作**。`promote_to_rule` / `demote_to_hypothesis` / `archive_as_forgotten` 都是 P5 的派生展示，不是数据库动作。

### 5.2 完整公式

```python
# Lazy time decay — multiplicative, floored at prior
def apply_decay(f, now, lambda_daily=0.995):
    days = (now - f.last_decay_applied_at).days
    if days <= 0: return  # idempotent
    decay = lambda_daily ** days
    f.alpha = max(0.5, f.alpha * decay)
    f.beta  = max(0.5, f.beta  * decay)
    f.last_decay_applied_at = now

# Positive observation update — single formula for batch & incremental
def apply_observation(f, output, rho, now):
    K, N = output.K, output.N
    f.alpha += rho * K
    f.beta  += rho * (N - K)
    f.supporting_episodes.append(Episode(
        event_id=ulid(), timestamp=now,
        source_kind=output.source_kind,
        K=K, N=N, rho=rho,
        alpha_delta=rho * K,
        beta_delta_silent=rho * (N - K),
        sample_ids=output.supporting_sample_ids,
    ))
    f.last_updated_at = now

# Counter event — always single sample, weighted β increment
def apply_counter(f, sample_id, rho, gamma, now):
    f.beta += gamma * rho
    f.counter_episodes.append(CounterEpisode(
        event_id=ulid(), timestamp=now,
        rho=rho, gamma=gamma,
        beta_delta=gamma * rho,
        sample_id=sample_id,
    ))
    f.last_updated_at = now
```

**统一 batch / incremental**：
- Batch（N=12, K=9, ρ=0.4）：α += 3.6, β += 1.2
- Single-sample（N=1, K=1, ρ=0.5）：α += 0.5, β += 0
- 单一公式，无分支

### 5.3 Match existing vs Create new

```python
def find_or_create(self, output) -> Feature:
    embedding = embed(output.text)
    candidates = self.find_similar(embedding, threshold=0.85)
    if not candidates:
        return self.create_new(output, embedding)
    # Tie-break by archetype_class match, then recency
    return max(candidates, key=lambda f: (
        int(f.archetype_class == output.archetype_class),
        f.last_updated_at,
    ))
```

**dedup 阈值 0.85** 是经验值。过松 → 不同概念被合并；过严 → 同义表述被拆。需在使用中校准（§10）。

### 5.4 端到端例子

```python
# Round 1: dense batch, 12 user-curated, K=9
output_1 = InducerOutput(
    text="consolidation_range_width <= 15% AND vol_ratio_breakout >= 2.0",
    supporting_sample_ids=["S001", ..., "S009"],
    K=9, N=12, source_kind="skill_dense_round", rho_recommended=0.4,
)
f = librarian.upsert_feature_from_observation(output_1, now=t1)
# create new (no match) → init (0.5, 0.5)
# update: α = 0.5 + 0.4·9 = 4.1; β = 0.5 + 0.4·3 = 1.7
# P5 ≈ 0.45 → consolidated band

# Round 2, 30 days later: K=10, N=12
f = librarian.upsert_feature_from_observation(output_2, now=t1 + 30days)
# decay λ^30 ≈ 0.860 → (3.526, 1.462)
# update → (7.526, 2.262)
# P5 ≈ 0.50 → still consolidated

# Counter event 5 days later
librarian.record_counter_event(f.id, "LIVE-...", rho=0.5, now=t2 + 5days)
# decay λ^5 ≈ 0.975 → (7.34, 2.21)
# counter: β += 1.5 → β = 3.71
# P5 ≈ 0.42 → still consolidated, UI shows "1 counter recorded"
```

UI 在每次读时自动显示更新的 P5 与状态带——无任何状态机迁移代码。

---

## §6 6 路径表的塌缩

### 6.1 旧 6 路径回顾

| # | Source | Target | 旧动作 |
|---|---|---|---|
| 1 | New skill output | Hypothesis pool | 创建 hypothesis |
| 2 | Existing hypothesis | Hypothesis pool | 累加 obs |
| 3 | Existing hypothesis | Rules library | 升级（满足阈值）|
| 4 | New skill output | Rules library | （罕见）直接创建 rule |
| 5 | Existing rule | Rules library | 累加 obs |
| 6 | Existing rule | Hypothesis pool | 降级（衰减触发）|

### 6.2 塌缩后的 3 类动作

**source 决定动作类型，target 永远是同一张 features 表：**

| # | 触发条件 | 动作 | (α, β) 变化 |
|---|---|---|---|
| **A** | embedding 不匹配既有 feature | `create_new + apply_observation` | 从 (0.5, 0.5) 起，α += ρK, β += ρ(N-K) |
| **B** | embedding 匹配既有 + 正向事件 | `apply_decay + apply_observation` | α += ρK, β += ρ(N-K) |
| **C** | 任意 feature + counter 事件 | `apply_decay + apply_counter` | β += γρ |

**6 → 3 映射**：

| 旧路径 | 新动作 | 备注 |
|---|---|---|
| 1 | A | 新 feature 入表 |
| 2 | B | 累加，无状态变更 |
| 3 | B（**无升级动作**）| P5 跨 0.40，UI 自动显 consolidated；DB 无变更 |
| 4 | A（**无 rule 标签**）| 同 1 |
| 5 | B | 同 2 |
| 6 | （仅 decay，**无独立动作**）| 衰减 lazy，读时计算；无显式降级写入 |

### 6.3 简化收益

旧设计：`hypothesis_pool` + `rules_library` 双表 + `Promote` / `Demote` 状态机 + 引用更新——约 800-1200 行。

新设计：`features` 单表 + `apply_observation` / `apply_counter` / 隐式 `apply_decay`——约 200-300 行。

---

## §7 兼容性映射：旧字段 → 新字段

### 7.1 完整映射表

| 旧字段 | 新位置 | 关系 | 备注 |
|---|---|---|---|
| `independent_observations` | `α - α₀` | 吸收 | 旧字段未对沉默样本计入；新字段同时记录 K 与 N-K |
| `episodes_count` | `len(supporting_episodes)` | 吸收 | 不再独立计数器，从 audit trail 派生 |
| `counter_observations` | β 中由 counter 贡献的部分 | 吸收 | = Σ(ce.beta_delta) |
| `prompted_yes` | `prompted_yes_count`（保留）| 保留为辅助 | 不进 (α, β)；UI 显示 |
| `prompted_no` | `prompted_no_count` + 触发 counter | 保留+触发 | 同时增加计数 + 调用 counter 路径 |
| `state` / `is_rule` / `is_hypothesis` | 删除 | 由 P5 派生 | UI 实时计算 |
| `hypothesis_pool` / `rules_library` 表 | 合并 | 单一 features 表 | |
| 6 状态转换 | 删除 | 由 P5 连续值表达 | UI 状态带是只读派生 |
| `significance_vs_p0`, `p0_estimate`, `n_control`, `control_corpus_id` | 删除 | 主路径无 p₀ | |
| `confidence_interval` | (P5, P95) 派生 | 吸收 | UI 可显；不持久化 |

### 7.2 prompted_yes/no 的特殊处理

- `prompted_yes`：用户/AI 主动提示某 feature 在某样本上"应当满足"，AI 同意——质量信号，不进 (α, β)
- `prompted_no`：同上反向——**唯一与 (α, β) 的耦合点**：prompted_no 事件**同时**：
  1. 增加 `prompted_no_count` 计数
  2. 调用 counter 路径，β += γρ

避免"prompted_no 不影响后验"的反直觉。

### 7.3 数学等价检查

旧体系判定 "rule" 的伪规则：`independent_observations >= 2 AND episodes >= 2`。新体系下等价的 (α, β)：

| 旧判据 | (α, β) 估计 | P5 | 新状态带 |
|---|---|---|---|
| 2 obs, 2 ep, 平均 N=5 | (1.3, 2.9) | 0.05 | candidate |
| 5 obs, 5 ep, 平均 N=10 | (2.5, 5.5) | 0.13 | candidate |
| 10 obs, 5 ep, 平均 N=10 | (4.5, 4.5) | 0.21 | supported |
| 50 obs, 10 ep, 平均 N=10 | (20.5, 20.5) | 0.39 | supported（接近 consolidated）|

**观察**：旧体系 "obs >= 2 AND episodes >= 2" 在新体系下大多对应 candidate / supported，**不会立刻成为 consolidated**。这反映了对低 K/N 样本的天然惩罚，符合用户最初的痛点诊断。

---

## §8 诚实评估：什么被吞掉了？

### 8.1 离散仪式感的丧失

**旧体系**：用户跑 `add-new-factor` → hypothesis 升 rule → 写入 `factor_registry.FACTOR_REGISTRY`。**离散的、有仪式感的**事件。

**新体系**：升级是连续的——P5 跨过 0.40 没有任何"事件"，只是某次读时 status_band 变了。

**这是表达力的下降**：
- 用户失去"庆祝瞬间"
- 调试时难以问"特征 F 在哪一刻升 rule"

**缓解**：在 audit trail 中持久化"P5 跨阈值的瞬间"作为派生事件：

```yaml
threshold_crossings: list[ThresholdCrossing]
ThresholdCrossing:
  event_id: str
  timestamp: datetime
  band_from: str          # "supported"
  band_to: str            # "consolidated"
  trigger_episode_id: str
```

派生记录，不影响决策；保留"特征第一次进 consolidated"的仪式感与可调试性。

### 8.2 "rule" 与 `factor_registry` 的脱钩

**旧体系**：rule 落地物理标志 = 写入 `FACTOR_REGISTRY` + 跑 `add-new-factor`。

**新体系**：features 表与 `FACTOR_REGISTRY` 保持解耦——features 是 AI 归纳的统计累积，FACTOR_REGISTRY 是"已工程化、被 mining/live 使用"的因子。两者通过用户显式动作连接：

- 用户在 UI 看到某 feature 进入 consolidated → 决定"值得做成因子"
- 跑 `add-new-factor` → mining 验证 → 落 FACTOR_REGISTRY

**这个"用户拍板"环节是有意保留的**——philosophy_decision §5.3 已强调"系统级学习收敛由人拍板"。

### 8.3 UI 上的可见性

**用户能否清楚知道"这条 feature 现在算什么级别"？**

- ✅ 可以：UI 显示 status_band + P5 + (α, β) + episodes 数 + counters 数
- ✅ 可以：UI 显示 P5 时间序列图（看到何时跨阈值）
- ⚠ 不能：UI 不显示"这是 hypothesis 还是 rule"——因为这个二元不存在了

**判断**：表达力下降存在，但不致命。consolidated/supported 直接代表了 rule/hypothesis 的语义。

### 8.4 调试与归因

**旧**：bug 时可问"为什么这个 feature 是 rule"——查 promote 事件即可。
**新**：必须问"为什么 P5 = 0.42"——回放 supporting_episodes + counter_episodes 重算。

**缓解**：audit trail 完整保留所有 episodes，回放成本 O(num_episodes)，对单 feature 通常 < 100。提供 `librarian.replay(feature_id)` 工具，逐事件输出 (α, β, P5) 序列。

### 8.5 必须保留的审计字段

| 字段 | 必要性 | 为何 |
|---|---|---|
| `supporting_episodes` (完整列表) | 必需 | 重放、调试、用户审查 |
| `counter_episodes` (完整列表) | 必需 | 同上 |
| `prompted_yes_count` / `prompted_no_count` | 必需 | UI 质量信号 |
| `factor_overlap` | 必需 | skill SYSTEM 条款执行轨迹 |
| 三个 timestamp | 必需 | decay 计算 + 审计 |
| `threshold_crossings` (派生) | 推荐 | 保留 §8.1 仪式感 |
| `embedding`, `archetype_class`, `research_status` | 必需 | dedup / UI 聚类 / 用户拍板 |

按需计算（不持久化）：`P5`, `posterior_mean`, `status_band`, `confidence_interval`——全部从 (α, β) 派生。

---

## §9 与 philosophy-decision 的兼容性

### 9.1 三层架构对照

philosophy_decision §2 的 L1（视觉）/ L2（归纳）/ L3（验证）：

| Layer | 与本设计的关系 |
|---|---|
| L1 | `archetype_class` 字段是 L1 输出；不影响 (α, β) |
| **L2** | **(α, β) 累积统计量；本 schema 主要服务于 L2** |
| L3 | Factor Draft → mining/ + hold-out + permutation；与 features 表解耦 |

### 9.2 与三条硬修正的对接

philosophy_decision §4.3 提出的硬修正：

| 硬修正 | 与本 schema 关系 |
|---|---|
| 1. vocabulary_draft.md 归档 | 解耦；archetype_class + invariant text 自动作为 vocabulary 来源 |
| 2. L3 hold-out 协议 | 在 features → Factor Draft → mining 之间，**不影响 features 表本身** |
| 3. L3 permutation test | 同上；audit trail 完整使 permutation 实施更容易（直接拿 supporting_episodes 重放）|

### 9.3 与 Phase 路线图

| Phase | 现有任务 | 本 schema 增量 |
|---|---|---|
| Phase 1 | corpus exporter + vocabulary 归档 | features 表初始化、空状态 |
| Phase 2 | skill end-to-end (text_only) | Inducer → Librarian 接入；apply_observation 实现 |
| Phase 3 | hybrid_light + permutation test | Counter 事件接入（DeepSeek L1）|
| Phase 4+ | algo / intel 路径 | features 表是两条路径共同载体（algo 加 primitives，intel 加 archetypes，都落 features 表）|

---

## §10 边界场景与失败模式

### 10.1 Embedding 误匹配

**风险**：语义不同但表面相似的 invariant 被合并：
- "consolidation_range_width <= 15%"
- "consolidation_range_width <= 25%"

**缓解**：
- dedup 同时检查 `factor_overlap_declared` 一致
- UI "split this feature" 按钮，让用户手动拆分
- 新增字段 `text_canonical`：AI 抽取的结构化条件（如 `{condition: "lte", attribute: "range_width", threshold: 0.15}`）；canonical 不一致时不合并

### 10.2 Embedding 漏匹配

**风险**：同一 invariant 不同表述被拆成多 entry。

**缓解**：
- skill 内强制英文标准化输出（SYSTEM rule）
- `librarian.dedup_pass()` 周期性扫描 cosine sim > 0.95 的 pair，提示用户合并

### 10.3 抽样偏差累加

**风险**：用户连续多次挑同类样本，(α, β) 持续增长，P5 错误升至 consolidated。

**缓解**：
- ρ_user = 0.4 已部分缓解
- philosophy_decision §4.3 hold-out 协议是最终防线：哪怕 P5 = 0.50，hold-out 上 Spearman 不一致 → Factor Draft 落不下去
- features 表本身不解决此问题——它只诚实记录"在用户挑选过的样本里 P5 = X"。下游决策由 mining/ + hold-out 兜底

### 10.4 forgotten feature 永远不消失

**风险**：lazy decay 不归零（floor 在 0.5）→ 长期不被观察的 feature 占据 UI 空间。

**缓解**：
- UI 默认隐藏 forgotten 状态带
- `librarian.archive(feature_id)` 把 forgotten 移到 archived 表（不删，可恢复）
- archived 不参与 dedup 匹配，新 feature 可重新创建

---

## §11 配置默认值汇总

```yaml
# configs/feature_mining.yaml
posterior_init:
  alpha_0: 0.5             # Jeffreys prior
  beta_0: 0.5

decay:
  daily_lambda: 0.995      # half-life ≈ 138 days
  floor_alpha: 0.5
  floor_beta: 0.5

counter:
  gamma: 3.0               # counter = 3 silent samples

sampling_rho:
  user_curated: 0.4
  cold_start: 0.7
  random: 1.0
  live_promotion: 0.5
  skill_label_reveal: 0.5

dedup:
  embedding_cosine_threshold: 0.85
  archetype_match_required: false

status_band:
  forgotten_max: 0.05
  candidate_max: 0.20
  supported_max: 0.40
  disputed_counter_ratio: 0.30
  disputed_min_counter_episodes: 2

features_table:
  archive_threshold_p5: 0.02
  archive_inactivity_days: 180
```

**所有默认值均为先验直觉，应在使用 3-6 个月后基于真实数据校准。**

---

## §12 落地 checklist

### Phase 1（与现有 §7.1 P0 兼容）

- [ ] 实现 `Feature` / `Episode` / `CounterEpisode` dataclass（YAML schema → Pydantic）
- [ ] 实现 `Librarian.upsert_feature_from_observation()` / `record_counter_event()` / `get_feature()`
- [ ] 实现 `derive_status_band()`（纯函数，依赖 (α, β)）
- [ ] 实现 features 表持久化（YAML / SQLite，按用户偏好）
- [ ] 单元测试：§5.4 端到端例子的数值精确匹配

### Phase 2

- [ ] Inducer 输出 schema 接入（skill 产出 → InducerOutput）
- [ ] Embedding 计算与 dedup
- [ ] UI：features list view（带 P5 + status_band + 历史 episode 时间线）
- [ ] `librarian.replay(feature_id)` 调试工具

### Phase 3

- [ ] DeepSeek L1 → counter event 接入
- [ ] threshold_crossings 派生事件落 audit
- [ ] features `dedup_pass` 扫描器（每周）

### 不做（明确排除）

- **不做** rule/hypothesis 双表
- **不做** promote/demote 状态机
- **不做** p₀ 估计 / control corpus / 反例池作为 features 表的一部分
- **不做** 自动 `add-new-factor`——P5 ≥ 0.40 只是 UI 提示

---

## §13 关键术语速查

| 术语 | 含义 |
|---|---|
| `observed_feature` / `feature` | 统一实体；同时承担 hypothesis 与 rule 语义 |
| `(α, β)` | Beta 后验参数；唯一驱动状态的存量 |
| **P5** | `Beta_lower_5pct(α, β)`；唯一连续刻度 |
| **Status band** | UI 展示分箱（candidate/supported/consolidated/disputed/forgotten）；非门槛 |
| **Episode** | 一次正向观察事件的审计记录；不可删除 |
| **CounterEpisode** | 一次硬反对事件的审计记录 |
| **Inducer output** | 单一 schema (text, sample_ids, K, N, ...)；无 batch/single 分模式 |
| **3 类原子动作** | A: create_new + apply_observation；B: apply_decay + apply_observation；C: apply_decay + apply_counter |
| **Lazy decay** | 读/写时按 elapsed days 一次性折算 (α, β)，floor 在 prior |
| **Self-referential** | (α, β) 只随 feature 自身被观察的事件累加，不与其他 feature / 总体比较 |

---

## §14 一句话总结

**所有归纳产物都是同一种实体 `observed_feature`，状态由共轭后验 (α, β) 与衍生 P5 = Beta_lower_5pct(α, β) 唯一驱动。Inducer 不分类，只报告 (text, sample_ids, K, N)；Librarian 不分门槛，只做 α += ρK / β += ρ(N-K) 与 counter β += γρ 三类加法；状态语义带是 P5 的 UI 展示分箱，不参与判定。旧 6 路径塌缩为 3 类原子动作；旧字段被 (α, β) 完全吸收；旧二分（hypothesis pool / rules library）合并为单一 features 表。代价：用户失去"hypothesis 升 rule"的离散瞬间，获得连续刻度 + 极简代码 + 完整审计。**

---

**文档结束。**
