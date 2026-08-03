"""tb detector 端到端 fixture:一次数据流 3 个 bo → 3 事件覆盖 rise/break/timeout。

真跑 detector(不 monkeypatch evaluate_throwback),验证:
1. 三 outcome 各产一个 tb event;
2. event.outcome 字段正确;
3. event.anchor_bo_id 与 bo.event_id 对齐;
4. events 按 end_idx 升序 yield。
"""
from __future__ import annotations

import pandas as pd

from path2.atoms.breakout import BOEvent
from path2.atoms.throwback import ThrowbackDetector


def _bo(idx):
    return BOEvent(event_id=f"bo_{idx}", start_idx=idx, end_idx=idx, confirm_idx=idx)


def _base_series(n, base=100.0):
    """ATR≈2.0 的基座序列。"""
    return [(base, base + 1.0, base - 1.0, base, 1000) for _ in range(n)]


def test_e2e_three_outcomes_in_one_run():
    """构造一个 df 让三个 bo 各产 rise/break/timeout 一个事件。"""
    # 段 1(idx 0-19):基座,ATR@18=2.0,anchor=high[18]=101
    rows = _base_series(20, base=100.0)
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)   # bo_1 @19,峰 high=104

    # bo_1 后 → 'rise' outcome(confirm@23, rise@24, end=23)
    tail_rise = [
        (102.5, 103.0, 101.6, 102.0, 1000),   # 20
        (101.8, 102.0, 101.5, 101.7, 1000),   # 21 trough low=101.5
        (101.7, 102.5, 101.6, 102.4, 1000),   # 22
        (102.4, 103.0, 101.8, 102.9, 1000),   # 23 confirm(bullish@23,K=2 达)
        (102.9, 105.5, 102.5, 105.0, 1000),   # 24 high-101.5=4>=3 → rise, end=23
    ]
    rows += tail_rise

    # 段 2(idx 25-44):新基座,ATR≈2.0,anchor=high[43]=101
    rows += _base_series(19, base=100.0)   # 25-43
    rows.append((100.0, 104.0, 100.0, 103.0, 5000))   # bo_2 @44 (idx 44)

    # bo_2 后 → 'break' outcome(confirm@48, break@49, end=48)
    tail_break = [
        (102.5, 103.0, 101.6, 102.0, 1000),   # 45
        (101.8, 102.0, 101.5, 101.7, 1000),   # 46 trough
        (101.7, 102.5, 101.6, 102.4, 1000),   # 47
        (102.4, 103.0, 101.8, 102.9, 1000),   # 48 confirm
        (102.9, 103.0, 100.5, 100.6, 1000),   # 49 low=100.5<101 → break, end=48
    ]
    rows += tail_break

    # 段 3(idx 50-69):新基座,anchor=high[68]=101
    rows += _base_series(19, base=100.0)   # 50-68
    rows.append((100.0, 104.0, 100.0, 103.0, 5000))   # bo_3 @69

    # bo_3 后 → 'timeout' outcome(confirm@73, 无 rise/break, end=73+5=78)
    tail_timeout = [
        (102.5, 103.0, 101.6, 102.0, 1000),   # 70
        (101.8, 102.0, 101.5, 101.7, 1000),   # 71 trough
        (101.7, 102.5, 101.6, 102.4, 1000),   # 72
        (102.4, 103.0, 101.8, 102.9, 1000),   # 73 confirm
        (102.9, 103.0, 101.9, 102.5, 1000),   # 74
        (102.5, 103.0, 101.7, 102.4, 1000),   # 75
        (102.4, 103.0, 101.8, 102.6, 1000),   # 76
        (102.6, 103.0, 101.9, 102.5, 1000),   # 77
        (102.5, 103.0, 101.8, 102.4, 1000),   # 78 timeout=73+5
    ]
    rows += tail_timeout

    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    detector = ThrowbackDetector()   # 新 default: max_start_gap=7, stop_confirm_bars=2, support_measure='low'
    bos = [_bo(19), _bo(44), _bo(69)]
    events = list(detector.detect(bos, df))

    assert len(events) == 3
    outcomes = sorted(e.outcome for e in events)
    assert outcomes == ["break", "rise", "timeout"]

    # anchor_bo_id 对齐
    by_anchor = {e.anchor_bo_id: e for e in events}
    assert by_anchor["bo_19"].outcome == "rise"
    assert by_anchor["bo_44"].outcome == "break"
    assert by_anchor["bo_69"].outcome == "timeout"

    # end_idx 升序 yield(run() 不变式)
    end_idxs = [e.end_idx for e in events]
    assert end_idxs == sorted(end_idxs)


def test_e2e_no_event_when_rise_before_confirm():
    """rise-before-confirm 场景端到端:detector 不产任何事件。"""
    rows = _base_series(20, base=100.0)
    rows[19] = (100.0, 104.0, 100.0, 103.0, 5000)   # bo
    # confirm 前发生 V 型反弹:trough@20, rise@21
    rows += [
        (102.0, 102.5, 101.5, 102.0, 1000),   # 20 trough low=101.5
        (102.0, 108.0, 102.0, 107.5, 1000),   # 21 high-base=6.5 ≥ 3 → rise before confirm
    ]
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    events = list(ThrowbackDetector().detect([_bo(19)], df))
    assert events == []
