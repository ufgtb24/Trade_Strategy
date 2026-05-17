"""Path 2 stdlib:消费 TemporalEdge 声明的标准 PatternDetector +
日常便利层(Detector 模板 / id 便利)。

用户只写声明(edges + 每标签一条事件流),stdlib 跑最优实现;
BarwiseDetector 提供逐 bar 单点扫描模板,span_id 提供 id 便利。
"""
from path2.stdlib._ids import span_id
from path2.stdlib.detectors import Chain, Dag, Kof, Neg
from path2.stdlib.pattern_match import PatternMatch
from path2.stdlib.templates import BarwiseDetector

__all__ = ["Chain", "Dag", "Kof", "Neg", "PatternMatch", "BarwiseDetector", "span_id"]
