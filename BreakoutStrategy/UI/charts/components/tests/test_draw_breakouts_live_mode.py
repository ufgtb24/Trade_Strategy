"""Unit tests for MarkerComponent.draw_breakouts_live_mode (4-tier)."""
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from BreakoutStrategy.UI.charts.components.markers import MarkerComponent


@pytest.fixture
def axes_with_df():
    fig, ax = plt.subplots(figsize=(6, 4))
    df = pd.DataFrame({
        "open": [1.0, 1.1, 1.2, 1.3, 1.4],
        "high": [1.1, 1.2, 1.3, 1.4, 1.5],
        "low":  [0.9, 1.0, 1.1, 1.2, 1.3],
        "close":[1.05,1.15,1.25,1.35,1.45],
    })
    ax.plot(range(5), df["close"])
    ax.set_ylim(0.8, 1.6)
    yield ax, df
    plt.close(fig)


def _make_bo(index, broken_peak_ids):
    return SimpleNamespace(index=index, broken_peak_ids=broken_peak_ids, price=1.0)


_COLORS = {
    "bo_marker_current": "#1565C0",
    "bo_marker_visible": "#64B5F6",
    "bo_marker_filtered_out": "#9E9E9E",
    "breakout_marker": "#0000FF",   # legacy, kept for safety
    "breakout_text_bg": "#FFFFFF",
}


def _find_tier_scatter(ax, tier: str):
    for c in ax.collections:
        if getattr(c, "bo_tier", None) == tier:
            return c
    return None


def test_current_bo_drawn_in_current_group(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=2,
        visible_matched_indices={2},
        colors=_COLORS,
    )
    sc = _find_tier_scatter(ax, "current")
    assert sc is not None
    face = sc.get_facecolor()
    assert face[0][0] == pytest.approx(0x15 / 255, abs=0.01)
    assert face[0][1] == pytest.approx(0x65 / 255, abs=0.01)
    assert face[0][2] == pytest.approx(0xC0 / 255, abs=0.01)


def test_visible_matched_drawn_in_visible_group(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices={2, 100},
        colors=_COLORS,
    )
    sc = _find_tier_scatter(ax, "visible")
    assert sc is not None
    assert _find_tier_scatter(ax, "current") is None


def test_filtered_out_drawn_in_filtered_group(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices=set(),
        filtered_out_matched_indices={2},
        colors=_COLORS,
    )
    sc = _find_tier_scatter(ax, "filtered_out")
    assert sc is not None
    # 灰色 alpha 0.7
    face = sc.get_facecolor()
    assert face[0][3] == pytest.approx(0.7, abs=0.01)


def test_plain_drawn_hollow(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices={100},
        colors=_COLORS,
    )
    sc = _find_tier_scatter(ax, "plain")
    assert sc is not None
    assert len(sc.get_facecolor()) == 0   # facecolor="none" 返回空数组


def test_pickable_groups_have_picker_and_indices(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7]), _make_bo(3, [8])],
        current_bo_index=2,
        visible_matched_indices={2, 3},
        colors=_COLORS,
    )
    current = _find_tier_scatter(ax, "current")
    visible = _find_tier_scatter(ax, "visible")
    assert current.get_picker() is not None   # True / pickradius
    assert visible.get_picker() is not None
    assert current.bo_chart_indices == [2]
    assert visible.bo_chart_indices == [3]


def test_plain_group_has_no_picker(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [])],
        current_bo_index=100,
        visible_matched_indices={100},
        colors=_COLORS,
    )
    plain = _find_tier_scatter(ax, "plain")
    # matplotlib 的 picker=None → get_picker() 返回 None
    assert plain.get_picker() is None


def test_label_still_drawn(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [3, 5, 8])],
        current_bo_index=2,
        visible_matched_indices={2},
        colors=_COLORS,
    )
    texts = [t.get_text() for t in ax.texts]
    assert any("[3,5,8]" in t for t in texts)


def test_empty_noop(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [], current_bo_index=None,
        visible_matched_indices=set(),
        colors=_COLORS,
    )
    assert len(ax.collections) == 0
    assert len(ax.texts) == 0


def test_overlap_stacks_above_peak(axes_with_df):
    ax, df = axes_with_df
    bo_idx = 2
    fake_peak = SimpleNamespace(index=bo_idx, price=1.2)
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(bo_idx, [7])],
        current_bo_index=bo_idx,
        visible_matched_indices={bo_idx},
        peaks=[fake_peak],
        colors=_COLORS,
    )
    # price_range=0.8 → offset_unit=0.016；base=df.iloc[2]["high"]=1.3
    # overlap 分支 marker_y=1.3+0.016*4=1.364, label_y=1.3+0.016*2.2=1.3352
    offset = 0.8 * 0.02
    expected_marker_y = 1.3 + offset * 4.0
    sc = _find_tier_scatter(ax, "current")
    marker_y = sc.get_offsets()[0][1]
    assert marker_y == pytest.approx(expected_marker_y, abs=1e-6)


def test_all_tiers_populated_produces_four_scatters(axes_with_df):
    """当 4 种 tier 都有 BO 时，应产生 4 个独立的 scatter artist。"""
    ax, df = axes_with_df
    bos = [
        _make_bo(0, [1]),   # will be current
        _make_bo(1, [2]),   # visible
        _make_bo(2, [3]),   # filtered_out
        _make_bo(3, [4]),   # plain
    ]
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, bos,
        current_bo_index=0,
        visible_matched_indices={0, 1},   # includes current
        filtered_out_matched_indices={2},
        colors=_COLORS,
    )
    tiers = {getattr(c, "bo_tier", None) for c in ax.collections}
    assert tiers == {"current", "visible", "filtered_out", "plain"}
    assert len(ax.collections) == 4
