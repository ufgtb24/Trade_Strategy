"""Tests for LiveApp._on_filter_changed current-selected invalidation."""
from types import SimpleNamespace

from BreakoutStrategy.live.pipeline.results import MatchedBreakout
from BreakoutStrategy.live.state import AppState


def _mb(symbol, date, bo_index=0):
    return MatchedBreakout(
        symbol=symbol,
        breakout_date=date,
        breakout_price=1.0,
        factors={},
        sentiment_score=None,
        sentiment_category="analyzed",
        sentiment_summary=None,
        raw_breakout={"index": bo_index},
        raw_peaks=[],
    )


class _StubMatchList:
    def __init__(self, visible):
        self._visible = list(visible)

    def get_visible_items(self):
        return list(self._visible)

    def get_date_cutoff(self):
        from datetime import date
        return date.today()


class _StubApp:
    """Reuse enough of LiveApp for _on_filter_changed."""
    def __init__(self, visible):
        self.state = AppState()
        self.match_list = _StubMatchList(visible)
        self.chart = SimpleNamespace(update_filter_range=lambda *_a, **_k: None)
        self.detail_panel = SimpleNamespace(update_item=lambda *_a, **_k: None)
        self.rendered = 0

    def _render_selection(self):
        self.rendered += 1

    def _update_selection(self, new):
        # Mirror real logic (no Tk)
        self.state.current_selected = new
        self._render_selection()


def test_filter_changed_keeps_current_when_still_visible():
    from BreakoutStrategy.live.app import LiveApp
    a = _mb("AAPL", "2026-04-01")
    app = _StubApp(visible=[a])
    app.state.current_selected = a

    LiveApp._on_filter_changed(app)

    assert app.state.current_selected is a
    assert app.rendered >= 1


def test_filter_changed_clears_current_when_filtered_out():
    from BreakoutStrategy.live.app import LiveApp
    a = _mb("AAPL", "2026-04-01")
    app = _StubApp(visible=[])  # a 被过滤掉
    app.state.current_selected = a

    LiveApp._on_filter_changed(app)

    assert app.state.current_selected is None


def test_filter_changed_noop_when_nothing_selected():
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp(visible=[])

    LiveApp._on_filter_changed(app)

    assert app.state.current_selected is None
