import pandas as pd
import pytest

from path2_web.data import slice_window, serialize_ohlc


def _mk_df(n=30, start="2025-01-01"):
    idx = pd.date_range(start, periods=n, freq="D", name="date")
    return pd.DataFrame({
        "open":   [10.0 + i for i in range(n)],
        "high":   [11.0 + i for i in range(n)],
        "low":    [9.0 + i for i in range(n)],
        "close":  [10.5 + i for i in range(n)],
        "volume": [1000.0 + i for i in range(n)],
    }, index=idx)


def test_slice_window_inclusive_and_zero_based():
    df = _mk_df()
    win = slice_window(df, "2025-01-05", "2025-01-10")
    # 双端含端点 → 6 行;reset_index 后 0-based 行位置 + date 列
    assert len(win) == 6
    assert list(win.index) == list(range(6))
    assert "date" in win.columns
    assert str(win.iloc[0]["date"])[:10] == "2025-01-05"
    assert str(win.iloc[-1]["date"])[:10] == "2025-01-10"


def test_slice_window_empty_on_out_of_range():
    df = _mk_df()
    win = slice_window(df, "2030-01-01", "2030-12-31")
    assert len(win) == 0


def test_slice_window_tz_aware_localized():
    df = _mk_df()
    df.index = df.index.tz_localize("America/New_York")
    win = slice_window(df, "2025-01-05", "2025-01-10")
    assert len(win) == 6  # tz 去除后仍可切


def test_serialize_ohlc_aligns_with_slice():
    df = _mk_df()
    win = slice_window(df, "2025-01-05", "2025-01-20")
    ohlc = serialize_ohlc("AAPL", win)
    assert ohlc["symbol"] == "AAPL"
    assert len(ohlc["bars"]) == len(win)
    # bars[i] ↔ start_idx==i 严格对齐
    for i in range(len(win)):
        assert ohlc["bars"][i]["date"] == str(win.iloc[i]["date"])[:10]
        assert ohlc["bars"][i]["o"] == pytest.approx(float(win.iloc[i]["open"]))
        assert ohlc["bars"][i]["v"] == pytest.approx(float(win.iloc[i]["volume"]))
