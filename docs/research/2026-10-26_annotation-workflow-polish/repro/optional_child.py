"""验证:复合事件里「可有可无」的子事件,三种 where 写法遇到「没有」时各怎样。不读行情。"""
from dataclasses import dataclass
from typing import Optional, Tuple

from path2.core import Event
from path2.dag import where as W


@dataclass(frozen=True)
class Leaf(Event):
    ratio: float = 0.0


@dataclass(frozen=True)
class Box(Event):
    """「横盘」复合事件:shrink 组可空;shrink_ratio 是 detector 预算的字段,没有缩量时为 None。"""
    shrink: Tuple[Leaf, ...] = ()
    shrink_ratio: Optional[float] = None

    def child_slots(self):
        return {"shrink": self.shrink}

    def child(self, name):
        if name == "first_shrink":
            return self.shrink[0]
        raise KeyError(name)

    def children(self, name):
        if name == "shrink":
            return self.shrink
        raise KeyError(name)


with_child = Box(start_idx=0, end_idx=10, confirm_idx=10,
                 shrink=(Leaf(start_idx=3, end_idx=5, confirm_idx=5, ratio=0.4),), shrink_ratio=0.4)
without = Box(start_idx=0, end_idx=10, confirm_idx=10)

cases = {
    "W.child('first_shrink', attr ratio<=0.5)": W.child("first_shrink", W.attr("ratio", "<=", 0.5)),
    "W.children('shrink', len>=1)": W.children("shrink", lambda seq: len(seq) >= 1),
    "W.attr('shrink_ratio', '<=', 0.5)": W.attr("shrink_ratio", "<=", 0.5),
    "W.any(attr shrink_ratio<=0.5, attr ... 另一支)": W.any(W.attr("shrink_ratio", "<=", 0.5),
                                                       W.attr("end_idx", ">=", 100)),
}
for name, fn in cases.items():
    for label, ev in (("有缩量", with_child), ("没缩量", without)):
        try:
            r = fn(ev)
        except Exception as ex:  # noqa: BLE001
            r = f"抛 {type(ex).__name__}: {ex}"
        print(f"{name:52s} {label}: {r}")
