"""
阶段状态机模块

核心组件:
- AnalysisEvidence: 分析证据聚合数据类
- PhaseTransitionResult: 阶段转换结果
- PhaseStateMachine: 阶段状态机核心类

状态机负责:
- 管理阶段状态 (INITIAL -> PULLBACK -> CONSOLIDATION -> REIGNITION -> SIGNAL)
- 根据证据判断阶段转换
- 记录转换历史
"""
from .evidence import AnalysisEvidence
from .transitions import PhaseTransitionResult
from .machine import PhaseStateMachine

__all__ = [
    'AnalysisEvidence',
    'PhaseTransitionResult',
    'PhaseStateMachine',
]
