"""
Shadow Mode 回测脚本

用于收集美股低价股突破后的行为数据，为"由简入繁"规则迭代提供数据基础。

核心特点:
- 独立计算模式：每个突破独立计算 MFE/MAE
- 简单过滤：直接过滤 bo.date 和 bo.price
- 输出 MFE/MAE 等指标供分析

使用方法:
    python scripts/backtest/shadow_mode_backtest.py

配置参数在 main() 函数起始位置设置。

输出:
    - outputs/shadow_pool/shadow_results_YYYYMMDD_HHMMSS.json
    - outputs/shadow_pool/shadow_results_YYYYMMDD_HHMMSS.csv
"""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd


def main():
    """主入口"""
    # =========================================================================
    # 配置参数
    # =========================================================================

    # 数据源
    scan_result_path = 'outputs/scan_results/as.json'
    data_dir = 'datasets/pkls'

    # 过滤条件（设为 None 禁用对应过滤）
    date_start: Optional[date] = None   # 突破日期起始
    date_end: Optional[date] = None     # 突破日期结束
    price_min: Optional[float] = 1.0    # 最低价格
    price_max: Optional[float] = 5.0    # 最高价格
    score_min: Optional[float] = 100   # 最低质量分数

    # 跟踪参数
    tracking_days = 40

    # 输出配置
    output_dir = 'outputs/shadow_pool'

    # =========================================================================
    # 执行
    # =========================================================================

    print("=" * 60)
    print("Shadow Mode Backtest (Independent Calculation)")
    print("=" * 60)
    print(f"Price filter: ${price_min or 0:.2f} - ${price_max or 'inf'}")
    print(f"Date filter: {date_start or 'None'} to {date_end or 'None'}")
    print(f"Score filter: >= {score_min or 'None'}")
    print(f"Tracking days: {tracking_days}")
    print()

    # 1. 加载数据
    print("[1/4] Loading data...")
    breakouts, price_data = load_data(scan_result_path, data_dir)
    print(f"  Loaded {len(breakouts)} breakouts from {len(price_data)} stocks")

    # 2. 过滤突破
    print("[2/4] Filtering breakouts...")
    filtered = filter_breakouts(
        breakouts,
        date_start=date_start,
        date_end=date_end,
        price_min=price_min,
        price_max=price_max,
        score_min=score_min,
    )
    print(f"  After filter: {len(filtered)} breakouts")

    # 3. 运行计算
    print("[3/4] Computing MFE/MAE...")
    from BreakoutStrategy.shadow_pool import ShadowBacktestEngine

    def progress_callback(current: int, total: int):
        if current % 500 == 0 or current == total:
            pct = current / total * 100
            print(f"  Progress: {current}/{total} ({pct:.1f}%)", end='\r')

    engine = ShadowBacktestEngine(
        tracking_days=tracking_days,
        price_range=(price_min or 0, price_max or float('inf')),
        progress_callback=progress_callback
    )

    result = engine.run(filtered, price_data)
    print()

    # 4. 保存结果
    print("[4/4] Saving results...")
    from BreakoutStrategy.shadow_pool.engine import save_results
    json_path, csv_path = save_results(result, output_dir)
    print(f"  JSON: {json_path}")
    print(f"  CSV:  {csv_path}")

    # 打印摘要
    print_summary(result)

    print()
    print("=" * 60)
    print("Done!")
    print("=" * 60)


def load_data(scan_result_path: str, data_dir: str):
    """
    加载突破数据和价格数据（不做过滤）

    Args:
        scan_result_path: JSON 扫描结果路径
        data_dir: PKL 数据目录

    Returns:
        (breakouts, price_data)
    """
    from BreakoutStrategy.observation.adapters.json_adapter import BreakoutJSONAdapter

    # 加载 JSON 数据
    json_path = Path(scan_result_path)
    if not json_path.exists():
        print(f"Error: Scan result file not found: {scan_result_path}")
        sys.exit(1)

    with open(json_path, 'r') as f:
        json_data = json.load(f)

    # 使用适配器加载突破（不过滤日期）
    adapter = BreakoutJSONAdapter()
    breakouts_by_date = adapter.load_batch(
        json_data,
        data_dir,
        start_date=None,  # 不过滤
        end_date=None
    )

    # 扁平化突破列表
    all_breakouts = []
    for date_key, bos in breakouts_by_date.items():
        all_breakouts.extend(bos)

    # 收集需要的股票代码
    symbols = set(bo.symbol for bo in all_breakouts)

    # 加载价格数据
    price_data = {}
    data_path = Path(data_dir)

    for symbol in symbols:
        pkl_path = data_path / f"{symbol}.pkl"
        if pkl_path.exists():
            try:
                df = pd.read_pickle(pkl_path)
                # 确保索引是日期类型
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                price_data[symbol] = df
            except Exception as e:
                print(f"  Warning: Failed to load {symbol}: {e}")

    return all_breakouts, price_data


def filter_breakouts(breakouts,
                     date_start: Optional[date] = None,
                     date_end: Optional[date] = None,
                     price_min: Optional[float] = None,
                     price_max: Optional[float] = None,
                     score_min: Optional[float] = None):
    """
    过滤突破列表

    Args:
        breakouts: 突破列表
        date_start: 最早日期（含）
        date_end: 最晚日期（含）
        price_min: 最低价格（含）
        price_max: 最高价格（含）
        score_min: 最低质量分数（含）

    Returns:
        过滤后的突破列表
    """
    filtered = []
    for bo in breakouts:
        # 日期过滤
        if date_start and bo.date < date_start:
            continue
        if date_end and bo.date > date_end:
            continue
        # 价格过滤
        if price_min and bo.price < price_min:
            continue
        if price_max and bo.price > price_max:
            continue
        # 分值过滤
        if score_min and getattr(bo, 'quality_score', 0) < score_min:
            continue
        filtered.append(bo)
    return filtered


def print_summary(result):
    """打印结果摘要"""
    print()
    print("  " + "-" * 40)
    print(f"  Total breakouts input:    {result.total_breakouts_input:,}")
    print(f"  Breakouts processed:      {result.breakouts_processed:,}")
    print(f"  Results valid:            {result.results_valid:,}")
    print()
    print("  MFE Distribution:")
    print(f"    Mean:   {result.mfe_mean:6.2f}%")
    print(f"    Median: {result.mfe_median:6.2f}%")
    print(f"    Std:    {result.mfe_std:6.2f}%")
    print()
    print("  MAE Distribution:")
    print(f"    Mean:   {result.mae_mean:6.2f}%")
    print(f"    Median: {result.mae_median:6.2f}%")
    print()
    print("  Success Rates:")
    print(f"    >= 10% gain: {result.success_rate_10 * 100:5.1f}%")
    print(f"    >= 20% gain: {result.success_rate_20 * 100:5.1f}%")
    print("  " + "-" * 40)


if __name__ == '__main__':
    main()
