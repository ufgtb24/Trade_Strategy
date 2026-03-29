"""
买入条件评估结果

定义评估结果的数据结构，包括：
- EvaluationAction: 评估动作枚举
- DimensionScore: 单维度评分结果
- EvaluationResult: 综合评估结果
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EvaluationAction(Enum):
    """
    评估结果动作

    决定对观察池条目的处理方式：
    - STRONG_BUY: 强买入信号 (评分 >= 70)
    - NORMAL_BUY: 普通买入信号 (评分 50-70)
    - HOLD: 继续观察
    - REMOVE: 移出观察池 (突破失败)
    - TRANSFER: 转移到日K池
    """
    STRONG_BUY = 'strong_buy'
    NORMAL_BUY = 'normal_buy'
    HOLD = 'hold'
    REMOVE = 'remove'
    TRANSFER = 'transfer'


@dataclass
class DimensionScore:
    """
    单维度评分结果

    记录某一维度（时间窗口/价格确认/成交量/风险过滤）的评估结果。

    Attributes:
        dimension: 维度名称
        score: 评分 (0-100)
        weight: 权重 (用于加权计算)
        details: 详细信息字典
        passed: 是否通过门槛 (用于风险过滤等门槛条件)
    """
    dimension: str
    score: float
    weight: float
    details: Dict[str, Any] = field(default_factory=dict)
    passed: bool = True

    @property
    def weighted_score(self) -> float:
        """加权评分"""
        return self.score * self.weight

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"DimensionScore({self.dimension}: {self.score:.1f} * {self.weight:.2f} = {self.weighted_score:.1f}, {status})"


@dataclass
class EvaluationResult:
    """
    综合评估结果

    整合所有维度的评估结果，提供最终的买入决策和交易建议。

    Attributes:
        symbol: 股票代码
        action: 评估动作
        total_score: 综合评分 (0-100)
        dimension_scores: 各维度评分列表
        suggested_entry_price: 建议买入价格
        suggested_stop_loss: 建议止损价格
        suggested_position_pct: 建议仓位比例 (0-1)
        reason: 决策原因描述
        metadata: 额外元数据
        evaluated_at: 评估时间
    """
    symbol: str
    action: EvaluationAction
    total_score: float
    dimension_scores: List[DimensionScore]

    # 交易建议
    suggested_entry_price: Optional[float] = None
    suggested_stop_loss: Optional[float] = None
    suggested_position_pct: float = 0.10

    # 元信息
    reason: str = ''
    metadata: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=datetime.now)

    @property
    def is_buy_signal(self) -> bool:
        """是否为买入信号"""
        return self.action in (EvaluationAction.STRONG_BUY, EvaluationAction.NORMAL_BUY)

    @property
    def is_strong_buy(self) -> bool:
        """是否为强买入信号"""
        return self.action == EvaluationAction.STRONG_BUY

    @property
    def signal_strength(self) -> float:
        """
        信号强度 (0-1)

        用于 BuySignal 的 signal_strength 字段
        """
        return min(self.total_score / 100, 1.0)

    @property
    def risk_reward_ratio(self) -> Optional[float]:
        """
        风险收益比

        基于建议入场价和止损价计算
        """
        if (self.suggested_entry_price is not None
                and self.suggested_stop_loss is not None
                and self.suggested_entry_price > 0):
            risk = self.suggested_entry_price - self.suggested_stop_loss
            if risk > 0:
                # 假设目标收益是风险的2倍
                return 2.0
        return None

    def get_dimension_score(self, dimension: str) -> Optional[DimensionScore]:
        """获取指定维度的评分"""
        for ds in self.dimension_scores:
            if ds.dimension == dimension:
                return ds
        return None

    def all_filters_passed(self) -> bool:
        """所有门槛条件是否都通过"""
        return all(ds.passed for ds in self.dimension_scores)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于日志或序列化）"""
        return {
            'symbol': self.symbol,
            'action': self.action.value,
            'total_score': self.total_score,
            'is_buy_signal': self.is_buy_signal,
            'signal_strength': self.signal_strength,
            'suggested_entry_price': self.suggested_entry_price,
            'suggested_stop_loss': self.suggested_stop_loss,
            'suggested_position_pct': self.suggested_position_pct,
            'reason': self.reason,
            'dimension_scores': [
                {
                    'dimension': ds.dimension,
                    'score': ds.score,
                    'weight': ds.weight,
                    'passed': ds.passed,
                    'details': ds.details,
                }
                for ds in self.dimension_scores
            ],
            'evaluated_at': self.evaluated_at.isoformat(),
        }

    def __repr__(self) -> str:
        dims_str = ', '.join(f"{ds.dimension}={ds.score:.0f}" for ds in self.dimension_scores)
        return (f"EvaluationResult({self.symbol}: {self.action.value}, "
                f"score={self.total_score:.1f}, [{dims_str}])")
