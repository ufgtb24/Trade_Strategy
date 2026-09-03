"""path2 stdlib 便利层:走势-无关的 Detector 模板。

(旧 PatternDetector 引擎 Chain/Dag/Kof/Neg 已随理想架构 dag 引擎取代而移除;
此处仅保留 atoms 仍依赖的 BarwiseDetector。)
"""
from path2.stdlib.templates import BarwiseDetector
from path2.stdlib.app import make_app

__all__ = ["BarwiseDetector", "make_app"]
