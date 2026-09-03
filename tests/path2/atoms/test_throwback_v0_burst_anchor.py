"""tb v0 锚 last_bo:detect 消费 burst 流、anchor=last_bo 上一根 bar 价(非串内 min)。"""
from __future__ import annotations

import pandas as pd

from path2.atoms.breakout import BOEvent, BurstEvent
from path2.atoms.throwback_v0 import ThrowbackDetectorV0, evaluate_throwback


def _make_df(rows):
    return pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])


def _bo(idx):
    return BOEvent(start_idx=idx, end_idx=idx, confirm_idx=idx, instance_id=f"bo_{idx}#0")


def _burst(*bos):
    first, last = bos[0], bos[-1]
    return BurstEvent(start_idx=first.start_idx, end_idx=last.end_idx,
                      confirm_idx=last.end_idx, members=tuple(bos))


def _base_series(n, base=100.0):
    return [(base, base + 1.0, base - 1.0, base, 1000) for _ in range(n)]


def test_evaluate_anchor_override_controls_phase1_break():
    """显式 anchor 生效:anchor=99(低)时回踩 close 守住 → 事件存活;anchor=103(高)时 phase1_break。"""
    from path2.atoms.throwback_v0 import evaluate_throwback
    rows = _base_series(20, base=100.0)
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)   # bo_19
    rows += [(102.5, 103.0, 101.6, 102.0, 1000),    # 20 trough low=101.6
             (101.8, 102.0, 101.7, 101.7, 1000),    # 21 low≥101.6 不刷新 trough(K=2 需 trough 停 20)
             (101.7, 102.5, 101.6, 102.4, 1000)]    # 22 阳线止跌 → confirm
    df = _make_df(rows)
    bo = _bo(19)
    # anchor=99:close[20..22]=102.0/101.7/102.4 全守住 → confirm@22
    r = evaluate_throwback(bo, df, anchor=99.0, atr_window=14,
                           max_start_gap=7, stop_confirm_bars=2)
    assert r is not None and r.start_idx == 22
    # anchor=103:close[20]=102.0 < 103 → phase1_break → None
    r2 = evaluate_throwback(bo, df, anchor=103.0, atr_window=14,
                            max_start_gap=7, stop_confirm_bars=2)
    assert r2 is None


def test_detect_single_member_burst_uses_lastbo_prev_close_as_anchor():
    """单 bo burst:anchor=last_bo 上一根 bar close(close[18]=100);回踩 close 守住 → 事件存活。"""
    rows = _base_series(20, base=100.0)
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)   # bo_19 当根 close=103;anchor=close[18]=100(基座)
    rows += [(103.5, 104.0, 102.8, 103.6, 1000),    # 20 close 103.6 ≥ 100
             (103.4, 103.6, 102.6, 103.3, 1000),    # 21 close 103.3 ≥ 100(trough low=102.6)
             (103.3, 104.5, 103.0, 104.2, 1000)]    # 22 close 104.2 阳线 → confirm
    df = _make_df(rows)
    det = ThrowbackDetectorV0(anchor_measure="close", support_measure="close",
                              stop_confirm_bars=1)
    events = list(det.detect([_burst(_bo(19))], df))
    assert len(events) == 1
    assert events[0].anchor_bo_id == "bo_19#0"   # 交错标注后取源 bo 的 instance_id


def test_detect_multi_member_anchor_is_lastbo_prev():
    """双 bo burst:anchor=last_bo(bo_6)上一根 bar close(close[5]=100);回踩 close 守住 → 不 break。"""
    rows = _base_series(7, base=100.0)   # 7 根基座:回踩段落在 idx 7/8/9(原 10 根会让回踩落 10-12 而 7-9 是基座 close=100<103)
    rows[4] = (100.0, 105.0, 100.0, 103.0, 5000)    # bo_4 close=103
    rows[6] = (103.0, 106.0, 102.5, 104.5, 5000)    # bo_6 当根 close=104.5;anchor=close[5]=100(基座)
    rows += [(104.0, 104.5, 103.4, 103.8, 1000),    # 7 close 103.8 ≥ 100
             (103.5, 104.0, 103.2, 103.5, 1000),    # 8 close 103.5 ≥ 100(trough low=103.2)
             (103.4, 104.2, 103.3, 104.0, 1000)]    # 9 close 104.0 阳线 → confirm(不刷新 trough)
    df = _make_df(rows)
    det = ThrowbackDetectorV0(anchor_measure="close", support_measure="close",
                              stop_confirm_bars=1, atr_window=5)   # 数据仅 10 根:ATR@5 需 period≤6
    events = list(det.detect([_burst(_bo(4), _bo(6))], df))
    assert len(events) == 1
    assert events[0].anchor_bo_id == "bo_6#0"   # last_bo 是锚
