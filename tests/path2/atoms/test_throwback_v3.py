"""tb v3 多段 re-entry 状态机行为测试。

对照 spec §2 状态机逐判据验证:
  1. re-entry:首段 weak 退出后重新企稳 → 第二段产出(核心新行为)
  2. 段级 vs 全局:weak 退段后可再开段;破全局 anchor 以 'break' 截断且不再开段
  3. rise / timeout 退段后各自 re-entry
  4. 段外 rise-before-confirm → 无段且整 bo 终止
  5. 段外破 anchor → 无段且终止
  6. 预算扫满 in_segment → 强制 timeout 闭合;0 段 → 空列表
  7. anchor_mode 三模式(last_bo/min_bo/span_min)定锚差异
  8. 容器结构:segments 顺序/span/confirm/outcome
  9. 非法参数 ValueError

数据约定:judged=reference=close,stop_confirm_bars=1,big_rise_k=3.0,atr=1.0;
anchor=90.0(测试 1/3/4/5/6 不破);最大数据 9 根,已逐根手推。
"""
from __future__ import annotations

import pandas as pd
import pytest

from path2.atoms.breakout import BOEvent, BurstEvent
from path2.atoms.throwback_v3 import (
    ThrowbackDetectorV3, ThrowbackEventV3, enumerate_segments_v3,
)


def _make_df(rows):
    return pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])


def _bo(idx):
    return BOEvent(start_idx=idx, end_idx=idx, confirm_idx=idx, instance_id=f"bo_{idx}#0")


def _burst(*bos):
    first, last = bos[0], bos[-1]
    return BurstEvent(start_idx=first.start_idx, end_idx=last.end_idx,
                      confirm_idx=last.end_idx, members=tuple(bos))


def _atr_one_series(n, base=100.0):
    """ATR≈2.0 的基座序列(高=+1 低=-1)。"""
    return [(base, base + 1.0, base - 1.0, base, 1000) for _ in range(n)]


def test_weak_exit_then_reentry():
    """首段 weak 退出后段外重新企稳 → 第二段产出(容器 segments 长度 2)。

    推演:bo@0;trough@1(close=96.0);confirm@2(阳线,i-trough=1≥K=1,
    [1,2] 含 bullish);weak@3(close=95.6<96.0)→ 段1=(2,2,'weak');
    段外从 3 起:trough=3(close=95.6);i=4 阴线无 stop signal 不 confirm;
    i=5 阳线 confirm@5 → 段2 enter=5;预算末 6 仍段内 → 强制 timeout 闭合。
    """
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),   # 0 bo
        (96.0, 96.5, 95.8, 96.0, 1000),    # 1 trough(close=96.0)
        (96.0, 96.8, 95.9, 96.3, 1000),    # 2 confirm(阳线)→ 段1 enter
        (96.3, 96.5, 94.0, 95.6, 1000),    # 3 close=95.6<96.0 → weak,段1=(2,2,'weak')
        (95.6, 95.9, 95.3, 95.55, 1000),   # 4 阴线+无 signal(下影 0.43<0.5)→ 不 confirm
        (95.7, 96.2, 95.5, 96.0, 1000),    # 5 阳线 → confirm@5 → 段2 enter
        (96.0, 96.3, 95.8, 96.1, 1000),    # 6 预算末(bo+max_start_gap=6)→ 强制闭合
    ]
    df = _make_df(rows)
    segs = enumerate_segments_v3(df, bo_idx=0, anchor=90.0,
                                 max_start_gap=6, max_window=5, atr=1.0,
                                 stop_confirm_bars=1, big_rise_k=3.0)
    assert segs == [(2, 2, 'weak'), (5, 6, 'timeout')]


def test_weak_is_segment_level_break_is_global():
    """段级 vs 全局:段1 weak 后 re-entry 段2 成立;段2 内破 anchor → 'break'
    截断且不再开段(整 bo 终止)。

    推演:段1 同测试 1(weak@3,段1=(2,2,'weak'));段2 confirm@5;
    段2 内 i=6/7 正常;破 anchor@8(close=89.0<90)→ 段2=(5,7,'break')。
    """
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),   # 0 bo
        (96.0, 96.5, 95.8, 96.0, 1000),    # 1 trough
        (96.0, 96.8, 95.9, 96.3, 1000),    # 2 confirm → 段1 enter
        (96.3, 96.5, 94.0, 95.6, 1000),    # 3 weak → 段1=(2,2,'weak')
        (95.6, 95.9, 95.3, 95.55, 1000),   # 4 无 signal
        (95.7, 96.2, 95.5, 96.0, 1000),    # 5 confirm → 段2 enter
        (96.0, 96.3, 95.8, 96.1, 1000),    # 6 段内正常
        (96.1, 96.4, 95.9, 96.2, 1000),    # 7 段内正常
        (96.2, 96.5, 88.0, 89.0, 1000),    # 8 close=89.0<90 → 全局终止,段2 截断
    ]
    df = _make_df(rows)
    segs = enumerate_segments_v3(df, bo_idx=0, anchor=90.0,
                                 max_start_gap=8, max_window=5, atr=1.0,
                                 stop_confirm_bars=1, big_rise_k=3.0)
    assert segs == [(2, 2, 'weak'), (5, 7, 'break')]


def test_rise_exit_then_reentry():
    """rise 段退出后段外重新企稳 → 第二段(段1=(2,2,'rise'))。

    推演:confirm@2(段1 enter,trough@1);rise@3(high[3]-base_min=99.5-95.8
    =3.7 ≥ 3.0)→ 段1=(2,2,'rise');段外从 3 起:trough 起点 3(close=99.0),
    base_min 重置为 low[3]=96.0;rise-before-confirm 阈值 3.0 约束段外
    high[i] < 99.0;i=4 close 98.7 刷新 trough=4 且无 signal(阴线、下影
    0.33<0.5);i=5 阳线(98.8>98.7)→ confirm@5 → 段2 enter;预算末 6
    强制闭合:段2=(5,6,'timeout')。
    """
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),   # 0 bo
        (96.0, 96.5, 95.8, 96.0, 1000),    # 1 trough(close=96.0)
        (96.0, 96.8, 95.9, 96.3, 1000),    # 2 confirm → 段1 enter
        (96.3, 99.5, 96.0, 99.0, 1000),    # 3 rise(high-95.8=3.7≥3)→ 段1=(2,2,'rise')
        (98.9, 98.9, 98.6, 98.7, 1000),    # 4 close 98.7<99.0 刷 trough=4;无 signal
        (98.7, 98.9, 98.6, 98.8, 1000),    # 5 阳线 → confirm@5 → 段2 enter
        (98.8, 99.0, 98.7, 98.9, 1000),    # 6 预算末 → 强制闭合
    ]
    df = _make_df(rows)
    segs = enumerate_segments_v3(df, bo_idx=0, anchor=90.0,
                                 max_start_gap=6, max_window=5, atr=1.0,
                                 stop_confirm_bars=1, big_rise_k=3.0)
    assert segs == [(2, 2, 'rise'), (5, 6, 'timeout')]


def test_timeout_exit_then_reentry():
    """timeout 段退出后段外重新企稳 → 第二段(段1=(2,4,'timeout'))。

    推演:confirm@2(段1 enter,trough@1,close[1]=96.0);i=3 段内正常;
    i=4 timeout(i-enter=2≥max_window=2,timeout end=enter+max_window=4)
    → 段1=(2,4,'timeout');段外从 4 起:trough 起点 4(close=96.5),
    base_min=low[4]=96.1;i=5 刷新 trough(close=95.2<96.5);
    i=6 close_up(95.4>95.2)→ confirm@6 → 段2 enter;预算末 7 强制闭合。
    """
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),   # 0 bo
        (96.0, 96.5, 95.8, 96.0, 1000),    # 1 trough(close=96.0)
        (96.0, 96.8, 95.9, 96.3, 1000),    # 2 confirm → 段1 enter
        (96.3, 96.5, 96.0, 96.4, 1000),    # 3 段内正常(不破 96.0、不 rise、未超时)
        (96.4, 96.6, 96.1, 96.5, 1000),    # 4 timeout(i-enter=2≥2)→ 段1=(2,4,'timeout')
        (96.5, 96.8, 95.0, 95.2, 1000),    # 5 trough 刷新(close=95.2<96.5)
        (95.2, 95.6, 95.1, 95.4, 1000),    # 6 confirm(close_up 95.4>95.2)→ 段2 enter
        (95.4, 95.7, 95.2, 95.5, 1000),    # 7 预算末 → 强制闭合
    ]
    df = _make_df(rows)
    segs = enumerate_segments_v3(df, bo_idx=0, anchor=90.0,
                                 max_start_gap=7, max_window=2, atr=1.0,
                                 stop_confirm_bars=1, big_rise_k=3.0)
    assert segs == [(2, 4, 'timeout'), (6, 7, 'timeout')]


def test_rise_before_confirm_terminates():
    """段外 rise-before-confirm → 无段且整 bo 终止(返回空列表)。

    推演:confirm 前 high[2]-base_min=100.0-95.8=4.2 ≥ 3.0 → 终止。
    """
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),   # 0 bo
        (96.0, 96.5, 95.8, 96.0, 1000),    # 1 trough(close=96.0)
        (96.0, 100.0, 95.9, 99.5, 1000),   # 2 rise-before-confirm → 终止
    ]
    df = _make_df(rows)
    segs = enumerate_segments_v3(df, bo_idx=0, anchor=90.0,
                                 max_start_gap=5, max_window=5, atr=1.0,
                                 stop_confirm_bars=1, big_rise_k=3.0)
    assert segs == []


def test_anchor_break_before_any_segment_terminates():
    """段外破全局 anchor → 无段且终止(返回空列表)。

    推演:close[2]=89.5 < anchor=90.0 → 段外破 anchor → 终止。
    """
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),   # 0 bo
        (96.0, 96.5, 95.8, 96.0, 1000),    # 1 trough
        (96.0, 96.2, 89.0, 89.5, 1000),    # 2 close=89.5<90 → 段外破 anchor
    ]
    df = _make_df(rows)
    segs = enumerate_segments_v3(df, bo_idx=0, anchor=90.0,
                                 max_start_gap=5, max_window=5, atr=1.0,
                                 stop_confirm_bars=1, big_rise_k=3.0)
    assert segs == []


def test_anchor_mode_three_modes():
    """anchor_mode 三模式定锚差异(两个 df、六次 detect,判别力两两覆盖)。

    burst span=[15,19],members=bo_1@15(close=103)、bo_2@19(close=105)。
    df1(rows[18]=102.3):三模式 anchor = last_bo=close[18]=102.3 / min_bo=103
    / span_min=101.9。回踩 close∈[102.0,102.9]:
      last_bo(102.3)→ i=20 段外破 → 无事件;min_bo(103)→ i=20 破 → 无事件;
      span_min(101.9)→ 全程守住,confirm@22 → 有事件。
    df2(rows[18]=103.5):anchor = last_bo=103.5 / min_bo=103 / span_min=101.9。
      回踩 close∈[103.3,104.0]:
      last_bo(103.5)→ i=20 破 → 无事件;min_bo(103)→ 守住,confirm@22 → 有事件。
    两 df 合起来两两覆盖三模式(last_bo vs span_min / last_bo vs min_bo)。

    注:detect 默认 stop_confirm_bars=2;df1 中 i=20/21 两根不降、i=22 confirm
    (i-trough=2);df2 同。默认 big_rise_k=1.5、基座 ATR≈2 → rise 阈值≈3,
    回踩 high 差 ≤ 1.0 不触发。
    """
    # ── df1:rows[18]=102.3 → span_min=101.9 / min_bo=103 / last_bo=102.3 ──
    rows1 = _atr_one_series(15, base=100.0)                 # 0-14 基座
    rows1.append((100.0, 104.0, 100.0, 103.0, 5000))        # 15 bo_1
    rows1.append((102.0, 102.5, 101.5, 101.9, 1000))        # 16
    rows1.append((101.9, 102.4, 101.4, 101.9, 1000))        # 17
    rows1.append((102.3, 102.8, 101.8, 102.3, 1000))        # 18
    rows1.append((102.5, 106.0, 102.0, 105.0, 5000))        # 19 bo_2
    rows1.append((102.0, 102.5, 101.6, 102.0, 1000))        # 20 trough(close=102.0)
    rows1.append((102.0, 102.6, 101.9, 102.3, 1000))        # 21 阳线(close 不降)
    rows1.append((102.3, 102.7, 102.0, 102.5, 1000))        # 22 阳线 → confirm
    rows1.append((102.5, 102.8, 102.2, 102.6, 1000))        # 23 段内
    rows1.append((102.6, 102.9, 102.3, 102.7, 1000))        # 24 段内
    rows1.append((102.7, 103.0, 102.4, 102.8, 1000))        # 25 段内
    rows1.append((102.8, 103.1, 102.5, 102.9, 1000))        # 26 预算末(19+7=26)→ 闭合
    df1 = _make_df(rows1)
    burst1 = [_burst(_bo(15), _bo(19))]
    assert len(list(ThrowbackDetectorV3(anchor_mode='span_min').detect(burst1, df1))) == 1
    assert list(ThrowbackDetectorV3(anchor_mode='last_bo').detect(burst1, df1)) == []
    assert list(ThrowbackDetectorV3(anchor_mode='min_bo').detect(burst1, df1)) == []

    # ── df2:rows[18]=103.5 → last_bo=103.5 / min_bo=103(区分 last_bo vs min_bo)──
    rows2 = _atr_one_series(15, base=100.0)
    rows2.append((100.0, 104.0, 100.0, 103.0, 5000))        # 15 bo_1
    rows2.append((103.0, 103.5, 102.5, 103.2, 1000))        # 16
    rows2.append((103.2, 103.7, 102.7, 103.4, 1000))        # 17
    rows2.append((103.5, 104.0, 103.0, 103.5, 1000))        # 18
    rows2.append((103.5, 106.0, 103.0, 105.0, 5000))        # 19 bo_2
    rows2.append((103.3, 103.8, 102.9, 103.3, 1000))        # 20 trough(close=103.3)
    rows2.append((103.3, 103.9, 103.2, 103.6, 1000))        # 21 阳线
    rows2.append((103.6, 104.0, 103.3, 103.8, 1000))        # 22 阳线 → confirm
    rows2.append((103.8, 104.2, 103.5, 103.9, 1000))        # 23 段内
    rows2.append((103.9, 104.3, 103.6, 104.0, 1000))        # 24 段内
    rows2.append((104.0, 104.4, 103.7, 104.1, 1000))        # 25 段内
    rows2.append((104.1, 104.5, 103.8, 104.2, 1000))        # 26 预算末 → 闭合
    df2 = _make_df(rows2)
    burst2 = [_burst(_bo(15), _bo(19))]
    assert list(ThrowbackDetectorV3(anchor_mode='last_bo').detect(burst2, df2)) == []
    assert len(list(ThrowbackDetectorV3(anchor_mode='min_bo').detect(burst2, df2))) == 1


def test_container_structure():
    """容器装配:segments 顺序/span=首段 enter..末段 exit/confirm=start/outcome=末段结局。

    detect 需要有效 ATR(period 14),bo 放 idx 14(前 14 根基座)。
    注意:单 bo burst 下 span_min=close[14]=99.0,trough 必须高于 anchor
    (close[15]=99.5)才有 weak 区间(judged ∈ [99.0, 99.5))。
    推演:trough@15(close=99.5);confirm@16(段1 enter,trough_price=99.5);
    weak@17(99.2<99.5 且 ≥99.0)→ 段1=(16,16,'weak');段外 18 刷 trough
    (close 99.15<99.2)且无 signal;19 阳线 confirm@19(段2 enter,trough=18);
    预算末 20 强制闭合:段2=(19,20,'timeout')。
    """
    rows = _atr_one_series(14, base=100.0)                 # 0-13 基座(ATR≈2)
    rows.append((99.0, 100.0, 98.0, 99.0, 1000))           # 14 bo
    rows.append((99.5, 100.0, 99.2, 99.5, 1000))           # 15 trough(close=99.5)
    rows.append((99.5, 100.2, 99.3, 99.8, 1000))           # 16 confirm → 段1
    rows.append((99.8, 100.0, 97.0, 99.2, 1000))           # 17 weak(99.2<99.5)→ 段1=(16,16,'weak')
    rows.append((99.2, 99.5, 98.9, 99.15, 1000))           # 18 刷 trough(99.15<99.2);无 signal
    rows.append((99.15, 99.6, 99.0, 99.4, 1000))           # 19 confirm(阳线)→ 段2
    rows.append((99.4, 99.7, 99.1, 99.5, 1000))            # 20 预算末强制闭合
    df = _make_df(rows)
    events = list(ThrowbackDetectorV3(stop_confirm_bars=1).detect([_burst(_bo(14))], df))
    assert len(events) == 1
    e = events[0]
    assert isinstance(e, ThrowbackEventV3)
    assert type(e).__name__ == "ThrowbackEventV3"
    assert e.start_idx == 16 and e.end_idx == 20    # span=[首段 enter, 末段 exit]
    assert e.confirm_idx == 16                      # confirm=start(首段 enter)
    assert len(e.segments) == 2
    seg0, seg1 = e.segments
    assert (seg0.start_idx, seg0.end_idx, seg0.outcome) == (16, 16, 'weak')
    assert (seg1.start_idx, seg1.end_idx, seg1.outcome) == (19, 20, 'timeout')
    assert type(seg0).__name__ == "ThrowbackSegmentV3"
    assert seg0.confirm_idx == seg0.start_idx
    assert e.outcome == 'timeout'                   # 容器 outcome=末段结局
    assert e.anchor_bo_id == "bo_14#0"           # 交错标注后取源 bo 的 instance_id
    assert set(e.child_slots()) == {"segments"}


def test_validation_raises():
    """judged/reference/scb_mode/anchor_mode 非法值 ValueError。"""
    with pytest.raises(ValueError, match="judged_measure"):
        ThrowbackDetectorV3(judged_measure="bogus")
    with pytest.raises(ValueError, match="reference_measure"):
        ThrowbackDetectorV3(reference_measure="bogus")
    with pytest.raises(ValueError, match="scb_mode"):
        ThrowbackDetectorV3(scb_mode="bogus")
    with pytest.raises(ValueError, match="anchor_mode"):
        ThrowbackDetectorV3(anchor_mode="bogus")
