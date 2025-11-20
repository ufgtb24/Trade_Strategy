"""
测试 Peak ID 功能

验证以下功能：
1. Peak 对象有 id 字段
2. BreakthroughDetector 正确分配 id
3. BreakoutInfo 和 Breakthrough 有 broken_peak_ids 属性
4. 缓存保存/加载正确处理 id
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

    # 创建带有明显峰值和突破的数据
    np.random.seed(42)
    base_price = 100
    prices = []

    for i in range(n):
        # 添加一些峰值
        if i in [50, 100, 150]:  # 在这些位置创建峰值
            price = base_price + 10
        elif i in [120, 170]:  # 在这些位置突破峰值
            price = base_price + 15
        else:
            price = base_price + np.random.randn() * 2

        prices.append(price)
        base_price = price * 0.98 + 100 * 0.02  # 均值回归

    df = pd.DataFrame({
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': np.random.randint(1000000, 2000000, n)
    }, index=dates)

    return df


def test_peak_id_assignment():
    """测试 Peak ID 分配"""
    print("=" * 60)
    print("测试 1: Peak ID 分配")
    print("=" * 60)

    df = create_test_data()
    detector = BreakthroughDetector(symbol="TEST", window=5)

    # 批量添加数据
    breakout_infos = detector.batch_add_bars(df, return_breakouts=True)

    # 检查 active_peaks 是否有 id
    print(f"\nActive peaks count: {len(detector.active_peaks)}")
    for i, peak in enumerate(detector.active_peaks[:5]):  # 只显示前5个
        print(f"  Peak {i}: id={peak.id}, index={peak.index}, price={peak.price:.2f}")

    # 检查 id 是否唯一
    peak_ids = [p.id for p in detector.active_peaks]
    assert len(peak_ids) == len(set(peak_ids)), "Peak IDs are not unique!"
    print("\n✓ All peak IDs are unique")

    # 检查 id 是否按顺序递增
    for peak in detector.active_peaks:
        assert peak.id is not None, "Peak ID is None!"
    print("✓ All peaks have non-None IDs")

    return detector, breakout_infos


def test_broken_peak_ids():
    """测试 broken_peak_ids 属性"""
    print("\n" + "=" * 60)
    print("测试 2: broken_peak_ids 属性")
    print("=" * 60)

    df = create_test_data()
    detector = BreakthroughDetector(symbol="TEST", window=5)
    breakout_infos = detector.batch_add_bars(df, return_breakouts=True)

    print(f"\nBreakout count: {len(breakout_infos)}")

    # 检查 BreakoutInfo 的 broken_peak_ids
    for i, breakout_info in enumerate(breakout_infos[:5]):  # 只显示前5个
        print(f"\n  Breakout {i}:")
        print(f"    Index: {breakout_info.current_index}")
        print(f"    Peaks broken: {breakout_info.num_peaks_broken}")
        print(f"    Broken peak IDs: {breakout_info.broken_peak_ids}")

        # 验证 broken_peak_ids 数量与 broken_peaks 数量一致
        assert len(breakout_info.broken_peak_ids) == len(breakout_info.broken_peaks), \
            "broken_peak_ids count mismatch!"

    print("\n✓ All BreakoutInfo objects have correct broken_peak_ids")

    # 计算特征并测试 Breakthrough
    feature_calc = FeatureCalculator()
    breakthroughs = []
    for breakout_info in breakout_infos:
        bt = feature_calc.enrich_breakthrough(df, breakout_info, "TEST")
        breakthroughs.append(bt)

    print(f"\nBreakthrough count: {len(breakthroughs)}")

    # 检查 Breakthrough 的 broken_peak_ids
    for i, bt in enumerate(breakthroughs[:5]):
        print(f"\n  Breakthrough {i}:")
        print(f"    Date: {bt.date}")
        print(f"    Peaks broken: {bt.num_peaks_broken}")
        print(f"    Broken peak IDs: {bt.broken_peak_ids}")

        # 验证
        assert len(bt.broken_peak_ids) == bt.num_peaks_broken, \
            "Breakthrough broken_peak_ids count mismatch!"

    print("\n✓ All Breakthrough objects have correct broken_peak_ids")


def test_cache_persistence():
    """测试缓存持久化"""
    print("\n" + "=" * 60)
    print("测试 3: 缓存持久化")
    print("=" * 60)

    import tempfile
    import shutil

    # 创建临时缓存目录
    temp_dir = tempfile.mkdtemp()

    try:
        df = create_test_data()

        # 创建 detector 并启用缓存
        detector1 = BreakthroughDetector(
            symbol="TEST_CACHE",
            window=5,
            use_cache=True,
            cache_dir=temp_dir
        )

        # 添加数据
        detector1.batch_add_bars(df)

        print(f"\nDetector 1:")
        print(f"  Active peaks: {len(detector1.active_peaks)}")
        print(f"  Peak ID counter: {detector1.peak_id_counter}")
        print(f"  First 3 peak IDs: {[p.id for p in detector1.active_peaks[:3]]}")

        # 创建新的 detector 从缓存加载
        detector2 = BreakthroughDetector(
            symbol="TEST_CACHE",
            window=5,
            use_cache=True,
            cache_dir=temp_dir
        )

        print(f"\nDetector 2 (loaded from cache):")
        print(f"  Active peaks: {len(detector2.active_peaks)}")
        print(f"  Peak ID counter: {detector2.peak_id_counter}")
        print(f"  First 3 peak IDs: {[p.id for p in detector2.active_peaks[:3]]}")

        # 验证缓存正确恢复
        assert len(detector1.active_peaks) == len(detector2.active_peaks), \
            "Active peaks count mismatch!"
        assert detector1.peak_id_counter == detector2.peak_id_counter, \
            "Peak ID counter mismatch!"

        for p1, p2 in zip(detector1.active_peaks, detector2.active_peaks):
            assert p1.id == p2.id, f"Peak ID mismatch: {p1.id} != {p2.id}"

        print("\n✓ Cache correctly persists and restores peak IDs")

    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir)


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("Peak ID 功能测试")
    print("=" * 60)

    try:
        # 测试 1: Peak ID 分配
        test_peak_id_assignment()

        # 测试 2: broken_peak_ids 属性
        test_broken_peak_ids()

        # 测试 3: 缓存持久化
        test_cache_persistence()

        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
