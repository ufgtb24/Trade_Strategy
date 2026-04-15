# Spec 2: Per-Factor Gating 消费端改造

> 日期：2026-04-15
> 分支：trade_UI
> 前置：[Spec 1 核心基础设施](./2026-04-15-per-factor-gating-spec1-core.md) 必须先完成
> 研究：[research/per-factor-gating-implementation-plan.md](../../research/per-factor-gating-implementation-plan.md)
> 范围：mining NaN-aware + live detail_panel None 兜底 + factor_diag.yaml 审计字段

## 1. Purpose

Spec 1 让 `Breakout` 字段承载 None 语义；Spec 2 让下游消费链路对 NaN robust：
1. mining 管线不再用 `fillna(0)` 掩盖缺失——让 NaN 自然承载，每个统计函数显式决策如何处理
2. `build_triggered_matrix` / `apply_binary_levels` 的反向因子隐性 bug 修复（per_factor scheme 激活）
3. `factor_diag.yaml` 加每因子 `valid_count` / `valid_ratio` / `buffer` 审计字段
4. live `detail_panel._fmt` 加 None 兜底防 TypeError

**非目标**：
- 跨 scheme 兼容代码（用户明确拒绝）
- `gate_mode` 元数据（单一 scheme 下无意义）
- `template_lift_valid_intersection`（推迟 P2）
- mining 挖掘流程 CLI 变化

## 2. Scope

### In-scope

| 文件 | 改动要点 | 优先级 |
|---|---|---|
| `BreakoutStrategy/mining/data_pipeline.py` | ① `prepare_raw_values:178` 去 `.fillna(0)`<br>② `build_dataframe:102` 因子列的 `or 0` 改 None 透传<br>③ `apply_binary_levels:198` 加 `~np.isnan(raw)` 保护 | P0 |
| `BreakoutStrategy/mining/threshold_optimizer.py` | ① `build_triggered_matrix:28` 加 `~np.isnan(raw)` 保护（正/反向因子都要）<br>② TPE `bounds:295` 的 `np.quantile` 前 `raw[~np.isnan(raw)]`<br>③ greedy beam `:202-206` 加 `valid` mask | P0 |
| `BreakoutStrategy/mining/factor_diagnosis.py` | factor_diag.yaml 每因子新增 `valid_count` / `valid_ratio` / `buffer` 字段（审计用）| P1 |
| `BreakoutStrategy/live/panels/detail_panel.py` | `_fmt:11-14` 加 `if value is None: return "N/A"` 分支 | P0 |

**全部改动 ~35 行代码**。

### Out-of-scope

- **跨 scheme 兼容代码**：不写 `gate_mode=="bo_level"` 特殊处理、不读旧 JSON / 旧 filter.yaml
- **元数据字段**：scan_metadata 不加 gate_mode；factor_diag.yaml/_meta 不加 gate_mode；filter.yaml 不升级 version；CachedResults 不加 gate_mode
- **`template_matcher.check_compatibility`**：保持原状，不校验 gate_mode
- **`template_lift` 定义修改**：推迟到 P2 单独讨论
- **CLI 变化**：mining / live 入口参数不变
- **旧归档迁移代码**：用户手工处理（删除或另存）

## 3. Architecture

### 3.1 mining NaN 污染修复（单一来源 + 3 处保护）

```
Spec 1 产出:
  scan_results/*.json
    breakouts[].volume = null (可能)
        │
        ▼
  data_pipeline.build_dataframe   ← (2) 因子列的 `or 0` 改 None 透传
        │
        ▼
  df with NaN（NaN 自然承载）
        │
        ▼
  data_pipeline.prepare_raw_values   ← (1) 去 .fillna(0)，唯一污染源修复
        │
        ▼
  raw_values: dict[key, np.ndarray]（含 np.nan）
        │
   ┌────┼────────────────┐
   ▼    ▼                ▼
  threshold   apply_binary   factor_diagnosis / distribution_analysis
  optimizer   levels          (已 robust，上游改完自动正确)
   │            │
   │            └── (3) apply_binary_levels 加 ~np.isnan(raw) 保护
   │
   ├── (4) build_triggered_matrix 加 ~np.isnan(raw) 保护
   ├── (5) TPE bounds quantile 加 raw[~np.isnan(raw)] 过滤
   └── (6) greedy beam mask 加 valid 保护
```

### 3.2 missing-as-fail 语义统一

| 路径 | 当前语义 | Spec 2 之后 |
|---|---|---|
| `template_matcher.match_breakout` | 显式 `value is None → False` | 不变（SSOT）|
| `build_triggered_matrix` | 隐式（`fillna(0)` 后 `>=`；反向因子错）| 显式 `~np.isnan & op` |
| `apply_binary_levels` | 隐式（同上）| 显式 `~np.isnan & op` |

三路径统一为 **missing-as-fail**（unavailable 因子 = 该模板对该 BO 不匹配）。

### 3.3 factor_diag.yaml 审计字段（P1）

```yaml
quality_scorer:
  volume_factor:
    enabled: true
    thresholds: [5.0, 10.0]
    values: [1.5, 2.0]
    mode: gte
    # ── 新增审计字段 ──
    valid_count: 38214     # 有 NaN 过滤后的有效 BO 数
    valid_ratio: 0.837     # valid_count / total_bo
    buffer: 63             # 该因子 effective buffer（来自 FeatureCalculator._effective_buffer）
```

**目的**：读 yaml 的人能立刻看到"该因子的统计基础是什么样"，排查因子缺失率异常。字段不参与 gate_mode 识别（单一 scheme 下无意义），纯审计用。

### 3.4 Live detail_panel 兜底

`daily_runner.py:172` 的 `factors={f: bo[f] for f in template["factors"] if f in bo}` 把 bo dict 中的 None 原样带入 MatchedBreakout.factors。

`detail_panel._fmt` 当前：

```python
def _fmt(value: float) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"   # ← None 走到这里 TypeError
```

改为：

```python
def _fmt(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"
```

## 4. Components

### 4.1 data_pipeline.py 改动

| 行号 | 改动 |
|---|---|
| `build_dataframe:102` | 因子列 `raw_val or (0 if fi.is_discrete else 0.0)` → `raw_val`（None 透传）|
| `prepare_raw_values:178` | `.fillna(0)` 去掉，直接 `df[fi.key].values.astype(np.float64)` |
| `apply_binary_levels:198` | `(raw <= thresholds[key])` → `(~np.isnan(raw) & (raw <= thresholds[key]))`；正向因子同理 |

### 4.2 threshold_optimizer.py 改动

| 行号 | 改动 |
|---|---|
| `build_triggered_matrix:28` 正向分支 | `(raw >= t)` → `(~np.isnan(raw) & (raw >= t))` |
| `build_triggered_matrix:28` 反向分支 | `(raw <= t)` → `(~np.isnan(raw) & (raw <= t))` |
| TPE `bounds:295` | `np.quantile(raw, ...)` 前 `raw = raw[~np.isnan(raw)]`；若空则该因子退出 bounds |
| greedy beam `:202-206` | `sub_mask = current_mask & (raw op threshold)` → `sub_mask = current_mask & ~np.isnan(raw) & (raw op threshold)` |

### 4.3 factor_diagnosis.py 改动（P1）

`main()` 在写 factor_diag.yaml 前为每因子计算 `valid_count` / `valid_ratio`：

```python
valid_mask = ~np.isnan(raw_values[fi.key])
valid_count = int(valid_mask.sum())
valid_ratio = valid_count / len(raw_values[fi.key])
buffer = feature_calc._effective_buffer(fi)  # 从 Spec 1 引入
# 写入 factor_diag.yaml 的每因子条目
```

### 4.4 detail_panel.py 改动

唯一 5 行：

```python
def _fmt(value) -> str:
    if value is None: return "N/A"
    if isinstance(value, int): return str(value)
    return f"{value:.2f}"
```

## 5. Data Flow

```
Spec 1 产出 (本项目的前提):
  Breakout.volume = None | float
        │
        ▼
  scanner._serialize_factor_fields → JSON (null | float)
        │
        ▼
[Spec 2 开始]
        │
        ▼
  data_pipeline.build_dataframe ──> df[factor].dtype=float64，含 NaN
        │
        ▼
  data_pipeline.prepare_raw_values ──> np.ndarray，含 np.nan
        │
        ▼
  threshold_optimizer.build_triggered_matrix ──> 0/1 int64
        │                                         (NaN→0，即未触发)
        ▼
  top-K 模板 + filter.yaml（_meta 不含 gate_mode）
        │
        ▼
  factor_diag.yaml（每因子含 valid_count/ratio/buffer，P1）

[live 侧]
  MatchedBreakout.factors = {key: None | float}
        │
        ▼
  detail_panel._fmt(None) ──> "N/A"
```

## 6. Error Handling

| 场景 | 行为 |
|---|---|
| `prepare_raw_values` 读到 None 因子值 | 自然转 `np.nan` |
| `build_triggered_matrix` 对 NaN 样本 | `~np.isnan & op` 为 False → 未触发（missing-as-fail）|
| 反向因子（overshoot/age lte）+ NaN | 不再被误判为"完美触发"（per_factor gate 激活的隐性 bug 修复）|
| TPE `np.quantile` 含 NaN | `raw[~np.isnan]` 过滤；若全空则该因子退出 bounds |
| greedy beam `sub_mask & (raw op t)` | `sub_mask & valid & (raw op t)` |
| `apply_binary_levels` 对反向因子 NaN | `~np.isnan & op` |
| `factor_diagnosis.diagnose_direction` | 已有 `~np.isnan`，上游改后自动正确 |
| `distribution_analysis.analyze_factor` | 已用 `raw_series.isna()` 分组，不变 |
| `stats_analysis._feature_importance` | `X.fillna(0)` on level_cols，0=未触发语义正确，不变 |
| `template_matcher.match_breakout` | 已 `value is None → False`，不变（SSOT）|
| `MatchedBreakout.factors` 值含 None | daily_runner 天然透传 |
| `detail_panel._fmt(None)` | 返回 `"N/A"` |
| 挖掘 factor valid_ratio=0 | yaml 记录 `valid_count: 0`；TPE 该因子退出 bounds |

**不处理**：跨 scheme 对比、旧 bo_level yaml 加载、template_lift 定义修改（P2）。

## 7. Testing

### 7.1 新增单元测试

| 测试 | 位置 | 验证点 |
|---|---|---|
| `test_prepare_raw_values_preserves_nan` | `mining/tests/` | 输入 DataFrame 含 None，输出 ndarray 含 `np.nan` |
| `test_build_triggered_matrix_nan_not_triggered` | `mining/tests/` | NaN 样本在正/反向因子上都判未触发 |
| `test_tpe_bounds_skip_nan` | `mining/tests/` | bounds 的 quantile 基于 `~np.isnan` 过滤后样本 |
| `test_apply_binary_levels_nan_safe` | `mining/tests/` | 反向因子 + NaN 不被误判为完美触发 |
| `test_factor_diagnosis_valid_count` | `mining/tests/` | factor_diag.yaml 含 valid_count/ratio/buffer（P1）|
| `test_detail_panel_fmt_none_na` | `live/tests/` | `_fmt(None)="N/A"`；`_fmt(3.14)="3.14"`；`_fmt(5)="5"` |

### 7.2 现有测试影响

| 测试类别 | 影响 |
|---|---|
| mining 下含 `fillna` 后 raw=0 断言的测试 | 改为 `np.isnan()` 判断 |
| mining 集成测试 baseline | 因分布基础变化需更新 baseline |

### 7.3 跨 Spec 手工验证（Spec 1 + Spec 2 实施完成后跑一次）

1. 扫描一只股票 → JSON 含 null 因子值
2. 跑 `BreakoutStrategy.mining.pipeline` → 产出新 factor_diag.yaml / filter.yaml（不含 gate_mode 字段）
3. 检查 factor_diag.yaml：每因子有 valid_count（P1），NaN 样本不污染 Spearman
4. UI 点 idx<252 的 BO → tooltip 显示若干 "N/A" 行
5. 启动 live，某股票 detail_panel 显示 `factor=N/A` 不崩

### 7.4 不测

- 跨 scheme 对比（用户拒绝）
- Spec 1 范围的测试

## 8. References

- [Spec 1](./2026-04-15-per-factor-gating-spec1-core.md)（前置必读）
- [研究报告：per-factor-gating-implementation-plan.md](../../research/per-factor-gating-implementation-plan.md) §2.3、§4.1 P0、§9.1
- [研究报告：.per-factor-gate-impl-workspace/mining-pipeline.md](../../research/.per-factor-gate-impl-workspace/mining-pipeline.md)
- [研究报告：.per-factor-gate-impl-workspace/live-integration.md](../../research/.per-factor-gate-impl-workspace/live-integration.md)
