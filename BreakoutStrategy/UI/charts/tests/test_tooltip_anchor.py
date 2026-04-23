"""Unit tests for compute_tooltip_anchor."""
import pytest

from BreakoutStrategy.UI.charts.tooltip_anchor import compute_tooltip_anchor


FIG = (1600, 900)
TIP = (400, 350)


def test_center_no_flip():
    ox, oy, ha, va = compute_tooltip_anchor(
        cursor_px=(800, 400), fig_size=FIG, est_tooltip_size=TIP
    )
    assert (ox, oy, ha, va) == (40, 40, "left", "bottom")


def test_right_edge_flips_x():
    # cursor.x + tw + margin = 1300 + 400 + 10 = 1710 > 1600 → flip_x
    ox, oy, ha, va = compute_tooltip_anchor(
        cursor_px=(1300, 400), fig_size=FIG, est_tooltip_size=TIP
    )
    assert (ox, oy, ha, va) == (-40, 40, "right", "bottom")


def test_top_edge_flips_y():
    # cursor.y + th + margin = 700 + 350 + 10 = 1060 > 900 → flip_y
    ox, oy, ha, va = compute_tooltip_anchor(
        cursor_px=(400, 700), fig_size=FIG, est_tooltip_size=TIP
    )
    assert (ox, oy, ha, va) == (40, -40, "left", "top")


def test_top_right_corner_flips_both():
    ox, oy, ha, va = compute_tooltip_anchor(
        cursor_px=(1400, 800), fig_size=FIG, est_tooltip_size=TIP
    )
    assert (ox, oy, ha, va) == (-40, -40, "right", "top")


def test_edge_margin_boundary():
    # Just below trigger: cx + tw + margin == fw → not > → no flip
    ox, _, ha, _ = compute_tooltip_anchor(
        cursor_px=(1190, 100), fig_size=FIG, est_tooltip_size=TIP
    )
    assert (ox, ha) == (40, "left")

    # One pixel over: flips
    ox, _, ha, _ = compute_tooltip_anchor(
        cursor_px=(1191, 100), fig_size=FIG, est_tooltip_size=TIP
    )
    assert (ox, ha) == (-40, "right")
