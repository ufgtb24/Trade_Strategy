# 阈值挖掘管线重构 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 重构阈值挖掘管线——删除无效的预筛选阶段，全因子直接搜索，新增参数文件输出，替换过时 skill。

**Architecture:** 在现有 `threshold_optimizer.py` 基础上删除 Stage 1/2（lift 筛选 + 时序验证），全因子直接进入 Beam Search + Optuna 搜索。新增 `param_writer.py` 将优化阈值写入 `all_bonus_mined.yaml`。`pipeline.py` 串联全流程。新建 `run-mining-pipeline` skill 替代过时的 `orchestrate-bonus-pipeline`。

**Tech Stack:** Python, Optuna, PyYAML, numpy, pandas

---

## Context

研究报告 `docs/research/pre_filter_vs_full_factor_optimization.md` 证明：
- Stage 1 的 lift 预筛选有系统性缺陷（循环依赖 + 假阴性），错误排除了 PK-Mom（重要性第 2）、PeakVol（第 4）、Age（第 5）
- 10 维全因子搜索仅比 6 维多花 37 秒，但 viable_count +361%
- Stage 2 时序验证应移至最终结果验证，而非中间产物

当前 `threshold_optimizer.py` 结构（661 行）：
- Lines 1-26: imports
- Lines 31-56: `build_triggered_matrix()` — **保留**
- Lines 59-86: `fast_evaluate()` — **保留**
- Lines 89-123: `decode_templates()` — **保留**
- Lines 130-143: `load_bk_thresholds()` — **删除**（仅 Stage 1 使用）
- Lines 146-158: `load_factor_modes()` — **保留**
- Lines 161-191: `compute_factor_lift()` — **删除**
- Lines 194-209: `stage1_factor_screening()` — **删除**
- Lines 216-247: `stage2_temporal_validation()` — **删除**
- Lines 254-340: `stage3a_greedy_beam_search()` — **保留**
- Lines 347-407: `stage3b_optuna_search()` — **保留**
- Lines 414-483: `select_best_trial()` — **保留**
- Lines 490-661: `main()` — **重写**

---

### Task 1: 精简 threshold_optimizer.py — 删除 Stage 1/2 函数

**Files:**
- Modify: `BreakoutStrategy/mining/threshold_optimizer.py`

**Step 1:** 更新模块 docstring（Lines 1-13）

替换为：

```python
"""
阈值优化流水线

全因子直接搜索最优阈值组合：
Step 1a: 贪心 Beam Search（快速找到好起点）
Step 1b: Optuna TPE 多目标搜索（精细优化）
Step 2: Bootstrap 验证 + 最优解选择

输入: bonus_analysis_data DataFrame + all_bonus.yaml (mode)
输出: bonus_filter.yaml 的模板列表
"""
```

**Step 2:** 删除 4 个函数

删除以下函数（含其上方的注释分隔线）：
- `load_bk_thresholds()` (Lines 126-143，含 Lines 126-128 的分隔线注释)
- `compute_factor_lift()` (Lines 161-191)
- `stage1_factor_screening()` (Lines 194-209)
- `stage2_temporal_validation()` (Lines 212-247，含 Lines 212-214 的分隔线注释)

同时删除 imports 中不再需要的 `Counter`（Line 17，仅 `compute_factor_lift` 使用）。

**Step 3:** 删除 `get_factor_config` import，因为 main() 重写后不再需要（Lines 23）。仅保留 `LABEL_COL`。新增 `get_active_factors` import（用于获取全因子列表）。

import 行变为：

```python
from .factor_registry import get_active_factors, LABEL_COL
```

注意：`load_factor_modes()` 内部也使用了 `get_factor_config`，需要改为本地 import。在 `load_factor_modes()` 函数内第一行添加：

```python
def load_factor_modes(yaml_path):
    """从 all_bonus.yaml 读取各因子的 mode，返回反向因子集合。"""
    from .factor_registry import get_factor_config
    factor_config = get_factor_config()
```

**Verify:** `uv run python -c "from BreakoutStrategy.mining.threshold_optimizer import build_triggered_matrix, fast_evaluate, decode_templates, load_factor_modes, stage3a_greedy_beam_search, stage3b_optuna_search, select_best_trial; print('OK')"`

**Commit:** `refactor: remove Stage 1/2 functions from threshold_optimizer`

---

### Task 2: 重写 threshold_optimizer.main() — 全因子直接搜索

**Files:**
- Modify: `BreakoutStrategy/mining/threshold_optimizer.py`

**Step 1:** 替换整个 `main()` 函数（从 `def main():` 到文件末尾）

```python
def main():
    from pathlib import Path

    from .template_generator import build_yaml_output, print_summary, write_yaml

    PROJECT_ROOT = Path.cwd()
    input_csv = str(PROJECT_ROOT / "outputs/analysis/bonus_analysis_data.csv")
    bonus_yaml = str(PROJECT_ROOT / "configs/params/all_bonus.yaml")
    output_yaml = str(PROJECT_ROOT / "configs/params/bonus_filter.yaml")

    # 搜索参数
    beam_width = 3
    n_trials = 3000
    min_count = 10
    trigger_rate_lo = 0.03
    trigger_rate_hi = 0.50
    top_k_objective = 5
    bootstrap_n = 1000

    # === 加载数据 ===
    print(f"Loading: {input_csv}")
    df = pd.read_csv(input_csv)
    df = df.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    print(f"  Rows: {len(df)}")

    # === 全因子列表（从 FACTOR_REGISTRY 获取） ===
    all_factors = [f.display_name for f in get_active_factors()]
    print(f"\n=== Factor Setup ===")
    print(f"  All factors ({len(all_factors)}): {all_factors}")

    raw_values = prepare_raw_values(df)
    labels = df[LABEL_COL].values
    negative_factors = load_factor_modes(bonus_yaml)
    print(f"  Negative factors (lte mode): {sorted(negative_factors) if negative_factors else 'none'}")

    # === Step 1a: 贪心 Beam Search ===
    print(f"\n=== Step 1a: Greedy Beam Search ===")
    greedy_results = stage3a_greedy_beam_search(
        raw_values, labels, all_factors,
        beam_width=beam_width, min_samples=min_count * 5,
        negative_factors=negative_factors,
    )

    print(f"\n  Greedy results ({len(greedy_results)} paths):")
    for i, r in enumerate(greedy_results):
        print(f"    Path {i+1}: median={r['median']:.4f}  count={r['count']}  "
              f"factors={r['factors_used']}  thresholds={r['thresholds']}")

    # === Step 1b: Optuna TPE 多目标搜索 ===
    print(f"\n=== Step 1b: Optuna TPE Multi-Objective ({n_trials} trials) ===")
    study = stage3b_optuna_search(
        raw_values, labels, all_factors,
        greedy_seeds=greedy_results,
        n_trials=n_trials, min_count=min_count,
        top_k=top_k_objective,
        trigger_rate_lo=trigger_rate_lo, trigger_rate_hi=trigger_rate_hi,
        negative_factors=negative_factors,
    )

    pareto_trials = study.best_trials
    print(f"\n  Pareto front: {len(pareto_trials)} solutions")
    pareto_sorted = sorted(pareto_trials, key=lambda t: t.values[0], reverse=True)
    print(f"  {'#':>3s} {'top5_median':>12s} {'viable_count':>13s}")
    for i, t in enumerate(pareto_sorted[:10]):
        print(f"  {i+1:3d} {t.values[0]:12.4f} {int(t.values[1]):13d}")

    # === Step 2: 验证 + 输出 ===
    print(f"\n=== Step 2: Validation & Output ===")
    best = select_best_trial(
        study, raw_values, labels, all_factors,
        min_count=min_count, bootstrap_n=bootstrap_n,
        negative_factors=negative_factors,
    )

    print(f"  Best solution:")
    print(f"    Top-5 avg median: {best['top5_median']:.4f}")
    print(f"    Viable count:     {best['viable_count']}")
    print(f"    Stability score:  {best['stability_score']:.3f}")
    print(f"    95% CI:           {best['ci_95']}")
    print(f"    Templates:        {best['n_templates']}")
    print(f"    Thresholds:")
    for name, t in best['thresholds'].items():
        if name in negative_factors:
            rate = (raw_values[name] <= t).mean()
            print(f"      {name:<10s}: <= {t:.4f}  (trigger rate: {rate:.1%})")
        else:
            rate = (raw_values[name] >= t).mean()
            print(f"      {name:<10s}: >= {t:.4f}  (trigger rate: {rate:.1%})")

    templates = best['templates']

    yaml_data = build_yaml_output(templates, df, input_csv, min_count,
                                  generator='BreakoutStrategy.mining.threshold_optimizer')

    yaml_data['_meta']['optimization'] = {
        'method': 'greedy_beam_search + optuna_tpe',
        'n_trials': n_trials,
        'active_factors': all_factors,
        'thresholds': {k: round(float(v), 4) for k, v in best['thresholds'].items()},
        'top5_median': round(float(best['top5_median']), 4),
        'stability_score': round(float(best['stability_score']), 3),
    }

    write_yaml(yaml_data, output_yaml,
               header_comment="# configs/params/bonus_filter.yaml\n"
                              "# 由 BreakoutStrategy.mining.threshold_optimizer 自动生成\n\n")
    print(f"\n  Output: {output_yaml}")

    print_summary(yaml_data)


if __name__ == "__main__":
    main()
```

**关键变更说明：**
- `factor_order` / `stable_factors` → `all_factors`，从 `get_active_factors()` 获取全部注册因子
- 删除 Stage 0/1/2 全部调用
- 原 Stage 3a → Step 1a，原 Stage 3b → Step 1b，原 Stage 4 → Step 2
- `bk_yaml` → `bonus_yaml`（语义更清晰）
- 删除 `required_raw_cols` 校验（`prepare_raw_values` 内部会处理）

**Verify:** `uv run python -c "from BreakoutStrategy.mining.threshold_optimizer import main; print('OK')"`

**Commit:** `refactor: rewrite threshold_optimizer main() for full-factor search`

---

### Task 3: 新建 param_writer.py

**Files:**
- Create: `BreakoutStrategy/mining/param_writer.py`

**Step 1:** 创建文件

```python
"""
参数文件生成器

读取 threshold_optimizer 优化后的阈值（bonus_filter.yaml），
将其写入 all_bonus_mined.yaml：复制 all_bonus.yaml 的完整结构，
替换 quality_scorer 中各因子的 thresholds 为单一二值阈值，values 设为 [1]。

未参与优化的因子（不在 FACTOR_REGISTRY 中）保持原值。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .factor_registry import FACTOR_REGISTRY


def build_mined_params(base_yaml_path: str, filter_yaml_path: str) -> dict:
    """
    合并 all_bonus.yaml 的完整结构与 bonus_filter.yaml 的优化阈值。

    Args:
        base_yaml_path: all_bonus.yaml 路径（完整结构模板）
        filter_yaml_path: bonus_filter.yaml 路径（含优化阈值）

    Returns:
        合并后的完整 YAML dict
    """
    with open(base_yaml_path) as f:
        base = yaml.safe_load(f)

    with open(filter_yaml_path) as f:
        filter_data = yaml.safe_load(f)

    # 从 bonus_filter.yaml 的 _meta.optimization.thresholds 读取优化阈值
    optimization = filter_data.get('_meta', {}).get('optimization', {})
    mined_thresholds = optimization.get('thresholds', {})

    if not mined_thresholds:
        raise ValueError(
            f"No optimization thresholds found in {filter_yaml_path}. "
            "Run threshold_optimizer first."
        )

    # 构建 display_name → yaml_key 映射
    name_to_yaml_key = {f.display_name: f.yaml_key for f in FACTOR_REGISTRY}

    # 替换 quality_scorer 中已优化因子的 thresholds 和 values
    qs = base.get('quality_scorer', {})
    applied = []

    for display_name, threshold in mined_thresholds.items():
        yaml_key = name_to_yaml_key.get(display_name)
        if yaml_key and yaml_key in qs:
            entry = qs[yaml_key]
            entry['thresholds'] = [round(float(threshold), 4)]
            entry['values'] = [1]
            applied.append(display_name)

    return base, applied


def write_mined_yaml(data: dict, output_path: str | Path, applied: list[str]):
    """写入 all_bonus_mined.yaml"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = (
        "# configs/params/all_bonus_mined.yaml\n"
        "# 由 BreakoutStrategy.mining.param_writer 自动生成\n"
        f"# 已优化因子: {', '.join(applied)}\n"
        "# thresholds = 挖掘到的二值阈值, values = [1]\n\n"
    )

    with open(output_path, 'w') as f:
        f.write(header)
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def main():
    PROJECT_ROOT = Path.cwd()
    base_yaml = str(PROJECT_ROOT / "configs/params/all_bonus.yaml")
    filter_yaml = str(PROJECT_ROOT / "configs/params/bonus_filter.yaml")
    output_yaml = str(PROJECT_ROOT / "configs/params/all_bonus_mined.yaml")

    print(f"Base config:  {base_yaml}")
    print(f"Filter file:  {filter_yaml}")

    data, applied = build_mined_params(base_yaml, filter_yaml)

    print(f"\n  Applied mined thresholds to {len(applied)} factors: {applied}")

    # 显示替换结果
    qs = data.get('quality_scorer', {})
    for name in applied:
        yaml_key = {f.display_name: f.yaml_key for f in FACTOR_REGISTRY}.get(name)
        if yaml_key:
            entry = qs[yaml_key]
            print(f"    {name:<10s}: mode={entry['mode']}  "
                  f"thresholds={entry['thresholds']}  values={entry['values']}")

    write_mined_yaml(data, output_yaml, applied)
    print(f"\n  Output: {output_yaml}")


if __name__ == "__main__":
    main()
```

**Verify:** `uv run python -c "from BreakoutStrategy.mining.param_writer import build_mined_params, write_mined_yaml; print('OK')"`

**Commit:** `feat: add param_writer for all_bonus_mined.yaml output`

---

### Task 4: 扩展 pipeline.py

**Files:**
- Modify: `BreakoutStrategy/mining/pipeline.py`

**Step 1:** 替换整个文件内容

```python
"""
阈值挖掘管线编排器

步骤:
  1. data_pipeline.main()          → bonus_analysis_data.csv
  2. factor_diagnosis.main()       → 诊断并修正 all_bonus.yaml
  3. threshold_optimizer.main()    → bonus_filter.yaml
  4. param_writer.main()           → all_bonus_mined.yaml

用法: uv run -m BreakoutStrategy.mining.pipeline
"""

from pathlib import Path


def main():
    import os
    os.environ["BONUS_AUTO_APPLY"] = "1"  # 无人值守模式

    print("=" * 60)
    print("[Pipeline] Step 1/4: 重建分析数据集")
    print("=" * 60)
    from .data_pipeline import main as data_main
    data_main()

    print("\n" + "=" * 60)
    print("[Pipeline] Step 2/4: 诊断并修正因子方向")
    print("=" * 60)
    from .factor_diagnosis import main as diag_main
    diag_main()

    print("\n" + "=" * 60)
    print("[Pipeline] Step 3/4: 全因子阈值优化")
    print("=" * 60)
    from .threshold_optimizer import main as opt_main
    opt_main()

    print("\n" + "=" * 60)
    print("[Pipeline] Step 4/4: 生成挖掘参数文件")
    print("=" * 60)
    from .param_writer import main as param_main
    param_main()

    PROJECT_ROOT = Path.cwd()
    print(f"\n{'=' * 60}")
    print("[Pipeline] All steps completed successfully!")
    print(f"{'=' * 60}")
    print("Output files:")
    print(f"  - {PROJECT_ROOT / 'configs/params/all_bonus.yaml'}  (方向已修正)")
    print(f"  - {PROJECT_ROOT / 'configs/params/bonus_filter.yaml'}  (组合模板)")
    print(f"  - {PROJECT_ROOT / 'configs/params/all_bonus_mined.yaml'}  (挖掘参数)")


if __name__ == "__main__":
    main()
```

**Verify:** `uv run python -c "from BreakoutStrategy.mining.pipeline import main; print('OK')"`

**Commit:** `feat: extend pipeline with param_writer step`

---

### Task 5: 更新 __init__.py docstring

**Files:**
- Modify: `BreakoutStrategy/mining/__init__.py`

**Step 1:** 替换模块 docstring（Lines 1-25）

```python
"""
数据挖掘模块

提供 bonus 因子的统一注册、数据管道、统计分析、
阈值优化和报告生成等功能。

核心组件:
- factor_registry: 统一因子注册表（消除 4 套分散映射）
- data_pipeline: 数据构建管道（build_dataframe + prepare_raw_values）
- stats_analysis: 组合统计分析引擎
- report_generator: Markdown 报告生成
- distribution_analysis: 分布形态分析
- factor_diagnosis: 因子方向诊断 + YAML 修正
- template_generator: 模板枚举 + YAML 输出
- threshold_optimizer: 全因子阈值优化（Beam Search + Optuna）
- param_writer: 参数文件生成（all_bonus_mined.yaml）
- pipeline: 全管线编排（1→2→3→4）

入口命令:
- uv run -m BreakoutStrategy.mining.data_pipeline      重建分析数据集
- uv run -m BreakoutStrategy.mining.factor_diagnosis    诊断因子方向
- uv run -m BreakoutStrategy.mining.threshold_optimizer 阈值优化
- uv run -m BreakoutStrategy.mining.template_generator  模板枚举
- uv run -m BreakoutStrategy.mining.param_writer        生成挖掘参数文件
- uv run -m BreakoutStrategy.mining.distribution_analysis 分布形态分析
- uv run -m BreakoutStrategy.mining.pipeline            全管线编排
"""
```

**Verify:** `uv run python -c "import BreakoutStrategy.mining; print('OK')"`

**Commit:** `docs: update mining __init__.py docstring`

---

### Task 6: 删除 orchestrate-bonus-pipeline skill

**Files:**
- Delete: `.claude/skills/orchestrate-bonus-pipeline/SKILL.md`
- Delete: `.claude/skills/orchestrate-bonus-pipeline/` (directory)

**Step 1:** 删除目录

```bash
rm -rf .claude/skills/orchestrate-bonus-pipeline
```

**Commit:** `chore: remove obsolete orchestrate-bonus-pipeline skill`

---

### Task 7: 新建 run-mining-pipeline skill

**Files:**
- Create: `.claude/skills/run-mining-pipeline/SKILL.md`

**Step 1:** 创建 skill 文件

```markdown
---
name: run-mining-pipeline
description: 运行阈值挖掘管线。对 FACTOR_REGISTRY 中所有因子进行全因子阈值搜索，输出组合模板和挖掘参数文件。触发词："run mining", "挖掘阈值", "threshold mining", "运行管线", "阈值优化"。
---

# Run Mining Pipeline

## Overview

对 FACTOR_REGISTRY 中所有已注册因子执行阈值挖掘，输出优化后的组合模板和参数文件。

**核心原则：AI 编排，脚本执行。** 数据处理和优化算法在确定性脚本中完成。AI 做状态诊断、结果解读、异常处理。

## 前置条件

- 已完成全量扫描（`outputs/scan_results/scan_results_all.json` 存在）
- 新因子已通过 `register-mining-bonus` skill 注册到 FACTOR_REGISTRY

## 文件地图

| 文件 | 角色 |
|------|------|
| `outputs/scan_results/scan_results_all.json` | 原始扫描数据 |
| `outputs/analysis/bonus_analysis_data.csv` | 分析数据集 |
| `configs/params/all_bonus.yaml` | 因子配置（mode 来源） |
| `configs/params/bonus_filter.yaml` | 输出：组合模板 |
| `configs/params/all_bonus_mined.yaml` | 输出：挖掘参数文件 |

## Step 1: 状态诊断

执行前检查前置条件：

```bash
# 检查扫描数据
ls -la outputs/scan_results/scan_results_all.json

# 检查现有输出时间戳
stat -c %y outputs/analysis/bonus_analysis_data.csv 2>/dev/null || echo "CSV 不存在"
stat -c %y configs/params/bonus_filter.yaml 2>/dev/null || echo "Filter 不存在"
```

### 诊断逻辑
- **JSON 不存在** → 提示用户先运行扫描，不代执行
- **CSV 不存在或过时** → 管线会自动重建
- **一切就绪** → 确认后执行

## Step 2: 执行管线

### 一键模式（推荐）

```bash
uv run -m BreakoutStrategy.mining.pipeline
```

管线自动串联 4 个步骤：
1. 重建分析数据集 → `bonus_analysis_data.csv`
2. 诊断并修正因子方向 → 更新 `all_bonus.yaml`
3. 全因子阈值优化 → `bonus_filter.yaml`
4. 生成挖掘参数文件 → `all_bonus_mined.yaml`

### 分步模式（调试用）

```bash
# 仅重建数据集
uv run -m BreakoutStrategy.mining.data_pipeline

# 仅诊断方向
uv run -m BreakoutStrategy.mining.factor_diagnosis

# 仅阈值优化
uv run -m BreakoutStrategy.mining.threshold_optimizer

# 仅生成参数文件
uv run -m BreakoutStrategy.mining.param_writer
```

## Step 3: 结果解读

管线完成后读取并呈现：

### 3.1 bonus_filter.yaml 摘要
```bash
uv run python -c "
import yaml
with open('configs/params/bonus_filter.yaml') as f:
    data = yaml.safe_load(f)
meta = data['_meta']
templates = data['templates']
print(f'Sample size: {meta[\"sample_size\"]}')
print(f'Total templates: {meta[\"total_templates\"]}')
print(f'Baseline median: {meta[\"baseline_median\"]}')
opt = meta.get('optimization', {})
print(f'Top-5 median: {opt.get(\"top5_median\")}')
print(f'Active factors: {opt.get(\"active_factors\")}')
print(f'Thresholds: {opt.get(\"thresholds\")}')
print(f'\nTop 5 templates:')
for i, t in enumerate(templates[:5]):
    print(f'  {i+1}. {t[\"name\"]}  count={t[\"count\"]}  median={t[\"median\"]}')
"
```

### 3.2 all_bonus_mined.yaml 检查
```bash
uv run python -c "
import yaml
with open('configs/params/all_bonus_mined.yaml') as f:
    data = yaml.safe_load(f)
qs = data['quality_scorer']
for key, entry in qs.items():
    if isinstance(entry, dict) and 'thresholds' in entry:
        print(f'{key}: mode={entry.get(\"mode\",\"gte\")} thresholds={entry[\"thresholds\"]} values={entry[\"values\"]}')
"
```

## Step 4: 异常处理

| 异常 | AI 行为 |
|------|---------|
| 脚本报错退出 | 读取错误信息，解释原因，建议修复 |
| 0 templates 生成 | 检查数据量、触发率约束，建议放宽参数 |
| stability_score = 0 | 样本量不足以做 bootstrap，正常但需注意 |
| factor_diagnosis 报 FLIP | 管线会自动修正（auto_apply=True） |

## 调参

`threshold_optimizer.py` 的 `main()` 参数：

```python
beam_width = 3          # 贪心搜索保留路径数
n_trials = 3000         # Optuna 搜索次数
min_count = 10          # 模板最小样本量
trigger_rate_lo = 0.03  # 触发率下限
trigger_rate_hi = 0.50  # 触发率上限
top_k_objective = 5     # 目标函数用 top-K 模板的平均 median
bootstrap_n = 1000      # Bootstrap 重采样次数
```
```

**Commit:** `feat: add run-mining-pipeline skill`

---

## Verification

```bash
# 1. 全链路 import 验证
uv run python -c "
from BreakoutStrategy.mining.threshold_optimizer import main as opt_main
from BreakoutStrategy.mining.param_writer import main as param_main
from BreakoutStrategy.mining.pipeline import main as pipe_main
print('All imports OK')
"

# 2. 确认 Stage 1/2 函数已删除
uv run python -c "
from BreakoutStrategy.mining import threshold_optimizer as to
assert not hasattr(to, 'stage1_factor_screening'), 'stage1 still exists!'
assert not hasattr(to, 'stage2_temporal_validation'), 'stage2 still exists!'
assert not hasattr(to, 'load_bk_thresholds'), 'load_bk_thresholds still exists!'
assert not hasattr(to, 'compute_factor_lift'), 'compute_factor_lift still exists!'
print('Stage 1/2 functions removed.')
"

# 3. 确认旧 skill 已删除
test ! -d .claude/skills/orchestrate-bonus-pipeline && echo "Old skill removed" || echo "FAIL: old skill still exists"

# 4. 确认新 skill 存在
test -f .claude/skills/run-mining-pipeline/SKILL.md && echo "New skill exists" || echo "FAIL: new skill missing"

# 5. 端到端管线运行（可选，约 2 分钟）
# uv run -m BreakoutStrategy.mining.pipeline
```
