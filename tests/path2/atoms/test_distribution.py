import pandas as pd
import pytest

from path2 import run
from path2.atoms.distribution import Distribution, DistributionDetector


def make_df(rows):
    """rows: list of dict with keys open/high/low/close/volume"""
    return pd.DataFrame(rows)


def test_distribution_hit():
    # 高放量阴线 + 长上影
    base = [{'open': 10.0, 'high': 10.1, 'low': 9.95, 'close': 10.0, 'volume': 1000.0}] * 70
    # 第 69 根:vol_ratio = 5(放量),close < open(阴),上影占 60%
    base[69] = {'open': 10.5, 'high': 12.0, 'low': 10.3, 'close': 10.4, 'volume': 5000.0}
    df = make_df(base)
    dists = list(run(DistributionDetector(vol_threshold=3.0, upper_shadow_threshold=0.5), df))
    assert len(dists) >= 1


def test_no_distribution_on_yang():
    base = [{'open': 10.0, 'high': 10.1, 'low': 9.95, 'close': 10.0, 'volume': 1000.0}] * 70
    base[69] = {'open': 10.0, 'high': 12.0, 'low': 9.9, 'close': 11.5, 'volume': 5000.0}  # 阳线
    df = make_df(base)
    dists = list(run(DistributionDetector(), df))
    assert dists == []


def test_no_distribution_on_low_vol():
    base = [{'open': 10.0, 'high': 10.1, 'low': 9.95, 'close': 10.0, 'volume': 1000.0}] * 70
    base[69] = {'open': 10.5, 'high': 12.0, 'low': 10.3, 'close': 10.4, 'volume': 1200.0}  # vol_ratio 太低
    df = make_df(base)
    dists = list(run(DistributionDetector(vol_threshold=3.0), df))
    assert dists == []
