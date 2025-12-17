"""
Pattern Label v2 回测验证脚本

对现有样本应用 v2 分类逻辑（基于 docs/research/pattern_label_redesign.md §4 伪代码），
验证 7 个假设（H1-H7），输出统计报告。

用法:
    uv run python scripts/analysis/pattern_v2_backtest.py
    uv run python scripts/analysis/pattern_v2_backtest.py --json-path outputs/scan_results/xxx.json
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, kruskal

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "analysis"))

from bonus_combination_analysis import build_dataframe
from _analysis_functions import (
    _pattern_analysis,
    _df_to_md_table,
    _fmt,
    _significance_stars,
    LABEL_COL,
)


# ---------------------------------------------------------------------------
# v2 分类逻辑（内联，来自 redesign doc §4）
# ---------------------------------------------------------------------------

def classify_pattern_v2(row) -> str:
    """
    v2 模式分类：按优先级判定 Volume > PBM+DayStr > PBM > Drought > PK-Mom > Streak > basic

    基于经 n=9810 验证的有效因子，移除 Age/Tests 分类轴。
    Streak 作为有条件降级标记 — 仅在缺乏正向因子对冲时降级。
    """
    vol = row["volume_level"]
    pbm = row["pbm_level"]
    daystr = row["day_str_level"]
    streak = row["streak_level"]
    pk_mom = row["pk_mom_level"]
    drought = row["drought_level"]

    # Tier 1: 放量驱动
    if vol >= 1:
        if pbm >= 2:
            return "power_surge"
        return "volume_breakout"

    # Tier 2: 动量驱动
    if pbm >= 2:
        if daystr >= 1:
            return "strong_momentum"
        return "momentum"

    # Tier 3: 辅助因子
    if drought >= 1:
        return "dormant_awakening"
    if pk_mom >= 2:
        return "dip_recovery"

    # Tier 4: 降级与兜底
    if streak >= 1:
        return "crowded_breakout"

    return "basic"


# ---------------------------------------------------------------------------
# 假设检验函数
# ---------------------------------------------------------------------------

V2_TIER_ORDER = [
    "power_surge", "volume_breakout", "strong_momentum", "momentum",
    "dormant_awakening", "dip_recovery", "crowded_breakout", "basic",
]


def _safe_mannwhitney(a, b):
    """安全调用 Mann-Whitney U, 样本不足时返回 (nan, nan)"""
    if len(a) < 5 or len(b) < 5:
        return np.nan, np.nan
    return mannwhitneyu(a, b, alternative="two-sided")


def test_h1(df: pd.DataFrame) -> dict:
    """
    H1: 新方案模式间区分度 — Kruskal-Wallis + 相邻 Tier Mann-Whitney

    通过标准: H >= 236 且相邻 Tier p < 0.05
    """
    groups = [g[LABEL_COL].values for _, g in df.groupby("pattern_v2") if len(g) >= 5]
    h_stat, h_p = kruskal(*groups) if len(groups) >= 2 else (np.nan, np.nan)

    # 相邻 Tier 比较
    adjacent_tests = []
    patterns_present = [p for p in V2_TIER_ORDER if p in df["pattern_v2"].values]
    for i in range(len(patterns_present) - 1):
        pa, pb = patterns_present[i], patterns_present[i + 1]
        ga = df.loc[df["pattern_v2"] == pa, LABEL_COL].dropna()
        gb = df.loc[df["pattern_v2"] == pb, LABEL_COL].dropna()
        u, p = _safe_mannwhitney(ga.values, gb.values)
        adjacent_tests.append({
            "pair": f"{pa} vs {pb}",
            "median_a": ga.median(),
            "median_b": gb.median(),
            "u_stat": u,
            "p_value": p,
            "significant": p < 0.05 if not np.isnan(p) else False,
        })

    all_adjacent_sig = all(t["significant"] for t in adjacent_tests)

    return {
        "passed": h_stat >= 236 and all_adjacent_sig,
        "h_stat": h_stat,
        "h_p": h_p,
        "h_threshold": 236,
        "adjacent_tests": adjacent_tests,
        "all_adjacent_significant": all_adjacent_sig,
    }


def test_h2(df: pd.DataFrame) -> dict:
    """
    H2: power_surge 是表现最好的模式

    通过标准: median >= 0.25 且 vs momentum Mann-Whitney p < 0.01
    """
    ps = df.loc[df["pattern_v2"] == "power_surge", LABEL_COL].dropna()
    mom = df.loc[df["pattern_v2"] == "momentum", LABEL_COL].dropna()
    u, p = _safe_mannwhitney(ps.values, mom.values)

    return {
        "passed": ps.median() >= 0.25 and (p < 0.01 if not np.isnan(p) else False),
        "power_surge_median": ps.median(),
        "power_surge_n": len(ps),
        "momentum_median": mom.median(),
        "u_stat": u,
        "p_value": p,
    }


def test_h3(df: pd.DataFrame) -> dict:
    """
    H3: crowded_breakout 的 median 显著低于 basic

    通过标准: p < 0.05 且 crowded median < basic median
    """
    crowd = df.loc[df["pattern_v2"] == "crowded_breakout", LABEL_COL].dropna()
    basic = df.loc[df["pattern_v2"] == "basic", LABEL_COL].dropna()
    u, p = _safe_mannwhitney(crowd.values, basic.values)

    return {
        "passed": (crowd.median() < basic.median()) and (p < 0.05 if not np.isnan(p) else False),
        "crowded_median": crowd.median(),
        "crowded_n": len(crowd),
        "basic_median": basic.median(),
        "basic_n": len(basic),
        "u_stat": u,
        "p_value": p,
    }


def test_h4(df: pd.DataFrame) -> dict:
    """
    H4: 旧 momentum 超大类被有效拆分

    通过标准: 新 momentum < 25% 且子类间 median 有显著差异
    """
    old_mom = df[df["pattern_label"] == "momentum"]
    old_mom_n = len(old_mom)

    # 旧 momentum 在新方案中的去向
    if old_mom_n > 0:
        dest = old_mom["pattern_v2"].value_counts()
        dest_pct = (dest / old_mom_n * 100).round(1)
    else:
        dest = pd.Series(dtype=int)
        dest_pct = pd.Series(dtype=float)

    new_mom = df[df["pattern_v2"] == "momentum"]
    new_mom_pct = len(new_mom) / len(df) * 100

    # 子类间 Mann-Whitney：strong_momentum vs momentum
    sm = df.loc[df["pattern_v2"] == "strong_momentum", LABEL_COL].dropna()
    mom = df.loc[df["pattern_v2"] == "momentum", LABEL_COL].dropna()
    u, p = _safe_mannwhitney(sm.values, mom.values)

    return {
        "passed": new_mom_pct < 25 and (p < 0.05 if not np.isnan(p) else False),
        "old_momentum_n": old_mom_n,
        "old_momentum_pct": old_mom_n / len(df) * 100,
        "new_momentum_n": len(new_mom),
        "new_momentum_pct": new_mom_pct,
        "destination_counts": dest.to_dict(),
        "destination_pct": dest_pct.to_dict(),
        "sm_vs_mom_u": u,
        "sm_vs_mom_p": p,
        "sm_median": sm.median() if len(sm) > 0 else np.nan,
        "mom_median": mom.median() if len(mom) > 0 else np.nan,
    }


def test_h5(df: pd.DataFrame) -> dict:
    """
    H5: Drought 的非线性特征 — dormant_awakening 中 level 1 vs 2+

    通过标准: level 1 median > level 2+ median
    """
    da = df[df["pattern_v2"] == "dormant_awakening"]
    lv1 = da.loc[da["drought_level"] == 1, LABEL_COL].dropna()
    lv2plus = da.loc[da["drought_level"] >= 2, LABEL_COL].dropna()

    return {
        "passed": lv1.median() > lv2plus.median() if len(lv1) > 0 and len(lv2plus) > 0 else False,
        "level_1_median": lv1.median() if len(lv1) > 0 else np.nan,
        "level_1_n": len(lv1),
        "level_2plus_median": lv2plus.median() if len(lv2plus) > 0 else np.nan,
        "level_2plus_n": len(lv2plus),
    }


def test_h6(df: pd.DataFrame) -> dict:
    """
    H6: 放量 Streak 突破不被错误降级

    通过标准: Streak>=1 & Vol>=1 的样本 100% 在 Tier 1/2 且 median >= 0.20
    """
    mask = (df["streak_level"] >= 1) & (df["volume_level"] >= 1)
    subset = df[mask]

    tier12 = {"power_surge", "volume_breakout", "strong_momentum", "momentum"}
    in_tier12 = subset[subset["pattern_v2"].isin(tier12)]
    pct_tier12 = len(in_tier12) / len(subset) * 100 if len(subset) > 0 else 0

    median_val = subset[LABEL_COL].median() if len(subset) > 0 else np.nan
    pattern_dist = subset["pattern_v2"].value_counts().to_dict() if len(subset) > 0 else {}

    return {
        "passed": pct_tier12 == 100 and (median_val >= 0.20 if not np.isnan(median_val) else False),
        "total_n": len(subset),
        "in_tier12_n": len(in_tier12),
        "pct_in_tier12": pct_tier12,
        "median": median_val,
        "pattern_distribution": pattern_dist,
    }


def test_h7(df: pd.DataFrame) -> dict:
    """
    H7: DayStr 为 strong_momentum 提供附加区分力

    通过标准: Mann-Whitney p < 0.05 且 strong_momentum median > momentum median
    """
    sm = df.loc[df["pattern_v2"] == "strong_momentum", LABEL_COL].dropna()
    mom = df.loc[df["pattern_v2"] == "momentum", LABEL_COL].dropna()
    u, p = _safe_mannwhitney(sm.values, mom.values)

    return {
        "passed": (sm.median() > mom.median()) and (p < 0.05 if not np.isnan(p) else False),
        "strong_momentum_median": sm.median() if len(sm) > 0 else np.nan,
        "strong_momentum_n": len(sm),
        "momentum_median": mom.median() if len(mom) > 0 else np.nan,
        "momentum_n": len(mom),
        "u_stat": u,
        "p_value": p,
    }


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def _find_latest_json() -> Path:
    """自动发现 outputs/scan_results/ 中最新的 scan_results JSON"""
    scan_dir = PROJECT_ROOT / "outputs" / "scan_results"
    candidates = sorted(scan_dir.glob("scan_results_*.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No scan_results_*.json found in {scan_dir}")
    return candidates[-1]


def generate_v2_report(df: pd.DataFrame, h_results: dict, old_stats: pd.DataFrame, new_stats: pd.DataFrame) -> Path:
    """
    生成 v2 回测验证报告

    Args:
        df: 包含 pattern_v2 列的 DataFrame
        h_results: 7 个假设检验结果
        old_stats: 旧模式统计表
        new_stats: 新模式统计表

    Returns:
        报告文件路径
    """
    lines = []
    lines.append("# Pattern Label v2 Backtest Report\n")
    lines.append(f"Sample size: **{len(df)}** breakout events\n")

    # --- Executive Summary ---
    passed = sum(1 for h in h_results.values() if h["passed"])
    total = len(h_results)
    lines.append("## Executive Summary\n")
    lines.append(f"**{passed}/{total} hypotheses passed.**\n")
    for key, res in h_results.items():
        status = "PASS" if res["passed"] else "FAIL"
        lines.append(f"- **{key}**: {status}")
    lines.append("")

    # --- 新模式分布 ---
    lines.append("## 1. v2 Pattern Distribution\n")
    dist = df["pattern_v2"].value_counts()
    dist_df = pd.DataFrame({
        "pattern": V2_TIER_ORDER,
        "count": [dist.get(p, 0) for p in V2_TIER_ORDER],
        "pct": [dist.get(p, 0) / len(df) * 100 for p in V2_TIER_ORDER],
    })
    lines.append(_df_to_md_table(dist_df, float_fmt=1))
    max_pct = dist_df["pct"].max()
    lines.append(f"\nMax pattern share: {max_pct:.1f}% ({'OK (<30%)' if max_pct < 30 else 'WARNING: >30%'})\n")

    # --- 新旧模式对比 ---
    lines.append("## 2. Old vs New Pattern Stats\n")
    lines.append("### 2.1 Old Patterns (v1)\n")
    lines.append(_df_to_md_table(old_stats))
    lines.append("")
    lines.append("### 2.2 New Patterns (v2)\n")
    lines.append(_df_to_md_table(new_stats))
    lines.append("")

    # --- 假设详细结果 ---
    lines.append("## 3. Hypothesis Test Details\n")

    # H1
    h1 = h_results["H1"]
    lines.append("### H1: Inter-pattern discrimination\n")
    lines.append(f"- Kruskal-Wallis H = {_fmt(h1['h_stat'])} (threshold: {h1['h_threshold']})")
    lines.append(f"- Kruskal-Wallis p = {_fmt(h1['h_p'])} {_significance_stars(h1['h_p'])}")
    lines.append(f"- All adjacent pairs significant: {'Yes' if h1['all_adjacent_significant'] else 'No'}")
    lines.append(f"- **Result: {'PASS' if h1['passed'] else 'FAIL'}**\n")
    adj_rows = []
    for t in h1["adjacent_tests"]:
        adj_rows.append({
            "pair": t["pair"],
            "median_a": t["median_a"],
            "median_b": t["median_b"],
            "p_value": t["p_value"],
            "sig": _significance_stars(t["p_value"]) if not np.isnan(t["p_value"]) else "",
        })
    lines.append(_df_to_md_table(pd.DataFrame(adj_rows)))
    lines.append("")

    # H2
    h2 = h_results["H2"]
    lines.append("### H2: power_surge is the best pattern\n")
    lines.append(f"- power_surge median = {_fmt(h2['power_surge_median'])} (n={h2['power_surge_n']})")
    lines.append(f"- momentum median = {_fmt(h2['momentum_median'])}")
    lines.append(f"- Mann-Whitney p = {_fmt(h2['p_value'])} {_significance_stars(h2['p_value'])}")
    lines.append(f"- **Result: {'PASS' if h2['passed'] else 'FAIL'}**\n")

    # H3
    h3 = h_results["H3"]
    lines.append("### H3: crowded_breakout worse than basic\n")
    lines.append(f"- crowded median = {_fmt(h3['crowded_median'])} (n={h3['crowded_n']})")
    lines.append(f"- basic median = {_fmt(h3['basic_median'])} (n={h3['basic_n']})")
    lines.append(f"- Mann-Whitney p = {_fmt(h3['p_value'])} {_significance_stars(h3['p_value'])}")
    lines.append(f"- **Result: {'PASS' if h3['passed'] else 'FAIL'}**\n")

    # H4
    h4 = h_results["H4"]
    lines.append("### H4: Old momentum effectively split\n")
    lines.append(f"- Old momentum: n={h4['old_momentum_n']} ({h4['old_momentum_pct']:.1f}%)")
    lines.append(f"- New momentum: n={h4['new_momentum_n']} ({h4['new_momentum_pct']:.1f}%)")
    lines.append(f"- strong_momentum median = {_fmt(h4['sm_median'])}")
    lines.append(f"- momentum median = {_fmt(h4['mom_median'])}")
    lines.append(f"- Mann-Whitney p = {_fmt(h4['sm_vs_mom_p'])} {_significance_stars(h4['sm_vs_mom_p'])}")
    lines.append(f"- **Result: {'PASS' if h4['passed'] else 'FAIL'}**\n")
    lines.append("Destination of old momentum samples:\n")
    dest_rows = [{"pattern_v2": k, "count": v, "pct": h4["destination_pct"].get(k, 0)}
                 for k, v in sorted(h4["destination_counts"].items(), key=lambda x: -x[1])]
    lines.append(_df_to_md_table(pd.DataFrame(dest_rows), float_fmt=1))
    lines.append("")

    # H5
    h5 = h_results["H5"]
    lines.append("### H5: Drought nonlinearity in dormant_awakening\n")
    lines.append(f"- Drought level 1: median = {_fmt(h5['level_1_median'])} (n={h5['level_1_n']})")
    lines.append(f"- Drought level 2+: median = {_fmt(h5['level_2plus_median'])} (n={h5['level_2plus_n']})")
    lines.append(f"- **Result: {'PASS' if h5['passed'] else 'FAIL'}**\n")

    # H6
    h6 = h_results["H6"]
    lines.append("### H6: Volume+Streak samples not wrongly degraded\n")
    lines.append(f"- Samples with Streak>=1 & Volume>=1: n={h6['total_n']}")
    lines.append(f"- In Tier 1/2: {h6['in_tier12_n']} ({h6['pct_in_tier12']:.0f}%)")
    lines.append(f"- Median = {_fmt(h6['median'])}")
    lines.append(f"- **Result: {'PASS' if h6['passed'] else 'FAIL'}**\n")
    if h6["pattern_distribution"]:
        pd_rows = [{"pattern": k, "count": v} for k, v in sorted(h6["pattern_distribution"].items(), key=lambda x: -x[1])]
        lines.append(_df_to_md_table(pd.DataFrame(pd_rows)))
    lines.append("")

    # H7
    h7 = h_results["H7"]
    lines.append("### H7: DayStr adds value to strong_momentum\n")
    lines.append(f"- strong_momentum median = {_fmt(h7['strong_momentum_median'])} (n={h7['strong_momentum_n']})")
    lines.append(f"- momentum median = {_fmt(h7['momentum_median'])} (n={h7['momentum_n']})")
    lines.append(f"- Mann-Whitney p = {_fmt(h7['p_value'])} {_significance_stars(h7['p_value'])}")
    lines.append(f"- **Result: {'PASS' if h7['passed'] else 'FAIL'}**\n")

    # --- 建议 ---
    lines.append("## 4. Recommendations\n")
    if passed == total:
        lines.append("All hypotheses passed. v2 classification is validated — proceed with code migration.\n")
    else:
        failed = [k for k, v in h_results.items() if not v["passed"]]
        lines.append(f"Failed hypotheses: {', '.join(failed)}. Review these before proceeding:\n")
        for f in failed:
            lines.append(f"- **{f}**: Consider adjusting thresholds or merging related patterns.")
    lines.append("")

    # --- Pairwise Mann-Whitney (全量) ---
    lines.append("## Appendix: Full Pairwise Mann-Whitney\n")
    v2_df = df.drop(columns=["pattern_label"]).rename(columns={"pattern_v2": "pattern_label"})
    pat_result = _pattern_analysis(v2_df)
    if not pat_result["pairwise"].empty:
        pw = pat_result["pairwise"].copy()
        pw["significance"] = pw["p_value"].apply(_significance_stars)
        pw = pw.sort_values("p_value").reset_index(drop=True)
        lines.append(_df_to_md_table(pw))
    lines.append("")

    # 写出
    report_path = PROJECT_ROOT / "docs" / "statistics" / "pattern_v2_backtest_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as fp:
        fp.write(content)

    print(f"\n[Report] Written to {report_path}")
    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pattern Label v2 backtest")
    parser.add_argument("--json-path", type=str, default=None,
                        help="Path to scan_results JSON (auto-discover if omitted)")
    args = parser.parse_args()

    # 1. 加载数据
    if args.json_path:
        json_path = Path(args.json_path)
    else:
        json_path = _find_latest_json()
    print(f"[Data] Using: {json_path}")

    df = build_dataframe(json_path)

    # 2. 应用 v2 分类
    df["pattern_v2"] = df.apply(classify_pattern_v2, axis=1)

    # 3. 旧/新模式统计
    old_stats_result = _pattern_analysis(df)
    new_df = df.copy()
    new_df["pattern_label"] = new_df["pattern_v2"]
    new_stats_result = _pattern_analysis(new_df)

    old_stats = old_stats_result["stats"]
    new_stats = new_stats_result["stats"]

    print(f"\n{'='*60}")
    print("Old Kruskal-Wallis H = {:.1f}, p = {:.2e}".format(
        old_stats_result["kruskal_stat"], old_stats_result["kruskal_p"]))
    print("New Kruskal-Wallis H = {:.1f}, p = {:.2e}".format(
        new_stats_result["kruskal_stat"], new_stats_result["kruskal_p"]))
    print(f"{'='*60}\n")

    # 4. 假设检验
    h_results = {
        "H1": test_h1(df),
        "H2": test_h2(df),
        "H3": test_h3(df),
        "H4": test_h4(df),
        "H5": test_h5(df),
        "H6": test_h6(df),
        "H7": test_h7(df),
    }

    # 5. 控制台摘要
    print("=" * 60)
    print("  HYPOTHESIS TEST SUMMARY")
    print("=" * 60)
    for key, res in h_results.items():
        status = "\033[92mPASS\033[0m" if res["passed"] else "\033[91mFAIL\033[0m"
        print(f"  {key}: {status}")
    passed = sum(1 for h in h_results.values() if h["passed"])
    print(f"\n  Result: {passed}/{len(h_results)} passed")
    print("=" * 60)

    # 6. 生成报告
    generate_v2_report(df, h_results, old_stats, new_stats)


if __name__ == "__main__":
    main()
