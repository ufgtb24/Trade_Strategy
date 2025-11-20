"""
创建用于测试悬浮窗口的数据文件

生成扫描结果 JSON 文件，可以在交互式查看器中加载
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import json
from datetime import date

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
    """主函数"""
    print("\n" + "=" * 60)
    print("创建悬浮窗口测试数据")
    print("=" * 60)

    output_dir = project_root / "outputs" / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建测试数据
    print("\n创建测试数据...")
    df = create_test_data()

    # 运行突破检测
    print("运行突破检测...")
    detector = BreakthroughDetector(symbol="HOVER_TEST", window=5)
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
        bt = feature_calc.enrich_breakthrough(df, breakout_info, "HOVER_TEST")
        breakthroughs.append(bt)

    # 批量评分
    quality_scorer.score_breakthroughs_batch(breakthroughs)

    # 为活跃峰值评分
    for peak in detector.active_peaks:
        if peak.quality_score is None:
            quality_scorer.score_peak(peak)

    # 保存为 JSON（模拟扫描结果格式）
    print("\n保存数据到 JSON...")

    scan_results = {
        "symbol": "HOVER_TEST",
        "scan_date": date.today().isoformat(),
        "total_breakthroughs": len(breakthroughs),
        "breakthroughs": []
    }

    for bt in breakthroughs:
        bt_data = {
            "date": bt.date.isoformat(),
            "price": float(bt.price),
            "index": int(bt.index),
            "num_peaks_broken": int(bt.num_peaks_broken),
            "broken_peak_ids": [int(id) for id in bt.broken_peak_ids],
            "breakthrough_type": str(bt.breakthrough_type),
            "price_change_pct": float(bt.price_change_pct),
            "gap_up": bool(bt.gap_up),
            "gap_up_pct": float(bt.gap_up_pct),
            "volume_surge_ratio": float(bt.volume_surge_ratio),
            "continuity_days": int(bt.continuity_days),
            "stability_score": float(bt.stability_score),
            "quality_score": float(bt.quality_score) if bt.quality_score else None,
            "broken_peaks": [
                {
                    "index": int(p.index),
                    "price": float(p.price),
                    "date": p.date.isoformat(),
                    "id": int(p.id) if p.id is not None else None,
                    "quality_score": float(p.quality_score) if p.quality_score else None
                }
                for p in bt.broken_peaks
            ]
        }
        scan_results["breakthroughs"].append(bt_data)

    # 添加 active_peaks
    scan_results["active_peaks"] = [
        {
            "index": int(p.index),
            "price": float(p.price),
            "date": p.date.isoformat(),
            "id": int(p.id) if p.id is not None else None,
            "quality_score": float(p.quality_score) if p.quality_score else None
        }
        for p in detector.active_peaks
    ]

    # 保存 JSON
    output_file = output_dir / "hover_test_scan.json"
    with open(output_file, 'w') as f:
        json.dump(scan_results, f, indent=2)

    print(f"\n✓ 数据已保存到: {output_file}")

    # 保存 CSV（OHLCV 数据）
    csv_file = output_dir / "hover_test_ohlcv.csv"
    df.to_csv(csv_file)
    print(f"✓ OHLCV数据已保存到: {csv_file}")

    print("\n" + "=" * 60)
    print("测试数据创建完成！")
    print("=" * 60)
    print("\n下一步：")
    print("  1. 运行交互式查看器:")
    print("     python scripts/visualization/interactive_viewer.py")
    print("  2. 加载扫描结果:")
    print(f"     {output_file}")
    print("  3. 在图表上移动鼠标，验证:")
    print("     - 悬浮窗口位置自动调整")
    print("     - 显示蓝色虚线十字线")
    print("     - 窗口始终在屏幕内")
    print("     - Peak IDs 正确显示\n")


if __name__ == "__main__":
    main()
