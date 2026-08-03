"""path2 stdlib 便利层:走势-无关的 Detector 模板与 id 便利。

(旧 PatternDetector 引擎 Chain/Dag/Kof/Neg 已随理想架构 dag 引擎取代而移除;
此处仅保留 atoms 仍依赖的 BarwiseDetector 与 span_id。)
"""
from path2.stdlib._ids import span_id
from path2.stdlib.templates import BarwiseDetector
from path2.stdlib.app import make_app

__all__ = ["BarwiseDetector", "span_id", "make_app"]
