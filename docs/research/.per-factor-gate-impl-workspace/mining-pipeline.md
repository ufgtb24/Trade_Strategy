# Per-Factor Gate 改造 · 挖掘流程影响分析

> 作者：mining-pipeline teammate
> 生成日期：2026-04-15
> 范围：`BreakoutStrategy/mining/` 全部 + `BreakoutStrategy/factor_registry.py` 相关字段
> 前置阅读：`docs/research/per-factor-gate-analysis.md`

---

## 0. 核心结论（TL;DR）

per-factor gate 让扫描产出的 BO 集合增大（idx<252 的 BO 也进来了，但部分因子字段为 None）。挖掘管线对 NaN 的 robust 程度存在**三档分化**：

1. **天然 robust**：`analyze_factor`（distribution_analysis.py）、`diagnose_direction`（factor_diagnosis.py）—— 已经走 `~np.isnan(raw)` 过滤。
2. **主污染源**：`prepare_raw_values`（data_pipeline.py:178）`.fillna(0)`——所有下游统计（TPE bounds、贪心 beam、fast_evaluate、template 生成、template_validator）都经由这一步，零值会被当成真实观察参与 quantile、median、trigger rate。
3. **语义模糊区**：`apply_binary_levels` 与 `template_matcher.match_breakout`——前者 fillna(0) 后做 `>=`，"缺失" 统一判为不触发（missing-as-fail 的隐式实现）；后者已显式 `value is None → return False`。两者语义**恰好一致**，但一个是隐式、一个是显式，需要显式化统一。

**修复路径**：在 `prepare_raw_values` 产出 `(raw_with_nan, valid_mask)` 双通道；每个下游统计函数自己决定怎么消费（分位数/median 过滤 NaN，triggered 矩阵将 NaN 行视为未触发）。factor_diag.yaml 增加 `valid_count` 字段，让统计基础被审计可见。模板匹配显式声明 `missing-as-fail` 作为语义锚点。

**关键发现（3 个）**：

- F1. `prepare_raw_values` 的 `.fillna(0)` 是整条挖掘流水线的单一污染源，改它等于修它——其他 N 个调用点不用重写。
- F2. `template_validator` 的 `template_lift` 基线是"**未命中**样本的测试集 median"——per-factor gate 让未命中集合里多了一批 idx<252 的"必然不匹配"BO，会让 `unmatched_median` 偏移，间接放大 lift。这是跨 scheme 比较的硬伤，**不能直接把新旧 lift 数值对标**。
- F3. template matcher 的 `match_breakout` 已是 missing-as-fail（显式 None-check），但 `apply_binary_levels` → fast_evaluate 链路里是"fillna(0) 后 >=threshold" 的隐式 missing-as-fail。两条路径在"threshold 为负 + gte" 或 "threshold<=0" 的边角情况下**可能不一致**。推荐明确化。

---

## 1. 挖掘流程现状（数据流与关键统计量）

### 1.1 五阶段数据流

```
(1) scan_results_*.json
      │ [build_dataframe]  data_pipeline.py:47
      │    按因子读 key → level 映射；has_nan_group=True 的因子保留 None
      ▼
(2) factor_analysis_data.csv
      │ [prepare_raw_values]  data_pipeline.py:153  ◀── 唯一的 fillna(0) 发生点
      ▼
(3) raw_values: {key: np.ndarray[n_bo]}   ← 已无 NaN
      │
      ├── [diagnose_direction]  factor_diagnosis.py:71 ─→ factor_diag.yaml (mode)
      ├── [diagnose_log_scale]  factor_diagnosis.py:148 ─→ TPE 采样空间
      ├── [stage3a_greedy_beam] threshold_optimizer.py:170 ─→ greedy_seeds
      ├── [stage3b_optuna]      threshold_optimizer.py:262  ─→ study
      └── [build_triggered_matrix] threshold_optimizer.py:28
              │
              ├── [fast_evaluate / decode_templates]   threshold_optimizer.py:56/114
              │                                           → top-K templates
              └── [select_best_trial bootstrap]        threshold_optimizer.py:459
                                                           → best trial

(4) filter.yaml (templates + thresholds + scan_params)
      │ [apply_binary_levels + template_validator._build_test_dataframe]
      │   template_validator.py:146
      ▼
(5) OOS: matched = build_triggered_matrix(test)
      ├── [_compute_validation_metrics]  template_validator.py:268
      │      D1 per-template, D2 retention, D3 KS+CI, D4 global_lift
      ▼
    validation_report.md
```

### 1.2 每阶段的关键统计量

| 阶段 | 关键统计量 | 计算位置 | 对 NaN 的当前行为 |
|---|---|---|---|
| **build_dataframe** | 因子 level（0..3） | data_pipeline.py:105 `get_level(level_input,...)` | `has_nan_group=True` 时用 0 代入 `get_level` → level=0；否则 `or 0`（False/None/0 均转 0） |
| **prepare_raw_values** | 每因子 float64 ndarray | data_pipeline.py:178 | `.fillna(0)` —— **唯一污染源** |
| **diagnose_direction** | Spearman r / p | factor_diagnosis.py:108 | `~np.isnan(raw)` 过滤——但 raw 已被 fillna(0)，isnan 已失效 |
| **diagnose_log_scale** | P10/P90 比值、SW 改善 | factor_diagnosis.py:177 | 先过滤 NaN，再 `valid[valid > 0]` 保留正值——fillna(0) 让"缺失" 进入 `<=0` 分支，走 R1 非正分支退为 linear；单纯看 rule 不知道是因为"真负值"还是"被 fillna 的 NaN" |
| **analyze_factor（分布）** | 分位数、skewness、Spearman | distribution_analysis.py:139 | 直接 `raw_series.isna()` 分组——**天然 robust**，但它读的是 DataFrame 不是 raw_values |
| **greedy_beam_search** | 子集 median、count | threshold_optimizer.py:170 | 基于 fillna 过的 raw，"缺失 BO"= value=0，`>=threshold` 判为 False、`<=threshold` 判为 True ← 反向因子会把缺失当成"完美触发" |
| **fast_evaluate** | shrinkage_score、combo median | threshold_optimizer.py:56 | 同 beam；缺失行会进入 combo_key=0，被 `stats.index > 0` 的过滤剔除——但只有**全因子** level=0 的行才会 combo_key=0，**部分缺失部分触发**的行仍然进入某个 combo |
| **build_triggered_matrix** | triggered 矩阵 | threshold_optimizer.py:28 | `value >= threshold` / `value <= threshold`——缺失=0，结果取决于 threshold 符号和方向 |
| **decode_templates / template_generator** | median、q25、count | threshold_optimizer.py:114, template_generator.py:77 | 模板统计基于 triggered 组合 key，不同模板的分母是同一份全体 BO |
| **template_validator D1** | train/test 统计五元组 | template_validator.py:230 | 基于 build_triggered_matrix 的结果分组计算 |
| **template_validator D4 lift** | matched_median - unmatched_median | template_validator.py:370 | `keys_test == target_key` 的二元切分；缺失的 BO 几乎必然落在 unmatched |

---

## 2. per-factor NaN 对每个统计量的污染点（表格化）

> 约定：**当前**= 现 fillna(0) 的实际行为；**NaN-aware** = 假定保留 NaN 后，统计本来该怎么做；"污染方式"给出具体的偏差路径。

| 统计量 | 当前行为（fillna 后） | NaN-aware 正确行为 | 污染方向 | 修复建议 |
|---|---|---|---|---|
| **quantile 候选（TPE bounds）** threshold_optimizer.py:295 | `np.quantile(raw, 2%)` 把 0 当真观察，下端被压低 | 仅在 `~np.isnan(raw)` 上取分位 | 下端压低 → TPE 搜索空间被扩展到无意义的 0 附近 | `bounds[key]` 前先 `raw_valid = raw[~np.isnan(raw)]` |
| **log-scale 诊断** factor_diagnosis.py:177 | 先 isnan 过滤（对 fillna 后数组不起作用），再 `valid[valid>0]` 把 0 值（假装的缺失）剔除 | 同左，但 `valid` 应该先真实去 NaN | 诊断结论可能从 R3_log 滑到 R1_non_pos（取决于有多少缺失被 fillna） | 让上游直接传 NaN-aware 数组 |
| **Spearman（direction）** factor_diagnosis.py:108 | isnan 在 fillna 后全 False → 把 0 当缺失参与相关 | 真正按 NaN 过滤 | 对 buffer>0 的因子（volume/day_str/overshoot...），0 的样本全部聚集在短 lookback 段，与 label 产生伪相关 | 让 `prepare_raw_values` 提供 mask，diagnose 用 mask 过滤 |
| **非单调检测** factor_diagnosis.py:25 | 基于已 fillna 的 raw | 基于 valid raw | 0 值堆积在 Q1，拉低 Q1 spearman；可能假阳性检出"非单调" | 同上 |
| **greedy beam `raw <= threshold`**（反向因子） threshold_optimizer.py:204 | 0 <= threshold 几乎恒真（阈值绝大多数 >0）→ 缺失 BO 被当成"完美触发反向条件" | 缺失应视为"不可评估"，在该因子上的组合被排除或不参与 | 反向因子（如 overshoot=lte）模板的 count 被虚胖，median 被稀释 | triggered 矩阵对 NaN 行强制 0（未触发） |
| **greedy beam `raw >= threshold`**（正向因子） threshold_optimizer.py:206 | 0 >= threshold 恒假（阈值 >0）→ 未触发 | 缺失应视为"未触发"，与当前一致 | 无显式污染 | 无需修，但显式化更稳健 |
| **fast_evaluate combo_key** threshold_optimizer.py:80 | 缺失行（所有 level=0）combo_key=0，被过滤；部分缺失行仍进入某 combo | 含 unavailable 因子的模板，BO 应退出该模板的 matched 集合，不进入分母 | 模板分母含"idx<252 的 BO"，median 被拉向这些短 lookback 样本 | 模板内对该 BO "unavailable → not-triggered"（与现状一致，但要显式） |
| **TPE baseline_median** threshold_optimizer.py:584 | 全体 BO 的 label median；per-factor gate 后 BO 变多，baseline 可能下移 | 同左，但本身是新语义下的新 baseline | 无污染（这是语义变化，不是 bug） | baseline 不需修，但 YAML 要记录是哪套数据的 baseline |
| **above_baseline_ratio** template_validator.py:357 | test median vs train baseline；top-K 模板在 test 上命中 ≥10 样本才计入 | 同左 | 新旧 scheme 下 baseline 语义不同，**跨 scheme 对比无效**（memory project_validation_stats 已指明） | 只能同 scheme 内比较；YAML 标注 gate_mode |
| **template_lift** template_validator.py:370 | `matched_labels median - unmatched_labels median` | 同左，但 unmatched 应该限定为"有能力被该模板评估"的 BO | per-factor gate 后 unmatched 集合里多了 idx<252 的"必然不匹配"BO（对含 volatility 因子的模板），拉动 unmatched_median | **见 §4：改 unmatched 为 valid-intersection；或保留当前定义并在报告中加 disclaimer** |
| **D1 per-template median** template_validator.py:234 | 组合 key 匹配的样本 | 同左 | 若模板里所有因子都是 buffer=0 的（age+test+height），新 scheme 下 matched 多了 idx<252 BO，测试集 median 是新的，train/test 的 median 分布都因 BO 变多而变化 | 不是 bug，是新语义；但 train/test 比较前需审视 integrity_info |
| **D3 Bootstrap CI** template_validator.py:336 | 对 test 命中样本 resample | 同左 | 无污染 | 无需修 |
| **baseline_median (filter.yaml _meta)** template_generator.py:118 | 全体 BO 的 median | 同左 | 新 scheme 下 BO 更多，baseline 不同 | YAML 加 gate_mode 字段 |
| **analyze_factor (distribution_analysis)** | 直接用 `raw_series.isna()` → NaN 分组统计 | 已正确 | 无 | 已 robust，无需改 |
| **stats_analysis `X.fillna(0)`** stats_analysis.py:226 | DecisionTree/RandomForest 特征用 level_cols，fillna 无害（level 本来 0=未触发） | 同左 | 无 | 无需改（level 语义已是 0=not-triggered） |
| **stats_analysis 因子相关矩阵** stats_analysis.py:282 | `raw_df[[i,j]].dropna()` | 已正确 | 无 | 无需改 |

---

## 3. valid_mask 贯穿方案（DataFrame 怎么承载、统计函数怎么改接口）

### 3.1 DataFrame 层：让 NaN 自然存在

`build_dataframe` 里的改动很小：

- 对 `has_nan_group=True` 的因子已经保留 None（data_pipeline.py:99）。
- 其他因子走 `raw_val or (0 if fi.is_discrete else 0.0)`（data_pipeline.py:102），把 None 替换为 0 ← **这是第二个污染源**，需改为直接用 None / NaN。
- 改后 `df[fi.key]` 列会是 `float64`，NaN 正常表达；DataFrame 的下游消费者（distribution_analysis 已正确）和 csv 往返（pandas read_csv 自动把空字段→NaN）都没问题。

**对非因子列的影响**：`annual_volatility` / `gap_up_pct` / `intraday_change_pct` 当前也是 `or 0.0`（data_pipeline.py:90-92）。这些不是 factor，不受 per-factor gate 改造影响，但它们是 scorer 旁路用的辅助字段，应**独立讨论**。从本次改造范围看，保留现状即可（它们是 0 代表缺失的惯例，UI 没有"N/A" 显示路径）。

### 3.2 prepare_raw_values 改双通道

当前签名：

```python
def prepare_raw_values(df, factors=None) -> dict[str, np.ndarray]
    # 每值都 fillna(0)
```

改造方案（两种形态，选其一）：

**方案 A（保守，改动最小）**：保留 dict[key, ndarray] 形状，但 ndarray 带 NaN；新增辅助 `prepare_valid_masks(df, factors=None) -> dict[key, np.ndarray[bool]]`。

**方案 B（结构化）**：返回 `dict[key, tuple[ndarray, mask_ndarray]]`。改动点多，但消费者"不经意忽略 mask" 的风险低。

推荐 **A**，因为绝大多数消费者（`diagnose_direction`、`diagnose_log_scale`、`stage3a/3b`）都是"在某个 key 上做统计"——一个 key 一个数组，按需要调 `mask = ~np.isnan(arr)`，行数轻。`build_triggered_matrix` 需要特殊处理（§3.3）。

### 3.3 每个统计函数的改接口细则

| 函数 | 改动点 | 备注 |
|---|---|---|
| `prepare_raw_values` data_pipeline.py:153 | 移除 `.fillna(0)`，直接 `df[fi.key].values.astype(np.float64)` | 改 1 行。所有下游统计都受益 |
| `apply_binary_levels` data_pipeline.py:183 | 把 `raw = df[fi.key].fillna(0)` 改为 `raw = df[fi.key]`，并在 `(raw <= thresholds[key]).astype(int)` 前加 `(raw.notna() & ...)`，让 NaN 行始终 level=0 | 这是显式 missing-as-fail 实现 |
| `diagnose_direction` factor_diagnosis.py:93/108 | 已用 `~np.isnan(raw)` 过滤——只要 prepare_raw_values 改了，它自动生效。但 `weak_threshold` 之下的 `detect_non_monotonicity(valid_raw,...)` 也要确保 valid_raw 来源无 NaN（已满足） | 无额外改动 |
| `diagnose_log_scale` factor_diagnosis.py:177 | 同上，只要上游 NaN-aware 它自动正确 | 无改动；但规则 `R1_non_pos` 的含义从"该因子本来有负值" 变回"该因子本来有非正值"——语义更干净 |
| `stage3a_greedy_beam_search` threshold_optimizer.py:170 | 对每个 factor 的 raw 数组，先构 `valid = ~np.isnan(raw)`；`sub_mask = current_mask & valid & (raw op threshold)`（`op` 由方向决定；NaN 与任何比较都 False 但为了清晰加 `valid`）| 确保"缺失 BO 不会被当成触发"，特别是反向因子 |
| `stage3b_optuna_search` threshold_optimizer.py:262 | `bounds[key]` 的 `np.quantile` 前先 `raw[~np.isnan(raw)]` | `build_triggered_matrix` 直接改，下游 TPE objective 自动正确 |
| `build_triggered_matrix` threshold_optimizer.py:28 | 两个比较都加 `~np.isnan(raw)` 保护：`(~np.isnan(raw) & (raw >= threshold)).astype(int64)` | 显式 missing-as-fail |
| `fast_evaluate / decode_templates` | 无需改：triggered 矩阵已经正确表达"缺失 → 0 bit"，combo_key 的 bit-pack 天然正确 | 无改动 |
| `template_generator.generate_templates` template_generator.py:59 | `(df[col] > 0)` 基于 level_col；只要 `apply_binary_levels` 或 `build_dataframe` 产出的 level 在 NaN 情况下为 0，这里自然正确 | 无改动 |
| `template_validator._match_templates` template_validator.py:207 | 走的还是 `prepare_raw_values` + `build_triggered_matrix`，上游改了它就对 | 无改动 |
| `_compute_validation_metrics D4` template_validator.py:354 | `unmatched_labels` 定义问题见 §4 | 选择题：保持当前定义 + disclaimer / 改成 valid-intersection |
| `stats_analysis.run_analysis` | `_feature_importance` 的 `.fillna(0)` 针对 level_cols，level=0 本来就是缺失的正确表达，保留 | 无改动 |

### 3.4 校验方式

改完后跑单因子回归：

1. `prepare_raw_values(df)` 输出的 `volume` key 的 `~np.isnan()` 计数应等于 `df[df['volume'].notna()]` 行数，且该计数在 per-factor gate 前后变化比例 ≈ `idx<63 的 BO 数 / 总 BO 数`。
2. `diagnose_log_scale` 的 `R3_log` 决定对 `idx≥63` BO-only 集合和全体集合应一致（前提是 idx<63 段本来就应该缺失）。若不一致，说明有其他 bug。
3. 挑一个 per-factor gate 前的 filter.yaml 的 top-1 模板，在新 scheme 下重跑 `threshold_optimizer`，top-1 的 thresholds 与旧值的相对误差应 <10%（factor_diag.yaml 的 mode 不应改变，否则说明 Spearman 被污染）。

---

## 4. factor_diag.yaml 扩展建议

当前 factor_diag.yaml 结构（参考 `outputs/statistics/20260407_134814/factor_diag.yaml`）：

```yaml
quality_scorer:
  volume_factor:
    enabled: true
    thresholds: [5.0, 10.0]
    values: [1.5, 2.0]
    mode: gte      # 本阶段加的字段
```

### 4.1 推荐扩展字段（每因子）

```yaml
quality_scorer:
  volume_factor:
    enabled: true
    thresholds: [5.0, 10.0]
    values: [1.5, 2.0]
    mode: gte
    # ── per-factor gate 新增 ──
    valid_count: 38214              # 有效 BO 数
    valid_ratio: 0.837              # valid_count / total_BO
    total_bo: 45660                 # 同 _meta.total_bo，冗余但便于单因子 self-contained
    buffer: 63                      # FactorInfo.buffer，审计用
    spearman_r_valid: 0.087         # 仅在 valid 样本上计算的 r（与 spearman_r 可能不同）
```

### 4.2 顶部 `_meta` 增强

```yaml
_meta:
  gate_mode: per_factor               # 或 bo_level（旧）
  total_bo: 45660
  total_bo_new: 7312                  # 相比 bo_level gate 新增的 BO 数（idx<max_buffer 段）
  factor_valid_counts:
    age: 45660
    test: 45660
    volume: 38214
    ...
  cross_factor_valid_intersection:    # 关键模板（前 5）的 valid 交集样本数
    "volume+day_str+height": 32108
```

### 4.3 为什么值得加

- **self-sufficiency**：读 yaml 的人能立刻知道"这个因子的统计基础是什么" ── 是在全体 BO 上，还是在子集上。
- **审计 TPE bounds**：`quantile_margin=0.02` 配 `valid_ratio=0.5` 意味着 quantile 是在半数 BO 上算的，这个信号应该可见。
- **防止跨 scheme 误读**：同一个 factor_diag.yaml 可能被 bo_level 和 per_factor 两套挖掘产生，gate_mode 字段让对比工具能检测。
- **cross_factor_valid_intersection**：回答 §7 的问题——模板的真实分母是"参与因子都 valid" 的 BO 数。

### 4.4 filter.yaml `_meta` 同步扩展

```yaml
_meta:
  version: 5                         # 从 4 升到 5
  gate_mode: per_factor
  sample_size: 45660                 # 全体 BO
  baseline_median: 0.042
  baseline_scheme: per_factor        # 明确这个 baseline 是新 scheme
```

version 升档让 template_matcher.load_filter_yaml 可以有选择地提示兼容性。

---

## 5. Template Matching 的 Missing 语义决策

### 5.1 当前代码实际行为（三条路径）

| 路径 | 行为 | 位置 |
|---|---|---|
| P1. `template_matcher.match_breakout` | **显式 missing-as-fail**：`value is None → return False` | template_matcher.py:84 |
| P2. mining 路径 `build_triggered_matrix` | **隐式 missing-as-fail**（fillna 后 `>=` 判 False；反向 `<=` 判 True ← **有歧义**） | threshold_optimizer.py:49 |
| P3. `apply_binary_levels` | **隐式 missing-as-fail**（fillna 后 `>=`/`<=` 同上） | data_pipeline.py:198 |

P2/P3 在**反向因子**且 threshold 大于 0 时，fillna(0) 会把缺失判为"触发反向条件"。例如 overshoot（mode=lte）、age（mode=lte）——缺失的 overshoot 会被当成"超涨比极低，完美的反向触发"。这是**错的**。

当前只是因为 overshoot 的 buffer=252，所有全局 gate 保护了这个边界；per-factor gate 下，overshoot 会真实出现 NaN，P2/P3 就暴露 bug。

### 5.2 现状 default semantic 推断

- `match_breakout` 已经明确 missing-as-fail，并且与 tom 的分析一致（per-factor-gate-analysis.md §3.3 选项 A）。
- mining 侧 P2/P3 现在只是**机械地复用 fillna(0) → compare** 的语义，在正向因子（gte）下恰好=missing-as-fail，在反向因子（lte）下错误。

**结论**：default semantic 在概念上是 missing-as-fail（match_breakout 体现了"作者意图"），但挖掘路径在反向因子上偏离了这个意图。**per-factor gate 让这个偏离从"永远不触发的边界"变成"经常发生的 bug"**。

### 5.3 推荐：明确化为 missing-as-fail，三条路径统一

具体做法：

1. `build_triggered_matrix` 和 `apply_binary_levels` 在比较时加 `~np.isnan(raw)` 保护（§3.3 已列）。
2. `match_breakout` 维持现状。
3. 在 `template_matcher` 加一个显式文档注释，说明"与挖掘侧三路径一致：unavailable 因子 → 模板对该 BO 不匹配"。
4. **不支持 abstain**（option B）和 **partial match**（option C），与 tom 的结论一致。

### 5.4 副效应与缓解

副效应：per-factor gate 下，含 volatility 因子的模板对 idx<252 的 BO 一律不匹配。表现为：

- 挖掘产出的 top-K 模板里，如果每个都含 volatility 因子，那 idx<252 段的 BO 不会进入 "matched"——行为上等价于旧架构把它们 gate 掉了。
- 若挖掘产出的 top-K 里有一个"纯 resistance 模板"（age+height），它对 idx<252 的 BO 也会匹配，进而提供覆盖 ← 这是 per-factor gate 的**新价值**。

缓解：在 validation_report 里单独打印"含 buffer>0 因子的模板覆盖率" vs "纯 buffer=0 模板覆盖率"，让用户了解每个模板真实覆盖的 BO 范围。

---

## 6. 数据迁移计划

### 6.1 不可避免的重挖

per-factor gate 改变了：

- **训练样本集**（BO 集合变大）
- **分布统计基础**（quantile、Spearman 都变）
- **baseline_median**（全体 BO median 变）
- **drought/streak 的"诚实化"**（detector history 不再被 gate，记忆里突破事件更完整）

所有依赖挖掘产出的 yaml 必须重挖：

- `configs/params/factor_diag.yaml` ← `factor_diagnosis.main`
- `configs/params/filter.yaml` ← `threshold_optimizer.main`
- `configs/params/all_factor.yaml` 中被 mining 覆盖的 thresholds/values ← `param_writer.main`

### 6.2 成本估算（基于 pipeline.py）

单次完整 pipeline 流程（`BreakoutStrategy.mining.pipeline.main`）：

| Step | 预计时长 | 瓶颈 |
|---|---|---|
| Step 1 data_pipeline.main | 数秒 ~ 数十秒 | JSON → DataFrame 遍历 |
| Step 2 factor_diagnosis.main | 数秒 | Spearman + shapiro |
| Step 3 threshold_optimizer.main | **数小时**（n_trials=50000） | TPE 目标评估（每 trial 一次 bit-pack） |
| Step 4 materialize_trial（含 OOS 验证） | 视 OOS 扫描期长度而定，通常 10 分钟~1 小时 | 测试期扫描 + 情感分析 |

主要成本在 **Step 3**。但 per-factor gate 本身不改变 TPE 的计算量（BO 数略增，每 trial 评估略慢但不致数量级变化）。

### 6.3 渐进式迁移方案

**阶段 A：旧 scheme snapshot**

```bash
# 锁住现有归档
cp -r outputs/statistics outputs/statistics.bo_level_snapshot
cp configs/params/filter.yaml configs/params/filter.bo_level.yaml
cp configs/params/all_factor.yaml configs/params/all_factor.bo_level.yaml
```

**阶段 B：per-factor 代码改造落地**

- detector + features + registry 改造（detector-arch 同事负责）
- mining 侧 prepare_raw_values + build_triggered_matrix + apply_binary_levels 改造
- scan_metadata 写入 `gate_mode: per_factor`
- filter.yaml `_meta` 写入 `gate_mode: per_factor`

**阶段 C：代码兼容 + 新旧并存**

- `template_matcher.load_filter_yaml` 读取 `gate_mode`（不匹配时给 warning 但不拒绝加载）
- Live 管道可同时持有两份 filter.yaml（UI 按 gate_mode 标注），过渡一周

**阶段 D：全量重挖**

```bash
uv run -m BreakoutStrategy.analysis.scanner  # 或 scripts/ 下入口
uv run -m BreakoutStrategy.mining.pipeline
```

产出新的 `outputs/statistics/<timestamp>_per_factor/`。

**阶段 E：切流量**

- 比对新旧 top-K 模板的重叠率（同 scheme 内的 top-1 thresholds 差距 <10% 视为健康）。
- 比对新旧 OOS validation 的 verdict；若都 PASS 则切换；若新版 FAIL 而旧版 PASS，回滚到阶段 A 的 snapshot。

**阶段 F：清理 bo_level 备份**（阶段 E 稳定运行一周后）。

### 6.4 回滚方案

- 代码层：每个改造点都是独立 commit，可 git revert。
- 配置层：阶段 A 保留的 snapshot 直接覆盖即可。
- 数据层：`outputs/scan_results/*.json` 保留历史版本（默认 scan 不覆盖旧 JSON），只要 scan_metadata 里有 `gate_mode`，UI/mining 都能区分。

---

## 7. 跨因子 valid 样本数不同的影响

### 7.1 问题

- `drought` buffer=0（~全部 BO 有效）
- `volume` buffer=63
- `day_str`/`overshoot`/`pbm`/`dd_recov` buffer=252

假设总 BO = 45660，idx<63 的 BO ≈ 2% = 913，idx<252 的 ≈ 15% = 6849。

对模板 `volume_level>=1 AND day_str_level>=1`，真正"两个因子都 valid" 的 BO 数 = `(1 - 0.15) * N = 38811`（day_str 更严格，是 intersection 的瓶颈）。

### 7.2 对 template lift 的影响

当前 `template_lift = median(matched) - median(unmatched)`（template_validator.py:371）。

**在 per-factor gate 下**，`matched` = `combo_key == target_key` 的 BO。`unmatched` = 其余所有 BO。idx<252 的 BO 对该模板 "必然不匹配"（missing-as-fail），全部进入 unmatched。

- **乐观解读**：idx<252 段本身收益分布可能偏低（短 lookback 股票特殊），落在 unmatched 拉低 `unmatched_median` → lift 变大。这是"真实信号"，因为该模板对这部分 BO 确实没判断力。
- **悲观解读**：lift 的含义从 "matched vs 同质 pool" 变成 "matched vs 混合 pool（含非我能力域的 BO）"，可比性下降。

### 7.3 基线重算方案（可选）

**方案 1：保持当前 unmatched 定义**

优点：兼容现有管线、不改代码。
缺点：跨 scheme 比较失真（但加 disclaimer 说明即可）。

**方案 2：valid_intersection_baseline**

把 unmatched 限定为"该模板所有因子都 valid 的 BO 中未匹配的"：

```python
# 计算模板的 valid_intersection mask
valid_mask = np.ones(len(labels_test), dtype=bool)
for factor in template["factors"]:
    valid_mask &= ~np.isnan(raw_test[factor])

matched_mask = (keys_test == target_key) & valid_mask
unmatched_mask = (~(keys_test == target_key)) & valid_mask  # 只在 valid 交集内取 unmatched

matched_median = np.median(labels_test[matched_mask])
unmatched_median = np.median(labels_test[unmatched_mask])
template_lift_v2 = matched_median - unmatched_median
```

优点：跨 scheme 可比；lift 仅衡量"模板在它能判断的样本上的真正增益"。
缺点：改 `_compute_validation_metrics`、加新字段、新旧 lift 数值不兼容。

**方案 3：并列两种 lift**

同时产出 `template_lift_global`（现定义）和 `template_lift_valid_intersection`，在报告里说明两者差。

**推荐 方案 3**，因为：

- 全局 lift 是用户看"这个模板对全体 BO 的总筛选增益"的直观指标，保留有价值。
- intersection lift 是工程上可比 + 诊断的正确基线，加一个新字段不伤兼容性。

### 7.4 shrinkage 收缩锚点的影响

`_shrinkage_score(median, count, baseline, n0)`（template_validator.py:260）的 baseline 是 `baseline_train`，即全体 BO median。

per-factor gate 下 baseline_train 变化（BO 变多），但这个变化对训练集和测试集都是一致的（都用 `baseline_train`）—— shrinkage 方向不变，只是数值基准漂移，不是 bug。

但 `n0_test = n0_train * (N_test / N_train)`（template_validator.py:289）在 per-factor gate 下 `N_train` 和 `N_test` 都因 BO 变多而成比例扩大，ratio 基本不变。这个机制**对 per-factor gate 天然稳健**，不需改。

---

## 8. 用户可见性评估

### 8.1 挖掘管线本身几乎对用户透明

挖掘的 CLI 入口：

- `pipeline.py main()`—— 参数在 `main()` 顶部声明，用户一直是"改代码顶部变量 + 运行" 模式。
- `threshold_optimizer.py main()`、`factor_diagnosis.py main()` 等子入口同理。

per-factor gate 改造不需改任何 CLI 参数。用户感知点：

- 扫描产出的 JSON 更大（BO 数增加 ~15-20%）
- 挖掘运行时的"sample size" 打印变大
- factor_diag.yaml 新增 `valid_count`/`valid_ratio` 字段（可选，见 §4）
- filter.yaml `_meta` 新增 `gate_mode` 字段

### 8.2 需要对用户可见的（建议保留）

- **filter.yaml 的 `gate_mode`** —— 避免跨版本 YAML 被误用
- **validation_report.md 的 gate_mode 注明** —— validation 结论的解释前提
- **per-factor valid_ratio**（factor_diag.yaml）—— 排查因子缺失率异常

### 8.3 可以隐藏的（不破坏现有输出）

- `prepare_raw_values` 的实现细节（从 dict[k, arr] 到 dict[k, (arr, mask)]）
- triggered_matrix 的 NaN 保护
- cross_factor_valid_intersection（放进 meta 即可，不打到 stdout）

### 8.4 CLI 产出示例对照

**旧**：

```
[Pipeline] Step 1/4: 重建分析数据集
  Rows: 38000
```

**新**：

```
[Pipeline] Step 1/4: 重建分析数据集
  Rows: 45660  (gate_mode=per_factor, +7660 from bo_level)
  Factor valid counts: age=45660, volume=38214, day_str=38811, ...
```

这个对照能让用户迅速看到"per-factor gate 带来了多少新样本、每个因子的 valid 率"。

---

## 9. 跨成员协作点

### 9.1 来自 detector-arch 的契约

- `FactorInfo.nullable` 字段扩展：所有 buffer>0 因子设置为 True（scorer/scanner 序列化自动 None-safe）。
- detector 的 `enrich_breakout` 对 NaN 因子传 None 到 Breakout dataclass。
- **挖掘侧保证**：`build_dataframe` 读 JSON 时，`bo.get(fi.key)` 拿到的可能是 None，已在 data_pipeline.py:97 处理。

### 9.2 来自 scorer-ui 的契约

- `FactorDetail.unavailable: bool` 新字段：scorer 在 None 因子的处理路径设置。
- **挖掘侧消费**：挖掘不直接读 `FactorDetail`——它读 JSON 里的原始因子字段。但 `template_validator` 的 UI 报告段（如果未来希望展示 "unavailable" 样本）可以用这个字段来区分"未触发"和"不可用"。目前不需要立刻消费。

### 9.3 来自 live-integration 的契约

- Live 扫描产出的 scan_metadata 必须含 `gate_mode: per_factor`。
- `template_matcher.load_filter_yaml` → `check_compatibility` 增加 gate_mode 校验（当前已经校验 detector/feature 参数，新增一个 key 即可）。

### 9.4 挖掘侧给外部的保证

- `prepare_raw_values` 的输出不再含假 0 —— **所有使用该函数的新代码必须对 NaN 容错**。
- `factor_diag.yaml` / `filter.yaml` 的 `gate_mode` 字段是 authoritative ← 消费者必须校验。
- template_matching 语义 = missing-as-fail，这是 SSOT，不支持运行时配置切换。

### 9.5 对 team-lead 的信号

- 改动不是"一刀切"—— prepare_raw_values 改一行触发下游连锁修复，但每个下游只是加一行 `~np.isnan()` 保护。总改动行数 <50 行。
- 主要风险在**跨 scheme 统计量对比**：用户不能把旧 filter.yaml 的 baseline_median 和新版直接对比。这需要文档化说明。
- 数据迁移成本主要是 TPE 跑一次（数小时），旧归档保留即可，无业务中断风险。

---

## 10. 关键文件·行号索引

| 类别 | 文件:行号 | 用途 |
|---|---|---|
| 主污染源 | `BreakoutStrategy/mining/data_pipeline.py:178` | `fillna(0)` ← 改这一行 |
| 第二污染源 | `BreakoutStrategy/mining/data_pipeline.py:102` | `or 0` ← build_dataframe 里 |
| 第三污染源 | `BreakoutStrategy/mining/data_pipeline.py:198` | `apply_binary_levels` 中的 fillna |
| triggered 矩阵 | `BreakoutStrategy/mining/threshold_optimizer.py:28` | 加 NaN 保护 |
| TPE bounds | `BreakoutStrategy/mining/threshold_optimizer.py:295` | quantile 前去 NaN |
| greedy beam | `BreakoutStrategy/mining/threshold_optimizer.py:202-206` | mask 加 `valid` 保护 |
| Spearman direction | `BreakoutStrategy/mining/factor_diagnosis.py:108` | 已有 isnan 保护，上游改了自动生效 |
| log scale 诊断 | `BreakoutStrategy/mining/factor_diagnosis.py:177` | 同上 |
| distribution analyze | `BreakoutStrategy/mining/distribution_analysis.py:157` | 已 robust |
| template 模板生成 | `BreakoutStrategy/mining/template_generator.py:59` | 无需改，依赖 level_col |
| template_matcher | `BreakoutStrategy/mining/template_matcher.py:84` | 已 missing-as-fail，保持 |
| D4 lift 定义 | `BreakoutStrategy/mining/template_validator.py:370` | §7 讨论点 |
| baseline_median 源头 | `BreakoutStrategy/mining/template_generator.py:118` | 保留现状，加 gate_mode 标注 |
| factor_registry nullable | `BreakoutStrategy/factor_registry.py:49` | 上游 detector-arch 扩展 |
| factor_registry has_nan_group | `BreakoutStrategy/factor_registry.py:41` | 可在后续清理为默认 True |

---

## 11. 实施优先级（按信噪比排序）

P0（必做，挖掘才能正确消费 per-factor 输出）：

- `prepare_raw_values` 去 fillna
- `apply_binary_levels` 加 NaN 保护
- `build_triggered_matrix` 加 NaN 保护
- `filter.yaml _meta.gate_mode` 字段

P1（强烈建议）：

- TPE bounds 的 quantile 去 NaN
- greedy beam 的 mask `valid` 保护
- factor_diag.yaml 增 `valid_count` / `valid_ratio`

P2（nice-to-have）：

- template_validator 新增 `template_lift_valid_intersection`
- factor_diag.yaml 增 `cross_factor_valid_intersection`
- CLI 打印 factor valid counts

P3（未来）：

- 移除 `FactorInfo.has_nan_group`（变为默认 True）
- 统一 template_matcher 和 mining 三路径的语义声明文档
