"""
阈值优化流水线

全因子直接搜索最优阈值组合：
Step 1a: 贪心 Beam Search（快速找到好起点）
Step 1b: Optuna TPE 单目标搜索（shrinkage score 精细优化）
Step 2: Bootstrap 验证 + 最优解选择

输入: factor_analysis_data DataFrame + all_factor.yaml (mode)
输出: filter.yaml 的模板列表
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from BreakoutStrategy.factor_registry import get_active_factors, get_factor, LABEL_COL
from BreakoutStrategy.mining.data_pipeline import prepare_raw_values
from BreakoutStrategy.mining.factor_diagnosis import diagnose_log_scale


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

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


def fast_evaluate(triggered, labels, min_count=10, top_k=5,
                  baseline_median=0.0, shrinkage_n0=50):
    """
    Bit-packed 向量化模板评估（~1ms），带 James-Stein 收缩。

    将 triggered 矩阵编码为整数 key（第 i 位 = 第 i 个因子），
    按 key 分组计算 count/median，对 top_k 模板应用收缩后返回评分。

    收缩公式: adjusted_i = w_i * median_i + (1 - w_i) * baseline_median
    其中 w_i = count_i / (count_i + shrinkage_n0)

    Args:
        triggered: (n_samples, n_factors) 二值触发矩阵
        labels: 样本标签数组
        min_count: 模板最小样本数
        top_k: 取前 k 个模板计算评分
        baseline_median: 全局基线 median，收缩目标
        shrinkage_n0: 收缩强度参数，0 表示不收缩

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
        return 0.0, n_templates, None

    top_stats = stats.iloc[:top_k]
    if shrinkage_n0 > 0:
        weights = top_stats['count'] / (top_stats['count'] + shrinkage_n0)
        adjusted = weights * top_stats['median'] + (1 - weights) * baseline_median
        shrinkage_score = float(adjusted.mean())
        best_idx = adjusted.idxmax()
        top_detail = {
            'median': float(top_stats.loc[best_idx, 'median']),
            'count': int(top_stats.loc[best_idx, 'count']),
            'adjusted': float(adjusted.loc[best_idx]),
        }
    else:
        shrinkage_score = float(top_stats['median'].mean())
        top_detail = {
            'median': float(top_stats.iloc[0]['median']),
            'count': int(top_stats.iloc[0]['count']),
            'adjusted': float(top_stats.iloc[0]['median']),
        }

    return shrinkage_score, n_templates, top_detail


def decode_templates(triggered, labels, factor_names, min_count=10):
    """
    从 triggered 矩阵解码完整模板列表（含名称）。

    Returns:
        list[dict]: 与 template_generator.generate_templates() 兼容的格式
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


def load_factor_modes(yaml_path):
    """从 factor_diag.yaml 读取各因子的 mode，返回反向因子集合。"""
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)
    qs = cfg.get('quality_scorer', {})

    negative = set()
    for fi in get_active_factors():
        entry = qs.get(fi.yaml_key, {})
        mode = entry.get('mode', 'gte')
        if mode == 'lte':
            negative.add(fi.key)
    return frozenset(negative)


# ---------------------------------------------------------------------------
# Step 1a: 贪心 Beam Search
# ---------------------------------------------------------------------------

def stage3a_greedy_beam_search(raw_values, labels, active_factors,
                               beam_width=3, min_samples=50,
                               n_candidates=20, negative_factors=frozenset()):
    """贪心 beam search：逐因子收缩子集，寻找高 median 路径。"""
    n_total = len(labels)

    candidates = {}
    for key in active_factors:
        raw = raw_values[key]
        if len(raw) < n_candidates:
            candidates[key] = np.unique(raw)
        else:
            percentiles = np.linspace(10, 90, n_candidates)
            candidates[key] = np.unique(np.percentile(raw, percentiles))

    beam = [{'thresholds': {}, 'mask': np.ones(n_total, dtype=bool),
             'median': float(np.median(labels)), 'count': n_total}]

    for depth in range(len(active_factors)):
        new_beam = []

        for path in beam:
            used = set(path['thresholds'].keys())
            current_mask = path['mask']

            best_for_path = []

            for factor in active_factors:
                if factor in used:
                    continue
                raw = raw_values[factor]

                for threshold in candidates.get(factor, []):
                    if factor in negative_factors:
                        sub_mask = current_mask & (raw <= threshold)
                    else:
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
                new_beam.append(path)
                continue

            best_for_path.sort(key=lambda x: x['median'], reverse=True)
            for cand in best_for_path[:beam_width]:
                new_thresholds = {**path['thresholds'], cand['factor']: cand['threshold']}
                if cand['factor'] in negative_factors:
                    new_mask = current_mask & (raw_values[cand['factor']] <= cand['threshold'])
                else:
                    new_mask = current_mask & (raw_values[cand['factor']] >= cand['threshold'])
                new_beam.append({
                    'thresholds': new_thresholds,
                    'mask': new_mask,
                    'median': cand['median'],
                    'count': cand['count'],
                })

        new_beam.sort(key=lambda x: (x['median'], x['count']), reverse=True)
        beam = new_beam[:beam_width]

        print(f"    Depth {depth+1}: beam top median={beam[0]['median']:.4f} "
              f"(n={beam[0]['count']}, factors={list(beam[0]['thresholds'].keys())})")

        if all(len(p['thresholds']) <= depth for p in beam):
            break

    results = []
    for p in beam:
        results.append({
            'thresholds': p['thresholds'],
            'factors_used': list(p['thresholds'].keys()),
            'median': p['median'],
            'count': p['count'],
        })

    return results


# ---------------------------------------------------------------------------
# Step 1b: Optuna TPE 单目标搜索 (shrinkage)
# ---------------------------------------------------------------------------

def stage3b_optuna_search(raw_values, labels, active_factors,
                          greedy_seeds, n_trials=100000, min_count=10,
                          top_k=1, negative_factors=frozenset(),
                          baseline_median=0.0, shrinkage_n0=20,
                          checkpoint_path=None, n_startup_trials=500,
                          checkpoint_interval=1000,
                          sampler="tpe",
                          enable_log=True,
                          quantile_margin=0.02,
                          overwrite_checkpoint=False):
    """
    Optuna TPE 单目标搜索（top-1 shrinkage score），以贪心结果做 warm start。

    使用纯内存存储 + pickle 检查点实现中断续跑。
    不设置 trigger rate 约束，让 TPE 自由探索，依赖 min_count 保护模板质量。

    Args:
        checkpoint_path: pickle 检查点文件路径。None 则不保存检查点。
        n_startup_trials: TPE 随机探索阶段的 trial 数，之后才开始建模。
        checkpoint_interval: 每多少 trials 保存一次检查点。
    """
    import optuna
    import pickle
    import os
    from pathlib import Path

    # 预处理：诊断 log scale + 构建统一搜索配置 (lo, hi, is_discrete, use_log)
    log_diagnosis = diagnose_log_scale(raw_values) if enable_log else {}

    bounds = {}
    for key in active_factors:
        fi = get_factor(key)
        raw = raw_values[key]
        lo = float(np.quantile(raw, quantile_margin))
        hi = float(np.quantile(raw, 1 - quantile_margin))
        if fi.is_discrete:
            lo, hi = int(lo), int(hi)
        use_log = log_diagnosis.get(key, {}).get('use_log', False) if enable_log else False
        bounds[key] = (lo, hi, fi.is_discrete, use_log)

    def objective(trial):
        thresholds = {}
        for key in active_factors:
            lo, hi, discrete, use_log = bounds[key]
            if lo >= hi:
                thresholds[key] = float(lo)
            elif discrete:
                thresholds[key] = float(trial.suggest_int(key, lo, hi, log=use_log))
            else:
                thresholds[key] = trial.suggest_float(key, lo, hi, log=use_log)

        triggered = build_triggered_matrix(raw_values, thresholds, active_factors,
                                           negative_factors)

        shrinkage_score, n_templates, top_detail = fast_evaluate(
            triggered, labels, min_count, top_k,
            baseline_median, shrinkage_n0
        )
        if top_detail:
            trial.set_user_attr('top_median', top_detail['median'])
            trial.set_user_attr('top_count', top_detail['count'])
            trial.set_user_attr('top_adjusted', top_detail['adjusted'])
        return shrinkage_score

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # 从 pickle 检查点恢复，或创建新的内存 study
    study = None
    if checkpoint_path:
        Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        if overwrite_checkpoint and Path(checkpoint_path).exists():
            Path(checkpoint_path).unlink()
            print(f"  Overwrite mode: deleted old checkpoint")
        elif Path(checkpoint_path).exists():
            with open(checkpoint_path, 'rb') as f:
                study = pickle.load(f)
            print(f"  Resumed from checkpoint: {len(study.trials)} trials")

    if study is None:
        if sampler == "multivariate_tpe":
            _sampler = optuna.samplers.TPESampler(
                seed=42, n_startup_trials=n_startup_trials,
                multivariate=True, group=True, n_ei_candidates=48,
            )
        else:  # "tpe"
            _sampler = optuna.samplers.TPESampler(
                seed=42, n_startup_trials=n_startup_trials,
            )
        study = optuna.create_study(direction="maximize", sampler=_sampler)

        # 仅在全新 study 时注入 warm start seeds
        for seed in greedy_seeds:
            params = {}
            for key in active_factors:
                lo, hi, discrete, _ = bounds[key]
                if key in seed['thresholds']:
                    val = seed['thresholds'][key]
                else:
                    raw = raw_values[key]
                    val = float(np.median(raw))
                params[key] = int(np.clip(val, lo, hi)) if discrete else float(np.clip(val, lo, hi))
            study.enqueue_trial(params)

    # 分批优化 + 周期性 pickle 检查点
    completed = len(study.trials)
    remaining = n_trials - completed
    if remaining <= 0:
        print(f"  Already completed {completed} trials (target: {n_trials}), skipping.")
        return study

    print(f"  Completed: {completed}, Remaining: {remaining}")
    print(f"  Total breakouts: {len(labels)}")

    n_total = len(labels)

    from tqdm import tqdm
    pbar = tqdm(total=remaining, initial=0, desc="TPE")

    try:
        prev_best_number = study.best_trial.number
    except ValueError:
        prev_best_number = -1

    def progress_callback(study, trial):
        nonlocal prev_best_number
        pbar.update(1)
        try:
            bt = study.best_trial
            best_val = bt.value
            med = bt.user_attrs.get('top_median')
            cnt = bt.user_attrs.get('top_count')
            if bt.number != prev_best_number:
                prev_best_number = bt.number
                entry = {
                    'trial_id': bt.number,
                    'value': round(float(best_val), 4),
                    'top_median': round(float(med), 4) if med is not None else None,
                    'top_count': cnt,
                }
                history = study.user_attrs.get('best_history', [])
                history.append(entry)
                study.set_user_attr('best_history', history)
                if checkpoint_path:
                    history_path = Path(checkpoint_path).parent / "best_trials.md"
                    with open(history_path, 'w') as hf:
                        hf.write("# Best Trial History\n\n")
                        hf.write("| # | Trial ID | Score | Median | Count |\n")
                        hf.write("|---|----------|-------|--------|-------|\n")
                        for idx, h in enumerate(history, 1):
                            m = f"{h['top_median']:.4f}" if h.get('top_median') is not None else "N/A"
                            c = str(h.get('top_count', 'N/A'))
                            hf.write(f"| {idx} | {h['trial_id']} | {h['value']:.4f} | {m} | {c} |\n")
            if med is not None:
                pbar.set_postfix_str(f"best={best_val:.4f} #={bt.number} top(med={med:.3f},n={cnt},r={cnt/n_total:.2%})")
            else:
                pbar.set_postfix_str(f"best={best_val:.4f} #={bt.number}")
        except ValueError:
            pass

    try:
        while remaining > 0:
            batch = min(checkpoint_interval, remaining)
            study.optimize(objective, n_trials=batch, show_progress_bar=False,
                           callbacks=[progress_callback])
            remaining -= batch

            # pickle 检查点：原子写入
            if checkpoint_path:
                tmp_path = checkpoint_path + '.tmp'
                with open(tmp_path, 'wb') as f:
                    pickle.dump(study, f)
                os.replace(tmp_path, checkpoint_path)
                print(f"  Checkpoint saved: {len(study.trials)} / {n_trials} trials")
    except KeyboardInterrupt:
        # 屏蔽后续 SIGINT，防止 cleanup 被二次中断（PyCharm 可能连发多次）
        import signal
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        pbar.close()
        n_done = len(study._storage.get_all_trials(study._study_id, deepcopy=False))
        print(f"\n  Early stop (Ctrl+C): {n_done} trials completed, generating results...")
        if checkpoint_path:
            tmp_path = checkpoint_path + '.tmp'
            with open(tmp_path, 'wb') as f:
                pickle.dump(study, f)
            os.replace(tmp_path, checkpoint_path)
            print(f"  Checkpoint saved: {n_done} trials")
        # 不恢复 SIG_DFL：后续 main() 中 study.trials 等操作仍需屏蔽
        return study

    pbar.close()
    return study


# ---------------------------------------------------------------------------
# Step 2: 验证 + 输出
# ---------------------------------------------------------------------------

def select_best_trial(study, raw_values, labels, active_factors,
                      min_count=10, bootstrap_n=1000, negative_factors=frozenset(),
                      top_k=5, min_viable_count=30):
    """从单目标 trials 中选择最佳解，用 bootstrap 评估 top_k 模板稳定性。"""
    all_trials = sorted(
        [t for t in study.trials if t.value is not None and t.value > 0],
        key=lambda t: t.value, reverse=True,
    )
    if not all_trials:
        raise ValueError("No valid trials found (all have value <= 0)")

    n_factors = len(active_factors)
    powers = (1 << np.arange(n_factors)).astype(np.int64)
    best = None
    best_score = -1

    for trial in all_trials[:10]:
        thresholds = {key: trial.params[key] for key in active_factors
                      if key in trial.params}
        triggered = build_triggered_matrix(raw_values, thresholds, active_factors,
                                           negative_factors)
        templates = decode_templates(triggered, labels, active_factors, min_count)

        if len(templates) < top_k:
            continue

        # count 门槛: top1 模板至少达到 min_viable_count
        if templates[0]['count'] < min_viable_count:
            continue

        top_k_raw_median = float(np.mean([t['median'] for t in templates[:top_k]]))

        # Bootstrap 覆盖所有 top_k 模板，取 min_stability
        combo_keys = triggered @ powers
        rng = np.random.default_rng(42)
        min_stability = 1.0
        top_k_ci = []

        for tmpl in templates[:top_k]:
            target_key = sum(1 << active_factors.index(f) for f in tmpl['factors'])
            member_labels = labels[combo_keys == target_key]
            tmpl_median = float(np.median(member_labels)) if len(member_labels) > 0 else 0.0

            if len(member_labels) >= 20:
                boot_medians = []
                for _ in range(bootstrap_n):
                    sample = rng.choice(member_labels, size=len(member_labels), replace=True)
                    boot_medians.append(float(np.median(sample)))
                ci_lo = np.percentile(boot_medians, 2.5)
                ci_hi = np.percentile(boot_medians, 97.5)
                ci_width = ci_hi - ci_lo
                stability = 1 - ci_width / tmpl_median if tmpl_median > 0 else 0
            else:
                stability = 0.0
                ci_lo = ci_hi = 0.0

            min_stability = min(min_stability, stability)
            top_k_ci.append((round(float(ci_lo), 4), round(float(ci_hi), 4)))

        score = trial.value

        if score > best_score:
            best_score = score
            best = {
                'thresholds': thresholds,
                'shrinkage_score': float(trial.value),
                'top_k_raw_median': top_k_raw_median,
                'min_stability': min_stability,
                'top_k_ci': top_k_ci,
                'templates': templates,
                'n_templates': len(templates),
            }

    if best is None:
        raise ValueError(
            "No viable solution found among top trials "
            f"(all produced < {top_k} templates or below count threshold). "
            "Consider relaxing constraints."
        )

    return best


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(input_csv, factor_yaml, output_yaml, report_name=None,
         optimizer_config: dict = None, checkpoint_path: str = None):
    from pathlib import Path
    from BreakoutStrategy.mining.template_generator import build_yaml_output, print_summary, write_yaml

    # 从 optimizer_config 读取搜索参数，提供默认值
    cfg = optimizer_config or {}
    beam_width = cfg.get('beam_width', 3)
    n_trials = cfg.get('n_trials', 50000)
    min_count = cfg.get('min_count', 30)
    shrinkage_k = cfg.get('shrinkage_k', 1)
    shrinkage_n0 = cfg.get('shrinkage_n0', 200)
    n_startup_trials = cfg.get('n_startup_trials', 1000)
    min_viable_count = cfg.get('min_viable_count', 30)
    bootstrap_n = cfg.get('bootstrap_n', 1000)
    sampler = cfg.get('sampler', 'tpe')
    enable_log = cfg.get('enable_log', True)
    quantile_margin = cfg.get('quantile_margin', 0.02)
    overwrite_checkpoint = cfg.get('overwrite_checkpoint', False)

    # checkpoint_path 默认值
    if checkpoint_path is None:
        project_root = Path(input_csv).resolve().parent.parent.parent
        checkpoint_path = str(project_root / "outputs" / "optuna" / f"tpe_{shrinkage_n0}_single.pkl")

    # === 加载数据 ===
    print(f"Loading: {input_csv}")
    df = pd.read_csv(input_csv)
    df = df.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    print(f"  Rows: {len(df)}")

    # === 全因子列表（从 FACTOR_REGISTRY 获取） ===
    all_factors = [f.key for f in get_active_factors()]
    print(f"\n=== Factor Setup ===")
    print(f"  All factors ({len(all_factors)}): {all_factors}")

    raw_values = prepare_raw_values(df)
    labels = df[LABEL_COL].values
    baseline_median = float(np.median(labels))
    negative_factors = load_factor_modes(factor_yaml)
    print(f"  Negative factors (lte mode): {sorted(negative_factors) if negative_factors else 'none'}")
    print(f"  Baseline median: {baseline_median:.4f}")

    # === Log scale 诊断 ===
    if enable_log:
        log_diag = diagnose_log_scale(raw_values)
        log_factors = [k for k, v in log_diag.items() if v.get('use_log')]
        print(f"\n  Log-scale factors: {log_factors}")
        for k, v in log_diag.items():
            if not get_factor(k).is_discrete:
                print(f"    {k:<10s}: log={str(v['use_log']):<5s}  rule={v['rule']:<10s}  "
                      f"{', '.join(f'{mk}={mv}' for mk, mv in v.items() if mk not in ('use_log', 'rule'))}")
    else:
        print(f"\n  Log-scale: DISABLED (enable_log=False)")

    # === Step 1a: 贪心 Beam Search ===
    print(f"\n=== Step 1a: Greedy Beam Search ===")
    greedy_results = stage3a_greedy_beam_search(
        raw_values, labels, all_factors,
        beam_width=beam_width, min_samples=min_count*5,
        negative_factors=negative_factors,
    )

    print(f"\n  Greedy results ({len(greedy_results)} paths):")
    for i, r in enumerate(greedy_results):
        print(f"    Path {i+1}: median={r['median']:.4f}  count={r['count']}  "
              f"factors={r['factors_used']}  thresholds={r['thresholds']}")

    # === Step 1b: Optuna TPE top-1 shrinkage（无 trigger rate 约束）===
    print(f"\n=== Step 1b: Optuna TPE Top-1 Shrinkage ({n_trials} trials, "
          f"n0={shrinkage_n0}, startup={n_startup_trials}) ===")
    print(f"  Checkpoint: {checkpoint_path}")
    study = stage3b_optuna_search(
        raw_values, labels, all_factors,
        greedy_seeds=greedy_results,
        n_trials=n_trials, min_count=min_count,
        top_k=shrinkage_k,
        negative_factors=negative_factors,
        baseline_median=baseline_median, shrinkage_n0=shrinkage_n0,
        checkpoint_path=checkpoint_path, n_startup_trials=n_startup_trials,
        sampler=sampler, enable_log=enable_log,
        quantile_margin=quantile_margin,
        overwrite_checkpoint=overwrite_checkpoint,
    )

    top_trials = sorted(
        [t for t in study.trials if t.value is not None and t.value > 0],
        key=lambda t: t.value, reverse=True,
    )
    print(f"\n  Valid trials: {len(top_trials)} / {len(study.trials)}")
    print(f"  {'#':>3s} {'shrinkage_score':>16s}")
    for i, t in enumerate(top_trials[:10]):
        print(f"  {i+1:3d} {t.value:16.4f}")

    # === Step 2: 验证 + 输出 ===
    print(f"\n=== Step 2: Validation & Output ===")
    best = select_best_trial(
        study, raw_values, labels, all_factors,
        min_count=min_count, bootstrap_n=bootstrap_n,
        negative_factors=negative_factors,
        top_k=shrinkage_k, min_viable_count=min_viable_count,
    )

    print(f"  Best solution:")
    print(f"    Shrinkage score:  {best['shrinkage_score']:.4f}")
    print(f"    Top-1 raw median: {best['top_k_raw_median']:.4f}")
    print(f"    Stability:        {best['min_stability']:.3f}")
    print(f"    Top-1 CI:         {best['top_k_ci']}")
    print(f"    Templates:        {best['n_templates']}")
    print(f"    Thresholds:")
    for key, t in best['thresholds'].items():
        if key in negative_factors:
            rate = (raw_values[key] <= t).mean()
            print(f"      {key:<10s}: <= {t:.4f}  (trigger rate: {rate:.1%})")
        else:
            rate = (raw_values[key] >= t).mean()
            print(f"      {key:<10s}: >= {t:.4f}  (trigger rate: {rate:.1%})")

    if output_yaml is not None:
        templates = best['templates'][:10]

        yaml_data = build_yaml_output(templates, df, input_csv, min_count,
                                      generator='BreakoutStrategy.mining.threshold_optimizer')

        yaml_data['_meta']['optimization'] = {
            'method': 'greedy_beam_search + optuna_tpe_top1_shrinkage',
            'n_trials': len(study.trials),
            'n_startup_trials': n_startup_trials,
            'active_factors': all_factors,
            'thresholds': {k: round(float(v), 4) for k, v in best['thresholds'].items()},
            'negative_factors': sorted(negative_factors),
            'shrinkage_score': round(float(best['shrinkage_score']), 4),
            'shrinkage_n0': shrinkage_n0,
            'shrinkage_k': shrinkage_k,
            'baseline_median': round(baseline_median, 4),
            'min_stability': round(float(best['min_stability']), 3),
        }

        # 嵌入扫描参数快照（自包含，不依赖外部文件）
        with open(factor_yaml, 'r', encoding='utf-8') as f:
            all_params = yaml.safe_load(f)
        scan_params = {}
        for section in ('breakout_detector', 'general_feature', 'quality_scorer'):
            if section in all_params:
                scan_params[section] = all_params[section]
        # 排除运行时参数
        scan_params.get('breakout_detector', {}).pop('cache_dir', None)
        scan_params.get('breakout_detector', {}).pop('use_cache', None)
        yaml_data['scan_params'] = scan_params
        yaml_data['_meta']['version'] = 4

        write_yaml(yaml_data, output_yaml,
                   header_comment="# configs/params/filter.yaml\n"
                                  "# 由 BreakoutStrategy.mining.threshold_optimizer 自动生成\n\n")
        print(f"\n  Output: {output_yaml}")

        print_summary(yaml_data)

    if report_name is not None:
        from BreakoutStrategy.mining.data_pipeline import apply_binary_levels
        from BreakoutStrategy.mining.stats_analysis import run_analysis
        from BreakoutStrategy.mining.report_generator import generate_report
        apply_binary_levels(df, best['thresholds'], negative_factors)
        results = run_analysis(df, thresholds=best['thresholds'],
                               negative_factors=negative_factors)
        generate_report(results, output_path=report_name)
        print(f"  Report: {report_name}")


if __name__ == "__main__":
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    main(
        input_csv=str(PROJECT_ROOT / "outputs/analysis/factor_analysis_data.csv"),
        factor_yaml=str(PROJECT_ROOT / "configs/params/all_factor.yaml"),
        output_yaml=str(PROJECT_ROOT / "configs/params/filter.yaml"),
    )
