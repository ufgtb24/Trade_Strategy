"""Unit tests for _classify_bo BO style classifier (4-tier)."""
from BreakoutStrategy.UI.charts.components.markers import _classify_bo


def test_current_wins_over_everything():
    assert _classify_bo(5, current=5, visible={5, 7}, filtered_out={3}) == "current"


def test_visible_matched_not_current():
    assert _classify_bo(7, current=5, visible={5, 7}, filtered_out={3}) == "visible"


def test_filtered_out_matched_not_current():
    assert _classify_bo(3, current=5, visible={5, 7}, filtered_out={3}) == "filtered_out"


def test_plain_when_not_in_any_matched():
    assert _classify_bo(99, current=5, visible={5, 7}, filtered_out={3}) == "plain"


def test_no_current_selected_falls_to_visible_or_filtered():
    assert _classify_bo(7, current=None, visible={7}, filtered_out=set()) == "visible"
    assert _classify_bo(3, current=None, visible=set(), filtered_out={3}) == "filtered_out"
    assert _classify_bo(99, current=None, visible=set(), filtered_out=set()) == "plain"


def test_visible_takes_precedence_over_filtered_out():
    """sanity: 同一 idx 只会归一处，但若 visible 和 filtered_out 都含它（理论不该
    发生），visible 优先——它更能代表"列表里能看到"的状态。"""
    assert _classify_bo(7, current=None, visible={7}, filtered_out={7}) == "visible"
