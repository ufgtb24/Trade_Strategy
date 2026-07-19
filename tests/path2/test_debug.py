"""path2/debug.py 的 ContextVar current_symbol 单测(Sprint 1 Stage 1)。"""
from path2.debug import current_symbol, set_current_symbol


def test_default_none():
    assert current_symbol.get() is None


def test_set_and_get():
    set_current_symbol("DGNX")
    try:
        assert current_symbol.get() == "DGNX"
    finally:
        set_current_symbol(None)


def test_reset():
    set_current_symbol("DGNX")
    set_current_symbol(None)
    assert current_symbol.get() is None
