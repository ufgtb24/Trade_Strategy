from datetime import date
import pandas as pd
import pytest

from BreakoutStrategy.live.pipeline.daily_runner import _build_range_spec_for_symbol


def _make_pkl_df(start="2022-01-01", periods=900):
    idx = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0
    }, index=idx)


def test_build_range_spec_returns_spec_when_df_valid(tmp_path):
    """从 pkl 构造 spec，应得到合理的 ChartRangeSpec。"""
    df = _make_pkl_df()
    pkl_path = tmp_path / "AAPL.pkl"
    df.to_pickle(pkl_path)

    spec = _build_range_spec_for_symbol(
        pkl_path=pkl_path,
        scan_start="2024-01-01",
        scan_end=df.index[-1].date().isoformat(),
    )

    assert spec is not None
    assert spec.scan_start_ideal == date(2024, 1, 1)


def test_build_range_spec_returns_none_on_missing_pkl(tmp_path):
    spec = _build_range_spec_for_symbol(
        pkl_path=tmp_path / "NOTEXIST.pkl",
        scan_start="2024-01-01",
        scan_end="2024-12-31",
    )
    assert spec is None
