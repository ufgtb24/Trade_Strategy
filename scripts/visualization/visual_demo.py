"""
可视化演示脚本
使用 yfinance 下载最新数据并生成分析图表
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import yfinance as yf

from BreakthroughStrategy.analysis import BreakthroughDetector
from BreakthroughStrategy.analysis.features import FeatureCalculator
from BreakthroughStrategy.analysis.quality_scorer import QualityScorer
from BreakthroughStrategy.visualization import BreakthroughPlotter


def main():
    # ========== 配置参数 ==========
    symbol = "AAPL"
    output_dir = project_root / "outputs" / "visualization"
    output_dir.mkdir(parents=True, exist_ok=True)

    window = 5
    exceed_threshold = 0.005

    # ========== 下载数据 ==========
    print(f"Downloading data for {symbol}...")
    df = yf.download(symbol, start="2020-01-01", end="2025-11-25", progress=False)

    # 标准化列名（处理 MultiIndex）
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [col.lower() if isinstance(col, str) else col for col in df.columns]

    print(f"Data downloaded: {len(df)} rows")
    print(f"Date range: {df.index.min()} to {df.index.max()}")
    print(f"Columns: {df.columns.tolist()}")

    # ========== 运行突破检测 ==========
    print("\nRunning breakthrough detection...")
    detector = BreakthroughDetector(
        symbol=symbol, window=window, exceed_threshold=exceed_threshold
    )

    # 批量添加数据并获取突破信息
    breakout_infos = detector.batch_add_bars(df, return_breakouts=True)
    print(f"Detected {len(breakout_infos)} raw breakthroughs")
    print(f"Active peaks: {len(detector.active_peaks)}")

    # ========== 特征计算和质量评分 ==========
    print("\nCalculating features and quality scores...")
    feature_calc = FeatureCalculator()
    quality_scorer = QualityScorer()

    breakthroughs = []
    for breakout_info in breakout_infos:
        # 先为峰值评分
        for peak in breakout_info.broken_peaks:
            if peak.quality_score is None:
                quality_scorer.score_peak(peak)

        # 计算完整特征
        bt = feature_calc.enrich_breakthrough(df, breakout_info, symbol)
        breakthroughs.append(bt)

    # 批量计算突破质量评分
    quality_scorer.score_breakthroughs_batch(breakthroughs)

    # 对所有活跃峰值评分
    for peak in detector.active_peaks:
        if peak.quality_score is None:
            quality_scorer.score_peak(peak)

    print(f"Enriched {len(breakthroughs)} breakthroughs")

    # 按质量分数排序
    breakthroughs_sorted = sorted(
        breakthroughs,
        key=lambda bt: bt.quality_score if bt.quality_score else 0,
        reverse=True,
    )

    # ========== 可视化 ==========
    print("\nGenerating visualizations...")
    plotter = BreakthroughPlotter()

    # 1. 完整分析图
    print("  [1/3] Generating full analysis plot...")
    plotter.plot_full_analysis(
        df=df,
        breakthroughs=breakthroughs,
        detector=detector,
        title=f"{symbol} - Breakthrough Analysis",
        save_path=output_dir / f"{symbol}_full_analysis.png",
        show=False,
    )

    # 2. Top 3 突破详情图
    print("  [2/3] Generating top 3 breakthrough details...")
    top3_breakthroughs = breakthroughs_sorted[:3]
    for i, bt in enumerate(top3_breakthroughs, 1):
        plotter.plot_breakout_detail(
            df=df,
            breakthrough=bt,
            context_days=50,
            save_path=output_dir / f"{symbol}_detail_top{i}.png",
            show=False,
        )

    # 3. 多峰值突破案例集
    print("  [3/3] Generating multi-peak cases...")
    multi_peak_bts = [bt for bt in breakthroughs if bt.num_peaks_broken > 1]
    if multi_peak_bts:
        plotter.plot_multi_peak_cases(
            df=df,
            multi_peak_breakthroughs=multi_peak_bts,
            top_n=6,
            save_path=output_dir / f"{symbol}_multi_peak_cases.png",
            show=False,
        )
        print(f"    Found {len(multi_peak_bts)} multi-peak breakthroughs")
    else:
        print("    No multi-peak breakthroughs found")

    # 4. 统计摘要
    print(f"\n{'=' * 60}")
    print("SUMMARY STATISTICS")
    print(f"{'=' * 60}")
    print(f"Total Breakthroughs: {len(breakthroughs)}")
    if breakthroughs:
        print(
            f"Multi-Peak Breakthroughs: {len(multi_peak_bts)} ({len(multi_peak_bts) / len(breakthroughs) * 100:.1f}%)"
        )
    print(f"Active Peaks: {len(detector.active_peaks)}")

    if breakthroughs:
        quality_scores = [bt.quality_score for bt in breakthroughs if bt.quality_score]
        if quality_scores:
            print("\nQuality Scores:")
            print(f"  Average: {sum(quality_scores) / len(quality_scores):.1f}")
            print(
                f"  Top 3 Average: {sum(quality_scores[:3]) / min(3, len(quality_scores)):.1f}"
            )
            print(f"  Max: {max(quality_scores):.1f}")
            print(f"  Min: {min(quality_scores):.1f}")

        print("\nTop 3 Breakthroughs:")
        for i, bt in enumerate(top3_breakthroughs, 1):
            print(
                f"  {i}. {bt.date} | {bt.num_peaks_broken} peaks | Q={bt.quality_score:.1f}"
            )

    print(f"\n{'=' * 60}")
    print(f"Visualizations saved to: {output_dir}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
