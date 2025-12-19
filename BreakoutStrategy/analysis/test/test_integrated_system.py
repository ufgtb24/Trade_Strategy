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

from BreakoutStrategy.analysis import (
    BreakoutDetector,
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
    detector = BreakoutDetector(
        symbol="AAPL",
        total_window=10,
        min_side_bars=2,
        min_relative_height=0.05,
        exceed_threshold=0.005,
        peak_supersede_threshold=0.03,
        use_cache=False,
    )
    print(f"    total_window={detector.total_window}, min_side_bars={detector.min_side_bars}")
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
    breakouts = []
    for info in breakout_infos:
        # 计算突破特征（传递 detector 以获取连续突破信息）
        bo = feature_calc.enrich_breakout(df, info, "AAPL", detector=detector)
        breakouts.append(bo)

    print(f"    转换为 {len(breakouts)} 个Breakout对象")
    print()

    # 质量评分
    print("[6] 质量评分...")
    scorer.score_breakouts_batch(breakouts)
    print("    完成评分")
    print()

    # 统计分析
    print("=" * 80)
    print("统计分析")
    print("=" * 80)
    print()

    scores = [bo.quality_score for bo in breakouts if bo.quality_score]
    if scores:
        print("突破质量评分:")
        print(f"  平均分: {sum(scores) / len(scores):.1f}")
        print(f"  最高分: {max(scores):.1f}")
        print(f"  最低分: {min(scores):.1f}")
        print()

    # 统计多峰值突破
    multi_peak_breakouts = [bo for bo in breakouts if bo.num_peaks_broken > 1]
    print("多峰值突破:")
    print(f"  数量: {len(multi_peak_breakouts)} / {len(breakouts)}")
    if multi_peak_breakouts:
        avg_peaks = sum(bo.num_peaks_broken for bo in multi_peak_breakouts) / len(
            multi_peak_breakouts
        )
        max_peaks = max(bo.num_peaks_broken for bo in multi_peak_breakouts)
        print(f"  平均突破峰值数: {avg_peaks:.1f}")
        print(f"  最多突破峰值数: {max_peaks}")
    print()

    # 按质量排序，显示Top 5
    print("=" * 80)
    print("Top 5 突破（按质量评分）")
    print("=" * 80)
    print()

    sorted_breakouts = sorted(
        breakouts, key=lambda x: x.quality_score or 0, reverse=True
    )

    for i, bo in enumerate(sorted_breakouts[:5], 1):
        print(f"[{i}] {bo.date} (索引: {bo.index})")
        print(f"    突破价格: ${bo.price:.2f}")
        print(
            f"    突破类型: {bo.breakout_type}, 涨幅: {bo.price_change_pct * 100:.2f}%"
        )
        print(
            f"    放量: {bo.volume_surge_ratio:.2f}倍, 连续性: {bo.continuity_days}天, 稳定性: {bo.stability_score:.0f}%"
        )
        print("    ---")
        print(f"    被突破峰值数: {bo.num_peaks_broken}")

        if bo.num_peaks_broken > 1:
            # 显示被突破的所有峰值
            prices = [p.price for p in bo.broken_peaks]
            print(f"    峰值价格: {prices}")
            print(f"    价格范围: ${bo.peak_price_range:.2f}")
        else:
            peak = bo.broken_peaks[0]
            print(f"    峰值价格: ${peak.price:.2f}")

        print("    ---")
        print(f"    ⭐️ 突破质量: {bo.quality_score:.1f}/100")
        print()

    # 显示一个多峰值突破的详细案例
    if multi_peak_breakouts:
        print("=" * 80)
        print("多峰值突破详细案例")
        print("=" * 80)
        print()

        # 选择突破峰值最多的案例
        best_multi = max(multi_peak_breakouts, key=lambda x: x.num_peaks_broken)

        print(f"日期: {best_multi.date}")
        print(f"突破价格: ${best_multi.price:.2f}")
        print(f"突破了 {best_multi.num_peaks_broken} 个峰值:")
        print()

        for i, peak in enumerate(best_multi.broken_peaks, 1):
            print(f"  峰值{i}:")
            print(f"    日期: {peak.date}")
            print(f"    价格: ${peak.price:.2f}")
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
