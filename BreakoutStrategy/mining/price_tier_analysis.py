"""
价格分层分析工具

对 scan_results JSON 进行价格维度的统计分析，输出：
1. Label 按价格区间的分布统计
2. 因子在各价格区间的分布差异（Kruskal-Wallis H / Spearman ρ）
3. 自然断点检测（Mann-Whitney U）
4. 分层方案对比（CV / 样本均衡 / 分离度 / Eta²）
5. 幂律衰减模型拟合

用法：
    python -m BreakoutStrategy.mining.price_tier_analysis
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats


# ── 常量 ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 扫描 JSON 中直接可用的因子字段（key 名）
RAW_FACTOR_COLS = [
    "volume",
    "day_str",
    "pbm",
    "pk_mom",
    "annual_volatility",
    "streak",
    "drought",
    "overshoot",
    "intraday_change_pct",
    "gap_up_pct",
    "num_peaks_broken",
]

# 阻力属性因子（key 名）
RESISTANCE_FACTOR_COLS = [
    "age",
    "test",
    "peak_vol",
    "height",
]

ALL_FACTOR_COLS = RAW_FACTOR_COLS + RESISTANCE_FACTOR_COLS


# ── 数据加载 ──────────────────────────────────────────────────────────

def load_breakouts(json_path: str | Path) -> pd.DataFrame:
    """
    从 scan_results JSON 加载所有 breakout 记录为 DataFrame。

    自动检测 label 字段名（label_10_40 / label_5_40 等）。
    """
    with open(json_path) as f:
        data = json.load(f)

    rows = []
    label_key = None

    for stock in data["results"]:
        symbol = stock["symbol"]

        for bo in stock.get("breakouts", []):
            # 自动检测 label key
            labels_dict = bo.get("labels", {})
            if label_key is None and labels_dict:
                label_key = list(labels_dict.keys())[0]

            label_val = labels_dict.get(label_key) if label_key else None

            row = {
                "symbol": symbol,
                "date": bo["date"],
                "price": bo["price"],
                "label": label_val,
                "age": bo.get("age") or 0,
                "test": bo.get("test") or 0,
                "peak_vol": bo.get("peak_vol") or 0.0,
                "height": bo.get("height") or 0.0,
            }
            # 添加原始因子
            for col in RAW_FACTOR_COLS:
                row[col] = bo.get(col)

            rows.append(row)

    df = pd.DataFrame(rows)
    print(f"[加载] {len(df)} breakouts, label 字段: {label_key}")
    print(f"[加载] 价格范围: ${df['price'].min():.2f} ~ ${df['price'].max():.2f}")
    return df, label_key


# ── 1. Label 分布统计 ──────────────────────────────────────────────────

def label_distribution(df: pd.DataFrame, bins: list[float] | None = None) -> pd.DataFrame:
    """
    按价格区间统计 label 分布。

    Args:
        df: 包含 price 和 label 列的 DataFrame
        bins: 价格区间边界列表，默认 $1 粒度
    """
    if bins is None:
        bins = list(range(1, int(df["price"].max()) + 2))

    valid = df.dropna(subset=["label"])
    results = []
    for i in range(len(bins) - 1):
        lo, hi = bins[i], bins[i + 1]
        mask = (valid["price"] >= lo) & (valid["price"] < hi)
        sub = valid.loc[mask, "label"]
        if len(sub) == 0:
            continue
        results.append({
            "bin": f"${lo}-{hi}",
            "lo": lo,
            "hi": hi,
            "n": len(sub),
            "median": sub.median(),
            "mean": sub.mean(),
            "std": sub.std(),
            "q25": sub.quantile(0.25),
            "q75": sub.quantile(0.75),
            "pct_gt10": (sub > 0.1).mean() * 100,
            "pct_gt20": (sub > 0.2).mean() * 100,
        })
    return pd.DataFrame(results)


# ── 2. 自然断点检测 ──────────────────────────────────────────────────

def detect_breakpoints(df: pd.DataFrame, test_points: list[float] | None = None) -> pd.DataFrame:
    """
    Mann-Whitney U 检验检测价格断点。

    两种模式：
    1. test_points=None: 相邻 $1 区间两两比较，找效应量最大的跳变
    2. test_points=[3,4,5,...]: 以每个点为分割，比较 <point vs >=point 的 label 分布

    返回按效应量降序排列的结果。
    """
    valid = df.dropna(subset=["label"])
    results = []

    if test_points is None:
        # 相邻 $1 区间对比
        max_price = int(valid["price"].max())
        for p in range(1, max_price):
            g1 = valid.loc[(valid["price"] >= p) & (valid["price"] < p + 1), "label"]
            g2 = valid.loc[(valid["price"] >= p + 1) & (valid["price"] < p + 2), "label"]
            if len(g1) < 30 or len(g2) < 30:
                continue
            u_stat, p_val = sp_stats.mannwhitneyu(g1, g2, alternative="two-sided")
            # rank-biserial r = 1 - 2U/(n1*n2)
            r_rb = 1 - 2 * u_stat / (len(g1) * len(g2))
            results.append({
                "boundary": f"${p}-{p+1} → ${p+1}-{p+2}",
                "price": p + 1,
                "r_rb": r_rb,
                "abs_r_rb": abs(r_rb),
                "p_value": p_val,
                "median_left": g1.median(),
                "median_right": g2.median(),
                "delta": g2.median() - g1.median(),
                "n_left": len(g1),
                "n_right": len(g2),
            })
    else:
        # 分割点对比
        for pt in test_points:
            g_low = valid.loc[valid["price"] < pt, "label"]
            g_high = valid.loc[valid["price"] >= pt, "label"]
            if len(g_low) < 30 or len(g_high) < 30:
                continue
            u_stat, p_val = sp_stats.mannwhitneyu(g_low, g_high, alternative="two-sided")
            r_rb = 1 - 2 * u_stat / (len(g_low) * len(g_high))
            results.append({
                "split_point": f"${pt}",
                "price": pt,
                "r_rb": r_rb,
                "abs_r_rb": abs(r_rb),
                "p_value": p_val,
                "median_low": g_low.median(),
                "median_high": g_high.median(),
                "n_low": len(g_low),
                "n_high": len(g_high),
            })

    result_df = pd.DataFrame(results)
    if len(result_df) > 0:
        result_df = result_df.sort_values("abs_r_rb", ascending=False).reset_index(drop=True)
    return result_df


# ── 3. 因子分布分析 ──────────────────────────────────────────────────

def factor_distribution(
    df: pd.DataFrame,
    price_bins: list[tuple[float, float]] | None = None,
) -> dict:
    """
    分析因子在不同价格区间的分布。

    返回:
        {
            'by_bin': DataFrame (factor, bin, mean, median, std),
            'kruskal': DataFrame (factor, H, p_value, significant),
            'spearman_vs_price': DataFrame (factor, rho, p_value),
        }
    """
    if price_bins is None:
        price_bins = [(1, 5), (5, 10), (10, 15), (15, 20)]

    # 确定可用因子（排除全 None 的）
    available = [c for c in ALL_FACTOR_COLS if c in df.columns and df[c].notna().sum() > 100]

    # 按区间统计
    by_bin_rows = []
    for col in available:
        for lo, hi in price_bins:
            sub = df.loc[(df["price"] >= lo) & (df["price"] < hi), col].dropna()
            if len(sub) == 0:
                continue
            by_bin_rows.append({
                "factor": col,
                "bin": f"${lo}-{hi}",
                "n": len(sub),
                "mean": sub.mean(),
                "median": sub.median(),
                "std": sub.std(),
            })

    # Kruskal-Wallis H 检验
    kruskal_rows = []
    for col in available:
        groups = []
        for lo, hi in price_bins:
            g = df.loc[(df["price"] >= lo) & (df["price"] < hi), col].dropna()
            if len(g) > 0:
                groups.append(g.values)
        if len(groups) >= 2:
            h_stat, p_val = sp_stats.kruskal(*groups)
            kruskal_rows.append({
                "factor": col,
                "H_stat": h_stat,
                "p_value": p_val,
                "significant": "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < 0.05 else "ns")),
            })

    # Spearman vs price
    spearman_rows = []
    for col in available:
        valid = df[["price", col]].dropna()
        if len(valid) > 2:
            rho, p_val = sp_stats.spearmanr(valid["price"], valid[col])
            spearman_rows.append({
                "factor": col,
                "rho": rho,
                "abs_rho": abs(rho),
                "p_value": p_val,
            })

    return {
        "by_bin": pd.DataFrame(by_bin_rows),
        "kruskal": pd.DataFrame(kruskal_rows).sort_values("H_stat", ascending=False).reset_index(drop=True),
        "spearman_vs_price": pd.DataFrame(spearman_rows).sort_values("abs_rho", ascending=False).reset_index(drop=True),
    }


def factor_label_correlation(
    df: pd.DataFrame,
    price_range: tuple[float, float] | None = None,
) -> pd.DataFrame:
    """
    计算因子对 label 的 Spearman 相关性，可限定价格区间。

    Args:
        price_range: (min, max) 价格范围，None 表示全量
    """
    sub = df.dropna(subset=["label"])
    if price_range:
        sub = sub[(sub["price"] >= price_range[0]) & (sub["price"] < price_range[1])]

    available = [c for c in ALL_FACTOR_COLS if c in sub.columns and sub[c].notna().sum() > 100]
    rows = []
    for col in available:
        valid = sub[["label", col]].dropna()
        if len(valid) > 2:
            rho, p_val = sp_stats.spearmanr(valid["label"], valid[col])
            rows.append({
                "factor": col,
                "rho": rho,
                "abs_rho": abs(rho),
                "p_value": p_val,
                "significant": "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < 0.05 else "ns")),
                "n": len(valid),
            })

    return pd.DataFrame(rows).sort_values("abs_rho", ascending=False).reset_index(drop=True)


# ── 4. 分层方案对比 ──────────────────────────────────────────────────

def _tier_stats(labels: np.ndarray) -> dict:
    """单个 tier 的统计量"""
    return {
        "n": len(labels),
        "median": np.median(labels),
        "mean": np.mean(labels),
        "std": np.std(labels),
        "cv": np.std(labels) / np.mean(labels) if np.mean(labels) > 0 else np.inf,
    }


def compare_tier_schemes(
    df: pd.DataFrame,
    schemes: dict[str, list[tuple[float, float]]] | None = None,
) -> pd.DataFrame:
    """
    对比多种分层方案的层内同质性、样本均衡性、分离度。

    Args:
        schemes: {方案名: [(lo1,hi1), (lo2,hi2), ...]}
                 None 使用默认候选方案

    指标说明:
        - avg_cv: 各 tier 的 CV 加权平均（越低越好）
        - balance: min_n / max_n（越接近 1 越好）
        - avg_sep: 相邻 tier median 差的均值（越大越好）
        - min_sep: 相邻 tier median 差的最小值（越大越好）
        - eta2: ANOVA 效应量 SS_between / SS_total（越大越好）
    """
    valid = df.dropna(subset=["label"])
    max_price = valid["price"].max()

    if schemes is None:
        schemes = {
            "linear_3 ($1-5/$5-10/$10-20)": [(1, 5), (5, 10), (10, 20)],
            "natural ($1-4/$4-10/$10-20)": [(1, 4), (4, 10), (10, 20)],
            "practical_log ($1-3/$3-10/$10-20)": [(1, 3), (3, 10), (10, 20)],
            "log_3 ($1-3.16/$3.16-10/$10-20)": [(1, 3.16), (3.16, 10), (10, 20)],
            "linear_4 ($1-5/$5-10/$10-15/$15-20)": [(1, 5), (5, 10), (10, 15), (15, 20)],
            "2-tier ($1-5/$5-10)": [(1, 5), (5, 10)],
        }

    results = []
    for name, tiers in schemes.items():
        # 收集每个 tier 的 label
        tier_labels = []
        tier_medians = []
        for lo, hi in tiers:
            hi_eff = min(hi, max_price + 1)
            sub = valid.loc[(valid["price"] >= lo) & (valid["price"] < hi_eff), "label"].values
            if len(sub) == 0:
                continue
            tier_labels.append(sub)
            st = _tier_stats(sub)
            tier_medians.append(st["median"])

        if len(tier_labels) < 2:
            continue

        ns = [len(t) for t in tier_labels]
        cvs = [np.std(t) / np.mean(t) if np.mean(t) > 0 else np.inf for t in tier_labels]

        # 样本均衡
        balance = min(ns) / max(ns)

        # 加权 CV
        total_n = sum(ns)
        avg_cv = sum(cv * n / total_n for cv, n in zip(cvs, ns))

        # 分离度（相邻 tier median 差）
        seps = [abs(tier_medians[i + 1] - tier_medians[i]) for i in range(len(tier_medians) - 1)]
        avg_sep = np.mean(seps)
        min_sep = min(seps)

        # Eta² (one-way ANOVA 效应量)
        all_labels = np.concatenate(tier_labels)
        grand_mean = np.mean(all_labels)
        ss_total = np.sum((all_labels - grand_mean) ** 2)
        ss_between = sum(len(t) * (np.mean(t) - grand_mean) ** 2 for t in tier_labels)
        eta2 = ss_between / ss_total if ss_total > 0 else 0

        # Mann-Whitney 相邻 tier 分离度
        mw_seps = []
        for i in range(len(tier_labels) - 1):
            u_stat, p_val = sp_stats.mannwhitneyu(tier_labels[i], tier_labels[i + 1], alternative="two-sided")
            r_rb = abs(1 - 2 * u_stat / (len(tier_labels[i]) * len(tier_labels[i + 1])))
            mw_seps.append(r_rb)

        results.append({
            "scheme": name,
            "n_tiers": len(tier_labels),
            "avg_cv": avg_cv,
            "balance": balance,
            "min_n": min(ns),
            "max_n": max(ns),
            "avg_sep": avg_sep,
            "min_sep": min_sep,
            "eta2": eta2,
            "avg_mw_sep": np.mean(mw_seps),
            "min_mw_sep": min(mw_seps),
            "tier_ns": ns,
            "tier_medians": [round(m, 4) for m in tier_medians],
        })

    return pd.DataFrame(results)


# ── 5. 幂律拟合 ──────────────────────────────────────────────────────

def fit_power_law(df: pd.DataFrame, granularity: float = 1.0) -> dict:
    """
    拟合 label_median = a * price^b 幂律模型。

    按 granularity 大小分 bin，取每个 bin 的 median，在 log-log 空间做线性回归。

    Returns:
        {'a': float, 'b': float, 'r_squared': float, 'bin_data': DataFrame}
    """
    valid = df.dropna(subset=["label"])
    min_p = int(valid["price"].min())
    max_p = int(valid["price"].max()) + 1
    bins = np.arange(min_p, max_p + granularity, granularity)

    medians = []
    mid_prices = []
    for i in range(len(bins) - 1):
        sub = valid.loc[(valid["price"] >= bins[i]) & (valid["price"] < bins[i + 1]), "label"]
        if len(sub) >= 20:
            medians.append(sub.median())
            mid_prices.append((bins[i] + bins[i + 1]) / 2)

    log_p = np.log(mid_prices)
    log_m = np.log(medians)
    slope, intercept, r_val, _, _ = sp_stats.linregress(log_p, log_m)

    a = np.exp(intercept)
    b = slope

    bin_data = pd.DataFrame({
        "mid_price": mid_prices,
        "actual_median": medians,
        "predicted": [a * p ** b for p in mid_prices],
    })

    return {"a": a, "b": b, "r_squared": r_val ** 2, "bin_data": bin_data}


# ── 汇总报告 ──────────────────────────────────────────────────────────

def run_full_analysis(json_path: str | Path, output_dir: str | Path | None = None) -> dict:
    """
    运行完整分析流程，输出到控制台并返回结果字典。

    Args:
        json_path: scan_results JSON 路径
        output_dir: 可选输出目录（写 CSV）
    """
    df, label_key = load_breakouts(json_path)
    results = {}

    # ── 1. Label 分布 ──
    print("\n" + "=" * 70)
    print("1. LABEL DISTRIBUTION BY PRICE")
    print("=" * 70)

    # 粗粒度
    coarse_bins = [1, 3, 5, 7, 10, 15, 20, 30, 50]
    coarse_bins = [b for b in coarse_bins if b <= df["price"].max() + 1]
    dist_coarse = label_distribution(df, coarse_bins)
    print("\n[粗粒度]")
    print(dist_coarse.to_string(index=False, float_format="{:.4f}".format))
    results["dist_coarse"] = dist_coarse

    # $1 粒度
    dist_fine = label_distribution(df)
    print("\n[$1 粒度]")
    print(dist_fine.to_string(index=False, float_format="{:.4f}".format))
    results["dist_fine"] = dist_fine

    # ── 2. 断点检测 ──
    print("\n" + "=" * 70)
    print("2. BREAKPOINT DETECTION (Mann-Whitney U)")
    print("=" * 70)

    bp_adjacent = detect_breakpoints(df)
    print("\n[相邻 $1 区间跳变] (Top 10)")
    print(bp_adjacent.head(10).to_string(index=False, float_format="{:.4f}".format))
    results["breakpoints_adjacent"] = bp_adjacent

    split_points = [3, 4, 5, 7, 10, 12, 15]
    split_points = [p for p in split_points if p < df["price"].max()]
    bp_splits = detect_breakpoints(df, split_points)
    print("\n[分割点对比]")
    print(bp_splits.to_string(index=False, float_format="{:.4f}".format))
    results["breakpoints_splits"] = bp_splits

    # ── 3. 因子分布 ──
    print("\n" + "=" * 70)
    print("3. FACTOR DISTRIBUTION ANALYSIS")
    print("=" * 70)

    max_p = df["price"].max()
    price_bins = [(1, 5), (5, 10)]
    if max_p >= 15:
        price_bins.append((10, 15))
    if max_p >= 20:
        price_bins[-1] = (10, 20)  # 合并为 $10-20
    elif max_p >= 10:
        price_bins.append((10, max_p + 1))

    fd = factor_distribution(df, price_bins)

    print("\n[Kruskal-Wallis H 检验]")
    print(fd["kruskal"].to_string(index=False, float_format="{:.4f}".format))

    print("\n[Spearman vs Price]")
    print(fd["spearman_vs_price"].to_string(index=False, float_format="{:.4f}".format))
    results["factor_dist"] = fd

    # 因子对 label 的区分力（分区间）
    print("\n[因子 vs Label 相关性]")
    for lo, hi in price_bins:
        corr = factor_label_correlation(df, (lo, hi))
        label = f"${lo}-{hi}"
        print(f"\n  {label}:")
        print(corr.head(10).to_string(index=False, float_format="{:.4f}".format))
        results[f"factor_label_{lo}_{hi}"] = corr

    # ── 4. 分层方案对比 ──
    print("\n" + "=" * 70)
    print("4. TIER SCHEME COMPARISON")
    print("=" * 70)

    schemes_df = compare_tier_schemes(df)
    print(schemes_df[["scheme", "n_tiers", "avg_cv", "balance", "min_n",
                       "avg_sep", "min_sep", "eta2", "tier_medians"]].to_string(
        index=False, float_format="{:.4f}".format
    ))
    results["tier_schemes"] = schemes_df

    # ── 5. 幂律拟合 ──
    print("\n" + "=" * 70)
    print("5. POWER LAW FIT")
    print("=" * 70)

    pl = fit_power_law(df)
    print(f"\n  模型: label_median = {pl['a']:.4f} × price^({pl['b']:.4f})")
    print(f"  R² = {pl['r_squared']:.4f}")
    print(f"  衰减率: 价格翻倍 → label × {2 ** pl['b']:.3f}")
    results["power_law"] = pl

    # ── 输出 ──
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        dist_coarse.to_csv(output_dir / "label_dist_coarse.csv", index=False)
        dist_fine.to_csv(output_dir / "label_dist_fine.csv", index=False)
        bp_adjacent.to_csv(output_dir / "breakpoints.csv", index=False)
        schemes_df.to_csv(output_dir / "tier_schemes.csv", index=False)
        print(f"\n[输出] CSV 已写入 {output_dir}")

    print("\n" + "=" * 70)
    print(f"分析完成 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print("=" * 70)

    return results


# ── 入口 ──────────────────────────────────────────────────────────────

def main():
    json_path = PROJECT_ROOT / "outputs" / "scan_results" / "scan_results_all.json"
    output_dir = PROJECT_ROOT / "outputs" / "analysis" / "price_tier"

    run_full_analysis(json_path, output_dir)


if __name__ == "__main__":
    main()
