"""
观察池回测脚本

基于观察池系统的回测引擎，从 JSON 扫描结果加载历史突破，
模拟交易并计算绩效。

使用方法：
    python scripts/backtest/realtime_pool_backtest.py

配置参数在 main() 函数中设置。

输出：
    - 控制台输出回测进度和绩效摘要
    - 可选：保存详细结果到 CSV/JSON
"""
from datetime import date
from pathlib import Path


def main():
    """回测主入口"""
    # ===== 配置参数 =====
    # 数据路径
    scan_result_path = 'outputs/scan_results/scan_results_20260101_013046.json'
    data_dir = 'datasets/pkls'

    # 回测时间范围
    start_date = '2024-01-01'
    end_date = '2024-06-30'

    # 输出配置
    save_results = True
    output_dir = 'outputs/backtest'

    # ===== 回测配置 =====
    from BreakoutStrategy.backtest import BacktestEngine, BacktestConfig

    config = BacktestConfig(
        # 资金管理
        initial_capital=100000,
        max_holdings=10,
        max_position_size_pct=0.10,
        min_position_size=1000,
        commission_rate=0.001,

        # 止盈止损
        stop_loss_pct=0.05,
        take_profit_pct=0.15,

        # 观察池配置
        realtime_observation_days=1,
        daily_observation_days=30,
        min_quality_score=0.0,
    )

    # ===== 执行回测 =====
    print("="*60)
    print("Pool-based Backtest Engine")
    print("="*60)

    engine = BacktestEngine(
        config=config,
        scan_result_path=scan_result_path,
        data_dir=data_dir
    )

    result = engine.run(start_date=start_date, end_date=end_date)

    # ===== 保存结果 =====
    if save_results:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 保存交易记录
        trades_file = output_path / f'trades_{start_date}_{end_date}.csv'
        _save_trades_to_csv(result.trades, trades_file)
        print(f"\nTrades saved to: {trades_file}")

        # 保存权益曲线
        equity_file = output_path / f'equity_{start_date}_{end_date}.csv'
        _save_equity_curve(result.equity_curve, equity_file)
        print(f"Equity curve saved to: {equity_file}")

        # 保存绩效摘要
        perf_file = output_path / f'performance_{start_date}_{end_date}.json'
        _save_performance(result.performance, config, perf_file)
        print(f"Performance saved to: {perf_file}")

    return result


def _save_trades_to_csv(trades, filepath):
    """保存交易记录到 CSV"""
    import csv

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'symbol', 'entry_date', 'entry_price', 'shares',
            'exit_date', 'exit_price', 'exit_reason',
            'pnl', 'pnl_pct', 'holding_days'
        ])

        for trade in trades:
            writer.writerow([
                trade.symbol,
                trade.entry_date.isoformat() if trade.entry_date else '',
                f'{trade.entry_price:.2f}',
                trade.shares,
                trade.exit_date.isoformat() if trade.exit_date else '',
                f'{trade.exit_price:.2f}' if trade.exit_price else '',
                trade.exit_reason,
                f'{trade.pnl:.2f}',
                f'{trade.pnl_pct:.4f}',
                trade.holding_days
            ])


def _save_equity_curve(equity_curve, filepath):
    """保存权益曲线到 CSV"""
    import csv

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'equity'])

        for dt, equity in equity_curve:
            writer.writerow([dt.isoformat(), f'{equity:.2f}'])


def _save_performance(performance, config, filepath):
    """保存绩效统计到 JSON"""
    import json

    data = {
        'config': {
            'initial_capital': config.initial_capital,
            'stop_loss_pct': config.stop_loss_pct,
            'take_profit_pct': config.take_profit_pct,
            'max_holdings': config.max_holdings,
            'max_position_size_pct': config.max_position_size_pct,
        },
        'performance': performance
    }

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)


if __name__ == '__main__':
    main()
