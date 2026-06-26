import numpy as np
import pandas as pd
import pytest

from path2.calc.atr import calculate_atr


def test_atr_basic_shape():
    n = 30
    highs = pd.Series(np.linspace(10, 12, n) + 0.5)
    lows = pd.Series(np.linspace(10, 12, n) - 0.5)
    closes = pd.Series(np.linspace(10, 12, n))
    atr = calculate_atr(highs, lows, closes, period=14)
    assert len(atr) == n
    assert atr.iloc[:13].isna().all()
    assert not atr.iloc[14:].isna().any()


def test_atr_constant_tr():
    n = 30
    highs = pd.Series([11.0] * n)
    lows = pd.Series([10.0] * n)
    closes = pd.Series([10.5] * n)
    atr = calculate_atr(highs, lows, closes, period=14)
    assert atr.iloc[20] == pytest.approx(1.0, rel=1e-6)


def test_atr_zero_when_no_range():
    n = 20
    highs = pd.Series([10.0] * n)
    lows = pd.Series([10.0] * n)
    closes = pd.Series([10.0] * n)
    atr = calculate_atr(highs, lows, closes, period=14)
    assert atr.iloc[15] == 0.0
