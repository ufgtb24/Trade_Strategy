from __future__ import annotations

import dataclasses
import inspect
import math
from abc import ABC
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Iterator,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from path2 import config

if TYPE_CHECKING:
    # 仅供静态类型检查；见下方 Detector.on_gate 注释——不可在运行时真正 import,
    # 否则打破 core.py(地基层)不依赖 dag/(上层)的分层方向。
    from path2.dag.gate_failure import GateFailure


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
    """从下层数据 / 事件流产生上层 Event 的生产者。

    on_gate: optional hook · attempt 短路失败时 detector 调用它上报 GateFailure。
    默认 None(生产路径无开销);仅诊断层挂 collector 时才启用(Task 10-12 消费)。
    声明置于 TYPE_CHECKING 守卫内,只供静态类型检查、不进入运行时
    __annotations__ —— Python 3.12 下 runtime_checkable 的 isinstance 结构检查会把
    Protocol 里任何(哪怕只声明、带默认值的)属性都纳入必须项;若此处正常声明,
    所有现有 conforming class(未显式带 on_gate,如
    tests/path2/test_detector_protocol.py::Good)会被判定不再满足 Detector,
    造成回归。TYPE_CHECKING 守卫两全:类型检查器仍能看到 on_gate 契约,
    运行时 isinstance 行为不变。
    """
    if TYPE_CHECKING:
        on_gate: Optional[Callable[["GateFailure"], None]]

    def detect(self, source: Any) -> Iterator[Event]: ...
