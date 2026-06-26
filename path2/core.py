from __future__ import annotations

import dataclasses
import inspect
import math
from abc import ABC
from dataclasses import dataclass
from typing import Any, ClassVar, Iterator, Mapping, Protocol, Tuple, runtime_checkable

from path2 import config


_CLASS_ID_REGISTRY: dict[str, type] = {}


@dataclass(frozen=True)
class Event(ABC):
    """Path 2 中事件的基类。所有具体事件 row 类必须继承自 Event。

    子类契约:必须 @dataclass(frozen=True);若自定义 __post_init__,
    必须调用 super().__post_init__()。
    """

    event_id: str
    start_idx: int
    end_idx: int

    class_id: ClassVar[str] = ""   # 子类必须覆盖为非空全局唯一值(spec §2.1)
    is_point: ClassVar[bool] = False   # 子类点事件覆写为 True(start_idx==end_idx 几何承诺)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return
        cid = cls.__dict__.get("class_id")
        if not cid:
            raise TypeError(f"{cls.__name__} 必须声明非空 class_id")
        prev = _CLASS_ID_REGISTRY.get(cid)
        if prev is not None and prev is not cls:
            raise ValueError(f"class_id 冲突: {cid!r} 已被 {prev.__name__} 占用")
        _CLASS_ID_REGISTRY[cid] = cls

    def __post_init__(self) -> None:
        if not config.RUNTIME_CHECKS:
            return
        # frozen 一致性由 @dataclass 在装饰期原生强制(非 frozen 子类继承 frozen Event
        # 会在类定义时即抛 TypeError),无需在此自检。
        if not isinstance(self.start_idx, int) or not isinstance(self.end_idx, int):
            raise TypeError("start_idx/end_idx 必须是 int")
        if type(self.start_idx) is bool or type(self.end_idx) is bool:
            raise TypeError("start_idx/end_idx 不能是 bool(bool ⊂ int,语义错误)")
        if self.start_idx < 0 or self.start_idx > self.end_idx:
            raise ValueError(f"非法区间 [{self.start_idx},{self.end_idx}]")
        for f in dataclasses.fields(self):
            v = getattr(self, f.name)
            if isinstance(v, float) and math.isnan(v):
                raise ValueError(
                    f"字段 {f.name} 为 NaN — 违反'Row 落地=字段完成'"
                )

    def child_slots(self) -> Mapping[str, "Event | Tuple[Event, ...]"]:
        """构成本 event 的非冗余主 child 集（展平/遍历用，不含投影别名）。叶子返回 {}。"""
        return {}

    def child(self, name: str) -> "Event":
        """命名取单 child（含 first_*/last_* 投影别名）。用途：selector / edge 端点。"""
        raise KeyError(name)

    def children(self, name: str) -> "Tuple[Event, ...]":
        """命名取组 child。用途：selector 聚合。"""
        raise KeyError(name)

    @property
    def descendant_leaves(self) -> "Tuple[Event, ...]":
        """递归展平到无 child 的 atom。终止不变式：is_leaf(e) ⟺ child_slots(e)=={}。"""
        out = []
        for slot in self.child_slots().values():
            members = slot if isinstance(slot, tuple) else (slot,)
            for m in members:
                out.extend(m.descendant_leaves if m.child_slots() else (m,))
        return tuple(out)


@runtime_checkable
class Detector(Protocol):
    """从下层数据 / 事件流产生上层 Event 的生产者。"""

    def detect(self, source: Any) -> Iterator[Event]: ...
