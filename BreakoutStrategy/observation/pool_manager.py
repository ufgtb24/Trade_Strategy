"""
观察池管理器

统一管理双池（实时池 + 日K池），提供：
- 输入接口：从不同来源添加条目
- 时间推进：回测用的每日推进
- 买入信号检测：评估买入条件
- 查询接口：获取池状态
- 事件系统：模块间通信
"""
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

import pandas as pd

from .interfaces import ITimeProvider, IPoolStorage
from .pool_base import ObservationPoolBase
from .pool_entry import PoolEntry
from .signals import BuySignal, PoolEvent, PoolEventType
from .evaluators import (
    CompositeBuyEvaluator,
    BuyConditionConfig,
    EvaluationAction,
)

if TYPE_CHECKING:
    from BreakoutStrategy.analysis import Breakout


class PoolManager:
    """
    观察池管理器（统一入口）

    职责：
    - 管理双池（实时池 + 日K池）
    - 处理池间转换（实时池超时 → 日K池）
    - 提供统一的对外接口
    - 发射事件供其他模块监听

    架构设计：
    - 实时池（RealtimePool）：观察当日突破，观察期默认1天
    - 日K池（DailyPool）：长期跟踪，观察期默认30天

    使用示例（回测）：
        from BreakoutStrategy.observation import create_backtest_pool_manager

        pool_mgr = create_backtest_pool_manager(
            start_date=date(2024, 1, 1),
            config={'realtime_observation_days': 1, 'daily_observation_days': 30}
        )

        # 添加突破
        pool_mgr.add_from_breakout(breakout)

        # 每日推进
        pool_mgr.advance_day()

        # 检查买入信号
        signals = pool_mgr.check_buy_signals(price_data)
    """

    def __init__(self,
                 time_provider: ITimeProvider,
                 storage: IPoolStorage,
                 config: Optional[dict] = None):
        """
        初始化观察池管理器

        Args:
            time_provider: 时间提供者
            storage: 存储策略
            config: 配置参数
                - realtime_observation_days: 实时池观察天数，默认1
                - daily_observation_days: 日K池观察天数，默认30
                - min_quality_score: 最低质量评分阈值，默认0
                - buy_confirm_threshold: 买入确认阈值（超过峰值的百分比），默认0.02
        """
        config = config or {}
        self.time_provider = time_provider
        self.storage = storage
        self.config = config

        # 初始化双池
        self.realtime_pool = ObservationPoolBase(
            pool_type='realtime',
            time_provider=time_provider,
            storage=storage,
            observation_days=config.get('realtime_observation_days', 1),
            config=config
        )
        self.daily_pool = ObservationPoolBase(
            pool_type='daily',
            time_provider=time_provider,
            storage=storage,
            observation_days=config.get('daily_observation_days', 30),
            config=config
        )

        # 配置参数
        self.min_quality_threshold = config.get('min_quality_score', 0)
        self.buy_confirm_threshold = config.get('buy_confirm_threshold', 0.02)

        # 初始化买入条件评估器
        self._init_buy_evaluator(config)

        # 事件监听器
        self._event_listeners: List[Callable[[PoolEvent], None]] = []

    def _init_buy_evaluator(self, config: dict) -> None:
        """
        初始化买入条件评估器

        Args:
            config: 配置参数，可包含：
                - buy_condition_config: BuyConditionConfig 实例
                - buy_condition_config_path: YAML 配置文件路径
                - mode: 'realtime' | 'backtest'
        """
        # 检查是否提供了评估器配置
        if 'buy_condition_config' in config:
            buy_config = config['buy_condition_config']
        elif 'buy_condition_config_path' in config:
            buy_config = BuyConditionConfig.from_yaml(config['buy_condition_config_path'])
        else:
            # 使用默认配置
            buy_config = BuyConditionConfig()

        # 根据时间提供者类型设置模式
        if self.time_provider.is_backtest_mode():
            buy_config.mode = 'backtest'
        else:
            buy_config.mode = config.get('mode', 'realtime')

        self.buy_evaluator = CompositeBuyEvaluator(buy_config)
        self.buy_condition_config = buy_config

    # ===== 输入接口 =====

    def add_from_breakout(self, breakout: 'Breakout') -> bool:
        """
        从技术分析模块接收突破结果

        根据突破日期自动分配到实时池或日K池：
        - 当日突破 → 实时池
        - 历史突破 → 日K池

        Args:
            breakout: Breakout 对象

        Returns:
            是否添加成功
        """
        # 质量评分过滤
        if breakout.quality_score is not None:
            if breakout.quality_score < self.min_quality_threshold:
                print(f"[PoolManager] {breakout.symbol} quality score "
                      f"{breakout.quality_score:.2f} < {self.min_quality_threshold}, skipping")
                return False

        entry = PoolEntry.from_breakout(breakout)
        today = self.time_provider.get_current_date()

        # 根据突破日期分配到对应池
        if breakout.date == today:
            success = self.realtime_pool.add(entry)
        else:
            entry.pool_type = 'daily'
            success = self.daily_pool.add(entry)

        if success:
            self._emit_event(PoolEvent(
                event_type=PoolEventType.ENTRY_ADDED,
                entry=entry,
                timestamp=datetime.now()
            ))

        return success

    def add_from_search_results(self,
                                results_df: pd.DataFrame,
                                breakouts: Optional[Dict[str, 'Breakout']] = None) -> int:
        """
        从搜索结果批量添加

        Args:
            results_df: 搜索结果 DataFrame，必须包含 'symbol' 和 'breakout_date' 列
            breakouts: 可选的 Breakout 对象字典，key 为 symbol

        Returns:
            成功添加的条目数量
        """
        added_count = 0
        today = self.time_provider.get_current_date()

        for _, row in results_df.iterrows():
            symbol = row['symbol']

            # 优先使用传入的 Breakout 对象
            if breakouts and symbol in breakouts:
                bo = breakouts[symbol]
                entry = PoolEntry.from_breakout(bo)
            else:
                entry = self._create_entry_from_row(row)

            # 质量评分过滤
            if entry.quality_score < self.min_quality_threshold:
                continue

            # 获取突破日期
            bo_date = row.get('breakout_date', row.get('bo_date'))
            if isinstance(bo_date, str):
                bo_date = date.fromisoformat(bo_date)
            elif isinstance(bo_date, pd.Timestamp):
                bo_date = bo_date.date()

            # 分配到对应池
            if bo_date == today:
                success = self.realtime_pool.add(entry)
            else:
                entry.pool_type = 'daily'
                success = self.daily_pool.add(entry)

            if success:
                added_count += 1
                self._emit_event(PoolEvent(
                    event_type=PoolEventType.ENTRY_ADDED,
                    entry=entry,
                    timestamp=datetime.now()
                ))

        print(f"[PoolManager] Added {added_count}/{len(results_df)} entries from search results")
        return added_count

    def re_add_after_trade(self, symbol: str, entry_info: Dict) -> bool:
        """
        循环跟踪：交易后重新加入日K池

        当一只股票完成交易（止盈/止损）后，可以重新加入日K池
        继续跟踪，retry_count 会增加。

        Args:
            symbol: 股票代码
            entry_info: 条目信息字典，包含 breakout_date 等字段

        Returns:
            是否添加成功
        """
        bo_date = entry_info.get('breakout_date')
        if isinstance(bo_date, str):
            bo_date = date.fromisoformat(bo_date)

        entry = PoolEntry(
            symbol=symbol,
            add_date=self.time_provider.get_current_date(),
            breakout_date=bo_date,
            quality_score=entry_info.get('quality_score', 0),
            breakout_price=entry_info.get('breakout_price', 0),
            highest_peak_price=entry_info.get('highest_peak_price', 0),
            num_peaks_broken=entry_info.get('num_peaks_broken', 1),
            pool_type='daily',
            retry_count=entry_info.get('retry_count', 0) + 1
        )

        success = self.daily_pool.add(entry)

        if success:
            print(f"[PoolManager] Re-added {symbol} to daily pool "
                  f"(retry_count={entry.retry_count})")
            self._emit_event(PoolEvent(
                event_type=PoolEventType.ENTRY_ADDED,
                entry=entry,
                timestamp=datetime.now(),
                metadata={'retry': True}
            ))

        return success

    # ===== 时间推进（回测用）=====

    def advance_day(self) -> Dict:
        """
        推进一天（回测专用）

        执行：
        1. 实时池超时检查 → 转入日K池
        2. 日K池过期检查
        3. 时间推进

        Returns:
            推进结果统计
        """
        result = {
            'transferred': 0,
            'expired': 0,
            'date_before': self.time_provider.get_current_date()
        }

        # 1. 实时池超时检查
        timeout_entries = self.realtime_pool.check_timeout()
        for entry in timeout_entries:
            # 从实时池移除
            self.realtime_pool.remove(entry.symbol)

            # 转入日K池
            entry.status = 'active'
            entry.pool_type = 'daily'
            entry.add_date = self.time_provider.get_current_date()
            self.daily_pool.add(entry)

            result['transferred'] += 1

            self._emit_event(PoolEvent(
                event_type=PoolEventType.POOL_TRANSFER,
                entry=entry,
                timestamp=datetime.now(),
                metadata={'from': 'realtime', 'to': 'daily'}
            ))

        # 2. 日K池过期检查
        expired_entries = self.daily_pool.check_timeout()
        for entry in expired_entries:
            result['expired'] += 1
            self._emit_event(PoolEvent(
                event_type=PoolEventType.ENTRY_EXPIRED,
                entry=entry,
                timestamp=datetime.now()
            ))

        # 3. 时间推进
        self.time_provider.advance(1)
        result['date_after'] = self.time_provider.get_current_date()

        return result

    # ===== 买入信号检测（回测用）=====

    def check_buy_signals(self,
                          price_data: Dict[str, pd.Series]) -> List[BuySignal]:
        """
        检查买入信号

        遍历所有活跃条目，评估是否满足买入条件。

        Args:
            price_data: 价格数据字典，key 为 symbol，value 为包含 'close', 'high', 'low' 的 Series

        Returns:
            产生的买入信号列表
        """
        signals = []
        current_date = self.time_provider.get_current_date()

        for entry in self.get_all_active():
            if entry.symbol not in price_data:
                continue

            bar = price_data[entry.symbol]
            signal = self._evaluate_buy_condition(entry, bar, current_date)

            if signal:
                signals.append(signal)
                self._emit_event(PoolEvent(
                    event_type=PoolEventType.BUY_SIGNAL,
                    entry=entry,
                    timestamp=datetime.now(),
                    metadata={'signal': signal}
                ))

        return signals

    def _evaluate_buy_condition(self,
                                entry: PoolEntry,
                                bar: pd.Series,
                                current_date: date,
                                context: Optional[Dict] = None) -> Optional[BuySignal]:
        """
        评估买入条件

        使用多维度评估器（时间窗口、价格确认、成交量验证、风险过滤）
        计算综合评分并决定是否生成买入信号。

        Args:
            entry: 池条目
            bar: 当日价格数据 (包含 open, high, low, close, volume)
            current_date: 当前日期
            context: 额外上下文（如分时数据、成交量基准等）

        Returns:
            买入信号，不满足条件时返回 None
        """
        context = context or {}

        # 准备评估上下文
        eval_context = self._prepare_evaluation_context(entry, bar, context)

        # 执行多维度评估
        result = self.buy_evaluator.evaluate(
            entry=entry,
            current_bar=bar,
            time_provider=self.time_provider,
            context=eval_context
        )

        # 更新 entry 评估状态
        current_price = bar.get('close', 0) if bar is not None else 0
        if current_price > 0:
            entry.update_evaluation(result.total_score, current_price)

        # 处理评估结果
        if result.action == EvaluationAction.REMOVE:
            # 触发移出
            self._handle_remove(entry, result.reason)
            return None

        if result.action == EvaluationAction.TRANSFER:
            # 触发转移到日K池
            self._handle_transfer_to_daily(entry, result.reason)
            return None

        # 生成买入信号
        if result.is_buy_signal:
            return BuySignal(
                symbol=entry.symbol,
                signal_date=current_date,
                signal_price=result.suggested_entry_price or current_price,
                signal_strength=result.signal_strength,
                entry=entry,
                reason=result.reason,
                suggested_entry_price=result.suggested_entry_price or current_price,
                suggested_stop_loss=result.suggested_stop_loss,
                suggested_position_size_pct=result.suggested_position_pct,
                metadata={
                    'evaluation_result': result.to_dict(),
                    'total_score': result.total_score,
                    'action': result.action.value,
                }
            )

        return None

    def _prepare_evaluation_context(
        self,
        entry: PoolEntry,
        bar: pd.Series,
        extra_context: Dict
    ) -> Dict:
        """
        准备评估上下文

        Args:
            entry: 池条目
            bar: 当前K线数据
            extra_context: 额外上下文

        Returns:
            完整的评估上下文
        """
        context = dict(extra_context)

        # 添加基准成交量
        if entry.baseline_volume > 0:
            context.setdefault('volume_ma20', entry.baseline_volume)
            context.setdefault('baseline_volume', entry.baseline_volume)

        # 添加前收盘价
        if 'prev_close' not in context:
            context['prev_close'] = entry.highest_peak_price or entry.breakout_price

        return context

    def _handle_remove(self, entry: PoolEntry, reason: str) -> None:
        """
        处理移出动作

        Args:
            entry: 池条目
            reason: 移出原因
        """
        entry.mark_failed(reason)
        self.remove_entry(entry.symbol)

        self._emit_event(PoolEvent(
            event_type=PoolEventType.ENTRY_REMOVED,
            entry=entry,
            timestamp=datetime.now(),
            metadata={'reason': reason, 'action': 'remove_by_evaluation'}
        ))

    def _handle_transfer_to_daily(self, entry: PoolEntry, reason: str) -> None:
        """
        处理转移到日K池的动作

        Args:
            entry: 池条目
            reason: 转移原因
        """
        if entry.pool_type != 'realtime':
            return

        # 从实时池移除
        self.realtime_pool.remove(entry.symbol)

        # 更新状态并加入日K池
        entry.pool_type = 'daily'
        entry.status = 'active'
        self.daily_pool.add(entry)

        self._emit_event(PoolEvent(
            event_type=PoolEventType.POOL_TRANSFER,
            entry=entry,
            timestamp=datetime.now(),
            metadata={'reason': reason, 'from': 'realtime', 'to': 'daily'}
        ))

    # ===== 条目操作 =====

    def mark_bought(self, symbol: str) -> bool:
        """
        标记条目为已买入

        Args:
            symbol: 股票代码

        Returns:
            是否成功
        """
        entry = self.get_entry(symbol)
        if entry is None:
            return False

        pool = self.realtime_pool if entry.pool_type == 'realtime' else self.daily_pool
        return pool.update_status(symbol, 'bought')

    def remove_entry(self, symbol: str) -> Optional[PoolEntry]:
        """
        移除条目

        Args:
            symbol: 股票代码

        Returns:
            被移除的条目
        """
        entry = self.realtime_pool.remove(symbol)
        if entry is None:
            entry = self.daily_pool.remove(symbol)

        if entry:
            self._emit_event(PoolEvent(
                event_type=PoolEventType.ENTRY_REMOVED,
                entry=entry,
                timestamp=datetime.now()
            ))

        return entry

    # ===== 查询接口 =====

    def get_entry(self, symbol: str) -> Optional[PoolEntry]:
        """获取单个条目"""
        entry = self.realtime_pool.get(symbol)
        if entry is None:
            entry = self.daily_pool.get(symbol)
        return entry

    def get_all_active(self) -> List[PoolEntry]:
        """获取所有活跃条目"""
        return self.realtime_pool.get_all('active') + self.daily_pool.get_all('active')

    def get_all_active_symbols(self) -> List[str]:
        """获取所有活跃股票代码"""
        return [e.symbol for e in self.get_all_active()]

    def is_in_pool(self, symbol: str) -> bool:
        """检查股票是否在观察池中"""
        return (self.realtime_pool.contains(symbol) or
                self.daily_pool.contains(symbol))

    def get_pool_type(self, symbol: str) -> Optional[str]:
        """获取股票所在的池类型"""
        if self.realtime_pool.contains(symbol):
            return 'realtime'
        if self.daily_pool.contains(symbol):
            return 'daily'
        return None

    def get_statistics(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        realtime_stats = self.realtime_pool.get_statistics()
        daily_stats = self.daily_pool.get_statistics()

        all_active = self.get_all_active()
        avg_quality = 0.0
        if all_active:
            avg_quality = sum(e.quality_score for e in all_active) / len(all_active)

        return {
            'current_date': self.time_provider.get_current_date().isoformat(),
            'is_backtest': self.time_provider.is_backtest_mode(),
            'realtime_pool': realtime_stats,
            'daily_pool': daily_stats,
            'total_active': len(all_active),
            'avg_quality_score': avg_quality,
            'config': {
                'min_quality_threshold': self.min_quality_threshold,
                'buy_confirm_threshold': self.buy_confirm_threshold
            }
        }

    # ===== 事件系统 =====

    def add_event_listener(self, listener: Callable[[PoolEvent], None]) -> None:
        """
        注册事件监听器

        Args:
            listener: 事件处理函数
        """
        self._event_listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[PoolEvent], None]) -> bool:
        """
        移除事件监听器

        Args:
            listener: 事件处理函数

        Returns:
            是否移除成功
        """
        if listener in self._event_listeners:
            self._event_listeners.remove(listener)
            return True
        return False

    def _emit_event(self, event: PoolEvent) -> None:
        """发射事件"""
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"[PoolManager] Event listener error: {e}")

    # ===== 辅助方法 =====

    def _create_entry_from_row(self, row: pd.Series) -> PoolEntry:
        """从 DataFrame 行创建 PoolEntry"""
        # 获取突破日期
        bo_date = row.get('breakout_date', row.get('bo_date'))
        if isinstance(bo_date, str):
            bo_date = date.fromisoformat(bo_date)
        elif isinstance(bo_date, pd.Timestamp):
            bo_date = bo_date.date()

        return PoolEntry(
            symbol=row['symbol'],
            add_date=self.time_provider.get_current_date(),
            breakout_date=bo_date,
            quality_score=row.get('breakout_quality_score',
                                  row.get('quality_score', 0)),
            breakout_price=row.get('breakout_price',
                                       row.get('bo_price', 0)),
            highest_peak_price=row.get('highest_peak_price',
                                       row.get('peak_price', 0)),
            num_peaks_broken=row.get('num_peaks_broken', 1)
        )

    def clear_all(self) -> Dict:
        """
        清空所有池

        Returns:
            清空结果
        """
        realtime_count = self.realtime_pool.clear()
        daily_count = self.daily_pool.clear()
        return {
            'realtime_cleared': realtime_count,
            'daily_cleared': daily_count
        }

    def __repr__(self) -> str:
        return (f"PoolManager(date={self.time_provider.get_current_date()}, "
                f"realtime={self.realtime_pool.active_count}, "
                f"daily={self.daily_pool.active_count})")
