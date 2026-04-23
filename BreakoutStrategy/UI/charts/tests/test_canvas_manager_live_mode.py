"""Dispatch-level test: canvas_manager.update_chart routes BO drawing to the
right method based on display_options['live_mode'].
"""
from types import SimpleNamespace
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")
import pandas as pd
import pytest
import tkinter as tk

from BreakoutStrategy.UI.charts.canvas_manager import ChartCanvasManager


@pytest.fixture
def tk_container():
    root = tk.Tk()
    root.withdraw()
    frame = tk.Frame(root)
    yield frame
    root.destroy()


@pytest.fixture
def minimal_df():
    idx = pd.date_range("2025-01-01", periods=30, freq="D")
    return pd.DataFrame({
        "open": [1.0] * 30, "high": [1.1] * 30,
        "low": [0.9] * 30, "close": [1.0] * 30,
        "volume": [1000] * 30,
    }, index=idx)


def _fake_bo(idx):
    return SimpleNamespace(
        index=idx,
        broken_peak_ids=[1],
        price=1.0,
        quality_score=100.0,
        num_peaks_broken=1,  # draw_resistance_zones 的 guard：<= 1 时直接 return
    )


def test_live_mode_true_calls_live_mode_draw(tk_container, minimal_df):
    mgr = ChartCanvasManager(tk_container)
    with patch.object(
        mgr.marker, "draw_breakouts_live_mode"
    ) as mock_live, patch.object(
        mgr.marker, "draw_breakouts"
    ) as mock_dev:
        mgr.update_chart(
            df=minimal_df,
            breakouts=[_fake_bo(10)],
            active_peaks=[], superseded_peaks=[],
            symbol="TEST",
            display_options={
                "live_mode": True,
                "current_bo_index": 10,
                "visible_matched_indices": {10},
            },
        )
        assert mock_live.called, "live_mode=True 应调 draw_breakouts_live_mode"
        assert not mock_dev.called, "live_mode=True 不应调旧 draw_breakouts"


def test_live_mode_false_calls_original_draw(tk_container, minimal_df):
    mgr = ChartCanvasManager(tk_container)
    with patch.object(
        mgr.marker, "draw_breakouts_live_mode"
    ) as mock_live, patch.object(
        mgr.marker, "draw_breakouts"
    ) as mock_dev:
        mgr.update_chart(
            df=minimal_df,
            breakouts=[_fake_bo(10)],
            active_peaks=[], superseded_peaks=[],
            symbol="TEST",
            display_options={
                "show_bo_score": True,
                "show_superseded_peaks": True,
            },  # Dev UI 的典型 display_options，无 live_mode
        )
        assert not mock_live.called, "live_mode 缺失时不应调 draw_breakouts_live_mode"
        assert mock_dev.called, "应调旧 draw_breakouts 保持 Dev UI 行为"


def test_live_mode_missing_equals_false(tk_container, minimal_df):
    """display_options={}（Live UI 当前默认）等价于 live_mode=False → 走旧 draw_breakouts。

    注：这是过渡状态保护测试；Task 7 会让 Live UI 显式传 live_mode=True。
    """
    mgr = ChartCanvasManager(tk_container)
    with patch.object(
        mgr.marker, "draw_breakouts_live_mode"
    ) as mock_live, patch.object(
        mgr.marker, "draw_breakouts"
    ) as mock_dev:
        mgr.update_chart(
            df=minimal_df,
            breakouts=[_fake_bo(10)],
            active_peaks=[], superseded_peaks=[],
            symbol="TEST",
            display_options={},
        )
        assert not mock_live.called
        assert mock_dev.called


def test_live_mode_passes_new_display_options_to_marker(tk_container, minimal_df):
    mgr = ChartCanvasManager(tk_container)
    captured = {}
    def fake_live(ax, df, breakouts, **kwargs):
        captured.update(kwargs)
    with patch.object(mgr.marker, "draw_breakouts_live_mode", side_effect=fake_live):
        mgr.update_chart(
            df=minimal_df,
            breakouts=[_fake_bo(10)],
            active_peaks=[], superseded_peaks=[],
            symbol="TEST",
            display_options={
                "live_mode": True,
                "current_bo_index": 10,
                "visible_matched_indices": {10, 15},
                "filtered_out_matched_indices": {20},
                "on_bo_picked": lambda _i: None,
            },
        )
    assert captured["current_bo_index"] == 10
    assert captured["visible_matched_indices"] == {10, 15}
    assert captured["filtered_out_matched_indices"] == {20}


def test_live_mode_pick_event_invokes_on_bo_picked(tk_container, minimal_df):
    """模拟 pick_event 触发，验证回调拿到正确的 bo_chart_idx。"""
    from types import SimpleNamespace
    mgr = ChartCanvasManager(tk_container)
    received = []
    mgr.update_chart(
        df=minimal_df,
        breakouts=[_fake_bo(10), _fake_bo(12)],
        active_peaks=[], superseded_peaks=[],
        symbol="TEST",
        display_options={
            "live_mode": True,
            "current_bo_index": 10,
            "visible_matched_indices": {10, 12},
            "on_bo_picked": lambda i: received.append(i),
        },
    )
    # 找到某个可点击 annotation，伪造 pick_event
    target = None
    for t in mgr.fig.axes[0].texts:
        if getattr(t, "bo_tier", None) == "matched":
            target = t
            break
    assert target is not None
    fake_event = SimpleNamespace(artist=target)
    mgr._on_pick(fake_event)
    assert received == [target.bo_chart_idx]


def test_update_chart_signature_has_spec_parameter():
    import inspect
    sig = inspect.signature(ChartCanvasManager.update_chart)
    assert "spec" in sig.parameters, "update_chart missing 'spec' parameter"
