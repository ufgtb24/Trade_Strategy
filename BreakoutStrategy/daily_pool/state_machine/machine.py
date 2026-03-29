"""
阶段状态机核心实现

PhaseStateMachine 是 Daily 池的核心决策引擎，负责:
- 管理阶段状态
- 根据证据判断阶段转换
- 记录转换历史
"""
from datetime import date
from typing import List

from ..models import Phase, PhaseTransition
from ..config import PhaseConfig
from .evidence import AnalysisEvidence
from .transitions import PhaseTransitionResult


class PhaseStateMachine:
    """
    阶段状态机

    状态转换图:
        INITIAL ──┬──> PULLBACK ──> CONSOLIDATION ──> REIGNITION ──> SIGNAL
                  └──> CONSOLIDATION ─────────────────────────────────────┘

        任意阶段 ──> FAILED (回调过深/阶段超时)
        任意阶段 ──> EXPIRED (观察期满)

    使用方式:
        machine = PhaseStateMachine(config, entry_date)
        result = machine.process(evidence)
        if result.is_signal:
            # 生成买入信号
    """

    def __init__(self, config: PhaseConfig, entry_date: date):
        """
        初始化状态机

        Args:
            config: 阶段配置
            entry_date: 入池日期
        """
        self.config = config
        self.entry_date = entry_date
        self.current_phase = Phase.INITIAL
        self.phase_start_date = entry_date
        self.history: List[PhaseTransition] = []

    def process(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """
        核心方法：根据证据判断阶段转换

        Args:
            evidence: 聚合的分析证据

        Returns:
            PhaseTransitionResult 描述转换动作
        """
        # 0. 过期检查（全局）
        total_days = (evidence.as_of_date - self.entry_date).days
        if total_days >= self.config.max_observation_days:
            return self._transition_to(
                Phase.EXPIRED,
                f"Observation period expired after {total_days} days",
                evidence
            )

        # 1. 全局失败检查
        if evidence.pullback_depth_atr > self.config.max_drop_from_breakout_atr:
            return self._transition_to(
                Phase.FAILED,
                f"Pullback too deep: {evidence.pullback_depth_atr:.2f} ATR > "
                f"{self.config.max_drop_from_breakout_atr} ATR limit",
                evidence
            )

        # 2. 阶段特定检查
        if self.current_phase == Phase.INITIAL:
            return self._eval_initial(evidence)
        elif self.current_phase == Phase.PULLBACK:
            return self._eval_pullback(evidence)
        elif self.current_phase == Phase.CONSOLIDATION:
            return self._eval_consolidation(evidence)
        elif self.current_phase == Phase.REIGNITION:
            return self._eval_reignition(evidence)

        # 终态不再转换
        return self._hold(evidence)

    def _eval_initial(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """
        INITIAL 阶段评估

        可能转换:
        - -> CONSOLIDATION: 无明显回调但波动收敛
        - -> PULLBACK: 开始回调
        """
        # 直接进入企稳（无明显回调但波动收敛）
        if (evidence.pullback_depth_atr < self.config.pullback_trigger_atr and
            evidence.convergence_score >= self.config.min_convergence_score):
            return self._transition_to(
                Phase.CONSOLIDATION,
                f"Direct to consolidation: no pullback (depth={evidence.pullback_depth_atr:.2f} ATR), "
                f"volatility converging (score={evidence.convergence_score:.2f})",
                evidence
            )

        # 进入回调
        if evidence.pullback_depth_atr >= self.config.pullback_trigger_atr:
            return self._transition_to(
                Phase.PULLBACK,
                f"Entering pullback: depth={evidence.pullback_depth_atr:.2f} ATR >= "
                f"{self.config.pullback_trigger_atr} ATR trigger",
                evidence
            )

        return self._hold(evidence)

    def _eval_pullback(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """
        PULLBACK 阶段评估

        可能转换:
        - -> CONSOLIDATION: 波动收敛 + 支撑形成
        - -> FAILED: 超时
        """
        days_in_phase = self._days_in_current_phase(evidence.as_of_date)

        # 超时失败
        if days_in_phase > self.config.max_pullback_days:
            return self._transition_to(
                Phase.FAILED,
                f"Pullback timeout: {days_in_phase} days > {self.config.max_pullback_days} days limit",
                evidence
            )

        # 进入企稳：波动收敛 + 支撑形成
        if (evidence.convergence_score >= self.config.min_convergence_score and
            evidence.support_tests_count >= self.config.min_support_tests):
            return self._transition_to(
                Phase.CONSOLIDATION,
                f"Entering consolidation: convergence={evidence.convergence_score:.2f} >= "
                f"{self.config.min_convergence_score}, support_tests={evidence.support_tests_count} >= "
                f"{self.config.min_support_tests}",
                evidence
            )

        return self._hold(evidence)

    def _eval_consolidation(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """
        CONSOLIDATION 阶段评估

        可能转换:
        - -> REIGNITION: 放量 + 突破区间上沿
        - -> FAILED: 超时
        """
        days_in_phase = self._days_in_current_phase(evidence.as_of_date)

        # 超时失败
        if days_in_phase > self.config.max_consolidation_days:
            return self._transition_to(
                Phase.FAILED,
                f"Consolidation timeout: {days_in_phase} days > "
                f"{self.config.max_consolidation_days} days limit",
                evidence
            )

        # 再启动：放量 + 突破区间上沿
        if (evidence.volume_expansion_ratio >= self.config.min_volume_expansion and
            evidence.price_above_consolidation_top):
            return self._transition_to(
                Phase.REIGNITION,
                f"Reignition triggered: volume={evidence.volume_expansion_ratio:.1f}x >= "
                f"{self.config.min_volume_expansion}x, price above consolidation top",
                evidence
            )

        return self._hold(evidence)

    def _eval_reignition(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """
        REIGNITION 阶段评估

        可能转换:
        - -> SIGNAL: 确认期满
        - -> CONSOLIDATION: 假突破回退
        """
        days_in_phase = self._days_in_current_phase(evidence.as_of_date)

        # 假突破回退
        if not evidence.price_above_consolidation_top:
            return self._transition_to(
                Phase.CONSOLIDATION,
                "False breakout: price fell back into consolidation range",
                evidence
            )

        # 确认信号
        if days_in_phase >= self.config.breakout_confirm_days:
            return self._transition_to(
                Phase.SIGNAL,
                f"Signal confirmed: breakout maintained for {days_in_phase} days >= "
                f"{self.config.breakout_confirm_days} days required",
                evidence
            )

        return self._hold(evidence)

    def _transition_to(self, to_phase: Phase, reason: str,
                       evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """执行阶段转换"""
        from_phase = self.current_phase

        # 记录历史
        transition = PhaseTransition(
            from_phase=from_phase,
            to_phase=to_phase,
            transition_date=evidence.as_of_date,
            reason=reason,
            evidence_snapshot=evidence.get_summary()
        )
        self.history.append(transition)

        # 更新状态
        self.current_phase = to_phase
        self.phase_start_date = evidence.as_of_date

        # 确定动作类型
        if to_phase == Phase.FAILED:
            action = "fail"
        elif to_phase == Phase.EXPIRED:
            action = "expire"
        else:
            action = "advance"

        return PhaseTransitionResult(
            action=action,
            from_phase=from_phase,
            to_phase=to_phase,
            reason=reason,
            evidence=evidence
        )

    def _hold(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """保持当前阶段"""
        return PhaseTransitionResult(
            action="hold",
            from_phase=self.current_phase,
            to_phase=self.current_phase,
            reason="Conditions not met for transition",
            evidence=evidence
        )

    def _days_in_current_phase(self, as_of_date: date) -> int:
        """计算在当前阶段的天数"""
        return (as_of_date - self.phase_start_date).days

    def can_emit_signal(self) -> bool:
        """是否可以发出信号"""
        return self.current_phase == Phase.SIGNAL

    def get_phase_duration(self, phase: Phase) -> int:
        """
        获取在某阶段停留的总天数

        Args:
            phase: 目标阶段

        Returns:
            在该阶段停留的天数，未经历返回0
        """
        total_days = 0
        for i, t in enumerate(self.history):
            if t.to_phase == phase:
                # 找到离开该阶段的时间
                if i + 1 < len(self.history):
                    end_date = self.history[i + 1].transition_date
                else:
                    end_date = t.transition_date
                total_days += (end_date - t.transition_date).days
        return total_days

    def __repr__(self) -> str:
        return (f"PhaseStateMachine(phase={self.current_phase.name}, "
                f"transitions={len(self.history)})")
