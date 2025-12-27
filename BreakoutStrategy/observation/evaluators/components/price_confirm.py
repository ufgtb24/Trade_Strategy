"""
价格确认评估器

评估当前价格相对于突破价的位置：
- 确认区间：突破价上方 1%-2%（满分）
- 低于确认区间：按比例降分
- 回踩区间：容忍3%回调，逐渐降分
- 跌破阈值：触发移出信号
- 追高区间：超过5%不追，评分降低
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
    价格确认评估器

    根据当前价格相对于突破价/峰值价的位置评估买入时机。

    评分逻辑：
    - 最优区间 (突破价 +1% ~ +2%)：100分
    - 低于最优但为正 (0% ~ +1%)：70-100分
    - 回踩区间 (0% ~ -3%)：0-70分（线性降低）
    - 跌破阈值 (-3% 以下)：0分，passed=False（触发移出）
    - 追高区间 (+2% ~ +5%)：100分递减到50分
    - 超过追高 (+5% 以上)：50分以下（放弃）
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

        Args:
            entry: 观察池条目
            current_bar: 当前价格数据
            time_provider: 时间提供者
            context: 额外上下文

        Returns:
            价格确认维度评分
        """
        # 获取当前价格
        current_price = self._safe_get_price(current_bar, 'close')
        if current_price <= 0:
            return self._create_fail_score(
                reason='Invalid current price',
                weight=self.weight,
                current_price=current_price
            )

        # 获取参考价格（优先使用最高峰值价，否则使用突破价）
        reference_price = entry.highest_peak_price
        if reference_price <= 0:
            reference_price = entry.breakout_price

        if reference_price <= 0:
            return self._create_fail_score(
                reason='Invalid reference price',
                weight=self.weight,
                reference_price=reference_price
            )

        # 计算价格偏离
        price_margin = self._calculate_margin(current_price, reference_price)

        # 检查是否跌破移出阈值
        if price_margin < -self.config.remove_threshold:
            return self._create_score(
                score=0,
                weight=self.weight,
                passed=False,
                action='remove',
                current_price=current_price,
                reference_price=reference_price,
                price_margin=price_margin,
                threshold=-self.config.remove_threshold,
                reason=f'Price dropped {abs(price_margin)*100:.1f}% below reference'
            )

        # 检查是否超过最大追高比例
        if price_margin > self.config.max_chase_pct:
            return self._create_score(
                score=30,  # 极低分数，但不触发移出
                weight=self.weight,
                passed=True,
                action='skip_chase',
                current_price=current_price,
                reference_price=reference_price,
                price_margin=price_margin,
                max_chase_pct=self.config.max_chase_pct,
                reason=f'Price too high (+{price_margin*100:.1f}%), skip to avoid chasing'
            )

        # 计算评分
        score = self._calculate_score(price_margin)

        return self._create_score(
            score=score,
            weight=self.weight,
            passed=True,
            current_price=current_price,
            reference_price=reference_price,
            price_margin=price_margin,
            optimal_range=(self.config.min_breakout_margin, self.config.max_breakout_margin)
        )

    def _calculate_score(self, margin: float) -> float:
        """
        计算价格确认评分

        Args:
            margin: 价格偏离比例 (正数高于参考价，负数低于)

        Returns:
            评分 (0-100)
        """
        min_m = self.config.min_breakout_margin  # 1%
        max_m = self.config.max_breakout_margin  # 2%
        pullback = self.config.pullback_tolerance  # 3%
        max_chase = self.config.max_chase_pct  # 5%

        if margin < -pullback:
            # 跌破回踩容忍度（但未到移出阈值）
            # 评分在 0-30 之间
            excess = abs(margin) - pullback
            return max(0, 30 - excess * 1000)

        elif margin < 0:
            # 回踩区间：0% ~ -3%
            # 线性降分：从70分降到30分
            ratio = abs(margin) / pullback
            return 70 - ratio * 40

        elif margin < min_m:
            # 低于最优区间但为正：0% ~ 1%
            # 从70分升到100分
            ratio = margin / min_m
            return 70 + ratio * 30

        elif margin <= max_m:
            # 最优区间：1% ~ 2%
            return 100

        else:
            # 追高区间：2% ~ 5%
            # 从100分降到50分
            excess = margin - max_m
            max_excess = max_chase - max_m
            if max_excess > 0:
                ratio = min(1.0, excess / max_excess)
                return 100 - ratio * 50
            return 50
