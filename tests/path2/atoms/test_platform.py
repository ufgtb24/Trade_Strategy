import numpy as np
import pandas as pd
import pytest

from path2 import run
from path2.atoms.platform import Platform, PlatformDetector


def make_df(closes, highs=None, lows=None):
    n = len(closes)
    return pd.DataFrame({
        'open': list(closes),
        'high': highs or [c + 0.05 for c in closes],
        'low': lows or [c - 0.05 for c in closes],
        'close': list(closes),
        'volume': [1000.0] * n,
    })


def test_narrow_segment_yields_platform():
    closes = [10.0 + 0.01 * np.sin(i) for i in range(30)]  # 极窄震荡
    df = make_df(closes)
    platforms = list(run(PlatformDetector(window=10, range_thr=0.05), df))
    assert len(platforms) >= 1


def test_wide_range_no_platform():
    closes = list(np.linspace(10.0, 20.0, 30))  # 100% range,远超 thr=0.05
    df = make_df(closes)
    platforms = list(run(PlatformDetector(window=10, range_thr=0.05), df))
    assert platforms == []


def test_platform_event_fields():
    closes = [10.0] * 30
    df = make_df(closes)
    platforms = list(run(PlatformDetector(window=10, range_thr=0.05), df))
    assert all(isinstance(p, Platform) for p in platforms)
    for p in platforms:
        assert p.range_pct >= 0
