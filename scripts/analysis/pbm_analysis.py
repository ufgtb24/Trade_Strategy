"""
PBM (Pre-Breakout Momentum) 分布分析脚本

目标：
1. 收集所有突破的 PBM 值
2. 分析分布（均值、中位数、分位数）
3. 研究 PBM 与突破后表现的相关性
4. 确定合适的阈值
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def load_scan_results(json_path: str) -> list:
    """加载扫描结果并提取 breakout 数据"""
    with open(json_path, "r") as f:
        data = json.load(f)

    breakouts = []
    for stock in data.get("results", []):
        symbol = stock.get("symbol")
        for bo in stock.get("breakouts", []):
            bo["symbol"] = symbol
            breakouts.append(bo)

    return breakouts


def analyze_pbm_distribution(breakouts: list) -> dict:
    """分析 PBM 分布"""
    # 提取 momentum 值
    momentum_values = [
        bo.get("momentum")
        for bo in breakouts
        if bo.get("momentum") is not None
    ]

    if not momentum_values:
        print("错误：未找到 momentum 数据")
        return {}

    arr = np.array(momentum_values)

    # 基础统计
    stats = {
        "count": len(arr),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "median": float(np.median(arr)),
    }

    # 分位数
    percentiles = [10, 25, 50, 75, 90, 95]
    for p in percentiles:
        stats[f"p{p}"] = float(np.percentile(arr, p))

    # 按符号分类
    positive = arr[arr > 0]
    negative = arr[arr < 0]
    near_zero = arr[(arr >= -0.0001) & (arr <= 0.0001)]

    stats["positive_count"] = len(positive)
    stats["negative_count"] = len(negative)
    stats["near_zero_count"] = len(near_zero)
    stats["positive_ratio"] = len(positive) / len(arr)

    if len(positive) > 0:
        stats["positive_mean"] = float(np.mean(positive))
        stats["positive_median"] = float(np.median(positive))
        stats["positive_p50"] = float(np.percentile(positive, 50))
        stats["positive_p75"] = float(np.percentile(positive, 75))
        stats["positive_p90"] = float(np.percentile(positive, 90))

    return stats


def analyze_pbm_vs_performance(breakouts: list, label_key: str = "5d_20d") -> dict:
    """分析 PBM 与突破后表现的关系"""
    # 筛选有 momentum 和 label 的数据
    valid_data = []
    for bo in breakouts:
        momentum = bo.get("momentum")
        labels = bo.get("labels", {})
        label_value = labels.get(label_key) if labels else None

        if momentum is not None and label_value is not None:
            valid_data.append({
                "symbol": bo.get("symbol"),
                "date": bo.get("date"),
                "momentum": momentum,
                "label": label_value,
                "quality_score": bo.get("quality_score", 0),
            })

    if len(valid_data) < 10:
        print(f"警告：有效数据太少 ({len(valid_data)} 条)")
        return {}

    df = pd.DataFrame(valid_data)

    # 相关性分析
    correlation = df["momentum"].corr(df["label"])

    # 按 momentum 分组分析
    # 将 momentum 分成 5 个区间
    df["momentum_group"] = pd.qcut(
        df["momentum"], q=5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"]
    )

    group_stats = df.groupby("momentum_group", observed=True).agg({
        "label": ["mean", "median", "count"],
        "momentum": ["mean", "min", "max"],
    }).round(4)

    # 转换为字典
    result = {
        "correlation": float(correlation),
        "valid_count": len(df),
        "label_key": label_key,
        "group_stats": group_stats.to_dict(),
    }

    # 打印分组统计
    print(f"\n=== PBM vs 表现相关性分析 ===")
    print(f"相关系数: {correlation:.4f}")
    print(f"有效数据: {len(df)} 条")
    print(f"\n分组统计 (按 Momentum 分位数):")
    print(group_stats.to_string())

    return result


def suggest_thresholds(stats: dict) -> dict:
    """基于分布建议阈值"""
    # 策略1：基于正数分布的分位数
    # - 第一档：存在涨势 → 正数中位数
    # - 第二档：强劲涨势 → 正数 P75

    suggestions = {}

    if "positive_median" in stats:
        suggestions["level1_median"] = round(stats["positive_median"], 5)
        suggestions["level1_p50"] = round(stats["positive_p50"], 5)
        suggestions["level2_p75"] = round(stats["positive_p75"], 5)
        suggestions["level2_p90"] = round(stats["positive_p90"], 5)

    # 策略2：基于全局分布
    suggestions["global_p50"] = round(stats["p50"], 5)
    suggestions["global_p75"] = round(stats["p75"], 5)
    suggestions["global_p90"] = round(stats["p90"], 5)

    return suggestions


def print_report(stats: dict, suggestions: dict):
    """打印分析报告"""
    print("\n" + "=" * 60)
    print("PBM (Pre-Breakout Momentum) 分布分析报告")
    print("=" * 60)

    print(f"\n=== 基础统计 ===")
    print(f"样本数量: {stats['count']}")
    print(f"均值: {stats['mean']*1000:.3f}‰")
    print(f"标准差: {stats['std']*1000:.3f}‰")
    print(f"中位数: {stats['median']*1000:.3f}‰")
    print(f"最小值: {stats['min']*1000:.3f}‰")
    print(f"最大值: {stats['max']*1000:.3f}‰")

    print(f"\n=== 分位数 (千分比) ===")
    for p in [10, 25, 50, 75, 90, 95]:
        print(f"P{p}: {stats[f'p{p}']*1000:.3f}‰")

    print(f"\n=== 方向分布 ===")
    print(f"正值 (上涨): {stats['positive_count']} ({stats['positive_ratio']*100:.1f}%)")
    print(f"负值 (下跌): {stats['negative_count']}")
    print(f"近零值 (震荡): {stats['near_zero_count']}")

    if "positive_mean" in stats:
        print(f"\n=== 正值分布 ===")
        print(f"均值: {stats['positive_mean']*1000:.3f}‰")
        print(f"中位数: {stats['positive_median']*1000:.3f}‰")
        print(f"P75: {stats['positive_p75']*1000:.3f}‰")
        print(f"P90: {stats['positive_p90']*1000:.3f}‰")

    print(f"\n=== 阈值建议 ===")
    print("基于正数分布:")
    if "level1_median" in suggestions:
        print(f"  Level 1 (存在涨势): {suggestions['level1_median']*1000:.3f}‰ (正数中位数)")
        print(f"  Level 2 (强劲涨势): {suggestions['level2_p75']*1000:.3f}‰ (正数 P75)")
    print("基于全局分布:")
    print(f"  P50: {suggestions['global_p50']*1000:.3f}‰")
    print(f"  P75: {suggestions['global_p75']*1000:.3f}‰")
    print(f"  P90: {suggestions['global_p90']*1000:.3f}‰")

    print("\n" + "=" * 60)


def run_fresh_scan():
    """运行新扫描获取 PBM 数据"""
    import yaml
    from BreakoutStrategy.UI import ScanManager

    # 加载配置
    config_path = project_root / "configs" / "scan_config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    params_path = project_root / config["params"]["config_file"]
    with open(params_path, "r") as f:
        params = yaml.safe_load(f)

    data_dir = config["data"]["data_dir"]
    output_dir = project_root / config["output"]["output_dir"]
    num_workers = config["performance"]["num_workers"]

    # 提取参数
    detector_params = params["breakout_detector"]
    feature_calc_config = params.get("feature_calculator", {})
    quality_scorer_config = params.get("quality_scorer", {})

    # 使用 UIScanConfigLoader 处理扫描模式
    from BreakoutStrategy.UI.config import UIScanConfigLoader
    scan_config_loader = UIScanConfigLoader(config_path)

    if scan_config_loader.is_csv_mode():
        stock_time_ranges = scan_config_loader.get_stock_time_ranges()
        symbols = list(stock_time_ranges.keys())
        start_date = None
        end_date = None
    else:
        import os
        symbols = [f[:-4] for f in os.listdir(data_dir) if f.endswith(".pkl")]
        stock_time_ranges = None
        start_date = scan_config_loader.get_start_date()
        end_date = scan_config_loader.get_end_date()

    # 限制扫描数量（可选）
    max_stocks = config["data"].get("max_stocks")
    if max_stocks:
        symbols = symbols[:max_stocks]
        if stock_time_ranges:
            stock_time_ranges = {k: stock_time_ranges[k] for k in symbols}

    print(f"扫描 {len(symbols)} 只股票...")

    # 创建 ScanManager
    manager = ScanManager(
        output_dir=output_dir,
        total_window=detector_params["total_window"],
        min_side_bars=detector_params["min_side_bars"],
        min_relative_height=detector_params["min_relative_height"],
        exceed_threshold=detector_params["exceed_threshold"],
        peak_supersede_threshold=detector_params["peak_supersede_threshold"],
        start_date=start_date,
        end_date=end_date,
        feature_calc_config=feature_calc_config,
        scorer_config=quality_scorer_config,
    )

    # 运行扫描
    if stock_time_ranges:
        results = manager.parallel_scan(
            symbols,
            data_dir=str(data_dir),
            num_workers=num_workers,
            stock_time_ranges=stock_time_ranges,
        )
    else:
        results = manager.parallel_scan(
            symbols,
            data_dir=str(data_dir),
            num_workers=num_workers,
        )

    # 保存结果
    output_file = manager.save_results(results, filename="pbm_analysis.json")
    print(f"结果已保存: {output_file}")

    return output_file


def main():
    import argparse

    parser = argparse.ArgumentParser(description="PBM 分布分析")
    parser.add_argument(
        "--scan", action="store_true",
        help="运行新扫描（否则使用现有结果）"
    )
    parser.add_argument(
        "--input", type=str, default=None,
        help="扫描结果 JSON 文件路径"
    )
    parser.add_argument(
        "--label", type=str, default="5d_20d",
        help="用于相关性分析的标签键"
    )
    args = parser.parse_args()

    # 确定数据来源
    if args.scan:
        json_path = run_fresh_scan()
    elif args.input:
        json_path = args.input
    else:
        # 使用默认路径
        default_path = project_root / "outputs/scan_results/pbm_analysis.json"
        if not default_path.exists():
            print("未找到现有结果，开始新扫描...")
            json_path = run_fresh_scan()
        else:
            json_path = str(default_path)

    print(f"\n加载数据: {json_path}")
    breakouts = load_scan_results(json_path)
    print(f"加载 {len(breakouts)} 个突破点")

    # 分析分布
    stats = analyze_pbm_distribution(breakouts)
    if not stats:
        return

    # 建议阈值
    suggestions = suggest_thresholds(stats)

    # 打印报告
    print_report(stats, suggestions)

    # 相关性分析
    analyze_pbm_vs_performance(breakouts, args.label)


if __name__ == "__main__":
    main()
