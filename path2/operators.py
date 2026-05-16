from __future__ import annotations

import operator as _op
from typing import Any as _Any
from typing import Callable, Iterable, Optional

from path2.core import Event

_OPS = {
    ">=": _op.ge,
    ">": _op.gt,
    "<=": _op.le,
    "<": _op.lt,
    "==": _op.eq,
    "!=": _op.ne,
}


def Before(
    anchor: Event,
    predicate: Callable,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
    """anchor 之前 window 个 bar 内某时刻满足 predicate。
    窗口 [anchor.start_idx - window, anchor.start_idx)(不含 anchor 自身)。
    """
    if window <= 0:
        return False
    if stream is None:
        lo = max(0, anchor.start_idx - window)
        return any(predicate(i) for i in range(lo, anchor.start_idx))
    return any(
        anchor.start_idx - window <= e.end_idx < anchor.start_idx and predicate(e)
        for e in stream
    )


def At(anchor: Event, predicate: Callable[[Event], bool]) -> bool:
    """anchor 自身满足 predicate。等价于 predicate(anchor)。"""
    return predicate(anchor)


def After(
    anchor: Event,
    predicate: Callable,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
    """anchor 之后 window 个 bar 内某时刻满足 predicate。
    窗口 (anchor.end_idx, anchor.end_idx + window](不含 anchor 自身)。
    """
    if window <= 0:
        return False
    if stream is None:
        return any(
            predicate(i)
            for i in range(anchor.end_idx + 1, anchor.end_idx + window + 1)
        )
    return any(
        anchor.end_idx < e.end_idx <= anchor.end_idx + window and predicate(e)
        for e in stream
    )


def Over(
    events: Iterable[Event],
    attribute: str,
    reduce: Callable[[Iterable], _Any],
    op: str,
    thr: _Any,
) -> bool:
    """对 events 取 attribute,reduce 聚合后用 op 与 thr 比较。"""
    if op not in _OPS:
        raise ValueError(f"未知 op: {op!r}")
    agg = reduce([getattr(e, attribute) for e in events])
    return _OPS[op](agg, thr)


def Any(events: Iterable[Event], predicate: Callable[[Event], bool]) -> bool:
    """容器中至少一个事件满足 predicate。"""
    return any(predicate(e) for e in events)
