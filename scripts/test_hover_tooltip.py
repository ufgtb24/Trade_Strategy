"""
测试悬浮窗口智能定位功能

验证：
1. 动态四象限定位
2. 十字线辅助显示
3. 边界情况处理
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


def create_test_data(n=200):
    """创建测试数据"""
    dates = pd.date_range('2024-01-01', periods=n, freq='D')

    np.random.seed(42)
    base_price = 100
    prices = []

    for i in range(n):
        # 创建一些峰值
        if i in [30, 60, 90, 120, 150]:
            price = base_price + 8
        # 创建一些突破
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
    print("悬浮窗口智能定位功能测试")
    print("=" * 60)

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

    print("\n" + "=" * 60)
    print("数据准备完成！")
    print("=" * 60)
    print(f"\n突破详情:")
    for i, bt in enumerate(breakthroughs):
        print(f"  {i+1}. 日期: {bt.date}, 突破 {bt.num_peaks_broken} 个峰值, "
              f"Peak IDs: {bt.broken_peak_ids}")

    print("\n" + "=" * 60)
    print("启动交互式UI进行测试...")
    print("=" * 60)
    print("\n请在UI中移动鼠标到不同位置，验证：")
    print("  1. 悬浮窗口位置会根据鼠标位置自动调整")
    print("  2. 显示蓝色虚线十字线")
    print("  3. 悬浮窗口始终在屏幕内，不会被截断")
    print("  4. Peak IDs 正确显示在 hover 信息中\n")

    # 启动交互式UI
    import tkinter as tk
    import matplotlib
    matplotlib.use('TkAgg')

    from BreakthroughStrategy.visualization.interactive import InteractiveUI

    root = tk.Tk()
    app = InteractiveUI(root)

    # 手动设置数据（模拟加载扫描结果）
    app.symbol_var.set("TEST")
    app.df = df
    app.breakthroughs = breakthroughs
    app.detector = detector

    # 更新图表
    app.chart_manager.update_chart(df, breakthroughs, detector, "TEST")

    # 启动UI
    root.mainloop()


if __name__ == "__main__":
    main()
