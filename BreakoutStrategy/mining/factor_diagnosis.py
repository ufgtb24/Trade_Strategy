"""
因子诊断

1. diagnose_direction: Spearman 相关性 → 因子触发方向 (gte/lte)
2. diagnose_log_scale: 分布形态 → TPE 是否需要对数空间采样

不依赖 level/threshold 预设，直接在原始数据空间操作。
"""

from __future__ import annotations

import numpy as np
import yaml
from scipy.stats import spearmanr, shapiro, skew

from BreakoutStrategy.factor_registry import get_active_factors, get_factor, LABEL_COL
from BreakoutStrategy.mining.data_pipeline import prepare_raw_values


def diagnose_direction(raw_values: dict[str, np.ndarray],
                       labels: np.ndarray,
                       weak_threshold: float = 0.015) -> dict[str, dict]:
    """
    基于 raw value Spearman 诊断各因子方向。

    Args:
        raw_values: {key: 原始值数组}，由 prepare_raw_values() 获得
        labels: label 数组
        weak_threshold: 弱相关阈值

    Returns:
        {key: {direction, mode, spearman_r, spearman_p}}
    """
    results = {}
    for key, raw in raw_values.items():
        # mining_mode 覆盖：跳过 Spearman 决策，仍计算用于日志
        try:
            fi = get_factor(key)
        except KeyError:
            fi = None
        if fi is not None and fi.mining_mode is not None:
            valid_mask = ~np.isnan(raw) & ~np.isnan(labels)
            valid_raw = raw[valid_mask]
            valid_labels = labels[valid_mask]
            r, p = (None, None)
            if len(valid_raw) > 10:
                r, p = spearmanr(valid_raw, valid_labels)
                r, p = round(float(r), 4), round(float(p), 6)
            results[key] = {
                'direction': 'override',
                'mode': fi.mining_mode,
                'spearman_r': r,
                'spearman_p': p,
            }
            continue

        valid_mask = ~np.isnan(raw) & ~np.isnan(labels)
        valid_raw = raw[valid_mask]
        valid_labels = labels[valid_mask]

        if len(valid_raw) <= 10:
            results[key] = {
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

        results[key] = {
            'direction': direction,
            'mode': mode,
            'spearman_r': round(float(r), 4),
            'spearman_p': round(float(p), 6),
        }
    return results


def diagnose_log_scale(raw_values: dict[str, np.ndarray],
                       range_threshold: float = 3.0,
                       sw_improve_threshold: float = 0.15,
                       log_skew_threshold: float = -0.55) -> dict[str, dict]:
    """
    基于分布形态判断各因子 TPE 搜索是否需要对数空间采样。

    三级过滤规则：
    R1: 存在任何非正值 (<=0)              → False (log 要求全正值)
    R2: P90/P10 < range_threshold         → False (值域太窄, log 无意义)
    R3: SW_improve >= sw_improve_threshold
        AND log_skew > log_skew_threshold → True  (log 改善正态性且不过度压缩)
    默认阈值 -0.55 处于经验安全区间 [-1.2, -0.4] 中部（基于当前因子集验证）。
    默认                                   → False

    其中 SW_improve = SW(log(x)) - SW(x)，衡量 log 变换对正态性的改善。
    log_skew 是 log 变换后的偏度，过度负偏说明 log 压缩过头。

    Args:
        raw_values: {key: 原始值数组}
        range_threshold: R2 P90/P10 最小比值
        sw_improve_threshold: R3 Shapiro-Wilk 改善量阈值
        log_skew_threshold: R3 log 偏度下限

    Returns:
        {key: {use_log, rule, neg_pct, range_ratio, sw_improve, log_skew}}
    """
    results = {}
    for key, raw in raw_values.items():
        valid = raw[~np.isnan(raw)]
        n_total = len(valid)
        if n_total == 0:
            results[key] = {'use_log': False, 'rule': 'no_data'}
            continue

        # R1: 存在任何非正值 → log 不兼容
        has_non_pos = bool(np.any(valid <= 0))
        if has_non_pos:
            non_pos_pct = float((valid <= 0).sum() / n_total)
            results[key] = {
                'use_log': False, 'rule': 'R1_non_pos',
                'non_pos_pct': round(non_pos_pct, 3),
            }
            continue

        # 只取正值用于后续分析（与 TPE bounds 计算一致）
        pos = valid[valid > 0]
        if len(pos) < 50:
            results[key] = {'use_log': False, 'rule': 'insufficient_pos'}
            continue

        p10 = float(np.quantile(pos, 0.10))
        p90 = float(np.quantile(pos, 0.90))
        range_ratio = p90 / p10 if p10 > 0 else float('inf')

        # R2: 值域太窄
        if range_ratio < range_threshold:
            results[key] = {
                'use_log': False, 'rule': 'R2_narrow',
                'range_ratio': round(range_ratio, 2),
            }
            continue

        # R3: Shapiro-Wilk 改善 + log 偏度
        # 采样 5000 以保证 shapiro 计算速度
        rng = np.random.default_rng(42)
        sample = rng.choice(pos, size=min(5000, len(pos)), replace=False)

        sw_original = shapiro(sample).statistic
        sw_log = shapiro(np.log(sample)).statistic
        sw_improve = float(sw_log - sw_original)
        log_skew_val = float(skew(np.log(sample)))

        use_log = sw_improve >= sw_improve_threshold and log_skew_val > log_skew_threshold

        results[key] = {
            'use_log': use_log,
            'rule': 'R3_log' if use_log else 'R3_fail',
            'range_ratio': round(range_ratio, 2),
            'sw_improve': round(sw_improve, 3),
            'log_skew': round(log_skew_val, 2),
        }

    return results


def load_current_modes(yaml_path: str) -> dict[str, str]:
    """从 all_factor.yaml 读取当前各因子的 mode 配置。"""
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)
    qs = cfg.get('quality_scorer', {})

    modes = {}
    for fi in get_active_factors():
        entry = qs.get(fi.yaml_key, {})
        modes[fi.key] = entry.get('mode', 'gte')
    return modes


def apply_corrections(yaml_path: str, corrections: dict[str, str]):
    """将方向修正写入 all_factor.yaml。"""
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)
    qs = cfg['quality_scorer']

    # 构建 key → yaml_key 映射
    key_to_yaml = {fi.key: fi.yaml_key for fi in get_active_factors()}

    for key, new_mode in corrections.items():
        yaml_key = key_to_yaml[key]
        # 为 REGISTRY 中有但 YAML 中无的因子合成默认条目
        if yaml_key not in qs:
            fi = get_factor(key)
            qs[yaml_key] = {
                'enabled': True,
                'thresholds': list(fi.default_thresholds),
                'values': list(fi.default_values),
                **{sp.yaml_name: sp.default for sp in fi.sub_params},
            }
        qs[yaml_key]['mode'] = new_mode

    with open(yaml_path, 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(input_csv, yaml_path, auto_apply):
    from pathlib import Path

    import pandas as pd

    print(f"Loading: {input_csv}")
    df = pd.read_csv(input_csv)
    df = df.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    print(f"  Rows: {len(df)}")

    raw_values = prepare_raw_values(df)
    labels = df[LABEL_COL].values
    diagnosis = diagnose_direction(raw_values, labels)
    current_modes = load_current_modes(yaml_path)

    all_factors = get_active_factors()
    print(f"\n  {'Factor':<10s} {'Spearman':>10s} {'Direction':>10s} {'Recommend':>10s} {'Current':>10s} {'Action':>10s}")
    print("  " + "-" * 63)

    corrections = {}
    for fi in all_factors:
        key = fi.key
        d = diagnosis.get(key, {})
        r = d.get('spearman_r')
        r_str = f"{r:+.4f}" if r is not None else "N/A"
        direction = d.get('direction', '?')
        recommended = d.get('mode', 'gte')
        current = current_modes.get(key, 'gte')
        action = "FLIP" if recommended != current else "OK"
        if d.get('direction') == 'override':
            action = "OVERRIDE"
        if recommended != current:
            corrections[key] = recommended
        print(f"  {key:<10s} {r_str:>10s} {direction:>10s} {recommended:>10s} {current:>10s} {action:>10s}")

    if corrections:
        print(f"\n  Corrections needed: {len(corrections)}")
        for key, mode in corrections.items():
            print(f"    {key}: {current_modes[key]} -> {mode}")
        if auto_apply:
            apply_corrections(yaml_path, corrections)
            print(f"\n  Applied to {yaml_path}")
        else:
            print(f"\n  Set BONUS_AUTO_APPLY=1 to auto-apply.")
    else:
        print(f"\n  All factor directions are correct.")


if __name__ == "__main__":
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    main(
        input_csv=str(PROJECT_ROOT / "outputs/analysis/factor_analysis_data.csv"),
        yaml_path=str(PROJECT_ROOT / "configs/params/all_factor.yaml"),
        auto_apply=False,
    )
