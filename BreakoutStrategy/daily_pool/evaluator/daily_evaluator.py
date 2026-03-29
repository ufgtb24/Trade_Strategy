"""
Daily 池评估器

协调分析器和状态机，实现完整的评估流程。
"""
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional

import pandas as pd

from ..models import Phase, DailyPoolEntry, DailySignal, SignalType, SignalStrength, PhaseTransition
from ..config import DailyPoolConfig
from ..state_machine import AnalysisEvidence, PhaseTransitionResult
from ..analyzers import (
    PricePatternAnalyzer, VolatilityAnalyzer, VolumeAnalyzer,
    PricePatternResult, VolatilityResult, VolumeResult
)


@dataclass
class PhaseEvaluation:
    """评估结果"""
    transition: PhaseTransitionResult
    signal: Optional[DailySignal]
    entry_updated: bool


class DailyPoolEvaluator:
    """
    Daily 池评估器

    核心职责:
    - 协调三个分析器
    - 聚合分析证据
    - 驱动状态机
    - 生成买入信号
    """

    def __init__(self, config: DailyPoolConfig):
        """
        初始化评估器

        Args:
            config: Daily 池配置
        """
        self.config = config
        self.price_analyzer = PricePatternAnalyzer(config.price_pattern)
        self.volatility_analyzer = VolatilityAnalyzer(config.volatility)
        self.volume_analyzer = VolumeAnalyzer(config.volume)

    def evaluate(self, entry: DailyPoolEntry, df: pd.DataFrame,
                 as_of_date: date) -> PhaseEvaluation:
        """
        评估单个条目

        Args:
            entry: 池条目
            df: 截止到 as_of_date 的 OHLCV DataFrame
            as_of_date: 评估日期

        Returns:
            PhaseEvaluation
        """
        if len(df) == 0:
            # 空数据，保持状态
            return PhaseEvaluation(
                transition=PhaseTransitionResult(
                    action="hold",
                    from_phase=entry.current_phase,
                    to_phase=entry.current_phase,
                    reason="No data available",
                    evidence=self._empty_evidence(as_of_date)
                ),
                signal=None,
                entry_updated=False
            )

        # 更新价格追踪
        latest = df.iloc[-1]
        entry.update_price_tracking(
            high=float(latest['high']),
            low=float(latest['low']),
            close=float(latest['close'])
        )

        # 1. 三维度分析
        price_result = self.price_analyzer.analyze(df, entry, as_of_date)
        volatility_result = self.volatility_analyzer.analyze(
            df, entry.initial_atr, as_of_date
        )
        volume_result = self.volume_analyzer.analyze(df, as_of_date)

        # 2. 聚合证据
        evidence = self._build_evidence(
            price_result, volatility_result, volume_result, as_of_date
        )

        # 3. 驱动状态机
        if entry.phase_machine is None:
            raise ValueError(f"Entry {entry.entry_id} has no phase_machine")

        transition = entry.phase_machine.process(evidence)
        
        # 4. 只有当状态机做出了实际转换（不是"hold"保持不变）时才记录
        if transition.action != "hold":
            entry.phase_history.add_transition(PhaseTransition(
                from_phase=transition.from_phase,  # 从哪个阶段
                to_phase=transition.to_phase,  # 转换到哪个阶段
                transition_date=as_of_date,  # 转换发生日期
                reason=transition.reason,  # 转换原因（可读文本）
                evidence_snapshot=evidence.get_summary()  # 当时的证据快照
            ))
            
        # 5. 生成信号（如果到达 SIGNAL 阶段）
        signal = None
        if entry.phase_machine.can_emit_signal():
            signal = self._generate_signal(entry, evidence, df)

        return PhaseEvaluation(
            transition=transition,
            signal=signal,
            entry_updated=True
        )

    def _build_evidence(self, price: PricePatternResult,
                        volatility: VolatilityResult,
                        volume: VolumeResult,
                        as_of_date: date) -> AnalysisEvidence:
        """从三个分析结果构建证据"""
        return AnalysisEvidence(
            as_of_date=as_of_date,
            # 价格模式
            pullback_depth_atr=price.pullback_depth_atr,
            support_strength=price.strongest_support.strength if price.strongest_support else 0.0,
            support_tests_count=price.strongest_support.test_count if price.strongest_support else 0,
            price_above_consolidation_top=(price.price_position == "above_range"),
            consolidation_valid=price.has_valid_consolidation,
            # 波动率
            convergence_score=volatility.convergence_score,
            volatility_state=volatility.volatility_state,
            atr_ratio=volatility.atr_ratio,
            # 成交量
            volume_expansion_ratio=volume.volume_expansion_ratio,
            surge_detected=volume.surge_detected,
            volume_trend=volume.volume_trend
        )

    def _generate_signal(self, entry: DailyPoolEntry,
                         evidence: AnalysisEvidence,
                         df: pd.DataFrame) -> DailySignal:
        """生成买入信号"""
        # 计算置信度
        confidence = self._calculate_confidence(evidence, entry)

        # 确定信号强度
        strength = self._determine_strength(confidence)

        # 计算交易参数
        current_price = entry.current_price
        stop_loss = self._calculate_stop_loss(entry, df)
        position_pct = self.config.signal.position_sizing.get(strength.value, 0.10)

        return DailySignal(
            symbol=entry.symbol,
            signal_date=evidence.as_of_date,
            signal_type=SignalType.REIGNITION_BUY,
            strength=strength,
            entry_price=current_price,
            stop_loss_price=stop_loss,
            position_size_pct=position_pct,
            phase_when_signaled=entry.current_phase,
            days_to_signal=entry.days_in_pool,
            evidence_summary=evidence.get_summary(),
            confidence=confidence
        )

    def _calculate_confidence(self, evidence: AnalysisEvidence,
                              entry: DailyPoolEntry) -> float:
        """
        计算置信度

        公式: confidence = w1*收敛分数 + w2*支撑强度 + w3*放量程度 + w4*突破质量
        """
        weights = self.config.signal.confidence_weights

        convergence_score = evidence.convergence_score * weights.get('convergence', 0.30)
        support_score = evidence.support_strength * weights.get('support', 0.25)
        volume_score = min(evidence.volume_expansion_ratio / 2.0, 1.0) * weights.get('volume', 0.25)
        quality_score = min(entry.quality_score / 100, 1.0) * weights.get('quality', 0.20)

        return convergence_score + support_score + volume_score + quality_score

    def _determine_strength(self, confidence: float) -> SignalStrength:
        """根据置信度确定信号强度"""
        if confidence >= 0.7:
            return SignalStrength.STRONG
        elif confidence >= 0.5:
            return SignalStrength.NORMAL
        else:
            return SignalStrength.WEAK

    def _calculate_stop_loss(self, entry: DailyPoolEntry,
                             df: pd.DataFrame) -> float:
        """
        计算止损价

        策略: 取最近10天低点下方 0.5 ATR
        """
        recent_low = float(df.tail(10)['low'].min())
        stop_loss = recent_low - 0.5 * entry.initial_atr
        return stop_loss

    def _empty_evidence(self, as_of_date: date) -> AnalysisEvidence:
        """创建空证据"""
        return AnalysisEvidence(
            as_of_date=as_of_date,
            pullback_depth_atr=0.0,
            support_strength=0.0,
            support_tests_count=0,
            price_above_consolidation_top=False,
            consolidation_valid=False,
            convergence_score=0.0,
            volatility_state="stable",
            atr_ratio=1.0,
            volume_expansion_ratio=1.0,
            surge_detected=False,
            volume_trend="neutral"
        )
