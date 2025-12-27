"""
组合买入条件评估器

整合四维度评估，计算综合评分并生成最终决策。

流程：
1. 执行所有维度评估
2. 检查门槛条件（风险过滤）
3. 计算加权总分
4. 结合质量评分调整
5. 确定最终动作
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import pandas as pd

from .base import IBuyConditionEvaluator
from .config import BuyConditionConfig
from .result import DimensionScore, EvaluationAction, EvaluationResult
from .components import (
    TimeWindowEvaluator,
    PriceConfirmEvaluator,
    VolumeVerifyEvaluator,
    RiskFilterEvaluator,
)

if TYPE_CHECKING:
    from ..pool_entry import PoolEntry
    from ..interfaces import ITimeProvider


class CompositeBuyEvaluator:
    """
    组合买入条件评估器

    整合四维度评估（时间窗口、价格确认、成交量验证、风险过滤），
    计算综合评分并生成买入决策。

    评分计算：
    1. 各维度评分加权求和（风险过滤不参与加权）
    2. 结合质量评分因子调整
    3. 根据阈值确定动作

    决策输出：
    - STRONG_BUY: 综合评分 >= 70
    - NORMAL_BUY: 综合评分 >= 50
    - HOLD: 评分 < 50，继续观察
    - REMOVE: 风险过滤失败（跌破阈值等）
    """

    def __init__(self, config: BuyConditionConfig):
        """
        初始化组合评估器

        Args:
            config: 买入条件完整配置
        """
        self.config = config

        # 创建四维度评估器
        self.evaluators: List[IBuyConditionEvaluator] = [
            TimeWindowEvaluator(
                config.time_window,
                scoring_weight=config.scoring.time_weight
            ),
            PriceConfirmEvaluator(
                config.price_confirm,
                scoring_weight=config.scoring.price_weight
            ),
            VolumeVerifyEvaluator(
                config.volume_verify,
                scoring_weight=config.scoring.volume_weight
            ),
            RiskFilterEvaluator(
                config.risk_filter,
                scoring_weight=0.0  # 风险过滤不参与加权
            ),
        ]

    def evaluate(
        self,
        entry: 'PoolEntry',
        current_bar: pd.Series,
        time_provider: 'ITimeProvider',
        context: Optional[Dict[str, Any]] = None
    ) -> EvaluationResult:
        """
        执行综合评估

        Args:
            entry: 观察池条目
            current_bar: 当前价格数据
            time_provider: 时间提供者
            context: 额外上下文

        Returns:
            EvaluationResult 综合评估结果
        """
        context = context or {}
        dimension_scores: List[DimensionScore] = []

        # ===== 阶段1：执行所有维度评估 =====
        for evaluator in self.evaluators:
            score = evaluator.evaluate(entry, current_bar, time_provider, context)
            dimension_scores.append(score)

        # ===== 阶段2：检查门槛条件 =====
        risk_score = self._get_dimension_score(dimension_scores, 'risk_filter')
        price_score = self._get_dimension_score(dimension_scores, 'price_confirm')

        # 风险过滤失败
        if risk_score and not risk_score.passed:
            action = EvaluationAction.REMOVE
            reason = 'Risk filter failed: ' + ', '.join(
                risk_score.details.get('issues', ['Unknown'])
            )
            return self._create_result(
                symbol=entry.symbol,
                action=action,
                total_score=0,
                dimension_scores=dimension_scores,
                reason=reason,
                current_bar=current_bar,
                entry=entry
            )

        # 价格确认失败（跌破阈值）
        if price_score and not price_score.passed:
            action_str = price_score.details.get('action', '')
            if action_str == 'remove':
                action = EvaluationAction.REMOVE
                reason = price_score.details.get('reason', 'Price dropped below threshold')
                return self._create_result(
                    symbol=entry.symbol,
                    action=action,
                    total_score=0,
                    dimension_scores=dimension_scores,
                    reason=reason,
                    current_bar=current_bar,
                    entry=entry
                )

        # ===== 阶段3：计算加权总分 =====
        weighted_sum = 0.0
        total_weight = 0.0

        for score in dimension_scores:
            if score.weight > 0:
                weighted_sum += score.score * score.weight
                total_weight += score.weight

        base_score = weighted_sum / total_weight if total_weight > 0 else 0

        # ===== 阶段4：质量评分调整 =====
        # 质量评分因子：0.5-1.0 的范围调整
        quality_score = entry.quality_score if entry.quality_score else 50
        quality_factor = 0.5 + (min(quality_score, 100) / 100) * 0.5

        # 应用质量因子（影响25%）
        quality_weight = self.config.scoring.quality_weight
        adjusted_score = base_score * (1 - quality_weight) + base_score * quality_factor * quality_weight

        # ===== 阶段5：确定最终动作 =====
        action, reason = self._determine_action(adjusted_score, dimension_scores)

        return self._create_result(
            symbol=entry.symbol,
            action=action,
            total_score=adjusted_score,
            dimension_scores=dimension_scores,
            reason=reason,
            current_bar=current_bar,
            entry=entry
        )

    def _get_dimension_score(
        self,
        scores: List[DimensionScore],
        dimension: str
    ) -> Optional[DimensionScore]:
        """获取指定维度的评分"""
        for score in scores:
            if score.dimension == dimension:
                return score
        return None

    def _determine_action(
        self,
        score: float,
        dimension_scores: List[DimensionScore]
    ) -> tuple:
        """
        确定最终动作

        Args:
            score: 综合评分
            dimension_scores: 各维度评分

        Returns:
            (action, reason) 元组
        """
        thresholds = self.config.scoring

        if score >= thresholds.strong_buy_threshold:
            return EvaluationAction.STRONG_BUY, f'Strong buy signal (score={score:.1f})'

        elif score >= thresholds.normal_buy_threshold:
            return EvaluationAction.NORMAL_BUY, f'Normal buy signal (score={score:.1f})'

        else:
            # 检查哪个维度得分最低，提供更具体的原因
            lowest_dim = min(
                [s for s in dimension_scores if s.weight > 0],
                key=lambda s: s.score,
                default=None
            )
            if lowest_dim:
                reason = (f'Score below threshold ({score:.1f} < {thresholds.normal_buy_threshold}), '
                         f'lowest: {lowest_dim.dimension}={lowest_dim.score:.0f}')
            else:
                reason = f'Score below threshold ({score:.1f} < {thresholds.normal_buy_threshold})'

            return EvaluationAction.HOLD, reason

    def _create_result(
        self,
        symbol: str,
        action: EvaluationAction,
        total_score: float,
        dimension_scores: List[DimensionScore],
        reason: str,
        current_bar: pd.Series,
        entry: 'PoolEntry'
    ) -> EvaluationResult:
        """创建评估结果"""
        current_price = current_bar.get('close', 0) if current_bar is not None else 0
        reference_price = entry.highest_peak_price or entry.breakout_price

        # 计算止损价
        stop_loss = None
        if reference_price > 0:
            stop_loss = reference_price * (1 - self.config.price_confirm.pullback_tolerance)

        # 计算建议仓位
        position_pct = self._calculate_position_size(total_score)

        return EvaluationResult(
            symbol=symbol,
            action=action,
            total_score=total_score,
            dimension_scores=dimension_scores,
            suggested_entry_price=current_price if current_price > 0 else None,
            suggested_stop_loss=stop_loss,
            suggested_position_pct=position_pct,
            reason=reason,
            metadata={
                'quality_score': entry.quality_score,
                'reference_price': reference_price,
                'config_mode': self.config.mode,
            }
        )

    def _calculate_position_size(self, score: float) -> float:
        """
        根据评分计算建议仓位比例

        Args:
            score: 综合评分 (0-100)

        Returns:
            仓位比例 (0-1)
        """
        if score >= 80:
            return 0.15
        elif score >= 70:
            return 0.12
        elif score >= 60:
            return 0.10
        elif score >= 50:
            return 0.08
        else:
            return 0.05
