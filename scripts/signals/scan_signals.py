"""
绝对信号扫描脚本

扫描所有股票，统计绝对信号数量，输出排序结果。
"""
import os
import sys
from datetime import date
from pathlib import Path

import yaml

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from BreakoutStrategy.signals import AbsoluteSignalScanner


def main():
    # ========== 参数配置 ==========
    # 数据目录
    data_dir = project_root / "datasets" / "pkls"

    # 配置文件
    config_path = project_root / "configs" / "signals" / "absolute_signals.yaml"

    # 输出数量限制
    top_n = 50

    # 统计截止日期（None 表示今天）
    as_of_date = None

    # ========== 加载配置 ==========
    config = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        print(f"Loaded config from {config_path}")
    else:
        print(f"Config not found, using defaults")

    # ========== 获取股票列表 ==========
    pkl_files = list(data_dir.glob("*.pkl"))
    symbols = [f.stem for f in pkl_files]
    print(f"Found {len(symbols)} stocks in {data_dir}")

    # ========== 执行扫描 ==========
    scanner = AbsoluteSignalScanner(config=config)

    if as_of_date is None:
        as_of_date = date.today()

    print(f"\nScanning {len(symbols)} stocks...")
    print(f"As of date: {as_of_date}")
    print(f"Lookback: {config.get('aggregator', {}).get('lookback_days', 42)} days")
    print()

    results = scanner.scan(
        symbols=symbols,
        data_dir=data_dir,
        scan_date=as_of_date,
        max_workers=os.cpu_count()-2,
    )

    # ========== 输出结果 ==========
    print("=" * 95)
    print(f"Absolute Signals Scan ({as_of_date})")
    print(f"Lookback: {config.get('aggregator', {}).get('lookback_days', 42)} days | Stocks: {len(symbols)}")
    print("=" * 95)
    print(f"{'Rank':<6}{'Symbol':<10}{'Signals':<10}{'Weighted':<10}{'Latest':<14}{'Sequence'}")
    print("-" * 95)

    turbulent_count = 0
    for i, stats in enumerate(results[:top_n], 1):
        marker = " *" if stats.turbulent else ""
        if stats.turbulent:
            turbulent_count += 1
        print(
            f"{i:<6}{stats.symbol:<10}{stats.signal_count:<10}"
            f"{stats.weighted_sum:<10.1f}{stats.latest_signal_date!s:<14}"
            f"{stats.sequence_label}{marker}"
        )

    print("-" * 95)
    print(f"Total stocks with signals: {len(results)}")
    if turbulent_count:
        print(f"  * = turbulent ({turbulent_count} stocks with amplitude >= 80%)")

    # 输出跳过统计
    skipped = scanner.get_skipped_symbols()
    if skipped:
        skipped_str = ", ".join(skipped[:10])
        if len(skipped) > 10:
            skipped_str += f"... (+{len(skipped) - 10} more)"
        print(f"Skipped {len(skipped)} stocks due to bad data: {skipped_str}")


if __name__ == "__main__":
    main()
