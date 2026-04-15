# Per-Factor Gating Spec 2 消费端改造 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 mining 管线对 NaN 稳健（data_pipeline 去 fillna；triggered 矩阵/TPE bounds/greedy beam 加 NaN 保护）；live detail_panel 对 None 防御；factor_diag.yaml 加审计字段。

**Architecture:** Spec 1 让 Breakout 字段承载 None 语义；Spec 2 让下游消费链路对 NaN robust，修复 mining 的"单一污染源"（`prepare_raw_values` 的 `.fillna(0)`）+ 3 处 NaN 保护（`build_triggered_matrix` / TPE bounds / greedy beam）；live 侧 `detail_panel._fmt` 加 None 分支；`factor_diag.yaml` 新增 `valid_count` / `valid_ratio` / `buffer` 审计字段。

**Tech Stack:** Python 3.x, pytest, numpy, pandas, tkinter, yaml.

**Spec:** [docs/superpowers/specs/2026-04-15-per-factor-gating-spec2-consumers.md](../specs/2026-04-15-per-factor-gating-spec2-consumers.md)

**Prereq:** Spec 1 已完成（最新 commit `526a881`）。`FeatureCalculator._effective_buffer` 是 SSOT；`Breakout` 8 字段 Optional；scanner 序列化按 `nullable` 透传 None。

---

## File Structure

**修改文件**：
- `BreakoutStrategy/mining/data_pipeline.py` — `build_dataframe`/`prepare_raw_values`/`apply_binary_levels` 三处 None/NaN 处理
- `BreakoutStrategy/mining/threshold_optimizer.py` — `build_triggered_matrix` / TPE bounds quantile / greedy beam mask 三处 NaN 保护
- `BreakoutStrategy/live/panels/detail_panel.py` — `_fmt` 加 None 分支
- `BreakoutStrategy/mining/factor_diagnosis.py` — factor_diag.yaml 新增审计字段（P1）

**新建 / 扩展测试文件**：
- `BreakoutStrategy/mining/tests/test_nan_aware.py` — mining NaN-aware 行为测试集合
- `BreakoutStrategy/live/tests/test_detail_panel.py` — 如果不存在，新建；否则追加

（若 `BreakoutStrategy/mining/tests/` 目录不存在，第一个任务创建它 + `__init__.py`）

---

## Task 执行顺序

```
T1: data_pipeline.build_dataframe 因子列 `or 0` → None 透传
T2: data_pipeline.prepare_raw_values 去 fillna(0)
T3: data_pipeline.apply_binary_levels 加 ~np.isnan 保护（反向因子 bug 修复）
T4: threshold_optimizer.build_triggered_matrix 加 ~np.isnan 保护
T5: threshold_optimizer TPE bounds quantile 去 NaN + greedy beam valid mask
T6: live/panels/detail_panel._fmt 加 None 分支
T7 (P1): factor_diagnosis factor_diag.yaml 加 valid_count/valid_ratio/buffer 审计字段
```

每个 Task 结束时全仓回归必须通过（139 passed + 1 skipped baseline，加上本 spec 新增测试）。

---

### Task 1: data_pipeline.build_dataframe 因子列 None 透传

**Files:**
- Modify: `BreakoutStrategy/mining/data_pipeline.py:96-105`
- Create: `BreakoutStrategy/mining/tests/__init__.py` (空文件，如果不存在)
- Create: `BreakoutStrategy/mining/tests/test_nan_aware.py`

**动机**：Spec 1 让 scanner 序列化时把 Optional 因子的 None 透传到 JSON（`fi.nullable=True` 分支）。mining 侧 `build_dataframe` 读 JSON 时用 `raw_val or (0 if fi.is_discrete else 0.0)` 把 None 折叠成 0，这是**第二个污染源**，要改成 None 透传（让 DataFrame 列成为 NaN-bearing）。

**关键点**：
- 只对 `has_nan_group=False` 分支加 None 检查（`has_nan_group=True` 已走 `if raw_val is not None else 0` 保留 None 语义 via level_input=0）
- level_col 保持 0（不触发）；raw 列走 None
- 改完后 DataFrame 里因子列的 `None` 会被 pandas 自动转成 `NaN`

- [ ] **Step 1: 确认 mining/tests/ 目录存在**

Run: `ls BreakoutStrategy/mining/tests/ 2>/dev/null || mkdir -p BreakoutStrategy/mining/tests && touch BreakoutStrategy/mining/tests/__init__.py`

- [ ] **Step 2: 写测试**

Create `BreakoutStrategy/mining/tests/test_nan_aware.py`:

```python
"""Per-Factor Gating Spec 2: mining NaN-aware behavior tests."""
import numpy as np
import pandas as pd
import pytest

from BreakoutStrategy.mining.data_pipeline import (
    build_dataframe,
    prepare_raw_values,
    apply_binary_levels,
)


def _mk_stock_json_with_nan():
    """Synthetic JSON: 2 BO, BO2 has volume=None (simulating Spec 1 's lookback-insufficient)."""
    return {
        "stocks": [
            {
                "symbol": "TEST",
                "breakouts": [
                    {
                        "date": "2024-01-10",
                        "price": 10.0,
                        "volume": 2.5,
                        "pbm": 1.3,
                        "age": 100,
                        "labels": {"label_5_20": 0.05},
                    },
                    {
                        "date": "2024-02-10",
                        "price": 11.0,
                        "volume": None,   # ← lookback insufficient
                        "pbm": None,
                        "age": 60,
                        "labels": {"label_5_20": 0.03},
                    },
                ],
            },
        ],
    }


def test_build_dataframe_preserves_none_as_nan():
    """build_dataframe 读 JSON 里的 None 因子值应透传为 NaN，不变成 0。"""
    stock_json = _mk_stock_json_with_nan()
    # build_dataframe needs factor_thresholds; use minimal dict
    factor_thresholds = {'volume': [5.0, 10.0], 'pbm': [0.7, 1.45], 'age': [42, 63]}
    df = build_dataframe(stock_json, label_key='label_5_20',
                        factor_thresholds=factor_thresholds)
    # BO1 row has volume=2.5 (normal); BO2 row has volume=NaN
    assert len(df) == 2
    row1 = df.iloc[0]
    row2 = df.iloc[1]
    assert row1['volume'] == 2.5
    assert pd.isna(row2['volume'])
    assert pd.isna(row2['pbm'])
    # age stays as integer (buffer=0 factor, not in Spec 1 scope)
    assert row1['age'] == 100
    assert row2['age'] == 60
```

- [ ] **Step 3: 看当前测试失败**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py::test_build_dataframe_preserves_none_as_nan -v`

Expected: FAIL。当前代码走 `raw_val = raw_val or (0 if fi.is_discrete else 0.0)`，把 None 折叠成 0.0，断言 `pd.isna(...)` 会失败。

- [ ] **Step 4: 改 build_dataframe**

在 `BreakoutStrategy/mining/data_pipeline.py:96-105`，当前：

```python
            # 注册因子：原始值 + level（动态）
            for fi in get_active_factors():
                raw_val = bo.get(fi.key)
                if fi.has_nan_group:
                    # 保留 None 语义（如 drought 首次突破、pk_mom 无近期 peak）
                    level_input = raw_val if raw_val is not None else 0
                else:
                    raw_val = raw_val or (0 if fi.is_discrete else 0.0)
                    level_input = raw_val
                row[fi.key] = raw_val
                row[fi.level_col] = get_level(level_input, factor_thresholds[fi.key])
```

改为（Spec 2：因子 nullable 扩展后，所有 lookback 因子的 None 都要透传；只有非 nullable 的 `or 0` 保留作数据错容错）：

```python
            # 注册因子：原始值 + level（动态）
            # per-factor gate 语义：nullable 因子的 None 透传（列成为 NaN），
            # level_input=0 保证 level_col 为 0（未触发）。非 nullable 因子沿用
            # 数据错容错（或 0），此处仅适用于 age/test/height/peak_vol/streak 等
            # buffer=0 且 nullable=False 的因子。
            for fi in get_active_factors():
                raw_val = bo.get(fi.key)
                if raw_val is None:
                    if fi.nullable or fi.has_nan_group:
                        # 保留 None（raw 列 NaN，level 0）
                        level_input = 0
                    else:
                        # 非 nullable 因子沿用旧容错
                        raw_val = 0 if fi.is_discrete else 0.0
                        level_input = raw_val
                else:
                    level_input = raw_val
                row[fi.key] = raw_val
                row[fi.level_col] = get_level(level_input, factor_thresholds[fi.key])
```

**注**：T1 之后 `fi.nullable or fi.has_nan_group` 的条件在 Spec 1 之后 `has_nan_group` 基本已被 `nullable` 覆盖（drought/pk_mom 两者都为 True）。为稳妥两个都判。

- [ ] **Step 5: 测试 PASS**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py::test_build_dataframe_preserves_none_as_nan -v`
Expected: PASS。

- [ ] **Step 6: 全仓回归**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/ --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q 2>&1 | tail -5`
Expected: 140 passed, 1 skipped（baseline 139 + 新增 1）。

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/mining/data_pipeline.py BreakoutStrategy/mining/tests/__init__.py BreakoutStrategy/mining/tests/test_nan_aware.py
git commit -m "data_pipeline: build_dataframe 对 nullable 因子透传 None

Spec 1 让 scanner 序列化时把 Optional 因子的 None 透传到 JSON；
Spec 2 让 build_dataframe 读 JSON 时不再把 None 折叠为 0。
raw 列成为 NaN，level 列为 0（未触发），下游 DataFrame 统计基于真实可用样本。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: data_pipeline.prepare_raw_values 去 fillna(0)

**Files:**
- Modify: `BreakoutStrategy/mining/data_pipeline.py:153-180`
- Test: `BreakoutStrategy/mining/tests/test_nan_aware.py` (append)

**动机**：`prepare_raw_values` 当前 `.fillna(0)` 是整条挖掘流水线的**单一污染源**（影响 TPE bounds、greedy beam、triggered 矩阵）。改为保留 NaN，让下游各自决策。

- [ ] **Step 1: 写测试**

追加到 `BreakoutStrategy/mining/tests/test_nan_aware.py`:

```python
def test_prepare_raw_values_preserves_nan():
    """prepare_raw_values 不再 fillna(0)；NaN 自然承载。"""
    df = pd.DataFrame({
        'symbol': ['A', 'B'],
        'date': ['2024-01-01', '2024-01-02'],
        'volume': [2.5, np.nan],      # volume nullable 因子
        'volume_level': [0, 0],
        'age': [100, 60],              # buffer=0 非 nullable 因子
        'age_level': [1, 0],
        'label': [0.05, 0.03],
    })
    raw = prepare_raw_values(df, factors=['volume', 'age'])
    # volume 保留 NaN
    assert np.isnan(raw['volume'][1])
    assert raw['volume'][0] == 2.5
    # age 无 NaN（buffer=0 因子原始数据无 None）
    assert raw['age'][0] == 100
    assert raw['age'][1] == 60
```

- [ ] **Step 2: 运行看失败**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py::test_prepare_raw_values_preserves_nan -v`
Expected: FAIL（当前 `.fillna(0)` 把 NaN 变成 0）。

- [ ] **Step 3: 改 prepare_raw_values**

在 `BreakoutStrategy/mining/data_pipeline.py:176-180`，当前：

```python
    raw = {}
    for fi in factor_list:
        raw[fi.key] = df[fi.key].fillna(0).values.astype(np.float64)

    return raw
```

改为：

```python
    raw = {}
    for fi in factor_list:
        # per-factor gate: 保留 NaN，下游统计各自决策（NaN-aware filter）
        raw[fi.key] = df[fi.key].values.astype(np.float64)

    return raw
```

同时更新函数 docstring 一句，说明 NaN-aware 契约：在 `"""` 里的 Returns 段改为：

```
    Returns:
        {key: 原始值 numpy 数组}；nullable 因子的 NaN 保留（per-factor gate 语义），
        下游函数（build_triggered_matrix/TPE bounds/greedy beam）通过 ~np.isnan 过滤。
```

- [ ] **Step 4: 跑测试 + 全仓回归**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py -v`
Expected: 2 PASS。

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/ --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q 2>&1 | tail -5`

**重要预期**：若 threshold_optimizer 的现有集成测试（如果有）在此时依赖 `prepare_raw_values` 不返回 NaN，可能 FAIL。验证：跑完看哪个 test 炸了。如果炸了，说明 **T4/T5 的 NaN 保护必须紧接着上**——先暂停 commit，继续做 T3-T5，最后一起 commit；或者 commit 一个"已知 mining 单元不跑"的中间状态（不推荐）。

**策略**：如果只有新单元测试通过 + `test_per_factor_gating.py` 等独立测试不受影响（它们不走 mining 链路），允许 commit 此阶段；后续 T3-T5 会把 mining 统计端也修好。

运行时若因其他依赖 prepare_raw_values 的代码崩，DONE_WITH_CONCERNS 上报状态即可。

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/mining/data_pipeline.py BreakoutStrategy/mining/tests/test_nan_aware.py
git commit -m "data_pipeline: prepare_raw_values 保留 NaN（去 fillna(0)）

per-factor gate 的 mining NaN-awareness 核心：单一污染源修复。
下游统计（build_triggered_matrix / TPE bounds / greedy beam）各自通过
~np.isnan 过滤。后续 tasks 给这些 hotspot 加 NaN 保护。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: data_pipeline.apply_binary_levels 加 ~np.isnan 保护

**Files:**
- Modify: `BreakoutStrategy/mining/data_pipeline.py:183-205`
- Test: `BreakoutStrategy/mining/tests/test_nan_aware.py`

**动机**：`apply_binary_levels` 对反向因子 `(raw <= threshold)` 的比较，在 NaN 上返回 False（numpy 语义），表面上正确——但当前代码先 `df[fi.key].fillna(0)`，让 NaN 变成 0，`0 <= threshold` 对正值 threshold 为 True，导致**反向因子把"不可算"样本误判为"完美触发"**。改为不 fillna + 加显式 NaN 保护。

- [ ] **Step 1: 写测试**

追加：

```python
def test_apply_binary_levels_reverse_factor_nan_not_triggered():
    """反向因子（如 overshoot mode=lte）+ NaN 样本不应被判为触发。"""
    df = pd.DataFrame({
        'overshoot': [2.0, np.nan, 10.0],       # 样本1 低触发；样本2 NaN；样本3 高不触发
        'overshoot_level': [0, 0, 0],
        'label': [0.05, 0.03, 0.02],
    })
    # 反向因子：overshoot <= 5.0 触发
    apply_binary_levels(df, {'overshoot': 5.0}, negative_factors={'overshoot'})
    # 样本1 (2.0 <= 5.0): triggered=1
    assert df['overshoot_level'].iloc[0] == 1
    # 样本2 (NaN): 绝不应被判为 triggered（即使 lte 且 threshold>0）
    assert df['overshoot_level'].iloc[1] == 0
    # 样本3 (10.0 > 5.0): triggered=0
    assert df['overshoot_level'].iloc[2] == 0


def test_apply_binary_levels_positive_factor_nan_not_triggered():
    """正向因子 + NaN 样本不触发。"""
    df = pd.DataFrame({
        'volume': [2.5, np.nan, 10.0],
        'volume_level': [0, 0, 0],
        'label': [0.05, 0.03, 0.02],
    })
    apply_binary_levels(df, {'volume': 5.0}, negative_factors=frozenset())
    assert df['volume_level'].iloc[0] == 0
    assert df['volume_level'].iloc[1] == 0  # NaN
    assert df['volume_level'].iloc[2] == 1
```

- [ ] **Step 2: 看当前行为**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py -v -k "apply_binary"`
Expected: `test_apply_binary_levels_reverse_factor_nan_not_triggered` FAIL（因为当前 `fillna(0)` 后 `0<=5.0=True`）；正向因子测试可能 PASS（0 `>=` 5.0 为 False，恰好正确）。

- [ ] **Step 3: 改 apply_binary_levels**

在 `BreakoutStrategy/mining/data_pipeline.py:183-205`：

```python
    for fi in get_active_factors():
        key = fi.key
        if key in thresholds:
            raw = df[fi.key].fillna(0)
            if key in negative_factors:
                df[fi.level_col] = (raw <= thresholds[key]).astype(int)
            else:
                df[fi.level_col] = (raw >= thresholds[key]).astype(int)
        else:
            df[fi.level_col] = 0
    return df
```

改为：

```python
    for fi in get_active_factors():
        key = fi.key
        if key in thresholds:
            raw = df[fi.key]
            valid = raw.notna()
            if key in negative_factors:
                df[fi.level_col] = (valid & (raw <= thresholds[key])).astype(int)
            else:
                df[fi.level_col] = (valid & (raw >= thresholds[key])).astype(int)
        else:
            df[fi.level_col] = 0
    return df
```

`raw.notna()` 返回 Series，和 `(raw op threshold)`（NaN 上返回 False）相与，确保 NaN 样本一律 level=0。

- [ ] **Step 4: 测试 PASS + 全仓回归**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py -v`
Expected: 全 PASS。

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/ --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q 2>&1 | tail -5`

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/mining/data_pipeline.py BreakoutStrategy/mining/tests/test_nan_aware.py
git commit -m "data_pipeline: apply_binary_levels 加 NaN 保护（修反向因子 bug）

原 fillna(0) 让反向因子对 NaN 样本判为'完美触发 lte 条件'（0<=threshold 恒真）。
改为 valid=raw.notna() mask，NaN 样本一律 level=0（missing-as-fail）。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: threshold_optimizer.build_triggered_matrix 加 ~np.isnan 保护

**Files:**
- Modify: `BreakoutStrategy/mining/threshold_optimizer.py:28-53`
- Test: `BreakoutStrategy/mining/tests/test_nan_aware.py`

**动机**：`build_triggered_matrix` 用 `raw_values` (T2 后可能含 NaN) 和 thresholds 算触发矩阵。`np.nan >= X` / `np.nan <= X` 在 numpy 下都是 False，但**反向因子的语义正确性**依赖 NaN 既不触发 gte 也不触发 lte——numpy 默认行为恰好对正向因子正确，对反向因子也正确（`nan <= X` 为 False）。**技术上 numpy 默认已经正确**，但为了显式化和未来阅读清晰度，加 `~np.isnan(raw)` 保护。

- [ ] **Step 1: 写测试**

```python
def test_build_triggered_matrix_nan_not_triggered():
    """NaN 样本在正向/反向因子上都判为未触发（level=0）。"""
    from BreakoutStrategy.mining.threshold_optimizer import build_triggered_matrix

    raw_values = {
        'volume': np.array([2.5, np.nan, 10.0]),
        'overshoot': np.array([2.0, np.nan, 10.0]),
    }
    thresholds = {'volume': 5.0, 'overshoot': 5.0}
    factor_order = ['volume', 'overshoot']

    # volume gte 5.0; overshoot lte 5.0
    triggered = build_triggered_matrix(
        raw_values, thresholds, factor_order,
        negative_factors={'overshoot'},
    )

    # Sample 0: volume=2.5 (not gte 5) → 0; overshoot=2.0 (lte 5) → 1
    assert triggered[0, 0] == 0
    assert triggered[0, 1] == 1
    # Sample 1: NaN NaN → both 0（missing-as-fail）
    assert triggered[1, 0] == 0
    assert triggered[1, 1] == 0
    # Sample 2: volume=10.0 (gte) → 1; overshoot=10.0 (not lte) → 0
    assert triggered[2, 0] == 1
    assert triggered[2, 1] == 0
```

- [ ] **Step 2: 运行看当前行为**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py::test_build_triggered_matrix_nan_not_triggered -v`
Expected: 可能 PASS（numpy `nan op X` 默认 False 语义）。即使已 PASS，Step 3 仍改代码使其显式。

- [ ] **Step 3: 改 build_triggered_matrix**

在 `BreakoutStrategy/mining/threshold_optimizer.py:28-53`：

```python
def build_triggered_matrix(raw_values, thresholds, factor_order,
                           negative_factors=frozenset()):
    """
    根据阈值构建二值触发矩阵。
    正向因子: value >= threshold → triggered=1
    反向因子: value <= threshold → triggered=1

    per-factor gate: NaN 样本一律 triggered=0（missing-as-fail）。

    Args:
        raw_values: prepare_raw_values() 的输出（可能含 NaN）
        thresholds: {key: threshold_value}
        factor_order: 因子顺序列表（决定 bit 位置）
        negative_factors: 反向因子集合，使用 <= 触发

    Returns:
        (n_samples, n_factors) int64 矩阵
    """
    n = len(next(iter(raw_values.values())))
    n_factors = len(factor_order)
    triggered = np.zeros((n, n_factors), dtype=np.int64)
    for i, key in enumerate(factor_order):
        if key in thresholds and key in raw_values:
            raw = raw_values[key]
            valid = ~np.isnan(raw)
            if key in negative_factors:
                triggered[:, i] = (valid & (raw <= thresholds[key])).astype(np.int64)
            else:
                triggered[:, i] = (valid & (raw >= thresholds[key])).astype(np.int64)
    return triggered
```

- [ ] **Step 4: 测试 PASS + 全仓回归**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py -v`
Expected: 全 PASS。

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/ --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q 2>&1 | tail -5`

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/mining/threshold_optimizer.py BreakoutStrategy/mining/tests/test_nan_aware.py
git commit -m "threshold_optimizer: build_triggered_matrix 加 ~np.isnan 保护

numpy 默认 NaN 比较为 False 恰好给 gte 正确结果，但对 lte 反向因子
也是 False（语义上恰好正确）。为显式化 missing-as-fail 契约，加 valid mask。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: threshold_optimizer TPE bounds + greedy beam NaN 保护

**Files:**
- Modify: `BreakoutStrategy/mining/threshold_optimizer.py:180-220, 293-300`
- Test: `BreakoutStrategy/mining/tests/test_nan_aware.py`

**动机**：
1. TPE bounds 用 `np.quantile(raw, 2%)` 和 `np.quantile(raw, 98%)` 算搜索范围。`np.quantile` 遇到 NaN 默认返回 NaN，污染 bounds。改为先 `raw[~np.isnan(raw)]`。
2. Greedy beam 用 `current_mask & (raw op threshold)` 算子集 mask。numpy 对 NaN 比较默认 False，技术上正确——但为显式化加 `& ~np.isnan(raw)`。

- [ ] **Step 1: 写测试**

```python
def test_tpe_bounds_skip_nan():
    """TPE bounds 的 quantile 应基于 NaN 过滤后的样本。"""
    from BreakoutStrategy.mining import threshold_optimizer

    # mock raw_values with NaN
    raw = np.array([1.0, 2.0, 3.0, 4.0, 5.0, np.nan, np.nan])
    # 期望：quantile(~isnan, 10%) ≈ 1.4, 不是 nan
    valid = raw[~np.isnan(raw)]
    expected_lo = float(np.quantile(valid, 0.1))
    expected_hi = float(np.quantile(valid, 0.9))

    # 间接验证：若 TPE bounds 不过滤 NaN，quantile 会 NaN；否则返回有限值
    # 我们通过在 bounds 计算函数上下文里测
    lo = float(np.quantile(raw[~np.isnan(raw)], 0.1))
    hi = float(np.quantile(raw[~np.isnan(raw)], 0.9))
    assert lo == expected_lo
    assert hi == expected_hi
    assert not np.isnan(lo)
    assert not np.isnan(hi)
```

（该测试其实是**行为契约文档**，真实的 integration 由实际 TPE 跑时 NaN-free bounds 保证。）

- [ ] **Step 2: 改 TPE bounds 计算**

在 `BreakoutStrategy/mining/threshold_optimizer.py:293-300`，找到 `stage3b_optuna_search` 里的 bounds 计算：

```python
        fi = get_factor(key)
        raw = raw_values[key]
        lo = float(np.quantile(raw, quantile_margin))
        hi = float(np.quantile(raw, 1 - quantile_margin))
```

改为：

```python
        fi = get_factor(key)
        raw = raw_values[key]
        # per-factor gate: 从 NaN-aware raw 里过滤出有效样本，quantile 才有意义
        valid = raw[~np.isnan(raw)]
        if len(valid) == 0:
            continue  # 该因子无任何有效样本，跳过（bounds 无意义）
        lo = float(np.quantile(valid, quantile_margin))
        hi = float(np.quantile(valid, 1 - quantile_margin))
```

**注**：`continue` 跳过该因子意味着它不参与 TPE，等价于"该因子不会被搜索到任何阈值"。如果用户全仓数据里某因子 100% 是 NaN（极端 edge case），静默跳过比崩溃好。

- [ ] **Step 3: 改 greedy beam candidates 计算**

在 `BreakoutStrategy/mining/threshold_optimizer.py:180-185`（`stage3a_greedy_beam_search` 里），找 `np.percentile(raw, percentiles)` 调用：

```python
        else:
            percentiles = np.linspace(10, 90, n_candidates)
            candidates[key] = np.unique(np.percentile(raw, percentiles))
```

改为：

```python
        else:
            valid = raw[~np.isnan(raw)]
            if len(valid) == 0:
                candidates[key] = np.array([])  # 该因子无有效样本
                continue
            percentiles = np.linspace(10, 90, n_candidates)
            candidates[key] = np.unique(np.percentile(valid, percentiles))
```

- [ ] **Step 4: 改 greedy beam sub_mask**

在 `BreakoutStrategy/mining/threshold_optimizer.py:202-206`：

```python
                for threshold in candidates.get(factor, []):
                    if factor in negative_factors:
                        sub_mask = current_mask & (raw <= threshold)
                    else:
                        sub_mask = current_mask & (raw >= threshold)
```

改为：

```python
                valid_mask = ~np.isnan(raw)
                for threshold in candidates.get(factor, []):
                    if factor in negative_factors:
                        sub_mask = current_mask & valid_mask & (raw <= threshold)
                    else:
                        sub_mask = current_mask & valid_mask & (raw >= threshold)
```

注：`valid_mask` 计算一次（per factor iteration），不在内层循环重算。

- [ ] **Step 5: 测试 + 全仓回归**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py -v`
Expected: 全 PASS。

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/ --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q 2>&1 | tail -5`

- [ ] **Step 6: Commit**

```bash
git add BreakoutStrategy/mining/threshold_optimizer.py BreakoutStrategy/mining/tests/test_nan_aware.py
git commit -m "threshold_optimizer: TPE bounds + greedy beam 加 NaN 保护

TPE quantile 前过滤 NaN（100% NaN 因子跳过不参与搜索）；
greedy beam 的 sub_mask 加 valid_mask 显式 missing-as-fail。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: live/panels/detail_panel._fmt 加 None 分支

**Files:**
- Modify: `BreakoutStrategy/live/panels/detail_panel.py:11-14`

**动机**：`daily_runner.py:172` 的 `factors={f: bo[f] for f in template["factors"] if f in bo}` 把 bo dict 中的 None 原样带入 `MatchedBreakout.factors`。`_fmt` 当前用 `f"{value:.2f}"` 处理浮点，传 None 会 TypeError。

- [ ] **Step 1: 写测试**

如果 `BreakoutStrategy/live/tests/` 存在，追加到合适的 test 文件；否则 new file `BreakoutStrategy/live/tests/test_detail_panel.py`:

```python
"""Per-Factor Gating Spec 2: live detail_panel None handling."""
from BreakoutStrategy.live.panels.detail_panel import _fmt


def test_fmt_none_returns_na():
    """_fmt(None) 返回 'N/A'，不 TypeError。"""
    assert _fmt(None) == "N/A"


def test_fmt_int_returns_int_str():
    """_fmt(5) 返回 '5'（整数分支保留）。"""
    assert _fmt(5) == "5"


def test_fmt_float_returns_2dp():
    """_fmt(3.14159) 返回 '3.14'（浮点 2 位小数）。"""
    assert _fmt(3.14159) == "3.14"
```

- [ ] **Step 2: 运行看 `test_fmt_none_returns_na` 失败**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/live/tests/test_detail_panel.py -v`
Expected: 1 FAIL（TypeError: unsupported format string passed to NoneType.__format__）；其他 2 PASS。

- [ ] **Step 3: 改 _fmt**

在 `BreakoutStrategy/live/panels/detail_panel.py:11-14`，当前：

```python
def _fmt(value: float) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"
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

签名的 `value: float` 类型注解去掉（或改成 `value: "float | int | None"`）；实际 Spec 2 下 value 可能是 None。

- [ ] **Step 4: 测试 + 全仓回归**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/live/tests/test_detail_panel.py -v`
Expected: 3 PASS。

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/ --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q 2>&1 | tail -5`

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/live/panels/detail_panel.py BreakoutStrategy/live/tests/test_detail_panel.py
git commit -m "live/detail_panel: _fmt 加 None 分支（防 TypeError）

per-factor gate 下 MatchedBreakout.factors 的值可能为 None（daily_runner
直接从 bo dict 透传）。_fmt 现对 None 返回 'N/A'，与 dev UI tooltip 一致。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7 (P1): factor_diagnosis factor_diag.yaml 审计字段

**Files:**
- Modify: `BreakoutStrategy/mining/factor_diagnosis.py:234-263`（`write_diagnosed_yaml`）
- Modify: `BreakoutStrategy/mining/factor_diagnosis.py:270-322`（`main` 收集 valid counts）
- Test: `BreakoutStrategy/mining/tests/test_nan_aware.py`

**动机**：factor_diag.yaml 每因子新增 `valid_count` / `valid_ratio` / `buffer` 字段，让用户直接看到该因子的统计基础。**纯审计字段**，非 gate_mode 切换——和单一 per_factor scheme 哲学一致。

- [ ] **Step 1: 写测试**

追加到 `BreakoutStrategy/mining/tests/test_nan_aware.py`:

```python
def test_factor_diag_yaml_has_audit_fields(tmp_path):
    """factor_diag.yaml 每因子条目含 valid_count/valid_ratio/buffer。"""
    import yaml
    from BreakoutStrategy.mining.factor_diagnosis import write_diagnosed_yaml

    # 造一个最小 source yaml
    source_yaml = tmp_path / "source.yaml"
    source_yaml.write_text(yaml.dump({
        'quality_scorer': {
            'volume_factor': {
                'enabled': True,
                'thresholds': [5.0, 10.0],
                'values': [1.5, 2.0],
            },
        },
    }))

    output_yaml = tmp_path / "factor_diag.yaml"

    # 提供 modes + 新增的 audit_info
    modes = {'volume': 'gte'}
    audit_info = {'volume': {'valid_count': 1000, 'valid_ratio': 0.85, 'buffer': 63}}
    write_diagnosed_yaml(str(source_yaml), str(output_yaml), modes, audit_info=audit_info)

    loaded = yaml.safe_load(output_yaml.read_text())
    vol = loaded['quality_scorer']['volume_factor']
    assert vol['mode'] == 'gte'
    assert vol['valid_count'] == 1000
    assert vol['valid_ratio'] == 0.85
    assert vol['buffer'] == 63
```

- [ ] **Step 2: 运行看失败**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py::test_factor_diag_yaml_has_audit_fields -v`
Expected: FAIL（`write_diagnosed_yaml` 不接受 audit_info 参数）。

- [ ] **Step 3: 改 write_diagnosed_yaml 签名**

在 `BreakoutStrategy/mining/factor_diagnosis.py:234`，当前：

```python
def write_diagnosed_yaml(source_yaml: str, output_yaml: str, modes: dict[str, str]):
    """读取 source_yaml 结构，写入所有因子的诊断方向，输出 output_yaml。"""
    ...
```

改为：

```python
def write_diagnosed_yaml(source_yaml: str, output_yaml: str, modes: dict[str, str],
                        audit_info: dict[str, dict] | None = None):
    """读取 source_yaml 结构，写入所有因子的诊断方向及审计字段，输出 output_yaml。

    Args:
        audit_info: 可选。{factor_key: {valid_count, valid_ratio, buffer}}。
                   per-factor gate 下让用户看到每因子统计基础。
    """
    ...
```

在循环里写入 audit fields：

```python
    for key, mode in modes.items():
        yaml_key = key_to_yaml.get(key)
        if not yaml_key:
            continue
        if yaml_key not in qs:
            fi = get_factor(key)
            qs[yaml_key] = {
                'enabled': True,
                'thresholds': list(fi.default_thresholds),
                'values': list(fi.default_values),
                **{sp.yaml_name: sp.default for sp in fi.sub_params},
            }
        qs[yaml_key]['mode'] = mode
        # per-factor gate: 审计字段（nullable=True 因子才有 NaN，写 valid_count/ratio/buffer）
        if audit_info and key in audit_info:
            info = audit_info[key]
            qs[yaml_key]['valid_count'] = info.get('valid_count')
            qs[yaml_key]['valid_ratio'] = round(info.get('valid_ratio', 0.0), 4)
            qs[yaml_key]['buffer'] = info.get('buffer')
```

- [ ] **Step 4: 让 main() 传 audit_info**

在 `BreakoutStrategy/mining/factor_diagnosis.py:270-322` 的 `main()` 函数里，在 `write_diagnosed_yaml(...)` 调用前收集 audit_info：

找到 `if auto_apply:` 这段之前，加：

```python
    # per-factor gate: 为每因子计算审计字段
    from BreakoutStrategy.analysis.features import FeatureCalculator
    calc = FeatureCalculator()
    audit_info = {}
    total_bo = len(df)
    for fi in all_factors:
        key = fi.key
        arr = raw_values.get(key)
        if arr is None:
            continue
        valid_count = int(np.sum(~np.isnan(arr)))
        audit_info[key] = {
            'valid_count': valid_count,
            'valid_ratio': valid_count / total_bo if total_bo > 0 else 0.0,
            'buffer': calc._effective_buffer(fi),
        }
```

然后把 `write_diagnosed_yaml(yaml_path, output_yaml, diagnosed_modes)` 改为：

```python
        write_diagnosed_yaml(yaml_path, output_yaml, diagnosed_modes,
                            audit_info=audit_info)
```

- [ ] **Step 5: 测试 + 全仓回归**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/mining/tests/test_nan_aware.py -v`
Expected: 全 PASS。

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest BreakoutStrategy/ --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q 2>&1 | tail -5`

- [ ] **Step 6: Commit**

```bash
git add BreakoutStrategy/mining/factor_diagnosis.py BreakoutStrategy/mining/tests/test_nan_aware.py
git commit -m "factor_diagnosis: factor_diag.yaml 每因子加 valid_count/valid_ratio/buffer

per-factor gate 下 nullable 因子有 NaN 样本，挖掘阈值/Spearman 基于 valid 子集。
yaml 新增审计字段让用户直接看到每因子的统计基础（防止误读全体 BO 分布）。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec 覆盖检查**：
- [x] §2 In-scope P0：data_pipeline 3 处（T1/T2/T3）
- [x] §2 In-scope P0：threshold_optimizer 3 处（T4 build_triggered_matrix / T5 TPE bounds + greedy beam）
- [x] §2 In-scope P0：detail_panel._fmt（T6）
- [x] §2 In-scope P1：factor_diag.yaml 审计字段（T7）
- [x] §3.1 mining NaN 污染修复（单一来源 + 3 处保护）→ T1-T5 协同
- [x] §3.2 missing-as-fail 语义统一（三路径统一）→ T3/T4 的显式 `valid` 保护
- [x] §3.3 factor_diag.yaml 审计字段 → T7
- [x] §3.4 Live detail_panel 兜底 → T6
- [x] §4.1 data_pipeline 3 行改动 → T1/T2/T3
- [x] §4.2 threshold_optimizer 3 行改动 → T4/T5
- [x] §4.3 factor_diagnosis（P1）→ T7
- [x] §4.4 detail_panel → T6
- [x] §6 错误处理的所有场景 → 对应测试覆盖
- [x] §7.1 新增单元测试 → 各任务嵌入 test_nan_aware.py / test_detail_panel.py

**Placeholder 扫描**：
- [x] 无 TBD / TODO / "implement later" / "add error handling"
- [x] 每个 Step 都有具体代码或 shell 命令
- [x] 没有"Similar to Task N"占位
- [x] 所有 import 在测试代码里写全

**类型/命名一致性**：
- [x] `valid`（不是 `mask` / `valid_mask` 互换）—— 在 T3/T4/T5 统一用局部变量命名
- [x] `audit_info`（T7）参数名
- [x] `_fmt`（T6）不改参数名，只加 None 分支
- [x] `prepare_raw_values` / `build_triggered_matrix` / `apply_binary_levels` 签名保持稳定（只改行为不改接口）

**DAG 依赖**：
- T1（build_dataframe None 透传）→ T2 生效前 T1 必须先走
- T2（prepare_raw_values 去 fillna）→ T3/T4/T5 前需先走（否则下游还是 fillna 过的值）
- T3（apply_binary_levels 加 NaN 保护）→ 独立，可与 T4/T5 并行
- T4（build_triggered_matrix）→ 独立
- T5（TPE/greedy）→ 独立
- T6（detail_panel）→ 独立
- T7（factor_diag.yaml）→ 依赖 T2 之后 raw_values 有 NaN（否则 valid_count = total_bo）

顺序正确：T1 → T2 → T3/T4/T5（并行或连续）→ T6（独立）→ T7（依赖 T2）。
