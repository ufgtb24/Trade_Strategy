"""
Simple Pool 回测脚本

基于即时判断的 Simple Pool 回测，从 JSON 扫描结果加载历史突破，
评估买入信号并生成回测报告。

使用方法：
    python scripts/backtest/simple_pool_backtest.py

配置参数在 main() 函数中设置。

输出：
    - 控制台输出回测进度和绩效摘要
    - 可选：保存信号记录到 JSON
"""
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd


def infer_date_range(
    json_data: dict,
    observation_buffer_days: int = 30
) -> Tuple[Optional[date], Optional[date]]:
    """
    从 JSON 突破数据中推断日期范围

    Args:
        json_data: JSON 扫描结果数据
        observation_buffer_days: 观察期缓冲天数，确保最后一个突破有足够观察期

    Returns:
        (start_date, end_date) 元组，如果无数据则返回 (None, None)
    """
    all_dates = []

    for stock_data in json_data.get("results", []):
        for bo_data in stock_data.get("breakouts", []):
            bo_date_str = bo_data.get("date")
            if bo_date_str:
                try:
                    # 处理 ISO 格式日期
                    bo_date = date.fromisoformat(bo_date_str[:10])
                    all_dates.append(bo_date)
                except ValueError:
                    continue

    if not all_dates:
        return None, None

    start_date = min(all_dates)
    # 结束日期 = 最晚突破日期 + 观察期缓冲
    end_date = max(all_dates) + timedelta(days=observation_buffer_days)

    return start_date, end_date


def main():
    """回测主入口"""
    # ===== 配置参数 =====
    # 数据路径
    scan_result_path = 'outputs/scan_results/as.json'
    data_dir = 'datasets/pkls'

    # 输出配置
    save_results = True
    output_dir = 'outputs/backtest/simple'

    # Simple Pool 策略 ('default', 'conservative', 'aggressive')
    strategy = 'default'

    # ===== 加载数据 =====
    print("=" * 60)
    print("Simple Pool Backtest Engine (MVP)")
    print("=" * 60)
    print(f"\nLoading data from: {scan_result_path}")

    from BreakoutStrategy.observation.adapters import BreakoutJSONAdapter
    from BreakoutStrategy.simple_pool import SimpleBacktestEngine, SimplePoolConfig

    # 先加载 JSON 原始数据以推断日期范围
    with open(scan_result_path, 'r') as f:
        json_data = json.load(f)

    # 加载配置以获取 max_observation_days
    default_yaml = Path('configs/simple_pool/default.yaml')
    if strategy == 'conservative':
        config = SimplePoolConfig.conservative()
    elif strategy == 'aggressive':
        config = SimplePoolConfig.aggressive()
    elif default_yaml.exists():
        config = SimplePoolConfig.from_yaml(str(default_yaml))
    else:
        config = SimplePoolConfig.default()

    # 自动推断日期范围
    start_date, end_date = infer_date_range(
        json_data,
        observation_buffer_days=config.max_observation_days
    )

    if start_date is None or end_date is None:
        print("Error: No breakout data found in JSON file. Exiting.")
        return None

    print(f"Auto-detected date range: {start_date} to {end_date}")
    print(f"  (observation buffer: {config.max_observation_days} days)")

    # 加载 JSON 扫描结果
    adapter = BreakoutJSONAdapter()
    breakouts_by_date = adapter.load_from_file(
        scan_result_path,
        data_dir,
        start_date=start_date,
        end_date=end_date
    )

    # 展平为列表
    all_breakouts = [
        bo for bos in breakouts_by_date.values() for bo in bos
    ]
    print(f"Loaded {len(all_breakouts)} breakouts from {len(breakouts_by_date)} dates")

    if not all_breakouts:
        print("No breakouts found in the specified date range. Exiting.")
        return None

    # 加载价格数据
    print("\nLoading price data...")
    price_data = {}
    symbols = set(bo.symbol for bo in all_breakouts)

    for symbol in symbols:
        pkl_path = Path(data_dir) / f"{symbol}.pkl"
        if pkl_path.exists():
            price_data[symbol] = pd.read_pickle(pkl_path)

    print(f"Loaded price data for {len(price_data)} symbols")

    missing = symbols - set(price_data.keys())
    if missing:
        print(f"Warning: Missing price data for {len(missing)} symbols: {list(missing)[:5]}...")

    # ===== 显示 Simple Pool 配置 =====
    print(f"\nUsing strategy: {strategy}")
    print(f"  Max pullback: {config.max_pullback_atr} ATR")
    print(f"  Volume threshold: {config.volume_threshold}x")
    print(f"  Min quality score: {config.min_quality_score}")
    print(f"  Max observation days: {config.max_observation_days}")

    # ===== 执行回测 =====
    # 后验跟踪天数（与 Shadow Mode 对齐，便于对比）
    tracking_days = 30

    print(f"\nRunning backtest from {start_date} to {end_date}...")
    print(f"  (tracking_days={tracking_days} for MFE/MAE evaluation)")

    engine = SimpleBacktestEngine(config)

    def on_signal(signal):
        print(f"  Signal: {signal.symbol} @ {signal.signal_date} "
              f"price={signal.entry_price:.2f} stop={signal.stop_loss:.2f}")

    result = engine.run(
        breakouts=all_breakouts,
        price_data=price_data,
        start_date=start_date,
        end_date=end_date,
        on_signal=on_signal,
        tracking_days=tracking_days
    )

    # ===== 输出结果 =====
    print("\n" + result.summary())

    # ===== 保存结果 =====
    if save_results:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 保存信号记录
        signals_file = output_path / f'simple_signals_{start_date}_{end_date}.json'
        _save_signals(result.signals, signals_file)
        print(f"\nSignals saved to: {signals_file}")

        # 保存统计摘要
        stats_file = output_path / f'simple_stats_{start_date}_{end_date}.json'
        _save_statistics(result.statistics, config, stats_file)
        print(f"Statistics saved to: {stats_file}")

    return result


def _save_signals(signals, filepath):
    """保存信号记录到 JSON"""
    data = []
    for s in signals:
        data.append(s.to_dict())

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


def _save_statistics(statistics, config, filepath):
    """保存统计摘要到 JSON"""
    data = {
        'config': {
            'max_pullback_atr': config.max_pullback_atr,
            'support_lookback': config.support_lookback,
            'volume_threshold': config.volume_threshold,
            'min_quality_score': config.min_quality_score,
            'max_observation_days': config.max_observation_days,
        },
        'statistics': statistics
    }

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)


if __name__ == '__main__':
    main()
