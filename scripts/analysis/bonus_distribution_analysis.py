"""
全 Bonus 分布形态分析脚本

对 11 个 bonus 因子统一执行分布形态分析（U型/倒U型/单调检测），
输出汇总报告到 docs/research/bonus_distribution_shape_analysis.md。

分析流程：
1. 基本统计（count, min/max, percentiles, mean/std, skewness）
2. 等频十分位分析 → 检测 label_10_40 的 median 形态
3. 形态自动判定（倒U型 / U型 / 单调递增 / 单调递减 / 平坦）
4. 当前 level 单调性检查
5. Spearman 相关系数
"""

import numpy as np
import pandas as pd
from scipy import stats
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime


# ── Bonus 配置 ──────────────────────────────────────────────────────────

@dataclass
class BonusConfig:
    """单个 bonus 的分析配置"""
    name: str           # 显示名称
    raw_col: str | None # CSV 中的原始列名（None 表示需要衍生）
    level_col: str      # CSV 中的 level 列名
    thresholds: list    # 当前阈值
    values: list        # 当前 bonus 乘数
    is_discrete: bool = False  # 是否为离散/整数型因子
    has_nan_group: bool = False # NaN 是否有业务含义


BONUS_CONFIGS = [
    BonusConfig("Age", "oldest_age", "age_level",
                [42, 63, 252], [1.02, 1.03, 1.05], is_discrete=True),
    BonusConfig("Tests", "test_count", "test_level",
                [2, 3, 4], [1.1, 1.25, 1.4], is_discrete=True),
    BonusConfig("Height", "max_height", "height_level",
                [0.2, 0.4, 0.7], [1.3, 1.6, 2.0]),
    BonusConfig("PeakVol", "max_peak_volume", "peak_vol_level",
                [3.0, 5.0], [1.1, 1.2]),
    BonusConfig("Volume", "volume_surge_ratio", "volume_level",
                [5.0, 10.0], [1.5, 2.0]),
    BonusConfig("PBM", "momentum", "pbm_level",
                [0.7, 1.45], [1.15, 1.3]),
    BonusConfig("Streak", "recent_breakout_count", "streak_level",
                [2, 4], [0.9, 0.75], is_discrete=True),
    BonusConfig("PK-Mom", "pk_momentum", "pk_mom_level",
                [1.2, 1.5], [1.2, 1.5], has_nan_group=True),
    BonusConfig("Drought", "days_since_last_breakout", "drought_level",
                [60, 80, 120], [1.25, 1.1, 1.05], has_nan_group=True),
    # 衍生因子
    BonusConfig("DayStr", None, "day_str_level",
                [1.5, 2.5], [1.2, 1.35]),
    BonusConfig("Overshoot", None, "overshoot_level",
                [4.0, 5.0], [0.8, 0.6]),
]

LABEL_COL = "label_10_40"


# ── 衍生列计算 ──────────────────────────────────────────────────────────

def compute_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """计算 DayStr 和 Overshoot 衍生列"""
    df = df.copy()

    # DayStr = max(|intraday_change_pct|, |gap_up_pct|) / (annual_volatility / sqrt(252))
    daily_vol = df["annual_volatility"] / np.sqrt(252)
    raw_strength = np.maximum(
        df["intraday_change_pct"].abs(),
        df["gap_up_pct"].abs()
    )
    df["day_str_raw"] = raw_strength / daily_vol

    # Overshoot = gain_5d / (annual_volatility / sqrt(50.4))
    vol_5d = df["annual_volatility"] / np.sqrt(50.4)
    df["overshoot_raw"] = df["gain_5d"] / vol_5d

    return df


# ── 形态检测 ──────────────────────────────────────────────────────────

def detect_shape(medians: list[float]) -> tuple[str, str]:
    """
    根据分位 median 序列判定分布形态。

    参数：
        medians: 从低分位到高分位的 label_10_40 median 列表

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

    # 用有效值的 index 来分析
    valid_idx = np.where(valid_mask)[0]
    valid_vals = arr[valid_mask]

    max_pos = valid_idx[np.argmax(valid_vals)]
    min_pos = valid_idx[np.argmin(valid_vals)]
    val_range = valid_vals.max() - valid_vals.min()

    # 平坦判定：范围太小
    if val_range < 0.005:
        return "平坦", f"median 范围仅 {val_range:.4f}，各分位表现接近"

    # 倒U型：最大值在内部（非两端），峰值前后均值显著低于峰值
    if 0 < max_pos < n - 1:
        # 用峰值前后的实际值比较
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

    # U型：最小值在内部，谷值前后均值显著高于谷值
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

    # 单调性检查
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


def check_level_monotonicity(df: pd.DataFrame, config: BonusConfig) -> tuple[bool, list[dict]]:
    """
    检查当前阈值下各 level 的 label_10_40 median 是否单调递增。

    返回：
        (is_monotonic, level_stats_list)
    """
    level_data = df.groupby(config.level_col)[LABEL_COL].agg(["median", "count"])
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

    # 判断递增：bonus 值 >= 1.0 的因子应递增，< 1.0 的应递减
    is_penalty = any(v < 1.0 for v in config.values)
    if is_penalty:
        # 惩罚因子：level 越高 median 应越低（表示惩罚合理）
        is_monotonic = all(medians[i] >= medians[i + 1] for i in range(len(medians) - 1))
    else:
        # 奖励因子：level 越高 median 应越高
        is_monotonic = all(medians[i] <= medians[i + 1] for i in range(len(medians) - 1))

    return is_monotonic, level_stats


# ── 核心分析函数 ──────────────────────────────────────────────────────────

def analyze_bonus(df: pd.DataFrame, config: BonusConfig) -> dict:
    """
    对单个 bonus 执行完整分析。

    流程：
        1. 提取原始值列，处理 NaN
        2. 基本统计
        3. 等频十分位（或离散值分组）分析
        4. 形态判定
        5. 当前 level 单调性
        6. Spearman 相关

    返回分析结果字典。
    """
    # 确定原始值列
    if config.raw_col is not None:
        raw_series = df[config.raw_col]
    elif config.name == "DayStr":
        raw_series = df["day_str_raw"]
    elif config.name == "Overshoot":
        raw_series = df["overshoot_raw"]
    else:
        raise ValueError(f"未知的衍生因子: {config.name}")

    result = {"name": config.name, "config": config}

    # ── NaN 组统计 ──
    nan_mask = raw_series.isna()
    nan_count = nan_mask.sum()
    result["nan_count"] = int(nan_count)

    if config.has_nan_group and nan_count > 0:
        nan_group_label = df.loc[nan_mask, LABEL_COL]
        result["nan_group"] = {
            "count": int(nan_count),
            "label_median": float(nan_group_label.median()) if len(nan_group_label) > 0 else None,
            "label_mean": float(nan_group_label.mean()) if len(nan_group_label) > 0 else None,
            "positive_rate": float((nan_group_label > 0).mean()) if len(nan_group_label) > 0 else None,
        }

    # 仅对非 NaN 数据分析
    valid_df = df[~nan_mask].copy()
    valid_series = raw_series[~nan_mask]
    valid_label = valid_df[LABEL_COL]

    result["valid_count"] = len(valid_series)

    if len(valid_series) == 0:
        result["error"] = "无有效数据"
        return result

    # ── 1. 基本统计 ──
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

    # ── 2. 分位/分组分析 ──
    if config.is_discrete:
        # 离散型：按原始值直接分组
        groups = _analyze_discrete_groups(valid_df, valid_series, config)
    else:
        # 连续型：等频十分位
        groups = _analyze_decile_groups(valid_df, valid_series, config)

    result["groups"] = groups

    # ── 3. 形态判定 ──
    medians = [g["label_median"] for g in groups]
    shape_name, shape_detail = detect_shape(medians)
    result["shape"] = shape_name
    result["shape_detail"] = shape_detail

    # ── 4. 当前 level 单调性 ──
    is_mono, level_stats = check_level_monotonicity(df, config)
    result["level_monotonic"] = is_mono
    result["level_stats"] = level_stats

    # ── 5. Spearman 相关 ──
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


def _analyze_decile_groups(valid_df: pd.DataFrame, valid_series: pd.Series,
                           config: BonusConfig) -> list[dict]:
    """等频十分位分析"""
    n_groups = 10
    try:
        valid_df = valid_df.copy()
        valid_df["_decile"] = pd.qcut(valid_series, n_groups, labels=False, duplicates="drop")
    except ValueError:
        # 值的唯一性不够，降低分组数
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


def _analyze_discrete_groups(valid_df: pd.DataFrame, valid_series: pd.Series,
                             config: BonusConfig) -> list[dict]:
    """离散值直接分组分析。值过多时合并尾部小组。"""
    vc = valid_series.value_counts().sort_index()

    # 如果唯一值 > 15，合并尾部使组数 <= 15
    if len(vc) > 15:
        # 保留前 14 个值，其余合并为 "其他"
        top_vals = vc.index[:14]
        mask_top = valid_series.isin(top_vals)
        groups = _build_groups_from_mask(valid_df[mask_top], valid_series[mask_top])
        # 尾部合并
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
    config = result["config"]

    parts = []
    if shape == "倒U型":
        parts.append("存在甜蜜区间，建议设定上下界阈值")
    elif shape == "U型":
        parts.append("两端优于中间，考虑非线性评分")
    elif shape == "单调递增":
        parts.append("当前递增模型合理")
    elif shape == "单调递减":
        if any(v < 1.0 for v in config.values):
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
    lines.append("# Bonus 分布形态分析报告")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 数据来源：`outputs/analysis/bonus_analysis_data.csv`")
    lines.append("")

    # ── 总览表 ──
    lines.append("## 总览表")
    lines.append("")
    lines.append("| Bonus | 形态 | Spearman r | 当前 level 单调? | 峰值/谷值位置 | 建议 |")
    lines.append("|-------|------|-----------|-----------------|-------------|------|")

    for r in results:
        name = r["name"]
        shape = r.get("shape", "N/A")
        sp_r = r.get("spearman_r")
        sp_str = f"{sp_r:.4f}" if sp_r is not None else "N/A"
        mono = "Yes" if r.get("level_monotonic", True) else "**No**"
        detail = r.get("shape_detail", "")
        # 截取关键部分
        if len(detail) > 40:
            detail = detail[:40] + "..."
        suggestion = generate_suggestion(r)
        lines.append(f"| {name} | {shape} | {sp_str} | {mono} | {detail} | {suggestion} |")

    lines.append("")

    # ── 各 bonus 详细分析 ──
    for i, r in enumerate(results, 1):
        lines.append(f"## {i}. {r['name']}")
        lines.append("")
        _append_bonus_detail(lines, r)
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _append_bonus_detail(lines: list[str], r: dict):
    """追加单个 bonus 的详细分析内容"""
    config = r["config"]

    # NaN 组
    if r.get("nan_group"):
        ng = r["nan_group"]
        lines.append(f"### NaN 组（业务含义：{'无近期 peak' if config.name == 'PK-Mom' else '首次突破'}）")
        lines.append(f"- 样本数：{ng['count']}")
        lines.append(f"- label_10_40 median：{ng['label_median']:.4f}" if ng['label_median'] is not None else "- label_10_40 median：N/A")
        lines.append(f"- label_10_40 mean：{ng['label_mean']:.4f}" if ng['label_mean'] is not None else "- label_10_40 mean：N/A")
        lines.append(f"- 正收益率：{ng['positive_rate']:.1%}" if ng['positive_rate'] is not None else "- 正收益率：N/A")
        lines.append("")

    if r.get("error"):
        lines.append(f"**错误：{r['error']}**")
        lines.append("")
        return

    # 基本统计
    bs = r["basic_stats"]
    lines.append("### 基本统计")
    lines.append(f"- 有效样本：{bs['count']}" + (f"（NaN: {r['nan_count']}）" if r['nan_count'] > 0 else ""))
    lines.append(f"- 范围：[{bs['min']:.4f}, {bs['max']:.4f}]")
    lines.append(f"- 均值 ± 标准差：{bs['mean']:.4f} ± {bs['std']:.4f}")
    lines.append(f"- 中位数：{bs['median']:.4f}")
    lines.append(f"- 偏度：{bs['skewness']:.4f}")
    lines.append(f"- 分位数：P5={bs['p5']:.4f} | P25={bs['p25']:.4f} | P50={bs['median']:.4f} | P75={bs['p75']:.4f} | P95={bs['p95']:.4f}")
    lines.append("")

    # 分组分析
    groups = r.get("groups", [])
    if groups:
        group_type = "按原始值分组" if config.is_discrete else "等频分位"
        lines.append(f"### 分组分析（{group_type}，label_10_40 by group）")
        lines.append("")

        # 表头
        if config.is_discrete:
            lines.append("| 值 | N | label median | label mean | 正收益率 |")
            lines.append("|-----|-----|-------------|------------|---------|")
        else:
            lines.append("| 分位 | 范围 | N | label median | label mean | 正收益率 |")
            lines.append("|------|------|-----|-------------|------------|---------|")

        for g in groups:
            if config.is_discrete:
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

        # 形态 ASCII 趋势图
        medians = [g["label_median"] for g in groups]
        lines.append("**Median 趋势：** " + _ascii_trend(medians))
        lines.append("")

    # 形态判定
    lines.append("### 形态判定")
    lines.append(f"- **形态：{r['shape']}**")
    lines.append(f"- 详情：{r['shape_detail']}")
    lines.append("")

    # 当前 level 单调性
    lines.append("### 当前 Level 单调性")
    level_stats = r.get("level_stats", [])
    if level_stats:
        is_penalty = any(v < 1.0 for v in config.values)
        expected = "递减（惩罚因子）" if is_penalty else "递增（奖励因子）"
        lines.append(f"- 期望方向：{expected}")
        lines.append(f"- 单调：{'Yes' if r['level_monotonic'] else '**No**'}")
        lines.append("")

        thresholds_str = ", ".join(str(t) for t in config.thresholds)
        values_str = ", ".join(str(v) for v in config.values)
        lines.append(f"  阈值：[{thresholds_str}]，乘数：[{values_str}]")
        lines.append("")
        lines.append("| Level | N | label median |")
        lines.append("|-------|-----|-------------|")
        for ls in level_stats:
            lines.append(f"| L{ls['level']} | {ls['count']} | {ls['median']:.4f} |")
        lines.append("")

    # Spearman
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


# ── 主流程 ──────────────────────────────────────────────────────────

def main():
    csv_path = Path("outputs/analysis/bonus_analysis_data.csv")
    output_path = Path("docs/research/bonus_distribution_shape_analysis.md")

    print(f"读取数据: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"总样本数: {len(df)}")

    # 计算衍生列
    df = compute_derived_columns(df)

    # 逐个 bonus 分析
    results = []
    for config in BONUS_CONFIGS:
        print(f"分析 {config.name}...")
        r = analyze_bonus(df, config)
        results.append(r)
        print(f"  形态: {r.get('shape', 'N/A')}, Spearman r: {r.get('spearman_r', 'N/A')}")

    # 生成报告
    report = format_report(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"\n报告已生成: {output_path}")


if __name__ == "__main__":
    main()
