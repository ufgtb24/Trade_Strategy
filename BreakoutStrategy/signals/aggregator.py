"""
信号聚合器

聚合多类型信号，统计排序。
"""

from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

from .composite import (
    calc_effective_weighted_sum,
    calculate_signal_strength,
    generate_sequence_label,
    is_turbulent,
)
from .models import AbsoluteSignal, SignalStats


class SignalAggregator:
    """
    信号聚合器

    按股票聚合信号，统计窗口内信号数量，按数量降序排序。

    参数：
        lookback_days: 信号统计回看天数（默认 42，约 2 个月）
    """

    def __init__(self, lookback_days: int = 42):
        self.lookback_days = lookback_days

    def aggregate(
        self,
        all_signals: List[AbsoluteSignal],
        scan_date: date,
        amplitude_by_symbol: Optional[Dict[str, float]] = None,
    ) -> List[SignalStats]:
        """
        按股票聚合信号，统计信号数量

        注意：信号的时间窗口过滤已在扫描阶段完成（使用交易日计算），
        此处直接按股票分组统计。

        Args:
            all_signals: 所有信号列表（已在扫描时按交易日过滤）
            scan_date: 扫描截止日期（保留参数以兼容接口）
            amplitude_by_symbol: 每只股票的 lookback 窗口价格振幅

        Returns:
            按 weighted_sum 降序排列的 SignalStats 列表
        """
        if not all_signals:
            return []

        if amplitude_by_symbol is None:
            amplitude_by_symbol = {}

        # 直接按股票分组（信号已在扫描时按交易日过滤）
        signals_by_symbol = defaultdict(list)
        for signal in all_signals:
            signals_by_symbol[signal.symbol].append(signal)

        # 构建 SignalStats 列表
        stats_list = []
        for symbol, signals in signals_by_symbol.items():
            if not signals:
                continue

            # 计算每个信号的强度
            for signal in signals:
                signal.strength = calculate_signal_strength(signal)

            # 按日期排序（降序，最新在前）
            signals_sorted = sorted(signals, key=lambda s: s.date, reverse=True)

            # 异常走势检测
            amplitude = amplitude_by_symbol.get(symbol, 0.0)
            turbulent = is_turbulent(amplitude)

            # turbulent 时仅 D 信号计入 weighted_sum
            weighted_sum = calc_effective_weighted_sum(signals, turbulent)

            stats = SignalStats(
                symbol=symbol,
                signal_count=len(signals),
                signals=signals_sorted,
                latest_signal_date=signals_sorted[0].date,
                latest_price=signals_sorted[0].price,
                weighted_sum=weighted_sum,
                sequence_label=generate_sequence_label(signals),
                amplitude=amplitude,
                turbulent=turbulent,
            )
            stats_list.append(stats)

        # 按 weighted_sum 降序排序，相同时按 signal_count 降序
        stats_list.sort(key=lambda s: (s.weighted_sum, s.signal_count), reverse=True)

        return stats_list
