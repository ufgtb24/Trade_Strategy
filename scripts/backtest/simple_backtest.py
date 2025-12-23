"""
简化版回测脚本

不依赖 search/data 模块，直接使用 PKL 数据和现有扫描功能验证策略有效性。

使用方式：
    python scripts/backtest/simple_backtest.py \
        --symbols AAPL,MSFT,GOOGL \
        --start-date 2023-01-01 \
        --end-date 2024-01-01 \
        --initial-capital 100000

或使用默认参数（扫描 datasets/pkls 下所有股票）：
    python scripts/backtest/simple_backtest.py
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from BreakthroughStrategy.analysis import BreakthroughDetector, Breakthrough
from BreakthroughStrategy.analysis.features import FeatureCalculator
from BreakthroughStrategy.analysis.breakthrough_scorer import BreakthroughScorer
from BreakthroughStrategy.observation import create_backtest_pool_manager


# ===== 数据结构 =====

@dataclass
class Position:
    """持仓"""
    symbol: str
    entry_date: date
    entry_price: float
    quantity: int
    stop_loss_price: float
    take_profit_price: float
    max_price: float = 0.0  # 持仓期间最高价（用于移动止损）
    trailing_stop_price: Optional[float] = None


@dataclass
class Trade:
    """成交记录"""
    symbol: str
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    quantity: int
    pnl: float  # 盈亏金额
    pnl_pct: float  # 盈亏百分比
    holding_days: int
    exit_reason: str  # 'take_profit', 'stop_loss', 'trailing_stop', 'timeout', 'end_of_backtest'


# ===== 性能分析 =====

class PerformanceAnalyzer:
    """性能分析器"""

    def __init__(
        self,
        trades: List[Trade],
        equity_curve: List[Tuple[date, float]],
        initial_capital: float
    ):
        self.trades = trades
        self.equity_curve = equity_curve
        self.initial_capital = initial_capital

        # 转换为 Series
        if equity_curve:
            self.equity_series = pd.Series(
                [eq for _, eq in equity_curve],
                index=pd.DatetimeIndex([dt for dt, _ in equity_curve])
            )
        else:
            self.equity_series = pd.Series(dtype=float)

    def calculate_metrics(self) -> Dict:
        """计算所有性能指标"""
        return {
            **self._calculate_returns(),
            **self._calculate_risk_metrics(),
            **self._calculate_trade_statistics()
        }

    def _calculate_returns(self) -> Dict:
        """计算收益指标"""
        if self.equity_series.empty:
            return {
                'total_return': 0,
                'total_return_pct': 0,
                'annual_return': 0,
                'annual_return_pct': 0,
                'final_equity': self.initial_capital
            }

        final_equity = self.equity_series.iloc[-1]
        total_return = (final_equity - self.initial_capital) / self.initial_capital

        # 年化收益率
        days = (self.equity_series.index[-1] - self.equity_series.index[0]).days
        years = days / 365.25
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

        return {
            'total_return': total_return,
            'total_return_pct': total_return * 100,
            'annual_return': annual_return,
            'annual_return_pct': annual_return * 100,
            'final_equity': final_equity
        }

    def _calculate_risk_metrics(self) -> Dict:
        """计算风险指标"""
        if len(self.equity_series) < 2:
            return {
                'sharpe_ratio': 0,
                'sortino_ratio': 0,
                'max_drawdown': 0,
                'max_drawdown_pct': 0,
                'max_drawdown_duration_days': 0,
                'calmar_ratio': 0,
                'volatility': 0
            }

        # 日收益率
        daily_returns = self.equity_series.pct_change().dropna()

        # 夏普比率（假设无风险利率为0）
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std()
        else:
            sharpe_ratio = 0

        # 索提诺比率（只考虑下行波动）
        downside_returns = daily_returns[daily_returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            sortino_ratio = np.sqrt(252) * daily_returns.mean() / downside_returns.std()
        else:
            sortino_ratio = 0

        # 最大回撤
        max_drawdown, max_drawdown_duration = self._calculate_max_drawdown()

        # 卡玛比率
        annual_return = self._calculate_returns()['annual_return']
        calmar_ratio = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0

        return {
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown * 100,
            'max_drawdown_duration_days': max_drawdown_duration,
            'calmar_ratio': calmar_ratio,
            'volatility': daily_returns.std() * np.sqrt(252) if len(daily_returns) > 0 else 0
        }

    def _calculate_max_drawdown(self) -> Tuple[float, int]:
        """计算最大回撤和持续时间"""
        if self.equity_series.empty:
            return 0, 0

        cum_max = self.equity_series.cummax()
        drawdown = (self.equity_series - cum_max) / cum_max

        max_dd = drawdown.min()

        # 计算最大回撤持续时间
        is_drawdown = drawdown < 0
        max_duration = 0
        current_duration = 0

        for is_dd in is_drawdown:
            if is_dd:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0

        return max_dd, max_duration

    def _calculate_trade_statistics(self) -> Dict:
        """计算交易统计"""
        if not self.trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'win_rate_pct': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'avg_holding_days': 0,
                'exit_reason_distribution': {}
            }

        trades_df = pd.DataFrame([{
            'pnl': t.pnl,
            'pnl_pct': t.pnl_pct,
            'holding_days': t.holding_days,
            'exit_reason': t.exit_reason
        } for t in self.trades])

        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] <= 0]

        total_trades = len(trades_df)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = win_count / total_trades if total_trades > 0 else 0

        avg_win = winning_trades['pnl'].mean() if win_count > 0 else 0
        avg_loss = losing_trades['pnl'].mean() if loss_count > 0 else 0

        total_profit = winning_trades['pnl'].sum() if win_count > 0 else 0
        total_loss = abs(losing_trades['pnl'].sum()) if loss_count > 0 else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else 0

        return {
            'total_trades': total_trades,
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'win_rate': win_rate,
            'win_rate_pct': win_rate * 100,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_holding_days': trades_df['holding_days'].mean(),
            'exit_reason_distribution': trades_df['exit_reason'].value_counts().to_dict()
        }

    def generate_summary(self) -> str:
        """生成性能摘要报告"""
        metrics = self.calculate_metrics()

        report = []
        report.append("=== Backtest Performance Summary ===\n")

        report.append("Returns:")
        report.append(f"  Total Return: {metrics['total_return_pct']:.2f}%")
        report.append(f"  Annual Return: {metrics['annual_return_pct']:.2f}%")
        report.append(f"  Final Equity: ${metrics['final_equity']:.2f}\n")

        report.append("Risk Metrics:")
        report.append(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        report.append(f"  Sortino Ratio: {metrics['sortino_ratio']:.2f}")
        report.append(f"  Calmar Ratio: {metrics['calmar_ratio']:.2f}")
        report.append(f"  Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
        report.append(f"  Max DD Duration: {metrics['max_drawdown_duration_days']} days")
        report.append(f"  Volatility: {metrics['volatility']*100:.2f}%\n")

        report.append("Trade Statistics:")
        report.append(f"  Total Trades: {metrics['total_trades']}")
        report.append(f"  Win Rate: {metrics['win_rate_pct']:.2f}%")
        report.append(f"  Profit Factor: {metrics['profit_factor']:.2f}")
        report.append(f"  Avg Win: ${metrics['avg_win']:.2f}")
        report.append(f"  Avg Loss: ${metrics['avg_loss']:.2f}")
        report.append(f"  Avg Holding: {metrics['avg_holding_days']:.1f} days")

        if metrics['exit_reason_distribution']:
            report.append("\nExit Reasons:")
            for reason, count in metrics['exit_reason_distribution'].items():
                report.append(f"  {reason}: {count}")

        return "\n".join(report)


# ===== 回测引擎 =====

class SimpleBacktestEngine:
    """简化版回测引擎"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化回测引擎

        Args:
            config: 回测配置字典
        """
        config = config or {}

        # 回测参数
        self.initial_capital = config.get('initial_capital', 100000)
        self.commission_rate = config.get('commission_rate', 0.001)
        self.slippage = config.get('slippage', 0.001)

        # 风险管理参数
        self.stop_loss_pct = config.get('stop_loss_pct', 0.05)
        self.trailing_stop_pct = config.get('trailing_stop_pct', 0.03)
        self.take_profit_pct = config.get('take_profit_pct', 0.15)
        self.max_holdings = config.get('max_holdings', 10)
        self.max_position_size_pct = config.get('max_position_size_pct', 0.10)
        self.max_holding_days = config.get('max_holding_days', 30)

        # 突破检测参数
        self.detector_params = config.get('detector_params', {
            'total_window': 30,
            'min_side_bars': 5,
            'min_relative_height': 0.3,
            'exceed_threshold': 0.001,
            'peak_supersede_threshold': 0.03
        })

        # 质量阈值
        self.min_quality_score = config.get('min_quality_score', 60)

        # 状态
        self.cash = self.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[date, float]] = []

        # 数据存储
        self.price_data: Dict[str, pd.DataFrame] = {}  # {symbol: DataFrame}
        self.detectors: Dict[str, BreakthroughDetector] = {}  # {symbol: detector}

        # 待买入队列（次日执行）
        self.pending_buys: List[Tuple[str, Breakthrough]] = []

    def load_data(self, symbols: List[str], data_dir: str = "datasets/pkls") -> int:
        """
        加载 PKL 数据

        Args:
            symbols: 股票代码列表
            data_dir: 数据目录

        Returns:
            成功加载的股票数量
        """
        data_path = Path(data_dir)
        loaded = 0

        for symbol in symbols:
            file_path = data_path / f"{symbol}.pkl"
            if file_path.exists():
                try:
                    df = pd.read_pickle(file_path)
                    self.price_data[symbol] = df
                    loaded += 1
                except Exception as e:
                    print(f"Failed to load {symbol}: {e}")

        print(f"Loaded {loaded}/{len(symbols)} symbols")
        return loaded

    def run_backtest(
        self,
        start_date: str,
        end_date: str,
    ) -> Dict:
        """
        运行回测

        Args:
            start_date: 回测开始日期 (YYYY-MM-DD)
            end_date: 回测结束日期 (YYYY-MM-DD)

        Returns:
            回测结果字典
        """
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        print(f"\nStarting backtest: {start_date} to {end_date}")
        print(f"Initial capital: ${self.initial_capital:,.2f}")
        print(f"Symbols: {len(self.price_data)}")
        print(f"Min quality score: {self.min_quality_score}")

        # 生成交易日序列（使用第一个有数据的股票的日期）
        trading_days = self._get_trading_days(start, end)
        print(f"Trading days: {len(trading_days)}")

        # 初始化每个股票的检测器
        self._initialize_detectors()

        # 逐日回测
        for i, current_date in enumerate(trading_days):
            self._process_day(current_date, trading_days)

            # 记录权益曲线
            equity = self._calculate_equity(current_date)
            self.equity_curve.append((current_date, equity))

            # 进度显示
            if (i + 1) % 50 == 0:
                print(f"  Day {i+1}/{len(trading_days)}: equity=${equity:,.2f}, positions={len(self.positions)}")

        # 平仓所有持仓
        self._close_all_positions(trading_days[-1])

        # 计算性能指标
        analyzer = PerformanceAnalyzer(
            trades=self.trades,
            equity_curve=self.equity_curve,
            initial_capital=self.initial_capital
        )

        print("\n" + analyzer.generate_summary())

        return {
            'trades': self.trades,
            'equity_curve': self.equity_curve,
            'performance': analyzer.calculate_metrics()
        }

    def _get_trading_days(self, start: date, end: date) -> List[date]:
        """获取交易日列表"""
        # 使用第一个有数据的股票的日期索引
        for symbol, df in self.price_data.items():
            dates = df.index.date if hasattr(df.index, 'date') else df.index
            trading_days = [d for d in dates if start <= d <= end]
            if trading_days:
                return sorted(trading_days)

        return []

    def _initialize_detectors(self):
        """为每个股票初始化突破检测器"""
        for symbol in self.price_data.keys():
            self.detectors[symbol] = BreakthroughDetector(
                symbol=symbol,
                **self.detector_params,
                use_cache=False
            )

    def _process_day(self, current_date: date, all_trading_days: List[date]):
        """
        处理单日回测

        流程：
        1. 执行待买入（昨日信号，今日开盘买入）
        2. 更新持仓（检查止盈止损）
        3. 扫描当日突破，加入待买入队列
        """
        # 1. 执行昨日产生的待买入（今日开盘价买入）
        self._execute_pending_buys(current_date)

        # 2. 更新持仓（检查止盈止损）
        self._update_positions(current_date, all_trading_days)

        # 3. 扫描当日突破，加入待买入队列（次日执行）
        self._scan_and_queue_breakthroughs(current_date)

    def _scan_and_queue_breakthroughs(self, current_date: date):
        """扫描当日突破并加入待买入队列"""
        feature_calc = FeatureCalculator()
        scorer = BreakthroughScorer()

        today_breakthroughs = []

        for symbol, df in self.price_data.items():
            # 跳过已持仓的股票
            if symbol in self.positions:
                continue

            # 获取截止到今天的数据
            mask = df.index.date <= current_date if hasattr(df.index, 'date') else df.index <= current_date
            df_until_today = df[mask]

            if df_until_today.empty:
                continue

            # 获取今日 bar
            today_mask = df.index.date == current_date if hasattr(df.index, 'date') else df.index == current_date
            today_bars = df[today_mask]

            if today_bars.empty:
                continue

            today_bar = today_bars.iloc[0]

            # 增量添加今日 bar
            detector = self.detectors[symbol]
            breakout_info = detector.add_bar(today_bar)

            if not breakout_info:
                continue

            # 计算特征和评分（add_bar 返回单个 BreakoutInfo 或 None）
            breakout_infos = [breakout_info] if breakout_info else []
            for info in breakout_infos:
                bt = feature_calc.enrich_breakthrough(df_until_today, info, symbol, detector=detector)
                today_breakthroughs.append((symbol, bt))

        # 批量评分
        if today_breakthroughs:
            all_bts = [bt for _, bt in today_breakthroughs]
            scorer.score_breakthroughs_batch(all_bts)

            # 过滤低质量突破，并按分数排序
            qualified = [
                (symbol, bt) for symbol, bt in today_breakthroughs
                if bt.quality_score is not None and bt.quality_score >= self.min_quality_score
            ]
            qualified.sort(key=lambda x: x[1].quality_score, reverse=True)

            # 加入待买入队列
            self.pending_buys.extend(qualified)

    def _execute_pending_buys(self, current_date: date):
        """执行待买入队列（使用今日开盘价）"""
        if not self.pending_buys:
            return

        # 按质量分数排序
        self.pending_buys.sort(key=lambda x: x[1].quality_score, reverse=True)

        executed = []
        for symbol, bt in self.pending_buys:
            # 检查持仓上限
            if len(self.positions) >= self.max_holdings:
                break

            # 跳过已持仓
            if symbol in self.positions:
                continue

            # 获取今日开盘价
            df = self.price_data.get(symbol)
            if df is None:
                continue

            today_mask = df.index.date == current_date if hasattr(df.index, 'date') else df.index == current_date
            today_bars = df[today_mask]

            if today_bars.empty:
                continue

            open_price = today_bars.iloc[0]['open']

            # 执行买入
            success = self._execute_buy(symbol, current_date, open_price, bt)
            if success:
                executed.append((symbol, bt))

        # 清空待买入队列
        self.pending_buys.clear()

    def _execute_buy(self, symbol: str, buy_date: date, price: float, bt: Breakthrough) -> bool:
        """
        执行买入

        Args:
            symbol: 股票代码
            buy_date: 买入日期
            price: 买入价格
            bt: 突破信息

        Returns:
            是否成功买入
        """
        # 计算买入价格（含滑点）
        entry_price = price * (1 + self.slippage)

        # 计算仓位
        position_value = self.cash * self.max_position_size_pct
        quantity = int(position_value / entry_price)

        if quantity == 0:
            return False

        # 计算成本
        cost = entry_price * quantity * (1 + self.commission_rate)
        if cost > self.cash:
            return False

        # 计算止损止盈价
        stop_loss_price = entry_price * (1 - self.stop_loss_pct)
        take_profit_price = entry_price * (1 + self.take_profit_pct)

        # 扣除现金
        self.cash -= cost

        # 创建持仓
        position = Position(
            symbol=symbol,
            entry_date=buy_date,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            max_price=entry_price
        )
        self.positions[symbol] = position

        return True

    def _update_positions(self, current_date: date, all_trading_days: List[date]):
        """更新持仓，检查止盈止损"""
        to_close = []

        for symbol, position in self.positions.items():
            df = self.price_data.get(symbol)
            if df is None:
                continue

            # 获取今日价格
            today_mask = df.index.date == current_date if hasattr(df.index, 'date') else df.index == current_date
            today_bars = df[today_mask]

            if today_bars.empty:
                continue

            today_data = today_bars.iloc[0]
            current_price = today_data['close']
            high_price = today_data['high']
            low_price = today_data['low']

            # 更新最高价
            if high_price > position.max_price:
                position.max_price = high_price
                # 更新移动止损价
                position.trailing_stop_price = position.max_price * (1 - self.trailing_stop_pct)

            # 检查止损
            if low_price <= position.stop_loss_price:
                to_close.append((symbol, position.stop_loss_price, 'stop_loss'))
                continue

            # 检查移动止损
            if position.trailing_stop_price and low_price <= position.trailing_stop_price:
                to_close.append((symbol, position.trailing_stop_price, 'trailing_stop'))
                continue

            # 检查止盈
            if high_price >= position.take_profit_price:
                to_close.append((symbol, position.take_profit_price, 'take_profit'))
                continue

            # 检查超时
            holding_days = (current_date - position.entry_date).days
            if holding_days >= self.max_holding_days:
                to_close.append((symbol, current_price, 'timeout'))
                continue

        # 执行平仓
        for symbol, exit_price, reason in to_close:
            self._close_position(symbol, current_date, exit_price, reason)

    def _close_position(self, symbol: str, exit_date: date, exit_price: float, reason: str):
        """平仓"""
        if symbol not in self.positions:
            return

        position = self.positions[symbol]

        # 计算收益（含滑点和手续费）
        exit_price_with_slippage = exit_price * (1 - self.slippage)
        proceeds = exit_price_with_slippage * position.quantity * (1 - self.commission_rate)

        cost = position.entry_price * position.quantity
        pnl = proceeds - cost
        pnl_pct = (exit_price_with_slippage - position.entry_price) / position.entry_price

        # 更新现金
        self.cash += proceeds

        # 记录交易
        trade = Trade(
            symbol=symbol,
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            exit_date=exit_date,
            exit_price=exit_price_with_slippage,
            quantity=position.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            holding_days=(exit_date - position.entry_date).days,
            exit_reason=reason
        )
        self.trades.append(trade)

        # 移除持仓
        del self.positions[symbol]

    def _close_all_positions(self, final_date: date):
        """平仓所有剩余持仓"""
        for symbol in list(self.positions.keys()):
            df = self.price_data.get(symbol)
            if df is None:
                continue

            today_mask = df.index.date == final_date if hasattr(df.index, 'date') else df.index == final_date
            today_bars = df[today_mask]

            if not today_bars.empty:
                close_price = today_bars.iloc[0]['close']
                self._close_position(symbol, final_date, close_price, 'end_of_backtest')

    def _calculate_equity(self, current_date: date) -> float:
        """计算当前权益"""
        equity = self.cash

        for symbol, position in self.positions.items():
            df = self.price_data.get(symbol)
            if df is None:
                equity += position.entry_price * position.quantity
                continue

            today_mask = df.index.date == current_date if hasattr(df.index, 'date') else df.index == current_date
            today_bars = df[today_mask]

            if not today_bars.empty:
                current_price = today_bars.iloc[0]['close']
                equity += current_price * position.quantity
            else:
                equity += position.entry_price * position.quantity

        return equity


# ===== 命令行入口 =====

def main():
    parser = argparse.ArgumentParser(description='Simple Backtest Script')
    parser.add_argument('--symbols', type=str, default=None,
                        help='Comma-separated list of symbols (default: all in data_dir)')
    parser.add_argument('--data-dir', type=str, default='datasets/pkls',
                        help='Data directory')
    parser.add_argument('--start-date', type=str, default='2023-01-01',
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default='2024-01-01',
                        help='End date (YYYY-MM-DD)')
    parser.add_argument('--initial-capital', type=float, default=100000,
                        help='Initial capital')
    parser.add_argument('--stop-loss', type=float, default=0.05,
                        help='Stop loss percentage')
    parser.add_argument('--take-profit', type=float, default=0.15,
                        help='Take profit percentage')
    parser.add_argument('--max-holdings', type=int, default=10,
                        help='Maximum number of holdings')
    parser.add_argument('--min-quality', type=float, default=60,
                        help='Minimum quality score threshold')

    args = parser.parse_args()

    # 获取股票列表
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(',')]
    else:
        # 扫描数据目录
        data_path = Path(args.data_dir)
        if data_path.exists():
            symbols = [f.stem for f in data_path.glob('*.pkl')]
        else:
            print(f"Data directory not found: {args.data_dir}")
            return

    if not symbols:
        print("No symbols to backtest")
        return

    print(f"Backtest Configuration:")
    print(f"  Symbols: {len(symbols)}")
    print(f"  Period: {args.start_date} to {args.end_date}")
    print(f"  Initial Capital: ${args.initial_capital:,.2f}")
    print(f"  Stop Loss: {args.stop_loss*100:.1f}%")
    print(f"  Take Profit: {args.take_profit*100:.1f}%")
    print(f"  Max Holdings: {args.max_holdings}")
    print(f"  Min Quality Score: {args.min_quality}")

    # 创建回测引擎
    config = {
        'initial_capital': args.initial_capital,
        'stop_loss_pct': args.stop_loss,
        'take_profit_pct': args.take_profit,
        'max_holdings': args.max_holdings,
        'min_quality_score': args.min_quality,
    }

    engine = SimpleBacktestEngine(config)

    # 加载数据
    loaded = engine.load_data(symbols, args.data_dir)
    if loaded == 0:
        print("No data loaded")
        return

    # 运行回测
    result = engine.run_backtest(args.start_date, args.end_date)

    # 输出交易明细
    print(f"\n=== Trade Details ({len(result['trades'])} trades) ===")
    for i, trade in enumerate(result['trades'][:20]):  # 只显示前20笔
        print(f"{i+1}. {trade.symbol}: {trade.entry_date} -> {trade.exit_date} | "
              f"${trade.entry_price:.2f} -> ${trade.exit_price:.2f} | "
              f"PnL: ${trade.pnl:.2f} ({trade.pnl_pct*100:.1f}%) | {trade.exit_reason}")

    if len(result['trades']) > 20:
        print(f"... and {len(result['trades']) - 20} more trades")


if __name__ == '__main__':
    main()
