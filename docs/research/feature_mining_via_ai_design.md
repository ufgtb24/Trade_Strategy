# AI 驱动的突破形态特征挖掘 — 方案设计

> 研究日期：2026-04-23
> 参与方：team-lead-2（协调/汇总）、kline-encoding-expert（task #2 结构化输入）、vision-input-expert（task #3 图像输入）、workflow-designer（task #4 端到端流程 + skill 封装）
> 输入文件参考：`BreakoutStrategy/factor_registry.py`、`BreakoutStrategy/analysis/`、`.claude/skills/add-new-factor/SKILL.md`

---

## 0. 摘要（Executive Summary）

**结论：可行，且值得立刻按推荐方案启动。**

痛点：`live` 匹配到的突破多为"高位突破"（无底部积累），用户理想形态是"底部稳固积累后温和突破"。目前 13 个活跃因子（`factor_registry.FACTOR_REGISTRY`）对此类形态刻画不足，且形态直觉难以语言化。

核心思路：把"特征归纳"这一环交给 Claude Code —— 用户从 `dev` UI 挑选正例/反例 BO → 系统以 **图像 + 结构化文本混合形式** 批量输入 → Claude 经 **多轮 dense→sparse compact 归纳** → 产出 **两层输出**（自然语言 Feature Spec + 可直接对接 `add-new-factor` 的 Factor Draft）→ 由 `mining/` 流水线做经验 falsifier 验证。

推荐输入方案：**图像（形态直觉）+ 三段式结构化文本（量化锚定）** 混合。
推荐流程封装：**新建 skill `induce-formation-feature`**，与 `add-new-factor` 同构（orchestration 模式，Claude-the-agent 执行循环，不调 LLM API）。

本研究不动任何代码，产出为本文档 + 配套落地 checklist。

---

## 1. 可行性结论

### 1.1 Claude Code 视觉能力边界（已确认）

| 能力维度 | Opus 4.7 | Sonnet 4.6 | 说明 |
|---|---|---|---|
| 单图分辨率上限 | 2576px 长边 / ~4500 tok | 1568px 长边 / ~1600 tok | 来源：vision-input-expert 实测 + 官方 docs |
| 单图可辨 K 线数 | 180~240 根（甜区），上限 ~320 | 100~150 根 | 2560px 宽，每根 ~10-14px 实体+影线都可分辨 |
| 单轮独立图数量 | 15~20 张（注意力瓶颈），硬上限 100 | 8~12 张 | 20+ 张后 AI 开始混淆样本编号 |
| 九宫格拼图 | 不推荐 | 不推荐 | 实测单格 ~850×480 px 下 K 线颜色都分辨不清 |
| 从图读数值 | **不可靠**（误差 ±30%） | 不可靠 | 金句：**AI 不应该从图像里读任何数字** |
| 识别定性形态 | 可靠（矩形/U 底/旗形/杯柄/三重顶） | 可靠 | 形态分类是视觉的核心价值 |

### 1.2 Token 预算（已核算）

| 输入形式 | 单样本成本 | 单轮容量（按 Opus 150k 甜区） |
|---|---|---|
| 纯结构化（三段式）| ~620 tok | 20~30 样本 |
| 纯图像（2560×1440）| ~4500 tok | 15~20 样本 |
| 混合（1 图 + 500 tok 精简结构化）| ~5000 tok | 15~20 样本 |
| Sparse 精简文本（Seg 1 traj 标签 + Seg 3 档位）| ~200 tok | 80~150 样本（聚类用） |

### 1.3 Dense → Sparse 多批次 compact 机制合理性

**合理，但需限定用法**：
- Dense 轮（20~30 样本 × 完整三段式 + 图像）是**主归纳**，不 compact、不分多 turn（横向对比要求信息密度）。
- Sparse 轮（80~150 样本 × Seg 1 traj 标签 + Seg 3 factor_levels 档位）用于**大样本粗聚类**或早期探索，此时 AI 的任务是"归类分组"而非"提炼不变量"。
- **"中间 compact 成 summary 再在 summary 上归纳"反模式**：会把样本间的精细差异压平，丢失盘整字段分布信息。只在样本数超过 80 时才分两阶段（sparse 聚类 → 各组 dense 归纳）。

### 1.4 用户担心的"过拟合"风险

用户明确拒绝深度学习路线（此前过拟合）。本方案的防过拟合机制：
1. **AI 只产生假设**（Feature Spec + Factor Draft），**不直接落地**。
2. **mining 流水线做 empirical falsifier**：Spearman 方向诊断 → TPE 阈值优化 → 5-dim OOS 验证。不通过验证的因子自然被丢弃。
3. **增删因子成本极低**（`add-new-factor` 只改 3 个文件），试错代价小。
4. **禁止用 label 反向拟合**：prompt 强制条款 + 两段式 label 揭示（详见 §3.2）。

---

## 2. 推荐方案总览

### 2.1 输入：图文混合、职责分离

> **核心原则**：**图像负责定性形态，结构化负责定量数值。AI 不从图像读任何数字。**

| 维度 | 图像负责 | 结构化负责 |
|---|---|---|
| 形态类别名词 | ✅（矩形盘整 / U 底 / VCP / 三重顶 / 高位横盘 …） | — |
| 结构关系 | ✅（盘整位于 X 年高点下方） | — |
| 时序感知 | ✅（先冲顶后回落） | — |
| 盘整长度、振幅、放量倍数、距前高百分比、因子值 | — | ✅ |
| Label / 评分 / 因子级别 | — | ✅ |

产出的归纳规则范式：**"矩形盘整（图）+ 盘整 30~60 根（文）+ 振幅 ≤ 15%（文）+ 突破日 RV ≥ 2.0（文）"** —— 可直接对接 `mining/` 阈值优化。

**配套原则（避免信息冗余）**：
- 文侧**不输出原始 OHLC 序列**（那是图的职责）。三段式只留骨架摘要（含 traj 自然语言标签）+ consolidation_json + factors/levels。
- 图侧**不写任何数字**（label / peak id / ticker / 因子值）。数值验证一律走文侧。

### 2.1.1 三档 input_mode（三方合流共识）

| Mode | 图 | 文 | tok/样本 | 样本/轮 | 用途 |
|---|---|---|---|---|---|
| `text_only` | — | dense 620 tok | ~620 | 20-30 | 阈值挖掘、大批量聚类、稀疏 fallback |
| `hybrid_light` ★ 默认 | detail (2560×1440) + consolidation_zoom (40-80 根特写) | sparse 500 tok | ~9500 | **12** | 主力归纳 |
| `hybrid_full` | + overview (500 根，~2 年位置背景) | sparse 500 tok | ~14000 | 8 | 位置属性归纳、高置信规则敲定 |

说明：
- 默认 `hybrid_light` 每样本必带 detail + zoom **两张图**（zoom 覆盖盘整段 40-80 根，单根 30+ px 宽，保留 DOJI/长影/吞没等细节）。
- `hybrid_full` 追加 overview（长周期位置背景）。
- 大样本聚类 / 第一次粗扫描 / vision 不可用时，降级到 `text_only`。
- Sonnet fallback：上述所有 token 数按 ~1/3 缩放（1568px 长边上限），但不推荐做主力归纳。

### 2.2 流程：Claude Code skill `induce-formation-feature`

与 `add-new-factor` 同构的 orchestration skill（无 LLM API 调用，由 Claude-the-agent 在被调用时执行循环）。核心阶段：

```
[0] 样本选择
    ├─ 用户从 dev UI 手选（P 键标正 / N 键标反） — 推荐
    └─ Cold-start fallback：label_5_20 top quartile，用户 spot-check ≥5 个
    └─ 反例池：high-label 中用户未确认形态的样本（⚠ 不是 low-label）

[1] 语料导出（corpus exporter）
    └─ 正/反例 → 三段式结构化文本 + AI-friendly 图像（可选）

[2] 多轮 compact 归纳
    Round k:
      Input:  SYSTEM prompt
              + PartialSpec_{k-1}   (evidence receipts 抗遗忘)
              + BATCH_k 正例样本（图+文）
              + NEG_BATCH_k 反例样本（与正例 regime 匹配）
      Output: PartialSpec_k (YAML, 含 clusters / invariants / counter_evidence)
              + per-sample label 盲猜（然后揭示真 label 做 self-correct）

[3] 产出两层输出到 docs/research/feature_library/<form_name>.md
      Layer A: 自然语言 Feature Spec（人读）
      Layer B: Factor Draft （8 项固定 checklist，可直接喂 add-new-factor）

[4] 用户 review → 调用 add-new-factor 落地 → mining 验证
```

### 2.3 用户工作量预估

- 每次 skill 调用：用户挑 10-20 个正例 + 系统自动选反例 → ~5 分钟准备 + 1-2 轮 dense 归纳（~150k input tokens/轮）
- 产出到因子落地：自然语言 → Factor Draft 已由 skill 完成；用户 review 后跑 `add-new-factor` 只需改 3 个文件 + 1 个 `_effective_buffer` 注册
- 挖掘验证：现成 `mining/` 流水线一次跑完，不用人工

---

## 3. 详细设计

### 3.1 结构化输入：三段式（每样本 ~620 token）

由 kline-encoding-expert 定稿，经用户 review 后移除原 Segment 2（Zig-Zag symbolic_sequence）—— 理由：符号化离散 token 更适合专门训练的小型 NLP 模型，对 Claude 这类通用 LLM 需现场查 legend、推理成本高且易错；在混合模式下形态骨架由图像承担，在 text-only 模式下由 Segment 1 的 `traj=` 自然语言标签承担，无需冗余符号段。

```
[Segment 1] one_line_tag
  "C0.range=8.8%/55bars touches=3↑/2↓ vol=0.85x→3.6x pbm=0.85σ traj=bottom_lift→breakout"
  ── 20-40 tok，给 AI 鸟瞰视角
  ── 其中 traj= 字段承担"形态轨迹鸟瞰"职责，用简短自然语言标签拼接
     （如 bottom_lift→breakout / long_decline→short_bounce→flat_consol→breakout），
     Claude 原生可解析，无需 legend。

[Segment 2] consolidation_json (核心细节 — 盘整 13 字段)
  ── 250 tok

[Segment 3] factors_and_levels
  {"values": {13 个因子原始值}, "levels": {13 个因子离散档位}}
  ── 160 tok，双视角（既看原值也看现有系统判定）
```

**盘整 13 字段**（Segment 2 的内容，由 kline-encoding-expert 定义）：

| 层级 | 字段 | 数据来源 | 成本 |
|---|---|---|---|
| **必需 (8)** | range_low_rel | broken_peaks 低价 | 现成 |
| | range_high_rel | broken_peaks 高价 | 现成 |
| | range_width_pct | 派生 | 零 |
| | range_duration_bars | 从最老 broken_peak.index 到 bo.index | **需新算** |
| | touches_upper | peaks 数量（≈ `test` 因子） | 半现成 |
| | touches_lower | 区间内 low 触及 range_low±noise 次数 | **需新算** |
| | intra_range_vol_ratio | `rv_63` 序列在盘整窗口均值 | 半现成 |
| | breakout_vol_ratio | `volume` 因子 | 现成 |
| **建议 (5)** | range_stability | std(close-mean)/mean | **需新算** |
| | slope_in_range_pct | 盘整 close 线性回归斜率 | **需新算** |
| | ma20_slope_in_range | 20 日均线斜率 | 半现成 |
| | vol_contraction_ratio | 后半均量/前半均量 | **需新算** |
| | breakout_vs_range_vol | 派生比值 | 零 |

**→ 5 个字段需新算**（range_duration_bars / touches_lower / range_stability / slope_in_range / vol_contraction_ratio）。落地由用户后续以普通 PR 在 `FeatureCalculator` 或独立 `ConsolidationSummarizer` 完成，见 §7 checklist。

### 3.2 图像输入：AI-friendly 渲染

由 vision-input-expert 定稿：

**尺寸规格**：
- Opus 4.7：2560×1440 px，200 DPI，~4500 tok/图
- Sonnet 降级：1560×880 px，~1600 tok/图
- K 线根数：180~240 根（覆盖 bo 前 150~200 根盘整 + bo 后 20~40 根）
- 格式：PNG（JPEG 多轮压缩损坏 K 线边缘）

**保留元素**：
- 蜡烛图（绿 `#4CAF50` / 红 `#B71C1C`）
- 成交量子图（占 20% 高度，突破日黄色高亮）
- **盘整区矩形框**（浅黄 alpha=0.12）— 显式告诉 AI 盘整范围
- **被突破 peak 的橙色虚线水平线**，贯穿盘整区 — 把"突破"从点动作升级为线索引
- BO 红色 ▲ + "BO" 单字
- 峰值 ▼ 黑色（无 ID）

**删除元素**：
- MA 均线（混淆形态） ★
- 网格线 / 日期标签
- **Ticker 代码 ★**（防止诱导先验偏见，破坏纯形态归纳）
- Peak ID / BO ID / Label 数值（小字不可读，走结构化）
- Tooltip / Score panel 等 UI 残留

**三层图像输入（`hybrid_light` / `hybrid_full` 模式）**：
- **detail**（默认）：180~240 根，BO 前 ~200 根 + BO 后 ~20 根，每根 K ~12px，主力形态视图
- **consolidation_zoom**（`hybrid_light` 默认随行）：仅盘整段 40~80 根，每根 K 30+ px 宽，保留 DOJI / 长影 / 吞没等单根纹理 —— 弥补 detail 图在盘整密集区的分辨率不足
- **overview**（`hybrid_full` 才开）：500 根，覆盖 ~2 年位置背景，用于"底部 vs 高位"的相对位置判断

默认主力 pipeline（`hybrid_light`）= detail + zoom 两张图 + sparse 文本 ≈ 9500 tok/样本，单轮 12 样本。

### 3.3 多轮 compact 归纳协议

#### PartialSpec Schema（YAML）

```yaml
clusters:
  - archetype: "tight_rectangle_at_support"   # 形态原型名
    sample_refs: [S001, S003, S007, ...]
    invariants:
      - statement: "contraction ratio decreases monotonically over last 3 sub-ranges"
        overlap_with_existing: []             # 与现有 13 因子重叠情况
        overlap_kind: null                    # duplicate | refinement | orthogonal | null
        evidence_receipts: [S001:0.92, S003:0.87, S007:0.95]
      - statement: "volume dries up in final contraction"
        overlap_with_existing: ['pre_vol']
        overlap_kind: 'refinement'
        evidence_receipts: [...]
    weak_signals:
      - "ma20 slope near flat (ambiguous across samples)"
    counter_evidence:
      - ref: S012
        observation: "breaks the tight-range invariant but still has high label"
        hypothesis: "may belong to different archetype"

distinguishing_vs_negative:
  - "negatives lack consolidation-to-breakout volume contraction-then-expansion pattern"
  - "negatives show slope_in_range > +1%/bar (drifting up, not flat)"

open_questions:
  - "is touches_lower >= 2 strictly necessary, or does 1 solid test suffice?"

coverage_stats:
  positives_explained: 9/10
  negatives_rejected: 8/10
  unexplained_positives: [S008]
  leaked_through_negatives: [N005, N006]

suggested_splits:      # 当正例原型数 > 4 时触发
  - sub_run_name: "low_price_basing"
    rationale: "price < $20 cluster with different volatility regime"
    positive_refs: [...]
    negative_refs: [...]
```

#### SYSTEM prompt 核心条款

1. **levels 破笼**：「`factor_levels` 代表现有 13 因子的判定。你的任务是找出 **levels 之外** 的判别信号。仅复述 levels 已表达的规律 = 失败。」
2. **Overlap 声明**：「每个 invariant 必须声明 `overlap_with_existing` 与 13 活跃因子（age, test, height, peak_vol, volume, overshoot, day_str, pbm, streak, drought, pk_mom, pre_vol, ma_pos）的关系为 duplicate/refinement/orthogonal。duplicate 必须 drop，除非能给出具体 refinement。」
3. **区分性强制**：「对每个 invariant，说明它如何区分正例与反例。若不能区分，drop。」
4. **不允许用 label 反向拟合**：「你的 invariants 必须基于 **形态特征**，不能通过 label 值直接推导。"高 label 样本共有 Y" 不是有效 invariant。」
5. **Counter-evidence 必须保留**：「PartialSpec 中已登记的 counter_evidence 不能在下一轮沉默删除，若要修改须说明理由。」

#### 两段式 label 揭示协议

```
Round k / Phase 1 (盲猜):
  Input:  SYSTEM + PartialSpec_{k-1} + BATCH_k (无 label)
  Output: PartialSpec_k draft + per-sample predicted_label_tier (low/mid/high)

Round k / Phase 2 (揭示 + 修正):
  Input:  真实 labels for BATCH_k
  Output: PartialSpec_k final
          + mispredicted_samples: [
              {ref, predicted, actual, which_invariant_failed, hypothesis}
            ]
```

理由：先盲猜迫使 AI 只用形态归纳，再用 label 做 self-correct，避免反向拟合。

### 3.4 正/反例样本策略（cold-start）

- **正例池**：`label_5_20` top quartile ∩ 用户 spot-check 确认 ≥5 个
- **主反例池**：`label_5_20` top quartile \ 正例池 —— 即 **高 label 但用户未确认形态** 的样本。**关键反例**，因为它们证伪"label = 形态"的假设，迫使 AI 给出形态层面的判别。
- **次反例池（可选）**：`label_5_20` 中分位，作为"mediocre form baseline"测试不变量泛化
- **禁用**：`label_5_20` 低分位样本 —— 会把"任何突破失败的原因"混入，这是 `mining/` direction diagnosis 的职责，不是形态归纳的任务

**Skill 启动 gate**：用户必须在 UI 上 attest 过 ≥5 个正例后 skill 才允许进入归纳阶段，防止无 anchor 的盲归纳。

### 3.5 两层输出

产出到 `docs/research/feature_library/<form_name>.md`。

#### Layer A — Feature Spec（自然语言，人读）

```markdown
# Feature Spec: Tight Rectangle Basing Breakout

## Archetype summary
... (两到三段自然语言描述，含形态命名、正反例差异)

## Invariants (with overlap classification)
1. Consolidation duration 30-80 bars [orthogonal to existing factors]
2. Range width 5-15% [orthogonal]
3. touches_lower >= 2 AND touches_upper >= 2 [refines `test`]
4. intra_range_vol_ratio < 1.0 AND breakout_vol_ratio >= 2 [refines `pre_vol` + `volume`]
5. range_stability < 0.03 (tight oscillation) [orthogonal]
6. slope_in_range in [-0.1%, +0.1%] per bar (truly flat) [orthogonal]

## Counter-evidence & limitations
- ... (保留 counter_evidence，作为长期知识)
```

#### Layer B — Factor Draft（8 项固定 checklist，对接 `add-new-factor`）

每条 invariant 若通过 `orphogonal` 或 `refinement` 筛选，产出一个 Factor Draft：

```yaml
factor_draft:
  key: "range_tight"
  name: "Range Tightness"
  cn_name: "盘整紧致度"
  category: "context"                     # resistance | breakout | context
  default_thresholds: [0.015, 0.025, 0.04]
  default_values: [1.25, 1.15, 1.05]      # 越小越好 → 奖励递减
  mining_mode: "lte"                      # 值越小越好
  nullable: true                          # effective_buffer > 0
  effective_buffer: 60                    # 需新算的盘整字段 lookback
  zero_guard: false
  pseudo_code: |
    def _calculate_range_tight(self, df, idx):
        if idx < 60:
            return None
        window = df.iloc[idx-60:idx]
        closes = window["close"]
        return closes.std() / closes.mean()
```

8 项固定字段（缺一不可，skill 内部 YAML validator 强制）：
`key, name, cn_name, category, default_thresholds, default_values, mining_mode, nullable`

配套说明字段：`effective_buffer`（用于 `FeatureCalculator._effective_buffer` 注册）、`pseudo_code`（供用户实现参考）。

### 3.6 Skill frontmatter 草稿

```yaml
---
name: induce-formation-feature
description: Use when user has selected positive/negative BO samples in dev UI
  (or curated them via cold-start label-quantile fallback) and wants Claude to
  induce formation-level features across them via multi-round dense→sparse
  compact, outputting a two-layer feature spec + factor draft ready for
  add-new-factor. Not for single-sample analysis, not for blind scans, not
  for re-ranking existing factors.
---
```

Skill 结构草稿：

```
induce-formation-feature/
  SKILL.md                       # 主入口，分阶段 instructions
  schemas/
    partial_spec.yaml.schema     # PartialSpec JSON Schema
    factor_draft.yaml.schema     # 8-item Factor Draft schema，validator 用
  prompts/
    system_inductive.md          # SYSTEM prompt（含 5 项核心条款）
    user_round_template.md       # USER prompt 骨架（每轮填 BATCH + NEG_BATCH）
    system_label_reveal.md       # 两段式 label 揭示 Phase 2 prompt
  templates/
    feature_library_output.md    # Layer A+B 两层输出模板
```

Skill **不调用 LLM API** —— 它是 orchestration 文档，Claude-the-agent 被用户唤起时读入并 **自身执行循环**。与 `add-new-factor` 同构。

---

## 4. 备选方案与权衡

### 4.1 输入形式

| 方案 | 单样本 tok | 形态感知 | 数值精度 | 结论 |
|---|---|---|---|---|
| 纯结构化三段式 | ~620 | 弱（仅靠 Seg 1 的 traj 自然语言标签，无符号串骨架） | 极强 | 备选 —— 图像不可用时降级 |
| 纯图像 AI-friendly | ~4500 | 强 | 0（AI 不读数字） | 备选 —— 早期形态分类探索 |
| **图 + 文 混合 ★** | ~5000 | 强 | 强 | **推荐** |
| 九宫格拼图 | ~500/样本 | 极弱（K 线糊） | 0 | 不推荐，仅粗扫描 |
| 多 turn + compact | 不定 | 跨 turn 遗忘 | — | 反模式，除非 >80 样本 |

### 4.2 流程封装

| 方案 | 优势 | 劣势 | 结论 |
|---|---|---|---|
| **封装 skill ★** | 固化 PartialSpec schema、prompt 条款、输出模板，每次一致；与 add-new-factor 对接有保证 | 前期有 SKILL.md 编写成本 | **推荐** |
| 不封装，每次 ad-hoc | 灵活 | schema 漂移、用户和未来 Claude 都会忘记协议 | 不推荐（用户将频繁使用） |

### 4.3 归纳策略

| 方案 | 场景 | 备注 |
|---|---|---|
| **Dense 单轮 20~30 样本 ★** | 主力归纳 | 推荐，跨样本对比密度最高 |
| Medium 单轮 30~50 样本（精简文本）| 复核 | 推荐，作为 Round 2 refinement |
| Sparse 单轮 80~150 样本（Seg 1 traj 标签 + Seg 3 factor levels 档位）| 先聚类 | 推荐，样本 >80 时使用 |
| Dense 多 turn + compact | — | **反模式**，丢失样本间差异 |

### 4.4 反例池策略

| 反例来源 | 效果 | 采纳 |
|---|---|---|
| High-label 中用户未确认形态 ★ | 迫使 AI 产出形态层面判别 | **推荐（主反例）** |
| Label 中分位 | Baseline 泛化测试 | 推荐（次反例） |
| Label 低分位 | 混入"任何突破失败"的噪声 | 禁用 |

---

## 5. 与现有系统的对接

### 5.1 数据侧

| 需要 | 现状 | 工作 |
|---|---|---|
| Breakout dataclass / peaks / factors | 已有（`analysis/features.py::Breakout`, 13 因子） | 无需改 |
| 盘整 13 字段中的 5 个新字段 | 无 | **新增**（见 §7 checklist） |
| 三段式 corpus exporter | 无 | **新增** |
| AI-friendly 图像渲染 | `UI/charts/` 有基础能力，但风格不同 | **新增 renderer**（建议挂 `dev/research/` 或 `UI/charts/ai_render/`） |

### 5.2 UI 侧

| 需要 | 现状 | 工作 |
|---|---|---|
| Dev UI 中选中 BO 并标 P/N | 有 HoverState 可复用 | **新增 P/N 键盘 hook** |
| 导出正例/反例 manifest（JSON）| 无 | **新增** |
| Cold-start label-quantile 自动抽样器 | 无 | **新增** |

### 5.3 输出侧

| 接口 | 现状 | 工作 |
|---|---|---|
| `add-new-factor` skill | 已有（`.claude/skills/add-new-factor/SKILL.md`） | 无需改 |
| `factor_registry.FACTOR_REGISTRY` | 已有 | 无需改（Factor Draft 直接对应 `FactorInfo` 参数） |
| `FeatureCalculator._effective_buffer` | 已有 SSOT | 新因子按 skill checklist 注册 case |
| `Breakout` dataclass 新因子字段 | 已有 pattern | 按 skill checklist 添加 |
| `mining/` 阈值优化 + OOS 验证 | 已有全流程 | **无需改，作为 empirical falsifier** |

### 5.4 路径约束

- 本研究文档：`docs/research/feature_mining_via_ai_design.md`（本文件）
- 详细工作流文档（workflow-designer 负责）：`docs/research/feature_induction_workflow_detail.md`
- Skill 本体：`.claude/skills/induce-formation-feature/`（与 `add-new-factor` 同位）
- 每次归纳产出：`docs/research/feature_library/<form_name>.md`（Layer A+B 两层输出）
- Renderer 代码建议路径（二选一，**由用户拍板**）：
  - `BreakoutStrategy/dev/research/ai_vision_render.py`（dev 下新设 research/ 子目录，归类于开发态工具）
  - `BreakoutStrategy/UI/charts/ai_render.py`（挂 UI/charts 作为专用渲染子模块，与现有 candlestick 共存）
  - vision-input-expert 最初建议顶层 `BreakoutStrategy/research/ai_vision_render.py`，但现有 code map 无顶层 `research/`，为保持模块边界一致性改为上述两条之一

---

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| AI 归纳出"伪因子"污染系统 | Factor Draft 只是假设，落地后由 `mining/` Spearman + TPE + OOS 验证；不通过自然被废 |
| AI 用 label 反向拟合 | 两段式 label 揭示（盲猜再揭示）+ SYSTEM 条款 4 明令禁止 |
| AI 归纳被现有因子"思维惯性"绑架 | `overlap_with_existing` 字段强制分类为 duplicate/refinement/orthogonal；duplicate 必须 drop |
| 样本异构度高导致 invariants 稀释 | 4-cluster hard cap → `suggested_splits` 结构化分叉（不允许返回"please split"自由文本） |
| 视觉 token 预算浪费（渲染细节过多）| AI-friendly 严白名单渲染，删 MA/网格/ticker/ID；双层图像默认关闭 |
| Skill 协议漂移（下次归纳方法变了）| schemas/ 下 JSON Schema 强校验 PartialSpec 与 Factor Draft |
| 用户忘记标 P/N 样本直接跑 | Skill 启动 gate 要求 ≥5 正例 attest |

---

## 7. 落地 checklist（下一步工作）

按优先级排列，**全部不在本研究的产出范围内**（本研究只输出设计，不动代码）。

### 7.1 P0 — MVP 闭环所需

1. **5 个盘整字段计算逻辑** — 作为独立 utility 模块 `BreakoutStrategy/analysis/consolidation_summary.py`（或并入 `features.py`）：
   - `range_duration_bars`、`touches_lower`、`range_stability`、`slope_in_range_pct`、`vol_contraction_ratio`
   - 不必先注册为正式因子；归纳阶段只作为 corpus 字段
2. **三段式 corpus exporter** — 新脚本 `scripts/export_formation_corpus.py`：输入 BO 列表（manifest JSON）→ 输出每样本三段式文本（含 Seg 1 `traj=` 自然语言标签的拼接逻辑）
3. **AI-friendly 渲染函数** — `render_bo_for_ai(bo, df, mode="detail"|"overview")`，2560×1440 PNG，严格按 §3.2 白名单/黑名单
4. **Dev UI P/N keyboard hook** — 在 `BreakoutStrategy/dev/` 的 hover 上绑定 P/N 键，写 manifest
5. **Cold-start 抽样器** — 按 label 分位数从 scan result JSON 抽样
6. **Skill 本体** `.claude/skills/induce-formation-feature/`：
   - `SKILL.md`
   - `schemas/partial_spec.yaml.schema` + `schemas/factor_draft.yaml.schema`
   - `prompts/system_inductive.md`（含 5 项条款）+ `prompts/user_round_template.md` + `prompts/system_label_reveal.md`
   - `templates/feature_library_output.md`

### 7.2 P1 — 体验增强

8. **`feature_library/` 自动索引** — skill 完成后向 `docs/research/feature_library/INDEX.md` 追加条目
9. **Round 之间的 PartialSpec 持久化缓存** — 失败可续跑
10. **Sparse 聚类模式** — 单独入口，样本 >80 时先分组
11. **多 cluster 分叉 → 子 run manifest 自动生成**

### 7.3 P2 — 长期优化

12. **形态命名归一化** — 维护一个 `form_archetype_glossary.md`，防止 AI 每次给"杯柄"起不同名字
13. **与 `news_sentiment` 交叉验证** — 正例形态是否叠加正面消息倾向

### 7.4 不做（本次明确排除）

- 自动 LLM API 调用（skill 保持 orchestration 模式）
- 替换现有 13 因子（新因子 additive 添加）
- 改动 `mining/` 流水线（它就是 falsifier，不改）
- 触碰 `.claude/docs/`（CLAUDE.md 严禁）

### 7.5 推荐施工序列（4 个 phase）

P0 的 7 项不是严格 DAG，但有强推荐的先后顺序，让路径渐进可用：

**Phase 1 — Corpus 能力打底（结构化路径先行）**
1. 5 个新盘整字段计算（`consolidation_summary.py` 或并入 `features.py`）
2. 三段式 corpus exporter（per-sample 文本包，含 Seg 1 `traj=` 自然语言标签拼接）
- **里程碑**：任意 BO 列表 → 三段式文本包，可**无 skill、无 UI 手工试跑归纳**（纯结构化模式）。这是最早的可验证状态。

**Phase 2 — UI 便利 + skill 骨架**
3. Dev UI P/N keyboard hook（manifest 导出）
4. Cold-start label-quantile 抽样器
5. Skill 本体（`SKILL.md` + schemas + prompts + templates）
- **里程碑**：skill 端到端跑通 `input_mode='structured'`。

**Phase 3 — 图像扩展（形态直觉升级）**
6. AI-friendly 渲染函数 `render_bo_for_ai(bo, df, mode)`
- **里程碑**：`input_mode='hybrid'` 启用。

**Phase 4（P1 后续）**：feature_library 自动索引、PartialSpec 持久化缓存、sparse 聚类入口、cluster 分叉子 manifest 自动生成。

**为什么这个顺序**：结构化路径所有 token 预算和字段清单已校准完整，先上最快闭环；图像作为 upgrade 而非 blocker，对齐 `input_mode` 参数化降级设计。P1 项在 P0 跑通并确认"归纳质量值得投资"后再投入。

参见 `feature_induction_workflow_detail.md` §7 的 rollout sequencing（镜像口径）。

---

## 8. 关键术语速查

| 术语 | 含义 |
|---|---|
| Formation / Form | 形态（图 A 的"底部盘整突破"是一种 form） |
| PartialSpec | 多轮 compact 的中间表征，YAML；evidence-receipts 抗遗忘 |
| Invariant | 一条形态不变量（候选因子的自然语言描述） |
| Feature Spec | Layer A，自然语言特征描述 |
| Factor Draft | Layer B，8 项 checklist 的 YAML，可喂 `add-new-factor` |
| Overlap kind | invariant 与现有 13 因子的关系：duplicate / refinement / orthogonal |
| Dense / Medium / Sparse | 三档归纳密度：20~30 / 30~50 / 80~150 样本一轮 |
| Cold-start gate | skill 启动前要求用户 attest ≥5 正例 |
| Empirical falsifier | `mining/` 的 TPE + OOS 验证，作为 AI 假设的经验检验 |

---

## 9. 附录

### 9.1 渲染伪代码骨架（vision-input-expert 规格）

> **Visual Schema Contract**：下列 palette / mode / 白名单 / 黑名单是**冻结契约**，修改需 vision-input-expert 认可。完整实现约 150-200 行（含空 df / bo 越界兜底、Sonnet 降级 1560×880、peaks 默认提取）。
> 推荐代码路径：`BreakoutStrategy/dev/research/ai_vision_render.py`（已由 vision-input-expert 二次确认）。

```python
"""
AI-friendly candlestick render for vision-based BO form induction.
Visual schema is frozen — see Visual Schema Contract above.
"""
import io
from typing import Literal
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
from ...analysis.breakout_detector import Breakout, Peak

# Frozen palette (do NOT theme)
_UP, _DOWN = "#4CAF50", "#B71C1C"
_CONSOL_FILL, _CONSOL_ALPHA = "#FFF9C4", 0.12
_RESIST_COLOR = "#FF9800"
_BO_COLOR = "#D32F2F"
_VOL_UP, _VOL_DOWN, _VOL_BO = "#D3D3D3", "#696969", "#FFD700"

_MODE_DEFAULTS = {"detail": 200, "consolidation_zoom": 60, "overview": 500}


def render_bo_for_ai(
    bo: Breakout,
    df: pd.DataFrame,
    *,
    mode: Literal["detail", "consolidation_zoom", "overview"] = "detail",
    window: int | None = None,
    size_px: tuple[int, int] = (2560, 1440),
    include_volume: bool = True,
    peaks: list[Peak] | None = None,
) -> bytes:
    n = window or _MODE_DEFAULTS[mode]
    left, right = _slice_window(bo, df, mode, n)
    sub = df.iloc[left:right + 1].reset_index(drop=True)

    dpi = 200
    fig, ax = plt.subplots(figsize=(size_px[0] / dpi, size_px[1] / dpi), dpi=dpi)
    ax.set_axis_off()  # no ticks, no date, no ticker

    # 1. candles
    for i, row in sub.iterrows():
        color = _UP if row.Close >= row.Open else _DOWN
        ax.plot([i, i], [row.Low, row.High], color=color, linewidth=1.2, zorder=2)
        body_lo, body_hi = min(row.Open, row.Close), max(row.Open, row.Close)
        ax.add_patch(mpatches.Rectangle(
            (i - 0.4, body_lo), 0.8, max(body_hi - body_lo, 1e-4),
            facecolor=color, edgecolor=color, linewidth=0.3, zorder=3,
        ))

    # 2. consolidation box (detail / consolidation_zoom only)
    if mode != "overview" and bo.consolidation_range is not None:
        c_left, c_right, c_lo, c_hi = bo.consolidation_range
        ax.add_patch(mpatches.Rectangle(
            (c_left - left, c_lo), c_right - c_left, c_hi - c_lo,
            facecolor=_CONSOL_FILL, alpha=_CONSOL_ALPHA,
            edgecolor="gray", linestyle=":", linewidth=1, zorder=1,
        ))

    # 3. resistance line (broken peak price)
    if bo.broken_peak_price is not None:
        ax.axhline(bo.broken_peak_price, color=_RESIST_COLOR,
                   linestyle="--", linewidth=1.8, alpha=0.85, zorder=4)

    # 4. BO anchor (single "BO" text, red ▲)
    bo_x = bo.index - left
    ax.scatter(bo_x, sub.iloc[bo_x].High, marker="^",
               s=180, color=_BO_COLOR, zorder=5)
    ax.annotate("BO", xy=(bo_x, sub.iloc[bo_x].High),
                xytext=(0, 12), textcoords="offset points",
                ha="center", color=_BO_COLOR, fontsize=16, fontweight="bold")

    # 5. peak anchors (black ▼, no ID)
    for p in (peaks or []):
        px = p.index - left
        if 0 <= px < len(sub):
            ax.scatter(px, sub.iloc[px].High, marker="v", s=120, color="black", zorder=5)

    # 6. volume sub-pane (bottom 20%)
    if include_volume:
        _overlay_volume(ax, sub, bo_x)

    ax.set_xlim(-1, len(sub))
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return buf.getvalue()


def _slice_window(bo, df, mode, n):
    """Window anchored on BO; consolidation_zoom tightens around consolidation."""
    if mode == "consolidation_zoom" and bo.consolidation_range is not None:
        c_left = bo.consolidation_range[0]
        return max(0, c_left - 3), min(len(df) - 1, bo.index + 5)
    return max(0, bo.index - n + 10), min(len(df) - 1, bo.index + 10)


def _overlay_volume(ax, sub, bo_x):
    """Overlay volume bars in bottom 20% of ylim, no separate axis/label."""
    y_lo, y_hi = ax.get_ylim()
    pane_top = y_lo + (y_hi - y_lo) * 0.2
    vol_max = sub.Volume.max() or 1
    for i, row in sub.iterrows():
        color = _VOL_BO if i == bo_x else (_VOL_UP if row.Close >= row.Open else _VOL_DOWN)
        h = (row.Volume / vol_max) * (pane_top - y_lo) * 0.9
        ax.add_patch(mpatches.Rectangle(
            (i - 0.4, y_lo), 0.8, h,
            facecolor=color, edgecolor="black", linewidth=0.3, alpha=0.75, zorder=1,
        ))
```

**适配注记**：
- `bo.consolidation_range` 与 `bo.broken_peak_price` 为假设字段名，实现时按 `Breakout` dataclass 实际字段名适配
- Sonnet 降级：`size_px=(1560, 880)`，~1590 tok/图
- 完整实现需补：空 df / bo 越界兜底、`peaks` 默认从 `bo.broken_peaks` 提取

### 9.2 Round 0 的 SYSTEM prompt 骨架（kline-encoding-expert 起草，workflow-designer 嵌入 skill）

```
You are inducing *formation-level* features that discriminate "good" breakout
setups from "bad" ones within the user's US equity breakout detection system.

CONTEXT
- 13 active factors already exist: age, test, height, peak_vol, volume,
  overshoot, day_str, pbm, streak, drought, pk_mom, pre_vol, ma_pos.
- Each sample below includes a `factor_levels` vector representing the
  current system's judgment. DO NOT rediscover these.

MANDATORY RULES
1. [Levels-breaking] factor_levels represents existing judgment. Your job is
   to find signals BEYOND levels. Merely restating level patterns = failure.
2. [Overlap declaration] For every invariant you propose, declare
   overlap_with_existing as list[factor_key] and overlap_kind as one of:
   duplicate | refinement | orthogonal. Duplicates MUST be dropped unless
   you provide a specific refinement.
3. [Discriminative] For every invariant, state how it distinguishes positive
   from negative samples in this batch. If it cannot, drop it.
4. [No label back-fitting] Invariants must be based on formation structure,
   not derivable from label values. "high-label samples share Y" is NOT valid.
5. [Evidence receipts] Every invariant must cite sample_refs. Counter-evidence
   recorded in prior rounds MAY NOT be silently deleted; retraction requires
   explicit justification.

OUTPUT
A valid PartialSpec YAML matching the schema provided. No prose outside YAML.
```

### 9.3 Teammate 产出汇总

- kline-encoding-expert（task #2）：结构化输入方案 + 盘整 13 字段 + token 预算；已在本文 §3.1 / §3.3 吸收（用户 review 后从四段式精简为三段式，移除 Zig-Zag symbolic_sequence）。完整精化版存于团队沟通记录。
- vision-input-expert（task #3）：AI-friendly 图像渲染规格 + Opus 4.7 视觉边界校正 + 混合方案职责分离；已在本文 §1.1 / §3.2 / §9.1 吸收。
- workflow-designer（task #4）：多轮 compact 协议 + PartialSpec schema + skill 封装决策 + 样本选择方案；已在本文 §2.2 / §3.3 / §3.4 / §3.6 吸收。其完整详稿另存 `docs/research/feature_induction_workflow_detail.md`（workflow-designer 后续独立交付）。

---

**文档结束。**
