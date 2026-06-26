import numpy as np
import pandas as pd
import pytest

from path2.calc.volume import calculate_vol_ratio


def test_vol_ratio_constant_volume_is_one():
    vols = pd.Series([1000.0] * 100)
    ratio = calculate_vol_ratio(vols, baseline_period=63)
    # 64+:ratio = 1000 / 1000 = 1.0
    assert ratio.iloc[64] == pytest.approx(1.0)


def test_vol_ratio_spike():
    vols = pd.Series([1000.0] * 70)
    vols.iloc[69] = 5000.0
    ratio = calculate_vol_ratio(vols, baseline_period=63)
    # 第 69 根的基线是 [6..68] 均值 = 1000,ratio = 5
    assert ratio.iloc[69] == pytest.approx(5.0)


def test_vol_ratio_warmup_is_nan():
    vols = pd.Series([1000.0] * 70)
    ratio = calculate_vol_ratio(vols, baseline_period=63)
    assert ratio.iloc[:63].isna().all()
