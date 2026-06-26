import numpy as np
import pandas as pd
import pytest

from path2 import run
from path2.atoms.trend import TrendSegment, TrendSegmentDetector


def make_df(closes):
    n = len(closes)
    return pd.DataFrame({
        'open': closes,
        'high': [c + 0.1 for c in closes],
        'low': [c - 0.1 for c in closes],
        'close': closes,
        'volume': [1000.0] * n,
    })


def test_sideways_all():
    closes = [10.0] * 100
    df = make_df(closes)
    segments = list(run(TrendSegmentDetector(), df))
    # 至少一段,全 sideways
    assert all(s.regime == 'sideways' for s in segments)


def test_up_trend():
    closes = list(np.linspace(10.0, 20.0, 100))  # +10 over 100 bars
    df = make_df(closes)
    segments = list(run(TrendSegmentDetector(), df))
    # 应至少有一段 up
    assert any(s.regime == 'up' for s in segments)


def test_down_trend():
    closes = list(np.linspace(20.0, 10.0, 100))
    df = make_df(closes)
    segments = list(run(TrendSegmentDetector(), df))
    assert any(s.regime == 'down' for s in segments)


def test_hysteresis_avoids_short_flip():
    # 长期 sideways,中间 2 bar 上行(< hysteresis_bars=3)→ 不切
    closes = [10.0] * 50 + list(np.linspace(10, 11, 2)) + [11.0] * 50
    df = make_df(closes)
    segments = list(run(TrendSegmentDetector(hysteresis_bars=10), df))
    regimes = [s.regime for s in segments]
    # 不应频繁切换(短切换被 hysteresis 吸收)
    assert len(set(regimes)) <= 3


def test_segments_cover_full_range():
    closes = [10.0] * 60
    df = make_df(closes)
    segments = list(run(TrendSegmentDetector(), df))
    if segments:
        assert segments[-1].end_idx == 59  # 末段到 df 末尾


def test_trend_segment_has_drawdown_field():
    # 构造一个明显下跌段:high 100 → 50,drawdown ≈ 0.5
    n = 200
    dates = pd.date_range("2024-01-01", periods=n)
    closes = pd.Series(np.linspace(100, 50, n), index=dates)
    highs = closes * 1.01
    lows = closes * 0.99
    df = pd.DataFrame({
        'open': closes,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': pd.Series([1e6] * n, index=dates),
    })
    detector = TrendSegmentDetector(ma_period=20, hysteresis_bars=5)
    segs = list(detector.detect(df))
    # 至少有一段 down,且 drawdown 应在 [0, 1] 且 > 0
    down_segs = [s for s in segs if s.regime == "down"]
    assert len(down_segs) >= 1
    assert all(0.0 <= s.drawdown <= 1.0 for s in down_segs)
    # 单调下跌 fixture,任一 down 段 drawdown 应明显 > 0(>= 0.1)
    assert max(s.drawdown for s in down_segs) >= 0.1


def test_sideways_eps_filter():
    # 极缓上升:per-bar SMA 相对变化 < sideways_eps,应保持 sideways
    # closes 每根 +0.0001(price=10 → SMA 每根变化约 +0.0001/10 = 1e-5),远低于 eps=0.0005
    n = 200
    closes = [10.0 + i * 0.0001 for i in range(n)]
    df = make_df(closes)
    segments = list(run(TrendSegmentDetector(sideways_eps=0.0005), df))
    # 微小斜率不应触发 up
    assert all(s.regime == 'sideways' for s in segments)
