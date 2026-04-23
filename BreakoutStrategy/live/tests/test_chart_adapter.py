"""Unit tests for chart_adapter.adapt_peaks split-by-is_superseded contract."""
from BreakoutStrategy.live.chart_adapter import adapt_peaks


def test_adapt_peaks_returns_three_values():
    """adapt_peaks 返回值必须是 (active_peaks, superseded_peaks, by_id) 三元组。"""
    result = adapt_peaks([])
    assert len(result) == 3


def test_adapt_peaks_empty_input():
    """空输入 → 三个空列表/dict。"""
    active, superseded, by_id = adapt_peaks([])
    assert active == []
    assert superseded == []
    assert by_id == {}


def test_adapt_peaks_splits_by_is_superseded_flag():
    """按 is_superseded 字段拆分：True 进 superseded；False/缺省 进 active。"""
    raw = [
        {"index": 10, "id": 1, "price": 1.5, "is_superseded": False},
        {"index": 20, "id": 2, "price": 1.8, "is_superseded": True},
        {"index": 30, "id": 3, "price": 2.0, "is_superseded": False},
        {"index": 40, "id": 4, "price": 1.9, "is_superseded": True},
    ]
    active, superseded, by_id = adapt_peaks(raw)

    assert [p.id for p in active] == [1, 3]
    assert [p.id for p in superseded] == [2, 4]
    # by_id 覆盖所有 peak（active + superseded）
    assert set(by_id.keys()) == {1, 2, 3, 4}


def test_adapt_peaks_missing_is_superseded_treated_as_active():
    """is_superseded 字段缺省（向前兼容旧 scanner 输出）→ 视为 active。"""
    raw = [
        {"index": 10, "id": 1, "price": 1.5},  # 无 is_superseded 字段
    ]
    active, superseded, by_id = adapt_peaks(raw)

    assert len(active) == 1
    assert active[0].id == 1
    assert superseded == []


def test_adapt_peaks_by_id_includes_both_active_and_superseded():
    """by_id 必须能反查到所有 peak（breakout.broken_peak_ids 可能指向任一类）。"""
    raw = [
        {"index": 10, "id": 7, "price": 1.5, "is_superseded": False},
        {"index": 20, "id": 8, "price": 1.8, "is_superseded": True},
    ]
    _, _, by_id = adapt_peaks(raw)
    assert by_id[7].price == 1.5
    assert by_id[8].price == 1.8
