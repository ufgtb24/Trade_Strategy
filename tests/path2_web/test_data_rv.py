"""rv 字段算法与口径测试。

dev UI 公式: rv[d] = volume[d] / mean(volume[d-63:d])
实现: rolling(63, min_periods=1).mean().shift(1)
"""
import numpy as np
import pandas as pd
import pytest

from path2_web.data import serialize_ohlc


def _make_df(volumes: list[float]) -> pd.DataFrame:
    n = len(volumes)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": [10.0] * n,
            "high": [11.0] * n,
            "low": [9.0] * n,
            "close": [10.5] * n,
            "volume": volumes,
            "date": dates,
        }
    )


def test_rv_at_idx_63_uses_prior_63_bars_as_denominator():
    volumes = [100.0 + i for i in range(70)]
    win_df = _make_df(volumes)
    result = serialize_ohlc("TEST", win_df)
    expected = volumes[63] / float(np.mean(volumes[:63]))
    assert result["bars"][63]["rv"] == pytest.approx(expected, rel=1e-9)


def test_rv_at_idx_0_returns_zero_due_to_shift():
    volumes = [100.0] * 5
    win_df = _make_df(volumes)
    result = serialize_ohlc("TEST", win_df)
    assert result["bars"][0]["rv"] == 0.0


def test_rv_at_idx_1_uses_only_idx_0_avg_under_min_periods():
    volumes = [100.0, 200.0, 300.0]
    win_df = _make_df(volumes)
    result = serialize_ohlc("TEST", win_df)
    assert result["bars"][1]["rv"] == pytest.approx(200.0 / 100.0, rel=1e-9)


def test_rv_zero_denominator_yields_zero_not_inf():
    volumes = [0.0, 0.0, 500.0]
    win_df = _make_df(volumes)
    result = serialize_ohlc("TEST", win_df)
    assert result["bars"][2]["rv"] == 0.0


def test_rv_field_present_on_every_bar_as_float():
    volumes = [100.0] * 10
    win_df = _make_df(volumes)
    result = serialize_ohlc("TEST", win_df)
    for b in result["bars"]:
        assert "rv" in b
        assert isinstance(b["rv"], float)
