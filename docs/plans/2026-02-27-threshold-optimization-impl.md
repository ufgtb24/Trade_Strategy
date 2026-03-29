# 组合模板阈值优化系统 — 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 `scripts/analysis/optimize_thresholds.py`，通过四阶段流水线搜索最优 bonus 因子阈值，产出高质量的 `bonus_filter.yaml`。

**Architecture:** 单一新脚本，四阶段流水线（逻辑排除 → 因子筛选 → 双引擎搜索 → 验证输出）。复用现有 `generate_templates()` 和 `build_yaml_output()` 做最终输出，内部用 bit-packed 向量化评估（1.1ms vs 原版 121ms）驱动 Optuna 3000 trials。

**Tech Stack:** Python 3.11+, pandas, numpy, optuna (新依赖), scipy, yaml

**Design doc:** `docs/plans/2026-02-27-threshold-optimization-design.md`

---

## 关键背景

- **CSV 数据**：`outputs/analysis/bonus_analysis_data.csv`，9810 行，含 11 个 `*_level` 列 + 原始特征列 + `label_10_40`
- **原版 generate_templates**：121ms/次（字符串拼接瓶颈），bit-packed 向量化版本 1.1ms/次
- **11 因子映射**：

| 显示名 | level 列 | 原始值列 | bk YAML key |
|--------|----------|---------|-------------|
| Height | `height_level` | `max_height` | `height_bonus` |
| PeakVol | `peak_vol_level` | `max_peak_volume` | `peak_volume_bonus` |
| Volume | `volume_level` | `volume_surge_ratio` | `volume_bonus` |
| DayStr | `day_str_level` | 衍生¹ | `breakout_day_strength_bonus` |
| Drought | `drought_level` | `days_since_last_breakout` | `drought_bonus` |
| Age | `age_level` | `oldest_age` | `age_bonus` |
| Streak | `streak_level` | `recent_breakout_count` | `streak_bonus` |
| PK-Mom | `pk_mom_level` | `pk_momentum` | `pk_momentum_bonus` |
| PBM | `pbm_level` | `momentum` | `pbm_bonus` |
| Tests | `test_level` | `test_count` | `test_bonus` |
| Overshoot | `overshoot_level` | 衍生² | `overshoot_penalty` — **排除** |

¹ `max(|intraday_change_pct|, |gap_up_pct|) / (annual_volatility / √252)`
² `gain_5d / (annual_volatility / √50.4)` — 前瞻偏差

- **binary trigger**：`generate_templates` 使用 `level > 0` 做二值化。因此 Optuna 每因子只需搜索 1 个阈值（即决定 triggered/not-triggered 的分界点）
- **项目约定**：不用 argparse，参数声明在 `main()` 开头；用 `uv run` 执行

---

### Task 1: 项目设置 + 脚本骨架

**Files:**
- Create: `scripts/analysis/optimize_thresholds.py`

**Step 1: 安装 optuna**

```bash
uv add optuna
```

Expected: `pyproject.toml` 更新，`uv.lock` 更新。

**Step 2: 验证 optuna 可用**

```bash
uv run python -c "import optuna; print(optuna.__version__)"
```

Expected: 打印版本号（如 `4.x.x`）

**Step 3: 创建脚本骨架**

Create `scripts/analysis/optimize_thresholds.py`:

```python
"""
组合模板阈值优化器

四阶段流水线：逻辑排除 → Bootstrap 因子筛选 → 双引擎搜索 → 验证输出
通过数据驱动搜索最优阈值，产出高质量 bonus_filter.yaml。

输入: outputs/analysis/bonus_analysis_data.csv + configs/params/all_bonus_bk.yaml
输出: configs/params/bonus_filter.yaml
"""

import math
from collections import Counter
from pathlib import Path

import numpy as np
import optuna
import pandas as pd
import yaml
from scipy.stats import bootstrap

from _analysis_functions import BONUS_COLS, BONUS_DISPLAY, LABEL_COL
from bonus_combination_analysis import get_level
from optimize_bonus_filter import build_yaml_output, print_summary

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# 常量：因子配置
# ---------------------------------------------------------------------------

# 排除的因子（前瞻偏差）
EXCLUDED_FACTORS = {'overshoot_level'}

# 活跃因子配置：显示名 → (level_col, raw_col_or_None, bk_yaml_key)
FACTOR_CONFIG = {
    'Height':  ('height_level',   'max_height',               'height_bonus'),
    'PeakVol': ('peak_vol_level', 'max_peak_volume',          'peak_volume_bonus'),
    'Volume':  ('volume_level',   'volume_surge_ratio',       'volume_bonus'),
    'DayStr':  ('day_str_level',  None,                       'breakout_day_strength_bonus'),
    'Drought': ('drought_level',  'days_since_last_breakout', 'drought_bonus'),
    'Age':     ('age_level',      'oldest_age',               'age_bonus'),
    'Streak':  ('streak_level',   'recent_breakout_count',    'streak_bonus'),
    'PK-Mom':  ('pk_mom_level',   'pk_momentum',              'pk_momentum_bonus'),
    'PBM':     ('pbm_level',      'momentum',                 'pbm_bonus'),
    'Tests':   ('test_level',     'test_count',               'test_bonus'),
}

# BONUS_COLS 去掉排除因子后的列表（保持原始顺序）
ACTIVE_LEVEL_COLS = [c for c in BONUS_COLS if c not in EXCLUDED_FACTORS]


def main():
    # === 配置 ===
    input_csv = str(PROJECT_ROOT / "outputs/analysis/bonus_analysis_data.csv")
    bk_yaml = str(PROJECT_ROOT / "configs/params/all_bonus_bk.yaml")
    output_yaml = str(PROJECT_ROOT / "configs/params/bonus_filter.yaml")

    # Stage 1
    top_k_templates = 30
    min_count_screening = 10

    # Stage 2
    temporal_split = 0.7

    # Stage 3
    beam_width = 3
    n_trials = 3000
    min_count_final = 10
    trigger_rate_lo = 0.03
    trigger_rate_hi = 0.50
    top_k_objective = 5

    # Stage 4
    bootstrap_n = 1000

    # === 加载数据 ===
    print(f"Loading: {input_csv}")
    df = pd.read_csv(input_csv)
    df = df.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    print(f"  Rows: {len(df)}")

    # === Stage 0: 逻辑排除 ===
    print("\n=== Stage 0: Logic Exclusion ===")
    print(f"  Excluded: {EXCLUDED_FACTORS}")
    print(f"  Active factors: {len(FACTOR_CONFIG)}")

    # TODO: Stage 1-4 in subsequent tasks

    print("\nDone.")


if __name__ == '__main__':
    main()
```

**Step 4: 验证骨架运行**

```bash
uv run python scripts/analysis/optimize_thresholds.py
```

Expected:
```
Loading: .../bonus_analysis_data.csv
  Rows: 9810

=== Stage 0: Logic Exclusion ===
  Excluded: {'overshoot_level'}
  Active factors: 10

Done.
```

**Step 5: Commit**

```bash
git add scripts/analysis/optimize_thresholds.py pyproject.toml uv.lock
git commit -m "feat: 阈值优化器骨架 + 安装 optuna 依赖"
```

---

### Task 2: 核心工具函数 — 原始值预计算 + 向量化评估

**Files:**
- Modify: `scripts/analysis/optimize_thresholds.py`

这些是后续所有 Stage 依赖的基础工具。

**Step 1: 实现 `prepare_raw_values()`**

在 `ACTIVE_LEVEL_COLS` 定义之后、`main()` 之前添加：

```python
# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def prepare_raw_values(df):
    """
    从 DataFrame 预提取各因子的原始数值（numpy 数组）。
    衍生因子（DayStr）在此处计算。预计算一次，后续搜索复用。

    Args:
        df: bonus_analysis_data DataFrame

    Returns:
        dict[str, np.ndarray]: {显示名: 原始值数组}
    """
    raw = {}
    for name, (level_col, raw_col, _) in FACTOR_CONFIG.items():
        if raw_col is not None:
            raw[name] = df[raw_col].fillna(0).values.astype(np.float64)
        elif name == 'DayStr':
            annual_vol = df['annual_volatility'].fillna(0).values
            daily_vol = annual_vol / np.sqrt(252)
            # 避免除零
            safe_daily_vol = np.where(daily_vol > 0, daily_vol, np.inf)
            idr = np.abs(df['intraday_change_pct'].fillna(0).values) / safe_daily_vol
            gap = np.abs(df['gap_up_pct'].fillna(0).values) / safe_daily_vol
            raw[name] = np.maximum(idr, gap)
    return raw
```

**Step 2: 实现 `build_triggered_matrix()`**

紧接着添加：

```python
def build_triggered_matrix(raw_values, thresholds, factor_order):
    """
    根据阈值构建二值触发矩阵。value >= threshold → triggered=1。

    Args:
        raw_values: prepare_raw_values() 的输出
        thresholds: {显示名: threshold_value}，每因子一个阈值
        factor_order: 因子顺序列表（决定 bit 位置）

    Returns:
        (n_samples, n_factors) int64 矩阵
    """
    n = len(next(iter(raw_values.values())))
    n_factors = len(factor_order)
    triggered = np.zeros((n, n_factors), dtype=np.int64)
    for i, name in enumerate(factor_order):
        if name in thresholds and name in raw_values:
            triggered[:, i] = (raw_values[name] >= thresholds[name]).astype(np.int64)
    return triggered
```

**Step 3: 实现 `fast_evaluate()`**

```python
def fast_evaluate(triggered, labels, min_count=10, top_k=5):
    """
    Bit-packed 向量化模板评估（~1ms）。

    将 triggered 矩阵编码为整数 key（第 i 位 = 第 i 个因子），
    按 key 分组计算 count/median，返回目标值。

    Args:
        triggered: (n_samples, n_factors) 二值矩阵
        labels: (n_samples,) label 数组
        min_count: 最小样本量
        top_k: 取 top-K median 计算平均值

    Returns:
        (top_k_median, viable_count, n_templates)
        - top_k_median: top-K 模板 median 的均值（优化目标 1）
        - viable_count: count >= 2*min_count 的模板数（优化目标 2）
        - n_templates: 满足 min_count 的模板总数
    """
    n_factors = triggered.shape[1]
    powers = (1 << np.arange(n_factors)).astype(np.int64)
    combo_keys = triggered @ powers

    combo_df = pd.DataFrame({'key': combo_keys, 'label': labels})
    stats = combo_df.groupby('key')['label'].agg(['count', 'median'])
    stats = stats[stats.index > 0]  # 排除 key=0（无因子触发）
    stats = stats[stats['count'] >= min_count]
    stats = stats.sort_values('median', ascending=False)

    n_templates = len(stats)
    if n_templates < top_k:
        return 0.0, 0, n_templates

    top_k_median = float(stats['median'].iloc[:top_k].mean())
    viable_count = int((stats['count'] >= 2 * min_count).sum())

    return top_k_median, viable_count, n_templates
```

**Step 4: 实现 `decode_templates()`**

```python
def decode_templates(triggered, labels, factor_names, min_count=10):
    """
    从 triggered 矩阵解码完整模板列表（含名称）。
    仅在最终输出时调用（比 fast_evaluate 慢但含完整信息）。

    Args:
        triggered: (n_samples, n_factors) 二值矩阵
        labels: (n_samples,) label 数组
        factor_names: 因子显示名列表（与 triggered 列对齐）
        min_count: 最小样本量

    Returns:
        list[dict]: 与 optimize_bonus_filter.generate_templates() 兼容的格式
    """
    n_factors = triggered.shape[1]
    powers = (1 << np.arange(n_factors)).astype(np.int64)
    combo_keys = triggered @ powers

    combo_df = pd.DataFrame({'key': combo_keys, 'label': labels})
    stats = combo_df.groupby('key').agg(
        count=('label', 'count'),
        median=('label', 'median'),
        q25=('label', lambda x: x.quantile(0.25)),
    ).reset_index()

    stats = stats[stats['key'] > 0]
    stats = stats[stats['count'] >= min_count]
    stats = stats.sort_values('median', ascending=False).reset_index(drop=True)

    templates = []
    for _, row in stats.iterrows():
        key = int(row['key'])
        factors = [factor_names[i] for i in range(n_factors) if key & (1 << i)]
        templates.append({
            'name': '+'.join(factors),
            'factors': factors,
            'count': int(row['count']),
            'median': round(float(row['median']), 4),
            'q25': round(float(row['q25']), 4),
        })

    return templates
```

**Step 5: 验证工具函数**

在 `main()` 的 Stage 0 打印之后，TODO 注释之前添加验证代码（后续 task 会替换为正式调用）：

```python
    # --- 验证工具函数 ---
    raw_values = prepare_raw_values(df)
    print(f"\n  Raw values prepared: {list(raw_values.keys())}")

    # 用 bk 阈值做简单测试
    test_thresholds = {'Height': 0.2, 'Volume': 5.0, 'DayStr': 1.5}
    test_order = ['Height', 'Volume', 'DayStr']
    test_triggered = build_triggered_matrix(raw_values, test_thresholds, test_order)
    test_labels = df[LABEL_COL].values
    top_k_med, viable, n_templ = fast_evaluate(test_triggered, test_labels, min_count=10, top_k=5)
    print(f"  Quick test (3 factors): top5_median={top_k_med:.4f}, viable={viable}, templates={n_templ}")

    templates = decode_templates(test_triggered, test_labels, test_order, min_count=10)
    print(f"  Decoded {len(templates)} templates, top-3:")
    for t in templates[:3]:
        print(f"    {t['name']:<30s} count={t['count']:4d}  median={t['median']:.4f}")
```

**Step 6: 运行验证**

```bash
uv run python scripts/analysis/optimize_thresholds.py
```

Expected: 打印原始值列表、3 因子快速测试结果（top5_median > 0, 数个模板），以及 decode 后的模板名。

**Step 7: Commit**

```bash
git add scripts/analysis/optimize_thresholds.py
git commit -m "feat: 阈值优化器核心工具函数（prepare_raw_values, fast_evaluate, decode_templates）"
```

---

### Task 3: Stage 1 — Bootstrap 因子筛选

**Files:**
- Modify: `scripts/analysis/optimize_thresholds.py`

**Step 1: 实现 `load_bk_thresholds()`**

在工具函数区域末尾添加：

```python
# ---------------------------------------------------------------------------
# Stage 1: Bootstrap 因子筛选
# ---------------------------------------------------------------------------

def load_bk_thresholds(yaml_path):
    """
    从 all_bonus_bk.yaml 读取各因子的第一个阈值（二值触发用）。

    Returns:
        dict[str, float]: {显示名: 第一个阈值}
    """
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)
    qs = cfg['quality_scorer']

    thresholds = {}
    for name, (_, _, yaml_key) in FACTOR_CONFIG.items():
        entry = qs.get(yaml_key, {})
        t_list = entry.get('thresholds', [])
        if t_list:
            thresholds[name] = float(t_list[0])  # 第一个阈值 = 二值触发点
    return thresholds
```

**Step 2: 实现 `compute_q70_thresholds()`**

```python
def compute_q70_thresholds(raw_values):
    """
    对每个因子原始值取 q70 分位数作为单一阈值。
    q70 意味着 top-30% 的样本被触发。

    Args:
        raw_values: prepare_raw_values() 的输出

    Returns:
        dict[str, float]: {显示名: q70 阈值}
    """
    thresholds = {}
    for name, values in raw_values.items():
        # 过滤掉 0 值（通常是缺失/无效）
        valid = values[values > 0]
        if len(valid) > 0:
            thresholds[name] = float(np.quantile(valid, 0.70))
        else:
            thresholds[name] = 0.0
    return thresholds
```

**Step 3: 实现 `compute_factor_lift()`**

```python
def compute_factor_lift(templates, top_k=30):
    """
    从模板列表计算因子加权频率和 lift。

    加权规则：rank 1-10 权重 3，rank 11-20 权重 2，rank 21-30 权重 1。
    lift = top_k 加权频率 / 全局频率。lift > 1 表示因子在高表现模板中富集。

    Args:
        templates: generate_templates 或 decode_templates 输出
        top_k: 取 top-K 模板分析

    Returns:
        dict[str, float]: {因子名: lift}
    """
    if not templates:
        return {}

    # 全局因子频率
    all_count = Counter()
    for t in templates:
        for f in t['factors']:
            all_count[f] += 1
    n_all = len(templates)

    # Top-K 加权频率
    top_templates = templates[:top_k]
    weighted_count = Counter()
    total_weight = 0
    for rank, t in enumerate(top_templates):
        weight = 3 if rank < 10 else (2 if rank < 20 else 1)
        total_weight += weight
        for f in t['factors']:
            weighted_count[f] += weight

    # 计算 lift
    lift = {}
    all_factors = set(all_count.keys()) | set(weighted_count.keys())
    for f in all_factors:
        top_freq = weighted_count.get(f, 0) / total_weight if total_weight > 0 else 0
        all_freq = all_count.get(f, 0) / n_all if n_all > 0 else 0
        lift[f] = top_freq / all_freq if all_freq > 0 else 0.0
    return lift
```

**Step 4: 实现 `stage1_factor_screening()`**

```python
def stage1_factor_screening(df, raw_values, bk_thresholds, q70_thresholds,
                            factor_order, min_count=10, top_k=30):
    """
    Bootstrap 因子筛选：用两套阈值各跑一次模板挖掘，
    提取高表现模板中的高频因子。

    Args:
        df: DataFrame
        raw_values: 预计算原始值
        bk_thresholds: bk 阈值 {显示名: float}
        q70_thresholds: q70 阈值 {显示名: float}
        factor_order: 因子顺序列表
        min_count: 最小样本量
        top_k: 取 top-K 模板

    Returns:
        (active_factors, lift_report)
        - active_factors: lift > 1.0 的因子列表
        - lift_report: {因子: {bk_lift, q70_lift, avg_lift}} 用于打印
    """
    labels = df[LABEL_COL].values
    lift_all = {}

    for tag, thresholds in [('bk', bk_thresholds), ('q70', q70_thresholds)]:
        triggered = build_triggered_matrix(raw_values, thresholds, factor_order)
        templates = decode_templates(triggered, labels, factor_order, min_count)
        lift = compute_factor_lift(templates, top_k)
        for f, v in lift.items():
            lift_all.setdefault(f, {})[tag] = v

    # 汇总：取两套 lift 的平均值
    report = {}
    for f, lifts in lift_all.items():
        bk_l = lifts.get('bk', 0)
        q70_l = lifts.get('q70', 0)
        report[f] = {'bk_lift': bk_l, 'q70_lift': q70_l, 'avg_lift': (bk_l + q70_l) / 2}

    # 筛选：avg_lift > 1.0
    active = [f for f, r in report.items() if r['avg_lift'] > 1.0]
    # 按 avg_lift 降序排序
    active.sort(key=lambda f: report[f]['avg_lift'], reverse=True)

    return active, report
```

**Step 5: 在 main() 中集成 Stage 1**

删除 Task 2 的验证代码块（`# --- 验证工具函数 ---` 到 `# TODO` 之间），替换为：

```python
    # === 预计算 ===
    raw_values = prepare_raw_values(df)
    factor_order = [name for name in FACTOR_CONFIG.keys()]
    labels = df[LABEL_COL].values

    # === Stage 1: Bootstrap 因子筛选 ===
    print("\n=== Stage 1: Bootstrap Factor Screening ===")
    bk_thresholds = load_bk_thresholds(bk_yaml)
    q70_thresholds = compute_q70_thresholds(raw_values)

    print(f"  bk thresholds:  { {k: round(v, 3) for k, v in bk_thresholds.items()} }")
    print(f"  q70 thresholds: { {k: round(v, 3) for k, v in q70_thresholds.items()} }")

    active_factors, lift_report = stage1_factor_screening(
        df, raw_values, bk_thresholds, q70_thresholds,
        factor_order, min_count_screening, top_k_templates
    )

    print(f"\n  Factor lift report:")
    print(f"  {'Factor':<10s} {'bk_lift':>8s} {'q70_lift':>9s} {'avg_lift':>9s} {'Active':>7s}")
    for name in factor_order:
        r = lift_report.get(name, {'bk_lift': 0, 'q70_lift': 0, 'avg_lift': 0})
        is_active = '  ✓' if name in active_factors else ''
        print(f"  {name:<10s} {r['bk_lift']:>8.3f} {r['q70_lift']:>9.3f} {r['avg_lift']:>9.3f} {is_active:>7s}")

    print(f"\n  Active factors ({len(active_factors)}): {active_factors}")

    # TODO: Stage 2-4
```

**Step 6: 运行验证**

```bash
uv run python scripts/analysis/optimize_thresholds.py
```

Expected: 打印 bk 和 q70 两套阈值，以及每个因子的 lift 值表格。Height 应该有最高 lift，Tests/PBM 可能 lift < 1。活跃因子列表约 5-8 个。

**Step 7: Commit**

```bash
git add scripts/analysis/optimize_thresholds.py
git commit -m "feat: Stage 1 Bootstrap 因子筛选（双阈值 lift 分析）"
```

---

### Task 4: Stage 2 — 时序验证

**Files:**
- Modify: `scripts/analysis/optimize_thresholds.py`

**Step 1: 实现 `stage2_temporal_validation()`**

在 Stage 1 函数之后添加：

```python
# ---------------------------------------------------------------------------
# Stage 2: 时序验证
# ---------------------------------------------------------------------------

def stage2_temporal_validation(df, raw_values, bk_thresholds, q70_thresholds,
                               factor_order, temporal_split=0.7,
                               min_count=10, top_k=30):
    """
    时序验证：按日期将数据分为前 70% / 后 30%，
    分别跑 Stage 1 因子筛选，取交集得到稳定因子。

    Args:
        df: 完整 DataFrame
        raw_values: 预计算原始值（完整数据集）
        bk_thresholds, q70_thresholds: 两套阈值
        factor_order: 因子顺序
        temporal_split: 训练集占比
        min_count, top_k: 筛选参数

    Returns:
        (stable_factors, diagnostics)
        - stable_factors: 两个窗口中 lift 均 > 1.0 的因子
        - diagnostics: {train_active, test_active, train_lift, test_lift}
    """
    # 按日期排序
    df_sorted = df.sort_values('date').reset_index(drop=True)
    split_idx = int(len(df_sorted) * temporal_split)

    results = {}
    for tag, start, end in [('train', 0, split_idx), ('test', split_idx, len(df_sorted))]:
        idx = df_sorted.index[start:end]
        sub_df = df_sorted.iloc[start:end]

        # 对子集重新准备 raw_values
        sub_raw = {}
        for name, values in raw_values.items():
            # raw_values 的顺序与 df 原始索引对齐
            # df_sorted 重排后需要用 df_sorted 的原始索引取值
            original_indices = df_sorted.iloc[start:end].index
            # 但由于 df 已经 reset_index，原始索引就是行号
            sub_raw[name] = prepare_raw_values(sub_df)[name]

        sub_labels = sub_df[LABEL_COL].values

        active, lift_report = stage1_factor_screening(
            sub_df, sub_raw, bk_thresholds, q70_thresholds,
            factor_order, min_count, top_k
        )
        results[tag] = {'active': set(active), 'lift': lift_report, 'n_samples': len(sub_df)}

    # 取交集
    stable = results['train']['active'] & results['test']['active']
    # 按训练集 avg_lift 排序
    stable_list = sorted(stable, key=lambda f: results['train']['lift'].get(f, {}).get('avg_lift', 0), reverse=True)

    diagnostics = {
        'train_n': results['train']['n_samples'],
        'test_n': results['test']['n_samples'],
        'train_active': sorted(results['train']['active']),
        'test_active': sorted(results['test']['active']),
        'train_only': sorted(results['train']['active'] - results['test']['active']),
        'test_only': sorted(results['test']['active'] - results['train']['active']),
    }

    return stable_list, diagnostics
```

**Step 2: 在 main() 中集成 Stage 2**

替换 `# TODO: Stage 2-4` 为：

```python
    # === Stage 2: 时序验证 ===
    print("\n=== Stage 2: Temporal Validation ===")
    stable_factors, diag = stage2_temporal_validation(
        df, raw_values, bk_thresholds, q70_thresholds,
        factor_order, temporal_split, min_count_screening, top_k_templates
    )

    print(f"  Train samples: {diag['train_n']}, Test samples: {diag['test_n']}")
    print(f"  Train active: {diag['train_active']}")
    print(f"  Test active:  {diag['test_active']}")
    if diag['train_only']:
        print(f"  Train only (dropped): {diag['train_only']}")
    if diag['test_only']:
        print(f"  Test only (dropped):  {diag['test_only']}")
    print(f"\n  Stable factors ({len(stable_factors)}): {stable_factors}")

    if len(stable_factors) < 3:
        print("  WARNING: < 3 stable factors. Falling back to Stage 1 active factors.")
        stable_factors = active_factors[:8]  # 降级使用 Stage 1 结果

    # TODO: Stage 3-4
```

**Step 3: 运行验证**

```bash
uv run python scripts/analysis/optimize_thresholds.py
```

Expected: 打印训练/测试集样本数（约 6867 / 2943），各自的活跃因子，以及交集（稳定因子）。Height 应在两个窗口中都出现。

**Step 4: Commit**

```bash
git add scripts/analysis/optimize_thresholds.py
git commit -m "feat: Stage 2 时序验证（70/30 分割，因子稳定性检查）"
```

---

### Task 5: Stage 3a — 贪心 Beam Search

**Files:**
- Modify: `scripts/analysis/optimize_thresholds.py`

**Step 1: 实现 `stage3a_greedy_beam_search()`**

在 Stage 2 函数之后添加：

```python
# ---------------------------------------------------------------------------
# Stage 3a: 贪心 Beam Search
# ---------------------------------------------------------------------------

def stage3a_greedy_beam_search(raw_values, labels, active_factors,
                               beam_width=3, min_samples=50,
                               n_candidates=20):
    """
    贪心 beam search：逐因子收缩子集，寻找高 median 路径。

    每步：
    1. 对所有未使用的活跃因子 × n_candidates 个阈值候选
    2. 计算子集 median
    3. 保留 top beam_width 路径
    4. 重复直到无法改善或子集太小

    Args:
        raw_values: 预计算原始值
        labels: label 数组
        active_factors: 活跃因子列表
        beam_width: beam 宽度
        min_samples: 子集最小样本量
        n_candidates: 每因子候选阈值数

    Returns:
        list[dict]: top beam_width 条路径，每条含：
            - thresholds: {因子: 阈值}
            - factors_used: [因子列表]
            - median: 最终子集 median
            - count: 最终子集大小
    """
    n_total = len(labels)

    # 预计算每因子的候选阈值（分位数）
    candidates = {}
    for name in active_factors:
        raw = raw_values[name]
        valid = raw[raw > 0]
        if len(valid) < n_candidates:
            candidates[name] = np.unique(valid)
        else:
            percentiles = np.linspace(10, 90, n_candidates)
            candidates[name] = np.unique(np.percentile(valid, percentiles))

    # 初始 beam: 一条空路径
    beam = [{'thresholds': {}, 'mask': np.ones(n_total, dtype=bool),
             'median': float(np.median(labels)), 'count': n_total}]

    for depth in range(len(active_factors)):
        new_beam = []

        for path in beam:
            used = set(path['thresholds'].keys())
            current_mask = path['mask']
            current_labels = labels[current_mask]

            best_for_path = []

            for factor in active_factors:
                if factor in used:
                    continue
                raw = raw_values[factor]

                for threshold in candidates.get(factor, []):
                    # 在当前子集上应用新筛选
                    sub_mask = current_mask & (raw >= threshold)
                    n_sub = sub_mask.sum()
                    if n_sub < min_samples:
                        continue

                    sub_median = float(np.median(labels[sub_mask]))
                    best_for_path.append({
                        'factor': factor,
                        'threshold': float(threshold),
                        'median': sub_median,
                        'count': int(n_sub),
                    })

            if not best_for_path:
                # 无法改善，保留当前路径
                new_beam.append(path)
                continue

            # 取 top beam_width 候选
            best_for_path.sort(key=lambda x: x['median'], reverse=True)
            for cand in best_for_path[:beam_width]:
                new_thresholds = {**path['thresholds'], cand['factor']: cand['threshold']}
                new_mask = current_mask & (raw_values[cand['factor']] >= cand['threshold'])
                new_beam.append({
                    'thresholds': new_thresholds,
                    'mask': new_mask,
                    'median': cand['median'],
                    'count': cand['count'],
                })

        # 去重 + 保留 top beam_width
        # 按 (median desc, count desc) 排序
        new_beam.sort(key=lambda x: (x['median'], x['count']), reverse=True)
        beam = new_beam[:beam_width]

        # 打印进度
        print(f"    Depth {depth+1}: beam top median={beam[0]['median']:.4f} "
              f"(n={beam[0]['count']}, factors={list(beam[0]['thresholds'].keys())})")

        # 终止条件：所有路径都不能改善
        if all(len(p['thresholds']) <= depth for p in beam):
            break

    # 清理 mask（不需要序列化）
    results = []
    for p in beam:
        results.append({
            'thresholds': p['thresholds'],
            'factors_used': list(p['thresholds'].keys()),
            'median': p['median'],
            'count': p['count'],
        })

    return results
```

**Step 2: 在 main() 中集成 Stage 3a**

替换 `# TODO: Stage 3-4` 为：

```python
    # === Stage 3a: 贪心 Beam Search ===
    print("\n=== Stage 3a: Greedy Beam Search ===")
    greedy_results = stage3a_greedy_beam_search(
        raw_values, labels, stable_factors,
        beam_width=beam_width, min_samples=min_count_final * 5,
    )

    print(f"\n  Greedy results ({len(greedy_results)} paths):")
    for i, r in enumerate(greedy_results):
        print(f"    Path {i+1}: median={r['median']:.4f}  count={r['count']}  "
              f"factors={r['factors_used']}  thresholds={r['thresholds']}")

    # TODO: Stage 3b, 4
```

**Step 3: 运行验证**

```bash
uv run python scripts/analysis/optimize_thresholds.py
```

Expected: 每个 depth 打印最优 beam 的 median 和因子，最终输出 3 条路径。Height 应在大多数路径中出现，median 预期 > 0.25。

**Step 4: Commit**

```bash
git add scripts/analysis/optimize_thresholds.py
git commit -m "feat: Stage 3a 贪心 beam search（逐因子条件化搜索）"
```

---

### Task 6: Stage 3b — Optuna TPE 多目标搜索

**Files:**
- Modify: `scripts/analysis/optimize_thresholds.py`

**Step 1: 实现 `stage3b_optuna_search()`**

在 Stage 3a 函数之后添加：

```python
# ---------------------------------------------------------------------------
# Stage 3b: Optuna TPE 多目标搜索
# ---------------------------------------------------------------------------

def stage3b_optuna_search(raw_values, labels, active_factors, factor_order,
                          greedy_seeds, n_trials=3000, min_count=10,
                          top_k=5, trigger_rate_lo=0.03, trigger_rate_hi=0.50):
    """
    Optuna TPE 多目标搜索，嵌套 bit-packed generate_templates。
    以贪心结果做 warm start。

    Args:
        raw_values: 预计算原始值
        labels: label 数组
        active_factors: 活跃因子列表（搜索空间）
        factor_order: 完整因子顺序（用于 bit-pack 位置）
        greedy_seeds: stage3a 的输出（warm start 用）
        n_trials: 搜索试验数
        min_count: generate_templates 最小样本量
        top_k: 目标函数 top-K
        trigger_rate_lo, trigger_rate_hi: 触发率约束

    Returns:
        optuna.Study
    """
    n_samples = len(labels)

    # 预计算搜索边界：每因子 raw 值的 [q5, q95]
    bounds = {}
    for name in active_factors:
        raw = raw_values[name]
        valid = raw[raw > 0]
        if len(valid) > 0:
            bounds[name] = (float(np.quantile(valid, 0.05)),
                            float(np.quantile(valid, 0.95)))
        else:
            bounds[name] = (0.0, 1.0)

    # factor_order 中活跃因子的索引（用于构建 triggered 矩阵）
    active_indices = [factor_order.index(f) for f in active_factors if f in factor_order]
    # 只用活跃因子的子集
    sub_factor_order = [factor_order[i] for i in active_indices]

    def objective(trial):
        # 采样每因子阈值
        thresholds = {}
        for name in active_factors:
            lo, hi = bounds[name]
            if lo >= hi:
                thresholds[name] = lo
            else:
                thresholds[name] = trial.suggest_float(name, lo, hi)

        # 构建 triggered 矩阵（只含活跃因子）
        triggered = build_triggered_matrix(raw_values, thresholds, sub_factor_order)

        # 触发率约束
        rates = triggered.mean(axis=0)
        for i, name in enumerate(sub_factor_order):
            if rates[i] > trigger_rate_hi or rates[i] < trigger_rate_lo:
                return 0.0, 0

        # 评估
        top_k_median, viable_count, n_templates = fast_evaluate(
            triggered, labels, min_count, top_k
        )
        return top_k_median, viable_count

    # 创建多目标 study
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        directions=["maximize", "maximize"],
        sampler=optuna.samplers.TPESampler(seed=42),
    )

    # Warm start: 注入贪心解
    for seed in greedy_seeds:
        params = {}
        for name in active_factors:
            if name in seed['thresholds']:
                params[name] = seed['thresholds'][name]
            else:
                # 未在贪心路径中使用的因子，用 q50 作为默认
                raw = raw_values[name]
                valid = raw[raw > 0]
                params[name] = float(np.median(valid)) if len(valid) > 0 else 0.0
        study.enqueue_trial(params)

    # 运行优化
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    return study
```

**Step 2: 在 main() 中集成 Stage 3b**

替换 `# TODO: Stage 3b, 4` 为：

```python
    # === Stage 3b: Optuna TPE 多目标搜索 ===
    print(f"\n=== Stage 3b: Optuna TPE Multi-Objective ({n_trials} trials) ===")
    study = stage3b_optuna_search(
        raw_values, labels, stable_factors, factor_order,
        greedy_seeds=greedy_results,
        n_trials=n_trials, min_count=min_count_final,
        top_k=top_k_objective,
        trigger_rate_lo=trigger_rate_lo, trigger_rate_hi=trigger_rate_hi,
    )

    # Pareto 前沿
    pareto_trials = study.best_trials
    print(f"\n  Pareto front: {len(pareto_trials)} solutions")
    # 按 top_k_median 降序排列
    pareto_sorted = sorted(pareto_trials, key=lambda t: t.values[0], reverse=True)
    print(f"  {'#':>3s} {'top5_median':>12s} {'viable_count':>13s}")
    for i, t in enumerate(pareto_sorted[:10]):
        print(f"  {i+1:3d} {t.values[0]:12.4f} {int(t.values[1]):13d}")

    # TODO: Stage 4
```

**Step 3: 运行验证**

```bash
uv run python scripts/analysis/optimize_thresholds.py
```

Expected: Optuna 进度条，3000 trials 完成后打印 Pareto 前沿。top5_median 最优解应 > 0.30，viable_count 最优解应 > 30。预计运行时间 ~5-15 秒。

**Step 4: Commit**

```bash
git add scripts/analysis/optimize_thresholds.py
git commit -m "feat: Stage 3b Optuna TPE 多目标搜索（warm start + 触发率约束）"
```

---

### Task 7: Stage 4 — 验证 + 输出

**Files:**
- Modify: `scripts/analysis/optimize_thresholds.py`

**Step 1: 实现 `select_best_trial()`**

在 Stage 3b 之后添加：

```python
# ---------------------------------------------------------------------------
# Stage 4: 验证 + 输出
# ---------------------------------------------------------------------------

def select_best_trial(study, raw_values, labels, factor_order, active_factors,
                      min_count=10, bootstrap_n=1000):
    """
    从 Pareto 前沿选择最佳解：优先 top5_median 最高，
    用 bootstrap 评估稳定性。

    Args:
        study: Optuna Study
        raw_values: 预计算原始值
        labels: label 数组
        factor_order: 因子顺序
        active_factors: 活跃因子
        min_count: 最小样本量
        bootstrap_n: bootstrap 重采样次数

    Returns:
        dict: {thresholds, top5_median, viable_count, stability_score, templates}
    """
    pareto = study.best_trials
    if not pareto:
        raise ValueError("No Pareto optimal trials found")

    # 按 top5_median 降序
    pareto_sorted = sorted(pareto, key=lambda t: t.values[0], reverse=True)

    # 只用活跃因子的子集
    sub_factor_order = [f for f in factor_order if f in active_factors]

    best = None
    best_score = -1

    for trial in pareto_sorted[:10]:  # 只评估 top-10
        thresholds = {name: trial.params[name] for name in active_factors
                      if name in trial.params}
        triggered = build_triggered_matrix(raw_values, thresholds, sub_factor_order)
        templates = decode_templates(triggered, labels, sub_factor_order, min_count)

        if len(templates) < 5:
            continue

        top5_medians = [t['median'] for t in templates[:5]]
        top5_avg = np.mean(top5_medians)

        # Bootstrap 稳定性：对 top-1 模板做 bootstrap
        top1 = templates[0]
        top1_key_factors = set(top1['factors'])
        # 找到属于 top-1 模板的样本
        n_factors = len(sub_factor_order)
        powers = (1 << np.arange(n_factors)).astype(np.int64)
        combo_keys = triggered @ powers
        target_key = sum(1 << sub_factor_order.index(f) for f in top1_key_factors)
        member_labels = labels[combo_keys == target_key]

        if len(member_labels) >= 20:
            # bootstrap 95% CI
            rng = np.random.default_rng(42)
            boot_medians = []
            for _ in range(bootstrap_n):
                sample = rng.choice(member_labels, size=len(member_labels), replace=True)
                boot_medians.append(float(np.median(sample)))
            ci_lo = np.percentile(boot_medians, 2.5)
            ci_hi = np.percentile(boot_medians, 97.5)
            ci_width = ci_hi - ci_lo
            stability = 1 - ci_width / top5_avg if top5_avg > 0 else 0
        else:
            stability = 0.0
            ci_lo = ci_hi = 0.0

        # 综合评分：top5_median × stability
        score = top5_avg * max(stability, 0.1)

        if score > best_score:
            best_score = score
            best = {
                'thresholds': thresholds,
                'top5_median': top5_avg,
                'viable_count': int(trial.values[1]),
                'stability_score': stability,
                'ci_95': (round(ci_lo, 4), round(ci_hi, 4)),
                'templates': templates,
                'n_templates': len(templates),
            }

    return best
```

**Step 2: 在 main() 中集成 Stage 4 + 最终输出**

替换 `# TODO: Stage 4` 为：

```python
    # === Stage 4: 验证 + 输出 ===
    print(f"\n=== Stage 4: Validation & Output ===")
    best = select_best_trial(
        study, raw_values, labels, factor_order, stable_factors,
        min_count=min_count_final, bootstrap_n=bootstrap_n,
    )

    print(f"  Best solution:")
    print(f"    Top-5 avg median: {best['top5_median']:.4f}")
    print(f"    Viable count:     {best['viable_count']}")
    print(f"    Stability score:  {best['stability_score']:.3f}")
    print(f"    95% CI:           {best['ci_95']}")
    print(f"    Templates:        {best['n_templates']}")
    print(f"    Thresholds:")
    for name, t in best['thresholds'].items():
        rate = (raw_values[name] >= t).mean()
        print(f"      {name:<10s}: {t:.4f}  (trigger rate: {rate:.1%})")

    # --- 输出 bonus_filter.yaml ---
    templates = best['templates']

    # 构建 YAML（复用 optimize_bonus_filter 的格式）
    yaml_data = build_yaml_output(templates, df, input_csv, min_count_final)

    # 在 _meta 中追加优化信息
    yaml_data['_meta']['generator'] = 'scripts/analysis/optimize_thresholds.py'
    yaml_data['_meta']['optimization'] = {
        'method': 'greedy_beam_search + optuna_tpe',
        'n_trials': n_trials,
        'active_factors': stable_factors,
        'thresholds': {k: round(v, 4) for k, v in best['thresholds'].items()},
        'top5_median': round(best['top5_median'], 4),
        'stability_score': round(best['stability_score'], 3),
    }

    # 写 YAML
    from optimize_bonus_filter import InlineListDumper
    Path(output_yaml).parent.mkdir(parents=True, exist_ok=True)
    with open(output_yaml, 'w') as f:
        f.write("# configs/params/bonus_filter.yaml\n")
        f.write("# 由 scripts/analysis/optimize_thresholds.py 自动生成（阈值优化版）\n\n")
        yaml.dump(yaml_data, f, Dumper=InlineListDumper,
                  default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"\n  Output: {output_yaml}")

    # 打印摘要
    print_summary(yaml_data)
```

**Step 3: 运行完整流水线**

```bash
uv run python scripts/analysis/optimize_thresholds.py
```

Expected:
- Stage 0-3 正常运行
- Stage 4 打印最优解的 thresholds、stability、CI
- 写入 `configs/params/bonus_filter.yaml`
- 摘要显示模板数约 60-150，Top-5 median 应 > 0.30

**Step 4: 验证输出文件**

```bash
uv run python -c "
import yaml
d = yaml.safe_load(open('configs/params/bonus_filter.yaml'))
meta = d['_meta']
print(f'Generator: {meta[\"generator\"]}')
print(f'Templates: {meta[\"total_templates\"]}')
print(f'Baseline: {meta[\"baseline_median\"]}')
opt = meta.get('optimization', {})
print(f'Method: {opt.get(\"method\", \"N/A\")}')
print(f'Active factors: {opt.get(\"active_factors\", [])}')
print(f'Optimized thresholds: {opt.get(\"thresholds\", {})}')
print(f'Top5 median: {opt.get(\"top5_median\", \"N/A\")}')
print(f'Stability: {opt.get(\"stability_score\", \"N/A\")}')
"
```

Expected: 输出优化元信息，generator 为 `optimize_thresholds.py`，包含 `optimization` 字段。

**Step 5: Commit**

```bash
git add scripts/analysis/optimize_thresholds.py configs/params/bonus_filter.yaml
git commit -m "feat: Stage 4 验证输出 + 完整阈值优化流水线"
```

---

### Task 8: 对比验证 + 清理

**Files:**
- Modify: `scripts/analysis/optimize_thresholds.py` (如需微调)

**Step 1: 对比 bk 原版基线**

```bash
uv run python -c "
import yaml

d = yaml.safe_load(open('configs/params/bonus_filter.yaml'))
templates = d['templates']
meta = d['_meta']

print(f'=== 优化后结果 ===')
print(f'Templates: {meta[\"total_templates\"]}')
print(f'Baseline median: {meta[\"baseline_median\"]}')
opt = meta.get('optimization', {})
print(f'Top5 median (优化): {opt.get(\"top5_median\", \"N/A\")}')
print(f'Active factors: {opt.get(\"active_factors\", [])}')
print()
print('Top-10 模板:')
for i, t in enumerate(templates[:10]):
    print(f'  {i+1:2d}. {t[\"name\"]:<50s} count={t[\"count\"]:4d}  median={t[\"median\"]:.4f}')

print()
print('=== 对比基线 ===')
print('bk 原始:  Top1 median=0.6037 (n=21),  128 templates')
print('auto_correct: Top1 median=0.3750,  171 templates')
"
```

Expected: 优化后 top5_median 在 0.35-0.50 范围，模板数 60-150。与 bk 对比，应在 median 和 count 之间找到更好的平衡。

**Step 2: 检查代码无调试残留**

确保 `main()` 中没有遗留的调试打印（Task 2 的验证代码应已删除）。确保所有 print 语句提供有用信息。

**Step 3: 最终 Commit**

```bash
git add scripts/analysis/optimize_thresholds.py
git commit -m "feat: 完成组合模板阈值优化系统（四阶段流水线）"
```

---

## 运行方式

```bash
# 完整运行
uv run python scripts/analysis/optimize_thresholds.py

# 预期运行时间: < 30 秒
# 预期输出: configs/params/bonus_filter.yaml (含优化元信息)
```

## 文件总结

| 操作 | 文件 |
|------|------|
| **新建** | `scripts/analysis/optimize_thresholds.py` |
| **修改** | `pyproject.toml`（添加 optuna 依赖） |
| **产出** | `configs/params/bonus_filter.yaml`（运行时生成） |
