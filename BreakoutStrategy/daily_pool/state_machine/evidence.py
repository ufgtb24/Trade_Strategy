"""
分析证据聚合

AnalysisEvidence 是三个分析器输出的聚合，作为状态机决策的输入。
"""
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict


@dataclass
class AnalysisEvidence:
    """
    分析证据聚合

    由 DailyPoolEvaluator 从三个 Analyzer 的结果中构建，
    作为 PhaseStateMachine.process() 的输入。

    设计理念:
        证据是"事实"，状态机根据事实做"判断"。
        分析器只负责计算，不做阈值判断。
    """
    as_of_date: date

    # ===== 价格模式证据 =====
    pullback_depth_atr: float          # 回调深度（ATR单位）
    support_strength: float            # 最强支撑位强度 (0-1)
    support_tests_count: int           # 支撑测试次数
    price_above_consolidation_top: bool  # 价格是否突破企稳区间上沿
    consolidation_valid: bool          # 企稳区间是否有效

    # ===== 波动率证据 =====
    convergence_score: float           # 收敛分数 (0-1)
    volatility_state: str              # "contracting" | "stable" | "expanding"
    atr_ratio: float                   # 当前ATR / 初始ATR

    # ===== 成交量证据 =====
    volume_expansion_ratio: float      # 放量比率（当前量/基准量）
    surge_detected: bool               # 是否检测到放量
    volume_trend: str                  # "increasing" | "neutral" | "decreasing"

    def to_dict(self) -> Dict[str, Any]:
        """转为字典（用于记录/调试）"""
        return {
            'as_of_date': self.as_of_date.isoformat(),
            'pullback_depth_atr': round(self.pullback_depth_atr, 3),
            'support_strength': round(self.support_strength, 3),
            'support_tests_count': self.support_tests_count,
            'price_above_consolidation_top': self.price_above_consolidation_top,
            'consolidation_valid': self.consolidation_valid,
            'convergence_score': round(self.convergence_score, 3),
            'volatility_state': self.volatility_state,
            'atr_ratio': round(self.atr_ratio, 3),
            'volume_expansion_ratio': round(self.volume_expansion_ratio, 2),
            'surge_detected': self.surge_detected,
            'volume_trend': self.volume_trend,
        }

    def get_summary(self) -> Dict[str, Any]:
        """获取关键指标摘要（用于信号可解释性）"""
        return {
            'pullback_depth_atr': round(self.pullback_depth_atr, 3),
            'convergence_score': round(self.convergence_score, 3),
            'support_tests': self.support_tests_count,
            'volume_ratio': round(self.volume_expansion_ratio, 2),
            'volatility_state': self.volatility_state,
            'price_position': 'above' if self.price_above_consolidation_top else 'in/below',
        }

    def __repr__(self) -> str:
        return (f"AnalysisEvidence(date={self.as_of_date}, "
                f"pullback={self.pullback_depth_atr:.2f}ATR, "
                f"convergence={self.convergence_score:.2f}, "
                f"volume={self.volume_expansion_ratio:.1f}x)")
