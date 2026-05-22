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
    predicate: Optional[Callable] = None,
    *,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
    """anchor 之前 window 个 bar 内某时刻满足 predicate。
    窗口 [anchor.start_idx - window, anchor.start_idx)(不含 anchor 自身)。
    predicate=None:仅判定窗内 stream 是否存在任一事件落窗(判据留在产
    stream 的 Detector)。predicate=None 且 stream=None 无流可查 → ValueError。
    stream=None 形态下 predicate 接收 bar 索引(int);stream 形态下接收 Event。
    """
    if window <= 0:
        return False
    if stream is None:
        if predicate is None:
            raise ValueError(
                "Before: predicate=None 需显式 stream(无流可作存在性检测)"
            )
        lo = max(0, anchor.start_idx - window)
        return any(predicate(i) for i in range(lo, anchor.start_idx))
    return any(
        anchor.start_idx - window <= e.end_idx < anchor.start_idx
        and (predicate is None or predicate(e))
        for e in stream
    )


def At(anchor: Event, predicate: Callable[[Event], bool]) -> bool:
    """anchor 自身满足 predicate。等价于 predicate(anchor)。"""
    return predicate(anchor)


def After(
    anchor: Event,
    predicate: Optional[Callable] = None,
    *,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
    """anchor 之后 window 个 bar 内某时刻满足 predicate。
    窗口 (anchor.end_idx, anchor.end_idx + window](不含 anchor 自身)。
    predicate=None:仅判定窗内 stream 是否存在任一事件落窗(判据留在产
    stream 的 Detector)。predicate=None 且 stream=None 无流可查 → ValueError。
    stream=None 形态下 predicate 接收 bar 索引(int);stream 形态下接收 Event。
    """
    if window <= 0:
        return False
    if stream is None:
        if predicate is None:
            raise ValueError(
                "After: predicate=None 需显式 stream(无流可作存在性检测)"
            )
        return any(
            predicate(i)
            for i in range(anchor.end_idx + 1, anchor.end_idx + window + 1)
        )
    return any(
        anchor.end_idx < e.end_idx <= anchor.end_idx + window
        and (predicate is None or predicate(e))
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


_OVERLAP_MODES = {
    "contains",
    "within",
    "overlapped_front",
    "overlapped_back",
    "equals",
}


def _overlaps_one(a: Event, e: Event, mode: str) -> bool:
    """单个 mode 下 e 是否与 a 成该区间关系(A=a 锚点,B=e)。"""
    if mode == "contains":            # A 包含 B
        return a.start_idx <= e.start_idx and e.end_idx <= a.end_idx
    if mode == "within":              # A 属于 B
        return e.start_idx <= a.start_idx and a.end_idx <= e.end_idx
    if mode == "overlapped_front":    # A 前端被叠:B 从前方探入
        return e.start_idx < a.start_idx and a.start_idx < e.end_idx < a.end_idx
    if mode == "overlapped_back":     # A 后端被叠:B 从 A 内延伸到后方
        return a.start_idx < e.start_idx < a.end_idx and a.end_idx < e.end_idx
    # mode == "equals":同段
    return e.start_idx == a.start_idx and e.end_idx == a.end_idx


def Overlaps(
    anchor: Event,
    mode: str | Iterable[str],
    predicate: Optional[Callable] = None,
    *,
    stream: Iterable[Event],
) -> bool:
    """stream 中是否存在与 anchor 成指定区间关系的事件(宽义 overlap=任意相交)。

    mode:单个 mode 字符串或一组(set/list),任一命中即 True。5 种(A=anchor,B=事件):
      "contains"          A 包含 B: a.start <= e.start and e.end <= a.end
      "within"            A 属于 B: e.start <= a.start and a.end <= e.end
      "overlapped_front"  A 前端被叠: e.start < a.start and a.start < e.end < a.end
      "overlapped_back"   A 后端被叠: a.start < e.start < a.end and a.end < e.end
      "equals"            同段: e.start == a.start and e.end == a.end
    包含用 <=(共享端点归包含,A==B 同时命中 contains/within/equals);重叠要真交叠
    (meets 单点相接不命中)。predicate 给出则与关系判定 AND。stream 必填(区间关系
    对裸 bar 索引无意义,故无 stream=None 索引形态)。
    """
    modes = {mode} if isinstance(mode, str) else set(mode)
    if not modes:
        raise ValueError("Overlaps: mode 不能为空")
    unknown = modes - _OVERLAP_MODES
    if unknown:
        raise ValueError(
            f"Overlaps: 未知 mode {unknown}; 合法值 {sorted(_OVERLAP_MODES)}"
        )
    return any(
        any(_overlaps_one(anchor, e, m) for m in modes)
        and (predicate is None or predicate(e))
        for e in stream
    )
