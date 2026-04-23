"""Unit tests for LiveApp._update_selection state transition logic.

Tests the pure state-machine portion only; no Tk/chart wiring here.
"""
from BreakoutStrategy.live.pipeline.results import MatchedBreakout
from BreakoutStrategy.live.state import AppState


def _mb(symbol: str, date: str) -> MatchedBreakout:
    return MatchedBreakout(
        symbol=symbol,
        breakout_date=date,
        breakout_price=1.0,
        factors={},
        sentiment_score=None,
        sentiment_category="analyzed",
        sentiment_summary=None,
        raw_breakout={"index": 0},
        raw_peaks=[],
    )


class _StubApp:
    """Isolate _update_selection logic from LiveApp's Tk dependencies."""
    def __init__(self):
        self.state = AppState()
        self.rendered = 0

    def _render_selection(self):
        self.rendered += 1


def test_update_selection_to_none_clears_current():
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp()
    app.state.current_selected = _mb("AAPL", "2026-04-01")

    LiveApp._update_selection(app, None)

    assert app.state.current_selected is None
    assert app.rendered == 1


def test_update_selection_first_click_sets_current():
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp()
    item = _mb("AAPL", "2026-04-01")

    LiveApp._update_selection(app, item)

    assert app.state.current_selected is item
    assert app.rendered == 1


def test_update_selection_same_symbol_replaces_current():
    """同 symbol 切换时 current 直接被新值替换；无任何 previous 副作用。"""
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp()
    first = _mb("AAPL", "2026-04-01")
    second = _mb("AAPL", "2026-03-15")
    app.state.current_selected = first

    LiveApp._update_selection(app, second)

    assert app.state.current_selected is second


def test_update_selection_different_symbol_replaces_current():
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp()
    old = _mb("AAPL", "2026-04-01")
    new = _mb("MSFT", "2026-04-02")
    app.state.current_selected = old

    LiveApp._update_selection(app, new)

    assert app.state.current_selected is new


def test_update_selection_same_item_idempotent():
    """重复选中已 current 的 item 保持状态不变。"""
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp()
    item = _mb("AAPL", "2026-04-01")
    app.state.current_selected = item

    LiveApp._update_selection(app, item)

    assert app.state.current_selected is item
