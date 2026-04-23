"""Unit tests for MarkerComponent.draw_breakouts_live_mode (annotation-based)."""
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
import pandas as pd
import pytest

from BreakoutStrategy.UI.charts.components.markers import MarkerComponent
from BreakoutStrategy.UI.styles import BO_LABEL_TIER_STYLE, CHART_COLORS


@pytest.fixture
def axes_with_df():
    fig, ax = plt.subplots(figsize=(6, 4))
    df = pd.DataFrame({
        "open":  [1.0, 1.1, 1.2, 1.3, 1.4],
        "high":  [1.1, 1.2, 1.3, 1.4, 1.5],
        "low":   [0.9, 1.0, 1.1, 1.2, 1.3],
        "close": [1.05, 1.15, 1.25, 1.35, 1.45],
    })
    ax.plot(range(5), df["close"])
    ax.set_ylim(0.8, 1.6)
    yield ax, df
    plt.close(fig)


def _make_bo(index, broken_peak_ids):
    return SimpleNamespace(index=index, broken_peak_ids=broken_peak_ids, price=1.0)


def _find_tier_annotation(ax, tier: str):
    for t in ax.texts:
        if getattr(t, "bo_tier", None) == tier:
            return t
    return None


def _bbox_rgb(ann) -> tuple:
    """Return RGB tuple of annotation's bbox facecolor (ignoring alpha)."""
    face = ann.get_bbox_patch().get_facecolor()
    return tuple(face[:3])


def test_current_bo_drawn_as_annotation_with_tier_style(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=2,
        visible_matched_indices={2},
    )
    ann = _find_tier_annotation(ax, "current")
    assert ann is not None
    assert _bbox_rgb(ann) == pytest.approx(to_rgb(BO_LABEL_TIER_STYLE["current"]["bg"]), abs=0.01)
    assert ann.get_color() == BO_LABEL_TIER_STYLE["current"]["fg"]


def test_passed_filter_matched_drawn_as_matched_tier_pickable(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices={2, 100},
    )
    ann = _find_tier_annotation(ax, "matched")
    assert ann is not None
    assert _bbox_rgb(ann) == pytest.approx(to_rgb(BO_LABEL_TIER_STYLE["matched"]["bg"]), abs=0.01)
    assert ann.get_color() == BO_LABEL_TIER_STYLE["matched"]["fg"]
    assert ann.get_picker() is not None
    assert _find_tier_annotation(ax, "current") is None


def test_filtered_out_matched_drawn_as_matched_tier_not_pickable(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices=set(),
        filtered_out_matched_indices={2},
    )
    ann = _find_tier_annotation(ax, "matched")
    assert ann is not None
    # 视觉与 passed 变种一致：相同 bg/fg
    assert _bbox_rgb(ann) == pytest.approx(to_rgb(BO_LABEL_TIER_STYLE["matched"]["bg"]), abs=0.01)
    assert ann.get_color() == BO_LABEL_TIER_STYLE["matched"]["fg"]
    # 行为差异：无 picker
    assert ann.get_picker() is None


def test_passed_and_filtered_matched_share_same_visual(axes_with_df):
    """regression: 两个 matched 变种的 bbox/fg 必须完全一致，仅 pickability 不同。"""
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(1, [10]), _make_bo(2, [20])],
        current_bo_index=100,
        visible_matched_indices={1},
        filtered_out_matched_indices={2},
    )
    matched_anns = [t for t in ax.texts if getattr(t, "bo_tier", None) == "matched"]
    assert len(matched_anns) == 2
    bbox_colors = {_bbox_rgb(a) for a in matched_anns}
    fg_colors = {a.get_color() for a in matched_anns}
    assert len(bbox_colors) == 1  # 完全一致
    assert len(fg_colors) == 1


def test_plain_drawn_as_plain_tier(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices={100},
    )
    ann = _find_tier_annotation(ax, "plain")
    assert ann is not None
    assert _bbox_rgb(ann) == pytest.approx(to_rgb(BO_LABEL_TIER_STYLE["plain"]["bg"]), abs=0.01)


def test_border_color_uniform_across_tiers(axes_with_df):
    ax, df = axes_with_df
    bos = [
        _make_bo(0, [1]),  # current
        _make_bo(1, [2]),  # matched (passed filter)
        _make_bo(2, [3]),  # matched (filtered out)
        _make_bo(3, [4]),  # plain
    ]
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, bos,
        current_bo_index=0,
        visible_matched_indices={0, 1},
        filtered_out_matched_indices={2},
    )
    border_rgb = to_rgb(CHART_COLORS["bo_marker_current"])
    # 所有 4 个 annotation（含两个 matched 变种）都应共享同色边框
    assert len(ax.texts) == 4
    for ann in ax.texts:
        edge = ann.get_bbox_patch().get_edgecolor()
        assert tuple(edge[:3]) == pytest.approx(border_rgb, abs=0.01), ann.bo_tier


def test_pickable_boundary_between_current_matched_plain(axes_with_df):
    """Picker 拆分：current + matched(passed) 可点击；matched(filtered) + plain 不可点击。"""
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [
            _make_bo(2, [7]),  # current
            _make_bo(3, [8]),  # matched passed
            _make_bo(4, [9]),  # matched filtered_out
            _make_bo(5, [10]),  # plain
        ],
        current_bo_index=2,
        visible_matched_indices={2, 3},
        filtered_out_matched_indices={4},
    )
    by_idx = {t.bo_chart_idx: t for t in ax.texts}
    assert by_idx[2].get_picker() is not None  # current
    assert by_idx[3].get_picker() is not None  # matched passed
    assert by_idx[4].get_picker() is None      # matched filtered_out
    assert by_idx[5].get_picker() is None      # plain
    assert by_idx[2].bo_tier == "current"
    assert by_idx[3].bo_tier == "matched"
    assert by_idx[4].bo_tier == "matched"
    assert by_idx[5].bo_tier == "plain"


def test_plain_tier_has_no_picker(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices={100},
    )
    plain = _find_tier_annotation(ax, "plain")
    assert plain.get_picker() is None


def test_label_text_matches_broken_peak_ids(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [3, 5, 8])],
        current_bo_index=2,
        visible_matched_indices={2},
    )
    ann = _find_tier_annotation(ax, "current")
    assert ann.get_text() == "[3,5,8]"


def test_empty_breakouts_noop(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [],
        current_bo_index=None,
        visible_matched_indices=set(),
    )
    assert len(ax.texts) == 0
    assert len(ax.collections) == 0


def test_bo_without_broken_peak_ids_is_skipped(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [])],
        current_bo_index=2,
        visible_matched_indices={2},
    )
    # No broken_peak_ids -> no label to draw
    assert len(ax.texts) == 0


def test_bo_label_offset_matches_helper_with_peak(axes_with_df):
    ax, df = axes_with_df
    bo_idx = 2
    fake_peak = SimpleNamespace(index=bo_idx, price=1.2, id=5)
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(bo_idx, [7])],
        current_bo_index=bo_idx,
        visible_matched_indices={bo_idx},
        peaks=[fake_peak],
    )
    ann = _find_tier_annotation(ax, "current")
    # triangle(14) + peak_id(14) + bo_label(10) = 38
    assert ann.xyann[1] == pytest.approx(38)


def test_bo_label_offset_without_peak(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=2,
        visible_matched_indices={2},
    )
    ann = _find_tier_annotation(ax, "current")
    # bo_label only = 10
    assert ann.xyann[1] == pytest.approx(10)


def test_four_bos_produce_three_visual_tiers(axes_with_df):
    ax, df = axes_with_df
    bos = [
        _make_bo(0, [1]),  # current
        _make_bo(1, [2]),  # matched passed
        _make_bo(2, [3]),  # matched filtered_out
        _make_bo(3, [4]),  # plain
    ]
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, bos,
        current_bo_index=0,
        visible_matched_indices={0, 1},
        filtered_out_matched_indices={2},
    )
    assert len(ax.texts) == 4
    tiers = {getattr(t, "bo_tier", None) for t in ax.texts if getattr(t, "bo_tier", None)}
    assert tiers == {"current", "matched", "plain"}
    # No scatter artists
    assert len(ax.collections) == 0
