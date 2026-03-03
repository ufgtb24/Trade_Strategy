"""信号检测器模块"""

from .base import SignalDetector
from .volume import HighVolumeDetector
from .big_yang import BigYangDetector
from .trough import Trough, TroughDetector
from .breakout import BreakoutSignalDetector
from .double_trough import DoubleTroughDetector

__all__ = [
    "SignalDetector",
    "HighVolumeDetector",
    "BigYangDetector",
    "Trough",
    "TroughDetector",
    "BreakoutSignalDetector",
    "DoubleTroughDetector",
]
