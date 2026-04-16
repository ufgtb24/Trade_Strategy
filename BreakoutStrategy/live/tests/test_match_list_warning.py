from datetime import date
from unittest.mock import MagicMock

from BreakoutStrategy.live.pipeline.results import MatchedBreakout
from BreakoutStrategy.UI.charts.range_utils import ChartRangeSpec


def _spec_no_degradation():
    return ChartRangeSpec(
        scan_start_ideal=date(2024, 1, 1), scan_end_ideal=date(2024, 12, 31),
        scan_start_actual=date(2024, 1, 1), scan_end_actual=date(2024, 12, 31),
        compute_start_ideal=date(2023, 11, 13), compute_start_actual=date(2023, 11, 13),
        display_start=date(2022, 1, 1), display_end=date(2024, 12, 31),
        pkl_start=date(2020, 1, 1), pkl_end=date(2024, 12, 31),
    )


def _spec_scan_start_degraded():
    return ChartRangeSpec(
        scan_start_ideal=date(2024, 1, 1), scan_end_ideal=date(2024, 12, 31),
        scan_start_actual=date(2024, 6, 1), scan_end_actual=date(2024, 12, 31),
        compute_start_ideal=date(2023, 11, 13), compute_start_actual=date(2024, 2, 1),
        display_start=date(2022, 1, 1), display_end=date(2024, 12, 31),
        pkl_start=date(2024, 2, 1), pkl_end=date(2024, 12, 31),
    )


def _make_mb(range_spec=None, sentiment_score=None):
    return MatchedBreakout(
        symbol="AAPL",
        breakout_date="2024-08-15",
        breakout_price=200.0,
        factors={},
        sentiment_score=sentiment_score,
        sentiment_category="pending",
        sentiment_summary=None,
        raw_breakout={"index": 0, "date": "2024-08-15", "price": 200.0},
        raw_peaks=[],
        range_spec=range_spec,
    )


def test_row_values_no_warning_when_spec_clean():
    from BreakoutStrategy.live.panels.match_list import MatchList
    ml = MatchList.__new__(MatchList)  # 绕过 __init__
    mb = _make_mb(range_spec=_spec_no_degradation())
    values = ml._row_values(mb)
    assert "⚠" not in values[0]


def test_row_values_appends_warning_when_spec_degraded():
    from BreakoutStrategy.live.panels.match_list import MatchList
    ml = MatchList.__new__(MatchList)
    mb = _make_mb(range_spec=_spec_scan_start_degraded())
    values = ml._row_values(mb)
    assert "⚠" in values[0]


def test_row_values_no_warning_when_range_spec_none():
    """旧缓存加载后 range_spec=None，不应出现 ⚠。"""
    from BreakoutStrategy.live.panels.match_list import MatchList
    ml = MatchList.__new__(MatchList)
    mb = _make_mb(range_spec=None)
    values = ml._row_values(mb)
    assert "⚠" not in values[0]
