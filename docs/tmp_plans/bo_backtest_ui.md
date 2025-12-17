# UI 突破扫描模块与观察池系统集成方案

> **创建日期**: 2024-12-31
> **实现范围**: 适配层 + 回测引擎 + UI 集成 + 文档更新

---

## 1. 问题分析

### 1.1 现状

| 模块 | 使用的 Breakout 类 | 数据来源 |
|------|-------------------|---------|
| 突破扫描模块 | `analysis/breakout_detector.py:Breakout` | 实时计算 |
| UI 显示 | 同上 | 从 JSON 重建 |
| 观察池系统 | 同上 | 从 Breakout 创建 PoolEntry |

**关键发现**：三个模块使用**同一个 Breakout 类**，JSON → Breakout 转换逻辑已存在于 `UI/main.py:_load_from_json_cache()`。

### 1.2 核心问题

1. **代码位置不合理**：转换逻辑在 UI 私有方法中，不可被观察池复用
2. **缺少连接路径**：UI 的 Breakout 只用于绑图，从未调用 `pool_mgr.add_from_breakout()`
3. **上下文数据分散**：买入评估需要的 `volume_ma20`、`prev_close` 需要额外计算

---

## 2. 架构设计

### 2.1 模块结构

```
BreakoutStrategy/
├── observation/
│   ├── adapters/                    # 【新增】适配器层
│   │   ├── __init__.py              # 导出接口
│   │   ├── json_adapter.py          # JSON ↔ Breakout 转换
│   │   └── context_builder.py       # 评估上下文构建器
│   ├── pool_manager.py              # 【修改】添加便捷方法
│   └── ...
├── backtest/                        # 【新增】回测模块
│   ├── __init__.py
│   └── engine.py                    # 回测引擎
└── UI/
    └── main.py                      # 【修改】改用适配器 + 观察池集成
```

### 2.2 数据流

```
JSON 扫描结果                    PKL 数据
      │                            │
      ▼                            ▼
┌─────────────────────────────────────────────┐
│           BreakoutJSONAdapter               │
│  - load_single(symbol, json_data, df)       │
│  - load_batch(json_path, data_dir)          │
└─────────────────┬───────────────────────────┘
                  │ List[Breakout]
                  ▼
┌─────────────────────────────────────────────┐
│         EvaluationContextBuilder            │
│  - build_price_data(symbols, df_cache)      │
│  - build_context_for_entry(symbol, df, bo)  │
└─────────────────┬───────────────────────────┘
                  │ price_data + context
                  ▼
┌─────────────────────────────────────────────┐
│              PoolManager                    │
│  - add_from_breakout(bo)                    │
│  - check_buy_signals(price_data, context)   │
└─────────────────────────────────────────────┘
```

---

## 3. 实现计划

### Phase 1: 创建适配器模块

#### 3.1.1 `BreakoutStrategy/observation/adapters/__init__.py`

```python
from .json_adapter import BreakoutJSONAdapter, LoadResult
from .context_builder import EvaluationContextBuilder

__all__ = ['BreakoutJSONAdapter', 'LoadResult', 'EvaluationContextBuilder']
```

#### 3.1.2 `BreakoutStrategy/observation/adapters/json_adapter.py`

**核心类 `BreakoutJSONAdapter`**：

```python
@dataclass
class LoadResult:
    """单个股票的加载结果"""
    breakouts: List[Breakout]
    detector: Optional[BreakoutDetector]
    peaks: Dict[str, Peak]

class BreakoutJSONAdapter:
    """JSON ↔ Breakout 转换适配器"""

    def __init__(self, detector_params: Optional[dict] = None):
        self.detector_params = detector_params or {}

    def load_single(self, symbol: str, stock_data: dict,
                    df: pd.DataFrame) -> LoadResult:
        """
        从 JSON 数据重建单个股票的 Breakout 对象

        逻辑提取自 UI/main.py:_load_from_json_cache()
        """
        ...

    def load_batch(self, json_data: dict,
                   data_dir: str) -> Dict[date, List[Breakout]]:
        """
        批量加载 JSON 扫描结果，按日期分组

        Returns:
            {date: [Breakout, ...]} 按突破日期分组的结果
        """
        ...

    def _rebuild_peaks(self, stock_data: dict, df: pd.DataFrame,
                       time_range: tuple) -> Dict[str, Peak]:
        """重建 Peak 对象，处理索引映射"""
        ...

    def _rebuild_breakouts(self, stock_data: dict, df: pd.DataFrame,
                           peaks: Dict[str, Peak],
                           time_range: tuple) -> List[Breakout]:
        """重建 Breakout 对象，关联已重建的 Peak"""
        ...
```

**索引映射逻辑**（从 UI 提取）：
```python
def _get_df_index(self, df: pd.DataFrame, target_date: date) -> int:
    """将日期映射到 DataFrame 索引"""
    date_index = df.index.get_loc(pd.Timestamp(target_date))
    return int(date_index) if isinstance(date_index, (int, np.integer)) else int(date_index.start)
```

#### 3.1.3 `BreakoutStrategy/observation/adapters/context_builder.py`

**核心类 `EvaluationContextBuilder`**：

```python
class EvaluationContextBuilder:
    """构建买入评估所需的上下文数据"""

    def build_price_data(self, symbols: List[str],
                         df_cache: Dict[str, pd.DataFrame],
                         as_of_date: date) -> Dict[str, pd.Series]:
        """
        构建价格数据字典

        Returns:
            {symbol: Series(open, high, low, close, volume)}
        """
        ...

    def build_context_for_entry(self, symbol: str,
                                df: pd.DataFrame,
                                breakout: Breakout,
                                as_of_date: date) -> Dict:
        """
        构建单个条目的评估上下文

        Returns:
            {
                'atr_value': float,      # 从 Breakout 对象获取
                'volume_ma20': float,    # 从 DataFrame 计算
                'prev_close': float,     # 前一日收盘价
                'baseline_volume': float # 基准成交量
            }
        """
        idx = self._get_date_index(df, as_of_date)
        return {
            'atr_value': breakout.atr_value,
            'volume_ma20': df['volume'].iloc[max(0, idx-20):idx].mean(),
            'prev_close': df['close'].iloc[idx-1] if idx > 0 else df['close'].iloc[idx],
            'baseline_volume': df['volume'].iloc[max(0, idx-20):idx].mean()
        }

    def build_batch_context(self, entries_with_breakouts: List[tuple],
                            df_cache: Dict[str, pd.DataFrame],
                            as_of_date: date) -> Dict[str, Dict]:
        """
        批量构建评估上下文

        Args:
            entries_with_breakouts: [(PoolEntry, Breakout), ...]

        Returns:
            {symbol: context_dict}
        """
        ...
```

**上下文字段来源**：

| 字段 | 来源 | 说明 |
|------|------|------|
| `atr_value` | `Breakout.atr_value` | 已在 JSON 中保存 |
| `volume_ma20` | DataFrame 计算 | `df['volume'].rolling(20).mean()` |
| `prev_close` | DataFrame | `df['close'].iloc[idx-1]` |
| `baseline_volume` | 同 `volume_ma20` | 用于成交量比较 |

---

### Phase 2: 修改现有文件

#### 3.2.1 修改 `BreakoutStrategy/observation/__init__.py`

添加 adapters 导出：

```python
# 适配器
from .adapters import BreakoutJSONAdapter, LoadResult, EvaluationContextBuilder

__all__ = [
    # ... 现有导出 ...
    # 适配器
    'BreakoutJSONAdapter',
    'LoadResult',
    'EvaluationContextBuilder',
]
```

#### 3.2.2 修改 `BreakoutStrategy/observation/pool_manager.py`

添加便捷方法：

```python
class PoolManager:
    # ... 现有代码 ...

    def add_batch_by_date(self, breakouts_by_date: Dict[date, List[Breakout]],
                          up_to_date: date) -> int:
        """
        按日期批量添加突破到观察池

        Args:
            breakouts_by_date: {date: [Breakout, ...]} 按日期分组的突破
            up_to_date: 处理到哪一天（包含）

        Returns:
            添加的条目数量
        """
        count = 0
        for bo_date in sorted(breakouts_by_date.keys()):
            if bo_date > up_to_date:
                break
            for bo in breakouts_by_date[bo_date]:
                self.add_from_breakout(bo)
                count += 1
        return count

    def get_entries_with_breakouts(self) -> List[Tuple[PoolEntry, Optional[Breakout]]]:
        """
        获取所有活跃条目及其关联的 Breakout 对象

        Returns:
            [(entry, breakout), ...] breakout 可能为 None（从数据库恢复时）
        """
        result = []
        for entry in self.get_active_entries():
            result.append((entry, entry.breakout))
        return result
```

#### 3.2.3 修改 `BreakoutStrategy/UI/main.py`

将 `_load_from_json_cache()` 改为使用适配器：

```python
def _load_from_json_cache(self, symbol: str, params: dict,
                          df: pd.DataFrame) -> Tuple[List, Optional[BreakoutDetector]]:
    """从 JSON 缓存加载突破数据"""
    from BreakoutStrategy.observation.adapters import BreakoutJSONAdapter

    # 获取 JSON 数据
    stock_data = self.scan_manager.get_scan_results().get(symbol)
    if not stock_data:
        return [], None

    # 使用适配器加载
    adapter = BreakoutJSONAdapter(detector_params=params)
    result = adapter.load_single(symbol, stock_data, df)

    return result.breakouts, result.detector
```

---

### Phase 3: 回测引擎实现

#### 3.3.1 `BreakoutStrategy/backtest/__init__.py`

```python
from .engine import BacktestEngine, BacktestConfig, BacktestResult

__all__ = ['BacktestEngine', 'BacktestConfig', 'BacktestResult']
```

#### 3.3.2 `BreakoutStrategy/backtest/engine.py`

**数据结构**：

```python
@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 100000      # 初始资金
    stop_loss_pct: float = 0.05          # 止损比例
    take_profit_pct: float = 0.15        # 止盈比例
    max_holdings: int = 10               # 最大持仓数
    max_position_size_pct: float = 0.10  # 单个持仓最大比例
    buy_condition_config_path: str = 'configs/buy_condition_config.yaml'

@dataclass
class Trade:
    """单笔交易记录"""
    symbol: str
    entry_date: date
    entry_price: float
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    exit_reason: str = ''  # 'stop_loss' | 'take_profit' | 'signal' | 'end'
    pnl: float = 0.0
    pnl_pct: float = 0.0

@dataclass
class BacktestResult:
    """回测结果"""
    trades: List[Trade]
    equity_curve: List[Tuple[date, float]]
    performance: Dict[str, float]  # total_return, win_rate, sharpe, max_drawdown, etc.
    pool_events: List[PoolEvent]
```

**核心类 `BacktestEngine`**：

```python
class BacktestEngine:
    """基于观察池的回测引擎"""

    def __init__(self, config: BacktestConfig,
                 scan_result_path: str,
                 data_dir: str):
        self.config = config
        self.scan_result_path = scan_result_path
        self.data_dir = data_dir

        # 初始化组件
        self.adapter = BreakoutJSONAdapter()
        self.context_builder = EvaluationContextBuilder()
        self.pool_mgr = None  # 在 run() 中初始化

        # 状态
        self.positions: Dict[str, Trade] = {}
        self.closed_trades: List[Trade] = []
        self.equity_curve: List[Tuple[date, float]] = []
        self.cash = config.initial_capital

    def run(self, start_date: str, end_date: str) -> BacktestResult:
        """
        执行回测

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        # 1. 加载数据
        json_data = self._load_scan_results()
        breakouts_by_date = self.adapter.load_batch(json_data, self.data_dir)
        df_cache = self._load_dataframes(json_data.keys())
        trading_days = self._get_trading_days(start, end, df_cache)

        # 2. 初始化观察池
        self.pool_mgr = create_backtest_pool_manager(start)

        # 3. 主循环
        for trading_day in trading_days:
            self._process_day(trading_day, breakouts_by_date, df_cache)

        # 4. 清算剩余持仓
        self._liquidate_all(end, df_cache)

        # 5. 计算绩效
        performance = self._calculate_performance()

        return BacktestResult(
            trades=self.closed_trades,
            equity_curve=self.equity_curve,
            performance=performance,
            pool_events=self.pool_mgr.get_events()
        )

    def _process_day(self, trading_day: date,
                     breakouts_by_date: Dict,
                     df_cache: Dict):
        """处理单个交易日"""
        # 1. 获取当日突破并加入观察池
        todays_breakouts = breakouts_by_date.get(trading_day, [])
        for bo in todays_breakouts:
            self.pool_mgr.add_from_breakout(bo)

        # 2. 构建价格数据和上下文
        active_symbols = [e.symbol for e in self.pool_mgr.get_active_entries()]
        price_data = self.context_builder.build_price_data(
            active_symbols, df_cache, trading_day
        )

        entries_with_bo = self.pool_mgr.get_entries_with_breakouts()
        context = self.context_builder.build_batch_context(
            entries_with_bo, df_cache, trading_day
        )

        # 3. 检查买入信号
        signals = self.pool_mgr.check_buy_signals(price_data, context)

        # 4. 执行买入
        for signal in signals:
            if len(self.positions) < self.config.max_holdings:
                self._execute_buy(signal, trading_day, price_data)

        # 5. 更新持仓（止盈止损）
        self._update_positions(trading_day, price_data)

        # 6. 记录权益曲线
        equity = self._calculate_equity(price_data)
        self.equity_curve.append((trading_day, equity))

        # 7. 推进观察池
        self.pool_mgr.advance_day()

    def _execute_buy(self, signal: BuySignal, trading_day: date,
                     price_data: Dict):
        """执行买入"""
        symbol = signal.symbol
        price = signal.suggested_price or price_data[symbol]['close']

        # 计算仓位大小
        position_value = min(
            self.cash * self.config.max_position_size_pct,
            self.cash / (self.config.max_holdings - len(self.positions))
        )

        if position_value > self.cash:
            return

        self.positions[symbol] = Trade(
            symbol=symbol,
            entry_date=trading_day,
            entry_price=price
        )
        self.cash -= position_value

    def _update_positions(self, trading_day: date, price_data: Dict):
        """更新持仓，检查止盈止损"""
        to_close = []

        for symbol, trade in self.positions.items():
            if symbol not in price_data:
                continue

            current_price = price_data[symbol]['close']
            pnl_pct = (current_price - trade.entry_price) / trade.entry_price

            # 止损
            if pnl_pct <= -self.config.stop_loss_pct:
                trade.exit_date = trading_day
                trade.exit_price = current_price
                trade.exit_reason = 'stop_loss'
                trade.pnl_pct = pnl_pct
                to_close.append(symbol)

            # 止盈
            elif pnl_pct >= self.config.take_profit_pct:
                trade.exit_date = trading_day
                trade.exit_price = current_price
                trade.exit_reason = 'take_profit'
                trade.pnl_pct = pnl_pct
                to_close.append(symbol)

        # 移动到已平仓列表
        for symbol in to_close:
            trade = self.positions.pop(symbol)
            self.closed_trades.append(trade)
            # 返还资金
            self.cash += trade.entry_price * (1 + trade.pnl_pct)
```

#### 3.3.3 回测入口脚本 `scripts/backtest/pool_backtest.py`

```python
"""
观察池回测脚本

使用方法：
    python scripts/backtest/realtime_pool_backtest.py

配置参数在 main() 函数中设置
"""
from datetime import date
from BreakoutStrategy.backtest import BacktestEngine, BacktestConfig


def main():
    # ===== 配置参数 =====
    scan_result_path = 'outputs/scan_results.json'
    data_dir = 'datasets/pkls'
    start_date = '2024-01-01'
    end_date = '2024-06-30'

    config = BacktestConfig(
        initial_capital=100000,
        stop_loss_pct=0.05,
        take_profit_pct=0.15,
        max_holdings=10,
        max_position_size_pct=0.10,
    )

    # ===== 执行回测 =====
    engine = BacktestEngine(
        config=config,
        scan_result_path=scan_result_path,
        data_dir=data_dir
    )

    result = engine.run(start_date=start_date, end_date=end_date)

    # ===== 输出结果 =====
    print("\n===== Backtest Results =====")
    print(f"Total Trades: {len(result.trades)}")
    print(f"Win Rate: {result.performance.get('win_rate', 0):.2%}")
    print(f"Total Return: {result.performance.get('total_return', 0):.2%}")
    print(f"Max Drawdown: {result.performance.get('max_drawdown', 0):.2%}")
    print(f"Sharpe Ratio: {result.performance.get('sharpe_ratio', 0):.2f}")


if __name__ == '__main__':
    main()
```

---

### Phase 4: UI 集成

#### 3.4.1 修改 `BreakoutStrategy/UI/main.py`

添加观察池管理器和相关方法：

```python
class InteractiveUI:
    def __init__(self, root):
        # ... 现有代码 ...
        self.pool_mgr = None  # 懒加载

    def _get_or_create_pool_manager(self) -> PoolManager:
        """获取或创建观察池管理器"""
        if self.pool_mgr is None:
            from BreakoutStrategy.observation import create_backtest_pool_manager
            self.pool_mgr = create_backtest_pool_manager(date.today())
        return self.pool_mgr

    def add_to_observation_pool(self):
        """将当前股票的突破添加到观察池"""
        if not hasattr(self, 'current_breakouts') or not self.current_breakouts:
            self.param_panel.set_status("No breakouts to add", "orange")
            return

        pool_mgr = self._get_or_create_pool_manager()
        added = 0
        for bo in self.current_breakouts:
            pool_mgr.add_from_breakout(bo)
            added += 1

        self.param_panel.set_status(
            f"Added {added} breakouts to observation pool", "green"
        )

    def show_pool_status(self):
        """显示观察池状态"""
        pool_mgr = self._get_or_create_pool_manager()

        realtime_count = len(pool_mgr.realtime_pool.get_active_entries())
        daily_count = len(pool_mgr.daily_pool.get_active_entries())

        status_msg = f"Pool Status: Realtime={realtime_count}, Daily={daily_count}"
        self.param_panel.set_status(status_msg, "blue")
```

#### 3.4.2 添加 UI 菜单项/按钮

在 `param_panel.py` 或 `stock_list_panel.py` 中添加：

```python
# 添加按钮
self.add_to_pool_btn = ttk.Button(
    button_frame,
    text="Add to Pool",
    command=self.parent.add_to_observation_pool
)
self.add_to_pool_btn.pack(side=tk.LEFT, padx=2)

# 或右键菜单
self.context_menu.add_command(
    label="Add to Observation Pool",
    command=self._add_selected_to_pool
)
```

---

### Phase 5: 文档更新

#### 3.5.1 更新 `docs/modules/specs/04_观察池系统_IMPL.md`

添加章节：

```markdown
## 7. 适配器模块

### 7.1 BreakoutJSONAdapter

用于将 JSON 扫描结果转换为 Breakout 对象：

```python
from BreakoutStrategy.observation.adapters import BreakoutJSONAdapter

adapter = BreakoutJSONAdapter()
result = adapter.load_single(symbol, stock_data, df)
breakouts = result.breakouts
```

### 7.2 EvaluationContextBuilder

构建买入评估所需的上下文数据：

```python
from BreakoutStrategy.observation.adapters import EvaluationContextBuilder

builder = EvaluationContextBuilder()
context = builder.build_context_for_entry(symbol, df, breakout, as_of_date)
```

## 8. 回测引擎使用

```python
from BreakoutStrategy.backtest import BacktestEngine, BacktestConfig

config = BacktestConfig(initial_capital=100000)
engine = BacktestEngine(config, 'outputs/scan.json', 'datasets/pkls')
result = engine.run('2024-01-01', '2024-06-30')
```
```

#### 3.5.2 更新 `docs/system/current_state.md`

```markdown
### 观察池系统 (4/5)
- [x] 核心架构（双池、状态机）
- [x] 买入条件评估器
- [x] 适配器层（JSON ↔ Breakout）  ← 新增
- [x] 回测引擎（BacktestEngine）    ← 新增
- [ ] 实盘数据库持久化
```

---

## 4. 文件清单

### 4.1 新增文件（6 个）

| 文件 | 说明 | 行数估计 |
|-----|------|---------|
| `observation/adapters/__init__.py` | 适配器模块导出 | ~10 |
| `observation/adapters/json_adapter.py` | JSON ↔ Breakout 转换 | ~200 |
| `observation/adapters/context_builder.py` | 评估上下文构建 | ~100 |
| `backtest/__init__.py` | 回测模块导出 | ~5 |
| `backtest/engine.py` | 回测引擎 | ~300 |
| `scripts/backtest/pool_backtest.py` | 回测入口脚本 | ~50 |

### 4.2 修改文件（5 个）

| 文件 | 修改内容 |
|-----|---------|
| `observation/__init__.py` | 添加 adapters 导出 |
| `observation/pool_manager.py` | 添加 `add_batch_by_date()`, `get_entries_with_breakouts()` |
| `UI/main.py` | 改用适配器 + 观察池集成方法 |
| `docs/modules/specs/04_观察池系统_IMPL.md` | 添加适配器/回测使用说明 |
| `docs/system/current_state.md` | 更新进度标记 |

---

## 5. 关键设计决策

| 决策 | 理由 |
|------|------|
| 适配器放在 `observation/` 内 | 服务于观察池系统，UI 作为调用方 |
| 保持 Breakout 类不变 | 三模块共用同一类，避免重复定义 |
| 上下文实时计算 | `volume_ma20` 等从 DataFrame 计算，避免 JSON 膨胀 |
| ATR 复用 JSON 数据 | 已在扫描时计算，直接从 Breakout 读取 |
| UI 观察池懒加载 | 避免不需要时的初始化开销 |
| 回测引擎独立模块 | 与 `simple_backtest.py` 并存，可逐步迁移 |

---

## 6. 实现顺序

```
Phase 1: 适配器层
    ├── 创建 adapters/ 目录结构
    ├── 实现 json_adapter.py（从 UI 提取逻辑）
    └── 实现 context_builder.py

Phase 2: 现有文件修改
    ├── 更新 observation/__init__.py
    ├── 扩展 pool_manager.py
    └── 重构 UI/main.py

Phase 3: 回测引擎
    ├── 创建 backtest/ 模块
    ├── 实现 engine.py
    └── 创建入口脚本

Phase 4: UI 集成
    ├── 添加观察池管理方法
    └── 添加 UI 控件

Phase 5: 文档
    ├── 更新实现规格文档
    └── 更新开发状态索引
```
