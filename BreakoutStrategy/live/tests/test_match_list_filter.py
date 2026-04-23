"""Tests for MatchList.get_date_cutoff and on_filter_changed callback."""
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def tk_root():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def test_get_date_cutoff_weeks_mode(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    ml.date_mode_var.set("weeks")
    ml.weeks_var.set(2)

    expected = datetime.now().date() - timedelta(days=14)
    assert ml.get_date_cutoff() == expected


def test_get_date_cutoff_days_mode(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    ml.date_mode_var.set("days")
    ml.days_var.set(7)

    expected = datetime.now().date() - timedelta(days=7)
    assert ml.get_date_cutoff() == expected


def test_on_filter_changed_fires_on_spinbox_change(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    calls: list[int] = []
    ml = MatchList(
        tk_root,
        on_row_selected=lambda _: None,
        scan_window_days=90,
        on_filter_changed=lambda: calls.append(1),
    )
    initial_count = len(calls)
    ml.weeks_var.set(3)
    assert len(calls) > initial_count
