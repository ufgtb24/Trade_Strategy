"""
回测引擎

基于观察池系统的回测引擎，模拟历史交易并计算绩效。

核心流程：
1. 加载 JSON 扫描结果，转换为 Breakout 对象
2. 按日期推进，将突破加入观察池
3. 评估买入信号，执行模拟交易
4. 管理持仓（止盈/止损）
5. 计算绩效统计

使用示例：
    config = BacktestConfig(initial_capital=100000)
    engine = BacktestEngine(config, 'outputs/scan.json', 'datasets/pkls')
result = engine.run('2024-01-01', '2024-06-30')
"""
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from BreakoutStrategy.observation import (
    create_backtest_pool_manager,
    PoolManager,
    BuySignal,
    PoolEvent,
)
from BreakoutStrategy.observation.adapters import (
    BreakoutJSONAdapter,
    EvaluationContextBuilder,
)


@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 100000      # 初始资金
    stop_loss_pct: float = 0.05          # 止损比例
    take_profit_pct: float = 0.15        # 止盈比例
    max_holdings: int = 10               # 最大持仓数
    max_position_size_pct: float = 0.10  # 单个持仓最大比例
    min_position_size: float = 1000      # 最小持仓金额
    commission_rate: float = 0.001       # 手续费率

    # 观察池配置
    realtime_observation_days: int = 1   # 实时池观察天数
    daily_observation_days: int = 30     # 日K池观察天数
    min_quality_score: float = 0.0       # 最低质量评分


@dataclass
class Trade:
    """单笔交易记录"""
    symbol: str
    entry_date: date
    entry_price: float
    shares: int = 0
    position_value: float = 0.0
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    exit_reason: str = ''  # 'stop_loss' | 'take_profit' | 'signal' | 'end'
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_days: int = 0


@dataclass
class BacktestResult:
    """回测结果"""
    trades: List[Trade]
    equity_curve: List[Tuple[date, float]]
    performance: Dict[str, float]
    pool_events: List[PoolEvent]
    config: BacktestConfig = None

    def summary(self) -> str:
        """生成回测摘要"""
        p = self.performance
        lines = [
            "===== Backtest Results =====",
            f"Total Trades: {p.get('total_trades', 0)}",
            f"Winning Trades: {p.get('winning_trades', 0)}",
            f"Win Rate: {p.get('win_rate', 0):.2%}",
            f"Total Return: {p.get('total_return', 0):.2%}",
            f"Max Drawdown: {p.get('max_drawdown', 0):.2%}",
            f"Sharpe Ratio: {p.get('sharpe_ratio', 0):.2f}",
            f"Profit Factor: {p.get('profit_factor', 0):.2f}",
            f"Avg Holding Days: {p.get('avg_holding_days', 0):.1f}",
        ]
        return "\n".join(lines)


class BacktestEngine:
    """
    基于观察池的回测引擎

    核心职责：
    - 加载和转换历史数据
    - 按日期推进模拟交易
    - 管理持仓和资金
    - 计算绩效统计

    使用示例：
        config = BacktestConfig(initial_capital=100000)
        engine = BacktestEngine(config, 'outputs/scan.json', 'datasets/pkls')
        result = engine.run('2024-01-01', '2024-06-30')
    """

    def __init__(
        self,
        config: BacktestConfig,
        scan_result_path: str,
        data_dir: str
    ):
        """
        初始化回测引擎

        Args:
            config: 回测配置
            scan_result_path: JSON 扫描结果路径
            data_dir: PKL 数据目录
        """
        self.config = config
        self.scan_result_path = Path(scan_result_path)
        self.data_dir = Path(data_dir)

        # 初始化组件
        self.adapter = BreakoutJSONAdapter()
        self.context_builder = EvaluationContextBuilder()
        self.pool_mgr: Optional[PoolManager] = None

        # 状态
        self.positions: Dict[str, Trade] = {}
        self.closed_trades: List[Trade] = []
        self.equity_curve: List[Tuple[date, float]] = []
        self.pool_events: List[PoolEvent] = []
        self.cash = config.initial_capital

        # 数据缓存
        self._json_data: Optional[dict] = None
        self._df_cache: Dict[str, pd.DataFrame] = {}
        self._breakouts_by_date: Dict[date, list] = {}

    def run(self, start_date: str, end_date: str) -> BacktestResult:
        """
        执行回测

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            BacktestResult 回测结果
        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        # 1. 加载数据
        print(f"Loading data from {self.scan_result_path}...")
        self._load_data(start, end)

        # 2. 获取交易日列表
        trading_days = self._get_trading_days(start, end)
        print(f"Trading days: {len(trading_days)} ({start} to {end})")

        # 3. 初始化观察池
        pool_config = {
            'realtime_observation_days': self.config.realtime_observation_days,
            'daily_observation_days': self.config.daily_observation_days,
            'min_quality_score': self.config.min_quality_score,
        }
        self.pool_mgr = create_backtest_pool_manager(start, pool_config)

        # 注册事件收集器
        self.pool_mgr.add_event_listener(self._collect_event)

        # 4. 主循环
        print("Running backtest...")
        for i, trading_day in enumerate(trading_days):
            self._process_day(trading_day)

            # 进度显示
            if (i + 1) % 20 == 0:
                equity = self._calculate_equity(trading_day)
                print(f"  Day {i+1}/{len(trading_days)}: {trading_day}, "
                      f"Equity: ${equity:,.0f}, Positions: {len(self.positions)}")

        # 5. 清算剩余持仓
        self._liquidate_all(end)

        # 6. 计算绩效
        performance = self._calculate_performance()

        print("\n" + "="*50)
        result = BacktestResult(
            trades=self.closed_trades,
            equity_curve=self.equity_curve,
            performance=performance,
            pool_events=self.pool_events,
            config=self.config
        )
        print(result.summary())

        return result

    def _load_data(self, start: date, end: date) -> None:
        """加载数据"""
        # 加载 JSON
        with open(self.scan_result_path, 'r') as f:
            self._json_data = json.load(f)

        # 转换为按日期分组的 Breakout
        self._breakouts_by_date = self.adapter.load_batch(
            self._json_data,
            str(self.data_dir),
            start_date=start,
            end_date=end
        )

        # 预加载需要的 DataFrame
        symbols = set()
        for breakouts in self._breakouts_by_date.values():
            for bo in breakouts:
                symbols.add(bo.symbol)

        for symbol in symbols:
            pkl_path = self.data_dir / f"{symbol}.pkl"
            if pkl_path.exists():
                self._df_cache[symbol] = pd.read_pickle(pkl_path)

        print(f"Loaded {len(self._breakouts_by_date)} days of breakouts, "
              f"{len(symbols)} symbols")

    def _get_trading_days(self, start: date, end: date) -> List[date]:
        """获取交易日列表"""
        # 从任意一个 DataFrame 获取交易日
        if not self._df_cache:
            # 如果没有缓存，生成工作日列表
            days = []
            current = start
            while current <= end:
                if current.weekday() < 5:  # 周一到周五
                    days.append(current)
                current += timedelta(days=1)
            return days

        # 使用第一个 DataFrame 的索引
        df = next(iter(self._df_cache.values()))
        mask = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
        return [ts.date() for ts in df.index[mask]]

    def _process_day(self, trading_day: date) -> None:
        """处理单个交易日"""
        # 1. 获取当日突破并加入观察池
        todays_breakouts = self._breakouts_by_date.get(trading_day, [])
        for bo in todays_breakouts:
            self.pool_mgr.add_from_breakout(bo)

        # 2. 构建价格数据和上下文
        entries_with_bo = self.pool_mgr.get_entries_with_breakouts()
        if entries_with_bo:
            price_data, context = self.context_builder.build_full_evaluation_data(
                entries_with_bo, self._df_cache, trading_day
            )

            # 3. 评估并获取买入信号
            results = self.pool_mgr.evaluate_entries(price_data, context)
            signals = self.pool_mgr.apply_evaluation_results(results)

            # 4. 执行买入
            for signal in signals:
                if len(self.positions) < self.config.max_holdings:
                    self._execute_buy(signal, trading_day)

        # 5. 更新持仓（止盈止损）
        self._update_positions(trading_day)

        # 6. 记录权益曲线
        equity = self._calculate_equity(trading_day)
        self.equity_curve.append((trading_day, equity))

        # 7. 推进观察池
        self.pool_mgr.advance_day()

    def _execute_buy(self, signal: BuySignal, trading_day: date) -> bool:
        """执行买入"""
        symbol = signal.symbol

        # 检查是否已持有
        if symbol in self.positions:
            return False

        # 获取价格
        if symbol not in self._df_cache:
            return False

        df = self._df_cache[symbol]
        price = self._get_price(df, trading_day, 'close')
        if price is None or price <= 0:
            return False

        # 计算仓位大小
        available_slots = self.config.max_holdings - len(self.positions)
        position_value = min(
            self.cash * self.config.max_position_size_pct,
            self.cash / max(1, available_slots)
        )

        if position_value < self.config.min_position_size:
            return False

        if position_value > self.cash:
            return False

        # 计算股数和实际金额
        shares = int(position_value / price)
        if shares <= 0:
            return False

        actual_value = shares * price
        commission = actual_value * self.config.commission_rate

        # 创建交易记录
        trade = Trade(
            symbol=symbol,
            entry_date=trading_day,
            entry_price=price,
            shares=shares,
            position_value=actual_value
        )
        self.positions[symbol] = trade
        self.cash -= (actual_value + commission)

        # 标记为已买入
        self.pool_mgr.mark_bought(symbol)

        return True

    def _update_positions(self, trading_day: date) -> None:
        """更新持仓，检查止盈止损"""
        to_close = []

        for symbol, trade in self.positions.items():
            if symbol not in self._df_cache:
                continue

            df = self._df_cache[symbol]
            current_price = self._get_price(df, trading_day, 'close')
            if current_price is None:
                continue

            pnl_pct = (current_price - trade.entry_price) / trade.entry_price

            # 止损
            if pnl_pct <= -self.config.stop_loss_pct:
                trade.exit_date = trading_day
                trade.exit_price = current_price
                trade.exit_reason = 'stop_loss'
                trade.pnl_pct = pnl_pct
                trade.pnl = trade.shares * (current_price - trade.entry_price)
                trade.holding_days = (trading_day - trade.entry_date).days
                to_close.append(symbol)

            # 止盈
            elif pnl_pct >= self.config.take_profit_pct:
                trade.exit_date = trading_day
                trade.exit_price = current_price
                trade.exit_reason = 'take_profit'
                trade.pnl_pct = pnl_pct
                trade.pnl = trade.shares * (current_price - trade.entry_price)
                trade.holding_days = (trading_day - trade.entry_date).days
                to_close.append(symbol)

        # 平仓
        for symbol in to_close:
            trade = self.positions.pop(symbol)
            self.closed_trades.append(trade)

            # 返还资金
            exit_value = trade.shares * trade.exit_price
            commission = exit_value * self.config.commission_rate
            self.cash += (exit_value - commission)

    def _liquidate_all(self, end_date: date) -> None:
        """清算所有剩余持仓"""
        for symbol, trade in list(self.positions.items()):
            if symbol not in self._df_cache:
                continue

            df = self._df_cache[symbol]
            exit_price = self._get_price(df, end_date, 'close')
            if exit_price is None:
                # 使用最后一个有效价格
                exit_price = df['close'].iloc[-1] if 'close' in df.columns else df['Close'].iloc[-1]

            trade.exit_date = end_date
            trade.exit_price = exit_price
            trade.exit_reason = 'end'
            trade.pnl_pct = (exit_price - trade.entry_price) / trade.entry_price
            trade.pnl = trade.shares * (exit_price - trade.entry_price)
            trade.holding_days = (end_date - trade.entry_date).days

            self.closed_trades.append(trade)

            # 返还资金
            exit_value = trade.shares * exit_price
            commission = exit_value * self.config.commission_rate
            self.cash += (exit_value - commission)

        self.positions.clear()

    def _calculate_equity(self, as_of_date: date) -> float:
        """计算当前权益"""
        equity = self.cash

        for symbol, trade in self.positions.items():
            if symbol not in self._df_cache:
                equity += trade.position_value
                continue

            df = self._df_cache[symbol]
            current_price = self._get_price(df, as_of_date, 'close')
            if current_price is None:
                equity += trade.position_value
            else:
                equity += trade.shares * current_price

        return equity

    def _calculate_performance(self) -> Dict[str, float]:
        """计算绩效统计"""
        if not self.closed_trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_return': 0.0,
                'max_drawdown': 0.0,
                'sharpe_ratio': 0.0,
                'profit_factor': 0.0,
                'avg_holding_days': 0.0,
            }

        # 基本统计
        total_trades = len(self.closed_trades)
        winning_trades = sum(1 for t in self.closed_trades if t.pnl > 0)
        losing_trades = sum(1 for t in self.closed_trades if t.pnl <= 0)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        # 收益统计
        total_pnl = sum(t.pnl for t in self.closed_trades)
        total_return = total_pnl / self.config.initial_capital

        gross_profit = sum(t.pnl for t in self.closed_trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.closed_trades if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # 最大回撤
        max_drawdown = self._calculate_max_drawdown()

        # Sharpe Ratio (简化计算，假设无风险利率为0)
        sharpe_ratio = self._calculate_sharpe_ratio()

        # 平均持仓天数
        avg_holding_days = sum(t.holding_days for t in self.closed_trades) / total_trades

        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_return': total_return,
            'total_pnl': total_pnl,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'profit_factor': profit_factor,
            'avg_holding_days': avg_holding_days,
            'final_equity': self.cash,
        }

    def _calculate_max_drawdown(self) -> float:
        """计算最大回撤"""
        if not self.equity_curve:
            return 0.0

        peak = self.equity_curve[0][1]
        max_dd = 0.0

        for _, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd

        return max_dd

    def _calculate_sharpe_ratio(self) -> float:
        """计算 Sharpe Ratio"""
        if len(self.equity_curve) < 2:
            return 0.0

        # 计算日收益率
        returns = []
        for i in range(1, len(self.equity_curve)):
            prev_equity = self.equity_curve[i-1][1]
            curr_equity = self.equity_curve[i][1]
            if prev_equity > 0:
                returns.append((curr_equity - prev_equity) / prev_equity)

        if not returns:
            return 0.0

        # 年化 Sharpe (假设252个交易日)
        import numpy as np
        returns_arr = np.array(returns)
        mean_return = np.mean(returns_arr)
        std_return = np.std(returns_arr)

        if std_return == 0:
            return 0.0

        sharpe = (mean_return / std_return) * np.sqrt(252)
        return sharpe

    def _get_price(self, df: pd.DataFrame, target_date: date, col: str) -> Optional[float]:
        """获取指定日期的价格"""
        try:
            ts = pd.Timestamp(target_date)
            if ts in df.index:
                # 兼容大小写列名
                if col in df.columns:
                    return float(df.loc[ts, col])
                elif col.capitalize() in df.columns:
                    return float(df.loc[ts, col.capitalize()])
            return None
        except Exception:
            return None

    def _collect_event(self, event: PoolEvent) -> None:
        """收集观察池事件"""
        self.pool_events.append(event)
