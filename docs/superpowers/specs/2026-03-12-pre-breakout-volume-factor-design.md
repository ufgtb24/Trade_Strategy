# Pre-Breakout Volume Factor (`pre_vol`) Design Spec

## Summary

新增突破前环境因子 `pre_vol`，表征突破前 window(默认10) 天内是否出现过显著放量。采用方案 B（扩展因子型），将其纳入现有 `FACTOR_REGISTRY` 体系，挖掘管道零改动。

## 因子定义

| 属性 | 值 |
|------|-----|
| key | `pre_vol` |
| name | `Pre-Breakout Volume` |
| cn_name | `突破前放量` |
| default_thresholds | `(3.0, 5.0)` |
| default_values | `(1.15, 1.25)` |
| category | `context` |
| is_discrete | `False` |
| has_nan_group | `False` |
| mining_mode | `None`（自动推断） |

**语义**：突破前 10 天内，每日相对于其自身过去 63 天均量的放量倍数的最大值。

**公式**：
```
vol_ratio[d] = volume[d] / mean(volume[max(0, d-63) : d])
pre_vol = max(vol_ratio[d]) for d in [idx-window, idx)
```

## 架构决策

### 计算优化：Rolling 预计算

使用 `rolling(63, min_periods=1).mean().shift(1)` 预计算每日放量倍数序列，替代朴素逐日循环。

- `shift(1)` 确保均值不包含当天
- `min_periods=1` 处理边界数据不足
- 与朴素算法语义完全一致
- 复杂度从 O(window * 63) 降到 O(window) 查表

传递方式与现有 `atr_series` 一致：在 caller 层面预计算一次，作为参数传入 `enrich_breakout()`。

### FactorInfo 扩展：category 字段

在 `FactorInfo` 中新增 `category` 字段，区分因子类别：
- `resistance`：阻力属性因子（age, test, height, peak_vol）
- `breakout`：突破行为因子（volume, day_str, pbm, streak, drought, pk_mom, overshoot）
- `context`：突破前环境因子（pre_vol）

`category` 纯元数据，不影响任何计算逻辑。

## 改动文件清单

### 1. `BreakoutStrategy/mining/factor_registry.py`
- `FactorInfo` dataclass 新增 `category: str = 'breakout'` 字段
- 为 4 个阻力属性因子（age, test, height, peak_vol）标注 `category='resistance'`，其余 7 个依赖默认值 `'breakout'`
- 注册 `pre_vol` 因子（category='context'）

### 2. `BreakoutStrategy/analysis/breakout_detector.py`
- `Breakout` dataclass 新增 `pre_vol: float = 0.0` 字段

### 3. `BreakoutStrategy/analysis/features.py`
- 新增 `_precompute_vol_ratio_series(df, lookback=63)` 静态/类方法：预计算每日放量倍数序列
- 新增 `_calculate_pre_breakout_volume(vol_ratio_series, idx, window=10)` 方法
- `enrich_breakout()` 签名新增 `vol_ratio_series` 参数（可选，与 `atr_series` 同级）
- 在 `enrich_breakout()` 中调用计算并赋值 `pre_vol`

### 4. `BreakoutStrategy/analysis/breakout_scorer.py`
- `__init__` 新增 `pre_vol_factor_thresholds` 和 `pre_vol_factor_values` 配置
- 新增 `_get_pre_vol_factor(pre_vol)` 方法，模式与 `_get_volume_factor()` 完全一致
- `get_breakout_score_breakdown()` 中添加 `pre_vol` factor 调用
- 更新模块 docstring 中的乘法公式（2 处：文件顶部和 `get_breakout_score_breakdown` 方法）

### 5. `BreakoutStrategy/mining/data_pipeline.py`
`build_dataframe()` 中需要 4 处新增：
1. 阈值读取：`scorer_params["pre_vol_factor"]["thresholds"]`
2. 原始值提取：`bo.get("pre_vol", 0.0)`
3. Level 计算：`get_level(pre_vol_val, pre_vol_thresholds)`
4. Row dict 组装：`"pre_vol": pre_vol_val` 和 `"pre_vol_level": pre_vol_level`

### 6. `BreakoutStrategy/UI/managers/scan_manager.py`
`_scan_single_stock()` 中 breakout-to-JSON 序列化是手动枚举的（非 `dataclasses.asdict`），需要在 breakout dict 中添加 `"pre_vol": float(bo.pre_vol)` 行。否则 `pre_vol` 不会出现在 `scan_results.json` 中。

### 8. `configs/params/all_factor.yaml`
在 `quality_scorer` 下添加 `pre_vol_factor` 配置段：
```yaml
  pre_vol_factor:
    enabled: true
    thresholds:
    - 3.0
    - 5.0
    values:
    - 1.15
    - 1.25
```

Note: `window=10` 硬编码在计算层，不通过 YAML 配置（避免死配置）。

### 9. Caller 层面：`enrich_breakout()` 调用点
需要预计算 `vol_ratio_series` 并传入。3 个调用点：

| 调用点 | 优先级 | 说明 |
|--------|--------|------|
| `scan_manager.py:compute_breakouts_from_dataframe` | **必须** | 扫描结果的数据源 |
| `scripts/backtest/trade_backtest.py` | 可选 | 回测脚本，不影响挖掘管道 |
| `analysis/test/test_integrated_system.py` | 可选 | 测试，不传则 pre_vol=0.0 |

## 边界情况

| 场景 | 处理方式 |
|------|---------|
| `idx < window`（接近 df 开头） | `pre_start = max(0, idx - window)`，使用可用数据 |
| `d=0`（无历史均量） | `shift(1)` 产生 NaN，`fillna(0.0)` 处理 |
| `avg_vol = 0`（某段全零量） | `replace([inf, -inf], 0.0)` 处理 |
| 窗口内无有效数据 | 返回 0.0 |

## 后续：编写 "添加新因子" Skill

实现完成后，将整个因子添加流程提炼为一个可复用的 superpowers skill，包含：
- 因子注册、计算、评分、序列化、管道接入的完整 checklist
- 需要改动的文件清单模板
- 每个文件的改动模式（参照本次 `pre_vol` 的实践）

## 不改动的模块

以下模块因 `FACTOR_REGISTRY` 驱动的统一架构，零改动自动接入：
- `stats_analysis.py`
- `threshold_optimizer.py`
- `template_generator.py`
- `factor_diagnosis.py`
- `param_writer.py`
