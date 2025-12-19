# 回测系统技术设计文档

**模块路径**：`BreakoutStrategy/backtest/`
**创建日期**：2025-11-16

---

## 一、模块概述

回测系统用于验证突破选股策略的有效性，模拟历史交易，计算性能指标，并支持参数优化。

**核心职责**：
1. 模拟历史交易过程
2. 计算性能指标（收益率、夏普比率、最大回撤等）
3. 生成回测报告
4. 支持参数优化（基于Optuna）

**依赖**：
- `search`：搜索历史突破
- `analysis`：技术分析
- `data`：获取历史数据
- `config`：回测参数

---

## 二、模块架构

```
BreakoutStrategy/backtest/
├── __init__.py
├── backtest_engine.py        # BacktestEngine - 回测引擎
├── performance.py             # PerformanceAnalyzer - 性能分析
├── optimizer.py               # ParameterOptimizer - 参数优化
└── report.py                  # ReportGenerator - 报告生成
```

---

## 三、回测流程

```
加载历史数据 → 搜索突破 → 模拟买入 → 持仓管理 → 模拟卖出 → 计算收益
     ↓              ↓            ↓           ↓            ↓           ↓
   时间范围       凸点/突破    买入信号   止盈/止损    卖出信号   性能指标
```

---

## 四、BacktestEngine（回测引擎）

### 4.1 核心数据结构

```python
from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass
class Position:
    """持仓"""
    symbol: str
    entry_date: date
    entry_price: float
    quantity: int
    stop_loss_price: float
    take_profit_price: Optional[float] = None
    trailing_stop_price: Optional[float] = None
    max_price: float = 0.0  # 持仓期间最高价

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
    exit_reason: str  # 'take_profit', 'stop_loss', 'timeout'
```

### 4.2 回测引擎实现

```python
from typing import List, Dict, Optional
import pandas as pd
from datetime import datetime, timedelta

class BacktestEngine:
    """回测引擎"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化回测引擎

        Args:
            config: 回测配置
        """
        if config is None:
            from BreakoutStrategy.config import ConfigManager
            cfg = ConfigManager.get_instance()
            self.config = cfg.get_section('backtest')
            self.risk_config = cfg.get_section('risk')
        else:
            self.config = config
            self.risk_config = config.get('risk', {})

        # 回测参数
        self.initial_capital = self.config.get('initial_capital', 100000)
        self.commission_rate = self.config.get('commission_rate', 0.001)
        self.slippage = self.config.get('slippage', 0.001)

        # 风险管理参数
        self.stop_loss_pct = self.risk_config.get('stop_loss_pct', 0.05)
        self.trailing_stop_pct = self.risk_config.get('trailing_stop_pct', 0.03)
        self.target_profit_pct = self.risk_config.get('target_profit_pct', 0.15)
        self.max_holdings = self.risk_config.get('max_holdings', 10)
        self.max_position_size_pct = self.risk_config.get('max_position_size_pct', 0.10)

        # 状态
        self.cash = self.initial_capital
        self.positions: Dict[str, Position] = {}  # {symbol: Position}
        self.trades: List[Trade] = []
        self.equity_curve = []  # [(date, equity), ...]

        # 依赖模块
        from BreakoutStrategy.search import SearchEngine
        from BreakoutStrategy.data import DataManager

        self.search_engine = SearchEngine()
        self.data_manager = DataManager()

        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('backtest.engine')

    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        search_frequency: str = 'daily'  # 'daily', 'weekly'
    ) -> Dict:
        """
        运行回测

        Args:
            start_date: 回测开始日期
            end_date: 回测结束日期
            search_frequency: 搜索频率

        Returns:
            回测结果字典
        """
        self.logger.info(f"Starting backtest: {start_date} to {end_date}")

        # 1. 生成回测日期序列
        from BreakoutStrategy.utils.date_utils import DateUtils
        trading_days = DateUtils.get_trading_days(
            datetime.strptime(start_date, '%Y-%m-%d').date(),
            datetime.strptime(end_date, '%Y-%m-%d').date()
        )

        # 2. 逐日回测
        for current_date in trading_days:
            self._process_day(current_date, search_frequency)

            # 记录权益曲线
            equity = self._calculate_equity(current_date)
            self.equity_curve.append((current_date, equity))

        # 3. 平仓所有持仓
        self._close_all_positions(trading_days[-1])

        # 4. 计算性能指标
        performance = self._calculate_performance()

        self.logger.info(f"Backtest completed: {len(self.trades)} trades, "
                        f"final equity: ${equity:.2f}")

        return {
            'trades': self.trades,
            'equity_curve': self.equity_curve,
            'performance': performance
        }

    def _process_day(self, current_date: date, search_frequency: str):
        """
        处理单日回测

        流程：
        1. 检查是否需要搜索新的突破（根据search_frequency）
        2. 更新持仓（检查止盈止损）
        3. 处理买入信号
        """
        # 1. 搜索新的突破（每日或每周）
        should_search = (
            search_frequency == 'daily' or
            (search_frequency == 'weekly' and current_date.weekday() == 0)
        )

        if should_search:
            self._search_and_buy(current_date)

        # 2. 更新持仓
        self._update_positions(current_date)

    def _search_and_buy(self, current_date: date):
        """搜索突破并尝试买入"""
        # 搜索过去N天的突破
        from BreakoutStrategy.config import ConfigManager
        cfg = ConfigManager.get_instance()
        historical_days = cfg.get('time.historical_search_days', 7)

        results = self.search_engine.search(
            end_date=current_date.isoformat(),
            historical_days=historical_days
        )

        # 按综合分数排序，买入最高分的N只
        for _, row in results.head(self.max_holdings - len(self.positions)).iterrows():
            symbol = row['symbol']

            # 如果已持有，跳过
            if symbol in self.positions:
                continue

            # 获取当前价格（次日开盘价，模拟实盘）
            try:
                df = self.data_manager.get_historical_data(
                    symbol,
                    current_date.isoformat(),
                    (current_date + timedelta(days=5)).isoformat()
                )

                if df.empty:
                    continue

                # 使用次日开盘价买入（模拟延迟）
                next_day_data = df.iloc[0] if len(df) > 0 else None
                if next_day_data is None:
                    continue

                entry_price = next_day_data['open'] * (1 + self.slippage)  # 加滑点

                # 计算买入数量
                position_size = self.cash * self.max_position_size_pct
                quantity = int(position_size / entry_price)

                if quantity == 0:
                    continue

                # 计算止损价
                stop_loss_price = entry_price * (1 - self.stop_loss_pct)

                # 买入
                cost = entry_price * quantity * (1 + self.commission_rate)
                if cost <= self.cash:
                    self.cash -= cost

                    position = Position(
                        symbol=symbol,
                        entry_date=current_date,
                        entry_price=entry_price,
                        quantity=quantity,
                        stop_loss_price=stop_loss_price,
                        max_price=entry_price
                    )
                    self.positions[symbol] = position

                    self.logger.debug(f"Bought {symbol} @ ${entry_price:.2f} x {quantity}")

            except Exception as e:
                self.logger.error(f"Failed to buy {symbol}: {e}")

    def _update_positions(self, current_date: date):
        """更新持仓，检查止盈止损"""
        to_close = []

        for symbol, position in self.positions.items():
            try:
                # 获取当日价格
                df = self.data_manager.get_historical_data(
                    symbol,
                    current_date.isoformat(),
                    (current_date + timedelta(days=1)).isoformat()
                )

                if df.empty:
                    continue

                today_data = df.iloc[0]
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

                # 检查目标止盈
                target_price = position.entry_price * (1 + self.target_profit_pct)
                if high_price >= target_price:
                    to_close.append((symbol, target_price, 'take_profit'))
                    continue

            except Exception as e:
                self.logger.error(f"Failed to update {symbol}: {e}")

        # 平仓
        for symbol, exit_price, reason in to_close:
            self._close_position(symbol, current_date, exit_price, reason)

    def _close_position(self, symbol: str, exit_date: date, exit_price: float, reason: str):
        """平仓"""
        if symbol not in self.positions:
            return

        position = self.positions[symbol]

        # 计算收益
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

        self.logger.debug(f"Closed {symbol} @ ${exit_price:.2f}, PnL: ${pnl:.2f} ({pnl_pct*100:.2f}%), Reason: {reason}")

        # 移除持仓
        del self.positions[symbol]

    def _close_all_positions(self, final_date: date):
        """平仓所有剩余持仓"""
        for symbol in list(self.positions.keys()):
            try:
                df = self.data_manager.get_historical_data(
                    symbol,
                    final_date.isoformat(),
                    (final_date + timedelta(days=1)).isoformat()
                )
                if not df.empty:
                    close_price = df.iloc[0]['close']
                    self._close_position(symbol, final_date, close_price, 'end_of_backtest')
            except Exception as e:
                self.logger.error(f"Failed to close {symbol}: {e}")

    def _calculate_equity(self, current_date: date) -> float:
        """计算当前权益"""
        equity = self.cash

        for symbol, position in self.positions.items():
            try:
                df = self.data_manager.get_historical_data(
                    symbol,
                    current_date.isoformat(),
                    (current_date + timedelta(days=1)).isoformat()
                )
                if not df.empty:
                    current_price = df.iloc[0]['close']
                    equity += current_price * position.quantity
            except:
                # 如果获取不到价格，使用买入价估算
                equity += position.entry_price * position.quantity

        return equity

    def _calculate_performance(self) -> Dict:
        """计算性能指标"""
        from BreakoutStrategy.backtest.performance import PerformanceAnalyzer

        analyzer = PerformanceAnalyzer(
            trades=self.trades,
            equity_curve=self.equity_curve,
            initial_capital=self.initial_capital
        )

        return analyzer.calculate_metrics()
```

---

## 五、PerformanceAnalyzer（性能分析）

```python
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict

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

        # 转换为Series
        self.equity_series = pd.Series(
            [eq for _, eq in equity_curve],
            index=[dt for dt, _ in equity_curve]
        )

    def calculate_metrics(self) -> Dict:
        """计算所有性能指标"""
        return {
            **self._calculate_returns(),
            **self._calculate_risk_metrics(),
            **self._calculate_trade_statistics()
        }

    def _calculate_returns(self) -> Dict:
        """计算收益指标"""
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
            'volatility': daily_returns.std() * np.sqrt(252)
        }

    def _calculate_max_drawdown(self) -> Tuple[float, int]:
        """计算最大回撤和持续时间"""
        cum_max = self.equity_series.cummax()
        drawdown = (self.equity_series - cum_max) / cum_max

        max_dd = drawdown.min()

        # 计算最大回撤持续时间
        is_drawdown = drawdown < 0
        drawdown_periods = is_drawdown.astype(int).diff().fillna(0)

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
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'avg_holding_days': 0
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
        report.append(f"  Max DD Duration: {metrics['max_drawdown_duration_days']} days\n")

        report.append("Trade Statistics:")
        report.append(f"  Total Trades: {metrics['total_trades']}")
        report.append(f"  Win Rate: {metrics['win_rate_pct']:.2f}%")
        report.append(f"  Profit Factor: {metrics['profit_factor']:.2f}")
        report.append(f"  Avg Win: ${metrics['avg_win']:.2f}")
        report.append(f"  Avg Loss: ${metrics['avg_loss']:.2f}")
        report.append(f"  Avg Holding: {metrics['avg_holding_days']:.1f} days")

        return "\n".join(report)
```

---

## 六、ParameterOptimizer（参数优化）

```python
import optuna
from typing import Dict, Callable

class ParameterOptimizer:
    """参数优化器（基于Optuna）"""

    def __init__(self, objective_metric: str = 'sharpe_ratio'):
        """
        Args:
            objective_metric: 优化目标指标
                - 'sharpe_ratio', 'sortino_ratio', 'calmar_ratio'
                - 'total_return', 'annual_return'
        """
        self.objective_metric = objective_metric

        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('backtest.optimizer')

    def optimize(
        self,
        start_date: str,
        end_date: str,
        n_trials: int = 100,
        timeout: Optional[int] = None
    ) -> Dict:
        """
        优化参数

        Args:
            start_date: 回测开始日期
            end_date: 回测结束日期
            n_trials: 优化试验次数
            timeout: 超时时间（秒）

        Returns:
            最优参数字典
        """
        def objective(trial: optuna.Trial) -> float:
            """优化目标函数"""
            # 定义参数空间
            params = {
                'stop_loss_pct': trial.suggest_float('stop_loss_pct', 0.02, 0.10),
                'trailing_stop_pct': trial.suggest_float('trailing_stop_pct', 0.01, 0.05),
                'target_profit_pct': trial.suggest_float('target_profit_pct', 0.10, 0.30),
                'peak_quality_min_score': trial.suggest_int('peak_quality_min_score', 50, 80),
                'breakout_quality_min_score': trial.suggest_int('breakout_quality_min_score', 60, 90),
                'max_holdings': trial.suggest_int('max_holdings', 5, 15),
                'max_position_size_pct': trial.suggest_float('max_position_size_pct', 0.05, 0.15)
            }

            # 运行回测
            engine = BacktestEngine(config={'backtest': {}, 'risk': params})
            result = engine.run_backtest(start_date, end_date)

            # 返回目标指标
            metric_value = result['performance'][self.objective_metric]

            return metric_value

        # 创建Optuna study
        study = optuna.create_study(
            direction='maximize',
            study_name='breakout_strategy_optimization'
        )

        # 执行优化
        study.optimize(objective, n_trials=n_trials, timeout=timeout)

        self.logger.info(f"Optimization completed: best {self.objective_metric} = {study.best_value:.4f}")
        self.logger.info(f"Best parameters: {study.best_params}")

        return {
            'best_params': study.best_params,
            'best_value': study.best_value,
            'study': study
        }
```

---

## 七、使用示例

### 7.1 简单回测

```python
from BreakoutStrategy.backtest import BacktestEngine

# 1. 初始化回测引擎
engine = BacktestEngine()

# 2. 运行回测
result = engine.run_backtest(
    start_date='2020-01-01',
    end_date='2024-01-01',
    search_frequency='daily'
)

# 3. 查看性能
from BreakoutStrategy.backtest.performance import PerformanceAnalyzer
analyzer = PerformanceAnalyzer(
    result['trades'],
    result['equity_curve'],
    engine.initial_capital
)

print(analyzer.generate_summary())

# 4. 可视化
from BreakoutStrategy.utils.visualizer import Visualizer
viz = Visualizer()

# 绘制权益曲线
equity_df = pd.DataFrame(result['equity_curve'], columns=['date', 'equity'])
equity_df.set_index('date', inplace=True)
viz.plot_equity_curve(equity_df['equity'])

# 绘制回撤
viz.plot_drawdown(equity_df['equity'])
```

### 7.2 参数优化

```python
from BreakoutStrategy.backtest import ParameterOptimizer

# 1. 初始化优化器
optimizer = ParameterOptimizer(objective_metric='sharpe_ratio')

# 2. 执行优化
result = optimizer.optimize(
    start_date='2020-01-01',
    end_date='2023-01-01',
    n_trials=100
)

# 3. 使用最优参数进行验证
best_params = result['best_params']
engine = BacktestEngine(config={'risk': best_params})

# 样本外测试
validation_result = engine.run_backtest(
    start_date='2023-01-01',
    end_date='2024-01-01'
)
```

---

## 八、性能报告示例

```
=== Backtest Performance Summary ===

Returns:
  Total Return: 45.80%
  Annual Return: 18.32%
  Final Equity: $145,800.00

Risk Metrics:
  Sharpe Ratio: 1.52
  Sortino Ratio: 2.18
  Calmar Ratio: 1.24
  Max Drawdown: -14.75%
  Max DD Duration: 45 days

Trade Statistics:
  Total Trades: 87
  Win Rate: 58.62%
  Profit Factor: 1.85
  Avg Win: $1,250.50
  Avg Loss: $-420.30
  Avg Holding: 8.5 days
```

---

## 九、测试方案

```python
# tests/backtest/test_backtest_engine.py
import pytest
from BreakoutStrategy.backtest import BacktestEngine

class TestBacktestEngine:

    def test_simple_backtest(self):
        """测试简单回测"""
        engine = BacktestEngine()

        result = engine.run_backtest(
            start_date='2023-01-01',
            end_date='2023-06-30'
        )

        assert 'trades' in result
        assert 'equity_curve' in result
        assert 'performance' in result

        # 验证权益曲线
        assert len(result['equity_curve']) > 0

    def test_performance_metrics(self):
        """测试性能指标计算"""
        from BreakoutStrategy.backtest.performance import PerformanceAnalyzer

        # 构造测试数据
        # ...

        analyzer = PerformanceAnalyzer(trades, equity_curve, 100000)
        metrics = analyzer.calculate_metrics()

        assert 'sharpe_ratio' in metrics
        assert 'max_drawdown' in metrics
        assert 'win_rate' in metrics
```

---

**文档状态**：初稿完成
**下一步**：编写观察池系统设计文档
