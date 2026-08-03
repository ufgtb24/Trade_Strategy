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


# ---- _find_confirm_idx(v3:K-bar trough-age 确认 + rise-before-confirm 守门)----


def test_find_confirm_idx_monotonic_confirms_at_trough_plus_K():
    """K=2:trough=1 后 idx 2/3 不刷新 → i=3 满足 i-trough=2≥K,断信号后 confirm。"""
    from path2.atoms.throwback import _find_confirm_idx
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),   # 0 bo(anchor 由 caller 传)
        (98.0, 98.5, 95.0, 96.0, 1000),    # 1 trough low=95
        (96.0, 97.0, 95.5, 96.8, 1000),    # 2 不创新低 + bullish(stop signal)
        (96.8, 98.0, 95.6, 97.9, 1000),    # 3 不创新低 + bullish → i-trough=2≥2 → confirm@3
    ]
    df = _make_df(rows)
    r = _find_confirm_idx(df, bo_idx=0, anchor=90.0, max_start_gap=10,
                        atr=1.0, stop_confirm_bars=2, big_rise_k=99.0)
    assert r == (3, 1)   # (confirm_idx, trough_idx)


def test_find_confirm_idx_zigzag_confirms_with_new_judgment():
    """锯齿横盘(旧'两连不创新低'判据必然失败,新 K 判据能过):
    low 序列 trough=95 → 95.6 → 95.4(小回调,但不刷 95)→ 95.5 → 95.45 → 95.5(K=2 后 confirm)。
    只要 trough 在窗内未被刷,i-trough≥K 就 confirm。
    """
    from path2.atoms.throwback import _find_confirm_idx
    rows = [
        (100.0, 100.5, 99.5, 100.0, 1000),  # 0 bo
        (99.0, 99.5, 95.0, 96.0, 1000),     # 1 trough low=95
        (96.0, 96.5, 95.6, 96.2, 1000),     # 2 不刷 + bullish
        (96.2, 96.5, 95.4, 95.5, 1000),     # 3 不刷 + no signal → i-trough=2≥2,证据窗 [1,3] 内有 bullish@2 → confirm@3
    ]
    df = _make_df(rows)
    r = _find_confirm_idx(df, bo_idx=0, anchor=90.0, max_start_gap=10,
                        atr=1.0, stop_confirm_bars=2, big_rise_k=99.0)
    assert r == (3, 1)


def test_find_confirm_idx_no_stop_signal_returns_none():
    """[trough, i] 内无任何 stop signal(全阴线且无下影/收涨/gap_up)→ 扫满 timeout。"""
    from path2.atoms.throwback import _find_confirm_idx
    # 全根 close < open 且 close < prev_close 且无长下影 → 无 stop signal
    rows = [(100.0 - i, 100.5 - i, 99.0 - i - 0.5, 99.5 - i, 1000) for i in range(6)]
    df = _make_df(rows)  # 每根创新低 → trough 一直更新 → i-trough 恒 0
    r = _find_confirm_idx(df, bo_idx=0, anchor=80.0, max_start_gap=5,
                        atr=1.0, stop_confirm_bars=2, big_rise_k=99.0)
    assert r is None


def test_find_confirm_idx_anchor_break_returns_none():
    """任一根 measure_at(i, support_measure) < anchor → phase1_break gate → None。"""
    from path2.atoms.throwback import _find_confirm_idx
    rows = [
        (100.0, 100.0, 99.5, 100.0, 1000),
        (100.0, 100.0, 100.0, 100.0, 1000),
        (98.0, 99.0, 98.0, 98.5, 1000),   # i=2 low=98 < anchor=100
    ]
    df = _make_df(rows)
    r = _find_confirm_idx(df, bo_idx=1, anchor=100.0, max_start_gap=10,
                        atr=1.0, stop_confirm_bars=2, big_rise_k=99.0)
    assert r is None


def test_find_confirm_idx_rise_before_confirm_returns_none():
    """确认前发生大涨(high[i]-base_min ≥ big_rise_k×atr)→ phase1_rise_before_confirm gate → None。
    fixture:trough@1 low=95,i=2 high=99, base_min=low[1]=95 → rise=4 ≥ 1.5×2=3 → 不产。"""
    from path2.atoms.throwback import _find_confirm_idx
    rows = [
        (100.0, 100.5, 99.0, 100.0, 1000),   # 0 bo
        (99.0, 99.5, 95.0, 96.0, 1000),      # 1 trough low=95
        (96.0, 99.0, 95.5, 98.8, 1000),      # 2 high=99, high-base_min=99-95=4 ≥ 1.5×2 → rise before confirm
    ]
    df = _make_df(rows)
    r = _find_confirm_idx(df, bo_idx=0, anchor=90.0, max_start_gap=10,
                        atr=2.0, stop_confirm_bars=2, big_rise_k=1.5)
    assert r is None


def test_find_confirm_idx_budget_cutoff():
    """窗宽 max_start_gap=3:trough@4 → confirm 需 i≥6 但窗止于 bo+3=3 → 扫满无 confirm → None。"""
    from path2.atoms.throwback import _find_confirm_idx
    rows = [
        (100.0, 100.5, 99.0, 100.0, 1000),    # 0 bo
        (99.0, 99.5, 96.0, 97.0, 1000),       # 1
        (97.0, 97.5, 95.5, 96.0, 1000),       # 2
        (96.0, 96.5, 95.0, 95.5, 1000),       # 3 trough low=95(窗末)
        (95.5, 96.5, 95.1, 96.3, 1000),       # 4 不刷 + bullish
        (96.3, 97.0, 95.2, 96.8, 1000),       # 5 不刷 + bullish
    ]
    df = _make_df(rows)
    # max_start_gap=3 → 扫 i∈[1,3] → 每根都在刷新 trough → i-trough=0 → 无 confirm
    r = _find_confirm_idx(df, bo_idx=0, anchor=90.0, max_start_gap=3,
                        atr=1.0, stop_confirm_bars=2, big_rise_k=99.0)
    assert r is None
    # 放宽 max_start_gap=7 → 扫到 i=5 时 trough@3,i-trough=2≥K,证据 [3,5] 有 bullish → confirm@5
    r2 = _find_confirm_idx(df, bo_idx=0, anchor=90.0, max_start_gap=7,
                         atr=1.0, stop_confirm_bars=2, big_rise_k=99.0)
    assert r2 == (5, 3)


def test_find_confirm_idx_support_measure_close_survives_low_dip():
    """low 跌破 anchor 但 close 守住:'low' 破位 → None;'close' 存活并 confirm。"""
    from path2.atoms.throwback import _find_confirm_idx
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),    # 0 bo
        (98.0, 98.5, 94.5, 96.0, 1000),     # 1 low=94.5<anchor=95, close=96
        (96.0, 96.5, 95.2, 95.8, 1000),     # 2 不刷 trough(仍 @1)
        (95.8, 96.5, 95.4, 96.3, 1000),     # 3 不刷 + bullish → i-trough=2≥2 → confirm@3
    ]
    df = _make_df(rows)
    assert _find_confirm_idx(df, bo_idx=0, anchor=95.0, max_start_gap=10,
                           atr=1.0, stop_confirm_bars=2, big_rise_k=99.0,
                           support_measure="low") is None
    r = _find_confirm_idx(df, bo_idx=0, anchor=95.0, max_start_gap=10,
                        atr=1.0, stop_confirm_bars=2, big_rise_k=99.0,
                        support_measure="close")
    assert r == (3, 1)


# ---- _find_end_idx(v3:接 trough_idx / base_min 锚 trough / 产 3 outcome)----


def test_find_end_idx_rise_outcome():
    """confirm 后 base_min = min low over [trough, confirm-1]='trough 的 low'。
    fixture:trough=0/confirm=1;i=2 high-base=2.0≥1.5,end=1,outcome='rise'。"""
    from path2.atoms.throwback import _find_end_idx
    rows = [
        (95.5, 96.0, 95.0, 95.5, 1000),   # 0 trough low=95
        (95.5, 96.0, 95.3, 95.8, 1000),   # 1 confirm
        (96.0, 97.0, 95.5, 96.8, 1000),   # 2 high-95=2.0 ≥ 1.5 → end=1, outcome=rise
    ]
    df = _make_df(rows)
    r = _find_end_idx(df, confirm_idx=1, trough_idx=0, anchor=90.0,
                      max_window=10, atr=1.0, big_rise_k=1.5)
    assert r == (1, "rise")


def test_find_end_idx_break_produces_event_now():
    """破位在 confirm 后 → 事件仍产,outcome='break',end=i-1。gate 仍 emit。"""
    from path2.atoms.throwback import _find_end_idx
    from path2.dag.gate_failure import GateFailure
    rows = [
        (95.0, 95.5, 95.0, 95.2, 1000),   # 0 trough
        (95.2, 95.5, 95.1, 95.3, 1000),   # 1 confirm
        (95.3, 95.5, 89.0, 90.0, 1000),   # 2 low=89 < anchor=90 破位
    ]
    df = _make_df(rows)
    captured: list[GateFailure] = []
    r = _find_end_idx(df, confirm_idx=1, trough_idx=0, anchor=90.0,
                      max_window=10, atr=1.0, big_rise_k=99.0,
                      on_gate=captured.append, bo_idx=0)
    assert r == (1, "break")   # end=i-1=1(单点窗:confirm 后立刻破位)
    breaks = [g for g in captured if g.gate_name == 'phase2_break']
    assert len(breaks) == 1


def test_find_end_idx_timeout_outcome():
    """扫满无 rise 无 break → outcome='timeout',end=min(confirm+max_window, len-1)。"""
    from path2.atoms.throwback import _find_end_idx
    rows = [(95.0, 95.4, 94.9, 95.1, 1000) for _ in range(8)]
    df = _make_df(rows)
    # confirm=1, max_window=5, len=8 → end=min(6,7)=6
    r = _find_end_idx(df, confirm_idx=1, trough_idx=0, anchor=90.0,
                      max_window=5, atr=1.0, big_rise_k=99.0)
    assert r == (6, "timeout")


def test_find_end_idx_base_min_anchored_at_trough():
    """base_min 锚 trough:trough low=95,confirm 处 low=98,i=2 high-95=4 → rise;
    若错锚 confirm(base_min=98),high-98=1 < 1.5 → 误 timeout。断值验证锚点正确。"""
    from path2.atoms.throwback import _find_end_idx
    rows = [
        (99.0, 99.5, 95.0, 96.0, 1000),   # 0 trough low=95
        (96.0, 98.5, 98.0, 98.3, 1000),   # 1 confirm  low=98(> trough)
        (98.3, 99.0, 98.2, 98.9, 1000),   # 2 high=99, high-base_min=99-95=4 ≥ 1.5 → rise, end=1
    ]
    df = _make_df(rows)
    r = _find_end_idx(df, confirm_idx=1, trough_idx=0, anchor=90.0,
                      max_window=10, atr=1.0, big_rise_k=1.5)
    assert r == (1, "rise")


def test_find_end_idx_base_min_excludes_current_bar():
    """base_min = running min over [trough, i-1](不含当前 i);
    i=2 的 low=93 不进 base_min → rise 用 base_min=95 断。"""
    from path2.atoms.throwback import _find_end_idx
    rows = [
        (95.0, 95.2, 95.0, 95.1, 1000),   # 0 trough
        (95.1, 95.3, 95.0, 95.2, 1000),   # 1 confirm
        (95.2, 99.0, 93.0, 95.0, 1000),   # 2 low=93 不进 base_min;high-95=4≥1.5 → end=1
    ]
    df = _make_df(rows)
    r = _find_end_idx(df, confirm_idx=1, trough_idx=0, anchor=80.0,
                      max_window=10, atr=1.0, big_rise_k=1.5)
    assert r == (1, "rise")


def test_find_end_idx_support_measure_close_survives_low_dip():
    """low 跌破 anchor 但 close 守住:'low' 破位 outcome='break';'close' timeout。"""
    from path2.atoms.throwback import _find_end_idx
    rows = [
        (95.0, 95.5, 95.0, 95.2, 1000),   # 0 trough
        (95.2, 95.5, 95.0, 95.3, 1000),   # 1 confirm
        (95.0, 95.5, 89.0, 95.1, 1000),   # 2 low=89<90,close=95.1
        (95.1, 95.6, 95.0, 95.3, 1000),   # 3
    ]
    df = _make_df(rows)
    r_low = _find_end_idx(df, confirm_idx=1, trough_idx=0, anchor=90.0,
                          max_window=5, atr=1.0, big_rise_k=99.0)
    assert r_low == (1, "break")
    r_close = _find_end_idx(df, confirm_idx=1, trough_idx=0, anchor=90.0,
                            max_window=5, atr=1.0, big_rise_k=99.0,
                            support_measure="close")
    # timeout: end = min(confirm+max_window, len-1) = min(6, 3) = 3
    assert r_close == (3, "timeout")


# ---- evaluate_throwback(v3 端到端)----


def _series_with_atr2(n, base=100.0):
    """每根 high-low=2、close 平、无跳空 → ATR≈2.0。返回 rows。"""
    return [(base, base + 1.0, base - 1.0, base, 1000) for _ in range(n)]


def _bo_at(idx):
    from path2.atoms.breakout import BOEvent
    return BOEvent(event_id=f"bo_{idx}", start_idx=idx, end_idx=idx, confirm_idx=idx)


def test_evaluate_returns_none_when_bo_idx_zero():
    from path2.atoms.throwback import evaluate_throwback
    df = pd.DataFrame(_series_with_atr2(30), columns=['open', 'high', 'low', 'close', 'volume'])
    assert evaluate_throwback(_bo_at(0), df) is None


def test_evaluate_returns_none_when_atr_zero():
    from path2.atoms.throwback import evaluate_throwback
    # 短序列,bo_idx-1 < atr_window-1 → atr==0 → None
    df = pd.DataFrame(_series_with_atr2(5), columns=['open', 'high', 'low', 'close', 'volume'])
    assert evaluate_throwback(_bo_at(3), df) is None


def test_evaluate_returns_none_when_bo_is_last_bar():
    """bo 落在数据末根:无后续 bar 可扫 → 返回 None,不得越界抛 IndexError。

    phase 1 的 base_min 若在循环外按 df['low'].iat[bo_idx+1] 初始化,
    此场景下会越界(全集扫描中整只股票崩掉)。
    """
    from path2.atoms.throwback import evaluate_throwback
    df = pd.DataFrame(_series_with_atr2(20), columns=['open', 'high', 'low', 'close', 'volume'])
    assert evaluate_throwback(_bo_at(len(df) - 1), df) is None


def test_evaluate_rise_outcome():
    """成功场景:phase1 confirm@22,phase2 rise@24 → end=23, outcome='rise'。"""
    from path2.atoms.throwback import evaluate_throwback, ThrowbackResult
    rows = _series_with_atr2(20, base=100.0)         # anchor=high[18]=101,ATR@18=2
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)    # bo 峰 high=104
    tail = [
        (102.5, 103.0, 101.6, 102.0, 1000),   # 20 trough low=101.6? 后面 21 更低
        (101.8, 102.0, 101.5, 101.7, 1000),   # 21 trough low=101.5
        (101.7, 102.5, 101.6, 102.4, 1000),   # 22 不刷 + bullish → i-trough=1,K=2 未到
        (102.4, 103.0, 101.8, 102.9, 1000),   # 23 不刷 + bullish → i-trough=2 → confirm@23
        (102.9, 105.5, 102.5, 105.0, 1000),   # 24 high=105.5-base(101.5)=4≥3(=1.5×2)→ end=23, rise
    ]
    rows += tail
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    r = evaluate_throwback(_bo_at(19), df, atr_window=14,
                           big_rise_k=1.5, stop_confirm_bars=2,
                           support_measure="low")
    # rise 在 confirm 当天 (i=24) 出现 → end=i-1=23 == confirm_idx
    # start_idx=confirm=23, end_idx=23, confirm_idx=confirm=23, outcome='rise'
    assert isinstance(r, ThrowbackResult)
    assert r == ThrowbackResult(23, 23, "rise")


def test_evaluate_break_outcome_after_confirm():
    """confirm 后破位 → 事件仍产,outcome='break'。"""
    from path2.atoms.throwback import evaluate_throwback
    rows = _series_with_atr2(20, base=100.0)
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)     # bo
    tail = [
        (102.5, 103.0, 101.6, 102.0, 1000),   # 20
        (101.8, 102.0, 101.5, 101.7, 1000),   # 21 trough
        (101.7, 102.5, 101.6, 102.4, 1000),   # 22
        (102.4, 103.0, 101.8, 102.9, 1000),   # 23 confirm
        (102.9, 103.0, 100.5, 100.6, 1000),   # 24 low=100.5 < anchor=101 → break, end=23
    ]
    rows += tail
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    r = evaluate_throwback(_bo_at(19), df, atr_window=14,
                           big_rise_k=99.0, stop_confirm_bars=2,
                           support_measure="low")
    assert r is not None
    assert r.outcome == "break"
    assert r.start_idx == 23 and r.end_idx == 23


def test_evaluate_timeout_outcome():
    """confirm 后无 rise 无 break,扫满 → outcome='timeout'。"""
    from path2.atoms.throwback import evaluate_throwback
    rows = _series_with_atr2(20, base=100.0)
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)     # bo
    tail = [
        (102.5, 103.0, 101.6, 102.0, 1000),   # 20
        (101.8, 102.0, 101.5, 101.7, 1000),   # 21 trough
        (101.7, 102.5, 101.6, 102.4, 1000),   # 22
        (102.4, 103.0, 101.8, 102.9, 1000),   # 23 confirm
        (102.9, 103.0, 101.9, 102.5, 1000),   # 24 无破位无大涨
        (102.5, 103.0, 101.7, 102.4, 1000),   # 25 同上
        (102.4, 103.0, 101.8, 102.6, 1000),   # 26 同上
        (102.6, 103.0, 101.9, 102.5, 1000),   # 27 同上
        (102.5, 103.0, 101.8, 102.4, 1000),   # 28 同上,confirm+max_window=23+5=28
    ]
    rows += tail
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    r = evaluate_throwback(_bo_at(19), df, atr_window=14, max_window=5,
                           big_rise_k=99.0, stop_confirm_bars=2,
                           support_measure="low")
    assert r is not None
    assert r.outcome == "timeout"
    assert r.start_idx == 23 and r.end_idx == 28


def test_evaluate_none_when_anchor_break_before_confirm():
    """confirm 之前 anchor 破位 → None(事件从未存在)。"""
    from path2.atoms.throwback import evaluate_throwback
    rows = _series_with_atr2(20, base=100.0)
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)   # bo, anchor = high[18]=101
    tail = [(100.0, 100.5, 99.0, 99.5, 1000)]        # 20 low=99 < 101
    rows += tail
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    r = evaluate_throwback(_bo_at(19), df, atr_window=14,
                           big_rise_k=1.5, stop_confirm_bars=2,
                           support_measure="low")
    assert r is None


def test_evaluate_none_when_rise_before_confirm():
    """confirm 之前发生大涨 → None(V 型反转,现实中买不到)。"""
    from path2.atoms.throwback import evaluate_throwback
    rows = _series_with_atr2(20, base=100.0)
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)   # bo
    tail = [
        (102.0, 102.5, 101.5, 102.0, 1000),   # 20 trough low=101.5
        (102.0, 108.0, 102.0, 107.5, 1000),   # 21 high-base(101.5)=6.5 ≥ 1.5×2=3 → rise before confirm
    ]
    rows += tail
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    r = evaluate_throwback(_bo_at(19), df, atr_window=14,
                           big_rise_k=1.5, stop_confirm_bars=2,
                           support_measure="low")
    assert r is None


def test_evaluate_atr_uses_bo_minus_1():
    """bo 当根巨幅 TR 不污染 ATR:仍用 bo-1 处 ATR。"""
    from path2.atoms.throwback import evaluate_throwback
    rows = _series_with_atr2(20, base=100.0)
    rows[19] = (100.0, 130.0, 100.0, 103.0, 5000)    # bo 巨幅 TR=30
    tail = [
        (102.5, 103.0, 101.6, 102.0, 1000),   # 20
        (101.8, 102.0, 101.5, 101.7, 1000),   # 21 trough
        (101.7, 102.5, 101.6, 102.4, 1000),   # 22
        (102.4, 103.0, 101.8, 102.9, 1000),   # 23 confirm
        (102.9, 106.6, 102.5, 106.0, 1000),   # 24 high-base=5.1
    ]
    rows += tail
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    r = evaluate_throwback(_bo_at(19), df, atr_window=14,
                           stop_confirm_bars=2, support_measure="low")
    assert r is not None
    # ATR@bo-1≈2.0 → rise 5.1 ≥ 1.5×2=3 → end=23, rise
    # 若误用 ATR@bo 当根≈4.0 → rise 5.1 < 1.5×4=6 → timeout → end=23+5=28
    assert r.outcome == "rise"
    assert r.end_idx == 23


