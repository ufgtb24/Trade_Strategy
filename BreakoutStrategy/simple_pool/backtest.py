"""
Simple Pool 回测引擎

驱动历史数据回放，收集回测指标。
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from .models import BuySignal, SignalPerformance
from .config import SimplePoolConfig
from .manager import SimplePoolManager


def compute_signal_performance(
    signal: BuySignal,
    df: pd.DataFrame,
    tracking_days: int = 30
) -> Optional[SignalPerformance]:
    """
    计算信号后验表现

    逻辑与 shadow_pool/calculator.py 的 compute_shadow_result 相同，
    但入场点是 signal_date 次日开始跟踪。

    Args:
        signal: 买入信号
        df: 股票价格数据 DataFrame
        tracking_days: 跟踪天数

    Returns:
        SignalPerformance 或 None（数据不足时）
    """
    # 截取信号日之后的数据（T+1 开始跟踪）
    future_mask = df.index > pd.Timestamp(signal.signal_date)
    future_df = df[future_mask].head(tracking_days)

    if len(future_df) == 0:
        return None

    # 提取价格序列
    highs = future_df['high'].values
    lows = future_df['low'].values
    closes = future_df['close'].values

    entry_price = signal.entry_price
    actual_days = len(future_df)
    complete = actual_days >= tracking_days

    # MFE: 最大涨幅
    max_high = float(np.max(highs))
    mfe = (max_high - entry_price) / entry_price * 100

    # MFE day: 达到最高价的天数
    mfe_day = int(np.argmax(highs)) + 1

    # MAE: 最大回撤
    min_low = float(np.min(lows))
    mae = max(0.0, (entry_price - min_low) / entry_price * 100)

    # MAE before MFE: MFE 前的最大回撤
    if mfe_day > 0:
        lows_before = lows[:mfe_day]
        min_low_before = float(np.min(lows_before))
        mae_before_mfe = max(0.0, (entry_price - min_low_before) / entry_price * 100)
    else:
        mae_before_mfe = 0.0

    # Max drawdown: 最大回撤
    max_drawdown = 0.0
    running_max = entry_price
    for h, l in zip(highs, lows):
        running_max = max(running_max, h)
        dd = (running_max - l) / running_max * 100
        max_drawdown = max(max_drawdown, dd)

    # Final return: 终点收益率
    final_price = float(closes[-1])
    final_return = (final_price - entry_price) / entry_price * 100

    return SignalPerformance(
        symbol=signal.symbol,
        signal_date=signal.signal_date,
        entry_price=round(entry_price, 4),
        mfe=round(mfe, 2),
        mae=round(mae, 2),
        mfe_day=mfe_day,
        mae_before_mfe=round(mae_before_mfe, 2),
        final_return=round(final_return, 2),
        max_drawdown=round(max_drawdown, 2),
        tracking_days=actual_days,
        complete=complete,
        success_10=mfe >= 10.0,
        success_20=mfe >= 20.0,
    )


@dataclass
class BacktestResult:
    """回测结果"""
    signals: List[BuySignal]
    performances: List[SignalPerformance]  # 信号后验表现
    statistics: Dict[str, Any]
    daily_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    abandoned_entries: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        """生成回测摘要"""
        stats = self.statistics
        total = stats.get('total_entries', 0)
        signaled = stats.get('signaled_entries', 0)
        abandoned = stats.get('abandoned_count', 0)

        lines = [
            "=== Simple Pool Backtest Result ===",
            f"Total entries: {total}",
            f"  - Signaled (success): {signaled} ({signaled/total*100:.1f}%)" if total > 0 else "  - Signaled: 0",
            f"  - Abandoned (failed): {abandoned} ({abandoned/total*100:.1f}%)" if total > 0 else "  - Abandoned: 0",
            f"Avg days to signal: {stats.get('avg_days_to_signal', 0):.1f}",
        ]

        # MFE/MAE 统计（如果有）
        if 'mfe_mean' in stats:
            lines.extend([
                "",
                f"=== MFE/MAE Performance ({stats.get('tracking_days', 30)}-day tracking) ===",
                f"MFE:  mean={stats.get('mfe_mean', 0):.1f}%, "
                f"median={stats.get('mfe_median', 0):.1f}%, "
                f"std={stats.get('mfe_std', 0):.1f}%",
                f"MAE:  mean={stats.get('mae_mean', 0):.1f}%, "
                f"median={stats.get('mae_median', 0):.1f}%",
                f"MAE before MFE: mean={stats.get('mae_before_mfe_mean', 0):.1f}%, "
                f"median={stats.get('mae_before_mfe_median', 0):.1f}%",
                f"Max drawdown: mean={stats.get('max_drawdown_mean', 0):.1f}%",
                f"Final return: mean={stats.get('final_return_mean', 0):.1f}%",
                f"Success rate (>=10%): {stats.get('success_rate_10', 0):.1%}",
                f"Success rate (>=20%): {stats.get('success_rate_20', 0):.1%}",
            ])

        return "\n".join(lines)


class SimpleBacktestEngine:
    """
    Simple Pool 回测引擎

    核心职责:
    - 驱动历史数据回放
    - 管理回测时间线
    - 收集回测指标

    使用方式:
        engine = SimpleBacktestEngine(config)
        result = engine.run(breakouts, price_data, start_date, end_date)
        print(result.summary())
    """

    def __init__(self, config: Optional[SimplePoolConfig] = None):
        """
        初始化回测引擎

        Args:
            config: Simple Pool 配置，默认使用 SimplePoolConfig.default()
        """
        self.config = config or SimplePoolConfig.default()
        self.manager = SimplePoolManager(self.config)

    def run(self,
            breakouts: List[Any],
            price_data: Dict[str, pd.DataFrame],
            start_date: date,
            end_date: date,
            on_signal: Optional[Callable[[BuySignal], None]] = None,
            tracking_days: int = 30
    ) -> BacktestResult:
        """
        运行回测

        Args:
            breakouts: 突破列表（需要有 date, symbol, price, atr 等属性）
            price_data: symbol -> DataFrame 的映射
            start_date: 回测开始日期
            end_date: 回测结束日期
            on_signal: 信号回调（可选）
            tracking_days: 信号后验追踪天数（默认 30 天）

        Returns:
            BacktestResult
        """
        # 重置管理器
        self.manager.clear()

        all_signals: List[BuySignal] = []
        daily_snapshots: List[Dict[str, Any]] = []
        abandoned_entries: List[Dict[str, Any]] = []
        total_added = 0  # 追踪总共入池的条目数

        # 按日期排序突破
        sorted_breakouts = sorted(breakouts, key=lambda b: getattr(b, 'date', start_date))
        breakout_idx = 0

        # 记录入池前的条目数，用于检测放弃
        prev_entry_ids = set()

        # 按日期迭代
        current_date = start_date
        while current_date <= end_date:
            # 1. 添加当日及之前的新突破
            while (breakout_idx < len(sorted_breakouts) and
                   getattr(sorted_breakouts[breakout_idx], 'date', current_date) <= current_date):
                bo = sorted_breakouts[breakout_idx]
                entry = self.manager.add_entry_from_breakout(bo)
                # entry 为 None 表示 quality 不达标，跳过
                if entry is not None:
                    prev_entry_ids.add(entry.entry_id)
                    total_added += 1
                breakout_idx += 1

            # 2. 更新所有条目
            new_signals = self.manager.update_all(current_date, price_data)

            # 3. 检测被放弃的条目（排除生成信号后移除的）
            current_entry_ids = {e.entry_id for e in self.manager.get_all_entries()}
            signaled_ids = {s.metrics.get('entry_id') for s in new_signals}
            removed_ids = prev_entry_ids - current_entry_ids
            for entry_id in removed_ids:
                # 只有非信号移除才算 abandoned
                if entry_id not in signaled_ids:
                    abandoned_entries.append({
                        'entry_id': entry_id,
                        'date': current_date.isoformat(),
                    })
            prev_entry_ids = current_entry_ids.copy()

            # 4. 处理信号
            for signal in new_signals:
                all_signals.append(signal)
                if on_signal:
                    on_signal(signal)

            # 5. 记录快照
            stats = self.manager.get_statistics()
            daily_snapshots.append({
                'date': current_date.isoformat(),
                'active_entries': stats['active_entries'],
                'new_signals': len(new_signals),
            })

            # 下一天
            current_date += timedelta(days=1)

        # 计算所有信号的后验表现
        performances: List[SignalPerformance] = []
        for signal in all_signals:
            if signal.symbol in price_data:
                perf = compute_signal_performance(
                    signal,
                    price_data[signal.symbol],
                    tracking_days
                )
                if perf:
                    performances.append(perf)

        # 计算统计（包含 MFE/MAE）
        statistics = self._calculate_statistics(
            all_signals, abandoned_entries, performances, tracking_days, total_added
        )

        return BacktestResult(
            signals=all_signals,
            performances=performances,
            statistics=statistics,
            daily_snapshots=daily_snapshots,
            abandoned_entries=abandoned_entries
        )

    def _calculate_statistics(
        self,
        signals: List[BuySignal],
        abandoned: List[Dict[str, Any]],
        performances: List[SignalPerformance],
        tracking_days: int,
        total_entries: int
    ) -> Dict[str, Any]:
        """计算回测统计（包含 MFE/MAE）"""
        # 去重信号数（按 entry_id）
        unique_signaled = len({s.metrics.get('entry_id') for s in signals})

        stats = {
            'total_entries': total_entries,
            'signaled_entries': unique_signaled,  # 生成信号的条目数（成功）
            'abandoned_count': len(abandoned),    # 放弃的条目数（失败）
            'signal_rate': unique_signaled / total_entries if total_entries > 0 else 0.0,
            'total_signals': len(signals),        # 信号总数（可能有重复）
            'avg_days_to_signal': (
                sum(s.days_to_signal for s in signals) / len(signals)
                if signals else 0.0
            ),
            'tracking_days': tracking_days,
        }

        # MFE/MAE 统计（基于完整跟踪的信号）
        if performances:
            valid = [p for p in performances if p.complete]
            if valid:
                mfes = [p.mfe for p in valid]
                maes = [p.mae for p in valid]

                mae_before_mfes = [p.mae_before_mfe for p in valid]
                stats.update({
                    'mfe_mean': float(np.mean(mfes)),
                    'mfe_median': float(np.median(mfes)),
                    'mfe_std': float(np.std(mfes)),
                    'mae_mean': float(np.mean(maes)),
                    'mae_median': float(np.median(maes)),
                    'mae_before_mfe_mean': float(np.mean(mae_before_mfes)),
                    'mae_before_mfe_median': float(np.median(mae_before_mfes)),
                    'max_drawdown_mean': float(np.mean([p.max_drawdown for p in valid])),
                    'final_return_mean': float(np.mean([p.final_return for p in valid])),
                    'success_rate_10': sum(1 for p in valid if p.success_10) / len(valid),
                    'success_rate_20': sum(1 for p in valid if p.success_20) / len(valid),
                    'valid_performances': len(valid),
                    'total_performances': len(performances),
                })

        return stats

    def get_manager(self) -> SimplePoolManager:
        """获取底层管理器（用于高级操作）"""
        return self.manager
