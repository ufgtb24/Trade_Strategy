"""Unit tests for compute_marker_offsets_pt helper in UI/styles.py."""
import pytest

from BreakoutStrategy.UI.styles import MARKER_STACK_GAPS_PT, compute_marker_offsets_pt


def test_single_layer_triangle():
    assert compute_marker_offsets_pt(["triangle"]) == {"triangle": 14}


def test_dev_full_stack():
    offsets = compute_marker_offsets_pt(
        ["triangle", "peak_id", "bo_label", "bo_score"]
    )
    assert offsets == {
        "triangle": 14,
        "peak_id": 28,
        "bo_label": 38,
        "bo_score": 68,
    }


def test_live_stack_with_peak():
    assert compute_marker_offsets_pt(
        ["triangle", "peak_id", "bo_label"]
    ) == {"triangle": 14, "peak_id": 28, "bo_label": 38}


def test_pure_bo_stack():
    assert compute_marker_offsets_pt(["bo_label", "bo_score"]) == {
        "bo_label": 10,
        "bo_score": 40,
    }


def test_unknown_layer_raises():
    with pytest.raises(KeyError):
        compute_marker_offsets_pt(["unknown_layer"])


def test_dict_keys_match_expected():
    assert set(MARKER_STACK_GAPS_PT.keys()) == {
        "triangle", "peak_id", "bo_label", "bo_score",
    }


def test_bo_label_tier_style_has_three_tiers():
    from BreakoutStrategy.UI.styles import BO_LABEL_TIER_STYLE
    assert set(BO_LABEL_TIER_STYLE.keys()) == {"current", "matched", "plain"}


def test_bo_label_tier_style_colors_follow_spec():
    from BreakoutStrategy.UI.styles import BO_LABEL_TIER_STYLE, CHART_COLORS
    current_color = CHART_COLORS["bo_marker_current"]

    assert BO_LABEL_TIER_STYLE["current"]["bg"] == current_color
    assert BO_LABEL_TIER_STYLE["current"]["fg"] == "#FFFFFF"

    # matched 统一灰底黑字，不再使用深蓝
    assert BO_LABEL_TIER_STYLE["matched"]["bg"] == "#BFBFBF"
    assert BO_LABEL_TIER_STYLE["matched"]["fg"] == "#000000"

    assert BO_LABEL_TIER_STYLE["plain"]["bg"] == CHART_COLORS["breakout_text_bg"]
    assert BO_LABEL_TIER_STYLE["plain"]["fg"] == current_color


import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from types import SimpleNamespace

from BreakoutStrategy.UI.charts.components.markers import MarkerComponent


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


def _find_annotation_by_text(ax, text_substring: str):
    for t in ax.texts:
        if text_substring in t.get_text():
            return t
    return None


def test_draw_peaks_without_id_has_no_text(axes_with_df):
    ax, df = axes_with_df
    peak = SimpleNamespace(index=2, price=1.2, id=None)
    MarkerComponent.draw_peaks(ax, df, [peak])
    assert len(ax.texts) == 0


def test_draw_peaks_with_id_annotation_at_28pt(axes_with_df):
    ax, df = axes_with_df
    peak = SimpleNamespace(index=2, price=1.2, id=7)
    MarkerComponent.draw_peaks(ax, df, [peak])
    ann = _find_annotation_by_text(ax, "7")
    assert ann is not None
    # xytext y should equal triangle(14) + peak_id(14) = 28
    assert ann.xyann[1] == pytest.approx(28)


def test_draw_breakouts_pure_bo_offsets(axes_with_df):
    ax, df = axes_with_df
    bo = SimpleNamespace(index=2, price=1.2, broken_peak_ids=[5], quality_score=80.0)
    MarkerComponent.draw_breakouts(ax, df, [bo], peaks=[])
    label = _find_annotation_by_text(ax, "[5]")
    assert label is not None
    assert label.xyann[1] == pytest.approx(10)   # bo_label gap=10, no layers below
    score = _find_annotation_by_text(ax, "80")
    assert score is not None
    assert score.xyann[1] == pytest.approx(40)   # bo_label(10) + bo_score(30)


def test_draw_breakouts_peak_overlap_offsets(axes_with_df):
    ax, df = axes_with_df
    bo = SimpleNamespace(index=2, price=1.2, broken_peak_ids=[5], quality_score=80.0)
    peak = SimpleNamespace(index=2, price=1.2, id=3)
    MarkerComponent.draw_breakouts(ax, df, [bo], peaks=[peak])
    label = _find_annotation_by_text(ax, "[5]")
    assert label is not None
    # triangle(14) + peak_id(14) + bo_label(10) = 38
    assert label.xyann[1] == pytest.approx(38)
    score = _find_annotation_by_text(ax, "80")
    assert score is not None
    # 38 + bo_score(30) = 68
    assert score.xyann[1] == pytest.approx(68)


def test_draw_breakouts_peak_without_id_overlap_offsets(axes_with_df):
    ax, df = axes_with_df
    bo = SimpleNamespace(index=2, price=1.2, broken_peak_ids=[5], quality_score=80.0)
    peak_no_id = SimpleNamespace(index=2, price=1.2, id=None)
    MarkerComponent.draw_breakouts(ax, df, [bo], peaks=[peak_no_id])
    label = _find_annotation_by_text(ax, "[5]")
    # triangle(14) + bo_label(10) = 24 (peak_id layer skipped because id is None)
    assert label.xyann[1] == pytest.approx(24)


def test_draw_breakouts_score_without_broken_peak_ids_takes_bo_label_slot(axes_with_df):
    """Edge case: score present but broken_peak_ids absent.

    Per draw_breakouts implementation, when `has_score and not has_broken_ids`,
    the score annotation is placed at where `bo_label` would be (via
    tmp_layers hack). For a pure BO (no peak), that slot is 10pt above High.
    """
    ax, df = axes_with_df
    bo = SimpleNamespace(index=2, price=1.2, broken_peak_ids=None, quality_score=80.0)
    MarkerComponent.draw_breakouts(ax, df, [bo], peaks=[])
    score = _find_annotation_by_text(ax, "80")
    assert score is not None
    # Score takes bo_label's slot (10pt) because no label to stack above.
    assert score.xyann[1] == pytest.approx(10)
    # No label annotation because broken_peak_ids is None.
    assert _find_annotation_by_text(ax, "[") is None
