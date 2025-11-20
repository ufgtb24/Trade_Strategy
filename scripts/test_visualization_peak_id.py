"""
测试可视化模块的 Peak ID 功能

验证以下功能：
1. Peak 三角标记旁边显示 id:score
2. 突破标记为圆圈并显示数字
3. 圆圈上方显示 peaks id 列表
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from BreakthroughStrategy.analysis import BreakthroughDetector
from BreakthroughStrategy.analysis.features import FeatureCalculator
from BreakthroughStrategy.analysis.quality_scorer import QualityScorer
from BreakthroughStrategy.visualization import BreakthroughPlotter


def create_test_data(n=200):
    """创建测试数据，包含明显的峰值和突破"""
    dates = pd.date_range('2024-01-01', periods=n, freq='D')

    np.random.seed(42)
    base_price = 100
    prices = []

    for i in range(n):
        # 在特定位置创建峰值
        if i in [30, 60, 90, 120, 150]:
            price = base_price + 8
        # 在特定位置创建突破（突破多个峰值）
        elif i in [100, 160]:
            price = base_price + 12
        else:
            price = base_price + np.random.randn() * 1.5

        prices.append(price)
        base_price = price * 0.98 + 100 * 0.02

    df = pd.DataFrame({
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': np.random.randint(1000000, 2000000, n)
    }, index=dates)

    return df


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("可视化模块 Peak ID 功能测试")
    print("=" * 60)

    # 创建输出目录
    output_dir = project_root / "outputs" / "test_visualization"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建测试数据
    print("\n创建测试数据...")
    df = create_test_data()

    # 运行突破检测
    print("运行突破检测...")
    detector = BreakthroughDetector(symbol="TEST", window=5)
    breakout_infos = detector.batch_add_bars(df, return_breakouts=True)

    print(f"  检测到 {len(breakout_infos)} 个突破")
    print(f"  活跃峰值: {len(detector.active_peaks)}")

    # 特征计算和质量评分
    print("计算特征和质量评分...")
    feature_calc = FeatureCalculator()
    quality_scorer = QualityScorer()

    breakthroughs = []
    for breakout_info in breakout_infos:
        # 为峰值评分
        for peak in breakout_info.broken_peaks:
            if peak.quality_score is None:
                quality_scorer.score_peak(peak)

        # 计算完整特征
        bt = feature_calc.enrich_breakthrough(df, breakout_info, "TEST")
        breakthroughs.append(bt)

    # 批量评分
    quality_scorer.score_breakthroughs_batch(breakthroughs)

    # 为活跃峰值评分
    for peak in detector.active_peaks:
        if peak.quality_score is None:
            quality_scorer.score_peak(peak)

    # 打印详细信息
    print(f"\n突破详情:")
    for i, bt in enumerate(breakthroughs):
        print(f"  {i+1}. 日期: {bt.date}, 突破 {bt.num_peaks_broken} 个峰值, "
              f"Peak IDs: {bt.broken_peak_ids}, 质量: {bt.quality_score:.1f}")

    # 生成可视化
    print("\n生成可视化图表...")
    plotter = BreakthroughPlotter()

    # 完整分析图
    save_path = output_dir / "test_peak_id_full_analysis.png"
    plotter.plot_full_analysis(
        df=df,
        breakthroughs=breakthroughs,
        detector=detector,
        title="Peak ID Feature Test - Full Analysis",
        save_path=save_path,
        show=False
    )
    print(f"  ✓ 完整分析图已保存: {save_path}")

    # 突破详情图（选择一个多峰值突破）
    multi_peak_bts = [bt for bt in breakthroughs if bt.num_peaks_broken > 1]
    if multi_peak_bts:
        bt = multi_peak_bts[0]
        save_path = output_dir / "test_peak_id_detail.png"
        plotter.plot_breakout_detail(
            df=df,
            breakthrough=bt,
            context_days=50,
            save_path=save_path,
            show=False
        )
        print(f"  ✓ 突破详情图已保存: {save_path}")
        print(f"    - 突破日期: {bt.date}")
        print(f"    - 突破峰值数: {bt.num_peaks_broken}")
        print(f"    - Peak IDs: {bt.broken_peak_ids}")

    print("\n" + "=" * 60)
    print("可视化测试完成！")
    print("=" * 60)
    print(f"\n请查看生成的图表以验证:")
    print(f"  1. Peak 三角标记旁边显示 'id:score'")
    print(f"  2. 突破标记为圆圈，圆圈中心显示突破的峰值数量")
    print(f"  3. 圆圈上方显示被突破的 peak id 列表 (如 [1,2,3])")
    print(f"\n图表位置: {output_dir}\n")


if __name__ == "__main__":
    main()
