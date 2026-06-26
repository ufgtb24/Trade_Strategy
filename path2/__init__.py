"""path2 公开 API:独立多级事件表达框架。

协议地基(core/runner/config)+ go-forward 的 dag 引擎(见 path2.dag 子包)。
事件用 path2.atoms 的 Detector 产出;形态用 path2.dag 的 NodeSpec/类型化边/where 声明,
交 path2.dag.engine.analyze 匹配。详见 docs/path2/。
"""
from path2 import config
from path2.config import set_runtime_checks
from path2.core import Detector, Event
from path2.runner import run

__all__ = [
    "Event",
    "Detector",
    "run",
    "config",
    "set_runtime_checks",
]
