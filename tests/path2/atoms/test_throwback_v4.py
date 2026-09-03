"""tb v4 测试:状态机纯函数(判据逐条 + 不变式,vol 注入式)+ detector 装配(TestDetector)
+ gate 接线(TestGates)+ debug 埋点(TestDebugHooks)。

enter 相位约定:enter = 第 K 根不刷新根本身(当根计数达标当根入段),依据
spec §3(confirm==enter,企稳在 enter 根已成立)/§8(K=不刷新根数)/§11
(连续 K 根不刷新转 STABLE 开段);见 throwback_v4.py 模块 docstring 的裁定记录。
"""
import numpy as np
import pandas as pd
import pytest

import path2.atoms.throwback_v4 as throwback_v4
from path2.atoms.breakout import BOEvent, BurstEvent
from path2.atoms.throwback_v4 import (
    ThrowbackDetectorV4,
    ThrowbackEventV4,
    ThrowbackSegmentV4,
    enumerate_segments_v4,
)
from path2.dag.gate_failure import MeasuredKindAware


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


def mk(closes, opens=None, vol=1.0):
    """造 (closes, opens, vol) 数组。opens 缺省 = close*0.99(全部非阴线)。"""
    closes = np.asarray(closes, dtype=float)
    opens = (np.asarray(opens, dtype=float) if opens is not None
             else closes * 0.99)
    vol = np.full(len(closes), float(vol))
    return closes, opens, vol


def run(closes, opens=None, vol=1.0, bo=3, gbot=50.0, k=1.5, K=1, ms=60,
        on_gate=None):
    c, o, v = mk(closes, opens, vol)
    return enumerate_segments_v4(c, o, bo, gbot, v, max_rise_k=k,
                                 stop_confirm_bars=K, max_span=ms,
                                 on_gate=on_gate)


class TestUpToDown:
    def test_decline_bar_triggers(self):
        # i=4 收跌(99<100)→ DOWN,trough=99;i=5 不刷新 cnt=1≥K → STABLE enter=5;
        # i=6/7 段内静止 → 预算尽 timeout 收口
        r = run([100, 100, 100, 100, 99, 99.2, 99.3, 99.4])
        assert r.segments[0].enter == 5
        assert r.machine_outcome in ('break', 'budget')

    def test_gapup_red_candle_triggers(self):
        # i=4 高开阴线:close=100.5 > close[3]=100(不收跌)但 close<open=101
        # → 阴线臂触发;i=4 转 DOWN trough=100.5。
        # i=5 处于 DOWN:不刷新(100.6>100.5)、rise 不触发(100.6<100.5+1.5=102)
        # → cnt=1≥K → STABLE enter=5(尾根即预算尽,timeout 段 (5,5))
        r = run([100, 100, 100, 100, 100.5, 100.6], opens=[99]*4 + [101, 100.4])
        assert r.segments[0].enter == 5

    def test_green_up_bar_stays_up(self):
        # 全阳线收涨 → 全程 UP 无段(bo_only 语义)
        r = run([100, 100, 100, 100, 101, 102, 103])
        assert r.segments == ()
        assert r.machine_outcome == 'budget'


class TestDown:
    def test_rise_arm_priority_v_bounce_no_segment(self):
        # i=5 大反弹 101 > trough99+1.5 → rise 臂直接 UP 不产段(V 反转不产段);
        # i=6 收跌 → DOWN trough=100.9;i=7 不刷新(rise 不触发:101<100.9+1.5=102.4)
        # cnt=1 → STABLE enter=7;i=8 rise(102.5>102.4)出段 (7,7)
        r = run([100, 100, 100, 100, 99, 101, 100.9, 101.0, 102.5])
        assert [s.outcome for s in r.segments] == ['rise']
        assert r.segments[0].enter == 7 and r.segments[0].exit == 7

    def test_equal_close_is_no_refresh(self):
        # i=5 close == trough(等值)→ 不刷新(严格小于才叫刷新),cnt=1 → STABLE
        r = run([100, 100, 100, 100, 98, 98, 98.5])
        assert r.segments[0].enter == 5   # i=4 DOWN(trough=98);i=5 等值 cnt=1 → STABLE

    def test_new_low_resets_count(self):
        # i=5 刷新 97(cnt 清零)→ i=6 不刷新 cnt=1 → STABLE enter=6
        r = run([100, 100, 100, 100, 98, 97, 97.2])
        assert r.segments[0].enter == 6


class TestStable:
    def test_rise_exit_ratchets(self):
        # trough=98.8(i=5);i=6 不刷新 cnt=1 → enter=6;i=7 close=100.5>98.8+1.5=100.3
        # → rise 段 (6,6),gbot ratchet → 98.8,回 UP;i=8 close=98.0<gbot=98.8 →
        # 段外全局退出(UP 中不追收段),machine='break'(已收段保留)
        r = run([100, 100, 100, 100, 99, 98.8, 99.0, 100.5, 98.0])
        assert r.segments == ((6, 6, 'rise'),)
        assert r.machine_outcome == 'break'

    def test_new_high_arm_exit(self):
        # k=100 → rise 臂不可达,仅 close>peak 臂:peak=close[bo]=100;
        # i=4~6 连续刷新(trough=85);i=7 不刷新 cnt=1 → STABLE enter=7;i=8 静止;
        # i=9 close=101>100 → rise 段 (7,8)(价格行为类 exit=i-1),回 UP 后序列
        # 耗尽 = 预算尽 → budget(非破线)
        r = run([100, 100, 100, 100, 95, 90, 85, 86, 87, 101], k=100.0)
        assert r.segments == ((7, 8, 'rise'),)
        assert r.machine_outcome == 'budget'

    def test_weak_exit_reentry(self):
        # i=5 不刷新 cnt=1 → enter=5(trough=99);i=6 close=97.9<99 → weak (5,5),
        # 转 DOWN trough=97.9;i=7 不刷新(rise 不触发:98<97.9+1.5=99.4)cnt=1 →
        # STABLE enter=7;i=8 rise(99.5>99.4)出段 (7,7)
        r = run([100, 100, 100, 100, 99, 99.2, 97.9, 98.0, 99.5])
        assert r.segments == ((5, 5, 'weak'), (7, 7, 'rise'))

    def test_budget_timeout_closes_segment(self):
        # i=4 DOWN(trough=98);i=5 不刷新 cnt=1 → enter=5;i=6/7 段内静止
        # (close 高于 trough 但 < 98+1.5=99.5,trough 不动不出段);
        # bo=3, ms=4 → 扫 i∈[4,7],i=7 处仍 STABLE → timeout 段 (5,7)(预算类含末根)
        r = run([100, 100, 100, 100, 98, 98.5, 98.9, 99.0], ms=4)
        assert r.segments == ((5, 7, 'timeout'),)
        assert r.machine_outcome == 'budget'


class TestGlobalBreak:
    def test_break_truncates_last_segment(self):
        # gbot=90;enter=5;i=6 静止;i=7 close=89<90 段内破线 → 末段 (5,6,'break')
        # (价格行为类不含破线根),机器终止
        r = run([100, 100, 100, 100, 99, 99.5, 99.6, 89], gbot=90.0)
        assert r.segments == ((5, 6, 'break'),)
        assert r.machine_outcome == 'break'

    def test_break_zero_segments(self):
        # 全程 UP 后 i=4 收跌 DOWN;i=5 直接破线 → 0 段 machine='break'
        r = run([100, 100, 100, 100, 99, 49], gbot=90.0)
        assert r.segments == ()
        assert r.machine_outcome == 'break'

    def test_ratchet_chain_then_break(self):
        # 两轮成功后第三根破抬升线才死:ratchet 生效则机器死于 i=10;
        # 若 gbot 未抬升(恒 50)则 i=10 的 96.0 不破线(转 DOWN),budget 存活。
        # 段1:i=4 DOWN(trough=95);i=5 不刷新 cnt=1 → enter=5;i=6 rise
        # (97.5>95+1.5=96.5)→ (5,5,'rise'),gbot ratchet → 95。
        # 段2:i=7 收跌 → DOWN(trough=96.5);i=8 不刷新(rise 不触发:97<96.5+1.5=98)
        # cnt=1 → enter=8;i=9 rise(98.2>98.0)→ (8,8,'rise'),gbot ratchet → 96.5。
        # i=10 close=96.0<gbot=96.5 → 段外全局退出 → machine='break'。
        r = run([100, 100, 100, 100, 95, 95.5, 97.5,   # 段1: trough=95, enter=5, rise@6
                 96.5, 97.0, 98.2,                     # 段2: trough=96.5, enter=8, rise@9
                 96.0], gbot=50.0)
        assert r.machine_outcome == 'break'
        assert len(r.segments) == 2


class TestBudget:
    def test_persistent_decline_budget_no_stable(self):
        # spec §6-3:持续阴跌但始终不破 global_bottom——i=4 收跌 DOWN(trough=99),
        # i=5~7 每根严格刷新(98→97→96)、cnt 恒清零,永远到不了计数分支;
        # 预算尽时 state=DOWN,收尾仅 STABLE 收 timeout → 0 段 + budget
        # (Task 4 budget_no_stable gate 的触发源形态)
        r = run([100, 100, 100, 100, 99, 98, 97, 96], gbot=50.0)
        assert r.segments == ()
        assert r.machine_outcome == 'budget'


class TestVolWarmup:
    def test_nan_vol_degrades_rise_arm(self):
        # vol[5]=NaN:反弹根 rise 臂降级跳过 → 落到计数臂入段(V 反弹根成入段根);
        # i=6 vol 恢复有效,rise(101.5>99+1.5)正常出段
        c, o, v = mk([100, 100, 100, 100, 99, 101, 101.5])
        v[5] = np.nan
        r = enumerate_segments_v4(c, o, 3, 50.0, v)
        assert r.segments[0].enter == 5


class TestRedCandleUsesRealClose:
    """spec §5:阴线判定 = close < open(K 线形态判据,不随 measure 变);收跌臂
    维持 measure 口径(closes[i] < closes[i-1],同一 measure 列内比较)。

    measure≠close 时 detect 恒传 real_closes(df['close']);纯函数层不传 = 现行为
    (用 closes 列判阴线,既有测试零改动的向后兼容)。
    """

    def test_measure_rising_low_column_no_avalanche(self):
        # measure 列(low 模拟)逐根升(无收跌)但每根 < open——measure='low' 下
        # low<open 结构性恒真,用 measure 列判阴线会雪崩误转 DOWN;真 close 全
        # 收涨且 ≥ open → 传 real_closes 后全程 UP 零段
        measure = [100, 100, 100, 100, 103, 103.2, 103.4, 103.6]
        opens = [99, 99, 99, 99, 104, 104.5, 104.8, 105.0]
        real = [100, 100, 100, 100, 105, 105.2, 105.4, 105.6]
        c, o, v = mk(measure, opens)
        r = enumerate_segments_v4(c, o, 3, 50.0, v,
                                  real_closes=np.asarray(real))
        assert r.segments == ()
        assert r.machine_outcome == 'budget'

    def test_decline_arm_keeps_measure_column(self):
        # 对称护栏:收跌臂仍用 measure 列(spec §5「全部比较同一 measure」,
        # 唯阴线臂跨列用真 close)——measure 列收跌而真 close 全涨 → 仍转 DOWN
        # 产段(若把收跌臂也换成真 close 会全程 UP 零段、此处失败)
        measure = [100, 100, 100, 100, 100, 99, 99.2]    # i=5 收跌(measure 口径)
        opens = [90, 90, 90, 90, 90, 90, 90]             # 两列均 ≥ open(无阴线)
        real = [100, 100, 100, 100, 105, 106, 107]       # 全收涨
        c, o, v = mk(measure, opens)
        r = enumerate_segments_v4(c, o, 3, 50.0, v,
                                  real_closes=np.asarray(real))
        assert r.segments[0].enter == 6   # i=5 measure 收跌→DOWN;i=6 不刷新 K=1→enter

    def test_detector_measure_low_uses_real_close(self):
        # detector 层:detect 恒传 real_closes=df['close']——measure='low' 下
        # low<open 结构性恒真,修复前阴线臂读 measure 列雪崩误产段;修复后真
        # close 全收涨无阴线、low 列无收跌 → 全程 UP 不产容器
        rows = _base_series(7)
        rows[6] = (100.0, 105.0, 99.0, 105.0, 5000)    # 单 bo,span_min 锚 = low = 99
        rows += [
            (104.0, 105.5, 103.0, 105.0, 1000),   # 7 low<open(误触发源);close≥open 收涨
            (104.5, 106.0, 103.2, 105.2, 1000),   # 8 low 逐根升(measure 无收跌)
            (104.8, 106.2, 103.4, 105.4, 1000),
            (105.0, 106.4, 103.6, 105.6, 1000),
            (105.2, 106.6, 103.8, 105.8, 1000),
            (105.4, 106.8, 104.0, 106.0, 1000),
        ]
        df = _make_df(rows)
        det = ThrowbackDetectorV4(vol_window=5, measure='low')
        assert list(det.detect([_burst(_bo(6))], df)) == []


class TestInvariant:
    def test_peak_monotone_multi_cycle(self):
        # 多轮后 peak 仍 ≥ 初始 100:段1 rise@i=6(97.5>96.5);i=7 收跌 DOWN、
        # i=8 刷新(96.5)、i=9 rise 臂回 UP(98.2>98.0,无段)、i=10 收跌 DOWN;
        # i=11 close=200:rise 臂(200>96+1.5)与 close>peak(200>100)双触发,
        # 无论 trough 深浅必反弹;若 peak 被重置会提前触发
        r = run([100, 100, 100, 100, 95, 95.5, 97.5, 97.0, 96.5, 98.2, 96.0, 200.0])
        assert any(s.outcome == 'rise' for s in r.segments)


class TestDetector:
    """detect 装配:anchor 三模式 / 容器结构 / 排序 / 0 段不产。

    burst 构造复用 test_throwback_v1_burst_anchor.py 的合成 helper 模式
    (_make_df/_bo/_burst/_base_series,已复制到本文件模块级)。
    """

    def test_container_structure(self):
        # 双 bo burst(span_min 锚=close[5]=98):i=7 阴线→DOWN;i=8 不刷新(K=1)
        # → 段1 enter=8;i=9 破段底→weak 出段;i=10 不刷新→段2 enter=10;i=11
        # close=106>peak=104.5→rise 出段;i=12 阴线→DOWN,序列尽→整机 budget。
        # 容器 span=[首段 enter=8, 末段 exit=10],confirm=8;outcome=末段 'rise';
        # machine_outcome='budget'(末段 rise 后整机未破线,B1 独立表达)。
        rows = _base_series(7)
        rows[4] = (100.0, 105.0, 100.0, 105.0, 5000)    # bo_4
        rows[5] = (99.0, 100.0, 97.0, 98.0, 1000)       # span 内非 bo bar → span_min 锚
        rows[6] = (101.0, 106.0, 100.5, 104.5, 5000)    # bo_6(peak=close[6]=104.5)
        rows += [
            (103.0, 103.5, 101.0, 101.5, 1000),   # 7 阴线→DOWN trough=101.5
            (101.4, 102.0, 101.0, 101.6, 1000),   # 8 不刷新→STABLE enter=8
            (101.5, 101.8, 100.0, 100.5, 1000),   # 9 破段底→weak (8,8)
            (100.6, 101.0, 100.2, 100.7, 1000),   # 10 不刷新→STABLE enter=10
            (105.0, 108.0, 104.0, 106.0, 1000),   # 11 close>peak→rise (10,10)
            (105.5, 106.5, 104.0, 105.0, 1000),   # 12 阴线→DOWN;序列尽→budget
        ]
        df = _make_df(rows)
        det = ThrowbackDetectorV4(vol_window=5)
        events = list(det.detect([_burst(_bo(4), _bo(6))], df))
        assert len(events) == 1                          # 一 burst 一容器
        ev = events[0]
        assert isinstance(ev, ThrowbackEventV4)
        assert (ev.start_idx, ev.end_idx, ev.confirm_idx) == (8, 10, 8)
        assert ev.child_slots() == {"segments": ev.segments}
        assert len(ev.segments) == 2
        assert all(isinstance(s, ThrowbackSegmentV4) for s in ev.segments)
        # 段字段:span/confirm=enter/单来源 anchor_bo_id/outcome 逐段透传
        assert (ev.segments[0].start_idx, ev.segments[0].end_idx,
                ev.segments[0].confirm_idx) == (8, 8, 8)
        assert (ev.segments[1].start_idx, ev.segments[1].end_idx,
                ev.segments[1].confirm_idx) == (10, 10, 10)
        assert [s.outcome for s in ev.segments] == ['weak', 'rise']
        assert ev.anchor_bo_id == 'bo_6#0'              # last_bo 的 instance_id
        assert all(s.anchor_bo_id == 'bo_6#0' for s in ev.segments)
        # 容器 outcome=末段 outcome;machine_outcome 独立透传(B1)
        assert ev.outcome == 'rise'
        assert ev.machine_outcome == 'budget'

    def test_anchor_three_modes(self):
        # 三锚取值不同(gap=4 双 bo,span [4,8]):
        # span_min = min(close[4..8]) = 100(idx5 非 bo bar);
        # min_bo = min(bo 当根) = min(103, 104.5) = 103;
        # last_bo = close[末 bo 上一根=7] = 103.2(非 bo bar)。
        # 分岔点 1:i=9 close=103.1 → 仅 last_bo(103.2)判破线,0 段不产;
        # 分岔点 2:i=11 close=102.5 → min_bo(103)段内破线(末段 'break'/机器
        # 'break');span_min(100)守线走 weak 出段 re-entry,末段 'timeout'/
        # 机器 'budget'。三模式段行为两两不同。
        rows = _base_series(9)
        rows[4] = (100.0, 105.0, 100.0, 103.0, 5000)    # bo_4 close=103
        rows[5] = (99.0, 100.0, 98.0, 100.0, 1000)      # 非 bo → span 最低
        rows[6] = (101.0, 104.0, 100.5, 104.0, 1000)    # 非 bo
        rows[7] = (102.0, 104.0, 101.0, 103.2, 1000)    # 非 bo → last_bo 上一根
        rows[8] = (103.0, 106.0, 102.5, 104.5, 5000)    # bo_8 = last_bo
        rows += [
            (104.0, 104.4, 102.8, 103.1, 1000),   # 9 阴线→DOWN trough=103.1(>103,>100)
            (103.2, 103.8, 103.0, 103.5, 1000),   # 10 不刷新→STABLE enter=10
            (103.0, 103.3, 102.0, 102.5, 1000),   # 11 分岔:<103 破 min_bo 锚;<段底 weak
            (102.4, 103.0, 102.2, 102.6, 1000),   # 12 span_min:不刷新→STABLE;末根 timeout
        ]
        df = _make_df(rows)
        burst = _burst(_bo(4), _bo(8))
        ev_span = list(ThrowbackDetectorV4(vol_window=5).detect([burst], df))
        assert [(s.start_idx, s.end_idx, s.outcome) for s in ev_span[0].segments] == \
            [(10, 10, 'weak'), (12, 12, 'timeout')]
        assert ev_span[0].machine_outcome == 'budget'
        ev_min = list(ThrowbackDetectorV4(vol_window=5, anchor_mode='min_bo')
                      .detect([burst], df))
        assert [(s.start_idx, s.end_idx, s.outcome) for s in ev_min[0].segments] == \
            [(10, 10, 'break')]
        assert ev_min[0].machine_outcome == 'break'
        ev_last = list(ThrowbackDetectorV4(vol_window=5, anchor_mode='last_bo')
                       .detect([burst], df))
        assert ev_last == []                             # i=9 即破线 → 无容器

    def test_zero_segments_no_event(self):
        # 全程阳线收涨(无阴线无收跌)→ 机器全程 UP、0 段 → 不产容器
        # (spec §6-2:无回踩无买点,bo_only 语义的正确静默)
        rows = _base_series(7)
        rows[6] = (101.0, 106.0, 100.5, 104.5, 5000)    # bo_6(单 bo,span_min 锚=104.5)
        rows += [
            (104.0, 105.0, 103.8, 104.8, 1000),
            (104.5, 106.0, 104.2, 105.5, 1000),
            (105.0, 107.0, 104.8, 106.5, 1000),
            (106.0, 108.0, 105.5, 107.5, 1000),
            (107.0, 109.0, 106.5, 108.2, 1000),
            (107.8, 110.0, 107.2, 109.0, 1000),
        ]
        df = _make_df(rows)
        assert list(ThrowbackDetectorV4().detect([_burst(_bo(6))], df)) == []

    def test_sorted_by_end(self):
        # 两台机走同构路径、错位排布(bo=6 / bo=20;max_span=7 让机器1 预算
        # 止于 i=13 基座,不吞入第二 burst 区段),乱序喂入 → 输出按
        # (end_idx, start_idx) 升序(run() 不变式)
        rows = _base_series(27)
        path = [
            (103.0, 103.5, 101.0, 101.5, 1000),   # +1 阴线→DOWN
            (101.4, 102.0, 101.0, 101.6, 1000),   # +2 不刷新→STABLE enter=8/22
            (101.5, 101.8, 100.0, 100.5, 1000),   # +3 破段底→weak
            (100.6, 101.0, 100.2, 100.7, 1000),   # +4 不刷新→STABLE enter=10/24
            (105.0, 108.0, 104.0, 106.0, 1000),   # +5 close>peak→rise
            (105.5, 106.5, 104.0, 105.0, 1000),   # +6 阴线→DOWN
        ]
        for off in (4, 18):
            rows[off] = (100.0, 105.0, 100.0, 105.0, 5000)      # 首 bo
            rows[off + 1] = (99.0, 100.0, 97.0, 98.0, 1000)     # span_min 锚 bar
            rows[off + 2] = (101.0, 106.0, 100.5, 104.5, 5000)  # 末 bo
            for j, r in enumerate(path):
                rows[off + 3 + j] = r
        df = _make_df(rows)
        det = ThrowbackDetectorV4(vol_window=5, max_span=7)
        b1 = _burst(_bo(4), _bo(6))       # 容器 (8, 10)
        b2 = _burst(_bo(18), _bo(20))     # 容器 (22, 24)
        events = list(det.detect([b2, b1], df))          # 乱序输入
        assert [(e.start_idx, e.end_idx) for e in events] == [(8, 10), (22, 24)]

    def test_invalid_params_raise(self):
        with pytest.raises(ValueError, match="measure"):
            ThrowbackDetectorV4(measure="bogus")
        with pytest.raises(ValueError, match="anchor_mode"):
            ThrowbackDetectorV4(anchor_mode="bogus")

    def test_bo_boundary_skips_machine(self):
        # spec §6-1 前置边界:bo < 1 或 bo >= len(df) 不启动机器、不产事件
        # (沿用 t1 惯例,非 gate)。bo == len(df)-1 合法但扫描区间空 → 0 段不产。
        rows = _base_series(6)
        rows[2] = (100.0, 105.0, 100.0, 105.0, 5000)
        df = _make_df(rows)
        det = ThrowbackDetectorV4(vol_window=5)
        assert list(det.detect([_burst(_bo(0))], df)) == []            # bo=0 < 1
        assert list(det.detect([_burst(_bo(len(df)))], df)) == []      # bo == n 越界
        assert list(det.detect([_burst(_bo(len(df) - 1))], df)) == []  # bo=n-1 合法,扫描区间空

    def test_prefix_family_no_dedup(self):
        # spec §6-6:同 cluster 前缀族(全串 (bo_4,bo_5,bo_6) + 前缀 (bo_4,bo_5))
        # → 两机两容器(span 完全重叠),各带单来源 anchor_bo_id,不合并不去重。
        # 推演(vol_window=5,vol[8]=median(TR[3..7])=5,rise 阈=101.5+7.5=109 不可达):
        # 全串机 bo=6,锚 span_min=min(105,98,104.5)=98,peak=104.5:i=7 阴线
        # →DOWN trough=101.5;i=8 不刷新 cnt=1≥K → STABLE enter=8,扫描尽 → (8,8,'timeout')。
        # 前缀机 bo=5,锚 span_min=min(105,98)=98,peak=98:i=6 收涨 peak→104.5;
        # i=7 阴线→DOWN trough=101.5;i=8 同上 → (8,8,'timeout')。两机轨迹几乎重合。
        rows = _base_series(7)
        rows[4] = (100.0, 105.0, 100.0, 105.0, 5000)    # bo_4
        rows[5] = (99.0, 104.0, 97.0, 98.0, 5000)       # bo_5(低位二破,压低两机锚)
        rows[6] = (101.0, 106.0, 100.5, 104.5, 5000)    # bo_6(全串机 last_bo)
        rows += [
            (103.0, 103.5, 101.0, 101.5, 1000),   # 7 两机各自阴线→DOWN trough=101.5
            (101.4, 102.0, 101.0, 101.6, 1000),   # 8 不刷新→STABLE enter=8
        ]
        df = _make_df(rows)
        det = ThrowbackDetectorV4(vol_window=5)
        events = list(det.detect(
            [_burst(_bo(4), _bo(5), _bo(6)), _burst(_bo(4), _bo(5))], df))
        assert len(events) == 2                        # 重叠 span 不去重
        by_anchor = {e.anchor_bo_id: e for e in events}
        assert set(by_anchor) == {'bo_6#0', 'bo_5#0'}  # 各带单来源 anchor
        for ev in events:
            assert [(s.start_idx, s.end_idx, s.outcome) for s in ev.segments] \
                == [(8, 8, 'timeout')]
            assert ev.machine_outcome == 'budget'


class TestGates:
    """gate 只收整机短路点(spec §7)。collector = 简单 list append。

    名表(逐字):break_no_stable(全局退出时 0 段)/ break_truncate(全局退出
    截断末段,事件仍产)/ budget_no_stable(预算尽 0 段);段级收口(rise/weak/
    timeout)与"机器已完成产出"的退出(段外破线且 ≥1 段、预算尽且已有段)不 emit。
    """

    def _run_collect(self, closes, **kw):
        collected = []
        r = run(closes, on_gate=collected.append, **kw)
        return r, collected

    def test_break_no_stable(self):
        # 0 段 + 段外破线(照 TestGlobalBreak.test_break_zero_segments 形态):
        # i=4 收跌 DOWN(trough=99);i=5 c=49<gbot=90 段外破线、0 段 →
        # 1 条 'break_no_stable',measured.kind='anchor_delta'
        r, collected = self._run_collect([100, 100, 100, 100, 99, 49], gbot=90.0)
        assert r.segments == ()
        assert len(collected) == 1
        g = collected[0]
        assert g.gate_name == 'break_no_stable'
        assert g.measured.kind == 'anchor_delta'
        assert g.gate_idx == 5                    # 破线根
        assert g.failure_event_window == (4, 5)   # (bo_idx+1, gate_idx)
        assert g.anchor_bar == 3                  # bo 根
        assert g.evaluation_lookback == (-9, 4)   # (gate_idx-vol_window, gate_idx-1) 随 gate_idx 移动

    def test_break_truncate(self):
        # 段内破线截断(照 test_break_truncates_last_segment):i=7 c=89<gbot=90
        # 段内破线 → 段 (5,6,'break') 仍产 + 1 条 'break_truncate'
        r, collected = self._run_collect(
            [100, 100, 100, 100, 99, 99.5, 99.6, 89], gbot=90.0)
        assert r.segments == ((5, 6, 'break'),)
        assert r.machine_outcome == 'break'
        assert len(collected) == 1
        g = collected[0]
        assert g.gate_name == 'break_truncate'
        assert g.measured.kind == 'anchor_delta'
        assert g.gate_idx == 7
        assert g.measured.value == pytest.approx(-1.0)   # c - gbot

    def test_budget_no_stable(self):
        # 预算尽 0 段(全程 UP 无阴线,照 test_green_up_bar_stays_up 形态)→
        # 'budget_no_stable',kind='count'
        r, collected = self._run_collect([100, 100, 100, 100, 101, 102, 103])
        assert r.segments == ()
        assert r.machine_outcome == 'budget'
        assert len(collected) == 1
        g = collected[0]
        assert g.gate_name == 'budget_no_stable'
        assert g.measured.kind == 'count'
        assert g.measured.value == 60             # max_span(预算值,照 v1 timeout 类口径)
        assert g.gate_idx == 6                    # end = min(bo+max_span, len-1)

    def test_no_gate_on_normal_exits(self):
        # 段级收口(rise/weak)、预算尽已有段(timeout 收口)、段外破线且已有段 →
        # 机器已完成产出,非整机短路 → collector 全空
        r1, c1 = self._run_collect([100, 100, 100, 100, 99, 99.2, 97.9, 98.0, 99.5])
        assert [s.outcome for s in r1.segments] == ['weak', 'rise']
        r2, c2 = self._run_collect([100, 100, 100, 100, 98, 98.5, 98.9, 99.0], ms=4)
        assert [s.outcome for s in r2.segments] == ['timeout']   # 预算尽已有段
        r3, c3 = self._run_collect([100, 100, 100, 100, 99, 98.8, 99.0, 100.5, 98.0])
        assert r3.segments == ((6, 6, 'rise'),)   # 段外破线且已有段
        assert r3.machine_outcome == 'break'
        assert c1 == [] and c2 == [] and c3 == []


class TestDebugHooks:
    """debug_break 埋点:entry(bo 根,tb 容器 entry 档)/ start(每段 enter 根,
    tb_seg 确认型 start 档)/ end(每段收口根 = 段 exit;rise/weak/break 类 exit
    本就是 i-1、timeout 是 end);helper 两路径照
    tests/path2/atoms/test_throwback_debug_hook.py 模式。"""

    def test_detect_three_anchor_kinds(self, monkeypatch):
        # 数据照 TestDetector.test_container_structure:bo=6、
        # 段1 (8,8,'weak')、段2 (10,10,'rise') → entry@6,confirm/end 逐段交错
        calls = []
        monkeypatch.setattr(
            "path2.atoms.throwback_v4.debug_break",
            lambda i, *, anchor_kind, **_kw: calls.append((i, anchor_kind)))
        rows = _base_series(7)
        rows[4] = (100.0, 105.0, 100.0, 105.0, 5000)
        rows[5] = (99.0, 100.0, 97.0, 98.0, 1000)
        rows[6] = (101.0, 106.0, 100.5, 104.5, 5000)
        rows += [
            (103.0, 103.5, 101.0, 101.5, 1000),   # 7 阴线→DOWN trough=101.5
            (101.4, 102.0, 101.0, 101.6, 1000),   # 8 不刷新→STABLE enter=8
            (101.5, 101.8, 100.0, 100.5, 1000),   # 9 破段底→weak (8,8)
            (100.6, 101.0, 100.2, 100.7, 1000),   # 10 不刷新→STABLE enter=10
            (105.0, 108.0, 104.0, 106.0, 1000),   # 11 close>peak→rise (10,10)
            (105.5, 106.5, 104.0, 105.0, 1000),   # 12 阴线→DOWN;序列尽→budget
        ]
        df = _make_df(rows)
        det = ThrowbackDetectorV4(vol_window=5)
        assert len(list(det.detect([_burst(_bo(4), _bo(6))], df))) == 1
        assert calls == [(6, 'entry'), (8, 'start'), (8, 'end'),
                         (10, 'start'), (10, 'end')]

    def test_emit_gate_triggers_debug_break_on_diagnose_path(self, monkeypatch):
        """on_gate 非 None(diagnose)→ debug_break 收到 gate_idx;GateFailure 的
        evaluation_lookback 随 gate_idx 移动(t4 口径,异于 t1 固定 (bo-窗, bo))。"""
        calls = []
        monkeypatch.setattr(
            "path2.atoms.throwback_v4.debug_break",
            lambda i, *, anchor_kind, **_kw: calls.append(i))
        collected = []
        throwback_v4._emit_tb_gate_v4(
            bo_idx=100, gate_idx=250, gate_name='break_no_stable',
            measured=MeasuredKindAware(kind='anchor_delta', value=-1.0,
                                       label='破位差'),
            threshold=0.0, vol_window=14,
            on_gate=lambda gf: collected.append(gf))
        assert calls == [250], "debug_break should be called with gate_idx (not bo_idx)"
        assert len(collected) == 1, "on_gate should still be called (existing behavior preserved)"
        assert collected[0].evaluation_lookback == (250 - 14, 250 - 1)

    def test_emit_gate_skips_debug_break_on_scan_path(self, monkeypatch):
        """on_gate=None → 早退分支(local invariant)。真实 scan attach 非 None
        on_gate,scan 真正的 bypass 靠 _DEBUG_MODE=False。"""
        calls = []
        monkeypatch.setattr(
            "path2.atoms.throwback_v4.debug_break",
            lambda i, *, anchor_kind, **_kw: calls.append(i))
        throwback_v4._emit_tb_gate_v4(
            bo_idx=100, gate_idx=250, gate_name='break_no_stable',
            measured=MeasuredKindAware(kind='anchor_delta', value=-1.0,
                                       label='破位差'),
            threshold=0.0, vol_window=14, on_gate=None)
        assert calls == [], "scan path (on_gate=None) must not touch debug_break"
