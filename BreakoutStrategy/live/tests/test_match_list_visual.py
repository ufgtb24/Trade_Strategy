"""Tests for MatchList.apply_selection_visual 3-state row tagging + select_item + keyboard nav."""
from datetime import date, timedelta

import pytest

from BreakoutStrategy.live.pipeline.results import MatchedBreakout


def _mb(symbol, bo_index, days_ago=3):
    today = date.today()
    return MatchedBreakout(
        symbol=symbol,
        breakout_date=(today - timedelta(days=days_ago)).isoformat(),
        breakout_price=5.0,
        factors={},
        sentiment_score=0.0,
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


def _row_tags(ml, item):
    visible = ml.get_visible_items()
    for iid in ml.tree.get_children():
        idx = ml.tree.index(iid)
        if visible[idx] is item:
            return set(ml.tree.item(iid, "tags"))
    return None


def test_apply_visual_no_selection_no_state_tag(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    items = [_mb("AAPL", 10), _mb("AAPL", 20), _mb("MSFT", 15)]
    ml.set_items(items)
    ml.apply_selection_visual(current=None)

    for it in items:
        tags = _row_tags(ml, it)
        assert "row_current" not in tags
        assert "row_companion" not in tags


def test_apply_visual_current_marks_current_row(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    items = [a1, _mb("AAPL", 20, days_ago=5), _mb("MSFT", 15)]
    ml.set_items(items)
    ml.apply_selection_visual(current=a1)

    assert "row_current" in _row_tags(ml, a1)


def test_apply_visual_same_symbol_siblings_become_companion(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a2 = _mb("AAPL", 20, days_ago=5)
    m1 = _mb("MSFT", 15)
    ml.set_items([a1, a2, m1])
    ml.apply_selection_visual(current=a1)

    assert "row_current" in _row_tags(ml, a1)
    assert "row_companion" in _row_tags(ml, a2)
    # Different symbol stays plain
    t = _row_tags(ml, m1)
    assert "row_current" not in t
    assert "row_companion" not in t


def test_apply_visual_old_current_becomes_companion(tk_root):
    """切换到同 symbol 的另一行后，原 current 退回 companion（浅蓝），无特殊视觉。"""
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a2 = _mb("AAPL", 20, days_ago=5)
    a3 = _mb("AAPL", 30, days_ago=7)
    ml.set_items([a1, a2, a3])

    ml.apply_selection_visual(current=a1)
    assert "row_current" in _row_tags(ml, a1)

    ml.apply_selection_visual(current=a2)
    assert "row_current" in _row_tags(ml, a2)
    # a1 不再是 current；与 a2 同 symbol → 应为 companion
    t1 = _row_tags(ml, a1)
    assert "row_current" not in t1
    assert "row_companion" in t1
    # a3 也是同 symbol companion
    assert "row_companion" in _row_tags(ml, a3)


def test_apply_visual_current_drops_base_color_tag(tk_root):
    """current 行只挂 row_current，不带 sentiment 颜色 tag——保证白字 foreground
    不被 base 颜色压过（ttk.Treeview tag 优先级跨主题不可靠）。"""
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a1.sentiment_score = 0.5  # 否则会是 pos tag
    ml.set_items([a1])
    ml.apply_selection_visual(current=a1)

    tags = _row_tags(ml, a1)
    assert tags == {"row_current"}, f"current 行应只有 row_current tag，实际 {tags}"


def test_apply_visual_default_row_keeps_base_color_tag(tk_root):
    """非高亮行保留原 pos/neg/neu/na 颜色 tag。"""
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a1.sentiment_score = 0.5  # pos
    ml.set_items([a1])
    ml.apply_selection_visual(current=None)  # 无选中

    assert _row_tags(ml, a1) == {"pos"}


def test_apply_visual_rerender_cleans_stale_state(tk_root):
    """二次调用要能清掉上一次的 state tag。"""
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a2 = _mb("AAPL", 20, days_ago=5)
    ml.set_items([a1, a2])
    ml.apply_selection_visual(current=a1)
    assert _row_tags(ml, a1) == {"row_current"}

    ml.apply_selection_visual(current=a2)
    # a1 不应再带 row_current；它现在是 companion（且只挂 row_companion，无 base）
    assert _row_tags(ml, a1) == {"row_companion"}
    assert _row_tags(ml, a2) == {"row_current"}


def test_select_item_triggers_on_row_selected_once(tk_root):
    """select_item 触发一次回调且不因内部 selection 操作产生重入。"""
    from BreakoutStrategy.live.panels.match_list import MatchList

    calls = []
    ml = MatchList(tk_root, on_row_selected=lambda it: calls.append(it), scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a2 = _mb("AAPL", 20)
    ml.set_items([a1, a2])

    ml.select_item(a1)
    tk_root.update()   # flush <<TreeviewSelect>> events

    assert calls == [a1]


def test_select_item_scrolls_target_into_view(tk_root):
    """select_item 必须调 tree.see 让目标行可见。"""
    from BreakoutStrategy.live.panels.match_list import MatchList
    from unittest.mock import patch

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    ml.set_items([a1])

    with patch.object(ml.tree, "see") as mock_see:
        ml.select_item(a1)
        assert mock_see.called


def test_select_item_unknown_item_is_noop(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    calls = []
    ml = MatchList(tk_root, on_row_selected=lambda it: calls.append(it), scan_window_days=90)
    a1 = _mb("AAPL", 10)
    ml.set_items([a1])

    ghost = _mb("GOOG", 99)
    ml.select_item(ghost)  # 不在 visible 里
    tk_root.update()

    assert calls == []


def test_keyboard_down_selects_next_visible(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    calls = []
    ml = MatchList(tk_root, on_row_selected=lambda it: calls.append(it), scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a2 = _mb("AAPL", 20)
    a3 = _mb("MSFT", 30)
    ml.set_items([a1, a2, a3])

    visible = ml.get_visible_items()
    ml._handle_key_navigate(direction=1, current=None)
    assert calls[-1] is visible[0]

    ml._handle_key_navigate(direction=1, current=visible[0])
    assert calls[-1] is visible[1]


def test_keyboard_up_at_top_stays(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    calls = []
    ml = MatchList(tk_root, on_row_selected=lambda it: calls.append(it), scan_window_days=90)
    ml.set_items([_mb("AAPL", 10), _mb("AAPL", 20)])

    # 当前第 0 行，按 Up 应保持在第 0 行（不 wrap）
    first = ml.get_visible_items()[0]
    ml._handle_key_navigate(direction=-1, current=first)
    assert calls[-1] is first
