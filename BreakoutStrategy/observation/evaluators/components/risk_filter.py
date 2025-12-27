"""
风险过滤评估器

检查各类风险条件，作为门槛条件（不参与加权计算）：
- 跌破阈值：跌破突破价 3% 触发移出
- 跳空过高：开盘跳空 > 8% 当日跳过
- 超时检查：观察天数超过限制
- 连续阴线：检测短期趋势反转信号
"""
from datetime import date
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import pandas as pd

from ..base import BaseEvaluator
from ..config import RiskFilterConfig
from ..result import DimensionScore

if TYPE_CHECKING:
    from ...pool_entry import PoolEntry
    from ...interfaces import ITimeProvider


class RiskFilterEvaluator(BaseEvaluator):
    """
    风险过滤评估器

    检查各类风险条件，决定是否应该移出观察池或暂停买入。

    作为门槛条件：
    - passed=False 表示触发风险红线
    - passed=True 表示通过所有检查

    权重为0，不参与综合评分的加权计算。

    检查项：
    1. 支撑破位：当前价 < 突破价 * (1 - drop_threshold)
    2. 跳空过高：开盘价 > 前收盘价 * (1 + gap_threshold)
    3. 观察超时：观察天数 > max_holding_days
    4. 连续阴线：最近N根K线连续下跌 (实时模式)
    """

    def __init__(self, config: RiskFilterConfig, scoring_weight: float = 0.0):
        """
        初始化风险过滤评估器

        Args:
            config: 风险过滤配置
            scoring_weight: 评分权重 (默认 0.0，门槛条件不参与加权)
        """
        self.config = config
        self.weight = scoring_weight

    @property
    def dimension_name(self) -> str:
        return 'risk_filter'

    def evaluate(
        self,
        entry: 'PoolEntry',
        current_bar: pd.Series,
        time_provider: 'ITimeProvider',
        context: Optional[Dict[str, Any]] = None
    ) -> DimensionScore:
        """
        评估风险过滤

        Args:
            entry: 观察池条目
            current_bar: 当前价格数据
            time_provider: 时间提供者
            context: 额外上下文，可能包含：
                - prev_close: 前日收盘价
                - minute_bars: 分钟K线（用于检查连续阴线）

        Returns:
            风险过滤维度评分
        """
        context = context or {}
        issues: List[str] = []
        passed = True
        score = 100.0

        current_price = self._safe_get_price(current_bar, 'close')
        open_price = self._safe_get_price(current_bar, 'open')
        reference_price = entry.highest_peak_price or entry.breakout_price

        # ===== 检查1：支撑破位 =====
        if reference_price > 0 and current_price > 0:
            drop_pct = (reference_price - current_price) / reference_price
            if drop_pct > self.config.drop_remove_threshold:
                issues.append(
                    f'Price dropped {drop_pct*100:.1f}% below reference '
                    f'(threshold: {self.config.drop_remove_threshold*100:.1f}%)'
                )
                passed = False
                score = 0

        # ===== 检查2：跳空过高 =====
        prev_close = context.get('prev_close', reference_price)
        if prev_close and prev_close > 0 and open_price > 0:
            gap_pct = (open_price - prev_close) / prev_close
            if gap_pct > self.config.gap_skip_threshold:
                issues.append(
                    f'Gap up {gap_pct*100:.1f}% too large '
                    f'(threshold: {self.config.gap_skip_threshold*100:.1f}%)'
                )
                passed = False
                score = 0

        # ===== 检查3：观察超时 =====
        current_date = time_provider.get_current_date()
        days_in_pool = (current_date - entry.add_date).days
        if days_in_pool > self.config.max_holding_days:
            issues.append(
                f'In pool for {days_in_pool} days, '
                f'exceeds max {self.config.max_holding_days}'
            )
            # 超时不触发移出，但降低评分
            score = max(0, score - 20)

        # ===== 检查4：连续阴线（仅实时模式）=====
        if not time_provider.is_backtest_mode():
            minute_bars = context.get('minute_bars')
            if minute_bars is not None and len(minute_bars) >= self.config.consecutive_red_limit:
                red_count = self._count_consecutive_red(minute_bars)
                if red_count >= self.config.consecutive_red_limit:
                    issues.append(
                        f'{red_count} consecutive red candles detected '
                        f'(limit: {self.config.consecutive_red_limit})'
                    )
                    # 连续阴线降低评分但不移出
                    score = max(0, score - 30)

        # ===== 检查5：巨量阴线（仅实时模式）=====
        if not time_provider.is_backtest_mode():
            massive_red = self._check_massive_red_candle(current_bar, context)
            if massive_red:
                issues.append('Massive red candle detected (high volume sell-off)')
                passed = False
                score = 0

        return self._create_score(
            score=score,
            weight=self.weight,
            passed=passed,
            issues=issues,
            days_in_pool=days_in_pool,
            current_price=current_price,
            reference_price=reference_price,
            checks_performed=[
                'support_break',
                'gap_excessive',
                'holding_timeout',
                'consecutive_red',
                'massive_red_candle'
            ]
        )

    def _count_consecutive_red(self, bars: pd.DataFrame) -> int:
        """
        计算最近连续阴线数量

        Args:
            bars: K线数据（需要有 open, close 列）

        Returns:
            连续阴线数量
        """
        if bars is None or len(bars) == 0:
            return 0

        count = 0
        # 从最新的K线往前数
        for i in range(len(bars) - 1, -1, -1):
            bar = bars.iloc[i]
            if bar.get('close', 0) < bar.get('open', 0):
                count += 1
            else:
                break  # 遇到阳线停止

        return count

    def _check_massive_red_candle(
        self,
        current_bar: pd.Series,
        context: Dict[str, Any]
    ) -> bool:
        """
        检查是否出现巨量阴线

        条件：
        - 当前K线为阴线
        - 跌幅 > 2%
        - 成交量 > 平均成交量的3倍

        Args:
            current_bar: 当前K线数据
            context: 上下文（包含 baseline_volume）

        Returns:
            是否为巨量阴线
        """
        open_price = self._safe_get_price(current_bar, 'open')
        close_price = self._safe_get_price(current_bar, 'close')
        volume = self._safe_get_price(current_bar, 'volume')

        if open_price <= 0 or close_price <= 0:
            return False

        # 检查是否为阴线
        if close_price >= open_price:
            return False

        # 检查跌幅
        drop_pct = (open_price - close_price) / open_price
        if drop_pct < 0.02:  # 跌幅需超过2%
            return False

        # 检查成交量
        baseline_volume = context.get('baseline_volume', 0)
        if baseline_volume > 0:
            volume_ratio = volume / baseline_volume
            if volume_ratio > 3.0:
                return True

        return False
