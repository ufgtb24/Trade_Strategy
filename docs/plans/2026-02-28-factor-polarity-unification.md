# Factor Polarity Unification 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一因子触发方向（polarity）的数据源，让业务代码和数据挖掘代码都从 `all_bonus.yaml` 的 `mode` 字段读取方向，消除硬编码和中间层丢失。

**Architecture:** `all_bonus.yaml` 是触发方向的单一真相源。`param_loader.py` 透传 mode；`optimize_thresholds.py` 从 yaml 动态读取 mode 替代硬编码 `NEGATIVE_FACTORS`；新建方向诊断脚本 + skill 替代已废弃的 `auto_correct_bonus.py`。

**Tech Stack:** Python, PyYAML, scipy.stats.spearmanr

---

### Task 0: 准备 all_bonus.yaml（用 all_bonus_bk.yaml 覆盖，补 mode 字段）

**说明:** `all_bonus_bk.yaml` 的阈值是经过校准的有用数据，但缺少 mode 字段。将其内容复制到 `all_bonus.yaml`，为所有因子补上 `mode: gte`（初始全正向），后续用方向诊断 skill 来验证和纠正。

**Files:**
- Read: `configs/params/all_bonus_bk.yaml`
- Overwrite: `configs/params/all_bonus.yaml`
- Delete: `configs/params/all_bonus_bk.yaml`

**Step 1: 读取 all_bonus_bk.yaml 并添加 mode 字段后写入 all_bonus.yaml**

在 `quality_scorer` 下每个 bonus 配置块中添加 `mode: gte`：

```yaml
quality_scorer:
  age_bonus:
    enabled: true
    thresholds: [42, 63, 252]
    values: [1.02, 1.03, 1.05]
    mode: gte                      # ← 新增
  # ... 所有其他因子同理
  streak_bonus:
    enabled: true
    thresholds: [2, 4]
    values: [0.9, 0.75]
    mode: gte                      # ← 初始设为 gte，待 skill 诊断后纠正
  # ... 其余因子 ...
```

注意：`breakout_detector` 和 `feature_calculator` 部分保持不变。

**Step 2: 删除 all_bonus_bk.yaml**

```bash
git rm configs/params/all_bonus_bk.yaml
```

**Step 3: Commit**

```bash
git add configs/params/all_bonus.yaml
git commit -m "refactor: 合并 all_bonus_bk.yaml 到 all_bonus.yaml，统一添加 mode: gte"
```

---

### Task 1: param_loader.py 补齐 mode 透传

**说明:** `get_scorer_params()` 对 11 个因子系统性遗漏了 `mode` 字段，导致 UI 路径下 `BreakoutScorer` 全部回退到默认 `gte`。

**Files:**
- Modify: `BreakoutStrategy/UI/config/param_loader.py:293-387`

**Step 1: 为每个 bonus 的 validated dict 添加 mode 字段**

在 `get_scorer_params()` 方法中，找到每个 bonus 配置的 validated dict 构建处，添加一行 `'mode'`。共 11 处，模式完全相同：

```python
# 行 295-299: age_bonus
validated['age_bonus'] = {
    'enabled': age_bonus.get('enabled', True),
    'thresholds': age_bonus.get('thresholds', [21, 63, 252]),
    'values': age_bonus.get('values', [1.15, 1.30, 1.50]),
    'mode': age_bonus.get('mode', 'gte'),          # ← 新增
}

# 行 302-307: test_bonus
validated['test_bonus'] = {
    'enabled': test_bonus.get('enabled', True),
    'thresholds': test_bonus.get('thresholds', [2, 3, 4]),
    'values': test_bonus.get('values', [1.10, 1.25, 1.40]),
    'mode': test_bonus.get('mode', 'gte'),          # ← 新增
}

# 行 310-315: height_bonus
validated['height_bonus'] = {
    'enabled': height_bonus.get('enabled', True),
    'thresholds': height_bonus.get('thresholds', [0.10, 0.20]),
    'values': height_bonus.get('values', [1.15, 1.30]),
    'mode': height_bonus.get('mode', 'gte'),        # ← 新增
}

# 行 318-323: peak_volume_bonus
validated['peak_volume_bonus'] = {
    'enabled': peak_volume_bonus.get('enabled', True),
    'thresholds': peak_volume_bonus.get('thresholds', [2.0, 4.0]),
    'values': peak_volume_bonus.get('values', [1.15, 1.30]),
    'mode': peak_volume_bonus.get('mode', 'gte'),   # ← 新增
}

# 行 326-331: volume_bonus
validated['volume_bonus'] = {
    'enabled': volume_bonus.get('enabled', True),
    'thresholds': volume_bonus.get('thresholds', [1.5, 2.0]),
    'values': volume_bonus.get('values', [1.15, 1.30]),
    'mode': volume_bonus.get('mode', 'gte'),        # ← 新增
}

# 行 334-339: pbm_bonus
validated['pbm_bonus'] = {
    'enabled': pbm_bonus.get('enabled', True),
    'thresholds': pbm_bonus.get('thresholds', [0.70, 1.45]),
    'values': pbm_bonus.get('values', [1.15, 1.30]),
    'mode': pbm_bonus.get('mode', 'gte'),           # ← 新增
}

# 行 342-347: streak_bonus
validated['streak_bonus'] = {
    'enabled': streak_bonus.get('enabled', True),
    'thresholds': streak_bonus.get('thresholds', [2, 4]),
    'values': streak_bonus.get('values', [1.20, 1.40]),
    'mode': streak_bonus.get('mode', 'gte'),        # ← 新增
}

# 行 350-355: drought_bonus
validated['drought_bonus'] = {
    'enabled': drought_bonus.get('enabled', True),
    'thresholds': drought_bonus.get('thresholds', [60, 120]),
    'values': drought_bonus.get('values', [1.15, 1.30]),
    'mode': drought_bonus.get('mode', 'gte'),       # ← 新增
}

# 行 366-371: overshoot_penalty
validated['overshoot_penalty'] = {
    'enabled': overshoot.get('enabled', True),
    'thresholds': overshoot.get('thresholds', [3.0, 4.0]),
    'values': overshoot.get('values', [0.80, 0.60]),
    'mode': overshoot.get('mode', 'gte'),           # ← 新增
}

# 行 374-379: breakout_day_strength_bonus
validated['breakout_day_strength_bonus'] = {
    'enabled': bds_bonus.get('enabled', True),
    'thresholds': bds_bonus.get('thresholds', [1.5, 2.5]),
    'values': bds_bonus.get('values', [1.10, 1.20]),
    'mode': bds_bonus.get('mode', 'gte'),           # ← 新增
}

# 行 382-387: pk_momentum_bonus
validated['pk_momentum_bonus'] = {
    'enabled': pk_momentum_bonus.get('enabled', True),
    'thresholds': pk_momentum_bonus.get('thresholds', [1.5, 2.0]),
    'values': pk_momentum_bonus.get('values', [1.15, 1.25]),
    'mode': pk_momentum_bonus.get('mode', 'gte'),   # ← 新增
}
```

**Step 2: Commit**

```bash
git add BreakoutStrategy/UI/config/param_loader.py
git commit -m "fix: param_loader.get_scorer_params() 透传 mode 字段"
```

---

### Task 2: optimize_thresholds.py 从 yaml 读取 mode

**说明:** 删除硬编码 `NEGATIVE_FACTORS = {'Streak'}`，改为从 `all_bonus.yaml` 动态读取各因子的 mode。同时将 yaml 输入路径从 `all_bonus_bk.yaml` 改为 `all_bonus.yaml`（Task 0 已合并）。

**Files:**
- Modify: `scripts/analysis/optimize_thresholds.py:7,22,45-46,198-215,670-674,720`

**Step 1: 删除 NEGATIVE_FACTORS 常量，新增 load_factor_modes 函数**

删除行 45-46:
```python
# 删除这两行
# 反向因子：value 越低表现越好，使用 value <= threshold 触发
NEGATIVE_FACTORS = {'Streak'}
```

在 `load_bk_thresholds()` 函数之后新增：

```python
def load_factor_modes(yaml_path):
    """
    从 all_bonus.yaml 读取各因子的 mode，返回反向因子集合。
    mode='lte' 的因子视为反向因子（value <= threshold 触发）。

    Returns:
        frozenset[str]: 反向因子的显示名集合
    """
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)
    qs = cfg.get('quality_scorer', {})

    negative = set()
    for name, (_, _, yaml_key) in FACTOR_CONFIG.items():
        entry = qs.get(yaml_key, {})
        if entry.get('mode', 'gte') == 'lte':
            negative.add(name)
    return frozenset(negative)
```

**Step 2: 修改 main() 中的 yaml 路径和 negative_factors 来源**

将 `bk_yaml` 路径改为 `all_bonus.yaml`：

```python
# 原来:
bk_yaml = str(PROJECT_ROOT / "configs/params/all_bonus_bk.yaml")
# 改为:
bk_yaml = str(PROJECT_ROOT / "configs/params/all_bonus.yaml")
```

在 `main()` 的预计算区域（`raw_values` 之后），加载 mode：

```python
    # === 预计算 ===
    raw_values = prepare_raw_values(df)
    factor_order = list(FACTOR_CONFIG.keys())
    labels = df[LABEL_COL].values
    negative_factors = load_factor_modes(bk_yaml)  # ← 新增
    print(f"  Negative factors (lte mode): {sorted(negative_factors) if negative_factors else 'none'}")
```

**Step 3: 将所有 NEGATIVE_FACTORS 引用替换为 negative_factors 变量**

在 `main()` 中全局替换：`NEGATIVE_FACTORS` → `negative_factors`（共 6 处：Stage 1/2/3a/3b/4 调用 + 触发率打印）。

**Step 4: 更新文件头部注释中的输入路径**

```python
# 原来:
# 输入: outputs/analysis/bonus_analysis_data.csv + configs/params/all_bonus_bk.yaml
# 改为:
# 输入: outputs/analysis/bonus_analysis_data.csv + configs/params/all_bonus.yaml
```

**Step 5: Commit**

```bash
git add scripts/analysis/optimize_thresholds.py
git commit -m "refactor: optimize_thresholds 从 yaml 读取 factor mode，删除硬编码 NEGATIVE_FACTORS"
```

---

### Task 3: 创建方向诊断脚本 diagnose_factor_direction.py

**说明:** 独立脚本，基于 raw value Spearman 判断各因子方向，输出诊断报告并可选自动修正 `all_bonus.yaml`。替代 `auto_correct_bonus.py` 中的方向诊断功能。

**Files:**
- Create: `scripts/analysis/diagnose_factor_direction.py`
- Reference: `scripts/analysis/_analysis_functions.py` (BONUS_COLS, LABEL_COL)
- Reference: `scripts/analysis/bonus_distribution_analysis.py` (BonusConfig 定义)

**Step 1: 创建脚本**

```python
"""
因子方向诊断器

基于 raw value 与 label 的 Spearman 相关性判断因子触发方向。
不依赖 level/threshold 预设，直接在原始数据空间操作。

输入: outputs/analysis/bonus_analysis_data.csv + configs/params/all_bonus.yaml
输出: 诊断报告（stdout）+ 可选自动修正 all_bonus.yaml
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 因子显示名 → (raw_col_in_csv, yaml_key)
# raw_col=None 的衍生因子需在 prepare_raw 中计算
FACTOR_MAP = {
    'Height':  ('max_height',               'height_bonus'),
    'PeakVol': ('max_peak_volume',          'peak_volume_bonus'),
    'Volume':  ('volume_surge_ratio',       'volume_bonus'),
    'DayStr':  (None,                       'breakout_day_strength_bonus'),
    'Drought': ('days_since_last_breakout', 'drought_bonus'),
    'Age':     ('oldest_age',               'age_bonus'),
    'Streak':  ('recent_breakout_count',    'streak_bonus'),
    'PK-Mom':  ('pk_momentum',              'pk_momentum_bonus'),
    'PBM':     ('momentum',                 'pbm_bonus'),
    'Tests':   ('test_count',               'test_bonus'),
}

LABEL_COL = 'label_10_40'


def prepare_raw_values(df):
    """提取各因子的原始数值，衍生因子在此处计算。"""
    raw = {}
    for name, (raw_col, _) in FACTOR_MAP.items():
        if raw_col is not None:
            raw[name] = df[raw_col].fillna(0).values.astype(np.float64)
        elif name == 'DayStr':
            annual_vol = df['annual_volatility'].fillna(0).values
            daily_vol = annual_vol / np.sqrt(252)
            safe_daily_vol = np.where(daily_vol > 0, daily_vol, np.inf)
            idr = np.abs(df['intraday_change_pct'].fillna(0).values) / safe_daily_vol
            gap = np.abs(df['gap_up_pct'].fillna(0).values) / safe_daily_vol
            raw[name] = np.maximum(idr, gap)
    return raw


def diagnose_direction(raw_values, labels, weak_threshold=0.015):
    """
    基于 raw value Spearman 诊断各因子方向。

    Returns:
        dict[str, dict]: {因子名: {direction, mode, spearman_r, spearman_p}}
    """
    results = {}
    for name, raw in raw_values.items():
        valid_mask = ~np.isnan(raw) & ~np.isnan(labels)
        valid_raw = raw[valid_mask]
        valid_labels = labels[valid_mask]

        if len(valid_raw) <= 10:
            results[name] = {
                'direction': 'weak', 'mode': 'gte',
                'spearman_r': None, 'spearman_p': None,
            }
            continue

        r, p = spearmanr(valid_raw, valid_labels)

        if abs(r) < weak_threshold:
            direction, mode = 'weak', 'gte'
        elif r > 0:
            direction, mode = 'positive', 'gte'
        else:
            direction, mode = 'negative', 'lte'

        results[name] = {
            'direction': direction,
            'mode': mode,
            'spearman_r': round(float(r), 4),
            'spearman_p': round(float(p), 6),
        }
    return results


def load_current_modes(yaml_path):
    """从 all_bonus.yaml 读取当前各因子的 mode 配置。"""
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)
    qs = cfg.get('quality_scorer', {})

    modes = {}
    for name, (_, yaml_key) in FACTOR_MAP.items():
        entry = qs.get(yaml_key, {})
        modes[name] = entry.get('mode', 'gte')
    return modes


def apply_corrections(yaml_path, corrections):
    """将方向修正写入 all_bonus.yaml。"""
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)
    qs = cfg['quality_scorer']

    for name, new_mode in corrections.items():
        _, yaml_key = FACTOR_MAP[name]
        if yaml_key in qs:
            qs[yaml_key]['mode'] = new_mode

    with open(yaml_path, 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def main():
    # === 配置 ===
    input_csv = str(PROJECT_ROOT / "outputs/analysis/bonus_analysis_data.csv")
    yaml_path = str(PROJECT_ROOT / "configs/params/all_bonus.yaml")
    auto_apply = False  # True 时自动写入修正

    # === 加载数据 ===
    print(f"Loading: {input_csv}")
    df = pd.read_csv(input_csv)
    df = df.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    print(f"  Rows: {len(df)}")

    # === 诊断 ===
    raw_values = prepare_raw_values(df)
    labels = df[LABEL_COL].values
    diagnosis = diagnose_direction(raw_values, labels)

    # 读取当前配置
    current_modes = load_current_modes(yaml_path)

    # === 报告 ===
    print(f"\n{'Factor':<10s} {'Spearman':>10s} {'Direction':>10s} {'Recommend':>10s} {'Current':>10s} {'Action':>10s}")
    print("-" * 65)

    corrections = {}
    for name in FACTOR_MAP:
        d = diagnosis.get(name, {})
        r = d.get('spearman_r')
        r_str = f"{r:+.4f}" if r is not None else "N/A"
        direction = d.get('direction', '?')
        recommended = d.get('mode', 'gte')
        current = current_modes.get(name, 'gte')
        action = "FLIP" if recommended != current else "OK"

        if recommended != current:
            corrections[name] = recommended

        print(f"  {name:<10s} {r_str:>10s} {direction:>10s} {recommended:>10s} {current:>10s} {action:>10s}")

    # === 修正 ===
    if corrections:
        print(f"\n  Corrections needed: {len(corrections)}")
        for name, mode in corrections.items():
            print(f"    {name}: {current_modes[name]} -> {mode}")

        if auto_apply:
            apply_corrections(yaml_path, corrections)
            print(f"\n  Applied to {yaml_path}")
        else:
            print(f"\n  Set auto_apply=True to write corrections, or use the correct-factor-direction skill.")
    else:
        print(f"\n  All factor directions are correct.")


if __name__ == '__main__':
    main()
```

**Step 2: 运行验证**

```bash
cd scripts/analysis && uv run python diagnose_factor_direction.py
```

预期输出：Streak 显示 Spearman 为负，recommend=lte，current=gte，action=FLIP。

**Step 3: Commit**

```bash
git add scripts/analysis/diagnose_factor_direction.py
git commit -m "feat: 新增因子方向诊断脚本（基于 raw value Spearman）"
```

---

### Task 4: 创建 correct-factor-direction skill

**说明:** 创建 AI skill，指导 AI 根据 `diagnose_factor_direction.py` 的输出自动修正 `all_bonus.yaml` 中的 mode 字段。

**Files:**
- Create: `.claude/skills/correct-factor-direction/SKILL.md`

**Step 1: 创建 skill 文件**

```markdown
---
name: correct-factor-direction
description: 诊断并修正因子触发方向。根据 raw value Spearman 相关性判断因子应该用 gte 还是 lte mode，自动修正 all_bonus.yaml。触发词："修正方向", "diagnose direction", "factor polarity", "检查因子方向"。
---

# Correct Factor Direction

## Overview

基于 raw value 与 label 的 Spearman 相关性，诊断因子触发方向并修正 `all_bonus.yaml`。

**核心原则：方向判断在原始数据空间进行，不依赖 level/threshold 预设。**

## 前置条件

检查 `outputs/analysis/bonus_analysis_data.csv` 是否存在且非空。如果不存在，提示用户先运行：
```bash
cd scripts/analysis && uv run python bonus_combination_analysis.py
```

## Step 1: 运行诊断

```bash
cd scripts/analysis && uv run python diagnose_factor_direction.py
```

解读输出表格：
- **Spearman > 0**：正向因子，值越大 label 越好 → mode=gte
- **Spearman < 0**：反向因子，值越大 label 越差 → mode=lte
- **|Spearman| < 0.015**：无显著方向，保持 gte

## Step 2: 确认修正

如果有 Action=FLIP 的因子，向用户展示：

| 因子 | Spearman | 当前 mode | 建议 mode | 含义 |
|------|----------|----------|----------|------|
| Streak | -0.1988 | gte | lte | 高 streak = 差表现，应奖励低 streak |

让用户确认是否接受全部修正，或逐个选择。

## Step 3: 应用修正

如果用户确认，读取 `configs/params/all_bonus.yaml`，将需要翻转的因子的 `mode` 字段修改为诊断建议的值。

修改时注意：
- 只改 `mode` 字段，不改 thresholds 和 values
- 如果从 gte 翻转为 lte，thresholds 的排列顺序可能需要反转（lte mode 要求降序）
- 提醒用户：翻转 mode 后，需重新运行 `optimize_thresholds.py` 以使 bonus_filter.yaml 与新方向一致

## Step 4: 验证

修正后再次运行诊断，确认所有因子 Action=OK：
```bash
cd scripts/analysis && uv run python diagnose_factor_direction.py
```

## 注意事项

- 本 skill 只修改 `all_bonus.yaml` 的 mode 字段
- 不修改 thresholds/values（那是 optimize_thresholds.py 的职责）
- 不修改任何 Python 代码
- 修正后需重新运行优化管线以更新 bonus_filter.yaml
```

**Step 2: Commit**

```bash
git add .claude/skills/correct-factor-direction/SKILL.md
git commit -m "feat: 新增因子方向修正 skill"
```

---

### Task 5: 更新 orchestrate-bonus-pipeline skill

**说明:** 管线编排 skill 中引用了 `auto_correct_bonus.py`，需替换为新的诊断脚本和方向修正 skill。

**Files:**
- Modify: `.claude/skills/orchestrate-bonus-pipeline/SKILL.md`

**Step 1: 修改管线步骤**

将 Step 3.2 中的 `auto_correct_bonus.py` 替换：

```markdown
### 3.2 诊断因子方向（场景 A/B）
```bash
cd scripts/analysis && uv run python diagnose_factor_direction.py
```
**关键交互点：** 如果有 Action=FLIP 的因子，使用 `correct-factor-direction` skill 的流程进行修正。
```

将文件地图中 `auto_correct_bonus.py` 的引用移除，改为 `diagnose_factor_direction.py`。

**Step 2: Commit**

```bash
git add .claude/skills/orchestrate-bonus-pipeline/SKILL.md
git commit -m "refactor: 管线 skill 引用诊断脚本替代 auto_correct_bonus.py"
```

---

### Task 6: 更新 add-new-bonus skill

**说明:** `add-new-bonus` skill 的 Step 9 引用了 `auto_correct_bonus.py` 的 `NAME_TO_YAML_KEY`，需更新为新脚本。

**Files:**
- Modify: `.claude/skills/add-new-bonus/SKILL.md`

**Step 1: 修改 Step 9**

将 Step 9 从 `auto_correct_bonus.py` 改为 `diagnose_factor_direction.py`：

```markdown
### Step 9: `scripts/analysis/diagnose_factor_direction.py` — `FACTOR_MAP` 注册

```python
FACTOR_MAP = {
    ...
    "XXX": ("xxx_value", "xxx_bonus"),    # ← 新增
}
```
```

同步更新检查清单和完成后操作的文字说明。

**Step 2: Commit**

```bash
git add .claude/skills/add-new-bonus/SKILL.md
git commit -m "refactor: add-new-bonus skill 引用诊断脚本替代 auto_correct_bonus.py"
```

---

### Task 7: 删除 auto_correct_bonus.py

**说明:** 该脚本的方向诊断功能已被 `diagnose_factor_direction.py` 替代，单因子阈值优化功能已被 `optimize_thresholds.py` 的组合优化取代。

**Files:**
- Delete: `scripts/analysis/auto_correct_bonus.py`

**Step 1: 确认无其他依赖**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy && grep -r "auto_correct_bonus" --include="*.py" --include="*.md" --include="*.yaml"
```

预期：仅在已修改的 skill 文件和自身中出现（skill 在 Task 5/6 已更新）。

**Step 2: 删除**

```bash
git rm scripts/analysis/auto_correct_bonus.py
```

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: 删除 auto_correct_bonus.py（已被组合优化 + 方向诊断替代）"
```

---

### Task 8: 端到端验证

**Step 1: 运行方向诊断，确认 Streak 被识别为反向**

```bash
cd scripts/analysis && uv run python diagnose_factor_direction.py
```

预期：Streak 行显示 Spearman < 0，recommend=lte，action=FLIP。

**Step 2: 手动修正 all_bonus.yaml 中 Streak 的 mode（模拟 skill 操作）**

将 `streak_bonus` 的 `mode: gte` 改为 `mode: lte`。

**Step 3: 再次运行诊断，确认全部 OK**

```bash
cd scripts/analysis && uv run python diagnose_factor_direction.py
```

预期：所有因子 Action=OK。

**Step 4: 运行优化管线确认无报错**

```bash
cd scripts/analysis && uv run python optimize_thresholds.py
```

预期：
- 打印 `Negative factors (lte mode): ['Streak']`
- Stage 1-4 正常运行
- 输出 `bonus_filter.yaml`

**Step 5: 验证输出 YAML 有效**

```bash
uv run python -c "import yaml; d=yaml.safe_load(open('../../configs/params/bonus_filter.yaml')); print(f'Templates: {d[\"_meta\"][\"total_templates\"]}')"
```
