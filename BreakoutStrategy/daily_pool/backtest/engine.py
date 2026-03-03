"""
Daily 池回测引擎

驱动历史数据回放，收集回测指标。
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from ..models import DailySignal, SignalStrength
from ..config import DailyPoolConfig
from ..manager import DailyPoolManager


@dataclass
class BacktestResult:
    """回测结果"""
    signals: List[DailySignal]
    statistics: Dict[str, Any]
    phase_transitions: List[Dict[str, Any]]
    daily_snapshots: List[Dict[str, Any]]

    def summary(self) -> str:
        """生成回测摘要"""
        lines = [
            "=== Daily Pool Backtest Result ===",
            f"Total entries: {self.statistics.get('total_entries', 0)}",
            f"Total signals: {self.statistics.get('total_signals', 0)}",
            f"Signal rate: {self.statistics.get('signal_rate', 0):.1%}",
            f"Avg days to signal: {self.statistics.get('avg_days_to_signal', 0):.1f}",
            "",
            "Signal strength distribution:",
        ]
        for strength, count in self.statistics.get('strength_distribution', {}).items():
            lines.append(f"  {strength}: {count}")

        lines.append("")
        lines.append("Top transition counts:")
        for key, count in sorted(
            self.statistics.get('transition_counts', {}).items(),
            key=lambda x: x[1], reverse=True
        )[:5]:
            lines.append(f"  {key}: {count}")

        return "\n".join(lines)


class DailyBacktestEngine:
    """
    Daily 池回测引擎

    核心职责:
    - 驱动历史数据回放
    - 管理回测时间线
    - 收集回测指标

    使用方式:
        engine = DailyBacktestEngine(config)
        result = engine.run(breakouts, price_data, start_date, end_date)
        print(result.summary())
    """

    def __init__(self, config: DailyPoolConfig):
        """
        初始化回测引擎

        Args:
            config: Daily 池配置
        """
        self.config = config
        self.manager = DailyPoolManager(config)

    def run(self,
            breakouts: List[Any],
            price_data: Dict[str, pd.DataFrame],
            start_date: date,
            end_date: date,
            on_signal: Optional[Callable[[DailySignal], None]] = None
    ) -> BacktestResult:
        """
        运行回测

        Args:
            breakouts: 突破列表（需要有 date, symbol, price, atr 等属性）
            price_data: symbol -> DataFrame 的映射
            start_date: 回测开始日期
            end_date: 回测结束日期
            on_signal: 信号回调（可选）

        Returns:
            BacktestResult
        """
        # 重置管理器
        self.manager.clear()

        all_signals: List[DailySignal] = []
        phase_transitions: List[Dict[str, Any]] = []
        daily_snapshots: List[Dict[str, Any]] = []

        # 按日期排序突破
        sorted_breakouts = sorted(breakouts, key=lambda b: getattr(b, 'date', start_date))
        breakout_idx = 0

        # 按日期迭代
        current_date = start_date
        while current_date <= end_date:
            # 1. 添加当日及之前的新突破
            while (breakout_idx < len(sorted_breakouts) and
                   getattr(sorted_breakouts[breakout_idx], 'date', current_date) <= current_date):
                bo = sorted_breakouts[breakout_idx]
                self.manager.add_entry_from_breakout(bo, getattr(bo, 'date', current_date))
                breakout_idx += 1

            # 2. 更新所有条目
            new_signals = self.manager.update_all(current_date, price_data)

            # 3. 处理信号
            for signal in new_signals:
                all_signals.append(signal)
                if on_signal:
                    on_signal(signal)

            # 4. 记录快照
            stats = self.manager.get_statistics()
            daily_snapshots.append({
                'date': current_date.isoformat(),
                'active_entries': stats['active_entries'],
                'new_signals': len(new_signals),
                'phase_distribution': stats['phase_distribution'].copy()
            })

            # 下一天（跳过周末）
            current_date += timedelta(days=1)

        # 收集阶段转换历史
        for entry in self.manager.get_all_entries():
            for t in entry.phase_history.transitions:
                phase_transitions.append({
                    'symbol': entry.symbol,
                    'entry_id': entry.entry_id,
                    'date': t.transition_date.isoformat(),
                    'from_phase': t.from_phase.name,
                    'to_phase': t.to_phase.name,
                    'reason': t.reason
                })

        # 计算统计
        statistics = self._calculate_statistics(all_signals, phase_transitions)

        return BacktestResult(
            signals=all_signals,
            statistics=statistics,
            phase_transitions=phase_transitions,
            daily_snapshots=daily_snapshots
        )

    def _calculate_statistics(self, signals: List[DailySignal],
                              transitions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算回测统计"""
        total_entries = len(self.manager.get_all_entries())

        # 信号强度分布
        strength_distribution = {
            'strong': 0,
            'normal': 0,
            'weak': 0
        }
        for s in signals:
            strength_distribution[s.strength.value] = strength_distribution.get(s.strength.value, 0) + 1

        # 转换计数
        transition_counts: Dict[str, int] = {}
        for t in transitions:
            key = f"{t['from_phase']}->{t['to_phase']}"
            transition_counts[key] = transition_counts.get(key, 0) + 1

        return {
            'total_entries': total_entries,
            'total_signals': len(signals),
            'signal_rate': len(signals) / total_entries if total_entries > 0 else 0.0,
            'avg_days_to_signal': (
                sum(s.days_to_signal for s in signals) / len(signals)
                if signals else 0.0
            ),
            'strength_distribution': strength_distribution,
            'transition_counts': transition_counts,
        }

    def get_manager(self) -> DailyPoolManager:
        """获取底层管理器（用于高级操作）"""
        return self.manager
