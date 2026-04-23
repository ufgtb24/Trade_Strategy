"""Unit tests for _classify_bo BO style classifier (3-tier visual + pickable flag)."""
from BreakoutStrategy.UI.charts.components.markers import _classify_bo


def test_current_wins_over_everything():
    assert _classify_bo(5, current=5, visible={5, 7}, filtered_out={3}) == ("current", True)


def test_passed_filter_matched_is_pickable():
    assert _classify_bo(7, current=5, visible={5, 7}, filtered_out={3}) == ("matched", True)


def test_filtered_out_matched_is_not_pickable():
    assert _classify_bo(3, current=5, visible={5, 7}, filtered_out={3}) == ("matched", False)


def test_plain_when_not_in_any_matched():
    assert _classify_bo(99, current=5, visible={5, 7}, filtered_out={3}) == ("plain", False)


def test_no_current_selected_falls_to_matched_or_plain():
    assert _classify_bo(7, current=None, visible={7}, filtered_out=set()) == ("matched", True)
    assert _classify_bo(3, current=None, visible=set(), filtered_out={3}) == ("matched", False)
    assert _classify_bo(99, current=None, visible=set(), filtered_out=set()) == ("plain", False)


def test_visible_takes_precedence_over_filtered_out():
    """同一 idx 若同时出现在 visible 和 filtered_out（理论不该发生），visible 优先
    —— pickable=True 胜出。"""
    assert _classify_bo(7, current=None, visible={7}, filtered_out={7}) == ("matched", True)
