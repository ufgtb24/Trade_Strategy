"""
价格确认评估器（Bonus 模型）

评估当前价格相对于突破价的位置，使用统一的 Bonus 模型：
    final = BASE(50) × bonus

Bonus 区间划分：
- 跌破移出线: bonus=0 → 0分，触发移出
- 回踩警戒区: bonus=0~0.8 → 0~40分
- 轻微回踩: bonus=0.8~1.0 → 40~50分
- 微弱确认: bonus=0.95 → 47.5分
- 理想确认: bonus=1.2 → 60分
- 追高警戒: bonus=0.6~1.0 → 30~50分
- 超过追高: bonus=0.6 → 30分

支持两种模式：
1. 传统百分比模式：使用固定百分比阈值（如 1%, 2%, 3%）
2. ATR 标准化模式：使用 ATR 倍数作为阈值，自动适应不同波动率股票
"""
from typing import Any, Dict, Optional, TYPE_CHECKING

import pandas as pd

from ..base import BaseEvaluator
from ..config import PriceConfirmConfig
from ..result import DimensionScore

if TYPE_CHECKING:
    from ...pool_entry import PoolEntry
    from ...interfaces import ITimeProvider


class PriceConfirmEvaluator(BaseEvaluator):
    """
    价格确认评估器（Bonus 模型）

    根据当前价格相对于突破价/峰值价的位置评估买入时机。
    使用统一的 Bonus 模型：final = BASE(50) × bonus

    Bonus 逻辑：
    - bonus=0: 跌破移出阈值，触发 passed=False
    - bonus=0.6~0.8: 回踩区间或追高区间
    - bonus=1.0: 中性位置
    - bonus=1.2: 理想确认区间
    """

    def __init__(self, config: PriceConfirmConfig, scoring_weight: float = 0.30):
        """
        初始化价格确认评估器

        Args:
            config: 价格确认配置
            scoring_weight: 评分权重 (默认 0.30)
        """
        self.config = config
        self.weight = scoring_weight

    @property
    def dimension_name(self) -> str:
        return 'price_confirm'

    def evaluate(
        self,
        entry: 'PoolEntry',
        current_bar: pd.Series,
        time_provider: 'ITimeProvider',
        context: Optional[Dict[str, Any]] = None
    ) -> DimensionScore:
        """
        评估价格确认

        支持两种模式：
        1. 传统百分比模式：使用固定百分比阈值
        2. ATR 标准化模式：使用 ATR 倍数作为阈值

        Args:
            entry: 观察池条目
            current_bar: 当前价格数据
            time_provider: 时间提供者
            context: 额外上下文，可包含:
                - atr_value: ATR 值（用于 ATR 标准化模式）

        Returns:
            价格确认维度评分
        """
        context = context or {}

        # 获取当前价格
        current_price = self._safe_get_price(current_bar, 'close')
        if current_price <= 0:
            return self._create_fail_score(
                reason='Invalid current price',
                weight=self.weight,
                current_price=current_price
            )

        # 获取参考价格（使用突破价，因为 breakout_price > highest_peak_price）
        reference_price = entry.breakout_price
        if reference_price <= 0:
            reference_price = entry.highest_peak_price

        if reference_price <= 0:
            return self._create_fail_score(
                reason='Invalid reference price',
                weight=self.weight,
                reference_price=reference_price
            )

        # 获取 ATR 值（优先从 context，否则从 entry.breakout）
        atr_value = context.get('atr_value')
        if atr_value is None and hasattr(entry, 'breakout') and entry.breakout:
            atr_value = getattr(entry.breakout, 'atr_value', 0)

        # 计算价格偏离（绝对值）
        deviation = current_price - reference_price

        # 选择评估模式
        if self.config.use_atr_normalization and atr_value and atr_value > 0:
            # ATR 标准化模式
            return self._evaluate_atr_normalized(
                deviation=deviation,
                atr_value=atr_value,
                current_price=current_price,
                reference_price=reference_price,
                entry=entry
            )
        else:
            # 传统百分比模式
            return self._evaluate_percentage(
                deviation=deviation,
                current_price=current_price,
                reference_price=reference_price,
                entry=entry
            )

    def _evaluate_percentage(
        self,
        deviation: float,
        current_price: float,
        reference_price: float,
        entry: 'PoolEntry'
    ) -> DimensionScore:
        """
        传统百分比模式评估（Bonus 模型）

        统一使用 Bonus 模型：final = BASE × bonus
        - bonus=0: 跌破移出
        - bonus=0.6: 追高过度
        - bonus=1.2: 理想确认

        Args:
            deviation: 价格偏离（绝对值）
            current_price: 当前价格
            reference_price: 参考价格
            entry: 观察池条目

        Returns:
            维度评分
        """
        cfg = self.config
        price_margin = deviation / reference_price
        base = 50.0
        bonus = 1.0
        status = 'unknown'
        passed = True

        # 检查各区间（从下到上）
        if price_margin < -cfg.remove_threshold:
            # 跌破移出阈值
            bonus = 0
            status = 'removed'
            passed = False

        elif price_margin < -cfg.pullback_tolerance:
            # 跌破回踩容忍度（但未到移出阈值）
            # 线性衰减：从 0.6 到 0
            excess_ratio = (abs(price_margin) - cfg.pullback_tolerance) / (cfg.remove_threshold - cfg.pullback_tolerance) if cfg.remove_threshold > cfg.pullback_tolerance else 1.0
            bonus = 0.6 * (1 - min(1.0, excess_ratio))
            status = 'pullback_critical'

        elif price_margin < 0:
            # 回踩区间：0% ~ -pullback_tolerance
            # 线性衰减：1.0 -> 0.6
            ratio = abs(price_margin) / cfg.pullback_tolerance
            bonus = 1.0 - ratio * 0.4
            status = 'pullback'

        elif price_margin < cfg.min_breakout_margin:
            # 低于最优区间但为正：0% ~ min_margin
            # 从 1.0 升到 1.1
            ratio = price_margin / cfg.min_breakout_margin if cfg.min_breakout_margin > 0 else 1.0
            bonus = 1.0 + ratio * 0.1
            status = 'weak_confirm'

        elif price_margin <= cfg.max_breakout_margin:
            # 最优区间：min_margin ~ max_margin
            bonus = 1.2
            status = 'ideal_confirm'

        elif price_margin <= cfg.max_chase_pct:
            # 追高区间：max_margin ~ max_chase
            # 线性衰减：1.0 -> 0.6
            excess = price_margin - cfg.max_breakout_margin
            max_excess = cfg.max_chase_pct - cfg.max_breakout_margin
            if max_excess > 0:
                ratio = min(1.0, excess / max_excess)
                bonus = 1.0 - ratio * 0.4
            else:
                bonus = 0.6
            status = 'chasing_warning'

        else:
            # 超过追高上限
            bonus = 0.6
            status = 'over_chased'

        final = base * bonus

        return self._create_score(
            score=final,
            weight=self.weight,
            passed=passed,
            action='remove' if status == 'removed' else None,
            mode='percentage',
            current_price=current_price,
            reference_price=reference_price,
            price_margin=price_margin,
            bonus=bonus,
            status=status
        )

    def _evaluate_atr_normalized(
        self,
        deviation: float,
        atr_value: float,
        current_price: float,
        reference_price: float,
        entry: 'PoolEntry'
    ) -> DimensionScore:
        """
        ATR 标准化模式评估（Bonus 模型）

        统一使用 Bonus 模型：final = BASE × bonus
        使用 ATR 倍数代替固定百分比，自动适应不同波动率股票。

        例如：$5 股票 ATR=$0.50，涨 $0.25 = 0.5 ATR
              $500 股票 ATR=$10，涨 $5 = 0.5 ATR
        两者评分相同。

        Args:
            deviation: 价格偏离（绝对值，正=上涨，负=下跌）
            atr_value: ATR 值
            current_price: 当前价格
            reference_price: 参考价格
            entry: 观察池条目

        Returns:
            维度评分
        """
        cfg = self.config
        deviation_atr = deviation / atr_value
        base = 50.0
        bonus = 1.0
        status = 'unknown'
        passed = True

        # 检查各区间（从下到上）
        if deviation_atr < cfg.remove_threshold_atr:
            # 跌破移出线（如 < -1.0 ATR）
            bonus = 0
            status = 'removed'
            passed = False

        elif deviation_atr < cfg.pullback_threshold_atr:
            # 回踩警戒区（如 -0.5 ~ -1.0 ATR）
            # 线性衰减：从 marginal_zone_penalty 到 0
            range_size = abs(cfg.remove_threshold_atr - cfg.pullback_threshold_atr)
            if range_size > 0:
                excess_ratio = (cfg.pullback_threshold_atr - deviation_atr) / range_size
                bonus = cfg.marginal_zone_penalty * (1 - min(1.0, excess_ratio))
            else:
                bonus = cfg.marginal_zone_penalty
            status = 'pullback_warning'

        elif deviation_atr < 0:
            # 轻微回踩（0 ~ pullback_threshold ATR）
            # 线性衰减：1.0 -> marginal_zone_penalty
            ratio = abs(deviation_atr) / abs(cfg.pullback_threshold_atr) if cfg.pullback_threshold_atr != 0 else 1.0
            bonus = 1.0 - ratio * (1.0 - cfg.marginal_zone_penalty)
            status = 'minor_pullback'

        elif deviation_atr < cfg.confirm_zone_min_atr:
            # 微弱确认（0 ~ confirm_zone_min ATR）
            bonus = 0.95
            status = 'weak_confirm'

        elif deviation_atr <= cfg.confirm_zone_max_atr:
            # 理想确认区间（confirm_zone_min ~ confirm_zone_max ATR）
            bonus = cfg.ideal_zone_bonus  # 1.2
            status = 'ideal_confirm'

        elif deviation_atr <= cfg.max_chase_atr:
            # 追高警戒区（confirm_zone_max ~ max_chase ATR）
            # 线性衰减 bonus：1.0 -> 0.6
            excess = deviation_atr - cfg.confirm_zone_max_atr
            max_excess = cfg.max_chase_atr - cfg.confirm_zone_max_atr
            if max_excess > 0:
                ratio = min(1.0, excess / max_excess)
                bonus = 1.0 - ratio * 0.4
            else:
                bonus = 0.6
            status = 'chasing_warning'

        else:
            # 超过追高上限（> max_chase ATR）
            bonus = 0.6
            status = 'over_chased'

        final = base * bonus

        return self._create_score(
            score=final,
            weight=self.weight,
            passed=passed,
            action='remove' if status == 'removed' else None,
            mode='atr_normalized',
            current_price=current_price,
            reference_price=reference_price,
            deviation_atr=round(deviation_atr, 2),
            atr_value=atr_value,
            bonus=bonus,
            status=status,
            confirm_zone=(cfg.confirm_zone_min_atr, cfg.confirm_zone_max_atr)
        )

