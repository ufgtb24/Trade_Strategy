import pandas as pd
from BreakoutStrategy.analysis.scanner import preprocess_dataframe


def _make_pkl(start="2020-01-01", periods=2000):
    """大于 compute_buffer 的 pkl，确保 preprocess 不会被 pkl 起点降级。"""
    idx = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({
        "open":   [100.0] * periods,
        "high":   [101.0] * periods,
        "low":    [99.0]  * periods,
        "close":  [100.0] * periods,
        "volume": [1000.0] * periods,
    }, index=idx)


def test_preprocess_writes_range_meta_with_required_keys():
    df = _make_pkl()
    out = preprocess_dataframe(df.copy(), start_date="2024-01-01", end_date="2024-12-31")
    meta = out.attrs.get("range_meta")
    assert meta is not None
    for key in [
        "pkl_start", "pkl_end",
        "scan_start_ideal", "scan_end_ideal",
        "compute_start_ideal", "compute_start_actual",
        "label_buffer_end_ideal", "label_buffer_end_actual",
    ]:
        assert key in meta, f"missing key: {key}"


def test_preprocess_ideal_values_match_inputs():
    df = _make_pkl()
    out = preprocess_dataframe(df.copy(), start_date="2024-01-01", end_date="2024-12-31")
    meta = out.attrs["range_meta"]
    assert str(meta["scan_start_ideal"]) == "2024-01-01"
    assert str(meta["scan_end_ideal"]) == "2024-12-31"


def test_preprocess_records_pkl_bounds_from_original_df():
    df = _make_pkl(start="2021-03-15", periods=1500)
    expected_end = df.index[-1].date()
    out = preprocess_dataframe(df.copy(), start_date="2024-01-01", end_date="2024-12-31")
    meta = out.attrs["range_meta"]
    assert str(meta["pkl_start"]) == "2021-03-15"
    assert meta["pkl_end"] == expected_end


def test_preprocess_compute_start_actual_equals_pkl_start_when_pkl_shorter():
    """pkl 起点晚于 scan_start - compute_buffer 时，compute_start_actual = pkl 起点。"""
    df = _make_pkl(start="2023-08-01", periods=600)  # pkl 起点 2023-08-01
    out = preprocess_dataframe(df.copy(), start_date="2024-01-01", end_date="2024-12-31")
    meta = out.attrs["range_meta"]
    # pkl 起点晚于 buffer_start (约 2022-11-13)，compute_start_actual 应跟随 pkl
    assert str(meta["compute_start_actual"]) == "2023-08-01"


import logging
from BreakoutStrategy.analysis.scanner import compute_breakouts_from_dataframe


def test_compute_breakouts_writes_scan_actual_when_no_degradation(caplog):
    df = _make_pkl()
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    with caplog.at_level(logging.INFO, logger="BreakoutStrategy.analysis.scanner"):
        compute_breakouts_from_dataframe(
            df, scan_start_date="2024-01-01", scan_end_date="2024-12-31"
        )
    meta = df.attrs["range_meta"]
    assert str(meta["scan_start_actual"]) == "2024-01-01"
    assert str(meta["scan_end_actual"]) == "2024-12-31"
    # 未降级：不应有 INFO 日志
    assert not any("degraded" in r.message for r in caplog.records)


def test_compute_breakouts_logs_and_records_scan_start_degradation(caplog):
    """pkl 起点晚于 scan_start 时，compute_breakouts 应记录 actual > ideal 并写日志。"""
    # pkl 起点 2024-03-01，scan_start 2024-01-01 —— scan_start 被降级
    df = _make_pkl(start="2024-03-01", periods=500)
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    with caplog.at_level(logging.INFO, logger="BreakoutStrategy.analysis.scanner"):
        compute_breakouts_from_dataframe(
            df, scan_start_date="2024-01-01", scan_end_date="2024-12-31"
        )
    meta = df.attrs["range_meta"]
    assert str(meta["scan_start_actual"]) == "2024-03-01"
    assert any(
        "scan_start degraded" in r.message for r in caplog.records
    ), f"no degradation log found, records: {[r.message for r in caplog.records]}"


def test_compute_breakouts_logs_scan_end_degradation(caplog):
    """pkl 终点早于 scan_end 时，scan_end 被降级。"""
    # pkl 终点 2024-06-30，scan_end 2024-12-31 —— scan_end 被降级
    df = _make_pkl(start="2022-01-01", periods=912)  # 截止 2024-06-30
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    with caplog.at_level(logging.INFO, logger="BreakoutStrategy.analysis.scanner"):
        compute_breakouts_from_dataframe(
            df, scan_start_date="2024-01-01", scan_end_date="2024-12-31"
        )
    meta = df.attrs["range_meta"]
    assert meta["scan_end_actual"] < pd.to_datetime("2024-12-31").date()
    assert any("scan_end degraded" in r.message for r in caplog.records)
