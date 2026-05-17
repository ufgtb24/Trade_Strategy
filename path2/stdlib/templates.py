"""stdlib Detector 模板(spec §3）。

BarwiseDetector:逐 bar 单点扫描模板。模板拥有扫描主循环 + emit
抽象契约;用户子类只实现领域判据。模板对 i 零领域假设(lookback
由子类在 emit 内 return None 自管),不做任何跨事件校验(end_idx
升序 / event_id 单 run 唯一全部留给协议层 run())。
"""
from __future__ import annotations

import abc
from typing import Iterator, Optional

import pandas as pd

from path2.core import Event


class BarwiseDetector(abc.ABC):
    """逐 bar 单点扫描模板。run(MyDet(), df) → detect(df) → 逐 i 调 emit。"""

    @abc.abstractmethod
    def emit(self, df: pd.DataFrame, i: int) -> Optional[Event]:
        """检视第 i 根 bar(0 <= i < len(df))。命中返回用户自己的
        Event 子类实例,否则 None。lookback 由子类自管(不够时 return
        None);event_id 由子类自行生成(可用 path2.span_id)。"""
        ...

    def detect(self, df: pd.DataFrame) -> Iterator[Event]:
        for i in range(len(df)):
            ev = self.emit(df, i)
            if ev is not None:
                yield ev
