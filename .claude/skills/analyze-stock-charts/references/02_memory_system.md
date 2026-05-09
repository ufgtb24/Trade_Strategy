# 02 — 跨会话规律库设计：持久化 + 增量整合 + 防幸存者偏差

> **角色**：本文件是 meta team `meta-stock-analyst-design` 中持久化规律库设计师的产出。
> **服务对象**：下游"反复运行"的股票分析团队 — 每次输入约 9 张 K 线图，每次都要在前次基础上**增量完善**对图形规律的认识。
> **不写实现代码**：本文件仅描述 schema、布局、协议、算法（用伪代码 / 决策树形式）。下游团队的 agent 用纯 markdown + yaml frontmatter 读写这套库。

> **设计约束**：所有规律库 IO 协议必须 LLM 可完成。详见 `SKILL.md §0.2 设计约束（LLM-only）`。

---

## 0. 设计目标与第一性原理

### 0.1 核心约束推导

下游任务有 4 个**结构性约束**，决定了规律库不能只是"普通的备忘录"：

| 约束 | 后果 |
|---|---|
| 每次只看 ~9 张图 | 单次发现的规律只能在 9-sample 上"假设性成立"，绝不是定论 |
| 多次运行才能积累足够样本 | 规律必须**跨会话可读、可累加**，且每次都要把"本批 9 图"的支持/反例写进规律记录 |
| AI 上下文+图像记忆有限 | 历史图不能全部带回上下文 — 必须有**结构化抽象**（chart_id + 关键特征摘要）替代"重新看图" |
| 大涨后行情天然稀缺 | 现有图都是"成功 case"，存在严重幸存者偏差 — 规律库**必须主动追踪反例与失败 case** |

### 0.2 第一性原理：规律 = 视角 × 数学定义 × 证据

一条"规律"在本系统中被严格定义为三元组：

```
Pattern = (Perspective, Definition, Evidence)
```

- **Perspective（视角）**：来自 stock-domain-expert 在 `01_analysis_dimensions.md` 中定义的分析维度（如 "long-base consolidation"、"volume signature"、"breakout impulse" 等）。一条规律必须**绑定至少 1 个视角维度的 dimension key**，否则无法被检索和归类。
- **Definition（数学定义）**：规律必须可被**代码化**或至少可代码化路径明确。"价格在某区间反复测试后突破" → 必须给出"区间宽度阈值、测试次数阈值、突破幅度阈值"的可量化规则草案。
- **Evidence（证据）**：必须包含**支持集**（跨独立 batch 的 figure-level support）。v2.3 移除了强制反例集要求（LLM-only 仅看上涨图，反例不可达）。

> **奥卡姆剃刀**：能用一条规律解释的，不要拆成两条。两条规律若 Perspective 重合且 Definition 在阈值层面只是参数差异 → 合并为一条 + 参数变体。

### 0.3 防幸存者偏差的硬约束（贯穿全文）

本系统从设计层面而非"建议层面"对抗幸存者偏差：

1. 每次新分析必须执行"**全规律巡检**"：把新一批图与现有所有规律交叉比对，逐条更新支持/反例集。
2. 状态机层面：规律不能从 `hypothesis` 直接跳到 `validated`，必须走 `partially-validated`，且需累计 K 张独立 chart（不同 runId）支持。

---

## A. 文件布局

### A.1 顶层目录结构

```
experiments/analyze_stock_charts/
├── stock_pattern_library/              ← 主规律库（跨 run 持久化）
│   ├── README.md                       ← 库的使用说明（IO 协议精简版）
│   ├── _meta/
│   │   ├── charts_index.md             ← 所有曾被分析过的 chart 全局索引
│   │   ├── run_history.md              ← 所有 run 的时间线索引
│   │   ├── dimensions_link.md          ← 引用 01_analysis_dimensions.md 的视角维度键值表
│   │   ├── chart_classes.md            ← chart_class 注册表（详见 §A.5）
│   │   └── schema_version.md           ← 规律库 schema 版本号 + 升级历史
│   ├── patterns/                       ← 已 validated / partially-validated 的规律
│   │   ├── <chart_class_a>/            ← 按 chart_class 分桶
│   │   │   ├── R-0001__name.md
│   │   │   └── R-0002__name.md
│   │   ├── <chart_class_b>/
│   │   │   └── R-0010__name.md
│   │   └── _retired/                   ← user 主动归档的规律（v2.3 起仅 user 手动操作）
│   │       └── R-00xx__<name>.md
│   └── conflicts/                      ← 冲突标记：两条规律给出相反预测的记录
│       └── C-0001__<patternA>_vs_<patternB>.md
│
├── stock_pattern_runs/                 ← 单次分析独立文档（每次运行一个目录）
│   ├── 2026-05-04_153022_a3f9b/        ← runId
│   │   ├── input.md                    ← 本次输入 chart 列表 + 元信息
│   │   ├── findings.md                 ← 本次发现（核心产出）
│   │   ├── crosscheck.md               ← 本批 chart × 历史规律 命中矩阵
│   │   ├── proposals.md                ← 本次建议的库变更（pending → 写库前的 staging）
│   │   └── written.md                  ← 最终落库后写入了什么的 audit log
│   └── 2026-05-04_181544_b7e22/
│       └── ...
│
└── images_cache/                       ← v2.1 新增：ephemeral 输入归档（粘贴/拖入图片落地）
    └── <run_id>/                       ← 与 stock_pattern_runs/<run_id>/ 共享 run_id
        └── *.png / *.jpg               ← 由 SKILL 在 Step 0 阶段写入，供后续步骤引用
```

**chart_class 物理切分**（详见 §D）：library 按 `chart_class` 分桶。`dim_sim` 比较只在同 class 内进行；跨 class 同义规律默认严格隔离（接受冗余），user 可 ad-hoc 合并。

### A.2 命名规范

| 实体 | 规则 | 示例 |
|---|---|---|
| **runId** | `YYYY-MM-DD_HHMMSS_<chartset_hash5>` | `2026-05-04_153022_a3f9b` |
| **chartset_hash** | 按文件名排序后拼接、SHA1 取前 5 位（小写 hex） | `a3f9b` |
| **chart_id** | `C-<runId缩写>-<seq>` 全局唯一 | `C-0504a3f-1`（即 `2026-05-04_a3f9b` 第 1 张） |
| **pattern_id** | `R-<4 位递增序号>` | `R-0023` |
| **conflict_id** | `C-<4 位递增序号>` | `C-0007` |
| **pattern 文件名** | `R-<id>__<snake_case_short_name>.md` | `R-0023__pre_breakout_volume_dryup.md` |

> **runId 选择 chartset_hash 的理由**：同一批图在不同时间被重新分析（追加证据）时，时间戳不同但 hash 相同 → 索引能立刻识别"这是同一批图的第 N 次复审"。

### A.3 索引文件 (`_meta/charts_index.md`) 的最小结构

```markdown
# Charts Index

| chart_id | source_file | chart_class | summary_tags | first_used_run | last_used_run | included_in_patterns |
|---|---|---|---|---|---|---|
| C-0504a3f-1 | image-cache/.../1.png | long_base_breakout | long-base, big-breakout, high-vol-spike | 2026-05-04_153022_a3f9b | 2026-05-04_153022_a3f9b | R-0001, R-0007 |
| C-0504a3f-2 | image-cache/.../2.png | v_reversal | u-shape-recovery, no-pre-vol | 2026-05-04_153022_a3f9b | 2026-05-04_153022_a3f9b | R-0010 |
```

`summary_tags` 是 4-8 个**视角维度命中**的快速摘要 — 让未来 agent 在不重新加载图片的情况下，仅凭 tags 就能筛选"哪些图与某规律相关"。

`chart_class` 列保存 overviewer 阶段为该图分配的 dominant class 标签（free-form，例如 `long_base_breakout`）。

### A.4 `run_history.md` 的最小结构

```markdown
# Run History

| runId | timestamp | chart_count | n_new_patterns | n_updated_patterns | n_retired_patterns | conflicts_opened |
|---|---|---|---|---|---|---|
| 2026-05-04_153022_a3f9b | 2026-05-04T15:30:22Z | 9 | 3 | 5 | 0 | 1 |
```

### A.5 `_meta/chart_classes.md`（class registry）

**用途**：维护已注册的 chart_class 列表 + descriptions。lead 在每次 batch 的 T1.5 节点（详见 SKILL.md §5.2bis）读它做合并候选检索；user 在 AskUserQuestion 中决议；synthesizer 写库时直接用 `final_chart_class`，不读 chart_classes.md 做同义判定。

**v2.2 schema 变化**：
- ❌ 移除 `aliases` 字段（性能 cache 价值随库扩大递减；user 决议替代）
- ❌ 移除 `## proposed classes` 段（决议同步落地，无需暂存）
- ✅ 新增 `## decision history` 段（跨 run 审计追溯 user 决议历史）

**新 schema 模板**：

````markdown
# Chart Classes Registry

> 本 batch 视觉类别（chart_class）的活跃注册表。每个 chart_class 对应 `patterns/<class_name>/` 一个目录。
> 决议由 user 在每次 batch 的 T1.5 节点完成（lead 协调），synthesizer 写库时直接使用 final_chart_class。

## active classes

| class_name | description | first_seen_run | patterns_count | last_updated |
|---|---|---|---|---|
| long_base_breakout | 宽幅区间内的低波动横盘 ≥40 日后突破 | 2026-05-06_112923_0bea3 | 5 | 2026-05-07_142311 |
| v_reversal | 深 V 反转后上涨 | 2026-05-10_xxxxxx_xxxxx | 3 | 2026-05-15_xxxxxx |

## decision history

> 每次 T1.5 决议追加一行（含分支、最终结果、所属 run）。供审计与跨 run 追溯用。

| run_id | dominant_class | final_chart_class | branch | user_choice |
|---|---|---|---|---|
| 2026-05-06_112923_0bea3 | long_consolidation_breakout | long_base_breakout | B-merge | merge_into |
````

**字段语义**：
- `class_name`：chart_class 主名（unique）
- `description`：1 行描述（lead 在新建分支时用 first_impression 概括）
- `first_seen_run`：首次出现的 runId
- `patterns_count`：当前 class 下的 pattern 数（仅 active / partially-validated / validated 状态）
- `last_updated`：最近一次 patterns_count 变更或 last_updated 触碰的时间戳
- decision history `branch`：A-existing / B-merge / B-new / C-no-candidate
- decision history `user_choice`：new / merge_into（branch A / C 时为空，notification_only）

**演化规则**：
- 新 class 由 lead 在 T1.5 决议 (B-new / C 分支) 后追加到 `## active classes`，写入即生效
- 现有 class 的 `patterns_count` 由 synthesizer 在 §5 写库后增量更新
- decision history 由 lead 在每次 T1.5 完成时追加 1 行
- class 不引入自动拆分机制（user 想拆分时手动改本文件 + 移动 patterns 子目录文件）

---

## B. 规律 schema（核心）

每条规律一个 markdown 文件，frontmatter 为 yaml，正文为可读说明。**字段强制全部存在**（可为空数组/null，但 key 不能缺）。

### B.1 规律文件模板

```markdown
---
# === 标识 ===
pattern_id: R-0001
name: "Long-base consolidation followed by volume breakout"
short_name: long_base_volume_breakout
schema_version: 1.0

# === 视角维度（与 01_analysis_dimensions.md 对齐）===
dimensions:
  primary: price_structure.long_base_consolidation       # 必需，至少 1 个
  secondary:
    - volume.pre_breakout_dryup
    - volume.breakout_spike
    - moving_average.curl_up_through_base

# === 一句话描述 + 详细描述 ===
one_liner: "价格在窄幅区间长期横盘（>= N 根 K 线）后，伴随放量首次突破区间上沿。"
description: |
  形态分三段：
  (1) 横盘段：close 价标准差 / 中位价 < 阈值 σ_max，持续 >= n_bars_min 根
  (2) 缩量段：横盘后期 m 根 K 线的成交量均值 < 横盘段均值 × ratio_dryup
  (3) 突破段：单根或连续 k 根 K 线收盘价 > 横盘段最高价 × (1 + breakout_pct_min)，
       且突破日成交量 >= 横盘均值 × ratio_spike

# === 数学定义 / 可代码化路径 ===
formalization:
  status: codifiable                  # codifiable | partial | sketch-only
  pseudocode: |
    base_window = bars[-(n_bars_min + lookback) : -lookback]
    sigma_norm = std(base_window.close) / median(base_window.close)
    if sigma_norm < SIGMA_MAX:
        base = base_window
        ...
  proposed_factors:                   # 建议新增的因子（供 BreakoutStrategy/factor_registry.py 参考）
    - name: base_consolidation_score
      formula: "1 - clamp(sigma_norm / SIGMA_MAX, 0, 1)"
    - name: pre_bo_vol_dryup_ratio
      formula: "mean(vol[-m:]) / mean(vol[base_window])"
  thresholds:
    SIGMA_MAX: 0.04
    n_bars_min: 60
    ratio_dryup: 0.6
    ratio_spike: 3.0
    breakout_pct_min: 0.05

# === 证据：支持 / 反例 / 应中未中 ===
evidence:
  # legacy 字段（保留向后兼容，仅作 audit trail；不再用作晋级判定）
  supports:                            # [legacy / deprecated for promotion logic]
    - chart_id: C-0504a3f-1
      run_id: 2026-05-04_153022_a3f9b
      observed:
        sigma_norm_est: 0.03
        base_bars_est: 80
        breakout_pct: 0.18
      notes: "Peak [3]→[2,5]→[2,6]→[7] 阶梯式放量，符合三段结构"
    - chart_id: C-0504a3f-4
      run_id: 2026-05-04_153022_a3f9b
      ...
  no_data_yet:                         # [legacy / deprecated for promotion logic] 无法判定的图（数据不足、视角不适用）
    - chart_id: C-0504a3f-9
      reason: "图截取窗口过短，无法判断 base 长度"

  # 双层 evidence 字段（晋级判定真实数据源，详见 §C.7）
  per_batch_observations:                                # 每个 batch 的 figure-level supports
    - batch_id: 2026-05-04-xxxx
      figure_supports: [C-xxxx-1, C-xxxx-3, C-xxxx-5]    # 该 batch 内支持本规律的图
    - batch_id: 2026-05-15-yyyy
      figure_supports: [C-yyyy-1, C-yyyy-2, C-yyyy-3, C-yyyy-4, C-yyyy-5]
  distinct_batches_supported: 2                          # 至少 1 张图支持的独立 batch 数（晋级判定数据源）
  total_figure_supports: 8                               # 跨所有 batch 的 figure-level support 总数（3 + 5）

# === 早期 vs 滞后信号 ===
signal_timing:
  type: early                         # early | concurrent | lagging
  detectable_before_breakout: true
  earliest_detection_offset_bars: -5  # 突破前 5 根 K 线即可初步识别（dryup 段）

# === 置信度 ===
confidence:
  status: partially-validated         # hypothesis | partially-validated | validated
  n_supports: 2
  confidence_score: 0.40              # supports / (supports + weight)

# === 关联规律 ===
relations:
  complements:                        # 互补：同时成立时增强预测
    - R-0007                          # "MA 上翘穿透横盘区"
  contradicts:                        # 矛盾：与本规律给出相反预测
    - R-0019                          # "假突破 — 长横盘后首根突破日量小"
  subsumes: []                        # 本规律是更一般情形，子规律 ID
  subsumed_by: []                     # 本规律是某更一般规律的特例

# === 元信息 ===
meta:
  created_at: 2026-05-04T15:30:22Z
  created_in_run: 2026-05-04_153022_a3f9b
  last_updated_at: 2026-05-04T15:30:22Z
  last_updated_in_run: 2026-05-04_153022_a3f9b
  version: 1.0.0                      # 升级 minor: 阈值微调 / patch: 文字修订 / major: schema 不兼容
  authors:
    - agent: <下游团队的 agent 名>
      run: 2026-05-04_153022_a3f9b
---

# R-0001: Long-base consolidation followed by volume breakout

（正文：可读详述，含图示意 ASCII / 链接到 chart_id 的截图路径 / 与其他规律的对比讨论）
```

### B.2 字段语义速查表（给 architect 直接拿去用）

| 字段路径 | 类型 | 含义 | 强制 |
|---|---|---|---|
| `pattern_id` | str | 全局唯一 ID | ✓ |
| `name` / `short_name` | str | 人可读名 / 文件名片段 | ✓ |
| `dimensions.primary` | str (key) | 主视角维度（指向 01_analysis_dimensions.md） | ✓ |
| `dimensions.secondary` | list[str] | 辅助视角维度 | 默认 [] |
| `one_liner` | str | ≤ 140 字一句话描述 | ✓ |
| `description` | str (multiline) | 详细形态描述 | ✓ |
| `formalization.status` | enum | codifiable / partial / sketch-only | ✓ |
| `formalization.pseudocode` | str | 至少给出可代码化路径 | partial+ 时必填 |
| `formalization.proposed_factors` | list | 建议新增因子（供 factor_registry 参考） | 默认 [] |
| `formalization.thresholds` | dict | 数值阈值 | codifiable 时必填 |
| `evidence.supports` | list | 支持本规律的 chart 列表（含具体观测，legacy audit trail） | ✓（可为 []） |
| `evidence.no_data_yet` | list | 无法判定的 chart | 默认 [] |
| `signal_timing.type` | enum | early / concurrent / lagging | ✓ |
| `signal_timing.earliest_detection_offset_bars` | int | 早期识别提前量（负数） | early 时必填 |
| `confidence.status` | enum | hypothesis / partially-validated / validated | ✓ |
| `confidence.n_supports` | int | 计数 | ✓（自动维护） |
| `evidence.per_batch_observations` | list | 每个 batch 的 figure-level supports（详见 §C.7） | ✓（可为 []） |
| `evidence.distinct_batches_supported` | int | 至少 1 张图支持的独立 batch 数（晋级判定数据源） | ✓（自动维护） |
| `evidence.total_figure_supports` | int | 跨所有 batch 的 figure-level support 总数（晋级判定数据源） | ✓（自动维护） |
| `confidence.confidence_score` | float [0,1] | `supports / total_weight` | ✓（自动计算） |
| `relations.complements` / `contradicts` / `subsumes` / `subsumed_by` | list[pattern_id] | 关联 | 默认 [] |
| `meta.created_at` / `last_updated_at` | ISO 8601 | 时间戳 | ✓ |
| `meta.version` | semver | 版本号 | ✓ |

### B.3 视角维度的命名约定

`dimensions.primary` 字段使用**自然语言 finding 名**。dim-expert 自由命名 finding，由 synthesizer 跨 run 用 LLM 语义聚类（详见 §C.2）。

**理由**：strict 格式约束会窄化 dim-expert 的 finding 表达，且 LLM 语义聚类天然能做归一化。同义异名（"volume.spike" vs "volume.surge"）由 LLM 判定为同 finding，不依赖 strict 命名。

**兼容性**：现有 patterns（如有）的 strict 格式 dimensions.primary 仍然有效；synthesizer 在比较时把它视为自然语言 finding 名（视为 1 个 token 的描述）。

**写法建议**（不强制）：
- 短描述（≤ 8 词）："short consolidation with volume dryup" / "deep V with high left wick"
- 避免引用 codebase 因子名（如 "high pre_vol"）— v2 完全和 factor_registry 解耦

**dimensions_link.md 在 v2 的维护方式**：

> 注：`_meta/dimensions_link.md` 在 v2 仍维护反向索引，但其键值由 synthesizer 在 LLM 语义聚类后用 cluster 名作为正式 key（不再用 strict `<category>.<subcategory>`）。lead T1.5 已完成 chart_class 决议；synthesizer 直接用 spawn prompt 注入的 final_chart_class，不参与同义判断。

---

## C. 增量整合算法（关键）

### C.1 总流程（决策树）

```
[本次 run 完成 N 个候选 patterns + N 个 crosscheck 结果]
                          │
                          ▼
   ┌──────────────────────────────────────────┐
   │ Phase 1: 候选规律 vs 现有规律 — 查重     │
   └──────────────────────────────────────────┘
                          │
       For each candidate Pcand:
                          │
                          ▼
   ① 计算 similarity(Pcand, Pexisting) — 见 C.2
                          │
   ② 按相似度阈值分桶：
      ├─ sim >= 0.85 → MERGE 候选         → 走 C.3 合并流程
      ├─ 0.50 <= sim < 0.85 → VARIANT 候选 → 走 C.4 变体流程
      ├─ 0.20 <= sim < 0.50 → COMPLEMENT/CONTRADICT → 走 C.5 关联记录
      └─ sim < 0.20 → NEW                   → 走 C.6 新增流程
                          │
                          ▼
   ┌──────────────────────────────────────────┐
   │ Phase 2: 现有规律的状态更新（巡检）       │
   └──────────────────────────────────────────┘
                          │
       For each existing Pattern P:
            读取本次 crosscheck 中 P 的命中情况
            ① supports++
            ② 重算 confidence_score
            ③ 应用状态机（C.7）→ 可能升级
            ④ 检查 conflicts（C.8）
                          │
                          ▼
   ┌──────────────────────────────────────────┐
   │ Phase 3: 库膨胀控制（C.9）               │
   └──────────────────────────────────────────┘
   只在 patterns/ 总数变化时触发：
      若某 dimension.primary 下规律数 > N_dim_max（建议 12）
        → 触发同维度规律相似度全量比对，建议 MERGE 候选给人工审核
```

### C.2 相似度判定函数（LLM 语义聚类 + Jaccard fallback）

**当前规则**：
```
def dim_sim(p1, p2, chart_class):
    # 前提：p1, p2 必须同 chart_class（跨 class 不比较）
    if p1.chart_class != p2.chart_class:
        return 0.0  # 不视为相似（跨 class 严格隔离，详见 §D.3）
    
    # 第一层：Jaccard 快速 fallback（如 dimensions.primary 严格相等 → 直接判同义）
    jaccard = len(set(p1.primary) & set(p2.primary)) / max(1, len(set(p1.primary) | set(p2.primary)))
    if jaccard >= 0.95:
        return jaccard  # 跳过 LLM
    
    # 第二层：LLM 语义聚类（synthesizer 是 opus，天然能做）
    # 由 synthesizer 在写库时用自然语言判断
    # prompt: "p1 描述: <p1.description>\np2 描述: <p2.description>\n它们是否描述同一规律？输出 [0.0-1.0] 相似度"
    return llm_semantic_score(p1, p2)
```

**配合 chart_class 切分**：dim_sim 比较只在同 class 内进行（§D.3），N（同 class 内 patterns 数）始终是小数（每类 20-50），LLM 调用成本可控。

**对原有 sim 阈值的影响**：MERGE / VARIANT / COMPLEMENT/CONTRADICT / NEW 阈值（§C.3-C.6）保持不变（0.85 / 0.50 / 0.20）；只是 sim 计算方式从 Jaccard 改为 LLM。

### C.3 MERGE 流程（sim ≥ 0.85）

```python
def merge(P_existing, P_candidate):
    # 1. supports 取并集（按 chart_id 去重）
    P_existing.evidence.supports = union_by_chart_id(...)

    # 2. thresholds 合并：按"覆盖更多 supports"取较宽松值，记录到 versioning notes
    P_existing.formalization.thresholds = wider_envelope(...)

    # 3. one_liner / description：保留 existing，把 candidate 的差异写入 description 末尾"## Variants observed"
    # 4. version: minor++（阈值变化）或 patch++（仅文字）
    # 5. last_updated_at / last_updated_in_run 更新
    # 6. authors 追加
    # 7. 不动 confidence.status — 但重算 confidence_score
```

### C.4 VARIANT 流程（0.50 ≤ sim < 0.85）

候选不与任何现有规律完全合并，但**不应**作为独立规律存在 — 作为现有规律的子变体：

- 不创建新文件
- 在 `P_existing.description` 增加 `## Variants` 段，描述候选的差异点
- 在 `relations.subsumes` 末尾追加候选的临时 ID（不分配 R-xxxx，只记录 description）

> **例外**：如果候选的 `signal_timing.type` 与现有不同（如一个 early、一个 lagging），即便其他相似 — 拆分为两条规律，互相 `subsumed_by` 一个父规律（如有）。

### C.5 COMPLEMENT/CONTRADICT 流程（0.20 ≤ sim < 0.50）

```
判断方向：
  - 若 dim_sim 高但两条对同一种 setup 给出相反结论 → CONTRADICT
    → 写入 conflicts/C-xxxx__<A>_vs_<B>.md（C.8 详述）
    → 在双方 relations.contradicts 互加引用
  - 若 dim_sim 中等且能联合预测 → COMPLEMENT
    → 在双方 relations.complements 互加引用，不开 conflict
  - 否则不建关联（避免噪音关联）
```

### C.6 NEW 流程（sim < 0.20）

```
1. 分配新 pattern_id（读取现有 R-xxxx 最大值 + 1）
2. 创建文件 patterns/R-xxxx__<short_name>.md
3. confidence.status 强制 = "hypothesis"
4. n_supports = len(supports)，但若 < 2 → 仍为 hypothesis；
   若 supports 跨越 1 个 batch（distinct_batches_supported < 2）→ 永远不能跳到 partially-validated
```

### C.7 状态机（confidence.status）— 双层 evidence

**双层 evidence schema**：

```yaml
evidence:
  # 单 batch 内 figure-level
  per_batch_observations:
    - batch_id: 2026-05-04-xxxx
      figure_supports: [C-xxxx-1, C-xxxx-3, C-xxxx-5]   # 该 batch 内支持本规律的图
    - batch_id: 2026-05-15-yyyy
      figure_supports: [C-yyyy-1, C-yyyy-2, C-yyyy-3, C-yyyy-4, C-yyyy-5]
  
  # 跨 batch 累积
  distinct_batches_supported: 2              # 至少 1 张图支持的独立 batch 数
  total_figure_supports: 8                   # 跨所有 batch 的 figure-level support 总数（3 + 5）
```

**状态机晋级条件**（v2.3 单向晋级，无降级路径）：

| 晋级目标 | 条件 |
|---|---|
| `partially-validated` | `distinct_batches_supported ≥ 2` AND `total_figure_supports ≥ 4` |
| `validated` | `distinct_batches_supported ≥ 3` AND `total_figure_supports ≥ 9` |

v2.3：状态机简化为单向晋级。`hypothesis → partially-validated → validated`，不再有自动降级路径。
- 移除 `disputed`：基于 `counterexamples ≥ 1`，但本 skill LLM-only 仅看上涨图，counterexamples 不可达
- 移除 `refuted`：基于 `should_have_matched_but_failed`，与"充分非必要"前提冲突
- `_retired/` 仅 user 主动归档（不再由状态机自动移入）

**理由**：双层让"单 batch 5/5 命中" vs "5 个 batch 各 1/5 命中"在 evidence 累积时区分开（前者是单批次幸存者偏差风险，后者是跨批次独立验证）。

> **v2.1 single-group cap**：`cross_group_diversity == false` 的 finding 入库时 `confidence_cap = medium`，永远不能升 `validated`（即使 `distinct_batches_supported ≥ 3` + 0 反例）。
> 这类 finding 仍可达 `partially-validated`，作为 user 探索素材或未来跨 batch 联立的输入。

### C.8 冲突处理（C-xxxx 文件）

两条规律给出相反预测时，开 `conflicts/C-xxxx__<A>_vs_<B>.md`：

```yaml
---
conflict_id: C-0001
pattern_a: R-0007
pattern_b: R-0019
opened_in_run: 2026-05-04_153022_a3f9b
status: open                  # open | resolved | abandoned
last_reviewed_at: 2026-05-04T15:30:22Z

# 在哪些 chart 上两规律分别命中且预测相反
divergence_charts:
  - chart_id: C-0504a3f-7
    A_predicts: "breakout valid"
    B_predicts: "false breakout"
    actual_outcome: "false breakout"   # 若图序列允许后验，写入；否则 unknown
    favors: B

resolution:
  hypothesis: "B 更精确：A 在 vol < 2× 均值 时不应触发"
  proposed_action: "为 R-0007 增加 ratio_spike >= 2.0 前置条件"
  human_review_required: true
---
```

**冲突触发再分析机制**（与 team-architect 对齐）：

冲突一旦开启（status=open），会形成对**未来所有 run 的硬性指令**，不会被静默遗忘：

```
每次 run 的 READ 协议 STEP 6 加载 conflicts/*.md (status=open) 后：
  for each open_conflict:
      把 open_conflict.divergence_charts 中已有的 chart_id 摘要载入上下文
      把 open_conflict.pattern_a / pattern_b 标注为"重点观察对象"

run 进行时（pattern-matcher 阶段）：
  for chart in this_batch:
      for open_conflict where chart 同时命中 pattern_a 和 pattern_b 的 dimensions.primary:
          强制要求 agent 在 crosscheck.md 显式记录：
            - 本 chart 是否能裁决该冲突
            - 若能：actual_outcome + favors 字段
            - 若不能：写明缺什么数据（提示 future runs 寻找）

run 结束时（library-curator 阶段）：
  for each open_conflict:
      若新增 ≥ 1 条 actual_outcome 已知的 divergence_chart 且全部 favors 同一方：
          → 提议 status=resolved，写入 proposals.md，由 writer 落库
      若开启已超过 N 个 run 仍无裁决证据：
          → 标注 stale=true，提醒 stock-domain-expert 是否要 abandon
```

> **关键**：冲突不是被动登记，而是"对下一次 run 的输入需求"。这与 team-architect 倾向的"标记冲突 + 触发再分析"完全对齐 — 触发的方式就是把冲突变成下次 run 的明确观察任务。

### C.9 库膨胀控制

```
每次 run 结束后：
  group_by_dimension = group(patterns, key=dimensions.primary)
  for dim, plist in group_by_dimension.items():
      if len(plist) > N_dim_max:           # 默认 N_dim_max = 12
          # 全量两两相似度
          sim_matrix = pairwise_similarity(plist)
          # 找 sim >= 0.6 的 cluster
          clusters = greedy_cluster(sim_matrix, threshold=0.6)
          for cluster in clusters:
              if len(cluster) >= 2:
                  open_consolidation_proposal(cluster)
                  # 不自动合并 — 写入 proposals.md 留待人工审核
```

> 不自动合并的理由：库膨胀的本质是"视角维度颗粒度过细" — 这是 stock-domain-expert 该决定的，不应由规律库自己悄悄削减信息量。

### C.10 强制全规律巡检（防偏差核心）

**每次 run 结束前必须执行**：

```python
def crosscheck_all_patterns(this_run_charts, all_existing_patterns):
    matrix = {}  # chart_id × pattern_id → enum
    for chart in this_run_charts:
        for P in all_existing_patterns:
            label = agent_judges(chart, P)  # one of (v2.3: 3 labels):
            # SUPPORT      — chart 完全符合 P
            # IRRELEVANT   — P 的视角维度不适用于这张图（含"满足部分条件但不构成支持"）
            # NO_DATA      — 无法判定（窗口不够、信息缺失）
            matrix[(chart, P)] = label

    # 写入 runs/<runId>/crosscheck.md
    # 然后用 matrix 中 SUPPORT 标签去更新 P.evidence.*
```

> **agent 不能跳过任何 (chart, pattern) 组合**。库膨胀到 50+ 条时这是 9 × 50 = 450 次判读，但**这是质量底线** — 不允许用"显然不相关"草率跳过。`IRRELEVANT` 标签必须给出 1 行理由，记录到 crosscheck.md。
>
> **v2.3 标签集变化**：原 4 标签（SUPPORT / COUNTER / IRRELEVANT / NO_DATA）缩减为 3 标签。`COUNTER`（chart 满足 trigger 却不涨）在仅看上涨图的 LLM-only 设定下不可达，已删除；同源含义（chart 不构成支持）由 `IRRELEVANT` 承载。

---

## D. chart_class 物理切分 + batch 协议

### D.1 概念

- **chart_class**：K 线图的形态类别（如 `long_base_breakout` / `v_reversal`）。每张图在 overviewer 阶段获得一个 chart_class 标签。
- **batch**：每次 skill 调用接收的 N 张图（N≈3-7 甜区（5 推荐），详见 §D.4）。一个 batch 必须**dominant 同 class**（同质性校验见 §D.5）。

### D.2 batch 流程

```
1. user 提供 N 张图（user 自认同类）
2. overviewer (opus) 看图 → 给每张图打 chart_class 标签 → 计算 dominant class + outlier
3. 同质性校验（§D.5）：通过则进入 dim-expert；不通过则 reject 或 warn
4. 4 个 dim-expert 各看全部 N 张图，做 cross-image 对比分析（每个 dim-expert 独立 context，~24K visual token / expert）
5. dim-expert 报告 supports / exceptions per-image 集合 + 软建议 K=3/5 cutoff
6. synthesizer 整合 → 写入 patterns/<final_chart_class>/R-xxxx.md（lead 在 T1.5 节点已完成 chart_class 决议，详见 SKILL.md §5.2bis）
7. 跨 batch 累积 distinct_batches_supported → 状态机晋级
```

### D.3 跨 class 隔离规则

- `dim_sim(p1, p2)` 只在 `p1.chart_class == p2.chart_class` 时计算；跨 class 返回 0
- 同义规律在多个 class 重复存储（接受冗余）
- user 可在 review 时 ad-hoc 合并（修改 `chart_classes.md` + 给 pattern 加 `cross_class_link` 字段）
- skill **不主动**做跨 class 检测（避免 O(N_classes × patterns_per_class) 的 LLM 比对成本）

### D.4 N 选择策略

| N | 处理 |
|---|---|
| N < 3 | 拒绝（提示 user 至少 3 张同类图）|
| 3 ≤ N ≤ 7 | 直接处理 |
| N = 8 或 9 | 警告 user "可能 attention dilution，建议拆为 5+4 两个 batch 顺序运行"，user 决议 |
| N ≥ 10 | 拒绝（提示拆 batch 后多次调用）|

### D.5 batch 同质性校验

overviewer 给每张图打 chart_class 标签后，按 outlier 比例分层：

| outlier 比例 | 处理 |
|---|---|
| ≤ 20% (1/5) | 保留为反例图，dim-expert 显式标记为 odd-one-out |
| 20-40% (2/5) | 警告 user "图 X, Y 不属于 dominant class Z，建议剔除或拆 batch"，user 决议 |
| ≥ 40% (≥ 2/5 当 N=5) | 拒绝（class 混杂程度太高，无 dominant class）|

### D.6 跨 batch 防重复

skill 不做技术识别（不引入 MD5 / pHash / CLIP fingerprint）。SKILL.md frontmatter 加 user-facing 提示：

> 多次调用 skill 时请避免重复提供相同的 batch（distinct_batches 累积要求独立证据；重复 batch 会假性增强 confidence）。

**理由**：完美识别需重型方案，轻型方案覆盖率有限；user 主动控制 batch 输入，无意重复概率低；真正的反幸存者偏差靠 chart_class 切分 + cross-batch K 累积阈值。

### D.7 chart_class 命名机制

- overviewer 给 free-form chart_class 名（如 `long_consolidation_lift_off`）
- chart_class 决议由 lead 在 T1.5 完成（详见 SKILL.md §5.2bis）：
  - 同名命中（A）→ 直接合并入该 class
  - LLM 推荐合并候选（B）→ user 选新建或合并
  - 无候选（C）→ 直接新建
- patterns 直接写入 `patterns/<final_chart_class>/`，无 `_pending/` 暂存
- aliases 概念已消除（v2.2）

### D.8 chart_class 拆分机制

**不引入自动拆分**。当某 class patterns 累积过多（如 50+），由 user 自行决议是否拆分（手动修改 `chart_classes.md` + 移动 `patterns/<class>/` 文件）。理由：class 粒度本质是分类学问题，user 比 LLM 更适合判断。

---

## E. 单次分析独立文档结构

每次 run 一个目录：`stock_pattern_runs/<runId>/`。包含 5 个文件：

### E.1 `input.md`

```markdown
---
run_id: 2026-05-04_153022_a3f9b
timestamp: 2026-05-04T15:30:22Z
chart_count: 9
chartset_hash: a3f9b
chart_files:
  - path: /home/yu/.claude/image-cache/.../1.png
    chart_id: C-0504a3f-1
    notes: "黑三角 8 个 peak，蓝框对应突破后的 [0,1] / [2,5] / [2,6] / [3] / [7]"
  - path: ...
analyst_team_config: ~/.claude/teams/stock-analyst/config.json
schema_version_used: 1.0
---

# Input Snapshot

(本次输入的 chart 元信息、初始观察、用户备注)
```

### E.2 `findings.md`（核心产出）

```markdown
---
run_id: 2026-05-04_153022_a3f9b
finding_count: 6
new_pattern_candidates: 3
updates_to_existing: 5
---

# Findings (Run 2026-05-04_153022_a3f9b)

## 1. 本次发现摘要（≤ 200 字）
...

## 2. 按 chart 的逐张分析
### C-0504a3f-1
- **summary_tags**: long-base, big-breakout, vol-spike, ma-curl-up
- **观察的视角**:
  - price_structure.long_base_consolidation: 命中（80 根 K 线、σ_norm ≈ 0.03）
  - volume.breakout_spike: 命中（突破日 vol ≈ 8× 均值）
  - volume.pre_breakout_dryup: **不明显**
- **触发的规律**: R-0001 (SUPPORT, 但 dryup 段疑似反例)、R-0007 (SUPPORT)
- **新规律候选**: 无

### C-0504a3f-2
...

## 3. 跨图共性 / 差异讨论
...
```

### E.3 `crosscheck.md`（命中矩阵）

```markdown
# Crosscheck Matrix (Run 2026-05-04_153022_a3f9b)

| chart_id ↓ \ pattern → | R-0001 | R-0002 | R-0007 | R-0019 | ... |
|---|---|---|---|---|---|
| C-0504a3f-1 | SUPPORT (σ=0.03) | IRRELEVANT (无平台) | SUPPORT | IRRELEVANT (vol > 2×，量能特征不符) | ... |
| C-0504a3f-2 | IRRELEVANT (long-base 命中但量能不足) | ... | ... | ... | ... |
| C-0504a3f-3 | NO_DATA (窗口短) | ... | ... | ... | ... |
| ... |

## 详细备注
- (C-0504a3f-2, R-0001): IRRELEVANT — 横盘段达标，但突破日 vol 仅 1.2× 均值，未达 ratio_spike 阈值（构不成 SUPPORT，但也非反例）。
- (C-0504a3f-3, R-0001): NO_DATA — 图截取窗口仅 ~40 根 K 线，base 长度不可判。
- ...
```

### E.4 `proposals.md`（写库前的 staging）

```markdown
---
run_id: 2026-05-04_153022_a3f9b
status: pending                   # pending | applied | rolled_back
---

# Proposals to Library

## Phase 1: 新增规律
### Proposal P-1: R-NEW-A
- 命名: pre_breakout_volume_dryup_then_spike
- dimensions: volume.pre_breakout_dryup + volume.breakout_spike
- 与现有最相似规律: R-0001 (sim ≈ 0.62) → 走 VARIANT 流程，不新增独立 R-id
- 决议: 合并到 R-0001.description 的 ## Variants 段

### Proposal P-2: ...

## Phase 2: 对现有规律的更新
- R-0001:
  - supports += [C-0504a3f-1, C-0504a3f-4]
  - confidence_score 重算: 0.42 → 0.51
  - status: hypothesis → partially-validated（distinct_batches_supported 达到 2 AND total_figure_supports ≥ 4）
- R-0007: ...

## Phase 3: 状态变更建议
- R-0019: supports 累积不足 → 保持 hypothesis

## Phase 4: 冲突
- 新开 C-0001 (R-0007 vs R-0019) — 在 C-0504a3f-7 上预测相反
```

### E.5 `written.md`（落库后 audit log）

```markdown
---
run_id: 2026-05-04_153022_a3f9b
applied_at: 2026-05-04T15:48:11Z
---

# Write Audit Log

## Files modified
- patterns/R-0001__long_base_volume_breakout.md (version 1.0.0 → 1.1.0)
- patterns/R-0007__ma_curl_up_through_base.md (version 1.0.0 → 1.0.1)
- patterns/R-0019__false_breakout_low_volume.md (status: hypothesis → under-review)

## Files created
- patterns/R-0023__volume_dryup_terminal_signature.md
- conflicts/C-0001__R-0007_vs_R-0019.md

## Files moved (retired)
- (none)

## Index updates
- _meta/charts_index.md: +9 rows
- _meta/run_history.md: +1 row
- _meta/dimensions_link.md: +1 dimension first-use (volume.pre_breakout_dryup)
```

---

## F. IO 协议（agent 团队的读写约定）

### F.1 读取协议（每次 run 开始前必做，按顺序）

```
STEP 1: 读 experiments/analyze_stock_charts/stock_pattern_library/_meta/schema_version.md
        → 校验 agent 知道的 schema_version 与库当前版本兼容
        → 不兼容时 abort + 报告

STEP 2: 读 experiments/analyze_stock_charts/stock_pattern_library/_meta/run_history.md
        → 上次 run 的时间、本次是第几次

STEP 3: 读 experiments/analyze_stock_charts/stock_pattern_library/_meta/dimensions_link.md
        → 知道当前所有视角维度键值

STEP 4: 读 .claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md
        → 校验所有 patterns 引用的 dimensions 都在此文档中存在

STEP 5: 全量读 experiments/analyze_stock_charts/stock_pattern_library/patterns/*.md
        (跳过 _retired/)
        → 加载所有 pattern 的 frontmatter + one_liner（不必读 full description 节省 token）
        → 仅当 crosscheck 阶段命中某 pattern 时再加载其完整描述

STEP 6: 全量读 experiments/analyze_stock_charts/stock_pattern_library/conflicts/*.md
        (status=open 的)
        → 标记需要主动裁决的冲突点

STEP 7: 读 experiments/analyze_stock_charts/stock_pattern_library/_meta/charts_index.md
        → 拿到所有历史 chart 的 summary_tags（不加载图本身）
        → 用于"本批新图与某历史图特征相似时，链接引用而不重新分析"
```

### F.2 写入协议（每次 run 结束时必做，**严格顺序**，原子化）

写入是**最危险**的环节 — 中途崩溃会污染库。强制顺序：

```
STEP 1: 在 stock_pattern_runs/<runId>/ 下写入：
        a. input.md
        b. findings.md
        c. crosscheck.md
        d. proposals.md (status=pending)
        ── 这一步全部在 runs/ 下，绝不触碰主库 ──

STEP 2: 自检：
        - 所有 candidate 是否走过 C.2 相似度判定？
        - 每条现有规律是否在 crosscheck 中都被遍历？
        - dimensions.primary 是否都在 dimensions_link.md 中？
        失败 → 不进入 STEP 3

STEP 3: 应用 proposals.md 到主库（按以下子顺序）：
        a. 写入新建的 patterns/R-xxxx__*.md
        b. 修改已有的 patterns/R-xxxx__*.md（version 自增）
        c. 移动被废弃的到 patterns/_retired/
        d. 写入新建的 conflicts/C-xxxx__*.md
        e. 修改已有 conflicts 的状态
        ── 每个文件写完后立即 fsync（agent 用 Write 工具时由系统保证）──

STEP 4: 更新 _meta 索引（最后一步，因为它们是"所有改动完成"的标记）：
        a. 追加 charts_index.md
        b. 追加 run_history.md
        c. 更新 dimensions_link.md（如有新 dimension 首次使用）
        d. 若 schema_version.md 需升级则更新

STEP 5: 把 proposals.md 的 status 改为 applied
        写入 written.md (audit log)
        ── 至此 run 完成 ──
```

### F.3 冲突协议（多 agent 并发写入）

实际上同一时间只一个团队跑，但保留为约定：

```
- 写入主库前，先在 stock_pattern_library/.lock 创建锁文件，内容含 runId。
- 锁文件存在时，其他 run 的写入阶段必须 abort，runs/<runId>/ 仍可保留作为 pending。
- 锁文件年龄 > 1 小时（明显是崩溃残留）→ 允许覆盖（写新 lock）+ 在 written.md 中标注 stale_lock_recovered。
- run 结束（成功 or 失败）务必删除锁文件。
```

### F.4 失败模式与回滚

```
情形 1: STEP 1-2 中崩溃
        → runs/<runId>/ 半成品保留，标记 status=incomplete
        → 主库未受影响，下次 run 跳过此目录

情形 2: STEP 3 中途崩溃（部分 patterns 已写）
        → 用 git 回滚（CLAUDE.md 已要求项目在 git 下）：
          git diff HEAD experiments/analyze_stock_charts/stock_pattern_library/  → 检查
          git checkout HEAD -- experiments/analyze_stock_charts/stock_pattern_library/
        → runs/<runId>/proposals.md 标记 status=rolled_back
        → 重跑（或仅重跑 STEP 3）

情形 3: STEP 4 中途崩溃（patterns 写了，索引未更新）
        → 索引可从 patterns/*.md 完全重建：
          扫描所有 frontmatter → 重建 dimensions_link.md 和 charts_index.md（部分）
        → run_history.md 通过遍历 stock_pattern_runs/*/written.md 重建

情形 4: 写后发现逻辑错误（人工介入）
        → 不直接编辑历史 — 创建新的"修订 run"（runId 后缀 _fix）
        → 在该 run 的 proposals.md 中说明 reverting 哪个 run 的哪些变更
```

---

## G. 防幸存者偏差的硬约束（汇总 + 强化）

把分散在前面各节的反偏差措施集中复述，便于架构师在 IO 协议中插入校验：

### G.1 入库准入（pre-write checks）

| 校验项 | 位置 | 不通过时 |
|---|---|---|
| 新规律 status 强制 `hypothesis` | C.6 | 强制覆盖 agent 给出的值 |
| n_supports < 2 → 不允许 status > hypothesis | C.7 | 状态降回 hypothesis |
| `distinct_batches_supported < 2` OR `total_figure_supports < 4` → 不允许 partially-validated | C.7 | 状态降回 hypothesis |
| `distinct_batches_supported < 3` OR `total_figure_supports < 9` → 不允许 validated | C.7 | 状态降回 partially-validated |

### G.2 巡检强制性

- 每次 run **必须**执行 C.10 全规律巡检，9 × N 单元格全部填充。
- `IRRELEVANT` 必须有 1 行理由（防止 agent 用它草率跳过）。

### G.3 状态变更说明（v2.3 单向晋级）

v2.3 状态机无自动降级路径。详见 §C.7。

- `_retired/` 仅 user 主动归档（手动移动文件）
- 连续 2 个 run 中 confidence_score 单调下降 → 在 last_updated 备注 "decay-trend"，触发 architect 关注

### G.4 数据多样性追踪（可选增强）

在 `_meta/run_history.md` 中追加 `chart_diversity_score` 字段（每次 run 评估本批 9 图的"形态多样性"），如果连续 N 个 run 都是高度同质的批次（都是大涨成功 case），库需要在 README 顶部弹出警告：**"近 N 次 run 输入同质化，结论存在偏差风险"**。

---

## H. 与团队架构的接口要点（给 architect 的"集成信号"）

> 以下是 architect 在设计团队结构时**必须遵循**的对接点。详细架构设计在 `03_team_architecture.md` 中由 architect 完成，这里只列约束。

### H.1 团队角色分工对应的库读写权限

> **角色 = 接口契约，不是物理 agent 边界**：下表的 5 个角色名是**职责切片**（每个职责对应一组明确的读写权限和执行阶段），不是"必须 5 个 agent"的硬性规定。team-architect 可以将多个角色合并到一个物理 agent 上（例如让一个 agent 同时承担 chart-perceiver 和 pattern-matcher），只要保证该 agent 在不同阶段遵循对应职责的权限边界即可。
>
> **唯一不可合并的硬约束**：`auditor` **不得**与 `writer`（或任何对主库有写权限的角色）合并到同一物理 agent 上。理由是"自我审查 ≠ 审查" — 写入者审计自己的写入会引入系统性盲区，违背防偏差的核心目的。auditor 必须是独立物理 agent，且其执行时机在 writer 落库之前（拦截 proposals.md）或之后（标记 written.md 的 review 状态）。
>
> **建议合并模式**（仅供 team-architect 参考，非强制）：
> - **激进合并**（2 物理 agent）：`{chart-perceiver + pattern-matcher + library-curator + writer}` 合一 / `auditor` 独立
> - **平衡分工**（3 物理 agent）：`{chart-perceiver + pattern-matcher}` 一个 / `{library-curator + writer}` 一个 / `auditor` 一个
> - **完全展开**（5 物理 agent）：每个角色一个 — 适合需要并行加速 chart 判读的场景
>
> 物理 agent 数由 team-architect 根据上下文压力、并行度需求决定，但 auditor 的独立性不可妥协。

| 角色 | 读 | 写 |
|---|---|---|
| chart-perceiver（视觉判读 9 张图） | input.md（仅本 run） | findings.md 的逐图块 |
| pattern-matcher（执行 crosscheck） | 全库 patterns + 历史 charts_index | crosscheck.md |
| library-curator（执行整合算法 C.x） | 全库 + crosscheck.md + findings.md | proposals.md |
| writer（执行 IO 写入协议 F.2） | proposals.md + 全库 | 主库 + written.md |
| auditor（防偏差校验 G.x） | 全部 | findings/crosscheck/proposals 的 review 标记 |

### H.2 必须串行的步骤

- **读取协议 F.1** 必须在 chart 视觉分析**之前**完成 — 否则 agent 无先验知识。
- **整合算法 C.1** 必须在 crosscheck 完成**之后** — 因为整合需要本批 chart × 全部 pattern 的交叉证据。
- **写入协议 F.2** 的 STEP 1-5 是严格序列，不可并行。
- **巡检 C.10** 必须在新规律候选生成**之后** — 否则候选 patterns 自身不在巡检范围内。

### H.3 可并行的步骤

- chart-perceiver 对 9 张图的判读可全并行。
- pattern-matcher 对每张图的 pattern crosscheck 可按 chart 维度并行。
- 但 library-curator 的整合是**强串行** — 不允许并行 merge（会破坏 supports 的去重一致性）。

### H.4 与 stock-domain-expert 的协调点

- `dimensions_link.md` 的 schema 由 stock-domain-expert 在 `01_analysis_dimensions.md` 中定义。
- 本设计假定 dimensions 命名为 `<category>.<subcategory>` — 若 expert 选择不同的命名（如三段、或带版本号），本设计的字段示例需相应调整，**不影响其他部分**。
- 当某 dimension 在 patterns 中被引用 0 次连续 N 次 run，可向 expert 反馈"该维度未产出可识别规律"。

### H.5 与 team-architect 提议的"最小字段集"映射

team-architect 在团队架构层提出了 7 字段的最小骨架 `{id, hypothesis, support_count, refute_count, sample_refs, confidence, last_updated}`。这与本设计的 schema **完全兼容** — 后者是前者的细化展开，不冲突。映射如下：

| team-architect 提议字段 | 本 02 设计中的对应字段 | 备注 |
|---|---|---|
| `id` | `pattern_id` | 命名差异；功能等同 |
| `hypothesis` | `one_liner` + `description` | 一句话假设在 `one_liner`；详细形态描述在 `description` |
| `support_count` | `confidence.n_supports` | 数值等同 |
| `refute_count` | （v2.3 已移除，`n_counterexamples` / `n_should_have_failed` 不再存在）| v2.3 单向晋级状态机，无降级路径，refute_count 概念已废除 |
| `sample_refs` | `evidence.supports[].chart_id` | v2.3 仅保留 supports 列表作为 sample_refs 来源 |
| `confidence` | `confidence.confidence_score` (float) + `confidence.status` (enum) | 本设计把"置信度"拆为连续分数和离散状态机两层 — 状态机用于决策（是否纳入预测），分数用于排序 |
| `last_updated` | `meta.last_updated_at` + `meta.last_updated_in_run` | 本设计同时记录绝对时间戳与触发更新的 runId，便于审计 |

**为何本设计字段更多**：team-architect 的字段是"agent 间通信和决策的最小集"；本设计补充的字段（`dimensions`、`formalization`、`evidence.*` 三类、`signal_timing`、`relations`、`meta.*`）是"防偏差与可追溯的最小集"。两者目标层次不同，叠加而非替代。

**给 architect 的实操建议**：在团队内部传递 pattern 摘要时（如 chart-perceiver → pattern-matcher 的消息），可只提取 7 字段的子集（`id / one_liner / n_supports / sample_refs / confidence_score / distinct_batches / last_updated_at`）作为"轻量摘要"，避免把完整 yaml 带进每个 agent 的上下文。完整 yaml 仅 library-curator 和 writer 需要。

### H.6 与下游策略库的（未来）集成

`pattern.formalization.proposed_factors` 字段为未来集成 `BreakoutStrategy/factor_registry.py` 预留 — 但**当前阶段不做集成**，只是把建议留在文档里。若 validated 状态（门槛见 §C.7）的规律积累到 ≥ 5 条，可启动一个独立 task 去落地这些 proposed_factors（届时由 add-new-factor skill 接管）。

---

## I. 设计决策的"为什么"（FAQ）

**Q1: 为什么不引入数据库 / SQLite？**
A: meta team 的产出是文档而非代码；引入 DB 增加下游 agent 的工具依赖。markdown + yaml frontmatter 可被任何 agent 用 Read/Write 工具操作，零依赖。代价是大库下解析慢 — 通过仅加载 frontmatter（不读 description）部分缓解。规律达到 200+ 条时再考虑迁移。

**Q2: 为什么 supports 用 chart_id 列表而不是计数？**
A: 计数信息无法回溯 — agent 看不到"具体是哪张图支持了我"。chart_id 列表保留追溯能力，是防幸存者偏差的关键。

**Q3: 为什么不允许 agent 直接给 confidence.status 升级？**
A: agent 对单批 9 图的判读可能过度乐观。状态升级条件用 distinct_batches_supported 强制做"时间分散"，本质上模拟了"独立验证集"。

**Q4: 为什么 VARIANT 不分配独立 ID？**
A: 库膨胀控制。同一规律的参数变体本质是"同规律不同标定"，分配独立 ID 会让规律数虚高，让 dim_max 触发频繁。

**Q5: 为什么 conflicts 单独建文件而不是 patterns 的字段？**
A: conflict 的生命周期独立于 pattern — 一个 conflict 解决后不应永久污染两个 pattern 文件，但需要审计追溯。单独文件 + status 字段是干净的方案。

**Q6: 为什么 §H.5 的字段比 team-architect 提议更多？**
A: team-architect 的字段是"agent 间通信的最小集"；本设计补充的字段（`dimensions`、`formalization`、`evidence.*`、`signal_timing`、`relations`、`meta.*`）是"防偏差与可追溯的最小集"。两者目标层次不同，叠加而非替代。

**Q7: "本次独立报告"是否应该作为规律库的"切片快照 + 变更日志"，而非平行文档？（team-architect 提议）**
A: 视角等价但物理布局不同。本设计的 `runs/<runId>/` 实质上**已经是**切片+变更日志的组合：
   - `crosscheck.md` ≡ "本批 chart × 全部规律的命中切片"（即 architect 所说的"切片快照"）
   - `proposals.md` + `written.md` ≡ "本次对规律库的变更日志"（即 architect 所说的"变更日志"）
   - 额外的 `findings.md` 是"切片之上的分析师笔记" — 跨 chart 的共性讨论、跨规律的关联观察，这部分**不属于切片**，是 LLM-team 区别于纯数据库的核心增值。
   保持 `runs/` 与主库**物理分离**而非内嵌的理由有三：
   (a) **审计/回滚干净**：主库的 git 历史只反映"规律集合的演化"，run 的中间产物不会污染；
   (b) **大小可控**：runs 目录可以归档/迁移，不影响主库可读性；
   (c) **写入失败安全**：runs/ 完整写完才进入主库写入，主库永远处于"已 commit 的 run"状态。
   实操上 architect 可以把 runs 视为"主库的衍生物"，在团队叙事中表述为"本次切片 + 变更日志"，与本物理设计不冲突。

**Q8: 用户说"不写代码"，但 formalization.pseudocode 里有伪代码 — 矛盾吗？**
A: 不矛盾。pseudocode 是规律的**数学定义载体**，是文档的一部分；它不会被执行，仅供未来落地因子时参考。

---

## J. 给团队架构师的速查（请在 03_team_architecture.md 中引用）

### J.1 schema 字段一览（一行式）

```
pattern_id, name, short_name, schema_version, chart_class,
dimensions{primary, secondary[]},
one_liner, description,
formalization{status, pseudocode, proposed_factors[], thresholds{}},
evidence{
  supports[], no_data_yet[],
  per_batch_observations[],                       # 双层 evidence（详见 §C.7）
  distinct_batches_supported,                     # 双层 evidence
  total_figure_supports                           # 双层 evidence
},
signal_timing{type, detectable_before_breakout, earliest_detection_offset_bars},
confidence{
  status, n_supports,
  validation_progress{},                          # [legacy / audit-only] 不再用作晋级判定
  confidence_score
},
relations{complements[], contradicts[], subsumes[], subsumed_by[]},
meta{created_at, created_in_run, last_updated_at, last_updated_in_run, version, authors[]}
```

### J.2 IO 协议要点（5 行）

```
READ:  schema_version → run_history → dimensions_link → 01_dimensions → patterns/*.md (frontmatter only) → conflicts/*(status=open) → charts_index
WRITE: 1) runs/<runId>/{input,findings,crosscheck,proposals}.md → 2) self-check → 3) patterns/_/conflicts/_ 主库 → 4) _meta/* 索引 → 5) proposals.applied + written.md
LOCK:  stock_pattern_library/.lock during STEP 3-4
ROLLBACK: git checkout HEAD -- stock_pattern_library/  on STEP 3 mid-failure
PARALLEL OK: chart-perceiver / pattern-matcher per-chart;  STRICT SERIAL: library-curator + writer
```

### J.3 四个不能跳过的硬约束

1. **每次 run 必须做全规律巡检**（C.10）— 9 张图 × N 条规律全部填充 SUPPORT/IRRELEVANT/NO_DATA 之一。
2. **新规律 status 强制 hypothesis**（C.6 / G.1）— agent 不得跳过此约束。
3. **晋级到 validated 要求**（双层 evidence 双门槛）ALL of:
   - distinct_batches_supported ≥ 3（跨 batch 时间分散）
   - total_figure_supports ≥ 9（图级证据累积）
   详见 §C.7 双层 evidence 状态机。
4. **不物理删除规律**（C.7）— 不再使用的规律移入 `_retired/`（仅 user 主动操作），完整历史保留。

---

## K. 后续扩展方向（标注但不实施）

- **规律的概率化**：当前 confidence_score 是简单分数；未来可改为 Beta 分布的 posterior，更好处理小样本。
- **图片相似检索**：基于 summary_tags 的检索是粗粒度的；未来可引入感知哈希让"找历史相似图"更精确。
- **proposed_factors 自动化落地**：当 validated 规律 ≥ 5 时触发 add-new-factor skill。
- **多团队协作**：当前假定单团队跑，未来若多团队并发，锁机制需升级到分布式锁 / 事件队列。

---

**文档版本**: 1.0  | **维护者**: memory-system-designer (meta team) | **依赖**: 待 stock-domain-expert 完成 `01_analysis_dimensions.md` 后做最后字段命名校对
