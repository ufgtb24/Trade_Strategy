"""
Daily 池管理器

管理条目生命周期、协调评估、收集信号。
"""
from datetime import date
from typing import Any, Dict, Iterator, List, Optional, TYPE_CHECKING

import pandas as pd

from ..models import Phase, DailyPoolEntry, DailySignal, PhaseHistory
from ..config import DailyPoolConfig
from ..state_machine import PhaseStateMachine
from ..evaluator import DailyPoolEvaluator

if TYPE_CHECKING:
    pass


class DailyPoolManager:
    """
    Daily 池管理器

    核心职责:
    - 管理条目生命周期（添加、更新、移除）
    - 协调每日评估
    - 收集和分发信号
    - 提供统计信息

    使用方式:
        manager = DailyPoolManager(config)
        entry = manager.add_entry(breakout_info, as_of_date)
        signals = manager.update_all(as_of_date, price_data)
    """

    def __init__(self, config: DailyPoolConfig):
        """
        初始化管理器

        Args:
            config: Daily 池配置
        """
        self.config = config
        self.evaluator = DailyPoolEvaluator(config)
        self._entries: Dict[str, DailyPoolEntry] = {}  # entry_id -> entry
        self._signals: List[DailySignal] = []

    def add_entry(self, symbol: str, breakout_date: date, breakout_price: float,
                  highest_peak_price: float, initial_atr: float,
                  quality_score: float = 0.0) -> DailyPoolEntry:
        """
        添加新条目到池中

        Args:
            symbol: 股票代码
            breakout_date: 突破日期
            breakout_price: 突破价格
            highest_peak_price: 突破的最高峰值价格
            initial_atr: 突破时的ATR
            quality_score: 突破质量评分 (0-100)

        Returns:
            新创建的 DailyPoolEntry
        """
        entry_id = f"{symbol}_{breakout_date.isoformat()}"

        # 创建状态机
        phase_machine = PhaseStateMachine(
            config=self.config.phase,
            entry_date=breakout_date
        )

        entry = DailyPoolEntry(
            symbol=symbol,
            entry_id=entry_id,
            breakout_date=breakout_date,
            breakout_price=breakout_price,
            highest_peak_price=highest_peak_price,
            initial_atr=initial_atr,
            quality_score=quality_score,
            phase_machine=phase_machine,
            phase_history=PhaseHistory(),
            post_breakout_high=highest_peak_price,
            post_breakout_low=breakout_price,
            current_price=breakout_price
        )

        self._entries[entry_id] = entry
        return entry

    def add_entry_from_breakout(self, breakout: Any, as_of_date: date) -> DailyPoolEntry:
        """
        从 Breakout 对象添加条目

        Args:
            breakout: Breakout 对象（需要有 symbol, date, price, atr, quality_score 等属性）
            as_of_date: 入池日期

        Returns:
            新创建的 DailyPoolEntry
        """
        # 获取最高峰值价格
        highest_peak_price = breakout.price
        if hasattr(breakout, 'broken_peaks') and breakout.broken_peaks:
            highest_peak_price = max(p.price for p in breakout.broken_peaks)

        return self.add_entry(
            symbol=breakout.symbol,
            breakout_date=breakout.date if hasattr(breakout, 'date') else as_of_date,
            breakout_price=breakout.price,
            highest_peak_price=highest_peak_price,
            initial_atr=getattr(breakout, 'atr_value', 1.0),
            quality_score=getattr(breakout, 'quality_score', 0.0)
        )

    def update_all(self, as_of_date: date,
                   price_data: Dict[str, pd.DataFrame]) -> List[DailySignal]:
        """
        更新所有活跃条目（每日收盘后调用）

        Args:
            as_of_date: 当前日期
            price_data: symbol -> DataFrame 的映射

        Returns:
            新生成的信号列表
        """
        new_signals = []

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

            # 收集信号
            if evaluation.signal:
                new_signals.append(evaluation.signal)
                self._signals.append(evaluation.signal)

        return new_signals

    def get_active_entries(self) -> List[DailyPoolEntry]:
        """获取所有活跃条目"""
        return [e for e in self._entries.values() if e.is_active]

    def get_entry(self, entry_id: str) -> Optional[DailyPoolEntry]:
        """根据 ID 获取条目"""
        return self._entries.get(entry_id)

    def get_entries_by_symbol(self, symbol: str) -> List[DailyPoolEntry]:
        """获取某股票的所有条目"""
        return [e for e in self._entries.values() if e.symbol == symbol]

    def get_entries_by_phase(self, phase: Phase) -> List[DailyPoolEntry]:
        """获取某阶段的所有条目"""
        return [e for e in self._entries.values() if e.current_phase == phase]

    def get_all_entries(self) -> List[DailyPoolEntry]:
        """获取所有条目（包括非活跃）"""
        return list(self._entries.values())

    def get_all_signals(self) -> List[DailySignal]:
        """获取所有历史信号"""
        return self._signals.copy()

    def get_statistics(self) -> Dict[str, Any]:
        """获取池统计信息"""
        active = self.get_active_entries()

        phase_counts: Dict[str, int] = {}
        for entry in active:
            phase = entry.current_phase.name
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

        total_entries = len(self._entries)

        return {
            'total_entries': total_entries,
            'active_entries': len(active),
            'phase_distribution': phase_counts,
            'total_signals': len(self._signals),
            'signal_rate': len(self._signals) / total_entries if total_entries > 0 else 0.0
        }

    def iter_entries_by_phase(self, phase: Phase) -> Iterator[DailyPoolEntry]:
        """按阶段迭代条目"""
        for entry in self._entries.values():
            if entry.current_phase == phase:
                yield entry

    def remove_entry(self, entry_id: str) -> Optional[DailyPoolEntry]:
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
        return (f"DailyPoolManager(entries={stats['total_entries']}, "
                f"active={stats['active_entries']}, signals={stats['total_signals']})")
