"""
Simple Pool 评估器

MVP 版本的核心逻辑：即时判断，无状态机。

买入条件 (全部满足):
1. 稳住: pullback <= max_pullback_atr AND price > recent_support
2. 上涨: 阳线 AND 放量 AND (涨 OR > MA5)

注: quality 检查已移至入池阶段 (manager.add_entry)

放弃条件 (任一):
1. 观察期满: days > max_observation_days
2. 回调过深: pullback > max_pullback_atr * abandon_buffer
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Any, Optional

import pandas as pd

from .config import SimplePoolConfig
from .models import PoolEntry, BuySignal
from . import utils


@dataclass
class Evaluation:
    """
    评估结果

    包含信号/放弃决策及诊断信息。
    """
    should_signal: bool          # 是否触发买入信号
    should_abandon: bool         # 是否放弃观察
    abandon_reason: Optional[str] = None  # 放弃原因
    signal: Optional[BuySignal] = None    # 买入信号

    # === 两条件检查结果 (用于诊断) ===
    # 注: quality 检查已移至入池阶段
    stable_ok: bool = False      # 条件1: 稳住
    rising_ok: bool = False      # 条件2: 上涨

    # === 详细指标 (用于调试和可视化) ===
    metrics: Dict[str, Any] = field(default_factory=dict)


class SimpleEvaluator:
    """
    Simple Pool 评估器

    核心特点:
    - 即时判断: 每次评估独立，不依赖历史状态
    - 两条件并行: 稳定性 + 上涨趋势 (quality 已在入池时检查)
    - 简化支撑: 用近 N 天最低价作为支撑位
    """

    def __init__(self, config: SimplePoolConfig):
        """
        初始化评估器

        Args:
            config: Simple Pool 配置
        """
        self.config = config

    def evaluate(self, entry: PoolEntry, df: pd.DataFrame,
                 as_of_date: date) -> Evaluation:
        """
        评估条目

        Args:
            entry: 池条目
            df: 截止到 as_of_date 的 OHLCV DataFrame
            as_of_date: 评估日期

        Returns:
            Evaluation 评估结果
        """
        if len(df) < 2:
            return self._empty_evaluation()

        # 更新价格追踪
        latest = df.iloc[-1]
        entry.update_price_tracking(
            high=float(latest['high']),
            low=float(latest['low']),
            close=float(latest['close'])
        )

        # 计算所有指标
        metrics = self._calculate_metrics(entry, df, as_of_date)

        # === 放弃条件检查 ===
        abandon_result = self._check_abandon(entry, metrics, as_of_date)
        if abandon_result is not None:
            return abandon_result

        # === 信号条件检查 (quality 已在入池时检查) ===
        # 如果已生成过信号，不再重复生成
        if entry.signal_generated:
            return Evaluation(
                should_signal=False,
                should_abandon=False,
                abandon_reason=None,
                signal=None,
                stable_ok=True,  # 已触发过，条件曾满足
                rising_ok=True,
                metrics=metrics
            )

        stable_ok = self._check_stability(entry, metrics)
        rising_ok = self._check_rising(metrics)

        should_signal = stable_ok and rising_ok

        signal = None
        if should_signal:
            signal = self._generate_signal(entry, metrics, as_of_date)
            entry.mark_signaled()

        return Evaluation(
            should_signal=should_signal,
            should_abandon=False,
            abandon_reason=None,
            signal=signal,
            stable_ok=stable_ok,
            rising_ok=rising_ok,
            metrics=metrics
        )

    def _calculate_metrics(self, entry: PoolEntry, df: pd.DataFrame,
                           as_of_date: date) -> Dict[str, Any]:
        """计算所有评估指标"""
        latest = df.iloc[-1]
        current_price = float(latest['close'])
        current_open = float(latest['open'])
        current_volume = float(latest['volume'])

        # 回调深度 (从入池后高点)
        pullback_atr = entry.pullback_from_high_atr

        # 支撑位 (近 N 天最低价)
        recent_support = utils.get_recent_support(df, self.config.support_lookback)

        # 成交量比率
        volume_ratio = utils.calculate_volume_ratio(df, self.config.volume_ma_period)

        # 价格均线
        price_ma = utils.calculate_price_ma(df, self.config.price_ma_period)

        # 阳线判断
        is_bullish = current_price > current_open

        # 价格变化
        price_change = utils.get_price_change(df)

        # 是否突破 MA
        above_ma = current_price > price_ma

        # 入池天数
        days_in_pool = entry.days_in_pool(as_of_date)

        return {
            'current_price': current_price,
            'current_open': current_open,
            'current_volume': current_volume,
            'pullback_atr': pullback_atr,
            'recent_support': recent_support,
            'volume_ratio': volume_ratio,
            'price_ma': price_ma,
            'is_bullish': is_bullish,
            'price_change': price_change,
            'above_ma': above_ma,
            'days_in_pool': days_in_pool,
            'quality_score': entry.quality_score,
            'post_high': entry.post_high,
        }

    def _check_abandon(self, entry: PoolEntry, metrics: Dict[str, Any],
                       as_of_date: date) -> Optional[Evaluation]:
        """
        检查放弃条件

        Returns:
            如果应该放弃，返回 Evaluation；否则返回 None
        """
        days = metrics['days_in_pool']
        pullback_atr = metrics['pullback_atr']

        # 条件1: 观察期满
        if days > self.config.max_observation_days:
            entry.mark_abandoned()
            return Evaluation(
                should_signal=False,
                should_abandon=True,
                abandon_reason=f"Observation expired: {days} days > {self.config.max_observation_days}",
                stable_ok=False,
                rising_ok=False,
                metrics=metrics
            )

        # 条件2: 回调过深
        if pullback_atr > self.config.abandon_threshold:
            entry.mark_abandoned()
            return Evaluation(
                should_signal=False,
                should_abandon=True,
                abandon_reason=f"Pullback too deep: {pullback_atr:.2f} ATR > {self.config.abandon_threshold:.2f}",
                stable_ok=False,
                rising_ok=False,
                metrics=metrics
            )

        return None

    def _check_stability(self, entry: PoolEntry, metrics: Dict[str, Any]) -> bool:
        """
        检查条件1: 稳住

        市场机制: 获利盘卖出 vs 新资金接盘 = 供需再平衡

        子条件:
        - 回调可控: pullback <= max_pullback_atr
        - 未破支撑: price > recent_support
        """
        pullback_ok = metrics['pullback_atr'] <= self.config.max_pullback_atr
        above_support = metrics['current_price'] > metrics['recent_support']

        return pullback_ok and above_support

    def _check_rising(self, metrics: Dict[str, Any]) -> bool:
        """
        检查条件2: 上涨

        市场机制: 新资金确认突破有效，再次供需失衡

        子条件:
        - 阳线: close > open
        - 放量: volume >= threshold * MA
        - 价格涨: close > yesterday_close OR close > MA5
        """
        is_bullish = metrics['is_bullish']
        volume_ok = metrics['volume_ratio'] >= self.config.volume_threshold
        price_up = metrics['price_change'] > 0 or metrics['above_ma']

        return is_bullish and volume_ok and price_up

    def _generate_signal(self, entry: PoolEntry, metrics: Dict[str, Any],
                         as_of_date: date) -> BuySignal:
        """生成买入信号"""
        # 止损价: 近期支撑下方 0.5 ATR
        stop_loss = metrics['recent_support'] - 0.5 * entry.initial_atr

        return BuySignal(
            symbol=entry.symbol,
            signal_date=as_of_date,
            entry_price=metrics['current_price'],
            stop_loss=stop_loss,
            days_to_signal=metrics['days_in_pool'],
            metrics={
                'entry_id': entry.entry_id,  # 用于追踪
                'pullback_atr': metrics['pullback_atr'],
                'volume_ratio': metrics['volume_ratio'],
                'recent_support': metrics['recent_support'],
                'quality_score': entry.quality_score,
                'price_ma': metrics['price_ma'],
            }
        )

    def _empty_evaluation(self) -> Evaluation:
        """返回空评估结果 (数据不足时)"""
        return Evaluation(
            should_signal=False,
            should_abandon=False,
            abandon_reason=None,
            signal=None,
            stable_ok=False,
            rising_ok=False,
            metrics={}
        )
