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
           description=(
               '算法：<1 句计算公式或算法>。\n\n'
               'source: BreakoutStrategy/analysis/features.py:<line>\n\n'
               '意义：<数值高/低含义、判别力来源>'
           ),
           nullable=True,  # ← 若 effective buffer>0 必填：per-factor gate 下 None = 不可算
           # 可选：
           # is_discrete=True, has_nan_group=True,
           # mining_mode='lte', zero_guard=True,
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
- `nullable`: `True` 当 effective_buffer>0 或 None 语义有效时必填（如 drought 首次突破、lookback 不足）
- `sub_params`: 计算参数元组，每个 `SubParamDef(yaml_name, internal_name, param_type, default, range, description, consumer)`
- `description`: **必填**。两段中文，第一段 "算法：…" 含 `source: file:line` 引用；第二段 "意义：…" 解释数值高/低对突破质量的影响。dev UI 参数编辑器据此在因子组标题上渲染 hover tooltip；不传该参数或传空字符串都会使 tooltip 不显示

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
new_factor: float | None = None  # 因子说明；None 表示 lookback 不足
```

### 4. Feature Calculator (`BreakoutStrategy/analysis/features.py`)

- 添加计算方法（如 `_calculate_xxx()`）
- 在 `enrich_breakout()` 中加一行 `key = self._calculate_xxx(...) if has_buffer('key') else None`
- 如需预计算序列（如 rolling），参照 `atr_series` 模式：在 caller 预计算一次，作为可选参数传入

**Per-factor lookback 自检**：如果你的因子需要 N 根历史 bar，在 `_calculate_xxx` 入口加：

```text
def _calculate_xxx(self, df, idx):
    if idx < N:                # N = 该因子的 effective buffer
        return None            # lookback 不足 → 该因子对该 BO 不可算
    # 正常计算 ...
```

这是第二道防线（第一道是 `has_buffer` 在 `enrich_breakout` 里拦截）。保留它使 `_calculate_xxx` 可以独立被测试/调用。

### 5. Per-factor effective buffer（`FeatureCalculator._effective_buffer`）

每个因子的 effective buffer（`idx >= N` 才能算）**必须**在 `FeatureCalculator._effective_buffer` 里注册一个 case。未注册的 fi.key 会 raise ValueError，在第一次扫描时立即暴露漏注册。

**伪代码**：

```python
def _effective_buffer(self, fi) -> int:
    if fi.key in {'age', 'test', 'height', 'peak_vol', 'streak', 'drought'}:
        return 0
    if fi.key == 'volume':  return 63
    if fi.key == 'pk_mom':  return self.pk_lookback + self.atr_period
    # ... 新因子在这里加 case
    raise ValueError(f"No effective_buffer registered for factor '{fi.key}'")
```

**取值规则**：

| 因子类型 | effective buffer | 例 |
|---|---|---|
| 无历史 lookback（peak 属性 / detector 状态） | `0` | `age`, `streak`, `drought` |
| 单一窗口因子 | 窗口长度 | `volume` → `63` |
| 组合窗口（多个 sub_params 串联） | 各部分之和 | `pk_mom` → `self.pk_lookback + self.atr_period` |
| 依赖 vol/MA/其他派生量 | 被依赖量的 buffer | `day_str/overshoot/pbm` → `252` (annual_volatility) |

**重要**：sub_params 通过 `self.xxx` 动态读；用户修改 YAML 里的 sub_param，`_effective_buffer` 自动反映实际 buffer 值。

**不再使用 `FactorInfo.buffer` 字段**（Spec 1 per-factor gate 改造后删除），SSOT 统一归 `_effective_buffer`。

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
from BreakoutStrategy.dev.config.param_editor_schema import PARAM_CONFIGS
print('xxx_factor' in PARAM_CONFIGS['quality_scorer'])
"

# 4. effective buffer（确认新因子已注册）
uv run python -c "
from BreakoutStrategy.analysis.features import FeatureCalculator
from BreakoutStrategy.factor_registry import get_factor
calc = FeatureCalculator()
fi = get_factor('xxx')
print('effective_buffer =', calc._effective_buffer(fi))
"
```

## Common Pitfalls

| 遗漏 | 后果 |
|------|------|
| FactorInfo 的 unit/display_transform 错误 | 评分分解中显示值不对 |
| Breakout dataclass 字段缺失 | `getattr(bo, key)` 返回默认值 0 |
| features.py 未赋值 | 因子永远为 0（静默失效） |
| sub_params 的 consumer 写错 | 参数传递到错误的消费者 |
| `_effective_buffer` 忘加 case | 扫描时立即 `ValueError: No effective_buffer registered for factor 'xxx'`（strict contract 早暴露） |
| `nullable=True` 漏加（且 effective_buffer>0） | scorer 对 None 走非 nullable 分支，raw_value 被当作 0 处理，FactorDetail.unavailable 不会显示，tooltip 不显示 "N/A" |
| `description` 缺失 | 参数编辑器中该因子标题 hover 无说明，新人无法理解因子含义 |
