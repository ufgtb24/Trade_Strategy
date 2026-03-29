"""
分布形态分析

对所有因子统一执行分布形态分析（U型/倒U型/单调检测），
输出汇总报告。

分析流程：
1. 基本统计（count, min/max, percentiles, mean/std, skewness）
2. 等频十分位分析 → 检测 label 的 median 形态
3. 形态自动判定（倒U型 / U型 / 单调递增 / 单调递减 / 平坦）
4. 当前 level 单调性检查
5. Spearman 相关系数
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

from BreakoutStrategy.factor_registry import get_active_factors, FactorInfo, LABEL_COL
from BreakoutStrategy.mining.data_pipeline import compute_derived_columns


# ── 形态检测 ──────────────────────────────────────────────────────────

def detect_shape(medians: list[float]) -> tuple[str, str]:
    """
    根据分位 median 序列判定分布形态。

    参数：
        medians: 从低分位到高分位的 label median 列表

    返回：
        (形态名称, 详细说明)

    判定逻辑：
        - 找 median 最大值/最小值所在位置
        - 最大值在中间（Q3~Q7）且两端显著低于峰值 → 倒U型
        - 最小值在中间且两端显著高于谷值 → U型
        - 其他 → 单调递增/递减/平坦
    """
    n = len(medians)
    if n < 3:
        return "样本不足", "分组数不足 3，无法判定形态"

    arr = np.array(medians, dtype=float)
    valid_mask = ~np.isnan(arr)
    if valid_mask.sum() < 3:
        return "样本不足", "有效分组数不足 3"

    valid_idx = np.where(valid_mask)[0]
    valid_vals = arr[valid_mask]

    max_pos = valid_idx[np.argmax(valid_vals)]
    min_pos = valid_idx[np.argmin(valid_vals)]
    val_range = valid_vals.max() - valid_vals.min()

    if val_range < 0.005:
        return "平坦", f"median 范围仅 {val_range:.4f}，各分位表现接近"

    if 0 < max_pos < n - 1:
        before_peak = valid_vals[:np.searchsorted(valid_idx, max_pos)]
        after_peak = valid_vals[np.searchsorted(valid_idx, max_pos) + 1:]
        if len(before_peak) >= 1 and len(after_peak) >= 1:
            before_mean = np.mean(before_peak)
            after_mean = np.mean(after_peak)
            peak_val = valid_vals.max()
            drop_threshold = val_range * 0.2
            if peak_val - before_mean > drop_threshold and peak_val - after_mean > drop_threshold:
                return "倒U型", (
                    f"峰值在 Q{max_pos + 1} (median={arr[max_pos]:.4f})，"
                    f"左侧均值={before_mean:.4f}，右侧均值={after_mean:.4f}"
                )

    if 0 < min_pos < n - 1:
        before_trough = valid_vals[:np.searchsorted(valid_idx, min_pos)]
        after_trough = valid_vals[np.searchsorted(valid_idx, min_pos) + 1:]
        if len(before_trough) >= 1 and len(after_trough) >= 1:
            before_mean = np.mean(before_trough)
            after_mean = np.mean(after_trough)
            trough_val = valid_vals.min()
            rise_threshold = val_range * 0.2
            if before_mean - trough_val > rise_threshold and after_mean - trough_val > rise_threshold:
                return "U型", (
                    f"谷值在 Q{min_pos + 1} (median={arr[min_pos]:.4f})，"
                    f"左侧均值={before_mean:.4f}，右侧均值={after_mean:.4f}"
                )

    diffs = np.diff(valid_vals)
    up_count = np.sum(diffs > 0)
    down_count = np.sum(diffs < 0)
    total_steps = len(diffs)

    if up_count >= total_steps * 0.7:
        return "单调递增", f"上升步数 {up_count}/{total_steps}"
    elif down_count >= total_steps * 0.7:
        return "单调递减", f"下降步数 {down_count}/{total_steps}"
    else:
        return "无明显模式", f"上升 {up_count}, 下降 {down_count} / {total_steps} 步"


def check_level_monotonicity(df: pd.DataFrame, factor: FactorInfo) -> tuple[bool, list[dict]]:
    """
    检查当前阈值下各 level 的 label median 是否单调递增。

    返回：
        (is_monotonic, level_stats_list)
    """
    level_data = df.groupby(factor.level_col)[LABEL_COL].agg(["median", "count"])
    level_data = level_data.sort_index()

    level_stats = []
    for level, row in level_data.iterrows():
        level_stats.append({
            "level": int(level),
            "median": row["median"],
            "count": int(row["count"]),
        })

    if len(level_stats) < 2:
        return True, level_stats

    medians = [s["median"] for s in level_stats]

    is_penalty = any(v < 1.0 for v in factor.default_values)
    if is_penalty:
        is_monotonic = all(medians[i] >= medians[i + 1] for i in range(len(medians) - 1))
    else:
        is_monotonic = all(medians[i] <= medians[i + 1] for i in range(len(medians) - 1))

    return is_monotonic, level_stats


# ── 核心分析函数 ──────────────────────────────────────────────────────────

def analyze_factor(df: pd.DataFrame, factor: FactorInfo) -> dict:
    """
    对单个因子执行完整分析。

    流程：
        1. 提取原始值列（key 列），处理 NaN
        2. 基本统计
        3. 等频十分位（或离散值分组）分析
        4. 形态判定
        5. 当前 level 单调性
        6. Spearman 相关

    返回分析结果字典。
    """
    raw_series = df[factor.key]

    result = {"name": factor.key, "factor": factor}

    nan_mask = raw_series.isna()
    nan_count = nan_mask.sum()
    result["nan_count"] = int(nan_count)

    if factor.has_nan_group and nan_count > 0:
        nan_group_label = df.loc[nan_mask, LABEL_COL]
        result["nan_group"] = {
            "count": int(nan_count),
            "label_median": float(nan_group_label.median()) if len(nan_group_label) > 0 else None,
            "label_mean": float(nan_group_label.mean()) if len(nan_group_label) > 0 else None,
            "positive_rate": float((nan_group_label > 0).mean()) if len(nan_group_label) > 0 else None,
        }

    valid_df = df[~nan_mask].copy()
    valid_series = raw_series[~nan_mask]
    valid_label = valid_df[LABEL_COL]

    result["valid_count"] = len(valid_series)

    if len(valid_series) == 0:
        result["error"] = "无有效数据"
        return result

    desc = valid_series.describe(percentiles=[0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95])
    result["basic_stats"] = {
        "count": int(desc["count"]),
        "min": float(desc["min"]),
        "p5": float(desc["5%"]),
        "p10": float(desc["10%"]),
        "p25": float(desc["25%"]),
        "median": float(desc["50%"]),
        "p75": float(desc["75%"]),
        "p90": float(desc["90%"]),
        "p95": float(desc["95%"]),
        "max": float(desc["max"]),
        "mean": float(desc["mean"]),
        "std": float(desc["std"]),
        "skewness": float(valid_series.skew()),
    }

    if factor.is_discrete:
        groups = _analyze_discrete_groups(valid_df, valid_series)
    else:
        groups = _analyze_decile_groups(valid_df, valid_series)

    result["groups"] = groups

    medians = [g["label_median"] for g in groups]
    shape_name, shape_detail = detect_shape(medians)
    result["shape"] = shape_name
    result["shape_detail"] = shape_detail

    is_mono, level_stats = check_level_monotonicity(df, factor)
    result["level_monotonic"] = is_mono
    result["level_stats"] = level_stats

    valid_both = valid_df[[LABEL_COL]].copy()
    valid_both["raw"] = valid_series.values
    valid_both = valid_both.dropna()
    if len(valid_both) > 10:
        rho, pval = stats.spearmanr(valid_both["raw"], valid_both[LABEL_COL])
        result["spearman_r"] = float(rho)
        result["spearman_p"] = float(pval)
    else:
        result["spearman_r"] = None
        result["spearman_p"] = None

    return result


def _analyze_decile_groups(valid_df: pd.DataFrame, valid_series: pd.Series) -> list[dict]:
    """等频十分位分析"""
    n_groups = 10
    try:
        valid_df = valid_df.copy()
        valid_df["_decile"] = pd.qcut(valid_series, n_groups, labels=False, duplicates="drop")
    except ValueError:
        for ng in [8, 6, 5, 4]:
            try:
                valid_df["_decile"] = pd.qcut(valid_series, ng, labels=False, duplicates="drop")
                n_groups = ng
                break
            except ValueError:
                continue
        else:
            return []

    groups = []
    for decile in sorted(valid_df["_decile"].unique()):
        mask = valid_df["_decile"] == decile
        subset = valid_df[mask]
        raw_vals = valid_series[mask]
        label_vals = subset[LABEL_COL]
        groups.append({
            "group_label": f"Q{int(decile) + 1}",
            "range": f"[{raw_vals.min():.4f}, {raw_vals.max():.4f}]",
            "count": int(len(subset)),
            "raw_median": float(raw_vals.median()),
            "label_median": float(label_vals.median()),
            "label_mean": float(label_vals.mean()),
            "positive_rate": float((label_vals > 0).mean()),
        })

    return groups


def _analyze_discrete_groups(valid_df: pd.DataFrame, valid_series: pd.Series) -> list[dict]:
    """离散值直接分组分析。值过多时合并尾部小组。"""
    vc = valid_series.value_counts().sort_index()

    if len(vc) > 15:
        top_vals = vc.index[:14]
        mask_top = valid_series.isin(top_vals)
        groups = _build_groups_from_mask(valid_df[mask_top], valid_series[mask_top])
        tail_df = valid_df[~mask_top]
        tail_series = valid_series[~mask_top]
        if len(tail_df) > 0:
            label_vals = tail_df[LABEL_COL]
            groups.append({
                "group_label": f"{int(top_vals[-1]) + 1}+",
                "range": f"[{tail_series.min()}, {tail_series.max()}]",
                "count": int(len(tail_df)),
                "raw_median": float(tail_series.median()),
                "label_median": float(label_vals.median()),
                "label_mean": float(label_vals.mean()),
                "positive_rate": float((label_vals > 0).mean()),
            })
        return groups
    else:
        return _build_groups_from_mask(valid_df, valid_series)


def _build_groups_from_mask(valid_df: pd.DataFrame, valid_series: pd.Series) -> list[dict]:
    """按唯一值构建分组统计"""
    groups = []
    for val in sorted(valid_series.unique()):
        mask = valid_series == val
        subset = valid_df[mask]
        label_vals = subset[LABEL_COL]
        groups.append({
            "group_label": str(int(val)) if val == int(val) else str(val),
            "range": str(val),
            "count": int(len(subset)),
            "raw_median": float(val),
            "label_median": float(label_vals.median()),
            "label_mean": float(label_vals.mean()),
            "positive_rate": float((label_vals > 0).mean()),
        })
    return groups


# ── 报告生成 ──────────────────────────────────────────────────────────

def generate_suggestion(result: dict) -> str:
    """根据分析结果生成建议"""
    shape = result.get("shape", "")
    is_mono = result.get("level_monotonic", True)
    spearman = result.get("spearman_r")
    factor = result["factor"]

    parts = []
    if shape == "倒U型":
        parts.append("存在甜蜜区间，建议设定上下界阈值")
    elif shape == "U型":
        parts.append("两端优于中间，考虑非线性评分")
    elif shape == "单调递增":
        parts.append("当前递增模型合理")
    elif shape == "单调递减":
        if any(v < 1.0 for v in factor.default_values):
            parts.append("惩罚方向正确")
        else:
            parts.append("实际为递减，与奖励方向矛盾，需审视")
    elif shape == "平坦":
        parts.append("对收益影响微弱，考虑降低权重或移除")

    if not is_mono:
        parts.append("当前 level 不单调，需调整阈值")

    if spearman is not None and abs(spearman) < 0.03:
        parts.append("相关性极弱")

    return "；".join(parts) if parts else "暂无特别建议"


def format_report(results: list[dict]) -> str:
    """生成完整的 Markdown 报告"""
    lines = []
    lines.append("# Factor 分布形态分析报告")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 数据来源：`outputs/analysis/factor_analysis_data.csv`")
    lines.append("")

    lines.append("## 总览表")
    lines.append("")
    lines.append("| Factor | 形态 | Spearman r | 当前 level 单调? | 峰值/谷值位置 | 建议 |")
    lines.append("|--------|------|-----------|-----------------|-------------|------|")

    for r in results:
        name = r["name"]
        shape = r.get("shape", "N/A")
        sp_r = r.get("spearman_r")
        sp_str = f"{sp_r:.4f}" if sp_r is not None else "N/A"
        mono = "Yes" if r.get("level_monotonic", True) else "**No**"
        detail = r.get("shape_detail", "")
        if len(detail) > 40:
            detail = detail[:40] + "..."
        suggestion = generate_suggestion(r)
        lines.append(f"| {name} | {shape} | {sp_str} | {mono} | {detail} | {suggestion} |")

    lines.append("")

    for i, r in enumerate(results, 1):
        lines.append(f"## {i}. {r['name']}")
        lines.append("")
        _append_factor_detail(lines, r)
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _append_factor_detail(lines: list[str], r: dict):
    """追加单个因子的详细分析内容"""
    factor: FactorInfo = r["factor"]

    if r.get("nan_group"):
        ng = r["nan_group"]
        lines.append(f"### NaN 组（业务含义：{'无近期 peak' if factor.key == 'pk_mom' else '首次突破'}）")
        lines.append(f"- 样本数：{ng['count']}")
        lines.append(f"- label median：{ng['label_median']:.4f}" if ng['label_median'] is not None else "- label median：N/A")
        lines.append(f"- label mean：{ng['label_mean']:.4f}" if ng['label_mean'] is not None else "- label mean：N/A")
        lines.append(f"- 正收益率：{ng['positive_rate']:.1%}" if ng['positive_rate'] is not None else "- 正收益率：N/A")
        lines.append("")

    if r.get("error"):
        lines.append(f"**错误：{r['error']}**")
        lines.append("")
        return

    bs = r["basic_stats"]
    lines.append("### 基本统计")
    lines.append(f"- 有效样本：{bs['count']}" + (f"（NaN: {r['nan_count']}）" if r['nan_count'] > 0 else ""))
    lines.append(f"- 范围：[{bs['min']:.4f}, {bs['max']:.4f}]")
    lines.append(f"- 均值 ± 标准差：{bs['mean']:.4f} ± {bs['std']:.4f}")
    lines.append(f"- 中位数：{bs['median']:.4f}")
    lines.append(f"- 偏度：{bs['skewness']:.4f}")
    lines.append(f"- 分位数：P5={bs['p5']:.4f} | P25={bs['p25']:.4f} | P50={bs['median']:.4f} | P75={bs['p75']:.4f} | P95={bs['p95']:.4f}")
    lines.append("")

    groups = r.get("groups", [])
    if groups:
        group_type = "按原始值分组" if factor.is_discrete else "等频分位"
        lines.append(f"### 分组分析（{group_type}，label by group）")
        lines.append("")

        if factor.is_discrete:
            lines.append("| 值 | N | label median | label mean | 正收益率 |")
            lines.append("|-----|-----|-------------|------------|---------|")
        else:
            lines.append("| 分位 | 范围 | N | label median | label mean | 正收益率 |")
            lines.append("|------|------|-----|-------------|------------|---------|")

        for g in groups:
            if factor.is_discrete:
                lines.append(
                    f"| {g['group_label']} | {g['count']} | "
                    f"{g['label_median']:.4f} | {g['label_mean']:.4f} | "
                    f"{g['positive_rate']:.1%} |"
                )
            else:
                lines.append(
                    f"| {g['group_label']} | {g['range']} | {g['count']} | "
                    f"{g['label_median']:.4f} | {g['label_mean']:.4f} | "
                    f"{g['positive_rate']:.1%} |"
                )

        lines.append("")

        medians = [g["label_median"] for g in groups]
        lines.append("**Median 趋势：** " + _ascii_trend(medians))
        lines.append("")

    lines.append("### 形态判定")
    lines.append(f"- **形态：{r['shape']}**")
    lines.append(f"- 详情：{r['shape_detail']}")
    lines.append("")

    lines.append("### 当前 Level 单调性")
    level_stats = r.get("level_stats", [])
    if level_stats:
        is_penalty = any(v < 1.0 for v in factor.default_values)
        expected = "递减（惩罚因子）" if is_penalty else "递增（奖励因子）"
        lines.append(f"- 期望方向：{expected}")
        lines.append(f"- 单调：{'Yes' if r['level_monotonic'] else '**No**'}")
        lines.append("")

        thresholds_str = ", ".join(str(t) for t in factor.default_thresholds)
        values_str = ", ".join(str(v) for v in factor.default_values)
        lines.append(f"  阈值：[{thresholds_str}]，乘数：[{values_str}]")
        lines.append("")
        lines.append("| Level | N | label median |")
        lines.append("|-------|-----|-------------|")
        for ls in level_stats:
            lines.append(f"| L{ls['level']} | {ls['count']} | {ls['median']:.4f} |")
        lines.append("")

    lines.append("### Spearman 相关")
    if r.get("spearman_r") is not None:
        lines.append(f"- rho = {r['spearman_r']:.4f}, p = {r['spearman_p']:.2e}")
        strength = "强" if abs(r['spearman_r']) > 0.1 else "弱" if abs(r['spearman_r']) > 0.03 else "极弱"
        lines.append(f"- 相关性：{strength}")
    else:
        lines.append("- 无法计算（样本不足）")
    lines.append("")


def _ascii_trend(values: list[float]) -> str:
    """生成简易 ASCII 趋势指示"""
    if len(values) < 2:
        return ""
    symbols = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        if diff > 0.002:
            symbols.append("↑")
        elif diff < -0.002:
            symbols.append("↓")
        else:
            symbols.append("→")
    return " ".join(symbols)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(csv_path, output_path):
    print(f"读取数据: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"总样本数: {len(df)}")
    df = compute_derived_columns(df)

    results = []
    for factor in get_active_factors():
        print(f"分析 {factor.key}...")
        r = analyze_factor(df, factor)
        results.append(r)
        print(f"  形态: {r.get('shape', 'N/A')}, Spearman r: {r.get('spearman_r', 'N/A')}")

    report = format_report(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"\n报告已生成: {output_path}")


if __name__ == "__main__":
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    main(
        csv_path=PROJECT_ROOT / "outputs/analysis/factor_analysis_data.csv",
        output_path=PROJECT_ROOT / "docs/research/factor_distribution_shape_analysis.md",
    )
