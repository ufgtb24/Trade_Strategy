"""tb 可买入区间事件单测(v2:预算拆分 max_start_gap/max_window、measure 参数化、ATR@bo-1)。"""
from __future__ import annotations

import pandas as pd
import pytest


def _make_df(rows):
    """构造 OHLCV DataFrame。rows: list of (o, h, l, c, v)。"""
    return pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])


# ---- _positive_signals(逻辑不变)----

def test_positive_signals_doji():
    from path2.atoms.throwback import _positive_signals
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (100.0, 105.0, 95.0, 100.5, 1000)])  # body/rng=0.05
    assert 'doji' in _positive_signals(df, 1)


def test_positive_signals_lower_shadow():
    from path2.atoms.throwback import _positive_signals
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (98.0, 103.0, 88.0, 100.0, 1000)])  # shadow=10/15
    assert 'lower_shadow' in _positive_signals(df, 1)


def test_positive_signals_bullish_close_up_gap_up():
    from path2.atoms.throwback import _positive_signals
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (101.0, 110.0, 100.5, 104.0, 1000)])
    sigs = _positive_signals(df, 1)
    assert 'gap_up' in sigs and 'bullish' in sigs and 'close_up' in sigs


def test_positive_signals_empty():
    from path2.atoms.throwback import _positive_signals
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (99.0, 100.0, 95.0, 96.0, 1000)])
    assert _positive_signals(df, 1) == []


# ---- _has_stop_signal(不变)----

def test_has_stop_signal_true_on_bullish():
    from path2.atoms.throwback import _has_stop_signal
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (100.0, 105.0, 99.0, 104.0, 1000)])
    assert _has_stop_signal(df, 1) is True


def test_has_stop_signal_false_on_gap_up_only():
    from path2.atoms.throwback import _has_stop_signal
    df = _make_df([(100.0, 100.0, 100.0, 100.0, 1000),
                   (101.0, 101.2, 98.0, 99.0, 1000)])
    assert _has_stop_signal(df, 1) is False


# ---- _atr_at(不变)----

def test_atr_at_constant_tr():
    from path2.atoms.throwback import _atr_at
    rows = [(100.0, 101.0, 99.0, 100.0, 1000) for _ in range(30)]
    df = _make_df(rows)
    assert _atr_at(df, 25, period=14) == pytest.approx(2.0, abs=1e-6)


def test_atr_at_nan_returns_zero():
    from path2.atoms.throwback import _atr_at
    df = _make_df([(100.0, 101.0, 99.0, 100.0, 1000) for _ in range(5)])
    assert _atr_at(df, 2, period=14) == 0.0


# ---- _find_start_idx(v2:max_start_gap + support_measure)----

def test_find_start_idx_break_before_stop():
    from path2.atoms.throwback import _find_start_idx
    rows = [(100.0, 100.0, 99.5, 100.0, 1000),
            (100.0, 100.0, 100.0, 100.0, 1000),
            (98.0, 99.0, 98.0, 98.5, 1000)]      # i=2 low=98 < anchor=100(=high[0])
    df = _make_df(rows)
    assert _find_start_idx(df, bo_idx=1, anchor=100.0, max_start_gap=10,
                           atr=1.0, pullback_min_atr=1.0) is None


def test_find_start_idx_stop_with_pullback():
    from path2.atoms.throwback import _find_start_idx
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),   # 0 bo:峰 high=100
        (98.0, 98.5, 96.0, 97.0, 1000),    # 1 跌
        (96.0, 96.5, 95.0, 95.5, 1000),    # 2 trough low=95
        (95.5, 97.0, 95.2, 96.8, 1000),    # 3 不创新低 + bullish
        (96.8, 98.0, 95.5, 97.9, 1000),    # 4 不创新低 + bullish → 双根确认@4
    ]
    df = _make_df(rows)
    start = _find_start_idx(df, bo_idx=0, anchor=90.0, max_start_gap=10,
                            atr=1.0, pullback_min_atr=1.0)
    assert start == 2


def test_find_start_idx_pullback_gate_fail():
    from path2.atoms.throwback import _find_start_idx
    rows = [
        (99.8, 100.0, 99.7, 99.9, 1000),
        (99.8, 100.0, 99.75, 99.9, 1000),
        (99.8, 100.0, 99.80, 99.95, 1000),
        (99.9, 100.1, 99.85, 100.0, 1000),  # 双根@3;回落=100−99.7=0.3 < 1.0×atr
    ]
    df = _make_df(rows)
    assert _find_start_idx(df, bo_idx=0, anchor=90.0, max_start_gap=10,
                           atr=1.0, pullback_min_atr=1.0) is None


def test_find_start_idx_no_stop_in_window():
    from path2.atoms.throwback import _find_start_idx
    rows = [(100.0 - i, 100.5 - i, 99.5 - i, 100.0 - i, 1000) for i in range(6)]
    df = _make_df(rows)  # 每根创新低,无止跌
    assert _find_start_idx(df, bo_idx=0, anchor=90.0, max_start_gap=5,
                           atr=1.0, pullback_min_atr=0.0) is None


def test_find_start_idx_budget_cutoff():
    # 止跌确认发生在 bo+max_start_gap 窗外 → None(买点不离 bo 过远)
    from path2.atoms.throwback import _find_start_idx
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),    # 0 bo,峰 high=100
        (98.0, 98.5, 96.0, 97.0, 1000),     # 1 跌
        (96.5, 97.0, 95.5, 96.0, 1000),     # 2 跌
        (95.8, 96.2, 95.0, 95.5, 1000),     # 3 跌(继续创新低)
        (95.4, 95.8, 94.5, 95.0, 1000),     # 4 trough low=94.5
        (95.0, 96.0, 94.7, 95.8, 1000),     # 5 不创新低 + bullish
        (95.8, 96.5, 94.9, 96.3, 1000),     # 6 不创新低 + bullish → 双根确认@6
    ]
    df = _make_df(rows)
    assert _find_start_idx(df, bo_idx=0, anchor=90.0, max_start_gap=3,
                           atr=1.0, pullback_min_atr=1.0) is None    # 窗止于 bo+3,确认不到
    assert _find_start_idx(df, bo_idx=0, anchor=90.0, max_start_gap=10,
                           atr=1.0, pullback_min_atr=1.0) == 4


def test_find_start_idx_support_measure_close_survives_low_dip():
    # low 跌破 anchor 但 close 守住:"low" 口径破位 → None;"close" 口径存活
    from path2.atoms.throwback import _find_start_idx
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),    # 0 bo,峰 high=100
        (98.0, 98.5, 94.5, 96.0, 1000),     # 1 low=94.5<95=anchor,close=96≥95
        (96.0, 96.5, 95.2, 95.8, 1000),     # 2
        (95.8, 97.0, 95.4, 96.8, 1000),     # 3 不创新低 + bullish → 确认@3
        (96.8, 98.0, 95.6, 97.9, 1000),     # 4
    ]
    df = _make_df(rows)
    assert _find_start_idx(df, bo_idx=0, anchor=95.0, max_start_gap=10,
                           atr=1.0, pullback_min_atr=1.0,
                           support_measure="low") is None
    assert _find_start_idx(df, bo_idx=0, anchor=95.0, max_start_gap=10,
                           atr=1.0, pullback_min_atr=1.0,
                           support_measure="close") == 1             # trough=argmin low=idx1


# ---- _find_end_idx(v2:max_window + support_measure)----

def test_find_end_idx_big_rise():
    from path2.atoms.throwback import _find_end_idx
    rows = [
        (95.5, 96.0, 95.0, 95.5, 1000),   # 0 start:base_min=95
        (95.6, 96.2, 95.3, 96.0, 1000),   # 1 high−95=1.2 <1.5
        (96.0, 97.0, 95.5, 96.8, 1000),   # 2 high−95=2.0 ≥1.5 → end=1
    ]
    df = _make_df(rows)
    assert _find_end_idx(df, start_idx=0, anchor=90.0, max_window=10,
                         atr=1.0, big_rise_k=1.5) == 1


def test_find_end_idx_degenerate_single_point():
    from path2.atoms.throwback import _find_end_idx
    rows = [
        (95.0, 95.5, 95.0, 95.2, 1000),
        (95.2, 97.0, 95.2, 96.8, 1000),   # 1 high−95=2.0≥1.5 → end=0(单点区间)
    ]
    df = _make_df(rows)
    assert _find_end_idx(df, start_idx=0, anchor=90.0, max_window=10,
                         atr=1.0, big_rise_k=1.5) == 0


def test_find_end_idx_timeout():
    from path2.atoms.throwback import _find_end_idx
    rows = [(95.0, 95.4, 94.9, 95.1, 1000) for _ in range(8)]
    df = _make_df(rows)
    # start=0,max_window=5 → end=min(5,7)=5(买点窗不持续过长)
    assert _find_end_idx(df, start_idx=0, anchor=90.0, max_window=5,
                         atr=1.0, big_rise_k=1.5) == 5


def test_find_end_idx_break_returns_none():
    from path2.atoms.throwback import _find_end_idx
    rows = [
        (95.0, 95.5, 95.0, 95.2, 1000),
        (95.0, 95.5, 89.0, 90.0, 1000),   # 1 low=89<anchor=90 破位
    ]
    df = _make_df(rows)
    assert _find_end_idx(df, start_idx=0, anchor=90.0, max_window=10,
                         atr=1.0, big_rise_k=1.5) is None


def test_find_end_idx_base_min_excludes_current_bar():
    from path2.atoms.throwback import _find_end_idx
    rows = [
        (95.0, 95.2, 95.0, 95.1, 1000),   # 0 start:base_min=95
        (95.1, 99.0, 93.0, 95.0, 1000),   # 1 base_min 取 [start,i-1]=95(非本根 93);high−95=4≥1.5 → end=0
    ]
    df = _make_df(rows)
    assert _find_end_idx(df, start_idx=0, anchor=80.0, max_window=10,
                         atr=1.0, big_rise_k=1.5) == 0


def test_find_end_idx_support_measure_close():
    # low 跌破 anchor 但 close 守住:"low" 破位 None;"close" 走到 timeout
    from path2.atoms.throwback import _find_end_idx
    rows = [
        (95.0, 95.5, 95.0, 95.2, 1000),   # 0 start
        (95.0, 95.5, 89.0, 95.1, 1000),   # 1 low=89<90,close=95.1≥90
        (95.1, 95.6, 95.0, 95.3, 1000),   # 2
    ]
    df = _make_df(rows)
    assert _find_end_idx(df, start_idx=0, anchor=90.0, max_window=5,
                         atr=1.0, big_rise_k=99.0) is None
    assert _find_end_idx(df, start_idx=0, anchor=90.0, max_window=5,
                         atr=1.0, big_rise_k=99.0,
                         support_measure="close") == 2               # timeout=min(5,len-1)=2


# ---- evaluate_throwback(v2 端到端)----

def _series_with_atr2(n, base=100.0):
    """每根 high-low=2、close 平、无跳空 → ATR≈2.0。返回 rows。"""
    return [(base, base + 1.0, base - 1.0, base, 1000) for _ in range(n)]


def _bo_at(idx):
    from path2.atoms.breakout import BOEvent
    return BOEvent(event_id=f"bo_{idx}", start_idx=idx, end_idx=idx)


def test_evaluate_returns_none_when_bo_idx_zero():
    from path2.atoms.throwback import evaluate_throwback
    df = pd.DataFrame(_series_with_atr2(30), columns=['open', 'high', 'low', 'close', 'volume'])
    assert evaluate_throwback(_bo_at(0), df) is None


def test_evaluate_break_returns_none():
    from path2.atoms.throwback import evaluate_throwback
    rows = _series_with_atr2(20)
    rows[19] = (100.0, 101.0, 90.0, 95.0, 1000)   # bo@18 后 idx19 low=90 破 anchor=high[17]=101
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    assert evaluate_throwback(_bo_at(18), df, atr_window=14) is None


def test_evaluate_success_returns_result():
    # 深历史(ATR@18=2.0)→ bo@19 → 回落≥2 → 双根止跌 → 大涨≥3;预算默认 5/5 内
    from path2.atoms.throwback import evaluate_throwback, ThrowbackResult
    rows = _series_with_atr2(20, base=100.0)         # anchor=high[18]=101
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)    # bo 峰 high=104
    tail = [
        (102.5, 103.0, 101.6, 102.0, 1000),   # 20 跌
        (101.8, 102.0, 101.5, 101.7, 1000),   # 21 trough low=101.5(回落=104−101.5=2.5≥2)
        (101.7, 102.5, 101.6, 102.4, 1000),   # 22 不创新低 + bullish
        (102.4, 103.0, 101.8, 102.9, 1000),   # 23 不创新低 + bullish → start=21(gap=2≤5)
        (102.9, 105.5, 102.5, 105.0, 1000),   # 24 high−101.5=4≥1.5×2 → end=23(window=2≤5)
    ]
    rows += tail
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    r = evaluate_throwback(_bo_at(19), df, atr_window=14,
                           big_rise_k=1.5, pullback_min_atr=1.0)
    assert isinstance(r, ThrowbackResult)
    assert r.start_idx == 21 and r.end_idx == 23


def test_evaluate_atr_uses_bo_minus_1():
    # bo 当根巨幅 TR(=30):ATR@19=(2×13+30)/14≈4.0,ATR@18=2.0。
    # 大涨幅 5.1:≥1.5×2.0=3.0(bo−1 口径,触发)但 <1.5×4.0=6.0(bo 当根口径,误判 timeout)。
    from path2.atoms.throwback import evaluate_throwback
    rows = _series_with_atr2(20, base=100.0)
    rows[19] = (100.0, 130.0, 100.0, 103.0, 5000)    # bo 巨幅 TR=30
    tail = [
        (102.5, 103.0, 101.6, 102.0, 1000),   # 20
        (101.8, 102.0, 101.5, 101.7, 1000),   # 21 trough
        (101.7, 102.5, 101.6, 102.4, 1000),   # 22
        (102.4, 103.0, 101.8, 102.9, 1000),   # 23 → start=21
        (102.9, 106.6, 102.5, 106.0, 1000),   # 24 high−101.5=5.1
    ]
    rows += tail
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    r = evaluate_throwback(_bo_at(19), df, atr_window=14)
    assert r is not None
    assert r.end_idx == 23      # 若误用 ATR@bo 当根 → timeout → end=24,此断言抓出


def test_evaluate_anchor_measure_close():
    # 回落 low 跌破 high[bo−1]=101 但守住 close[bo−1]=100:默认(high)None;"close" 成功
    from path2.atoms.throwback import evaluate_throwback
    rows = _series_with_atr2(20, base=100.0)
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)
    tail = [
        (102.5, 103.0, 100.5, 102.0, 1000),   # 20 low=100.5<101 但 ≥100
        (101.8, 102.0, 100.4, 101.7, 1000),   # 21 trough=100.4
        (101.7, 102.5, 100.6, 102.4, 1000),   # 22
        (102.4, 103.0, 100.8, 102.9, 1000),   # 23 → start=21
        (102.9, 106.0, 102.5, 105.5, 1000),   # 24 high−100.4=5.6≥3 → end=23
    ]
    rows += tail
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    assert evaluate_throwback(_bo_at(19), df, atr_window=14) is None
    r = evaluate_throwback(_bo_at(19), df, atr_window=14, anchor_measure="close")
    assert r is not None and r.start_idx == 21 and r.end_idx == 23
