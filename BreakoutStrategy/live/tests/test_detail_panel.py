"""Per-Factor Gating Spec 2: live detail_panel None handling."""
from BreakoutStrategy.live.panels.detail_panel import _fmt


def test_fmt_none_returns_na():
    """_fmt(None) 返回 'N/A'，不 TypeError。"""
    assert _fmt(None) == "N/A"


def test_fmt_int_returns_int_str():
    """_fmt(5) 返回 '5'（整数分支保留）。"""
    assert _fmt(5) == "5"


def test_fmt_float_returns_2dp():
    """_fmt(3.14159) 返回 '3.14'（浮点 2 位小数）。"""
    assert _fmt(3.14159) == "3.14"
