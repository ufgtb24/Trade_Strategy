"""
Sampler 基准对比实验

对比 5 种 Optuna sampler 在阈值优化场景下的表现。
每种 sampler 运行 N trials，记录收敛曲线和最终 best value。

用法: uv run python scripts/benchmark_samplers.py [sampler_name] [n_trials]
sampler_name: tpe | multivariate_tpe | qmc | cmaes | random
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import optuna

from BreakoutStrategy.factor_registry import get_active_factors, LABEL_COL
from BreakoutStrategy.mining.data_pipeline import prepare_raw_values
from BreakoutStrategy.mining.threshold_optimizer import (
    build_triggered_matrix, fast_evaluate, load_factor_modes,
    stage3a_greedy_beam_search,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 实验参数
MIN_COUNT = 20
SHRINKAGE_N0 = 50
TOP_K = 1
N_STARTUP = 200  # TPE 系列的 startup trials


def create_sampler(name: str):
    """根据名称创建 Optuna sampler。"""
    if name == "tpe":
        return optuna.samplers.TPESampler(seed=42, n_startup_trials=N_STARTUP)
    elif name == "multivariate_tpe":
        return optuna.samplers.TPESampler(
            seed=42, n_startup_trials=N_STARTUP,
            multivariate=True, group=True, n_ei_candidates=48,
        )
    elif name == "qmc":
        return optuna.samplers.QMCSampler(seed=42)
    elif name == "cmaes":
        return optuna.samplers.CmaEsSampler(seed=42, n_startup_trials=N_STARTUP)
    elif name == "random":
        return optuna.samplers.RandomSampler(seed=42)
    else:
        raise ValueError(f"Unknown sampler: {name}")


def run_benchmark(sampler_name: str, n_trials: int):
    """运行单个 sampler 的基准测试。"""
    # === 加载数据 ===
    input_csv = str(PROJECT_ROOT / "outputs/analysis/factor_analysis_data.csv")
    factor_yaml = str(PROJECT_ROOT / "configs/params/all_factor.yaml")

    print(f"Loading: {input_csv}")
    df = pd.read_csv(input_csv)
    df = df.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    print(f"  Rows: {len(df)}")

    all_factors = [f.key for f in get_active_factors()]
    raw_values = prepare_raw_values(df)
    labels = df[LABEL_COL].values
    baseline_median = float(np.median(labels))
    negative_factors = load_factor_modes(factor_yaml)

    print(f"  Factors: {all_factors}")
    print(f"  Baseline median: {baseline_median:.4f}")
    print(f"  Negative factors: {sorted(negative_factors) if negative_factors else 'none'}")

    # === Greedy warm start seeds ===
    print(f"\n=== Greedy Beam Search (warm start) ===")
    greedy_results = stage3a_greedy_beam_search(
        raw_values, labels, all_factors,
        beam_width=10, min_samples=30,
        negative_factors=negative_factors,
    )
    print(f"  {len(greedy_results)} seeds found")

    # === 构建搜索空间 ===
    bounds = {}
    for name in all_factors:
        raw = raw_values[name]
        valid = raw[raw > 0]
        if len(valid) > 0:
            bounds[name] = (float(np.quantile(valid, 0.05)),
                            float(np.quantile(valid, 0.95)))
        else:
            bounds[name] = (0.0, 1.0)

    def objective(trial):
        thresholds = {}
        for name in all_factors:
            lo, hi = bounds[name]
            if lo >= hi:
                thresholds[name] = lo
            else:
                thresholds[name] = trial.suggest_float(name, lo, hi)

        triggered = build_triggered_matrix(raw_values, thresholds, all_factors,
                                           negative_factors)
        shrinkage_score, n_templates, top_detail = fast_evaluate(
            triggered, labels, MIN_COUNT, TOP_K,
            baseline_median, SHRINKAGE_N0
        )
        return shrinkage_score

    # === 创建 study ===
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = create_sampler(sampler_name)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # 注入 warm start seeds (除了 QMC 和 Random，它们不支持 enqueue)
    if sampler_name in ("tpe", "multivariate_tpe", "cmaes"):
        for seed in greedy_results:
            params = {}
            for name in all_factors:
                lo, hi = bounds[name]
                if name in seed['thresholds']:
                    params[name] = float(np.clip(seed['thresholds'][name], lo, hi))
                else:
                    raw = raw_values[name]
                    valid = raw[raw > 0]
                    val = float(np.median(valid)) if len(valid) > 0 else 0.0
                    params[name] = float(np.clip(val, lo, hi))
            study.enqueue_trial(params)

    # === 运行优化 ===
    print(f"\n=== Benchmark: {sampler_name} x {n_trials} trials ===")
    print(f"  min_count={MIN_COUNT}, shrinkage_n0={SHRINKAGE_N0}, top_k={TOP_K}")

    # 收敛曲线：每 100 trials 记录一次 best
    curve = []
    t0 = time.time()

    def callback(study, trial):
        n = len(study.trials)
        if n % 100 == 0 or n == n_trials:
            elapsed = time.time() - t0
            try:
                best_val = study.best_value
            except ValueError:
                best_val = 0.0
            curve.append({
                'trial': n,
                'best_value': best_val,
                'elapsed_sec': round(elapsed, 1),
            })
            print(f"  [{n:>5d}/{n_trials}] best={best_val:.4f}  "
                  f"({elapsed:.1f}s, {n/elapsed:.1f} it/s)")

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False,
                   callbacks=[callback])

    elapsed = time.time() - t0

    # === 汇总结果 ===
    try:
        best_trial = study.best_trial
        best_value = best_trial.value
        best_number = best_trial.number
        best_params = best_trial.params
    except ValueError:
        best_value = 0.0
        best_number = -1
        best_params = {}

    # 统计非零 trial 数和分布
    values = [t.value for t in study.trials if t.value is not None]
    nonzero = [v for v in values if v > 0]
    unique_vals = len(set(values))

    result = {
        'sampler': sampler_name,
        'n_trials': n_trials,
        'elapsed_sec': round(elapsed, 1),
        'speed_it_s': round(n_trials / elapsed, 1),
        'best_value': round(best_value, 6),
        'best_trial_number': best_number,
        'best_params': {k: round(v, 4) for k, v in best_params.items()},
        'nonzero_count': len(nonzero),
        'nonzero_pct': round(len(nonzero) / len(values) * 100, 1) if values else 0,
        'unique_values': unique_vals,
        'unique_pct': round(unique_vals / len(values) * 100, 1) if values else 0,
        'value_stats': {
            'mean': round(float(np.mean(values)), 4) if values else 0,
            'std': round(float(np.std(values)), 4) if values else 0,
            'p50': round(float(np.median(values)), 4) if values else 0,
            'p90': round(float(np.percentile(values, 90)), 4) if values else 0,
            'p99': round(float(np.percentile(values, 99)), 4) if values else 0,
        },
        'curve': curve,
    }

    # 输出 JSON
    output_dir = PROJECT_ROOT / "outputs" / "benchmark"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sampler_name}.json"
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\n=== Result: {sampler_name} ===")
    print(f"  Best: {best_value:.4f} (trial #{best_number})")
    print(f"  Speed: {result['speed_it_s']} it/s")
    print(f"  Nonzero: {result['nonzero_pct']}%")
    print(f"  Unique: {result['unique_pct']}%")
    print(f"  Output: {output_path}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sampler", choices=["tpe", "multivariate_tpe", "qmc", "cmaes", "random"])
    parser.add_argument("--n-trials", type=int, default=3000)
    args = parser.parse_args()
    run_benchmark(args.sampler, args.n_trials)
