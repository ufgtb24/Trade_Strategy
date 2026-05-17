"""Path 2 stdlib:消费 TemporalEdge 声明的标准 PatternDetector。

用户只写声明(edges + 每标签一条事件流),stdlib 跑最优实现。
"""
from path2.stdlib.detectors import Chain, Dag, Kof, Neg
from path2.stdlib.pattern_match import PatternMatch

__all__ = ["Chain", "Dag", "Kof", "Neg", "PatternMatch"]
