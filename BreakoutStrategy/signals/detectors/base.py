"""
信号检测器基类

所有具体检测器都继承此基类，实现 detect 方法。
"""

from abc import ABC, abstractmethod
from typing import List

import pandas as pd

from ..models import AbsoluteSignal


class SignalDetector(ABC):
    """
    信号检测器抽象基类

    子类必须实现 detect 方法，扫描 DataFrame 并返回检测到的信号列表。
    """

    @abstractmethod
    def detect(self, df: pd.DataFrame, symbol: str) -> List[AbsoluteSignal]:
        """
        检测信号

        Args:
            df: OHLCV 数据，索引为日期
            symbol: 股票代码

        Returns:
            检测到的信号列表
        """
        pass
