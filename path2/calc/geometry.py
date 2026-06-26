"""K 线几何比例:上影 / 下影 / 实体占比。

零除守卫用 `rng <= 0` 而非 spec §3.6 的 `h == l → 0`:更 defensive,
顺带挡住理论上不该出现的 h < l(坏数据)。语义对正常 K 线一致。
"""
from __future__ import annotations


def upper_shadow_ratio(o: float, h: float, l: float, c: float) -> float:
    """(h - max(o, c)) / (h - l);rng <= 0 → 0(零除守卫)。"""
    rng = h - l
    if rng <= 0:
        return 0.0
    return (h - max(o, c)) / rng


def lower_shadow_ratio(o: float, h: float, l: float, c: float) -> float:
    """(min(o, c) - l) / (h - l);rng <= 0 → 0(零除守卫)。"""
    rng = h - l
    if rng <= 0:
        return 0.0
    return (min(o, c) - l) / rng


def body_pct(o: float, h: float, l: float, c: float) -> float:
    """|c - o| / (h - l);rng <= 0 → 0(零除守卫)。"""
    rng = h - l
    if rng <= 0:
        return 0.0
    return abs(c - o) / rng
