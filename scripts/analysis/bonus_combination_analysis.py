"""
Bonus 组合分析 — 数据管道 + 统计分析

从 scan_results JSON 重建所有 bonus levels，输出清洗后的 DataFrame。
"""

import json
import math
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# 通用 level 计算
# ---------------------------------------------------------------------------

def get_level(value, thresholds):
    """根据阈值列表返回 level (0, 1, 2, ...)"""
    level = 0
    for i, t in enumerate(thresholds):
        if value >= t:
            level = i + 1
        else:
            break
    return level


# ---------------------------------------------------------------------------
# Peak 聚类 — 贪心 3% 阈值
# ---------------------------------------------------------------------------

def _largest_cluster_size(peak_prices, threshold=0.03):
    """
    贪心聚类：按价格排序后，相邻价差比 <= threshold 归为同一簇。
    返回最大簇的大小。
    """
    if not peak_prices:
        return 0
    sorted_prices = sorted(peak_prices)
    best = 1
    current = 1
    for i in range(1, len(sorted_prices)):
        ratio = (sorted_prices[i] - sorted_prices[i - 1]) / sorted_prices[i - 1]
        if ratio <= threshold:
            current += 1
        else:
            best = max(best, current)
            current = 1
    best = max(best, current)
    return best


# ---------------------------------------------------------------------------
# 从 peak 数据重建特征
# ---------------------------------------------------------------------------

def _rebuild_peak_features(breakout, all_peaks_by_id):
    """
    从 breakout 的 broken_peak_ids + stock 的 all_peaks 重建：
    - oldest_age: breakout.index - min(peak.index)
    - test_count: 最大阻力簇大小（贪心聚类 3%）
    - max_peak_volume: max(peak.volume_surge_ratio)
    - max_height: max(peak.relative_height)
    """
    broken_ids = breakout.get("broken_peak_ids", [])
    if not broken_ids:
        return 0, 0, 0.0, 0.0

    matched_peaks = [all_peaks_by_id[pid] for pid in broken_ids if pid in all_peaks_by_id]
    if not matched_peaks:
        return 0, 0, 0.0, 0.0

    bo_index = breakout["index"]
    oldest_age = bo_index - min(p["index"] for p in matched_peaks)
    test_count = _largest_cluster_size([p["price"] for p in matched_peaks])
    max_peak_volume = max(p["volume_surge_ratio"] for p in matched_peaks)
    max_height = max(p["relative_height"] for p in matched_peaks)

    return oldest_age, test_count, max_peak_volume, max_height


# ---------------------------------------------------------------------------
# 核心数据管道
# ---------------------------------------------------------------------------

def build_dataframe(json_path):
    """
    从 scan_results JSON 构建分析用 DataFrame。

    Args:
        json_path: scan_results JSON 文件路径

    步骤:
    1. 加载 JSON，提取每条 breakout 的原始特征
    2. 从 peak 数据重建 oldest_age / test_count / max_peak_volume
    3. 根据阈值配置计算所有 bonus levels
    4. 过滤掉 label_10_40 为 None 的记录
    5. 保存 CSV 并返回 DataFrame
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    # --- 从 metadata 读取阈值配置 ---
    scorer_params = data["scan_metadata"]["quality_scorer_params"]

    age_thresholds = scorer_params["age_bonus"]["thresholds"]          # [42, 63, 252]
    test_thresholds = scorer_params["test_bonus"]["thresholds"]        # [2, 3, 4]
    peak_vol_thresholds = scorer_params["peak_volume_bonus"]["thresholds"]  # [3.0, 5.0]
    volume_thresholds = scorer_params["volume_bonus"]["thresholds"]    # [5.0, 10.0]
    pbm_thresholds = scorer_params["pbm_bonus"]["thresholds"]          # [0.006, 0.01]
    streak_thresholds = scorer_params["streak_bonus"]["thresholds"]    # [2, 4]
    overshoot_thresholds = scorer_params["overshoot_penalty"]["thresholds"]  # [4.0, 5.0]
    day_str_thresholds = scorer_params["breakout_day_strength_bonus"]["thresholds"]  # [1.5, 2.5]
    pk_mom_thresholds = scorer_params["pk_momentum_bonus"]["thresholds"]    # [1.2, 1.5]
    drought_thresholds = scorer_params.get("drought_bonus", {}).get("thresholds", [60, 80, 120])
    height_thresholds = scorer_params["height_bonus"]["thresholds"]

    # enabled 标志（disabled 的因子 level 强制为 0，与 QualityScorer 行为一致）
    age_enabled = scorer_params["age_bonus"].get("enabled", True)
    test_enabled = scorer_params["test_bonus"].get("enabled", True)
    peak_vol_enabled = scorer_params["peak_volume_bonus"].get("enabled", True)
    volume_enabled = scorer_params["volume_bonus"].get("enabled", True)
    pbm_enabled = scorer_params["pbm_bonus"].get("enabled", True)
    streak_enabled = scorer_params["streak_bonus"].get("enabled", True)
    overshoot_enabled = scorer_params["overshoot_penalty"].get("enabled", True)
    day_str_enabled = scorer_params["breakout_day_strength_bonus"].get("enabled", True)
    pk_mom_enabled = scorer_params["pk_momentum_bonus"].get("enabled", True)
    drought_enabled = scorer_params.get("drought_bonus", {}).get("enabled", True)
    height_enabled = scorer_params["height_bonus"].get("enabled", True)

    # --- 遍历所有 breakout 记录 ---
    rows = []
    for stock in data["results"]:
        symbol = stock["symbol"]
        all_peaks_by_id = {p["id"]: p for p in stock.get("all_peaks", [])}

        for bo in stock.get("breakouts", []):
            label_val = bo.get("labels", {}).get("label_10_40")

            # 原始特征（None 处理为 0）
            volume_surge = bo.get("volume_surge_ratio") or 0.0
            momentum = bo.get("momentum") or 0.0
            pk_momentum = bo.get("pk_momentum")  # 保留 None 用于列输出
            gain_5d = bo.get("gain_5d") or 0.0
            annual_vol = bo.get("annual_volatility") or 0.0
            recent_bo_count = bo.get("recent_breakout_count") or 0
            gap_up_pct = bo.get("gap_up_pct") or 0.0
            intraday_change_pct = bo.get("intraday_change_pct") or 0.0

            # 从 peak 数据重建
            oldest_age, test_count, max_peak_volume, max_height = _rebuild_peak_features(bo, all_peaks_by_id)

            # --- 计算各 bonus level（disabled 的因子强制为 0）---
            # Volume
            volume_level = get_level(volume_surge, volume_thresholds) if volume_enabled else 0
            # PBM
            pbm_level = get_level(momentum, pbm_thresholds) if pbm_enabled else 0
            # PK-Mom (None → 0)
            pk_mom_level = get_level(pk_momentum if pk_momentum is not None else 0, pk_mom_thresholds) if pk_mom_enabled else 0
            # Age
            age_level = get_level(oldest_age, age_thresholds) if age_enabled else 0
            # Test
            test_level = get_level(test_count, test_thresholds) if test_enabled else 0
            # Peak Volume
            peak_vol_level = get_level(max_peak_volume, peak_vol_thresholds) if peak_vol_enabled else 0
            # Height
            height_level = get_level(max_height, height_thresholds) if height_enabled else 0
            # Streak
            streak_level = get_level(recent_bo_count, streak_thresholds) if streak_enabled else 0

            # Overshoot penalty: ratio = gain_5d / (annual_vol / sqrt(50.4))
            if annual_vol > 0:
                overshoot_ratio = gain_5d / (annual_vol / math.sqrt(50.4))
            else:
                overshoot_ratio = 0.0
            overshoot_level = get_level(overshoot_ratio, overshoot_thresholds) if overshoot_enabled else 0

            # DayStr bonus: ratio = max(idr/daily_vol, gap/daily_vol)
            # daily_vol = annual_vol / sqrt(252)
            if annual_vol > 0:
                daily_vol = annual_vol / math.sqrt(252)
                idr_ratio = abs(intraday_change_pct) / daily_vol
                gap_ratio = abs(gap_up_pct) / daily_vol
                day_str_ratio = max(idr_ratio, gap_ratio)
            else:
                day_str_ratio = 0.0
            day_str_level = get_level(day_str_ratio, day_str_thresholds) if day_str_enabled else 0

            # Drought bonus: 距上次突破的交易日间隔
            days_since = bo.get("days_since_last_breakout")
            drought_level = get_level(days_since or 0, drought_thresholds) if drought_enabled else 0

            rows.append({
                # 标识
                "symbol": symbol,
                "date": bo["date"],
                "price": bo["price"],
                "quality_score": bo.get("quality_score", 0),
                "pattern_label": bo.get("pattern_label", ""),
                # 原始特征
                "volume_surge_ratio": volume_surge,
                "momentum": momentum,
                "pk_momentum": pk_momentum,
                "gain_5d": gain_5d,
                "annual_volatility": annual_vol,
                "recent_breakout_count": recent_bo_count,
                "gap_up_pct": gap_up_pct,
                "intraday_change_pct": intraday_change_pct,
                # 重建特征
                "oldest_age": oldest_age,
                "test_count": test_count,
                "max_peak_volume": max_peak_volume,
                "max_height": max_height,
                # Bonus levels
                "age_level": age_level,
                "test_level": test_level,
                "volume_level": volume_level,
                "pk_mom_level": pk_mom_level,
                "streak_level": streak_level,
                "pbm_level": pbm_level,
                "overshoot_level": overshoot_level,
                "day_str_level": day_str_level,
                "peak_vol_level": peak_vol_level,
                "height_level": height_level,
                "days_since_last_breakout": days_since,
                "drought_level": drought_level,
                # Label
                "label_10_40": label_val,
            })

    df = pd.DataFrame(rows)

    # 过滤掉 label 为 None 的记录
    before_count = len(df)
    df = df.dropna(subset=["label_10_40"]).reset_index(drop=True)
    after_count = len(df)

    # 保存 CSV
    output_path = PROJECT_ROOT / "outputs" / "analysis" / "bonus_analysis_data.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    # 打印基本统计
    print(f"=== Data Pipeline Summary ===")
    print(f"Total breakouts extracted: {before_count}")
    print(f"After filtering (label_10_40 not null): {after_count}")
    print(f"Removed: {before_count - after_count}")
    print(f"Unique symbols: {df['symbol'].nunique()}")
    print(f"Date range: {df['date'].min()} ~ {df['date'].max()}")
    print(f"\nLabel stats:")
    print(df["label_10_40"].describe())
    print(f"\nBonus level distributions:")
    level_cols = [c for c in df.columns if c.endswith("_level")]
    for col in level_cols:
        dist = df[col].value_counts().sort_index().to_dict()
        print(f"  {col}: {dist}")
    print(f"\nSaved to: {output_path}")

    return df


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from _analysis_functions import run_analysis, generate_report

    # ---- 配置区 ----
    json_path = PROJECT_ROOT / "outputs" / "scan_results" / "scan_results_all.json"
    report_name = "bonus_combination_all.md"

    df = build_dataframe(json_path)
    results = run_analysis(df)
    generate_report(results, report_name)
