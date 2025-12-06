"""
测试改进后的集成系统

验证：
1. 增量式突破检测
2. 多峰值突破
3. 改进的评分系统（密集度修复、峰值质量综合）
"""

import os
import pickle
import sys

# 添加项目根目录到path
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, project_root)

from BreakthroughStrategy.analysis import (
    BreakthroughDetector,
    FeatureCalculator,
    QualityScorer,
)


def test_integrated_system():
    """测试完整的集成系统"""
    print("=" * 80)
    print("测试改进后的突破检测系统")
    print("=" * 80)
    print()

    # 加载数据
    print("[1] 加载AAPL数据...")
    import os

    base_path = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    data_path = os.path.join(base_path, "datasets", "process_pkls", "AAPL.pkl")
    df = pickle.load(open(data_path, "rb"))
    print(f"    数据: {len(df)}天 ({df.index[0].date()} ~ {df.index[-1].date()})")
    print()

    # 创建检测器（不使用缓存，用于回测）
    print("[2] 创建突破检测器（增量式）...")
    detector = BreakthroughDetector(
        symbol="AAPL",
        window=5,
        exceed_threshold=0.005,
        peak_supersede_threshold=0.03,
        use_cache=False,
    )
    print(f"    window={detector.window}")
    print(f"    exceed_threshold={detector.exceed_threshold}")
    print(f"    peak_supersede_threshold={detector.peak_supersede_threshold}")
    print()

    # 批量添加历史数据，获取所有突破
    print("[3] 批量添加历史数据，检测突破...")
    breakout_infos = detector.batch_add_bars(df, return_breakouts=True)
    print(f"    识别到 {len(breakout_infos)} 个突破")
    print(f"    当前活跃峰值: {len(detector.active_peaks)} 个")
    print()

    # 创建特征计算器和评分器
    print("[4] 创建特征计算器和评分器...")
    feature_calc = FeatureCalculator()
    scorer = QualityScorer()
    print()

    # 计算丰富特征
    print("[5] 计算丰富特征...")
    breakthroughs = []
    for info in breakout_infos:
        # 先为峰值评分
        for peak in info.broken_peaks:
            if peak.quality_score is None:
                scorer.score_peak(peak)

        # 计算突破特征
        bt = feature_calc.enrich_breakthrough(df, info, "AAPL")
        breakthroughs.append(bt)

    print(f"    转换为 {len(breakthroughs)} 个Breakthrough对象")
    print()

    # 质量评分
    print("[6] 质量评分...")
    scorer.score_breakthroughs_batch(breakthroughs)
    print("    完成评分")
    print()

    # 统计分析
    print("=" * 80)
    print("统计分析")
    print("=" * 80)
    print()

    scores = [bt.quality_score for bt in breakthroughs if bt.quality_score]
    if scores:
        print("突破质量评分:")
        print(f"  平均分: {sum(scores) / len(scores):.1f}")
        print(f"  最高分: {max(scores):.1f}")
        print(f"  最低分: {min(scores):.1f}")
        print()

    # 统计多峰值突破
    multi_peak_breakthroughs = [bt for bt in breakthroughs if bt.num_peaks_broken > 1]
    print("多峰值突破:")
    print(f"  数量: {len(multi_peak_breakthroughs)} / {len(breakthroughs)}")
    if multi_peak_breakthroughs:
        avg_peaks = sum(bt.num_peaks_broken for bt in multi_peak_breakthroughs) / len(
            multi_peak_breakthroughs
        )
        max_peaks = max(bt.num_peaks_broken for bt in multi_peak_breakthroughs)
        print(f"  平均突破峰值数: {avg_peaks:.1f}")
        print(f"  最多突破峰值数: {max_peaks}")
    print()

    # 按质量排序，显示Top 5
    print("=" * 80)
    print("Top 5 突破（按质量评分）")
    print("=" * 80)
    print()

    sorted_breakthroughs = sorted(
        breakthroughs, key=lambda x: x.quality_score or 0, reverse=True
    )

    for i, bt in enumerate(sorted_breakthroughs[:5], 1):
        print(f"[{i}] {bt.date} (索引: {bt.index})")
        print(f"    突破价格: ${bt.price:.2f}")
        print(
            f"    突破类型: {bt.breakthrough_type}, 涨幅: {bt.price_change_pct * 100:.2f}%"
        )
        print(
            f"    放量: {bt.volume_surge_ratio:.2f}倍, 连续性: {bt.continuity_days}天, 稳定性: {bt.stability_score:.0f}%"
        )
        print("    ---")
        print(f"    被突破峰值数: {bt.num_peaks_broken}")

        if bt.num_peaks_broken > 1:
            # 显示被突破的所有峰值
            prices = [p.price for p in bt.broken_peaks]
            qualities = [p.quality_score for p in bt.broken_peaks if p.quality_score]

            print(f"    峰值价格: {prices}")
            print(f"    价格范围: ${bt.peak_price_range:.2f}")

            if qualities:
                print(
                    f"    峰值质量: min={min(qualities):.1f}, avg={sum(qualities) / len(qualities):.1f}, max={max(qualities):.1f}"
                )
        else:
            peak = bt.broken_peaks[0]
            print(f"    峰值价格: ${peak.price:.2f}")
            print(f"    峰值质量: {peak.quality_score:.1f}")

        print("    ---")
        print(f"    ⭐️ 突破质量: {bt.quality_score:.1f}/100")
        print()

    # 显示一个多峰值突破的详细案例
    if multi_peak_breakthroughs:
        print("=" * 80)
        print("多峰值突破详细案例")
        print("=" * 80)
        print()

        # 选择突破峰值最多的案例
        best_multi = max(multi_peak_breakthroughs, key=lambda x: x.num_peaks_broken)

        print(f"日期: {best_multi.date}")
        print(f"突破价格: ${best_multi.price:.2f}")
        print(f"突破了 {best_multi.num_peaks_broken} 个峰值:")
        print()

        for i, peak in enumerate(best_multi.broken_peaks, 1):
            print(f"  峰值{i}:")
            print(f"    日期: {peak.date}")
            print(f"    价格: ${peak.price:.2f}")
            print(f"    质量: {peak.quality_score:.1f}/100")
            print(f"    放量: {peak.volume_surge_ratio:.2f}倍")
            print(
                f"    压制: 左{peak.left_suppression_days}天, 右{peak.right_suppression_days}天"
            )
            print()

        print("阻力区分析:")
        prices = sorted([p.price for p in best_multi.broken_peaks])
        avg_price = sum(prices) / len(prices)
        print(f"  价格范围: ${min(prices):.2f} ~ ${max(prices):.2f}")
        print(
            f"  价格差距: ${best_multi.peak_price_range:.2f} ({best_multi.peak_price_range / avg_price * 100:.2f}%)"
        )
        print()

        print(f"评分: {best_multi.quality_score:.1f}/100")

    print()
    print("=" * 80)
    print("✓ 测试完成！")
    print("=" * 80)


if __name__ == "__main__":
    test_integrated_system()
