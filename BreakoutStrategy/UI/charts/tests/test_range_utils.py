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


from datetime import timedelta
from BreakoutStrategy.UI.charts.range_utils import (
    _collect_warnings, DISPLAY_MIN_WINDOW
)


def test_collect_warnings_returns_empty_when_no_degradation():
    spec = _make_spec()
    assert _collect_warnings(spec) == []


def test_collect_warnings_includes_scan_start():
    spec = _make_spec(
        scan_start_ideal=date(2024, 1, 1),
        scan_start_actual=date(2024, 6, 1),
    )
    warnings = _collect_warnings(spec)
    assert len(warnings) == 1
    assert "scan_start" in warnings[0]
    assert "2024-06-01" in warnings[0]


def test_collect_warnings_includes_multiple():
    spec = _make_spec(
        scan_start_ideal=date(2024, 1, 1),
        scan_start_actual=date(2024, 6, 1),
        scan_end_ideal=date(2024, 12, 31),
        scan_end_actual=date(2024, 10, 15),
        compute_start_ideal=date(2023, 11, 13),
        compute_start_actual=date(2024, 1, 1),
    )
    warnings = _collect_warnings(spec)
    assert len(warnings) == 3


# ---- from_df_and_scan 工厂 ----
from BreakoutStrategy.analysis.scanner import preprocess_dataframe, compute_breakouts_from_dataframe


def _make_pkl_for_spec(start="2020-01-01", periods=2000):
    idx = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({
        "open": [100.0]*periods, "high": [101.0]*periods,
        "low": [99.0]*periods, "close": [100.0]*periods,
        "volume": [1000.0]*periods,
    }, index=idx)


# 为触发 compute_breakouts 写 scan_*_actual 到 attrs，我们需要提供 detector 参数
_DETECTOR_KWARGS = dict(
    total_window=60, min_side_bars=5, min_relative_height=0.02,
    exceed_threshold=0.01, peak_supersede_threshold=0.02,
)


def _compute_valid_indices(df, scan_start_date, scan_end_date):
    """辅助：从 df 中找 valid_start_index / valid_end_index，供测试传入 compute_breakouts_from_dataframe。"""
    mask_start = df.index >= pd.to_datetime(scan_start_date)
    valid_start = int(mask_start.argmax()) if mask_start.any() else 0
    mask_end = df.index <= pd.to_datetime(scan_end_date)
    valid_end = int(len(df) - mask_end[::-1].argmax()) if mask_end.any() else len(df)
    return valid_start, valid_end


def test_from_df_and_scan_constructs_spec_with_all_fields():
    df = _make_pkl_for_spec()
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    valid_start, valid_end = _compute_valid_indices(df, "2024-01-01", "2024-12-31")
    compute_breakouts_from_dataframe(
        symbol="TEST", df=df,
        valid_start_index=valid_start, valid_end_index=valid_end,
        scan_start_date="2024-01-01", scan_end_date="2024-12-31",
        **_DETECTOR_KWARGS,
    )
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2024-01-01",
        scan_end="2024-12-31",
        display_end=date(2024, 12, 31),
    )
    assert spec.scan_start_ideal == date(2024, 1, 1)
    assert spec.scan_start_actual == date(2024, 1, 1)
    assert spec.scan_start_degraded is False
    assert spec.display_end == date(2024, 12, 31)


def test_from_df_and_scan_applies_display_min_window():
    """display_start = min(scan_start_actual, display_end - 3y)，典型 scan 窗口下取后者。"""
    df = _make_pkl_for_spec()
    df = preprocess_dataframe(df, start_date="2024-06-01", end_date="2024-12-31")
    valid_start, valid_end = _compute_valid_indices(df, "2024-06-01", "2024-12-31")
    compute_breakouts_from_dataframe(
        symbol="TEST", df=df,
        valid_start_index=valid_start, valid_end_index=valid_end,
        scan_start_date="2024-06-01", scan_end_date="2024-12-31",
        **_DETECTOR_KWARGS,
    )
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2024-06-01",
        scan_end="2024-12-31",
        display_end=date(2024, 12, 31),
        display_min_window=timedelta(days=1095),
    )
    # scan_start (2024-06-01) > display_end - 3y (2022-01-01) → 取后者
    assert spec.display_start == date(2022, 1, 1)


def test_from_df_and_scan_degrades_display_start_to_pkl_start():
    """pkl 短于 3 年时，display_start 被 pkl 起点封顶。"""
    df = _make_pkl_for_spec(start="2023-01-01", periods=500)  # pkl 从 2023-01-01
    df = preprocess_dataframe(df, start_date="2023-06-01", end_date="2024-03-31")
    compute_breakouts_from_dataframe(
        symbol="TEST", df=df,
        scan_start_date="2023-06-01", scan_end_date="2024-03-31",
        **_DETECTOR_KWARGS,
    )
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2023-06-01",
        scan_end="2024-03-31",
        display_end=date(2024, 3, 31),
    )
    # display_end - 3y = 2021-03-31，但 pkl_start = 2023-01-01，所以 display_start = pkl_start
    assert spec.display_start == date(2023, 1, 1)


def test_from_df_and_scan_records_scan_start_degradation():
    df = _make_pkl_for_spec(start="2024-03-01", periods=500)
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    compute_breakouts_from_dataframe(
        symbol="TEST", df=df,
        scan_start_date="2024-01-01", scan_end_date="2024-12-31",
        **_DETECTOR_KWARGS,
    )
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2024-01-01",
        scan_end="2024-12-31",
        display_end=date(2024, 12, 31),
    )
    assert spec.scan_start_degraded is True
    assert spec.scan_start_actual == date(2024, 3, 1)


def test_from_df_and_scan_display_min_window_none_means_full_scan():
    df = _make_pkl_for_spec()
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    compute_breakouts_from_dataframe(
        symbol="TEST", df=df,
        scan_start_date="2024-01-01", scan_end_date="2024-12-31",
        **_DETECTOR_KWARGS,
    )
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2024-01-01",
        scan_end="2024-12-31",
        display_end=date(2024, 12, 31),
        display_min_window=None,
    )
    # display_start 沿 scan_start_actual
    assert spec.display_start == spec.scan_start_actual


def test_from_df_and_scan_works_without_compute_breakouts():
    """JSON cache 路径：只 preprocess、不 compute_breakouts，工厂应仍可构造 spec。"""
    df = _make_pkl_for_spec()
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    # 注意：不调用 compute_breakouts_from_dataframe
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2024-01-01",
        scan_end="2024-12-31",
        display_end=date(2024, 12, 31),
        display_min_window=None,
    )
    assert spec.scan_start_actual == date(2024, 1, 1)
    assert spec.scan_end_actual == date(2024, 12, 31)


def test_from_df_and_scan_handles_none_scan_dates():
    """当 scan_start/scan_end 为 None 时，ideal 字段 fallback 到 actual，不崩。"""
    df = _make_pkl_for_spec()
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    compute_breakouts_from_dataframe(
        symbol="TEST", df=df,
        scan_start_date="2024-01-01", scan_end_date="2024-12-31",
        **_DETECTOR_KWARGS,
    )
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start=None,  # type: ignore
        scan_end=None,    # type: ignore
        display_end=date(2024, 12, 31),
        display_min_window=None,
    )
    assert spec.scan_start_ideal == spec.scan_start_actual
    assert spec.scan_end_ideal == spec.scan_end_actual
    assert spec.scan_start_degraded is False
    assert spec.scan_end_degraded is False
