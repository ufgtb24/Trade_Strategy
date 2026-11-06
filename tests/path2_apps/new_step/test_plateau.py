"""PlateauDetector:旧平台 → 阶跃 → 新平台,逐天产截到当天的复合事件。

只直接调用 PlateauDetector(...).detect(df),不经 app 的 dag_spec。期望值按计划里的
字段定义用纯 Python(math / statistics)独立重算,不复用 detector 的 numpy 实现。
"""
import math
import statistics

import numpy as np
import pandas as pd
import pytest

from path2.debug import current_symbol
from path2.runner import run
from path2_apps.new_step.plateau import (
    NewPlatform, OldPlatform, PlateauDetector, PlateauEvent, Step, Today,
)

L = 15
KW = dict(old_window=L, strong_k=3.0, max_step_bars=5, max_days=40)


def make_df(closes, highs=None, lows=None, opens=None, vols=None):
    n = len(closes)
    return pd.DataFrame({
        'open': opens or list(closes),
        'high': highs or [c + 0.1 for c in closes],
        'low': lows or [c - 0.1 for c in closes],
        'close': list(closes),
        'volume': vols or [1000.0] * n,
    })


def base_bars():
    """主样例(42 根):
    0..19  旧平台,收盘 10.0 / 10.05 交替(偶数 10.0、奇数 10.05),量 1000
    20, 21 两根大阳线 12.0、14.0,量 5000、8000;21 根上影线最高 14.5
    22..34 新平台,收盘 13.9 / 14.0 交替(偶数 13.9),开盘一律 13.95,量 2000
    35     跌回 10.0(≤ 旧平台价位 10.05)
    36..41 10.1 / 10.15 交替,回到旧平台价位之上但不构成新阶跃
    """
    closes = [10.0 if j % 2 == 0 else 10.05 for j in range(20)]
    closes += [12.0, 14.0]
    closes += [13.9 if j % 2 == 0 else 14.0 for j in range(22, 35)]
    closes += [10.0]
    closes += [10.1 if j % 2 == 0 else 10.15 for j in range(36, 42)]
    opens = list(closes)
    for j in range(22, 35):
        opens[j] = 13.95
    highs = [c + 0.1 for c in closes]
    highs[21] = 14.5
    vols = [1000.0] * 20 + [5000.0, 8000.0] + [2000.0] * 20
    return dict(closes=closes, opens=opens, highs=highs, vols=vols)


def df_of(bars):
    return make_df(bars["closes"], highs=bars["highs"], opens=bars["opens"], vols=bars["vols"])


def detect(bars, **over):
    det = PlateauDetector(**{**KW, **over})
    return list(run(det, df_of(bars)))


def key(ev):
    """(阶跃起点, 阶跃末根, 当天)。"""
    return (ev.step.start_idx, ev.step.end_idx, ev.today.start_idx)


def ref_fields(bars, s, e, t):
    """按计划字段定义独立重算一个实例的全部字段。"""
    c, o, h, v = bars["closes"], bars["opens"], bars["highs"], bars["vols"]
    r = lambda j: math.log(c[j] / c[j - 1])
    old_c = c[s - L:s]
    level = statistics.median(old_c)
    old_sigma = statistics.median(abs(r(j)) for j in range(s - L, s))
    vol_mean = sum(v[s - L:s]) / L
    height = math.log(c[e] / level)
    max_ret = max(r(j) for j in range(s, e + 1))
    new_c = c[e + 1:t]
    new_sigma = statistics.median(abs(r(j)) for j in range(e + 1, t))
    new_range = math.log(max(new_c) / min(new_c))
    old_range = math.log(max(old_c) / min(old_c))
    return {
        "old": dict(level=level, range=old_range, sigma=old_sigma, vol_mean=vol_mean),
        "step": dict(bars=e - s + 1, rise=c[e] / c[s - 1] - 1, max_ret=max_ret,
                     vs_left=max_ret / old_sigma,
                     vol_ratio=max(v[s:e + 1]) / vol_mean if vol_mean > 0 else None),
        "new": dict(bars=t - 1 - e, low=min(new_c), range=new_range, sigma=new_sigma),
        "today": dict(body=c[t] / o[t] - 1),
        "plateau": dict(days=t - e, height=height, old_flat_ratio=old_range / height,
                        vs_right=max_ret / new_sigma if new_sigma > 0 else None,
                        calm_ratio=new_range / height,
                        keep_ratio=math.log(min(c[e + 1:t + 1]) / level) / height,
                        vs_high=c[t] / max(h[s:t])),
    }


def assert_fields(obj, expected):
    for name, want in expected.items():
        got = getattr(obj, name)
        if want is None:
            assert got is None, name
        else:
            assert got == pytest.approx(want, rel=1e-12, abs=1e-15), name


# ── 实例集合 ──

def test_two_prefixes_each_form_a_family():
    evs = detect(base_bars())
    want = {(20, 20, t) for t in range(22, 35)} | {(20, 21, t) for t in range(23, 35)}
    assert {key(ev) for ev in evs} == want
    assert len(evs) == len(want)
    assert all(type(ev) is PlateauEvent for ev in evs)


def test_first_day_after_step_not_produced():
    evs = detect(base_bars())
    assert all(ev.today.start_idx >= ev.step.end_idx + 2 for ev in evs)
    assert not any(key(ev) in {(20, 20, 21), (20, 21, 22)} for ev in evs)
    assert min(ev.days for ev in evs) == 2


def test_family_ends_after_falling_back_to_old_level():
    bars = base_bars()
    evs = detect(bars)
    # 36..41 收盘又站回旧平台价位之上,但 35 那天已跌回,两族都到 34 为止
    assert all(c > 10.05 for c in bars["closes"][36:])
    assert max(ev.today.start_idx for ev in evs) == 34


def test_spans_and_confirm():
    for ev in detect(base_bars()):
        s, e, t = key(ev)
        assert (ev.start_idx, ev.end_idx, ev.confirm_idx) == (s - L, t, t)
        assert (ev.old.start_idx, ev.old.end_idx, ev.old.confirm_idx) == (s - L, s - 1, s - 1)
        assert (ev.step.start_idx, ev.step.end_idx, ev.step.confirm_idx) == (s, e, e)
        assert (ev.new.start_idx, ev.new.end_idx, ev.new.confirm_idx) == (e + 1, t - 1, t - 1)
        assert (ev.today.start_idx, ev.today.end_idx, ev.today.confirm_idx) == (t, t, t)
        assert Today.is_point and not PlateauEvent.is_point


# ── 字段值 ──

def test_fields_match_hand_calculation():
    bars = base_bars()
    evs = detect(bars)
    for ev in evs:
        s, e, t = key(ev)
        ref = ref_fields(bars, s, e, t)
        assert_fields(ev.old, ref["old"])
        assert_fields(ev.step, ref["step"])
        assert_fields(ev.new, ref["new"])
        assert_fields(ev.today, ref["today"])
        assert_fields(ev, ref["plateau"])


def test_fields_literal_spot_checks():
    by_key = {key(ev): ev for ev in detect(base_bars())}
    a = by_key[(20, 20, 22)]          # 一根阳线的前缀,新平台只有 21 那根
    assert a.old.level == pytest.approx(10.05)
    assert a.old.vol_mean == pytest.approx(1000.0)
    assert a.step.rise == pytest.approx(12.0 / 10.05 - 1)
    assert a.step.vol_ratio == pytest.approx(5.0)
    assert a.step.vs_left == pytest.approx(math.log(12 / 10.05) / math.log(10.05 / 10.0))
    assert a.new.bars == 1 and a.new.low == pytest.approx(14.0) and a.new.range == 0.0
    assert a.height == pytest.approx(math.log(12 / 10.05))
    assert a.keep_ratio == pytest.approx(math.log(13.9 / 10.05) / math.log(12 / 10.05))
    assert a.vs_high == pytest.approx(13.9 / 14.5)
    assert a.today.body == pytest.approx(13.9 / 13.95 - 1)
    b = by_key[(20, 21, 25)]          # 两根阳线的前缀
    assert b.step.bars == 2 and b.step.vol_ratio == pytest.approx(8.0)
    assert b.step.rise == pytest.approx(14.0 / 10.05 - 1)
    assert b.days == 4 and b.new.bars == 3
    assert b.calm_ratio == pytest.approx(math.log(14.0 / 13.9) / math.log(14.0 / 10.05))
    assert b.today.body == pytest.approx(14.0 / 13.95 - 1)


# ── 对象共用 ──

def test_shared_objects():
    evs = detect(base_bars())
    assert len({id(ev.old) for ev in evs}) == 1                       # 同一 s 一个旧平台
    by_prefix = {}
    for ev in evs:
        by_prefix.setdefault(ev.step.end_idx, set()).add(id(ev.step))
    assert {k: len(v) for k, v in by_prefix.items()} == {20: 1, 21: 1}   # 同一前缀一个阶跃
    today_ids = {}
    for ev in evs:
        today_ids.setdefault(ev.today.start_idx, set()).add(id(ev.today))
    assert all(len(v) == 1 for v in today_ids.values())               # 同一天跨族一个当天
    assert sum(1 for ev in evs if ev.today.start_idx == 30) == 2      # 30 那天两族都有
    assert len({id(ev.new) for ev in evs}) == len(evs)                # 新平台逐实例新造
    assert len({id(ev) for ev in evs}) == len(evs)


def test_child_slots_and_child():
    ev = detect(base_bars())[0]
    slots = ev.child_slots()
    assert list(slots) == ["old", "step", "new", "today"]
    assert slots["old"] is ev.old and slots["step"] is ev.step
    assert slots["new"] is ev.new and slots["today"] is ev.today
    assert all(not isinstance(v, tuple) and v is not None for v in slots.values())
    for name in slots:
        assert ev.child(name) is slots[name]
    with pytest.raises(KeyError):
        ev.child("first_bo")
    for sub in (ev.old, ev.step, ev.new, ev.today):
        assert sub.child_slots() == {}
    assert isinstance(ev.old, OldPlatform) and isinstance(ev.step, Step)
    assert isinstance(ev.new, NewPlatform) and isinstance(ev.today, Today)


# ── 流顺序 ──

def test_stream_sorted_by_end_then_start():
    evs = detect(base_bars())          # run() 自带 end_idx 升序 + 无完全重复对象校验
    keys = [(ev.end_idx, ev.start_idx) for ev in evs]
    assert keys == sorted(keys)


def test_stream_sorted_across_segments():
    """两段阶跃的族交错:后一段的实例 end 可能早于前一段的晚期实例。"""
    bars = base_bars()
    c = bars["closes"]
    # 30 起再来一段:30 收 17.0(阶跃),其后 31..34 在 17 附近,35..41 同样留在高位
    c2 = c[:30] + [17.0] + [16.9 if j % 2 == 0 else 17.0 for j in range(31, 42)]
    bars2 = dict(closes=c2, opens=list(c2), highs=[x + 0.1 for x in c2],
                 vols=bars["vols"])
    evs = detect(bars2)
    steps = {ev.step.start_idx for ev in evs}
    assert steps == {20, 30}
    keys = [(ev.end_idx, ev.start_idx) for ev in evs]
    assert keys == sorted(keys)
    # 30 那根对前缀 [20,20]/[20,21] 来说是新平台上的一天,照样产
    by_key = {key(ev): ev for ev in evs}
    at30 = by_key[(20, 21, 30)]
    # vs_high 口径 [s, t-1] = [20, 29],不含当天:最高价 14.0 + 0.1,当天收 17.0 → 追高了(> 1)
    assert at30.vs_high == pytest.approx(17.0 / 14.1)
    assert at30.vs_high > 1
    assert (20, 21, 33) in by_key                        # 新平台含 30 那根大阳线
    # 结束日相同、起点不同的实例确实存在(排序断言不是空检)
    ends = {}
    for ev in evs:
        ends.setdefault(ev.end_idx, set()).add(ev.start_idx)
    assert any(len(v) > 1 for v in ends.values())


def test_sort_key_includes_start_idx():
    """把各段实例的收集顺序倒过来(后一段先进),输出仍按 (end_idx, start_idx) 排——
    只按 end_idx 的稳定排序在这里会把起点大的排在前面,两种排法结果不同。"""
    bars = base_bars()
    c = bars["closes"]
    c2 = c[:30] + [17.0] + [16.9 if j % 2 == 0 else 17.0 for j in range(31, 42)]
    bars2 = dict(closes=c2, opens=list(c2), highs=[x + 0.1 for x in c2], vols=bars["vols"])

    class Prepend(PlateauDetector):
        def _emit_segment(self, s, seg_end, close, high, open_, vol, r, abs_r, price_ok,
                          out, today_cache):
            tmp = []
            super()._emit_segment(s, seg_end, close, high, open_, vol, r, abs_r, price_ok,
                                  tmp, today_cache)
            out[:0] = tmp
            self.collected = list(out)

    det = Prepend(**KW)
    evs = list(run(det, df_of(bars2)))
    keys = [(ev.end_idx, ev.start_idx) for ev in evs]
    assert keys == sorted(keys)
    end_only = [(ev.end_idx, ev.start_idx) for ev in sorted(det.collected, key=lambda e: e.end_idx)]
    assert end_only != keys


# ── on_gate ──

def gate_bars():
    """旧平台每天跌 1%,第 20 根涨 5%:开得了阶跃,但收盘仍低于旧平台收盘中位数。"""
    closes = [12.0 * 0.99 ** j for j in range(20)]
    c20 = closes[-1] * 1.05
    closes += [c20 if j % 2 == 0 else c20 * 1.001 for j in range(20, 30)]
    return dict(closes=closes, opens=list(closes), highs=[x + 0.1 for x in closes],
                vols=[1000.0] * 30)


def test_gate_step_not_above_old():
    bars = gate_bars()
    got = []
    det = PlateauDetector(**KW)
    det.on_gate = got.append
    tok = current_symbol.set("TEST")
    try:
        evs = list(run(det, df_of(bars)))
    finally:
        current_symbol.reset(tok)
    assert evs == []
    assert len(got) == 1
    g = got[0]
    level = statistics.median(bars["closes"][5:20])
    height = math.log(bars["closes"][20] / level)
    assert height < 0
    assert g.gate_name == "step_not_above_old"
    assert g.failure_event_window == (20, 20)
    assert (g.start_idx, g.gate_idx, g.anchor_bar) == (20, 20, 20)
    assert g.measured.kind == "log_ratio" and g.measured.label == "height"
    assert g.measured.value == pytest.approx(height)
    assert g.threshold == 0.0 and g.op == ">" and g.threshold_param is None
    assert g.evaluation_lookback == (5, 19)
    assert g.symbol == "TEST"
    assert g.stream is None


def test_normal_family_end_emits_no_gate():
    got = []
    det = PlateauDetector(**{**KW, "max_days": 5})
    det.on_gate = got.append
    evs = list(run(det, df_of(base_bars())))
    assert evs and got == []


# ── None 语义 ──

def test_vol_ratio_none_when_old_volume_all_zero():
    bars = base_bars()
    bars["vols"] = [0.0] * 20 + bars["vols"][20:]
    evs = detect(bars)
    assert {key(ev) for ev in evs} == {key(ev) for ev in detect(base_bars())}
    assert all(ev.old.vol_mean == 0.0 for ev in evs)
    assert all(ev.step.vol_ratio is None for ev in evs)


def test_vs_right_none_when_new_sigma_zero():
    bars = base_bars()
    bars["closes"][22] = 14.0             # 22 与 21 同收:新平台 [22,22] 的 σ = 0
    by_key = {key(ev): ev for ev in detect(bars)}
    assert by_key[(20, 21, 23)].new.sigma == 0.0
    assert by_key[(20, 21, 23)].vs_right is None
    assert by_key[(20, 20, 22)].vs_right is not None   # [21,21] 的 σ = |r_21| > 0


# ── 过滤型参数 ──

@pytest.mark.parametrize("m", [2, 5, 10, 14])
def test_max_days_filter_equivalence(m):
    field, op = PlateauDetector.filter_params["max_days"]
    assert (field, op) == ("days", "<=")
    loose = detect(base_bars(), max_days=40)
    direct = detect(base_bars(), max_days=m)
    filtered = [ev for ev in loose if getattr(ev, field) <= m]
    assert direct and filtered == direct


# ── 数据边界 ──

def test_too_short_data_produces_nothing():
    bars = base_bars()
    short = {k: v[:L + 1] for k, v in bars.items()}
    assert detect(short) == []


def test_step_needs_l_plus_one_bars_before_it():
    """阶跃起点最早是第 L+1 根:同样的形状,阶跃落在第 L 根就不认,落在第 L+1 根就认。"""
    def shaped(step_at):
        closes = [10.0 if j % 2 == 0 else 10.05 for j in range(step_at)]
        closes += [12.0] + [11.9 if j % 2 == 0 else 12.0 for j in range(10)]
        return dict(closes=closes, opens=list(closes), highs=[x + 0.1 for x in closes],
                    vols=[1000.0] * len(closes))
    assert detect(shaped(L)) == []
    evs = detect(shaped(L + 1))
    assert evs and {ev.step.start_idx for ev in evs} == {L + 1}


def test_nan_volume_in_old_platform_skips_step():
    bars = base_bars()
    bars["vols"][10] = float("nan")
    assert detect(bars) == []


def test_nan_volume_on_new_platform_does_not_matter():
    bars = base_bars()
    bars["vols"][28] = float("nan")
    assert detect(bars) == detect(base_bars())


def test_bad_price_on_new_platform_truncates_family():
    bars = base_bars()
    bars["closes"][28] = 0.0
    evs = detect(bars)
    clean = [ev for ev in detect(base_bars()) if ev.today.start_idx < 28]
    assert evs == clean
    for ev in evs:
        assert not any(isinstance(v, float) and np.isnan(v) for v in vars(ev).values())


def test_constructor_rejects_degenerate_windows():
    with pytest.raises(ValueError):
        PlateauDetector(**{**KW, "old_window": 0})
    with pytest.raises(ValueError):
        PlateauDetector(**{**KW, "max_step_bars": 0})


# ── 读窗口口径(小 L、各根 |r| 不等,字面数断言) ──

def small_l_bars():
    """L = 3。旧平台 [1,3] 收盘 10.1 / 10.05 / 10.35,|r| 三根各不相同
    (ln(10.1/10.0)、ln(10.1/10.05)、ln(10.35/10.05)),中位数 = ln(10.1/10.0)。
    4、5 两根阶跃:r_4 = ln(11/10.35) 过 3·σ_4;r_5 = ln(11.6/11) 过 3·σ_s(σ_s = σ_4),
    但不过逐根滚动的 3·σ_5(σ_5 = median |r| over [2,4] = ln(10.35/10.05))。
    阶跃第一根量 9000 大于末根 4000。6..10 是新平台。
    """
    closes = [10.0, 10.1, 10.05, 10.35, 11.0, 11.6, 11.5, 11.7, 11.55, 11.65, 11.6]
    vols = [1000.0] * 4 + [9000.0, 4000.0] + [2000.0] * 5
    return dict(closes=closes, opens=list(closes), highs=[x + 0.1 for x in closes], vols=vols)


def test_small_window_literals():
    ln = math.log
    bars = small_l_bars()
    sigma_s = ln(10.1 / 10.0)
    r4, r5 = ln(11.0 / 10.35), ln(11.6 / 11.0)
    # 前提自检:r_5 过 σ_s 的门槛、不过滚动 σ_5 的门槛
    assert r5 >= 3 * sigma_s and r5 < 3 * ln(10.35 / 10.05)
    evs = detect(bars, old_window=3)
    by_key = {key(ev): ev for ev in evs}
    assert {k[:2] for k in by_key} == {(4, 4), (4, 5)}        # 第 5 根按 σ_s 并入
    assert {k for k in by_key if k[:2] == (4, 4)} == {(4, 4, t) for t in range(6, 11)}
    assert {k for k in by_key if k[:2] == (4, 5)} == {(4, 5, t) for t in range(7, 11)}

    a = by_key[(4, 4, 6)]
    assert (a.old.start_idx, a.old.end_idx) == (1, 3)
    assert a.old.level == pytest.approx(10.1)
    assert a.old.sigma == pytest.approx(sigma_s)
    assert a.old.range == pytest.approx(ln(10.35 / 10.05))
    assert a.step.max_ret == pytest.approx(r4)
    assert a.step.vs_left == pytest.approx(r4 / sigma_s)
    assert a.old_flat_ratio == pytest.approx(ln(10.35 / 10.05) / ln(11.0 / 10.1))
    assert a.new.sigma == pytest.approx(r5)                    # 新平台 [5,5]
    assert a.vs_right == pytest.approx(r4 / r5)
    assert a.step.vol_ratio == pytest.approx(9.0)

    b8 = by_key[(4, 5, 8)]                                     # 新平台 [6,7]
    assert b8.step.max_ret == pytest.approx(r4)                # 段内最大 r 是第一根
    assert b8.step.vs_left == pytest.approx(r4 / sigma_s)
    assert b8.step.vol_ratio == pytest.approx(9.0)             # 段内最大量 9000,不是末根 4000
    assert b8.old_flat_ratio == pytest.approx(ln(10.35 / 10.05) / ln(11.6 / 10.1))
    new_sigma8 = (ln(11.6 / 11.5) + ln(11.7 / 11.5)) / 2
    assert b8.new.sigma == pytest.approx(new_sigma8)
    assert b8.new.range == pytest.approx(ln(11.7 / 11.5))
    assert b8.vs_right == pytest.approx(r4 / new_sigma8)

    b9 = by_key[(4, 5, 9)]                                     # 新平台 [6,8],|r| 三根各不相同
    assert b9.new.sigma == pytest.approx(ln(11.7 / 11.55))
    assert b9.vs_right == pytest.approx(r4 / ln(11.7 / 11.55))


# ── 分支补全 ──

def three_step_bars():
    """主样例的旧平台 + 三根大阳线 12 / 14 / 16(20..22),23..34 在 15.9 / 16.0 交替。"""
    closes = [10.0 if j % 2 == 0 else 10.05 for j in range(20)]
    closes += [12.0, 14.0, 16.0]
    closes += [15.9 if j % 2 == 0 else 16.0 for j in range(23, 35)]
    return dict(closes=closes, opens=list(closes), highs=[x + 0.1 for x in closes],
                vols=[1000.0] * len(closes))


def test_segment_truncated_at_max_step_bars_then_next_bar_opens():
    bars = three_step_bars()
    spans5 = {(ev.step.start_idx, ev.step.end_idx) for ev in detect(bars, max_step_bars=5)}
    assert spans5 == {(20, 20), (20, 21), (20, 22)}
    evs2 = detect(bars, max_step_bars=2)
    spans2 = {(ev.step.start_idx, ev.step.end_idx) for ev in evs2}
    assert spans2 == {(20, 20), (20, 21), (22, 22)}           # 满 2 根收段,第 22 根另开一段
    new_seg = [ev for ev in evs2 if ev.step.start_idx == 22]
    assert {(ev.old.start_idx, ev.old.end_idx) for ev in new_seg} == {(7, 21)}
    assert {ev.today.start_idx for ev in new_seg} == set(range(24, 35))


def declining_bars(rate, factors, n=30):
    """旧平台每天跌 rate,第 20 根起依次乘 factors(阶跃),之后在末价与末价×1.001 间交替。"""
    closes = [12.0 * (1 - rate) ** j for j in range(20)]
    for f in factors:
        closes.append(closes[-1] * f)
    last = closes[-1]
    closes += [last if j % 2 == 0 else last * 1.001 for j in range(len(closes), n)]
    return dict(closes=closes, opens=list(closes), highs=[x + 0.1 for x in closes],
                vols=[1000.0] * n)


def detect_with_gates(bars, **over):
    det = PlateauDetector(**{**KW, **over})
    got = []
    det.on_gate = got.append
    return list(run(det, df_of(bars))), got


def test_first_prefix_below_old_second_above():
    bars = declining_bars(0.01, [1.05, 1.10])
    level = statistics.median(bars["closes"][5:20])
    assert math.log(bars["closes"][20] / level) <= 0 < math.log(bars["closes"][21] / level)
    evs, gates = detect_with_gates(bars)
    assert [g.failure_event_window for g in gates] == [(20, 20)]
    assert {(ev.step.start_idx, ev.step.end_idx) for ev in evs} == {(20, 21)}
    assert {ev.today.start_idx for ev in evs} == set(range(23, 30))


def test_close_equal_to_old_level_ends_family():
    bars = base_bars()
    bars["closes"][30] = 10.05            # 恰好等于旧平台价位(收盘中位数 10.05)
    evs = [ev for ev in detect(bars) if ev.step.start_idx == 20]
    assert evs and max(ev.today.start_idx for ev in evs) == 29
    bars["closes"][30] = 10.05 + 1e-9     # 略高一点就不收族
    evs = [ev for ev in detect(bars) if ev.step.start_idx == 20]
    assert 30 in {ev.today.start_idx for ev in evs}
    assert max(ev.today.start_idx for ev in evs) == 34


def merge_bars():
    """旧平台每天跌 2%,三根各涨 7%:前两个前缀没高过旧平台价位(各发一条 gate),
    第三个前缀高过。用 gate 条数看出这段阶跃并入了几根。"""
    return declining_bars(0.02, [1.07, 1.07, 1.07])


def test_merge_stops_at_bad_bar():
    _, gates = detect_with_gates(merge_bars())
    assert [g.failure_event_window for g in gates] == [(20, 20), (20, 21)]   # 干净时并到 22
    bad_price = merge_bars()
    bad_price["opens"][21] = 0.0
    evs, gates = detect_with_gates(bad_price)
    assert [g.failure_event_window for g in gates] == [(20, 20)] and evs == []
    bad_vol = merge_bars()
    bad_vol["vols"][21] = float("nan")
    evs, gates = detect_with_gates(bad_vol)
    assert [g.failure_event_window for g in gates] == [(20, 20)] and evs == []


def test_bad_price_on_first_day_after_step_skips_prefix():
    """阶跃 [20,22];第 23 根(前缀 [20,22] 的 e+1)开盘价坏:该前缀整个不产、不报错;
    前缀 [20,20] 只剩 t=22,前缀 [20,21] 的首个当天就是 23,也不产。"""
    bars = three_step_bars()
    bars["opens"][23] = 0.0
    evs = detect(bars)
    assert {key(ev) for ev in evs} == {(20, 20, 22)}
