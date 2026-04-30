# Feature Induction Workflow — Detailed Design (Annex)

> 生成日期：2026-04-23
> 范围：`BreakoutStrategy/dev/`、`BreakoutStrategy/factor_registry.py`、`.claude/skills/add-new-factor/SKILL.md`、`BreakoutStrategy/mining/pipeline.py`
> 角色：`docs/research/feature_mining_via_ai_design.md` 的详细附件。总终稿负责可行性结论、三方案总览、推荐、工程 checklist；本文负责 workflow 语义（sample 曲线、多轮 compact 协议、PartialSpec schema、skill 编排、落地接力链）。
>
> 上游产物：
> - kline-encoding-expert 的结构化编码方案（Scheme B 三段式；dense / medium / sparse 各档位精简，详见 §3.1；Review 后移除了原 Zig-Zag symbolic_sequence）
> - vision-input-expert 的图像渲染方案（2560×1440 PNG + 白名单标注）
>
> 下游接入：
> - `.claude/skills/add-new-factor/SKILL.md` 的 3 文件 checklist
> - `BreakoutStrategy/mining/pipeline.py` 的 Spearman 方向诊断 → TPE 阈值优化 → 5 维 OOS 验证

---

## 1. 样本曲线（Sample Curation）

### 1.1 主路径：用户在 dev UI 里挑选

工程细节（"本研究落地所需的代码工作"）在总终稿的 engineering checklist 里展开；此处只锁 workflow 语义：

- `P`/`N` 键盘钩子挂在 `BreakoutStrategy/dev/main.py` 的 `HoverState` 上：用户悬停某 BO 标记时按键，将当前 BO 追加写入 `corpus/<run_name>/positive.jsonl` 或 `negative.jsonl`。
- 每条记录的最小 schema：

```json
{"ticker": "AAPL", "bo_date": "2024-03-15", "bo_index": 142, "label_value": 0.23, "user_note": "textbook VCP, 3 contractions"}
```

- `user_note` 是可选但强烈建议的字段：用户选择样本的"理由文字"是高信号，归纳过程会把它作为 hint 喂给模型（见 §2.4）。
- 目标体量：**正例 30–60 / 反例 20–40**。反例需要 *matched*（同规模/同价区/同 volatility profile），不是随机失败样本。

### 1.2 冷启动回退：没有用户曲线时

冷启动方案最容易犯的错是用 `label_low` 做反例——会让 workflow 退化成"重新发明 label"。正确构造：

| 池 | 定义 | 用途 |
|---|---|---|
| 正例池 | `label_5_20` top quartile，**且用户至少 spot-check 过 5 个**（attestation gate） | 归纳 invariants |
| 主反例池 | `label_5_20` top quartile \ 正例池 | 形态判别性反例（高 label 但形态用户没确认好） |
| 次反例池（可选） | `label_5_20` middle quartile | mediocre form baseline，检测 invariants 的泛化性 |
| **禁用** | `label_5_20` bottom quartile | 这是"任何 BO 都会失败的原因"信号，属 mining pipeline 方向诊断的职责，不归本 workflow |

**Attestation gate**：skill 在冷启动路径下拒绝开始，直到用户在 UI 里确认 ≥5 个正例确实显示意图形态。这一步不是摆设——冷启动样本的质量决定整轮归纳的天花板。

这个设计强制 compact loop 产出 **form-level 判别性**（正例 vs 反例都是高 label），而不是滑回"label 预测器"。

---

## 2. 多轮 Dense → Sparse Compact 协议

### 2.1 每轮 prompt 形状

```
Input  = SYSTEM_PROMPT
       + PartialSpec_{k-1}              # 若 k>1
       + BATCH_k(positives)
       + NEG_BATCH_k(matched)
       + [overview images if spatial round]

Output = PartialSpec_k                   # 结构化 YAML，无散文
```

Dense 样本跨轮丢弃；只 PartialSpec 携带向前。最后一轮是 self-consistency spot-check：从前几轮抽 3–5 个样本，用当前 invariants 重新分类；错配 ≥20% 触发一轮额外精化。

### 2.2 输入模式与每轮容量

| mode | 样本数/轮 | 每轮输入 token | 使用阶段 |
|---|---|---|---|
| **hybrid**（默认） | 15（8+ / 7−） | ~100–110k | 归纳主循环，rounds 1..k-1 |
| **hybrid + overview** | 10（5+ / 5−） | ~105k | 仅当 `open_questions` 涉及空间位置（"底部 vs 高位"）时打开 |
| **structured-dense** | 20–30 | ~20–25k | 纯结构化归纳（非视觉依赖任务） |
| **structured-medium** | 30–50 | ~12–20k | 中段精化，降采样掉 trajectory 保留因子分组 |
| **structured-sparse** | 80–150 | ~16–30k | 晚段 compact、spot-check、split_required 聚类侦察 |
| **post-hoc forensics** | 10（`post_bars=20`） | ~15k | **OUT-OF-LOOP** 归纳冻结后的验证 |

注意 mode ↔ schema 的硬绑定：
- `dense` → 完整三段式（one_line_tag 含 traj + consolidation + factors + trajectory_ds8）
- `medium` → 去 trajectory_ds8，保留 one_line_tag + consolidation + factors(grouped)
- `sparse` → **自动降级**：Seg 1 one_line_tag（含 `traj=` 自然语言轨迹标签）+ factor_levels 档位

这个绑定要进 adapter 里做断言，禁止调用方随意混搭。

### 2.3 图像与结构化的配对规则

从 vision-input-expert 的合同里硬落几条：

1. 图像**永不独行**。任何归纳轮次里，image 必与 structured（最低 medium 层）配对。理由：AI 从图像上读数值极不可靠，图只负责定性形态。
2. 消息组装走 **image-before-text 对比配对**：

```
[TEXT: 批次指令]
[IMG: BO#1 pos][TEXT: BO#1 structured]
[IMG: BO#2 neg][TEXT: BO#2 structured]
[IMG: BO#3 pos][TEXT: BO#3 structured]
...
[TEXT: "propose/refine PartialSpec"]
```

3. 图上标注白名单（**不经专家签字禁改**）：K 线 + 成交量子图 + 盘整矩形框（α 0.12）+ 阻力水平线（orange dashed）+ BO 红色 ▲ + 峰值黑色 ▼。禁止出现：MA 均线、网格、日期标签、ticker、label 值、peak/bo ID、tooltip。

### 2.4 SYSTEM prompt 强制条款（每轮必带）

这些条款是防止 AI 产出"听着有道理但不落地"的护栏：

1. **对比条款**：*"对每个 invariant，陈述它如何将正例与反例区分开。若无法区分，丢弃。"*
2. **重叠检查条款**：*"对每个 invariant，声明其与 13 个现有活跃因子的关系——`duplicate` / `refinement` / `orthogonal`。duplicate 必须丢弃，除非 refinement 足够具体且可辩护。"* 上下文附带现有因子列表（key + cn_name + unit + category）。
3. **schema 强制条款**：*"仅输出有效 PartialSpec YAML。schema 之外的散文会被丢弃。"*

注：prompt 模板本体（SYSTEM 骨架 + 每轮 USER 骨架 + "levels 破笼"条款 + "两段式 label 揭示"协议）由 kline-encoding-expert 单独供稿，落地时直接嵌入本节，不在此自造轮子。

### 2.5 PartialSpec schema（结构化 YAML，抗漂移）

```yaml
version: k                                    # 轮次计数
clusters:                                     # 正例原型，≤ 4
  - name: "VCP-style contraction"
    confidence: 0.7                           # 当前证据下的坚定程度
    invariants:
      - statement: "contraction ratio decreases monotonically across ≥3 pullbacks"
        overlap_with_existing: []             # 空 = 正交（理想）
        overlap_kind: null                    # 'duplicate' | 'refinement' | 'orthogonal' | null
      - statement: "volume dries up (<50% of 20d avg) in final contraction"
        overlap_with_existing: ['pre_vol']
        overlap_kind: 'refinement'            # 用"单调下降"精化了 pre_vol
    weak_signals:                             # 部分样本出现，非全部
      - "optional gap up on breakout day"
    counter_evidence: []                      # 违反 invariant 的样本（附 ticker_date）
    sample_refs: [AAPL_2024-03-15, NVDA_2023-11-02, ...]    # 廉价指针，非完整数据

distinguishing_vs_negative:                   # 与反例的判别要点（跨 cluster）
  - "negatives lack the volume dry-up phase"
  - "negatives show upper-shadow clustering in final 5 bars"

open_questions:                               # active learning 信号
  - "is rel-vol floor ≤0.5x required or 0.7x sufficient?"
  - "does contraction count need to be ≥3 strict, or ≥2 with extreme final contraction?"

coverage_stats:
  samples_seen_positive: 24
  samples_seen_negative: 12
  samples_unclassified: 3                     # 模型拒绝归类的样本
```

**抗遗忘机制**：
- `invariants` + `counter_evidence` 是 *evidence receipts*。新一轮只能通过向 `counter_evidence` 追加反例来撤销 invariant，**不能**静默地重新发现已建立的 invariant。
- `sample_refs` 保留 `ticker+date` 指针，不嵌入数据本身；后续轮次可以廉价引用。
- `open_questions` 是**主动学习指令**，引导下一批样本的注意力焦点。

**早停条件**：连续 2 轮 invariant 无变化 **且** 无新 open_questions 被提出。

### 2.6 Cluster 硬上限：4 个 + 形式化 split

当模型想提第 5 个 cluster 时，改输出 split 请求：

```yaml
split_required: true
reason: "5th cluster attempted; corpus heterogeneity exceeds single-run capacity."
suggested_splits:
  - sub_run_name: "low_price_basing"
    rationale: "price < $20 samples show faster volatility regime"
    positive_refs: [TICK1_DATE, TICK2_DATE, ...]
    negative_refs: [TICKN_DATE, ...]
  - sub_run_name: "growth_vcp"
    rationale: "high-beta samples with contraction ratio < 0.4 per pullback"
    positive_refs: [...]
    negative_refs: [...]
```

用户保存每个 sub-run manifest 后对 skill 分别重新调用。不允许自由散文 "please split"——用户要能点一下就分叉。

---

## 3. Adapter Contracts

### 3.1 结构化 adapter

实现在 `BreakoutStrategy/analysis/llm_encoding.py`（工程落地点在总终稿 checklist）：

```python
encode_samples(
    corpus_refs: list[dict],                  # [{ticker, bo_date, bo_index, user_note?}]
    mode: Literal['dense', 'medium', 'sparse'],
    traj_points: int = 9,                     # 9 | 12 | 15；dense/medium 适用，sparse 忽略
    post_bars: int = 0,                       # 归纳强制 0；forensics 才允许 20
    include_cn_unit: bool = True,             # factors{} 是否带中文+单位（sparse 强制 False）
) -> list[dict]                               # ready-to-serialize 样本 JSON 列表
```

**模式绑定**（断言，不依赖调用方自觉）：

| mode | 输出段 | 约 token/样本 |
|---|---|---|
| `dense` | one_line_tag(含 traj) + bo + peaks + consolidation + factors(grouped) + trajectory_ds8 + volume_ds8 + label | ~620 |
| `medium` | one_line_tag(含 traj) + bo + peaks + consolidation + factors(grouped) | ~380 |
| `sparse` | one_line_tag(含 traj) + factor_levels 档位 | ~200 |

**硬断言**：归纳主循环（rounds 1..k-1）里 `post_bars != 0` 直接抛异常。仅在 `forensics` 阶段（PartialSpec 已冻结）才能通过显式 flag 放行。

### 3.2 视觉 adapter

实现在 `BreakoutStrategy/research/ai_vision_render.py`：

```python
render_bo_for_ai(
    bo: Breakout,
    df: pd.DataFrame,
    mode: Literal['detail', 'overview'],
) -> bytes                                    # PNG
```

- `detail`：180–240 根 K 线覆盖盘整+突破，~4500 token（Opus 4.7 native 2560×1440）。
- `overview`：500 根 K 线，用于底部/高位空间定位，仅当 `open_questions` 明确要求时打开。
- 其他模型（Sonnet/Haiku）用长边 1568px 版本，~1568 token；切换由 skill 的 model routing 决定。

### 3.3 Adapter 使用不变量

1. Hybrid 模式下 image 与 structured 必须成对出现（1:1 映射 `corpus_refs[i]`）。
2. Structured-only 模式允许独立使用 `encode_samples`。
3. Image-only 模式**禁用**（违反 vision-input-expert 合同）。

---

## 4. 两层输出（Two-Layer Output）

### 4.1 Layer A — Feature Spec（自然语言，面向人）

位置：`docs/research/feature_library/<form_name>.md`

小节：
1. **Intuition** — 为什么这种形态值得存在为一个因子
2. **Invariants** — 从 PartialSpec 提炼的定义性条件
3. **Measurement Hint** — 如何从 K 线数据里量化（不是最终代码，只是方向）
4. **Known Edge Cases** — 哪些样本是反例，为什么反例不符合
5. **Confidence** — 基于样本数 + spot-check pass rate 的置信度
6. **Source Corpus Ref** — 来源 corpus 路径 + 轮次数
7. **Signal Novelty** — "newly-added signal" vs "restatement of known signal"，从所有 invariants 的 `overlap_kind` 频次汇总出来（若 refinement 占多数，总结为"对 pre_vol 的结构性精化"；若 orthogonal 占多数，总结为"正交新信号"；若 duplicate 占多数，整个 Feature Spec 应该被打回重做）

### 4.2 Layer B — Factor Draft（严格 8 字段）

这是 `add-new-factor` skill 的输入契约。**skill 会 reject 任何缺字段的 draft**，不允许 AI 临场发挥字段名：

```yaml
factor_draft:
  key: contraction_monotonic              # lowercase_with_underscore
  name: "Contraction Monotonicity"        # English
  cn_name: "盘整收缩单调性"                 # 中文
  category: context                       # 'resistance' | 'breakout' | 'context'
  default_thresholds: [0.5, 0.7, 0.9]     # 递增元组
  default_values: [1.1, 1.25, 1.4]        # 奖励/惩罚乘数
  mining_mode: gte                        # 'gte' | 'lte' | None
  nullable: true                          # effective_buffer > 0 时必须 true
  effective_buffer_hint: 60               # 所需历史 bar 数；add-new-factor 会在 _effective_buffer 注册
  calculate_pseudocode: |
    def _calculate_contraction_monotonic(self, df, idx):
        if idx < 60:                        # lookback 不足 gate（第二道防线）
            return None
        # 1. identify last 3 pullbacks from active_peaks + recent lows
        # 2. compute contraction_ratio = [pullback_depth_i / pullback_depth_{i-1}]
        # 3. score = fraction of i where ratio < 1 (monotonic decrease)
        return score
```

**category 分类规则**（防止 AI 按"阶段"而不是"属性"来归类）：
- `resistance` — 测量被突破 peak 或阻力簇的**结构属性**（如 peak 聚集紧度、测试次数）
- `breakout` — 测量突破瞬间的**行为特征**（如放量、跳空、突破日强度）
- `context` — 测量突破前的**环境特征**（如均线位置、回撤恢复、盘整结构）

盘整形态类因子大多落 `context`，但"峰值聚集紧度"这种测量 peak 结构的因子必须是 `resistance`。

**`add-new-factor` 3 文件 checklist 的额外产物**（Layer B 顺带输出，减少 skill 调用次数）：

```yaml
breakout_dataclass_stub: |
  contraction_monotonic: float | None = None  # 收缩单调性评分；None 表示 lookback 不足

effective_buffer_case: |
  if fi.key == 'contraction_monotonic': return 60
```

---

## 5. Skill 封装（完整大纲）

### 5.1 为什么封装

- 工作流有不明显的顺序（曲线 → hybrid compact loop → PartialSpec 精化 → Layer A/B 输出 → add-new-factor 接力），不编码进 skill 则每次 future-Claude 都要重新推理。
- 上游天然接 dev UI 导出，下游天然接 `add-new-factor`，是 skill 组合链里缺失的一环。
- Skill 职责是**编排 + prompt + schema**，**不**调用 LLM API——Claude-the-agent 在 skill 调用内自行驱动循环，与 `add-new-factor` 同构。

### 5.2 Skill 文件骨架（不实际写文件，只草稿）

```markdown
---
name: induce-factor-from-samples
description: Use when user has selected positive/negative BO samples in dev UI
  (or curated them via cold-start label-quantile fallback) and wants Claude
  to induce formation-level features across them via multi-round dense→sparse
  compact, outputting a two-layer feature spec + factor draft ready for
  add-new-factor. Not for single-sample analysis, not for blind scans, not
  for re-ranking existing factors.
---

# Induce Factor From BO Samples

## Overview

Drive a structured, multi-round LLM-induction loop over a corpus of
positive/negative breakout samples. Emit a two-layer Feature Library entry
whose Factor Draft section can be piped to `add-new-factor` verbatim.

## When to use

Trigger phrases:
- "induce a factor from these BOs"
- "learn what makes these breakouts good"
- "从这些 BO 里归纳特征" / "特征挖掘"

Prerequisite: `corpus/<run_name>/{positive,negative}.jsonl` exist (created
either via dev UI P/N hooks or via cold-start helper). Skill refuses to run
without them.

## Inputs

- corpus_path: directory containing positive.jsonl + negative.jsonl
- input_mode: 'hybrid' (default) | 'structured-dense' | 'structured-medium'
  | 'structured-sparse' | 'structured+overview'
- form_name: short slug (e.g. 'vcp_contraction')
- max_rounds: default 5
- cold_start: bool — apply label-quantile construction with attestation gate

## Procedure

### Step 1 — Corpus prep
- Load positive/negative refs; assert each pkl exists.
- Call `encode_samples(mode=...)` per input_mode; when hybrid, also call
  `render_bo_for_ai(mode='detail')` per sample.
- Partition into batches per §2.2 size table.
- **Assert `post_bars == 0`** on every sample.

### Step 2 — Multi-round compact loop
For k in 1..max_rounds:
  1. Build prompt: SYSTEM + (PartialSpec_{k-1} if k>1) + BATCH_k + NEG_BATCH_k
     + [overview images if current cluster stage requires spatial info].
  2. SYSTEM prompt enforces:
     - contrastive clause (§2.4 #1)
     - overlap clause (§2.4 #2, with current FACTOR_REGISTRY dump)
     - schema clause (§2.4 #3)
  3. Persist PartialSpec_k to `<corpus_path>/specs/round_{k}.yaml`.
  4. Early-stop: 2 consecutive rounds with no invariant change AND no new
     open_questions.
  5. 4-cluster cap: if model attempts 5th cluster, emit split_required
     manifest and halt this run (see §2.6).

### Step 3 — Self-consistency spot-check
- Switch to `structured-sparse` mode.
- Sample 3–5 random earlier BOs (positives + negatives).
- Re-classify against current PartialSpec invariants.
- If ≥20% mismatch: trigger one extra round of dense refinement, then
  re-run spot-check.

### Step 4 — Emit Feature Library entry
- Write `docs/research/feature_library/<form_name>.md`:
  - Layer A: Feature Spec (Intuition / Invariants / Measurement Hint /
    Edge Cases / Confidence / Source Corpus Ref / Signal Novelty).
  - Layer B: `factor_draft` YAML with all 8 fields + dataclass stub +
    effective_buffer case (§4.2).
- **Reject Layer B missing any of the 8 fields.** No field may be `null`
  or "TBD". Reject and re-prompt for the missing one.

### Step 5 — Handoff
- If user accepts the Factor Draft, invoke `add-new-factor` skill with
  the `factor_draft` YAML as input.
- After factor lands in codebase, run `BreakoutStrategy.mining.pipeline`
  to empirically validate direction + thresholds.
- OOS fail signals a weak or overfit hypothesis; revert is cheap (3 files).

## Contracts — DO NOT MODIFY WITHOUT EXPERT SIGN-OFF

1. **Image annotation whitelist** (vision-input-expert): K-lines + volume
   pane + consolidation rect (α 0.12) + resistance lines (orange dashed)
   + BO ▲ red + peak ▼ black. Forbidden: MA, grid, dates, ticker, labels,
   IDs, tooltips.
2. **`post_bars = 0` in induction rounds** — hard assertion. Only the
   forensics stage (out-of-loop) may use `post_bars = 20`.
3. **Layer B 8-field checklist** — non-negotiable. Reject incomplete
   drafts.
4. **SYSTEM-prompt mandatory clauses** (§2.4) — must appear every round.

## Common Pitfalls

| Trap | Symptom | Fix |
|---|---|---|
| Running without negatives | Output reads "generic bull flag" | Add ≥10 matched negatives |
| Using label-low as negatives | Factor Draft just proxies label | Use §1.2 cold-start construction |
| Mixed-regime corpus | Incoherent invariants across clusters | Let split_required trigger; re-run per split |
| Skipping spot-check | Invariants quietly drift from early samples | Never skip Step 3 |
| AI reading numbers off images | Wrong quantitative invariants | Enforce hybrid: image + structured always paired |
| Accepting Layer B with null category | add-new-factor rejects downstream | Reject at Step 4 before handoff |

## Dependencies

- Consumes: dev UI corpus export (§1.1)
- Calls: `encode_samples` (§3.1), `render_bo_for_ai` (§3.2)
- Sister skills: `add-new-factor` (downstream), `write-user-doc` (for
  standalone Layer A persistence)
- Produces inputs for: `BreakoutStrategy.mining.pipeline` (empirical
  falsifier)

## Artifacts Written

- `<corpus_path>/specs/round_{k}.yaml` — per-round PartialSpec snapshots
- `<corpus_path>/specs/final.yaml` — frozen PartialSpec
- `docs/research/feature_library/<form_name>.md` — Layer A + Layer B
- `<corpus_path>/splits/<sub_run>.yaml` — only if split_required was raised
```

---

## 6. Handoff + Falsifier Chain

```
feature_library/<form>.md (Layer A + Layer B)
    │
    ├──[human review of Layer B]
    ▼
.claude/skills/add-new-factor/SKILL.md
    │
    ├── 1. FactorInfo registration (factor_registry.py)
    ├── 2. Breakout dataclass field (breakout_detector.py)
    ├── 3. _calculate_xxx + enrich_breakout line (features.py)
    ├── 4. _effective_buffer case (features.py)
    └── 5. Verification (registry / scorer / UI schema / buffer)
    │
    ▼
BreakoutStrategy/mining/pipeline.py
    │
    ├── Step 2: factor_diagnosis
    │           (Spearman direction on raw values; may overwrite
    │            proposed mining_mode if empirical signal contradicts)
    ├── Step 3: threshold_optimizer
    │           (Greedy beam → Optuna TPE → Bootstrap 稳定性)
    └── Step 4: template_validator
                (5-dim OOS: per-template / top-K retention / KS+CI /
                 baseline shift / coverage)
    │
    ▼
 ┌──────────────────────────────────────────────┐
 │ PASS → factor earns its place; update         │
 │        feature_library/<form>.md Confidence   │
 │        section with OOS 结论                  │
 │                                               │
 │ CONDITIONAL PASS → human review required      │
 │                                               │
 │ FAIL → hypothesis falsified; revert factor    │
 │        (3-file diff; cheap); refine corpus    │
 │        or retire the form                     │
 └──────────────────────────────────────────────┘
```

**为什么这样安排**：AI 归纳生产的是**便宜假设**，mining pipeline 是**严格判官**。两者分工使 workflow 在科学意义上 sound——归纳不依赖人对因子好坏的主观判断；主观判断只决定"看哪些样本"，客观验证决定"因子能不能留下"。

**重要的反馈回路**：OOS FAIL 不只是扔掉因子。它是一个信号："用户挑的正例与反例不够判别 / 归纳过程抓到的是噪声 / 或形态本身在样本外不稳定"。对应的响应是：
1. 检查 corpus——是否样本过少、过同质、或反例构造有问题
2. 检查 PartialSpec 的 Signal Novelty 摘要——如果是 `duplicate`/`refinement` 居多，说明归纳本身价值低
3. 检查 invariant 的 `counter_evidence`——如果有但被忽略了，说明前几轮的判别太脆弱

每一种响应都指向下一次 induction 运行的改进方向。

---

## 7. Pitfalls & Open Items

### 7.1 执行层 Pitfalls（skill 内嵌入 Common Pitfalls 表）

已经在 §5.2 skill 骨架里展开。这里只标注 workflow 层的二阶陷阱：

- **正例 attestation 的认知疲劳**：用户确认 5 个正例是低成本动作；但冷启动场景下，用户对"什么叫好形态"本身不确定。建议 attestation UI 先展示一个"已知好形态样板"（如从现有高分 trial 抽的），再让用户对比新样本。
- **open_questions 回写的陷阱**：模型可能为了显得"谦虚"每轮都塞几个 open_questions，污染早停判据。早停判据只计 *新* open_questions（relative to 上一轮）。
- **overlap_with_existing 的假阳性**：模型可能误判"和 pre_vol 有关"为 duplicate，实际只是 measurement 思路接近但测量对象不同。SYSTEM prompt 里要提示："duplicate 要求测量对象、窗口、触发方向三者都相同；任一不同走 refinement。"

### 7.2 Open Items（等 upstream 结论）

- **Prompt 模板本体**：kline-encoding-expert 供稿中，到位后直接嵌入 §2.4，当前版本为占位（语义已锁）。
- **Vision per-image 调优**：若后续发现 AI 从 detail 图反复出错读某类形态，可能需要修订白名单（但必须走 vision-input-expert 签字流程）。
- **模式切换自动化**：当前 input_mode 由 skill 调用方指定。未来可加一个启发式："PartialSpec 稳定且 cluster 数已收敛 → 自动切 sparse 做大样本 coverage 确认"，让 skill 自适应降级。
- **Feature Library INDEX**：`docs/research/feature_library/INDEX.md` 汇总所有 form_name → Layer B key → mining 验证结果。在 library 增长到 3+ 条时值得加；当前不是瓶颈。
- **情感验证耦合**：mining pipeline 的 Step 6（sentiment validation）目前在 template 层。如果 AI 归纳出的因子本身就"带情感含义"（例如"伴随爆量+新闻催化"），是否在 Factor Draft 里留一个 `sentiment_hint` 字段？暂不加，等第一个实例再决定。

### 7.3 落地工程工作清单

以下工程落地项在总终稿 `feature_mining_via_ai_design.md` 的 engineering checklist 章节展开，本文不重复：

- 5 个新盘整字段（range_duration_bars / touches_lower / range_stability / slope_in_range / vol_contraction_ratio）由 `FeatureCalculator` 或 `ConsolidationSummarizer` 产出
- Dev UI 的 `P`/`N` keyboard hook + cold-start 抽样辅助
- 三段式 corpus exporter（dense / medium / sparse 各档位按 §3.1 模式绑定自动精简；Seg 1 的 `traj=` 自然语言轨迹标签拼接逻辑）
- skill 文件 `.claude/skills/induce-factor-from-samples/SKILL.md` 本身

本详细设计锁的是这些工程落地项的**语义契约**；具体实现计划与优先级排序由总终稿决定。
