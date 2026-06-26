"""measure_at / measure_series 单测(价格度量纯函数)。"""
import pandas as pd
import pytest

from path2.calc.measure import VALID_MEASURES, measure_at, measure_series


def _df():
    # 1 根:open=100, high=105, low=95, close=98(阴线,body_top=open=100)
    return pd.DataFrame([(100.0, 105.0, 95.0, 98.0, 1000)],
                        columns=['open', 'high', 'low', 'close', 'volume'])


def test_measure_at_all_modes():
    df = _df()
    assert measure_at(df, 0, "high") == 105.0
    assert measure_at(df, 0, "close") == 98.0
    assert measure_at(df, 0, "body_top") == 100.0
    assert measure_at(df, 0, "low") == 95.0


def test_measure_series_all_modes():
    df = _df()
    assert measure_series(df, "high").iloc[0] == 105.0
    assert measure_series(df, "close").iloc[0] == 98.0
    assert measure_series(df, "body_top").iloc[0] == 100.0
    assert measure_series(df, "low").iloc[0] == 95.0


def test_invalid_measure_raises():
    df = _df()
    with pytest.raises(ValueError):
        measure_at(df, 0, "vwap")
    with pytest.raises(ValueError):
        measure_series(df, "vwap")


def test_valid_measures_constant():
    assert set(VALID_MEASURES) == {"high", "close", "body_top", "low"}
