from __future__ import annotations

import dataclasses
import math
from abc import ABC
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Protocol, runtime_checkable

from path2 import config


@dataclass(frozen=True)
class Event(ABC):
    """Path 2 中事件的基类。所有具体事件 row 类必须继承自 Event。

    子类契约:必须 @dataclass(frozen=True);若自定义 __post_init__,
    必须调用 super().__post_init__()。
    """

    event_id: str
    start_idx: int
    end_idx: int

    def __post_init__(self) -> None:
        if not config.RUNTIME_CHECKS:
            return
        # frozen 一致性由 @dataclass 在装饰期原生强制(非 frozen 子类继承 frozen Event
        # 会在类定义时即抛 TypeError),无需在此自检。
        if not isinstance(self.start_idx, int) or not isinstance(self.end_idx, int):
            raise TypeError("start_idx/end_idx 必须是 int")
        if self.start_idx < 0 or self.start_idx > self.end_idx:
            raise ValueError(f"非法区间 [{self.start_idx},{self.end_idx}]")
        for f in dataclasses.fields(self):
            v = getattr(self, f.name)
            if isinstance(v, float) and math.isnan(v):
                raise ValueError(
                    f"字段 {f.name} 为 NaN — 违反'Row 落地=字段完成'"
                )

    @property
    def features(self) -> Mapping[str, float]:
        """默认:所有 int/float 字段(排除 bool);子类可覆盖。"""
        return {
            f.name: getattr(self, f.name)
            for f in dataclasses.fields(self)
            if isinstance(getattr(self, f.name), (int, float))
            and not isinstance(getattr(self, f.name), bool)
        }


@dataclass(frozen=True)
class TemporalEdge:
    """显式声明两个事件之间的时间关系约束。

    gap = later.start_idx - earlier.end_idx
    """

    earlier: str
    later: str
    min_gap: int = 0
    max_gap: float = math.inf

    def __post_init__(self) -> None:
        if config.RUNTIME_CHECKS and (
            self.min_gap < 0 or self.min_gap > self.max_gap
        ):
            raise ValueError(f"非法 gap 区间 [{self.min_gap},{self.max_gap}]")
