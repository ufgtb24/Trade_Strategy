"""PlateauDetector:旧平台 → 一串最高价连续抬高的阶跃 → 新平台,逐天产截到当天的复合事件。

只直接调用 PlateauDetector(...).detect(df),不经 app 的 dag_spec。期望值按字段定义用纯 Python
(math / statistics)独立重算,不复用 detector 的 numpy 实现。合成 K 线里旧平台、新平台的最高价
一律压平,免得交替的收盘让最高价「每隔一根抬高一次」、被往前找起点吸进阶跃。
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
OVERHEAD_W = 60
CALM_W = 10
DUMP_W = 10
KW = dict(old_window=L, strong_k=3.0, max_step_bars=30, max_pause=3, max_days=40,
          overhead_window=OVERHEAD_W, calm_window=CALM_W, dump_window=DUMP_W)


def make_df(closes, highs=None, lows=None, opens=None, vols=None):
    n = len(closes)
    return pd.DataFrame({
        'open': opens or list(closes),
        'high': highs or [c + 0.1 for c in closes],
        'low': lows or [c - 0.1 for c in closes],
        'close': list(closes),
        'volume': vols or [1000.0] * n,
    })


def old_closes(n=20):
    return [10.0 if j % 2 == 0 else 10.05 for j in range(n)]


def base_bars():
    """主样例(42 根):
    0..19  旧平台,收盘 10.0 / 10.05 交替,最高价一律 10.2,量 1000
    20, 21 两根大阳线 12.0、14.0(最高价 12.1、14.5),量 5000、8000 → 阶跃 [20, 21]
    22..34 新平台,收盘 13.9 / 14.0 交替(偶数 13.9),开盘一律 13.95,最高价一律 14.1,量 2000
    35     跌回 10.0(≤ 旧平台价位 10.05),最高价 10.1
    36..41 10.1 / 10.15 交替,最高价一律 10.3,回到旧平台价位之上但不构成新阶跃
    """
    closes = old_closes() + [12.0, 14.0]
    closes += [13.9 if j % 2 == 0 else 14.0 for j in range(22, 35)]
    closes += [10.0]
    closes += [10.1 if j % 2 == 0 else 10.15 for j in range(36, 42)]
    opens = list(closes)
    for j in range(22, 35):
        opens[j] = 13.95
    highs = [10.2] * 20 + [12.1, 14.5] + [14.1] * 13 + [10.1] + [10.3] * 6
    vols = [1000.0] * 20 + [5000.0, 8000.0] + [2000.0] * 20
    return dict(closes=closes, opens=opens, highs=highs, vols=vols)


def resume_bars():
    """停一下又续上(41 根):0..19 旧平台;20、21 阶跃(最高 12.1、14.5);22、23 停顿(最高 14.2、
    14.0,没再抬高);24 猛涨到 17.0、最高 17.5(创新高)→ 续上;25 18.0、最高 18.5;26 起最高价回落,
    26..40 在 17.8 / 17.9 交替,最高 18.0。量:阶跃 5000、8000,停顿 1500,续上 9000、7000,新平台 2000。"""
    closes = old_closes() + [12.0, 14.0, 13.6, 13.7, 17.0, 18.0]
    closes += [17.8 if j % 2 == 0 else 17.9 for j in range(26, 41)]
    highs = [10.2] * 20 + [12.1, 14.5, 14.2, 14.0, 17.5, 18.5] + [18.0] * 15
    vols = [1000.0] * 20 + [5000.0, 8000.0, 1500.0, 1500.0, 9000.0, 7000.0] + [2000.0] * 15
    return dict(closes=closes, opens=list(closes), highs=highs, vols=vols)


def pause_strong_bars():
    """停顿窗里有猛涨、但没创新高(41 根):20、21 阶跃(最高 14.5);22 跌到 12.5(最高 13.0);
    23 猛涨回 13.9(r 远超门槛)但最高 14.2 < 14.5 → 既不算续上、也不另开阶跃;24.. 13.9 / 14.0 交替。"""
    closes = old_closes() + [12.0, 14.0, 12.5, 13.9]
    closes += [13.9 if j % 2 == 0 else 14.0 for j in range(24, 41)]
    highs = [10.2] * 20 + [12.1, 14.5, 13.0, 14.2] + [14.1] * 17
    return dict(closes=closes, opens=list(closes), highs=highs, vols=[1000.0] * len(closes))


def df_of(bars):
    return make_df(bars["closes"], highs=bars["highs"], opens=bars["opens"], vols=bars["vols"])


def detect(bars, **over):
    det = PlateauDetector(**{**KW, **over})
    return list(run(det, df_of(bars)))


def detect_with_gates(bars, **over):
    det = PlateauDetector(**{**KW, **over})
    got = []
    det.on_gate = got.append
    return list(run(det, df_of(bars))), got


def key(ev):
    """(阶跃起点, 阶跃末根, 当天)。"""
    return (ev.step.start_idx, ev.step.end_idx, ev.today.start_idx)


def ref_sigma(xs):
    """波动:中位数,为 0 时取平均数。"""
    xs = list(xs)
    m = statistics.median(xs)
    return m if m != 0 else sum(xs) / len(xs)


def ref_low_age(c, e, t):
    """距 [e+2, t] 里最近一次严格创新低(低于 [e+1, j-1] 全部收盘)的根数;没有为 None。"""
    last = None
    for j in range(e + 2, t + 1):
        if c[j] < min(c[e + 1:j]):
            last = j
    return None if last is None else t - last


def ref_dump(c, s, e, t, d=DUMP_W):
    """对 u ∈ [e+1, t]:peak = [s, u] 最高收盘,recent = [max(s, u-d), u] 最高收盘;
    eaten = ln(recent / c_u) / ln(peak / c_{s-1}),取最大;peak 不高于 c_{s-1} 的 u 不算,一个都不算时为 None。"""
    base, best = c[s - 1], None
    for u in range(e + 1, t + 1):
        peak = max(c[s:u + 1])
        if peak > base:
            recent = max(c[max(s, u - d):u + 1])
            x = math.log(recent / c[u]) / math.log(peak / base)
            best = x if best is None else max(best, x)
    return best


def ref_fields(bars, s, e, t, lw=L):
    """按字段定义独立重算一个实例的全部字段(lw = 旧平台根数)。"""
    L = lw
    c, o, h, v = bars["closes"], bars["opens"], bars["highs"], bars["vols"]
    r = lambda j: math.log(c[j] / c[j - 1])
    old_c = c[s - L:s]
    level = statistics.median(old_c)
    old_sigma = ref_sigma(abs(r(j)) for j in range(s - L, s))
    vol_mean = sum(v[s - L:s]) / L
    top = max(c[s:e + 1])
    height = math.log(top / level)
    max_ret = max(r(j) for j in range(s, e + 1))
    new_c = c[e + 1:t]
    new_sigma = ref_sigma(abs(r(j)) for j in range(e + 1, t))
    new_range = math.log(max(new_c) / min(new_c))
    recent = new_c[-CALM_W:]
    recent_range = math.log(max(recent) / min(recent))
    new_vols = [x for x in v[e + 1:t] if math.isfinite(x) and x >= 0]
    new_vol_mean = sum(new_vols) / len(new_vols) if new_vols else None
    step_vol_max = max(v[s:e + 1])
    old_range = math.log(max(old_c) / min(old_c))
    lo = min(max(0, t - OVERHEAD_W), s - 1)
    return {
        "old": dict(level=level, range=old_range, sigma=old_sigma, vol_mean=vol_mean),
        "step": dict(bars=e - s + 1, rise=top / c[s - 1] - 1, max_ret=max_ret,
                     vs_left=max_ret / old_sigma,
                     vol_ratio=step_vol_max / vol_mean if vol_mean > 0 else None,
                     vol_mean=sum(v[s:e + 1]) / (e - s + 1), vol_max=step_vol_max),
        "new": dict(bars=t - 1 - e, low=min(new_c), range=new_range, recent_range=recent_range,
                    sigma=new_sigma, vol_mean=new_vol_mean),
        "today": dict(body=c[t] / o[t] - 1),
        "plateau": dict(days=t - e, height=height, old_flat_ratio=old_range / height,
                        vs_right=max_ret / new_sigma if new_sigma > 0 else None,
                        calm_ratio=recent_range / height,
                        keep_ratio=math.log(c[t] / level) / height,
                        vs_high=c[t] / max(h[s:t]),
                        overhead=max(h[lo:s]) / c[t],
                        vol_shrink=(new_vol_mean / step_vol_max
                                    if new_vol_mean is not None and step_vol_max > 0 else None),
                        low_age=ref_low_age(c, e, t),
                        dump_ratio=ref_dump(c, s, e, t)),
    }


def assert_fields(obj, expected):
    for name, want in expected.items():
        got = getattr(obj, name)
        if want is None:
            assert got is None, name
        else:
            assert got == pytest.approx(want, rel=1e-12, abs=1e-15), name


def assert_all_fields(bars, evs, lw=L):
    for ev in evs:
        ref = ref_fields(bars, *key(ev), lw=lw)
        assert_fields(ev.old, ref["old"])
        assert_fields(ev.step, ref["step"])
        assert_fields(ev.new, ref["new"])
        assert_fields(ev.today, ref["today"])
        assert_fields(ev, ref["plateau"])


# ── 实例集合 ──

def test_one_step_one_family():
    evs = detect(base_bars())
    # 阶跃 [20, 21]:22 最高价回落、阶跃完成;不再按前缀各成一族;35 跌回旧平台价位不收族
    assert {key(ev) for ev in evs} == {(20, 21, t) for t in range(23, 42)}
    assert len(evs) == 19
    assert all(type(ev) is PlateauEvent for ev in evs)


def test_first_day_after_step_not_produced():
    evs = detect(base_bars())
    assert all(ev.today.start_idx >= ev.step.end_idx + 2 for ev in evs)
    assert min(ev.days for ev in evs) == 2


def test_falling_back_to_old_level_does_not_end_family():
    """35 那天收盘跌回旧平台价位:照样产(keep_ratio < 0,由 where 判不买);36..41 站回来后照样产。"""
    bars = base_bars()
    by_t = {ev.today.start_idx: ev for ev in detect(bars)}
    assert by_t[35].keep_ratio < 0
    assert all(by_t[t].keep_ratio > 0 for t in range(36, 42))
    assert max(by_t) == 41


def test_spans_and_confirm():
    for ev in detect(resume_bars()) + detect(base_bars()):
        s, e, t = key(ev)
        assert (ev.start_idx, ev.end_idx, ev.confirm_idx) == (s - L, t, t)
        assert (ev.old.start_idx, ev.old.end_idx, ev.old.confirm_idx) == (s - L, s - 1, s - 1)
        assert (ev.step.start_idx, ev.step.end_idx, ev.step.confirm_idx) == (s, e, e)
        assert (ev.new.start_idx, ev.new.end_idx, ev.new.confirm_idx) == (e + 1, t - 1, t - 1)
        assert (ev.today.start_idx, ev.today.end_idx, ev.today.confirm_idx) == (t, t, t)
    assert Today.is_point and not PlateauEvent.is_point


# ── 起点、终点、续上 ──

def test_start_walks_back_along_rising_highs():
    """猛涨那根(20)之前 18、19 两根最高价一根比一根高(涨得很少):往前找把它们算进阶跃,
    17 最高价没抬高,停在 18。"""
    bars = base_bars()
    bars["closes"][18], bars["highs"][18] = 10.1, 10.3
    bars["closes"][19], bars["highs"][19] = 10.15, 10.4
    evs = detect(bars)
    assert {(ev.step.start_idx, ev.step.end_idx) for ev in evs} == {(18, 21)}
    ev = evs[0]
    assert (ev.old.start_idx, ev.old.end_idx) == (3, 17)
    assert ev.step.bars == 4
    assert ev.step.rise == pytest.approx(14.0 / bars["closes"][17] - 1)
    assert_all_fields(bars, evs)


def test_end_by_high_and_height_by_close():
    """22 收盘回落到 13.5 但最高价冲到 15.0(上影线):最高价还在抬高,22 仍是阶跃;阶跃抬了多少按
    收盘算,取段内最高收盘 14.0(21),不取末根收盘 13.5,也不取最高价。"""
    bars = base_bars()
    bars["closes"][22], bars["highs"][22] = 13.5, 15.0
    evs = detect(bars)
    assert {(ev.step.start_idx, ev.step.end_idx) for ev in evs} == {(20, 22)}
    ev = evs[0]
    assert ev.height == pytest.approx(math.log(14.0 / 10.05))
    assert ev.step.rise == pytest.approx(14.0 / 10.05 - 1)
    assert ev.vs_high == pytest.approx(bars["closes"][ev.today.start_idx] / 15.0)
    assert_all_fields(bars, evs)


def test_resume_after_pause_overrides_forward_only():
    bars = resume_bars()
    evs = detect(bars)
    keys = {key(ev) for ev in evs}
    # 第一个版本 [20,21]:停顿那几天照旧产(23),续上那天(24)起换版本;第二个版本 [20,25] 含停顿两根
    assert keys == {(20, 21, 23)} | {(20, 25, t) for t in range(27, 41)}
    assert len({id(ev.old) for ev in evs}) == 1                      # 同一个起点一个旧平台
    v2 = next(ev for ev in evs if ev.step.end_idx == 25)
    assert v2.step.bars == 6
    assert v2.step.vol_max == 9000.0
    assert v2.step.max_ret == pytest.approx(math.log(17.0 / 13.7))
    assert v2.step.rise == pytest.approx(18.0 / 10.05 - 1)
    assert_all_fields(bars, evs)


def test_strong_bar_in_pause_without_new_high_is_neither_resume_nor_new_step():
    evs = detect(pause_strong_bars())
    assert {(ev.step.start_idx, ev.step.end_idx) for ev in evs} == {(20, 21)}
    assert {ev.today.start_idx for ev in evs} == set(range(23, 41))


def test_pause_longer_than_max_pause_starts_no_resume():
    """停顿 2 根才续上:max_pause = 1 时不算续上(那一根在停顿窗外,另开一次阶跃)。"""
    evs = detect(resume_bars(), max_pause=1)
    assert (20, 25) not in {(ev.step.start_idx, ev.step.end_idx) for ev in evs}
    assert 21 in {ev.step.end_idx for ev in evs if ev.step.start_idx == 20}


@pytest.mark.parametrize("make,over", [
    (resume_bars, {}),
    (resume_bars, {"max_step_bars": 4}),       # 续上之后太长:这次阶跃从续上那天起不再产
    (pause_strong_bars, {}),
    (base_bars, {}),
])
def test_causal_truncation(make, over):
    """数据只给到第 T 根时产出的(当天 ≤ T)实例,与给全数据时当天 ≤ T 的实例逐字段相等:
    续上、停顿窗都只往后覆盖,不拿后来的行情改当时的判断。"""
    bars = make()
    full = detect(bars, **over)
    n = len(bars["closes"])
    for T in range(L + 2, n):
        cut = {k: v[:T + 1] for k, v in bars.items()}
        assert detect(cut, **over) == [ev for ev in full if ev.end_idx <= T], T


def test_too_long_resume_stops_the_step_at_resume():
    evs = detect(resume_bars(), max_step_bars=4)
    assert {key(ev) for ev in evs} == {(20, 21, 23)}


# ── 字段值 ──

def test_fields_match_hand_calculation():
    for make in (base_bars, resume_bars, pause_strong_bars):
        bars = make()
        assert_all_fields(bars, detect(bars))


def test_fields_literal_spot_checks():
    by_key = {key(ev): ev for ev in detect(base_bars())}
    a = by_key[(20, 21, 23)]          # 新平台只有 22 那根
    assert a.old.level == pytest.approx(10.05)
    assert a.old.vol_mean == pytest.approx(1000.0)
    assert a.step.rise == pytest.approx(14.0 / 10.05 - 1)
    assert a.step.vol_ratio == pytest.approx(8.0)
    assert a.step.vol_max == 8000.0
    assert a.step.vs_left == pytest.approx(math.log(12 / 10.05) / math.log(10.05 / 10.0))
    assert a.new.bars == 1 and a.new.low == pytest.approx(13.9) and a.new.range == 0.0
    assert a.height == pytest.approx(math.log(14 / 10.05))
    assert a.keep_ratio == pytest.approx(1.0)
    assert a.vs_high == pytest.approx(14.0 / 14.5)
    assert a.vol_shrink == pytest.approx(2000.0 / 8000.0)
    b = by_key[(20, 21, 25)]
    assert b.step.bars == 2
    assert b.days == 4 and b.new.bars == 3
    assert b.calm_ratio == pytest.approx(math.log(14.0 / 13.9) / math.log(14.0 / 10.05))
    assert b.today.body == pytest.approx(14.0 / 13.95 - 1)


def slide_bars():
    """主样例到第 29 根;30..41 每天收盘乘 0.973,12 天从 14.0 慢慢跌到约 10.1(回到旧平台价位),
    最高价比收盘高 0.05(一路走低,不构成新阶跃)。"""
    bars = base_bars()
    c = bars["closes"][:30]
    for _ in range(30, 42):
        c.append(c[-1] * 0.973)
    return dict(closes=c, opens=list(c), highs=bars["highs"][:30] + [x + 0.05 for x in c[30:]],
                vols=bars["vols"])


def test_dump_ratio_fast_drop_counts_slow_slide_does_not():
    """35 一天从 13.9 跌到 10.0:最近 10 根的最高收盘 14.0 跌到 10.0,吃掉 ln(14/10)/ln(14/10.05) > 1
    (跌破阶跃起点前一天的收盘),之后各天一直带着(只增不减)。慢慢阴跌回去的(每天 -2.7%),同样跌回
    旧平台价位,dump_window = 2 时最近 2 根之内只跌掉一小截,读数很小。"""
    bars = base_bars()
    by_t = {ev.today.start_idx: ev for ev in detect(bars)}
    wobble = math.log(14.0 / 13.9) / math.log(14.0 / 10.05)
    assert by_t[30].dump_ratio == pytest.approx(wobble)
    big = math.log(14.0 / 10.0) / math.log(14.0 / 10.05)
    assert big > 1
    assert all(by_t[t].dump_ratio == pytest.approx(big) for t in range(35, 42))
    slide = slide_bars()
    evs = detect(slide, dump_window=2)
    last = max(evs, key=lambda ev: ev.today.start_idx)
    assert last.keep_ratio < 0.1                      # 已经跌回旧平台价位附近
    assert last.dump_ratio == pytest.approx(math.log(1 / 0.973 ** 2) / math.log(14.0 / 10.05))
    assert last.dump_ratio < 0.2
    for ev in evs:
        assert ev.dump_ratio == pytest.approx(ref_dump(slide["closes"], *key(ev), d=2))


# ── 对象共用 ──

def test_shared_objects():
    evs = detect(resume_bars())
    assert len({id(ev.old) for ev in evs}) == 1                       # 同一 s 一个旧平台
    by_version = {}
    for ev in evs:
        by_version.setdefault(ev.step.end_idx, set()).add(id(ev.step))
    assert {k: len(v) for k, v in by_version.items()} == {21: 1, 25: 1}   # 一个版本一个阶跃
    today_ids = {}
    for ev in evs:
        today_ids.setdefault(ev.today.start_idx, set()).add(id(ev.today))
    assert all(len(v) == 1 for v in today_ids.values())
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

def two_step_bars():
    """主样例前 30 根 + 30 收 17.0(最高 17.5,第二次阶跃),31..41 在 16.9 / 17.0 交替(最高 17.1)。"""
    bars = base_bars()
    c = bars["closes"][:30] + [17.0] + [16.9 if j % 2 == 0 else 17.0 for j in range(31, 42)]
    h = bars["highs"][:30] + [17.5] + [17.1] * 11
    return dict(closes=c, opens=list(c), highs=h, vols=bars["vols"])


def test_stream_sorted_across_steps():
    """两次阶跃的族交错:后一次的实例 end 可能早于前一次的晚期实例。"""
    bars = two_step_bars()
    evs = detect(bars)
    assert {ev.step.start_idx for ev in evs} == {20, 30}
    keys = [(ev.end_idx, ev.start_idx) for ev in evs]
    assert keys == sorted(keys)
    by_key = {key(ev): ev for ev in evs}
    at30 = by_key[(20, 21, 30)]                      # 30 那根对第一次阶跃来说是新平台上的一天
    assert at30.vs_high == pytest.approx(17.0 / 14.5)  # [20, 29] 最高价 14.5,当天收 17.0 → 追高
    assert (20, 21, 33) in by_key
    ends = {}
    for ev in evs:
        ends.setdefault(ev.end_idx, set()).add(ev.start_idx)
    assert any(len(v) > 1 for v in ends.values())
    assert_all_fields(bars, evs)


def test_sort_key_includes_start_idx():
    """把各次阶跃的收集顺序倒过来(后一次先进),输出仍按 (end_idx, start_idx) 排——
    只按 end_idx 的稳定排序在这里会把起点大的排在前面,两种排法结果不同。"""
    class Prepend(PlateauDetector):
        def _emit_step(self, s, versions, tail, *args):
            out = args[-2]
            tmp = []
            super()._emit_step(s, versions, tail, *args[:-2], tmp, args[-1])
            out[:0] = tmp
            self.collected = list(out)

    det = Prepend(**KW)
    evs = list(run(det, df_of(two_step_bars())))
    keys = [(ev.end_idx, ev.start_idx) for ev in evs]
    assert keys == sorted(keys)
    end_only = [(ev.end_idx, ev.start_idx) for ev in sorted(det.collected, key=lambda e: e.end_idx)]
    assert end_only != keys


# ── on_gate ──

def gate_bars():
    """旧平台每天跌 1%,第 20 根涨 5%(最高价抬高):开得了阶跃,但收盘仍低于旧平台收盘中位数。
    之后最高价压在 20 之下,阶跃只有 20 一根。"""
    closes = [12.0 * 0.99 ** j for j in range(20)]
    c20 = closes[-1] * 1.05
    closes += [c20 if j % 2 == 0 else c20 * 1.001 for j in range(20, 30)]
    highs = [x + 0.1 for x in closes[:21]] + [c20 + 0.05] * 9
    return dict(closes=closes, opens=list(closes), highs=highs, vols=[1000.0] * 30)


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


def three_step_bars():
    """旧平台 + 三根大阳线 12 / 14 / 16(20..22,最高价逐根抬高),23..34 在 15.9 / 16.0 交替(最高 16.05)。"""
    closes = old_closes() + [12.0, 14.0, 16.0]
    closes += [15.9 if j % 2 == 0 else 16.0 for j in range(23, 35)]
    highs = [10.2] * 20 + [12.1, 14.1, 16.1] + [16.05] * 12
    return dict(closes=closes, opens=list(closes), highs=highs, vols=[1000.0] * len(closes))


def test_gate_step_too_long():
    evs, gates = detect_with_gates(three_step_bars(), max_step_bars=2)
    assert evs == []
    assert [g.gate_name for g in gates] == ["step_too_long"]
    g = gates[0]
    assert g.failure_event_window == (20, 22)
    assert g.measured.kind == "count" and g.measured.value == 3.0
    assert g.threshold == 2.0 and g.op == "<=" and g.threshold_param == "max_step_bars"
    evs = detect(three_step_bars())
    assert {(ev.step.start_idx, ev.step.end_idx) for ev in evs} == {(20, 22)}
    assert {ev.today.start_idx for ev in evs} == set(range(24, 35))


def test_normal_family_end_emits_no_gate():
    evs, got = detect_with_gates(base_bars(), max_days=5)
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
    assert by_key[(20, 21, 24)].vs_right is None           # [22,23] 两根都同收
    assert by_key[(20, 21, 25)].vs_right is not None       # [22,24] 中位数 0、平均数 > 0


# ── 过滤型参数 ──

@pytest.mark.parametrize("m", [2, 5, 10, 14])
def test_max_days_filter_equivalence(m):
    field, op = PlateauDetector.filter_params["max_days"]
    assert (field, op) == ("days", "<=")
    for make in (base_bars, resume_bars):
        loose = detect(make(), max_days=40)
        direct = detect(make(), max_days=m)
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
        closes = old_closes(step_at) + [12.0] + [11.9 if j % 2 == 0 else 12.0 for j in range(10)]
        highs = [10.2] * step_at + [12.1] + [12.05] * 10
        return dict(closes=closes, opens=list(closes), highs=highs, vols=[1000.0] * len(closes))
    assert detect(shaped(L)) == []
    evs = detect(shaped(L + 1))
    assert evs and {ev.step.start_idx for ev in evs} == {L + 1}


def test_nan_volume_in_old_platform_skips_step():
    bars = base_bars()
    bars["vols"][10] = float("nan")
    assert detect(bars) == []


def test_nan_volume_on_new_platform_only_skips_that_bar_in_vol_mean():
    """新平台上一根量坏:实例一个不差,新平台平均量跳过这根,其余字段不变。"""
    bars = base_bars()
    bars["vols"][28] = float("nan")
    got, ref = detect(bars), detect(base_bars())
    assert [key(ev) for ev in got] == [key(ev) for ev in ref]
    for a, b in zip(got, ref):
        if a.new.start_idx <= 28 <= a.new.end_idx:
            assert a.new.vol_mean == pytest.approx(2000.0)
        assert_fields(a, ref_fields(bars, *key(a))["plateau"])
        assert (a.days, a.keep_ratio, a.calm_ratio) == (b.days, b.keep_ratio, b.calm_ratio)


def test_bad_price_on_new_platform_truncates_family():
    bars = base_bars()
    bars["closes"][28] = 0.0
    evs = detect(bars)
    clean = [ev for ev in detect(base_bars()) if ev.today.start_idx < 28]
    assert evs == clean
    for ev in evs:
        assert not any(isinstance(v, float) and np.isnan(v) for v in vars(ev).values())


def test_bad_bar_ends_the_rise():
    """三根阳线里第 21 根量坏:阶跃在 20 完成(并入要求量好);第 21 根开盘价坏:20 之后第一根价格坏,
    这一次阶跃不产。"""
    bad_vol = three_step_bars()
    bad_vol["vols"][21] = float("nan")
    assert {(ev.step.start_idx, ev.step.end_idx) for ev in detect(bad_vol)} == {(20, 20)}
    bad_price = three_step_bars()
    bad_price["opens"][21] = 0.0
    assert detect(bad_price) == []


def test_bad_price_on_first_day_after_step_skips_it():
    bars = three_step_bars()
    bars["opens"][23] = 0.0
    assert detect(bars) == []


def test_constructor_rejects_degenerate_windows():
    for name, bad in (("old_window", 0), ("max_step_bars", 0), ("overhead_window", 0),
                      ("calm_window", 0), ("max_pause", -1), ("dump_window", -1)):
        with pytest.raises(ValueError):
            PlateauDetector(**{**KW, name: bad})


# ── 读窗口口径(小 L、各根 |r| 不等,字面数断言) ──

def small_l_bars():
    """L = 3。旧平台 [1,3] 收盘 10.1 / 10.05 / 10.35,|r| 三根各不相同,中位数 = ln(10.1/10.0)。
    4、5 两根阳线 11.0、11.6,最高价逐根抬高 → 阶跃 [4, 5](4 之前的第 3 根够不着 L+1,不往前找)。
    阶跃第一根量 9000 大于末根 4000。6..10 是新平台(6 最高价回落)。"""
    closes = [10.0, 10.1, 10.05, 10.35, 11.0, 11.6, 11.5, 11.7, 11.55, 11.65, 11.6]
    vols = [1000.0] * 4 + [9000.0, 4000.0] + [2000.0] * 5
    return dict(closes=closes, opens=list(closes), highs=[x + 0.1 for x in closes], vols=vols)


def test_small_window_literals():
    ln = math.log
    bars = small_l_bars()
    sigma_s = ln(10.1 / 10.0)
    r4 = ln(11.0 / 10.35)
    evs = detect(bars, old_window=3)
    by_key = {key(ev): ev for ev in evs}
    assert set(by_key) == {(4, 5, t) for t in range(7, 11)}

    b8 = by_key[(4, 5, 8)]                                     # 新平台 [6,7]
    assert (b8.old.start_idx, b8.old.end_idx) == (1, 3)
    assert b8.old.level == pytest.approx(10.1)
    assert b8.old.sigma == pytest.approx(sigma_s)
    assert b8.old.range == pytest.approx(ln(10.35 / 10.05))
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
    assert_all_fields(bars, evs, lw=3)


def test_close_equal_to_old_level_keeps_family_with_zero_keep():
    bars = base_bars()
    bars["closes"][30] = 10.05            # 恰好等于旧平台价位(收盘中位数 10.05)
    evs = {ev.today.start_idx: ev for ev in detect(bars) if ev.step.start_idx == 20}
    assert evs[30].keep_ratio == pytest.approx(0.0, abs=1e-12)
    assert evs[31].keep_ratio > 0
    assert max(evs) == 41


# ── 旧平台波动为 0 时兜底、前高压力、创新低、最近一段振幅 ──

def tick_stuck_bars(bumps=(6, 12)):
    """旧平台收盘卡在 10.0,只在 bumps 那几根冒到 10.5 再回来:回看窗 [5, 19] 里 |r| 过半为 0,
    中位数 0、平均数 > 0。最高价一律 10.6。20、21 两根大阳线 12.0、14.0(最高 12.1、14.5);
    22..34 新平台 13.9 / 14.0 交替(最高 14.1)。"""
    closes = [10.5 if j in bumps else 10.0 for j in range(20)] + [12.0, 14.0]
    closes += [13.9 if j % 2 == 0 else 14.0 for j in range(22, 35)]
    opens = list(closes)
    for j in range(22, 35):
        opens[j] = 13.95
    highs = [10.6] * 20 + [12.1, 14.5] + [14.1] * 13
    vols = [1000.0] * 20 + [5000.0, 8000.0] + [2000.0] * 13
    return dict(closes=closes, opens=opens, highs=highs, vols=vols)


def test_zero_median_sigma_falls_back_to_mean():
    bars = tick_stuck_bars()
    absr = [abs(math.log(bars["closes"][j] / bars["closes"][j - 1])) for j in range(5, 20)]
    assert statistics.median(absr) == 0 < sum(absr) / len(absr)
    evs = detect(bars)
    assert {(ev.step.start_idx, ev.step.end_idx) for ev in evs} == {(20, 21)}
    assert evs[0].old.sigma == pytest.approx(sum(absr) / len(absr), rel=1e-12)
    assert_all_fields(bars, evs)


def test_all_zero_old_platform_does_not_open_or_walk_back_into_it():
    """回看窗 [5, 19] 收盘一根都没动:第 20 根不开段;第 21 根开段(回看窗含 20 那一跳),
    往前找时 20 虽然最高价抬高,但以 20 为起点的旧平台波动为 0,不往前找,起点停在 21。"""
    evs = detect(tick_stuck_bars(bumps=()))
    assert {ev.step.start_idx for ev in evs} == {21}
    assert all(ev.old.sigma > 0 for ev in evs)


def overhead_bars():
    """0..39 旧平台 10.0 / 10.05 交替、最高价 10.2,第 15 根上影线冲到 30(收盘不变);40、41 阶跃
    12.0、14.0(最高 12.1、14.5);42..85 新平台 13.9 / 14.0 交替(最高 14.1)。"""
    closes = old_closes(40) + [12.0, 14.0]
    closes += [13.9 if j % 2 == 0 else 14.0 for j in range(42, 86)]
    opens = list(closes)
    for j in range(42, 86):
        opens[j] = 13.95
    highs = [10.2] * 40 + [12.1, 14.5] + [14.1] * 44
    highs[15] = 30.0
    vols = [1000.0] * 40 + [5000.0, 8000.0] + [2000.0] * 44
    return dict(closes=closes, opens=opens, highs=highs, vols=vols)


def test_overhead_sees_prior_high_until_it_leaves_the_window():
    """前高在第 15 根:当天 t 往前 60 根还够得着它时 overhead > 1,t ≥ 76 窗口起点越过 15 后 < 1。"""
    bars = overhead_bars()
    by_t = {ev.today.start_idx: ev for ev in detect(bars) if ev.step.start_idx == 40}
    assert set(by_t) == set(range(43, 82))              # t ≤ e + max_days = 81
    for t, ev in by_t.items():
        assert_fields(ev, ref_fields(bars, 40, 41, t)["plateau"])
        if t - OVERHEAD_W <= 15:
            assert ev.overhead == pytest.approx(30.0 / bars["closes"][t])
        else:
            assert ev.overhead < 1
    assert by_t[75].overhead > 1 and by_t[76].overhead < 1


def test_low_age_counts_strict_new_lows_only():
    """新平台第一天不算创新低;收盘等于之前最低不算;严格更低才算,之后逐日累加。"""
    bars = base_bars()
    bars["closes"][27] = 13.9               # 本来就是 13.9:等于新平台最低,不算
    bars["closes"][29] = 13.8               # 严格新低
    by_t = {ev.today.start_idx: ev for ev in detect(bars)}
    assert all(by_t[t].low_age is None for t in range(23, 29))
    assert by_t[29].low_age == 0
    assert [by_t[t].low_age for t in range(30, 35)] == [1, 2, 3, 4, 5]
    assert by_t[35].low_age == 0            # 跌回 10.0,又一次严格新低


def test_calm_ratio_reads_only_recent_window():
    """新平台头几天晃一下(23 冲到 15.5):累计振幅一直带着它,最近 calm_window 根移过去之后就看不到了。"""
    bars = base_bars()
    bars["closes"][23] = 15.5
    by_t = {ev.today.start_idx: ev for ev in detect(bars)}
    wobble = math.log(15.5 / 13.9)
    quiet = math.log(14.0 / 13.9)
    for t in range(24, 35):
        ev = by_t[t]
        assert ev.new.range == pytest.approx(wobble)
        want = wobble if t - CALM_W <= 23 else quiet
        assert ev.new.recent_range == pytest.approx(want)
        assert ev.calm_ratio == pytest.approx(want / ev.height)
