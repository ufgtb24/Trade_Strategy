"""
因子诊断

1. diagnose_direction: Spearman 相关性 → 因子触发方向 (gte/lte)
2. diagnose_log_scale: 分布形态 → TPE 是否需要对数空间采样

不依赖 level/threshold 预设，直接在原始数据空间操作。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml
from scipy.stats import spearmanr, shapiro, skew

from BreakoutStrategy.factor_registry import (
    FACTOR_REGISTRY, INACTIVE_FACTORS,
    get_active_factors, get_factor, LABEL_COL,
)
from BreakoutStrategy.mining.data_pipeline import prepare_raw_values


def detect_non_monotonicity(raw: np.ndarray, labels: np.ndarray,
                            n_segments: int = 3,
                            flip_threshold: float = 0.02) -> dict:
    """
    分段 Spearman 非单调性检测。

    按因子值的分位数切分为若干段，各段分别计算 Spearman 相关系数，
    检测段间符号是否翻转。若翻转则判定为非单调。

    Args:
        raw: 因子原始值数组
        labels: label 数组
        n_segments: 分段数（默认三分位）
        flip_threshold: 忽略绝对值低于此阈值的段（噪声过滤）

    Returns:
        {is_non_monotonic, segments: [{quantile_range, spearman_r, n_samples}]}
    """
    quantiles = np.linspace(0, 1, n_segments + 1)
    boundaries = np.quantile(raw, quantiles)

    segment_results = []
    for i in range(n_segments):
        if i == n_segments - 1:
            mask = (raw >= boundaries[i]) & (raw <= boundaries[i + 1])
        else:
            mask = (raw >= boundaries[i]) & (raw < boundaries[i + 1])
        seg_raw, seg_labels = raw[mask], labels[mask]
        if len(seg_raw) > 10:
            r, p = spearmanr(seg_raw, seg_labels)
            segment_results.append({
                'quantile_range': (round(float(quantiles[i]), 2),
                                   round(float(quantiles[i + 1]), 2)),
                'spearman_r': round(float(r), 4),
                'spearman_p': round(float(p), 6),
                'n_samples': int(len(seg_raw)),
            })

    # 检测符号翻转（忽略绝对值过小的段）
    signs = [np.sign(s['spearman_r']) for s in segment_results
             if abs(s['spearman_r']) > flip_threshold]
    is_non_monotonic = len(set(signs)) > 1

    return {'is_non_monotonic': is_non_monotonic, 'segments': segment_results}


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
            # 全局 Spearman 弱 → 可能是非单调，追加分段检测
            nm = detect_non_monotonicity(valid_raw, valid_labels)
            if nm['is_non_monotonic']:
                # 取各段中绝对值最大的 Spearman 方向作为主导 mode
                strongest = max(nm['segments'], key=lambda s: abs(s['spearman_r']))
                mode = 'lte' if strongest['spearman_r'] < 0 else 'gte'
                direction = 'non_monotonic'
            else:
                direction, mode = 'weak', 'gte'
        elif r > 0:
            direction, mode = 'positive', 'gte'
        else:
            direction, mode = 'negative', 'lte'

        result_entry = {
            'direction': direction,
            'mode': mode,
            'spearman_r': round(float(r), 4),
            'spearman_p': round(float(p), 6),
        }
        if direction == 'non_monotonic':
            result_entry['segments'] = nm['segments']
        results[key] = result_entry
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


def write_diagnosed_yaml(source_yaml: str, output_yaml: str, modes: dict[str, str],
                         audit_info: dict[str, dict] | None = None):
    """读取 source_yaml 结构，写入所有因子的诊断方向及审计字段，输出 output_yaml。

    Args:
        source_yaml: 结构模板 yaml 路径
        output_yaml: 输出路径
        modes: {factor_key: 'gte'|'lte'}
        audit_info: 可选。{factor_key: {valid_count, valid_ratio, buffer}}。
                   per-factor gate 下让用户看到每因子的统计基础。
    """
    with open(source_yaml) as f:
        cfg = yaml.safe_load(f)
    qs = cfg['quality_scorer']

    key_to_yaml = {fi.key: fi.yaml_key for fi in get_active_factors()}

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
        # per-factor gate: 审计字段（让用户直接看到每因子的统计基础）
        if audit_info and key in audit_info:
            info = audit_info[key]
            if 'valid_count' in info:
                qs[yaml_key]['valid_count'] = info['valid_count']
            if 'valid_ratio' in info:
                qs[yaml_key]['valid_ratio'] = round(info['valid_ratio'], 4)
            if 'buffer' in info:
                qs[yaml_key]['buffer'] = info['buffer']

    # 移除非活跃因子条目
    inactive_yaml_keys = {f.yaml_key for f in FACTOR_REGISTRY if f.key in INACTIVE_FACTORS}
    for ik in inactive_yaml_keys:
        qs.pop(ik, None)

    Path(output_yaml).parent.mkdir(parents=True, exist_ok=True)
    with open(output_yaml, 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(input_csv, yaml_path, output_yaml, auto_apply):
    """
    诊断所有因子方向并全量写入 output_yaml。

    Args:
        input_csv: 分析数据 CSV
        yaml_path: 输入的 all_factor.yaml（结构模板，只读）
        output_yaml: 输出的 factor_diag.yaml（包含所有因子的 mode）
        auto_apply: 是否写入 output_yaml
    """
    import pandas as pd

    print(f"Loading: {input_csv}")
    df = pd.read_csv(input_csv)
    df = df.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    print(f"  Rows: {len(df)}")

    raw_values = prepare_raw_values(df)
    labels = df[LABEL_COL].values
    diagnosis = diagnose_direction(raw_values, labels)

    all_factors = get_active_factors()
    print(f"\n  {'Factor':<10s} {'Spearman':>10s} {'Direction':>10s} {'Mode':>6s}")
    print("  " + "-" * 40)

    diagnosed_modes = {}
    for fi in all_factors:
        key = fi.key
        d = diagnosis.get(key, {})
        r = d.get('spearman_r')
        r_str = f"{r:+.4f}" if r is not None else "N/A"
        direction = d.get('direction', '?')
        mode = d.get('mode', 'gte')
        diagnosed_modes[key] = mode
        print(f"  {key:<10s} {r_str:>10s} {direction:>10s} {mode:>6s}")

    # 非单调因子分段详情
    nm_factors = {k: v for k, v in diagnosis.items() if v.get('direction') == 'non_monotonic'}
    if nm_factors:
        print(f"\n  Non-monotonic factors detected: {len(nm_factors)}")
        for key, d in nm_factors.items():
            print(f"    {key} (global r={d['spearman_r']:+.4f}):")
            for seg in d['segments']:
                qr = seg['quantile_range']
                print(f"      Q{qr[0]:.0%}-{qr[1]:.0%}: r={seg['spearman_r']:+.4f}  "
                      f"(n={seg['n_samples']}, p={seg['spearman_p']:.4f})")

    # per-factor gate: 为每因子计算审计字段（valid_count/valid_ratio/buffer）
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

    if auto_apply:
        write_diagnosed_yaml(yaml_path, output_yaml, diagnosed_modes,
                             audit_info=audit_info)
        print(f"\n  Diagnosed {len(diagnosed_modes)} factors. Written to {output_yaml}")
    else:
        print(f"\n  Diagnosed {len(diagnosed_modes)} factors. (dry run)")


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    main(
        input_csv=str(PROJECT_ROOT / "outputs/analysis/factor_analysis_data.csv"),
        yaml_path=str(PROJECT_ROOT / "configs/params/all_factor.yaml"),
        output_yaml=str(PROJECT_ROOT / "configs/params/all_factor.yaml"),  # 独立运行时原地修改
        auto_apply=False,
    )
