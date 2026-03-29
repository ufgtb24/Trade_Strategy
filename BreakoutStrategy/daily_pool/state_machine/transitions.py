"""
阶段转换结果

PhaseTransitionResult 描述单次状态机处理的结果。
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .evidence import AnalysisEvidence
    from ..models import Phase


@dataclass
class PhaseTransitionResult:
    """
    阶段转换结果

    描述 PhaseStateMachine.process() 的输出:
    - action: 动作类型
    - from_phase / to_phase: 转换前后的阶段
    - reason: 转换原因（可读字符串）
    - evidence: 导致此转换的证据

    动作类型:
    - "hold": 保持当前阶段
    - "advance": 前进到下一阶段
    - "fail": 转换到 FAILED
    - "expire": 转换到 EXPIRED
    """
    action: str  # "hold" | "advance" | "fail" | "expire"
    from_phase: 'Phase'
    to_phase: 'Phase'
    reason: str
    evidence: 'AnalysisEvidence'

    @property
    def is_transition(self) -> bool:
        """是否发生了阶段转换"""
        return self.action != "hold"

    @property
    def is_terminal(self) -> bool:
        """是否转换到终态"""
        return self.action in ("fail", "expire")

    @property
    def is_signal(self) -> bool:
        """是否生成信号"""
        from ..models import Phase
        return self.to_phase == Phase.SIGNAL

    def __repr__(self) -> str:
        if self.action == "hold":
            return f"PhaseTransitionResult(hold at {self.from_phase.name})"
        return (f"PhaseTransitionResult({self.from_phase.name} -> {self.to_phase.name}, "
                f"action={self.action}, reason={self.reason!r})")
