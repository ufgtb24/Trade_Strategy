"""
Daily 池回测脚本

基于阶段状态机的 Daily 池回测，从 JSON 扫描结果加载历史突破，
评估"回调-企稳-再启动"过程并生成买入信号。

使用方法：
    python scripts/backtest/daily_pool_backtest.py

配置参数在 main() 函数中设置。

输出：
    - 控制台输出回测进度和绩效摘要
    - 可选：保存信号和转换记录到 JSON
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd


def main():
    """回测主入口"""
    # ===== 配置参数 =====
    # 数据路径
    scan_result_path = 'outputs/scan_results/scan_results_bo.json'
    data_dir = 'datasets/pkls'

    # 回测时间范围
    start_date = '2024-01-01'
    end_date = '2024-06-30'

    # 输出配置
    save_results = True
    output_dir = 'outputs/backtest/daily'

    # Daily 池策略 ('default', 'conservative', 'aggressive')
    strategy = 'default'

    # ===== 加载数据 =====
    print("=" * 60)
    print("Daily Pool Backtest Engine")
    print("=" * 60)
    print(f"\nLoading data from: {scan_result_path}")

    from BreakoutStrategy.observation.adapters import BreakoutJSONAdapter
    from BreakoutStrategy.daily_pool import (
        DailyBacktestEngine, DailyPoolConfig, load_config
    )

    # 加载 JSON 扫描结果
    adapter = BreakoutJSONAdapter()
    breakouts_by_date = adapter.load_from_file(
        scan_result_path,
        data_dir,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date)
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

    # ===== 配置 Daily 池 =====
    if strategy == 'conservative':
        config = DailyPoolConfig.conservative()
    elif strategy == 'aggressive':
        config = DailyPoolConfig.aggressive()
    else:
        # 尝试从 YAML 加载，失败则使用默认配置
        default_yaml = Path('configs/daily_pool/default.yaml')
        if default_yaml.exists():
            config = load_config(default_yaml)
        else:
            config = DailyPoolConfig.default()

    print(f"\nUsing strategy: {strategy}")
    print(f"  Max observation days: {config.phase.max_observation_days}")
    print(f"  Max drop from breakout: {config.phase.max_drop_from_breakout_atr} ATR")

    # ===== 执行回测 =====
    print(f"\nRunning backtest from {start_date} to {end_date}...")

    engine = DailyBacktestEngine(config)

    def on_signal(signal):
        print(f"  Signal: {signal.symbol} @ {signal.signal_date} "
              f"[{signal.strength.value}] confidence={signal.confidence:.2f}")

    result = engine.run(
        breakouts=all_breakouts,
        price_data=price_data,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date),
        on_signal=on_signal
    )

    # ===== 输出结果 =====
    print("\n" + result.summary())

    # ===== 保存结果 =====
    if save_results:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 保存信号记录
        signals_file = output_path / f'daily_signals_{start_date}_{end_date}.json'
        _save_signals(result.signals, signals_file)
        print(f"\nSignals saved to: {signals_file}")

        # 保存阶段转换记录
        transitions_file = output_path / f'daily_transitions_{start_date}_{end_date}.json'
        _save_transitions(result.phase_transitions, transitions_file)
        print(f"Transitions saved to: {transitions_file}")

        # 保存统计摘要
        stats_file = output_path / f'daily_stats_{start_date}_{end_date}.json'
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


def _save_transitions(transitions, filepath):
    """保存阶段转换记录到 JSON"""
    with open(filepath, 'w') as f:
        json.dump(transitions, f, indent=2)


def _save_statistics(statistics, config, filepath):
    """保存统计摘要到 JSON"""
    data = {
        'config': {
            'max_observation_days': config.phase.max_observation_days,
            'max_drop_from_breakout_atr': config.phase.max_drop_from_breakout_atr,
            'min_convergence_score': config.phase.min_convergence_score,
            'min_volume_expansion': config.phase.min_volume_expansion,
        },
        'statistics': statistics
    }

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)


if __name__ == '__main__':
    main()
