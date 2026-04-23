"""Tests for MatchList visible-items / bo-indices accessors."""
from datetime import date, timedelta

import pytest

from BreakoutStrategy.live.pipeline.results import MatchedBreakout


def _mb(symbol, bo_index, days_ago, price=5.0, score=0.0):
    today = date.today()
    return MatchedBreakout(
        symbol=symbol,
        breakout_date=(today - timedelta(days=days_ago)).isoformat(),
        breakout_price=price,
        factors={},
        sentiment_score=score,
        sentiment_category="analyzed",
        sentiment_summary=None,
        raw_breakout={"index": bo_index},
        raw_peaks=[],
        all_stock_breakouts=[],
        all_matched_bo_chart_indices=[bo_index],
    )


@pytest.fixture
def tk_root():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def test_get_visible_items_returns_filtered_subset(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    ml.set_items([
        _mb("AAPL", 10, days_ago=3),
        _mb("AAPL", 20, days_ago=30),   # 超出 default 2 weeks
        _mb("MSFT", 15, days_ago=5),
    ])
    visible = ml.get_visible_items()
    # default weeks=2 → cutoff=14 天前，30 天前的被过滤
    assert len(visible) == 2
    symbols = {it.symbol for it in visible}
    assert symbols == {"AAPL", "MSFT"}


def test_get_visible_bo_indices_same_symbol(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    ml.set_items([
        _mb("AAPL", 10, days_ago=3),
        _mb("AAPL", 20, days_ago=5),
        _mb("MSFT", 15, days_ago=5),
    ])
    assert ml.get_visible_bo_indices("AAPL") == {10, 20}
    assert ml.get_visible_bo_indices("MSFT") == {15}
    assert ml.get_visible_bo_indices("GOOG") == set()


def test_get_visible_bo_indices_excludes_filtered(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    ml.set_items([
        _mb("AAPL", 10, days_ago=3),
        _mb("AAPL", 99, days_ago=60),  # 被 date filter 过滤
    ])
    assert ml.get_visible_bo_indices("AAPL") == {10}
