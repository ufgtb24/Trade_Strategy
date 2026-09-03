"""confirm_idx 协议测试 — 因果闸的地基。

依据 docs/research/2026-07-25_path2-app-optimization-workflow/11_path2_causal_gate_guide.md。
confirm_idx = 事件被确认成立的 bar；买点锚点 bar 必须 ≥ confirm_idx。
"""
from dataclasses import dataclass

import pytest

from path2.core import Event


@dataclass(frozen=True)
class _SpanEvent(Event):
    """测试用跨度事件（confirm_idx 可落在区间任意位置）。"""


# ---- 必填 ----

def test_confirm_idx_is_required():
    """confirm_idx 是必填字段，不传 → TypeError。"""
    with pytest.raises(TypeError):
        _SpanEvent(start_idx=5, end_idx=10)


# ---- 区间不变式 ----

def test_confirm_idx_below_start_raises():
    with pytest.raises(ValueError, match="confirm_idx"):
        _SpanEvent(start_idx=5, end_idx=10, confirm_idx=3)


def test_confirm_idx_above_end_raises():
    with pytest.raises(ValueError, match="confirm_idx"):
        _SpanEvent(start_idx=5, end_idx=10, confirm_idx=12)


def test_confirm_idx_at_start_ok():
    """confirm_idx == start_idx 合法（确认类，如 tb）。"""
    ev = _SpanEvent(start_idx=5, end_idx=10, confirm_idx=5)
    assert ev.confirm_idx == 5


def test_confirm_idx_at_end_ok():
    """confirm_idx == end_idx 合法（retrospective，如 burst/trend）。"""
    ev = _SpanEvent(start_idx=5, end_idx=10, confirm_idx=10)
    assert ev.confirm_idx == 10
