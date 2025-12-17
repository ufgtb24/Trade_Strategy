"""
Simple Pool 管理器

管理池条目的生命周期：添加、更新、移除。
"""
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from .config import SimplePoolConfig
from .models import PoolEntry, BuySignal
from .evaluator import SimpleEvaluator


class SimplePoolManager:
    """
    Simple Pool 管理器

    核心职责:
    - 管理条目生命周期 (添加、更新、移除)
    - 协调每日评估
    - 收集和分发信号
    - 提供统计信息

    使用方式:
        manager = SimplePoolManager(config)
        entry = manager.add_entry(...)
        signals = manager.update_all(as_of_date, price_data)
    """

    def __init__(self, config: Optional[SimplePoolConfig] = None):
        """
        初始化管理器

        Args:
            config: Simple Pool 配置，默认使用 SimplePoolConfig.default()
        """
        self.config = config or SimplePoolConfig.default()
        self.evaluator = SimpleEvaluator(self.config)
        self._entries: Dict[str, PoolEntry] = {}  # entry_id -> entry
        self._signals: List[BuySignal] = []

    def add_entry(self, symbol: str, breakout_date: date, breakout_price: float,
                  peak_price: float, initial_atr: float,
                  quality_score: float = 0.0,
                  pattern_label: str = "basic") -> Optional[PoolEntry]:
        """
        添加新条目到池中

        Args:
            symbol: 股票代码
            breakout_date: 突破日期
            breakout_price: 突破价格
            peak_price: 突破的峰值价格
            initial_atr: 突破时的 ATR
            quality_score: 突破质量评分 (0-100)

        Returns:
            新创建的 PoolEntry，如果 quality 不达标则返回 None
        """
        # 入池前检查: quality 不达标直接拒绝
        if quality_score < self.config.min_quality_score:
            return None

        entry_id = f"{symbol}_{breakout_date.isoformat()}"

        entry = PoolEntry(
            symbol=symbol,
            entry_id=entry_id,
            breakout_date=breakout_date,
            breakout_price=breakout_price,
            peak_price=peak_price,
            initial_atr=initial_atr,
            quality_score=quality_score,
            pattern_label=pattern_label,
            post_high=peak_price,
            post_low=breakout_price,
            current_price=breakout_price
        )

        self._entries[entry_id] = entry
        return entry

    def add_entry_from_breakout(self, breakout: Any) -> Optional[PoolEntry]:
        """
        从 Breakout 对象添加条目

        Args:
            breakout: Breakout 对象 (需有 symbol, date, price, atr_value, quality_score 等属性)

        Returns:
            新创建的 PoolEntry，如果 quality 不达标则返回 None
        """
        # 获取峰值价格
        peak_price = breakout.price
        if hasattr(breakout, 'broken_peaks') and breakout.broken_peaks:
            peak_price = max(p.price for p in breakout.broken_peaks)

        return self.add_entry(
            symbol=breakout.symbol,
            breakout_date=getattr(breakout, 'date', date.today()),
            breakout_price=breakout.price,
            peak_price=peak_price,
            initial_atr=getattr(breakout, 'atr_value', 1.0),
            quality_score=getattr(breakout, 'quality_score', 0.0),
            pattern_label=getattr(breakout, 'pattern_label', 'basic')
        )

    def update_all(self, as_of_date: date,
                   price_data: Dict[str, pd.DataFrame]) -> List[BuySignal]:
        """
        更新所有活跃条目 (每日收盘后调用)

        Args:
            as_of_date: 当前日期
            price_data: symbol -> DataFrame 的映射

        Returns:
            新生成的信号列表
        """
        new_signals = []
        entries_to_remove = []

        for entry in self.get_active_entries():
            if entry.symbol not in price_data:
                continue

            df = price_data[entry.symbol]

            # 截止到 as_of_date
            if hasattr(df.index, 'date'):
                df_until = df[df.index.date <= as_of_date]
            else:
                df_until = df[df.index <= pd.Timestamp(as_of_date)]

            if len(df_until) == 0:
                continue

            # 评估
            evaluation = self.evaluator.evaluate(entry, df_until, as_of_date)

            # 处理放弃
            if evaluation.should_abandon:
                entries_to_remove.append(entry.entry_id)

            # 收集信号
            if evaluation.signal:
                new_signals.append(evaluation.signal)
                self._signals.append(evaluation.signal)
                # 生成信号后，条目任务完成，从池中移除
                entries_to_remove.append(entry.entry_id)

        # 移除已放弃的条目
        for entry_id in entries_to_remove:
            self.remove_entry(entry_id)

        return new_signals

    def get_active_entries(self) -> List[PoolEntry]:
        """获取所有活跃条目"""
        return [e for e in self._entries.values() if e.is_active]

    def get_entry(self, entry_id: str) -> Optional[PoolEntry]:
        """根据 ID 获取条目"""
        return self._entries.get(entry_id)

    def get_entries_by_symbol(self, symbol: str) -> List[PoolEntry]:
        """获取某股票的所有条目"""
        return [e for e in self._entries.values() if e.symbol == symbol]

    def get_all_entries(self) -> List[PoolEntry]:
        """获取所有条目 (包括非活跃)"""
        return list(self._entries.values())

    def get_all_signals(self) -> List[BuySignal]:
        """获取所有历史信号"""
        return self._signals.copy()

    def get_statistics(self) -> Dict[str, Any]:
        """获取池统计信息"""
        all_entries = list(self._entries.values())
        active = [e for e in all_entries if e.is_active]
        signaled = [e for e in all_entries if e.signal_generated]

        total = len(all_entries)

        return {
            'total_entries': total,
            'active_entries': len(active),
            'signaled_entries': len(signaled),
            'abandoned_entries': total - len(active) - len(signaled),
            'total_signals': len(self._signals),
            'signal_rate': len(self._signals) / total if total > 0 else 0.0
        }

    def remove_entry(self, entry_id: str) -> Optional[PoolEntry]:
        """移除条目"""
        return self._entries.pop(entry_id, None)

    def clear(self) -> None:
        """清空池"""
        self._entries.clear()
        self._signals.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (f"SimplePoolManager(entries={stats['total_entries']}, "
                f"active={stats['active_entries']}, signals={stats['total_signals']})")
