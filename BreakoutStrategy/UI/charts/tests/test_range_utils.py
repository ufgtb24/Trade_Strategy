from datetime import date
import pytest
import pandas as pd
from types import SimpleNamespace
from BreakoutStrategy.UI.charts.range_utils import ChartRangeSpec, trim_df_to_display, adjust_indices


def _make_spec(**overrides):
    """辅助：构造一个默认 spec，调用方按需覆盖字段。"""
    defaults = dict(
        scan_start_ideal=date(2024, 1, 1),
        scan_end_ideal=date(2024, 12, 31),
        scan_start_actual=date(2024, 1, 1),
        scan_end_actual=date(2024, 12, 31),
        compute_start_ideal=date(2023, 11, 13),
        compute_start_actual=date(2023, 11, 13),
        display_start=date(2022, 1, 1),
        display_end=date(2024, 12, 31),
        pkl_start=date(2020, 1, 1),
        pkl_end=date(2024, 12, 31),
    )
    defaults.update(overrides)
    return ChartRangeSpec(**defaults)


def test_no_degradation_when_actual_equals_ideal():
    spec = _make_spec()
    assert spec.scan_start_degraded is False
    assert spec.scan_end_degraded is False
    assert spec.compute_buffer_degraded is False


def test_scan_start_degraded_when_actual_later():
    spec = _make_spec(
        scan_start_ideal=date(2024, 1, 1),
        scan_start_actual=date(2024, 6, 1),
    )
    assert spec.scan_start_degraded is True


def test_scan_end_degraded_when_actual_earlier():
    spec = _make_spec(
        scan_end_ideal=date(2024, 12, 31),
        scan_end_actual=date(2024, 10, 15),
    )
    assert spec.scan_end_degraded is True


def test_compute_buffer_degraded_when_actual_later():
    spec = _make_spec(
        compute_start_ideal=date(2023, 11, 13),
        compute_start_actual=date(2024, 2, 1),
    )
    assert spec.compute_buffer_degraded is True


def test_spec_is_frozen():
    spec = _make_spec()
    with pytest.raises((AttributeError, TypeError)):
        spec.scan_start_actual = date(2020, 1, 1)


def _make_df(start="2020-01-01", periods=400):
    idx = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({"close": range(periods)}, index=idx)


def test_trim_returns_full_df_when_display_start_before_df_start():
    df = _make_df(start="2022-01-01", periods=100)
    spec = _make_spec(display_start=date(2020, 1, 1))
    display_df, offset = trim_df_to_display(df, spec)
    assert offset == 0
    assert len(display_df) == 100
    assert display_df.index[0] == df.index[0]


def test_trim_slices_front_when_display_start_inside_df():
    df = _make_df(start="2022-01-01", periods=100)
    spec = _make_spec(display_start=date(2022, 2, 1))
    display_df, offset = trim_df_to_display(df, spec)
    assert offset == 31  # 1 月 31 天
    assert display_df.index[0] == pd.Timestamp("2022-02-01")


def test_adjust_indices_zero_offset_returns_original():
    items = [SimpleNamespace(index=10), SimpleNamespace(index=20)]
    result = adjust_indices(items, 0)
    assert result is items  # 零 offset 走 shortcut


def test_adjust_indices_subtracts_offset():
    items = [SimpleNamespace(index=10), SimpleNamespace(index=20)]
    result = adjust_indices(items, 5)
    assert [it.index for it in result] == [5, 15]


def test_adjust_indices_skips_items_before_offset():
    items = [
        SimpleNamespace(index=3),   # 被跳过
        SimpleNamespace(index=10),
        SimpleNamespace(index=20),
    ]
    result = adjust_indices(items, 5)
    assert [it.index for it in result] == [5, 15]


def test_adjust_indices_recursively_adjusts_broken_peaks():
    peak1 = SimpleNamespace(index=15)
    peak2 = SimpleNamespace(index=18)
    bo = SimpleNamespace(index=20, broken_peaks=[peak1, peak2])
    result = adjust_indices([bo], 5)
    assert result[0].index == 15
    assert [p.index for p in result[0].broken_peaks] == [10, 13]
