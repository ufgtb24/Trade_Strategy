# Shrinkage Objective 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Optuna 搜索从有缺陷的 (top_k_median, viable_count) 双目标改为 shrinkage top_k 单目标，消除小样本噪声引导。

**Architecture:** 在 `fast_evaluate` 中引入 James-Stein 收缩（`w = n/(n+n0)`），将小样本模板的 median 向 baseline 收缩。Optuna 改为单目标最大化收缩后的 top_k 均值。`select_best_trial` 适配单目标 study 并增加 count>=30 后筛。k 可配置，k=1 时退化为 top1。

**Tech Stack:** numpy, pandas, optuna

---

### Task 1: 修改 fast_evaluate — 引入 shrinkage 评分

**Files:**
- Modify: `BreakoutStrategy/mining/threshold_optimizer.py:55-82`

**Step 1: 修改 fast_evaluate 函数签名和逻辑**

将 `fast_evaluate` 从返回 `(top_k_median, viable_count, n_templates)` 改为返回 `(shrinkage_score, n_templates)`。

```python
def fast_evaluate(triggered, labels, min_count=10, top_k=5,
                  baseline_median=0.0, shrinkage_n0=50):
    """
    Bit-packed 向量化模板评估 + James-Stein 收缩。

    收缩公式: adjusted_i = w_i * median_i + (1 - w_i) * baseline_median
    其中 w_i = count_i / (count_i + shrinkage_n0)

    当 shrinkage_n0=0 时退化为无收缩（原始 median）。
    当 top_k=1 时只评估最佳模板。

    Returns:
        (shrinkage_score, n_templates)
    """
    n_factors = triggered.shape[1]
    powers = (1 << np.arange(n_factors)).astype(np.int64)
    combo_keys = triggered @ powers

    combo_df = pd.DataFrame({'key': combo_keys, 'label': labels})
    stats = combo_df.groupby('key')['label'].agg(['count', 'median'])
    stats = stats[stats.index > 0]
    stats = stats[stats['count'] >= min_count]
    stats = stats.sort_values('median', ascending=False)

    n_templates = len(stats)
    if n_templates < top_k:
        return 0.0, n_templates

    top_stats = stats.iloc[:top_k]
    if shrinkage_n0 > 0:
        weights = top_stats['count'] / (top_stats['count'] + shrinkage_n0)
        adjusted = weights * top_stats['median'] + (1 - weights) * baseline_median
        shrinkage_score = float(adjusted.mean())
    else:
        shrinkage_score = float(top_stats['median'].mean())

    return shrinkage_score, n_templates
```

**Step 2: 验证修改**

运行: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "
from BreakoutStrategy.mining.threshold_optimizer import fast_evaluate
import numpy as np
# 简单验证: 2因子, 5样本
triggered = np.array([[1,0],[0,1],[1,1],[1,0],[0,1]], dtype=np.int64)
labels = np.array([0.5, 0.3, 0.8, 0.6, 0.2])
# 无收缩
score0, n0 = fast_evaluate(triggered, labels, min_count=1, top_k=2, baseline_median=0.1, shrinkage_n0=0)
# 有收缩
score50, n50 = fast_evaluate(triggered, labels, min_count=1, top_k=2, baseline_median=0.1, shrinkage_n0=50)
print(f'No shrinkage: score={score0:.4f}, n={n0}')
print(f'With n0=50:   score={score50:.4f}, n={n50}')
assert score50 < score0, 'Shrinkage should pull score toward baseline'
print('OK')
"`

Expected: shrinkage score < raw score, 打印 OK

---

### Task 2: 修改 stage3b_optuna_search — 单目标 shrinkage

**Files:**
- Modify: `BreakoutStrategy/mining/threshold_optimizer.py:235-295`

**Step 1: 修改函数签名和 objective**

```python
def stage3b_optuna_search(raw_values, labels, active_factors,
                          greedy_seeds, n_trials=3000, min_count=10,
                          top_k=5, trigger_rate_lo=0.03, trigger_rate_hi=0.50,
                          negative_factors=frozenset(),
                          baseline_median=0.0, shrinkage_n0=50):
    """Optuna TPE 单目标搜索（shrinkage top_k），以贪心结果做 warm start。"""
    import optuna

    bounds = {}
    for name in active_factors:
        raw = raw_values[name]
        valid = raw[raw > 0]
        if len(valid) > 0:
            bounds[name] = (float(np.quantile(valid, 0.05)),
                            float(np.quantile(valid, 0.95)))
        else:
            bounds[name] = (0.0, 1.0)

    def objective(trial):
        thresholds = {}
        for name in active_factors:
            lo, hi = bounds[name]
            if lo >= hi:
                thresholds[name] = lo
            else:
                thresholds[name] = trial.suggest_float(name, lo, hi)

        triggered = build_triggered_matrix(raw_values, thresholds, active_factors,
                                           negative_factors)

        rates = triggered.mean(axis=0)
        for i, name in enumerate(active_factors):
            if rates[i] > trigger_rate_hi or rates[i] < trigger_rate_lo:
                return 0.0

        shrinkage_score, n_templates = fast_evaluate(
            triggered, labels, min_count, top_k,
            baseline_median, shrinkage_n0
        )
        return shrinkage_score

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )

    for seed in greedy_seeds:
        params = {}
        for name in active_factors:
            lo, hi = bounds[name]
            if name in seed['thresholds']:
                params[name] = float(np.clip(seed['thresholds'][name], lo, hi))
            else:
                raw = raw_values[name]
                valid = raw[raw > 0]
                val = float(np.median(valid)) if len(valid) > 0 else 0.0
                params[name] = float(np.clip(val, lo, hi))
        study.enqueue_trial(params)

    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    return study
```

关键变化:
1. `create_study(direction="maximize")` 替代 `directions=["maximize","maximize"]`
2. objective 返回单值 `shrinkage_score` 替代 `(top_k_median, viable_count)`
3. 新增 `baseline_median` 和 `shrinkage_n0` 参数透传

---

### Task 3: 修改 select_best_trial — 适配单目标 + count 后筛

**Files:**
- Modify: `BreakoutStrategy/mining/threshold_optimizer.py:302-371`

**Step 1: 重写 select_best_trial**

```python
def select_best_trial(study, raw_values, labels, active_factors,
                      min_count=10, top_k=5, min_viable_count=30,
                      bootstrap_n=1000, negative_factors=frozenset()):
    """从单目标 study 中选择最佳解，用 count 门槛 + bootstrap 验证。"""
    trials_sorted = sorted(study.trials,
                           key=lambda t: t.value if t.value is not None else -1,
                           reverse=True)

    best = None
    best_score = -1

    for trial in trials_sorted[:20]:
        if trial.value is None or trial.value <= 0:
            continue

        thresholds = {name: trial.params[name] for name in active_factors
                      if name in trial.params}
        triggered = build_triggered_matrix(raw_values, thresholds, active_factors,
                                           negative_factors)
        templates = decode_templates(triggered, labels, active_factors, min_count)

        if len(templates) < top_k:
            continue

        # count 门槛: top1 的 count 必须 >= min_viable_count
        if templates[0]['count'] < min_viable_count:
            continue

        top_k_templates = templates[:top_k]
        top_k_medians = [t['median'] for t in top_k_templates]
        top_k_avg = np.mean(top_k_medians)

        # Bootstrap 验证所有 top_k 模板，取最小 stability
        n_factors = len(active_factors)
        powers = (1 << np.arange(n_factors)).astype(np.int64)
        combo_keys = triggered @ powers
        rng = np.random.default_rng(42)

        min_stability = 1.0
        all_ci = []
        for tmpl in top_k_templates:
            target_key = sum(1 << active_factors.index(f) for f in tmpl['factors'])
            member_labels = labels[combo_keys == target_key]

            if len(member_labels) >= 20:
                boot_medians = [float(np.median(rng.choice(member_labels, size=len(member_labels), replace=True)))
                                for _ in range(bootstrap_n)]
                ci_lo = np.percentile(boot_medians, 2.5)
                ci_hi = np.percentile(boot_medians, 97.5)
                ci_width = ci_hi - ci_lo
                tmpl_median = float(np.median(member_labels))
                stability = 1 - ci_width / tmpl_median if tmpl_median > 0 else 0
                min_stability = min(min_stability, stability)
                all_ci.append((round(float(ci_lo), 4), round(float(ci_hi), 4)))
            else:
                min_stability = 0.0
                all_ci.append((0.0, 0.0))

        score = trial.value  # 使用 Optuna 的 shrinkage score 作为主排序
        if score > best_score:
            best_score = score
            best = {
                'thresholds': thresholds,
                'shrinkage_score': round(float(trial.value), 4),
                'top_k_raw_median': round(float(top_k_avg), 4),
                'min_stability': round(float(min_stability), 3),
                'top_k_ci': all_ci,
                'templates': templates,
                'n_templates': len(templates),
            }

    if best is None:
        raise ValueError(
            "No viable solution found (all top trials have top1 count < "
            f"{min_viable_count} or < {top_k} templates). "
            "Consider relaxing min_viable_count."
        )

    return best
```

关键变化:
1. 使用 `study.trials` 排序替代 `study.best_trials` (Pareto 前沿)
2. 增加 `min_viable_count=30` 后筛: top1 的 count 必须 >= 30
3. Bootstrap 覆盖所有 top_k 模板，取 `min_stability`
4. 评分直接用 `trial.value`（shrinkage score），不再乘 stability

---

### Task 4: 修改 main — 更新参数和输出

**Files:**
- Modify: `BreakoutStrategy/mining/threshold_optimizer.py:378-490`

**Step 1: 更新 main 函数**

主要变化:
1. 新增 `shrinkage_n0` 和 `shrinkage_k` 参数
2. 计算 `baseline_median` 传给 Optuna
3. Optuna 输出适配单目标（无 Pareto front）
4. 最终输出适配新的 best 字典结构
5. `_meta.optimization` 记录 shrinkage 参数

```python
def main(input_csv, bonus_yaml, output_yaml):
    from BreakoutStrategy.mining.template_generator import build_yaml_output, print_summary, write_yaml

    # 搜索参数
    beam_width = 3
    n_trials = 2000
    min_count = 20
    trigger_rate_lo = 0.03
    trigger_rate_hi = 0.50
    bootstrap_n = 1000
    # Shrinkage 参数
    shrinkage_k = 5          # top_k 模板数 (k=1 时退化为 top1)
    shrinkage_n0 = 50        # 收缩强度 (等效先验样本量)
    min_viable_count = 30    # top1 最少样本量门槛

    # === 加载数据 ===
    print(f"Loading: {input_csv}")
    df = pd.read_csv(input_csv)
    df = df.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    print(f"  Rows: {len(df)}")

    # === 全因子列表 ===
    all_factors = [f.display_name for f in get_active_factors()]
    print(f"\n=== Factor Setup ===")
    print(f"  All factors ({len(all_factors)}): {all_factors}")

    raw_values = prepare_raw_values(df)
    labels = df[LABEL_COL].values
    baseline_median = float(np.median(labels))
    negative_factors = load_factor_modes(bonus_yaml)
    print(f"  Negative factors (lte mode): {sorted(negative_factors) if negative_factors else 'none'}")
    print(f"  Baseline median: {baseline_median:.4f}")
    print(f"  Shrinkage: n0={shrinkage_n0}, k={shrinkage_k}, min_viable_count={min_viable_count}")

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

    # === Step 1b: Optuna TPE 单目标搜索 ===
    print(f"\n=== Step 1b: Optuna TPE Shrinkage (k={shrinkage_k}, n0={shrinkage_n0}, {n_trials} trials) ===")
    study = stage3b_optuna_search(
        raw_values, labels, all_factors,
        greedy_seeds=greedy_results,
        n_trials=n_trials, min_count=min_count,
        top_k=shrinkage_k,
        trigger_rate_lo=trigger_rate_lo, trigger_rate_hi=trigger_rate_hi,
        negative_factors=negative_factors,
        baseline_median=baseline_median, shrinkage_n0=shrinkage_n0,
    )

    # 单目标: 输出 top 10 trials
    trials_sorted = sorted(study.trials,
                           key=lambda t: t.value if t.value is not None else -1,
                           reverse=True)
    print(f"\n  Top 10 trials:")
    print(f"  {'#':>3s} {'shrinkage_score':>16s}")
    for i, t in enumerate(trials_sorted[:10]):
        if t.value is not None:
            print(f"  {i+1:3d} {t.value:16.4f}")

    # === Step 2: 验证 + 输出 ===
    print(f"\n=== Step 2: Validation & Output (min_viable_count={min_viable_count}) ===")
    best = select_best_trial(
        study, raw_values, labels, all_factors,
        min_count=min_count, top_k=shrinkage_k,
        min_viable_count=min_viable_count,
        bootstrap_n=bootstrap_n,
        negative_factors=negative_factors,
    )

    print(f"  Best solution:")
    print(f"    Shrinkage score:  {best['shrinkage_score']}")
    print(f"    Top-{shrinkage_k} raw median: {best['top_k_raw_median']}")
    print(f"    Min stability:    {best['min_stability']}")
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
        'method': 'greedy_beam_search + optuna_tpe_shrinkage',
        'n_trials': n_trials,
        'shrinkage_n0': shrinkage_n0,
        'shrinkage_k': shrinkage_k,
        'min_viable_count': min_viable_count,
        'active_factors': all_factors,
        'thresholds': {k: round(float(v), 4) for k, v in best['thresholds'].items()},
        'shrinkage_score': best['shrinkage_score'],
        'top_k_raw_median': best['top_k_raw_median'],
        'min_stability': best['min_stability'],
    }

    write_yaml(yaml_data, output_yaml,
               header_comment="# configs/params/bonus_filter.yaml\n"
                              "# 由 BreakoutStrategy.mining.threshold_optimizer 自动生成\n\n")
    print(f"\n  Output: {output_yaml}")

    print_summary(yaml_data)
```

**Step 2: 验证编译通过**

运行: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "from BreakoutStrategy.mining.threshold_optimizer import main; print('Import OK')"`

Expected: `Import OK`

**Step 3: Commit**

```bash
git add BreakoutStrategy/mining/threshold_optimizer.py
git commit -m "feat: replace dual-objective with shrinkage single-objective in threshold optimizer

- fast_evaluate: add James-Stein shrinkage (w=n/(n+n0))
- stage3b_optuna_search: single-objective TPE maximizing shrinkage score
- select_best_trial: adapt to single-objective, add count>=30 filter,
  bootstrap all top_k templates (not just top1)
- Configurable k (top_k) and n0 (shrinkage strength)
- k=1 degrades to top1 optimization"
```

---

## 变更摘要

| 函数 | 变化 |
|------|------|
| `fast_evaluate` | +`baseline_median`, +`shrinkage_n0`, 返回 `(shrinkage_score, n_templates)` |
| `stage3b_optuna_search` | 单目标 `direction="maximize"`, +`baseline_median`, +`shrinkage_n0` |
| `select_best_trial` | 无 Pareto, +`min_viable_count=30` 后筛, bootstrap 覆盖所有 top_k |
| `main` | +`shrinkage_k`, +`shrinkage_n0`, +`min_viable_count`, 输出适配 |

**不变的函数**: `build_triggered_matrix`, `decode_templates`, `load_factor_modes`, `stage3a_greedy_beam_search`

**不变的文件**: `pipeline.py`（main 签名 `(input_csv, bonus_yaml, output_yaml)` 未变）
