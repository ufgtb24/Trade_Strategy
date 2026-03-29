---
name: add-new-factor
description: Use when adding a new factor to the breakout detection factor system - covers registration, computation, and dataclass field across 3 required files
---

# Add New Factor to Breakout System

## Overview

将新因子纳入现有 `FACTOR_REGISTRY` 体系的完整 checklist。每个因子仅需改动 **3 个文件**，其余模块通过 FACTOR_REGISTRY 自动驱动，零修改。

## Checklist

### 1. Factor Registry (`BreakoutStrategy/factor_registry.py`)

在 `FACTOR_REGISTRY` 列表中注册 `FactorInfo`（含完整元数据）：

```python
FactorInfo('key', 'English Name', '中文名',
           (threshold1, threshold2), (value1, value2),
           category='context',
           unit='x', display_transform='round2',
           # 可选：
           # is_discrete=True, has_nan_group=True,
           # mining_mode='lte', zero_guard=True, nullable=True,
           # sub_params=(SubParamDef(...),),
           ),
```

字段说明：
- `key`: 程序标识，全小写下划线
- `default_thresholds`: 阈值元组，递增排列
- `default_values`: 乘数元组，>1.0 奖励 / <1.0 惩罚
- `category`: `'resistance'` | `'breakout'` | `'context'`
- `unit`: 显示单位 (`'d'`, `'x'`, `'%'`, `'bo'`, `'σ'`, `'σN'`, `''`)
- `display_transform`: `'identity'` | `'pct100'` | `'round1'` | `'round2'`
- `zero_guard`: `True` 当 value <= 0 时 factor disabled
- `nullable`: `True` 当 None 有语义（如 drought 首次突破）
- `sub_params`: 计算参数元组，每个 `SubParamDef(yaml_name, internal_name, param_type, default, range, description, consumer)`

自动派生：`level_col = f"{key}_level"`, `yaml_key = f"{key}_factor"`

### 2. Breakout Dataclass (`BreakoutStrategy/analysis/breakout_detector.py`)

在 `Breakout` dataclass 中添加字段（带默认值）：

```python
    new_factor: float = 0.0  # 因子说明
```

### 3. Feature Calculator (`BreakoutStrategy/analysis/features.py`)

- 添加计算方法（如 `_calculate_xxx()`）
- 在 `enrich_breakout()` 中调用并赋值到 Breakout 构造器
- 如需预计算序列（如 rolling），参照 `atr_series` 模式：在 caller 预计算一次，作为可选参数传入

## 不需要改动的文件（FACTOR_REGISTRY 自动驱动）

以下模块通过遍历 `get_active_factors()` 动态驱动，添加新因子后**零修改**：

| 模块 | 自动驱动方式 |
|------|------------|
| `breakout_scorer.py` | `_compute_factor()` 循环 |
| `data_pipeline.py` | `build_dataframe()` 循环 |
| `scan_manager.py` | `_serialize_factor_fields()` 循环 |
| `param_editor_schema.py` | `_build_factor_schemas()` 生成 |
| `input_factory.py` | `param_value=None` 时 fallback 到 schema default |
| `param_loader.py` | `get_scorer_params()` 循环 |
| `all_factor.yaml` | fallback 到 registry defaults |
| `stats_analysis.py` | 遍历 level_cols |
| `threshold_optimizer.py` | 遍历 factors |
| `template_generator.py` | 遍历 level_cols |
| `factor_diagnosis.py` | 遍历 factors |
| `param_writer.py` | 遍历 factors |

## YAML 配置

新因子**无需手动编辑 YAML 文件**：
- **运行时**：`param_loader` 自动 fallback 到 `FactorInfo.default_thresholds` / `default_values`
- **挖掘流水线**：`param_writer` 和 `factor_diagnosis` 会为 YAML 中缺失的因子自动合成默认条目再覆写，不会静默跳过
- **UI 编辑器**：`input_factory` 对缺失值 fallback 到 schema default，正常渲染

## Verification

```bash
# 1. Registry
uv run python -c "from BreakoutStrategy.factor_registry import get_factor; fi = get_factor('xxx'); print(fi)"

# 2. Scorer（确认因子出现在评分分解中）
uv run python -c "
from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer
scorer = BreakoutScorer()
print('xxx' in scorer._factor_configs)
"

# 3. UI Schema（确认因子出现在参数编辑器中）
uv run python -c "
from BreakoutStrategy.UI.config.param_editor_schema import PARAM_CONFIGS
print('xxx_factor' in PARAM_CONFIGS['quality_scorer'])
"
```

## Common Pitfalls

| 遗漏 | 后果 |
|------|------|
| FactorInfo 的 unit/display_transform 错误 | 评分分解中显示值不对 |
| Breakout dataclass 字段缺失 | `getattr(bo, key)` 返回默认值 0 |
| features.py 未赋值 | 因子永远为 0（静默失效） |
| sub_params 的 consumer 写错 | 参数传递到错误的消费者 |
