# Factor Naming Unification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一全链路因子命名：每个因子只有 `key`（缩写）+ `name`（全称）+ `cn_name`（中文名）三个字段，`level_col` 和 `yaml_key` 从 key 派生；同时将所有 `bonus` 术语替换为 `factor`。

**Architecture:** 自底向上分 6 个 Task 推进——先改核心数据结构（Breakout/Peak dataclass），再改生产者（FeatureCalculator/BreakoutDetector），然后改消费者（BreakoutScorer/JSON 序列化），接着改 factor_registry + mining 管道，最后改 YAML 配置和 UI。每个 Task 完成后代码应可运行。

**Tech Stack:** Python dataclasses, PyYAML, pandas

---

## 命名映射表（全局参考）

### Breakout dataclass 字段重命名

| 旧字段名 | 新字段名 |
|---|---|
| `volume_surge_ratio` | `volume` |
| `momentum` | `pbm` |
| `pk_momentum` | `pk_mom` |
| `recent_breakout_count` | `streak` |
| `days_since_last_breakout` | `drought` |
| `day_str_ratio` | `day_str` |
| `overshoot_ratio` | `overshoot` |

### Peak dataclass 字段重命名

| 旧字段名 | 新字段名 |
|---|---|
| `volume_surge_ratio` | `volume_peak` |

### YAML 配置键重命名

| 旧 yaml_key | 新 yaml_key |
|---|---|
| `bonus_base_score` | `factor_base_score` |
| `age_bonus` | `age_factor` |
| `test_bonus` | `test_factor` |
| `volume_bonus` | `volume_factor` |
| `pk_momentum_bonus` | `pk_mom_factor` |
| `streak_bonus` | `streak_factor` |
| `pbm_bonus` | `pbm_factor` |
| `breakout_day_strength_bonus` | `day_str_factor` |
| `peak_volume_bonus` | `peak_vol_factor` |
| `drought_bonus` | `drought_factor` |
| `height_bonus` | `height_factor` |
| `overshoot_penalty` | `overshoot_factor` |

### 因子注册表

| key | name | cn_name |
|---|---|---|
| `age` | Age | 突破位龄 |
| `test` | Test Count | 测试次数 |
| `volume` | Volume Surge | 突破量能 |
| `pk_mom` | Peak Momentum | 峰值动量 |
| `streak` | Streak | 连续突破 |
| `pbm` | Pre-Breakout Momentum | 突破前动量 |
| `day_str` | Breakout Day Strength | 突破日强度 |
| `peak_vol` | Peak Volume | 峰值量能 |
| `drought` | Drought | 突破干旱期 |
| `height` | Height | 峰值高度 |
| `overshoot` | Overshoot | 超涨比 |

### bonus → factor 术语替换

| 旧术语 | 新术语 |
|---|---|
| `BonusDetail` | `FactorDetail` |
| `ScoreBreakdown.bonuses` | `ScoreBreakdown.factors` |
| `self.*_bonus_*` | `self.*_factor_*` |
| `_get_*_bonus()` | `_get_*_factor()` |
| `get_bonus_cols()` | `get_level_cols()` |
| `get_bonus_display()` | `get_factor_display()` |
| `is_bonus_group` | `is_factor_group` |

---

## Task 1: Breakout/Peak Dataclass + FeatureCalculator + BreakoutDetector

核心数据结构 + 生产者一起改，保持一致性。

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_detector.py` (Peak ~L22-39, Breakout ~L110-170, _create_peak ~L497-548, get_recent_breakout_count ~L647-671, get_days_since_last_breakout ~L673-688)
- Modify: `BreakoutStrategy/analysis/features.py` (enrich_breakout ~L53-212, 所有计算方法中的字段赋值)

**Step 1: 重命名 Peak dataclass 字段**

`breakout_detector.py` ~L34:
```python
# 旧
volume_surge_ratio: float = 0.0      # 放量倍数
# 新
volume_peak: float = 0.0             # 峰值放量倍数
```

全文搜索 `peak.volume_surge_ratio` / `p.volume_surge_ratio` 替换为 `peak.volume_peak` / `p.volume_peak`（同文件 _create_peak 方法内）。

**Step 2: 重命名 Breakout dataclass 字段**

`breakout_detector.py` ~L110-170:
```python
# 旧 → 新
volume_surge_ratio: float       → volume: float
momentum: float                 → pbm: float
pk_momentum: float = 0.0       → pk_mom: float = 0.0
recent_breakout_count: int = 1  → streak: int = 1
days_since_last_breakout: Optional[int] = None → drought: Optional[int] = None
day_str_ratio: float = 0.0     → day_str: float = 0.0
overshoot_ratio: float = 0.0   → overshoot: float = 0.0
```

注释保持中文，更新字段后面的注释使其与新名一致。

**Step 3: 更新 FeatureCalculator**

`features.py` enrich_breakout() 方法 (~L53-212) 中所有字段赋值：
```python
# 旧 → 新（构造 Breakout 对象时的 keyword arguments）
volume_surge_ratio=...  → volume=...
momentum=...            → pbm=...
pk_momentum=...         → pk_mom=...
recent_breakout_count=... → streak=...
days_since_last_breakout=... → drought=...
day_str_ratio=...       → day_str=...
overshoot_ratio=...     → overshoot=...
```

同时更新方法内部的局部变量名（如 `volume_surge_ratio = self._calculate_volume_ratio(...)` → `volume = ...`，`day_str_ratio = 0.0` → `day_str = 0.0` 等）。

**Step 4: 更新 BreakoutDetector**

`breakout_detector.py` _create_peak() ~L514:
```python
# 旧
volume_surge_ratio=vol_ratio
# 新
volume_peak=vol_ratio
```

get_recent_breakout_count() 和 get_days_since_last_breakout() 方法名不变（它们返回值，不涉及字段名）。

**Step 5: Commit**

```bash
git add BreakoutStrategy/analysis/breakout_detector.py BreakoutStrategy/analysis/features.py
git commit -m "refactor: rename Breakout/Peak dataclass fields to factor key names"
```

---

## Task 2: BreakoutScorer（bonus → factor 全面重命名）

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py` (~950 lines, 大量 bonus 引用)

**Step 1: 重命名 BonusDetail → FactorDetail**

~L44-52:
```python
@dataclass
class FactorDetail:
    """单个 Factor 的详情（乘法模型用）"""
    name: str           # 显示名称（如 "age", "volume"）
    raw_value: float    # 原始数值（如 180天, 2.5倍）
    unit: str           # 单位 ('d', 'x', '%', 'bo')
    multiplier: float   # factor 乘数（如 1.30）
    triggered: bool     # 是否触发（multiplier != 1.0）
    level: int          # 触发级别（0=未触发, 1=级别1, 2=级别2, ...）
```

注意：`bonus` 字段 → `multiplier`

**Step 2: 重命名 ScoreBreakdown 中的 bonus 引用**

~L55-90:
```python
@dataclass
class ScoreBreakdown:
    """评分分解（Factor 乘法模型）"""
    entity_type: str
    entity_id: Optional[int]
    total_score: float
    broken_peak_ids: Optional[List[int]] = None
    base_score: Optional[float] = None
    factors: Optional[List[FactorDetail]] = None  # 旧: bonuses
    pattern_label: Optional[str] = None
```

更新 `get_formula_string()` 中 `self.bonuses` → `self.factors`，`b.bonus` → `b.multiplier`。

**Step 3: 重命名 __init__ 中的配置读取**

~L96-199，所有 `self.*_bonus_*` 属性：
```python
# 旧模式
self.bonus_base_score = config.get('bonus_base_score', 50)
age_bonus = config.get('age_bonus', {})
self.age_bonus_enabled = age_bonus.get('enabled', True)
self.age_bonus_thresholds = ...
self.age_bonus_values = ...
self.age_bonus_mode = ...

# 新模式
self.factor_base_score = config.get('factor_base_score', 50)
age_cfg = config.get('age_factor', {})
self.age_factor_enabled = age_cfg.get('enabled', True)
self.age_factor_thresholds = ...
self.age_factor_values = ...
self.age_factor_mode = ...
```

对 11 个因子全部执行此重命名。特别注意：
- `overshoot_penalty` → `overshoot_factor`（config key 和所有属性名）
- `breakout_day_strength_bonus` → `day_str_factor`（config key）
- `pk_momentum_bonus` → `pk_mom_factor`（config key）
- `bds_bonus_*` → `day_str_factor_*`（属性名）
- `pk_momentum_bonus_*` → `pk_mom_factor_*`（属性名）

**Step 4: 重命名 _get_*_bonus() 方法 → _get_*_factor()**

11 个方法：
```
_get_age_bonus()           → _get_age_factor()
_get_test_bonus()          → _get_test_factor()
_get_volume_bonus()        → _get_volume_factor()
_get_pk_momentum_bonus()   → _get_pk_mom_factor()
_get_streak_bonus()        → _get_streak_factor()
_get_pbm_bonus()           → _get_pbm_factor()
_get_breakout_day_strength_bonus() → _get_day_str_factor()
_get_peak_volume_bonus()   → _get_peak_vol_factor()
_get_drought_bonus()       → _get_drought_factor()
_get_height_bonus()        → _get_height_factor()
_get_overshoot_penalty()   → _get_overshoot_factor()
```

每个方法内部：
- 读取 Breakout 字段时使用新名（`breakout.volume` 而非 `breakout.volume_surge_ratio`）
- 构造 `FactorDetail(...)` 而非 `BonusDetail(...)`
- `bonus=` 参数 → `multiplier=`
- `self.*_bonus_*` → `self.*_factor_*`

**Step 5: 重命名 get_breakout_score_breakdown_bonus()**

方法名 → `get_breakout_score_breakdown()`

内部调用全部改为 `_get_*_factor()`。

**Step 6: 更新 _classify_pattern()**

内部引用 `bonuses` → `factors`，`b.level` → `f.level` 等。

**Step 7: Commit**

```bash
git add BreakoutStrategy/analysis/breakout_scorer.py
git commit -m "refactor: rename bonus to factor in BreakoutScorer"
```

---

## Task 3: JSON 序列化（scan_manager + json_adapter）

**Files:**
- Modify: `BreakoutStrategy/UI/managers/scan_manager.py` (~L370-470, JSON 输出)
- Modify: `BreakoutStrategy/observation/adapters/json_adapter.py` (~L200-290, JSON 输入)

**Step 1: 更新 scan_manager.py JSON 输出**

Peak 序列化 (~L374-398):
```python
# 旧
"volume_surge_ratio": float(peak.volume_surge_ratio)
# 新
"volume_peak": float(peak.volume_peak)
```

Breakout 序列化 (~L399-470):
```python
# 旧 → 新
"volume_surge_ratio": float(bo.volume_surge_ratio)  → "volume": float(bo.volume)
"momentum": float(bo.momentum)                       → "pbm": float(bo.pbm)
"pk_momentum": float(bo.pk_momentum)                 → "pk_mom": float(bo.pk_mom)
"recent_breakout_count": int(bo.recent_breakout_count) → "streak": int(bo.streak)
"days_since_last_breakout": int(bo.days_since_last_breakout) → "drought": int(bo.drought)
"day_str_ratio": float(bo.day_str_ratio)             → "day_str": float(bo.day_str)
"overshoot_ratio": float(bo.overshoot_ratio)         → "overshoot": float(bo.overshoot)
```

**Step 2: 更新 json_adapter.py JSON 输入**

_rebuild_peaks() (~L204-214):
```python
# 旧
volume_surge_ratio=peak_data.get("volume_surge_ratio", 0.0)
# 新
volume_peak=peak_data.get("volume_peak", 0.0)
```

_rebuild_breakouts() (~L268-290):
```python
# 旧 → 新
volume_surge_ratio=bo_data.get("volume_surge_ratio") → volume=bo_data.get("volume")
momentum=bo_data.get("momentum")                      → pbm=bo_data.get("pbm")
pk_momentum=bo_data.get("pk_momentum")                → pk_mom=bo_data.get("pk_mom")
recent_breakout_count=bo_data.get("recent_breakout_count") → streak=bo_data.get("streak")
days_since_last_breakout=bo_data.get("days_since_last_breakout") → drought=bo_data.get("drought")
```

注意：`day_str_ratio` 和 `overshoot_ratio` 在 json_adapter 中可能未显式恢复（前次调研显示 adapter 忽略了它们），确认后如果有就改，没有则跳过。

**Step 3: Commit**

```bash
git add BreakoutStrategy/UI/managers/scan_manager.py BreakoutStrategy/observation/adapters/json_adapter.py
git commit -m "refactor: rename factor fields in JSON serialization"
```

---

## Task 4: factor_registry + mining 管道

**Files:**
- Modify: `BreakoutStrategy/mining/factor_registry.py` (整个文件重写)
- Modify: `BreakoutStrategy/mining/data_pipeline.py` (~L100-220)
- Modify: `BreakoutStrategy/mining/threshold_optimizer.py` (bonus → factor 术语)
- Modify: `BreakoutStrategy/mining/stats_analysis.py`
- Modify: `BreakoutStrategy/mining/distribution_analysis.py`
- Modify: `BreakoutStrategy/mining/template_generator.py`
- Modify: `BreakoutStrategy/mining/report_generator.py`
- Modify: `BreakoutStrategy/mining/factor_diagnosis.py`
- Modify: `BreakoutStrategy/mining/param_writer.py`
- Modify: `BreakoutStrategy/mining/pipeline.py`
- Modify: `BreakoutStrategy/mining/template_validator.py`
- Modify: `BreakoutStrategy/mining/__init__.py`
- Modify: `BreakoutStrategy/mining/price_tier_analysis.py`

**Step 1: 重写 factor_registry.py**

```python
"""
统一因子注册表

每个因子只有三个显式名称：
- key: 缩写/程序标识（如 "age", "pk_mom"）
- name: 英文全称（如 "Age", "Peak Momentum"）
- cn_name: 中文名（如 "突破位龄", "峰值动量"）

其他名称由 key 自动派生：
- level_col = f"{key}_level"（DataFrame 等级列）
- yaml_key = f"{key}_factor"（YAML 配置键）
- display_label = f"{key}({name}:{cn_name})"（Parameter Editor 显示）
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class FactorInfo:
    """单个因子的完整元数据"""
    key: str
    name: str
    cn_name: str
    default_thresholds: tuple
    default_values: tuple
    is_discrete: bool = False
    has_nan_group: bool = False

    @property
    def level_col(self) -> str:
        return f"{self.key}_level"

    @property
    def yaml_key(self) -> str:
        return f"{self.key}_factor"

    @property
    def display_label(self) -> str:
        return f"{self.key}({self.name}:{self.cn_name})"


FACTOR_REGISTRY: list[FactorInfo] = [
    FactorInfo('age', 'Age', '突破位龄', (42, 63, 252), (1.02, 1.03, 1.05), is_discrete=True),
    FactorInfo('test', 'Test Count', '测试次数', (2, 3, 4), (1.1, 1.25, 1.4), is_discrete=True),
    FactorInfo('volume', 'Volume Surge', '突破量能', (5.0, 10.0), (1.5, 2.0)),
    FactorInfo('pk_mom', 'Peak Momentum', '峰值动量', (1.2, 1.5), (1.2, 1.5), has_nan_group=True),
    FactorInfo('streak', 'Streak', '连续突破', (2, 4), (0.9, 0.75), is_discrete=True),
    FactorInfo('pbm', 'Pre-Breakout Momentum', '突破前动量', (0.7, 1.45), (1.15, 1.3)),
    FactorInfo('day_str', 'Breakout Day Strength', '突破日强度', (1.5, 2.5), (1.2, 1.35)),
    FactorInfo('peak_vol', 'Peak Volume', '峰值量能', (3.0, 5.0), (1.1, 1.2)),
    FactorInfo('drought', 'Drought', '突破干旱期', (60, 80, 120), (1.25, 1.1, 1.05), has_nan_group=True),
    FactorInfo('height', 'Height', '峰值高度', (0.2, 0.4, 0.7), (1.3, 1.6, 2.0)),
    FactorInfo('overshoot', 'Overshoot', '超涨比', (4.0, 5.0), (0.80, 0.60)),
]

LABEL_COL = 'label'

_BY_KEY: dict[str, FactorInfo] = {f.key: f for f in FACTOR_REGISTRY}
_BY_LEVEL_COL: dict[str, FactorInfo] = {f.level_col: f for f in FACTOR_REGISTRY}


def get_factor(key: str) -> FactorInfo:
    """按 key 获取因子信息"""
    return _BY_KEY[key]


def get_factor_by_level_col(level_col: str) -> FactorInfo:
    """按 level_col 获取因子信息"""
    return _BY_LEVEL_COL[level_col]


def get_active_factors() -> list[FactorInfo]:
    """返回所有已注册因子列表"""
    return list(FACTOR_REGISTRY)


def get_level_cols() -> list[str]:
    """所有因子的 level_col 列表"""
    return [f.level_col for f in FACTOR_REGISTRY]


def get_factor_display() -> dict[str, str]:
    """{level_col: key}"""
    return {f.level_col: f.key for f in FACTOR_REGISTRY}
```

**Step 2: 更新 data_pipeline.py**

~L140-220 中所有 JSON key 和 DataFrame 列名：
```python
# JSON 读取：旧 key → 新 key
bo.get("volume_surge_ratio")    → bo.get("volume")
bo.get("momentum")              → bo.get("pbm")
bo.get("pk_momentum")           → bo.get("pk_mom")
bo.get("recent_breakout_count") → bo.get("streak")
bo.get("day_str_ratio")         → bo.get("day_str")
bo.get("overshoot_ratio")       → bo.get("overshoot")
bo.get("days_since_last_breakout") → bo.get("drought")

# DataFrame 列名：使用 factor.key
"volume_surge_ratio": volume_surge  → "volume": volume_surge
"momentum": momentum                → "pbm": momentum_val
"pk_momentum": pk_momentum          → "pk_mom": pk_mom_val
"recent_breakout_count": ...        → "streak": ...
"day_str_ratio": ...                → "day_str": ...
"overshoot_ratio": ...              → "overshoot": ...
"oldest_age": ...                   → "age": ...
"test_count": ...                   → "test": ...
"max_peak_volume": ...              → "peak_vol": ...
"max_height": ...                   → "height": ...
"days_since_last_breakout": ...     → "drought": ...
```

同时更新 `_rebuild_peak_features()` 的返回变量名和注释。

`prepare_raw_values()` 函数：确认它使用 `fi.key` 而非 `fi.raw_col`（因为 raw_col 已不存在，DataFrame 列名就是 key）。

**Step 3: 更新 threshold_optimizer.py**

- 文件头部注释中 `bonus_analysis_data` → `factor_analysis_data`
- `bonus_filter.yaml` 的引用注释更新
- `load_factor_modes()` 中读取 yaml_key 使用新的 `fi.yaml_key`（自动生成 `{key}_factor`）
- 函数名 `load_factor_modes` 不变

**Step 4: 更新其他 mining 模块**

所有模块中：
- `get_bonus_cols()` → `get_level_cols()`
- `get_bonus_display()` → `get_factor_display()`
- `get_factor_config()` 和 `get_factor_map()` 如果仍需要，用新结构实现；否则删除（已被 `get_factor()` + property 替代）
- `f.display_name` → `f.key`（用于 DataFrame 索引、模板名等）
- `f.raw_col` → `f.key`（因为 DataFrame 列名就是 key）
- `f.yaml_key` → `f.yaml_key`（property 自动生成，用法不变）
- 注释中的 "bonus" → "factor"

具体文件：
- `stats_analysis.py`: `bonus_cols` → `level_cols`, `bonus_display` → `factor_display`
- `distribution_analysis.py`: 同上
- `template_generator.py`: 模板组合名用 `f.key`，如 `"age+pk_mom+streak+height"`
- `report_generator.py`: 报告标题、列名用 `f.key`
- `factor_diagnosis.py`: `get_factor_map()` → 直接用 `get_active_factors()`，读取 `f.yaml_key`
- `param_writer.py`: `f.display_name` → `f.key`，`f.yaml_key` 不变（自动生成）
- `pipeline.py`: 注释和 bonus 引用更新
- `template_validator.py`: bonus 引用更新
- `__init__.py`: 模块 docstring 更新
- `price_tier_analysis.py`: 原始列名更新

**Step 5: Commit**

```bash
git add BreakoutStrategy/mining/
git commit -m "refactor: unify factor registry and mining pipeline naming"
```

---

## Task 5: YAML 配置文件

**Files:**
- Modify: `configs/params/all_bonus.yaml` → rename to `configs/params/all_factor.yaml`
- Modify: `configs/params/bonus_filter.yaml` → rename to `configs/params/factor_filter.yaml`
- Modify: `configs/params/all_bonus_mined.yaml` → rename to `configs/params/all_factor_mined.yaml`
- Modify: `configs/params/all_bonus_0.yaml` → rename to `configs/params/all_factor_0.yaml`
- Modify: `configs/params/scan_params.yaml` (如果引用了 bonus 配置)
- Update all Python code that references these file paths

**Step 1: 重命名 all_bonus.yaml 配置键**

```yaml
# 旧 → 新
quality_scorer:
  bonus_base_score: 50        → factor_base_score: 50
  age_bonus:                  → age_factor:
  test_bonus:                 → test_factor:
  volume_bonus:               → volume_factor:
  pk_momentum_bonus:          → pk_mom_factor:
  streak_bonus:               → streak_factor:
  pbm_bonus:                  → pbm_factor:
  breakout_day_strength_bonus: → day_str_factor:
  peak_volume_bonus:          → peak_vol_factor:
  drought_bonus:              → drought_factor:
  height_bonus:               → height_factor:
  overshoot_penalty:          → overshoot_factor:
```

**Step 2: 重命名 YAML 文件名**

```bash
git mv configs/params/all_bonus.yaml configs/params/all_factor.yaml
git mv configs/params/bonus_filter.yaml configs/params/factor_filter.yaml
git mv configs/params/all_bonus_mined.yaml configs/params/all_factor_mined.yaml
git mv configs/params/all_bonus_0.yaml configs/params/all_factor_0.yaml
```

**Step 3: 更新所有引用 YAML 路径的代码**

全局搜索 `all_bonus` / `bonus_filter` / `all_bonus_mined` / `all_bonus_0`，替换为新文件名。涉及文件：
- `BreakoutStrategy/mining/param_writer.py` (~L106-108)
- `BreakoutStrategy/mining/pipeline.py`
- `BreakoutStrategy/mining/factor_diagnosis.py` (~L146-148)
- `BreakoutStrategy/UI/config/param_loader.py`
- `scripts/` 下可能引用的脚本
- `configs/buy_condition_config.yaml`（如果引用）

**Step 4: 更新其他 YAML 文件中的 bonus 键**

- `configs/params/scan_params.yaml`: 如果 quality_scorer 部分内嵌了 bonus 键
- `configs/params/all_factor_0.yaml`: 同步 Step 1 的键名变更
- `configs/params/all_factor_mined.yaml`: 同步键名变更（或后续由 param_writer 重新生成）

**Step 5: Commit**

```bash
git add configs/params/ BreakoutStrategy/mining/ scripts/
git commit -m "refactor: rename bonus to factor in YAML configs and file names"
```

---

## Task 6: UI + 其余引用 + 清理

**Files:**
- Modify: `BreakoutStrategy/UI/config/param_editor_schema.py` (~L88-402)
- Modify: `BreakoutStrategy/UI/config/param_loader.py` (~L298-402)
- Modify: `BreakoutStrategy/UI/charts/components/score_tooltip.py`
- Modify: `BreakoutStrategy/UI/styles.py` (如有 bonus 引用)
- Modify: `BreakoutStrategy/observation/evaluators/config.py` (如有 bonus 引用)
- Modify: `BreakoutStrategy/observation/evaluators/components/price_confirm.py` (如有 bonus 引用)
- Modify: `scripts/benchmark_samplers.py` (如有 bonus 引用)
- Modify: `BreakoutStrategy/analysis/test/test_integrated_system.py`

**Step 1: 更新 param_editor_schema.py**

~L88-402 中所有配置组键名：
```python
# 旧 → 新
"bonus_base_score": {...}              → "factor_base_score": {...}
"age_bonus": {...}                     → "age_factor": {...}
"test_bonus": {...}                    → "test_factor": {...}
"height_bonus": {...}                  → "height_factor": {...}
"peak_volume_bonus": {...}             → "peak_vol_factor": {...}
"volume_bonus": {...}                  → "volume_factor": {...}
"pbm_bonus": {...}                     → "pbm_factor": {...}
"streak_bonus": {...}                  → "streak_factor": {...}
"drought_bonus": {...}                 → "drought_factor": {...}
"overshoot_penalty": {...}             → "overshoot_factor": {...}
"breakout_day_strength_bonus": {...}   → "day_str_factor": {...}
"pk_momentum_bonus": {...}             → "pk_mom_factor": {...}

# 属性标记
"is_bonus_group": True                 → "is_factor_group": True
```

每个配置组的 `description` 更新以使用 `display_label` 格式。

**Step 2: 更新 param_loader.py**

~L298-402 中所有 bonus 配置加载逻辑：
- YAML 键名 `bonus_base_score` → `factor_base_score`
- 各因子键名按映射表替换

**Step 3: 更新 score_tooltip.py**

~L99-245 中：
- `breakdown.bonuses` → `breakdown.factors`
- `BonusDetail` 引用 → `FactorDetail`
- `b.bonus` → `f.multiplier`
- 方法名 `_build_bonus_table()` → `_build_factor_table()`

**Step 4: 更新 observation/evaluators**

检查 `config.py` 和 `price_confirm.py` 中的 bonus 引用，替换为 factor。

**Step 5: 更新测试文件**

`test_integrated_system.py` 中所有字段引用和断言更新。

**Step 6: 全局扫描残留**

```bash
# 确认无残留 bonus 引用（除了 git history 和 docs/）
grep -rn "bonus" --include="*.py" BreakoutStrategy/
grep -rn "_bonus" --include="*.yaml" configs/
```

如有残留，逐一修复。

**Step 7: 更新 docs 统计报告**

`docs/statistics/` 下的报告文件由 mining 管道自动生成，下次运行时会用新命名。如果报告中有硬编码的 "bonus" 文字，一并替换。

**Step 8: Commit**

```bash
git add BreakoutStrategy/UI/ BreakoutStrategy/observation/ BreakoutStrategy/analysis/test/ scripts/ docs/
git commit -m "refactor: complete bonus to factor rename in UI, observation, and tests"
```

---

## 验证清单

每个 Task 完成后执行：

1. **语法检查**: `python -c "from BreakoutStrategy.analysis.breakout_detector import Breakout, Peak"` 等关键导入
2. **全局搜索残留**: `grep -rn "bonus" --include="*.py"` 确认无遗漏
3. **Pipeline 冒烟测试**: 如果可以运行 mining pipeline，执行一次确认无崩溃
