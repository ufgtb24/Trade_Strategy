"""
阶段转换历史记录

用于追踪条目在各阶段间的转换过程，支持:
- 完整的转换历史记录
- 阶段停留时间计算
- 可解释性分析
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from .phase import Phase


@dataclass
class PhaseTransition:
    """
    阶段转换记录

    记录单次阶段转换的完整信息，用于:
    - 转换历史追溯
    - 信号可解释性
    - 策略调优分析
    """
    from_phase: Phase
    to_phase: Phase
    transition_date: date
    reason: str
    evidence_snapshot: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (f"PhaseTransition({self.from_phase.name} -> {self.to_phase.name}, "
                f"date={self.transition_date}, reason={self.reason!r})")

    def to_dict(self) -> Dict[str, Any]:
        """转为字典（用于序列化）"""
        return {
            'from_phase': self.from_phase.name,
            'to_phase': self.to_phase.name,
            'transition_date': self.transition_date.isoformat(),
            'reason': self.reason,
            'evidence_snapshot': self.evidence_snapshot,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PhaseTransition':
        """从字典创建（用于反序列化）"""
        return cls(
            from_phase=Phase[data['from_phase']],
            to_phase=Phase[data['to_phase']],
            transition_date=date.fromisoformat(data['transition_date']),
            reason=data['reason'],
            evidence_snapshot=data.get('evidence_snapshot', {}),
        )


@dataclass
class PhaseHistory:
    """
    阶段历史记录管理器

    管理条目的完整阶段转换历史，提供:
    - 转换记录添加
    - 阶段停留时间计算
    - 历史查询
    """
    transitions: List[PhaseTransition] = field(default_factory=list)

    def add_transition(self, transition: PhaseTransition) -> None:
        """添加转换记录"""
        self.transitions.append(transition)

    def get_days_in_phase(self, phase: Phase, current_date: date) -> int:
        """
        获取在某阶段停留的天数

        从最近一次进入该阶段的日期计算到当前日期的天数。

        Args:
            phase: 目标阶段
            current_date: 当前日期

        Returns:
            在该阶段停留的天数，未找到返回0
        """
        for t in reversed(self.transitions):
            if t.to_phase == phase:
                return (current_date - t.transition_date).days
        return 0

    def get_last_transition(self) -> Optional[PhaseTransition]:
        """获取最近一次转换"""
        return self.transitions[-1] if self.transitions else None

    def get_phase_entry_date(self, phase: Phase) -> Optional[date]:
        """获取进入某阶段的日期"""
        for t in reversed(self.transitions):
            if t.to_phase == phase:
                return t.transition_date
        return None

    def get_transitions_to(self, phase: Phase) -> List[PhaseTransition]:
        """获取所有进入某阶段的转换记录"""
        return [t for t in self.transitions if t.to_phase == phase]

    def get_phase_sequence(self) -> List[Phase]:
        """获取阶段序列（按时间顺序）"""
        if not self.transitions:
            return []
        sequence = [self.transitions[0].from_phase]
        for t in self.transitions:
            sequence.append(t.to_phase)
        return sequence

    def to_dict(self) -> Dict[str, Any]:
        """转为字典（用于序列化）"""
        return {
            'transitions': [t.to_dict() for t in self.transitions]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PhaseHistory':
        """从字典创建（用于反序列化）"""
        transitions = [
            PhaseTransition.from_dict(t) for t in data.get('transitions', [])
        ]
        return cls(transitions=transitions)

    def __len__(self) -> int:
        return len(self.transitions)

    def __repr__(self) -> str:
        if not self.transitions:
            return "PhaseHistory(empty)"
        sequence = ' -> '.join(p.name for p in self.get_phase_sequence())
        return f"PhaseHistory({sequence})"
