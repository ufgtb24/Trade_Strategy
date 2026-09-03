"""_positive_signals / _has_stop_signal / _atr_at 单测。

从 test_throwback.py 搬入(2026-08-25 tb-v1 首段即停重写,Task 3):这三个 helper
已随 Task 2 迁至 throwback_v3.py 本地副本(不再被 throwback_v1.py 复用),原测试
文件整体删除前,把它们对活代码的直接单测覆盖原样搬到这里,断言逐字不变。
"""
from __future__ import annotations

import pandas as pd
import pytest


def _make_df(rows):
    """构造 OHLCV DataFrame。rows: list of (o, h, l, c, v)。"""
    return pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])


# ---- _positive_signals(逻辑不变)----

def test_positive_signals_doji():
    from path2.atoms.throwback_v3 import _positive_signals
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (100.0, 105.0, 95.0, 100.5, 1000)])  # body/rng=0.05
    assert 'doji' in _positive_signals(df, 1)


def test_positive_signals_lower_shadow():
    from path2.atoms.throwback_v3 import _positive_signals
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (98.0, 103.0, 88.0, 100.0, 1000)])  # shadow=10/15
    assert 'lower_shadow' in _positive_signals(df, 1)


def test_positive_signals_bullish_close_up_gap_up():
    from path2.atoms.throwback_v3 import _positive_signals
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (101.0, 110.0, 100.5, 104.0, 1000)])
    sigs = _positive_signals(df, 1)
    assert 'gap_up' in sigs and 'bullish' in sigs and 'close_up' in sigs


def test_positive_signals_empty():
    from path2.atoms.throwback_v3 import _positive_signals
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (99.0, 100.0, 95.0, 96.0, 1000)])
    assert _positive_signals(df, 1) == []


# ---- _has_stop_signal(不变)----

def test_has_stop_signal_true_on_bullish():
    from path2.atoms.throwback_v3 import _has_stop_signal
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (100.0, 105.0, 99.0, 104.0, 1000)])
    assert _has_stop_signal(df, 1) is True


def test_has_stop_signal_false_on_gap_up_only():
    from path2.atoms.throwback_v3 import _has_stop_signal
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (101.0, 101.2, 98.0, 99.0, 1000)])
    assert _has_stop_signal(df, 1) is False


# ---- _atr_at(签名改为预算序列版,断言语义不变)----

def test_atr_at_constant_tr():
    from path2.atoms.throwback_v3 import _atr_at
    from path2.calc.atr import calculate_atr
    rows = [(100.0, 101.0, 99.0, 100.0, 1000) for _ in range(30)]
    df = _make_df(rows)
    atr = calculate_atr(df['high'], df['low'], df['close'], 14)
    assert _atr_at(atr, 25) == pytest.approx(2.0, abs=1e-6)


def test_atr_at_nan_returns_zero():
    from path2.atoms.throwback_v3 import _atr_at
    from path2.calc.atr import calculate_atr
    df = _make_df([(100.0, 101.0, 99.0, 100.0, 1000) for _ in range(5)])
    atr = calculate_atr(df['high'], df['low'], df['close'], 14)
    assert _atr_at(atr, 2) == 0.0
