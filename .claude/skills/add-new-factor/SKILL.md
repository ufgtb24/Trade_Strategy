---
name: add-new-factor
description: Use when adding a new factor to the breakout detection factor system - covers registration, computation, dataclass field, and BO-level buffer across required files
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
           buffer=N,                           # ← 必填：BO 级 lookback 需求
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
- `buffer`: BO 级 lookback 硬下限（trading days）—— 详见 §"BO 级 buffer" 小节

自动派生：`level_col = f"{key}_level"`, `yaml_key = f"{key}_factor"`

### 2. 方向判定

根据因子的**设计意图**判定方向："这个因子的值越高，对突破质量意味着什么？"

> `mining_mode` 和 `default_values` 均在步骤 1 的 `FactorInfo` 注册中设置。"锁定"指显式设置 `mining_mode='gte'` 或 `'lte'`，使挖掘管线跳过 Spearman 自动推断，直接使用指定方向。

**值越高越好（如量能）→ gte**

- `mining_mode = 'gte'` — 锁定
- `default_values = (1.2,)` 或按阈值档位递增（奖励型）

**值越高越差（如超涨）→ lte**

- `mining_mode = 'lte'` — 锁定
- `default_values = (0.8,)` 或按阈值档位递减（惩罚型）

**方向不确定**

- `mining_mode = None` — 不锁定，由 Spearman 自动推断
- `default_values = (1.0,)`

### 3. Breakout Dataclass (`BreakoutStrategy/analysis/breakout_detector.py`)

在 `Breakout` dataclass 中添加字段（带默认值）：

```python
    new_factor: float = 0.0  # 因子说明
```

### 4. Feature Calculator (`BreakoutStrategy/analysis/features.py`)

- 添加计算方法（如 `_calculate_xxx()`）
- 在 `enrich_breakout()` 中调用并赋值到 Breakout 构造器
- 如需预计算序列（如 rolling），参照 `atr_series` 模式：在 caller 预计算一次，作为可选参数传入

**严格 lookback 契约**：如果你的因子需要 N 根历史 bar，在 `_calculate_xxx` 入口加：

```python
if idx < N:
    raise ValueError(
        f"<factor_name> requires idx >= {N}, got idx={idx}. "
        f"Upstream BreakoutDetector should have gated this BO via max_buffer "
        f"(check FactorInfo.buffer in factor_registry.py)."
    )
```

这样万一 §5 的 `buffer` 字段填错或漏填，扫描时第一时间崩出来，不会静默给噪声。参考 `_calculate_annual_volatility`（features.py:518）。

### 5. BO 级 buffer（`FactorInfo.buffer`）

每个因子在 §1 的 `FactorInfo` 里**必须显式声明** `buffer=N`，告诉 BreakoutDetector "BO 在 idx<N 处不要产出"。`get_max_buffer()` 取所有活跃因子的最大值作为 detector 的硬下限。

**取值规则**：

| 因子类型 | buffer 值 | 例 |
|---|---|---|
| 无历史 lookback（peak 属性 / detector 状态） | `0`（默认，可省略） | `age`, `streak` |
| 单一窗口因子 | 窗口长度 | `volume=63` (VOLUME_LOOKBACK) |
| 组合窗口（多个 sub_params 串联） | 各部分之和 | `pk_mom=44` (pk_lookback=30 + atr_period=14) |
| 依赖 vol/MA/其他派生量 | 被依赖量的 buffer | `day_str=252`, `overshoot=252`, `pbm=252` (都依赖 annual_vol) |

**注意事项**：

- buffer 假设 sub_params 取**默认值**。如果将来 sub_param 改大，需要同步调高 buffer，否则上游 gate 不充分，下游 `_calculate_xxx` 的严格契约会触发 raise（这就是 §4 那个契约的作用）
- 即使是 INACTIVE 因子也填合理 buffer，未来重激活时不需要再回头补
- buffer=0 是默认值，无 lookback 的因子可以省略不写

设计背景：`docs/research/bo-level-buffer-redesign.md`

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
uv run python -c "from BreakoutStrategy.factor_registry import get_factor; fi = get_factor('xxx'); print(fi); print('buffer =', fi.buffer)"

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

# 4. max_buffer（确认新因子的 buffer 被聚合，必要时变更 detector gate）
uv run python -c "from BreakoutStrategy.factor_registry import get_max_buffer; print('max_buffer =', get_max_buffer())"
```

## Common Pitfalls

| 遗漏 | 后果 |
|------|------|
| FactorInfo 的 unit/display_transform 错误 | 评分分解中显示值不对 |
| Breakout dataclass 字段缺失 | `getattr(bo, key)` 返回默认值 0 |
| features.py 未赋值 | 因子永远为 0（静默失效） |
| sub_params 的 consumer 写错 | 参数传递到错误的消费者 |
| `FactorInfo.buffer` 漏填或填错（< 实际 lookback） | 上游 gate 不充分 → `_calculate_xxx` 在 idx 不足时 raise（如有契约）或静默给噪声（无契约）。**所以新因子务必加 §4 的 raise 契约**作为兜底 |
