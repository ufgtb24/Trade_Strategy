"""Unit tests for compute_left_idx."""
from datetime import date

import pandas as pd


def test_left_idx_cutoff_within_data():
    """cutoff 在 df 中间 → 返回第一根 >= cutoff 的索引。"""
    from BreakoutStrategy.UI.charts.filter_range import compute_left_idx

    idx = pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    assert compute_left_idx(idx, date(2024, 1, 3)) == 2


def test_left_idx_cutoff_before_data_start():
    """cutoff 早于最早数据 → 返回 0。"""
    from BreakoutStrategy.UI.charts.filter_range import compute_left_idx

    idx = pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-03"])
    assert compute_left_idx(idx, date(2023, 12, 1)) == 0


def test_left_idx_cutoff_after_data_end():
    """cutoff 晚于最新数据 → 返回 len(idx)。"""
    from BreakoutStrategy.UI.charts.filter_range import compute_left_idx

    idx = pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-03"])
    assert compute_left_idx(idx, date(2024, 2, 1)) == 3


def test_left_idx_cutoff_exact_match():
    """cutoff 等于某根 bar 的日期 → 返回该 bar 的索引（>= 语义）。"""
    from BreakoutStrategy.UI.charts.filter_range import compute_left_idx

    idx = pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-03"])
    assert compute_left_idx(idx, date(2024, 1, 1)) == 0
    assert compute_left_idx(idx, date(2024, 1, 2)) == 1
