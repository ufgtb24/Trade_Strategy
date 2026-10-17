"""要素库:每行事实声明的可判定值与通用条件类型(合成 QMMM 上 F05/F06/F08/F10/F12/F14 等的金标、
未来扰动下全部值与条件类型一字不差)、定义的校验(写错当场拒绝)、身份看定义不看字面(同义换写拒绝、
规范化后相同的算同一条、系统默认值不算身份)、别名、在用要素身份不变、待写代码写成计算时查重、
显式合并(别名并过去、旧编号照常解析)、要素文件进水位、查询命令;事实行登记(出处、查重提示)。"""
import json

import pandas as pd
import pytest

from chart_workflow import elements as E
from chart_workflow import facts, oplog, shapes
from chart_workflow.facts import compute_facts
from tests.chart_workflow.conftest import make_stock
from tests.chart_workflow.test_facts import _perturbed, qmmm_synthetic
from tests.chart_workflow.test_shapes import DET, _batch, _ann, _decision, el_op


def D(row, value, cond, variant=None, user=None, default=None):
    """一个定义(没经过规范化)。"""
    return {"row": row, "value": value, "cond": cond, "variant": variant,
            "user_params": dict(user or {}), "default_params": dict(default or {})}


PK1 = D("F01", "n_cleared", "at_least", user={"x": 1})                    # 按收盘至少越过一个峰
PK2 = D("F01", "n_cleared", "at_least", user={"x": 2})
BURST2 = D("F03", "chain", "at_least", "close", user={"x": 2})            # 按收盘连续越过两个峰
DIST20 = D("F13", "events", "events_any", user={"bars": 20})              # 最近 20 根里有派发
VOL = D("F07", "vr", "at_least", default={"x": 3.0})                      # 放量倍数用系统默认(待验证)


def _norm(d):
    out, errs = E.normalize_definition(d)
    assert errs == [], errs
    return out


def _verdict(d, f):
    return E.evaluate(_norm(d), f)[0]


def _qmmm():
    return compute_facts(qmmm_synthetic(), "2025-07-14", "2025-02-28")


# ── 声明 ───────────────────────────────────────────────────────────────────

def test_every_fact_row_declares_values(monkeypatch):
    assert E.check_values() == []
    assert set(E.VALUES) == set(facts.ROWS)
    kinds = {s["kind"] for vals in E.VALUES.values() for s in vals.values()}
    assert kinds == set(E.KIND_TEXT)
    assert {k for c in E.CONDS.values() for k in c["kinds"]} == set(E.KIND_TEXT)
    monkeypatch.setitem(E.VALUES, "F06", {"dry": {**E.VALUES["F06"]["dry"], "path": "{variant}.dry"}})
    monkeypatch.delitem(E.VALUES, "F11")
    errs = E.check_values()
    assert "F11: 没有声明可判定的值" in errs and any("F06.dry" in e for e in errs)


# ── 判定:合成 QMMM 金标 ─────────────────────────────────────────────────────

def test_qmmm_golden_original_three():
    """按收盘至少越过一个峰 是;按收盘连续越过两个峰 是;最近 20 根里有派发 否(5/28 那根离买点 33 根)。"""
    f = _qmmm()
    assert _verdict(PK1, f) == "yes"
    assert _verdict(BURST2, f) == "yes"
    assert _verdict(DIST20, f) == "no"
    assert _verdict(D("F13", "events", "events_any", user={"bars": 33}), f) == "no"
    assert _verdict(D("F13", "events", "events_any", user={"bars": 34}), f) == "yes"
    assert _verdict(D("F02", "n_cleared", "at_least", user={"x": 2}), f) == "no"
    assert _verdict(D("F03", "chain", "at_least", "close", user={"x": 3}), f) == "no"
    assert _verdict(D("F03", "chain", "at_least", "high", user={"x": 2}), f) == "no"
    assert _verdict(VOL, f) == "no"                                      # 当天量比 0.6
    assert E.evaluate(_norm(BURST2), f) == ("yes", "F03 按收盘最长一串连续越过的峰数 2")
    assert E.evaluate(_norm(DIST20), f) == ("no", "F13 最近 20 根里有 0 个派发；窗口里共 1 个")


def test_qmmm_f05_volume_runs():
    """放量段:6/20–7/3 那段的最后一根离买点 7 根,5/28 那段 33 根。「买点前最近 N 根里有放量段」。"""
    f = _qmmm()
    assert _verdict(D("F05", "runs", "events_any", user={"bars": 10}), f) == "yes"
    assert _verdict(D("F05", "runs", "events_any", user={"bars": 7}), f) == "no"     # 7 根以前:不在最近 7 根里
    assert _verdict(D("F05", "runs", "events_any", user={"bars": 8}), f) == "yes"
    assert _verdict(D("F05", "runs", "events_none", user={"bars": 5}), f) == "yes"
    assert _verdict(D("F05", "runs", "events_none", user={"bars": 10}), f) == "no"    # 有 1 段就不是「没有」
    assert _verdict(D("F13", "events", "events_none"), f) == "no"
    assert _verdict(D("F05", "runs", "events_at_least", user={"k": 2}), f) == "yes"
    assert _verdict(D("F05", "runs", "events_at_least", user={"k": 2, "bars": 30}), f) == "no"
    assert E.evaluate(_norm(D("F05", "runs", "events_any", user={"bars": 10})), f) == \
        ("yes", "F05 最近 10 根里有 1 个放量段（2025-06-20）；窗口里共 2 个")


def test_qmmm_f06_dry_before_buy():
    """买前缩量:7/10、7/11、7/14 量比都 < 1;这三天均量是最近一段放量段的 0.13。"""
    f = _qmmm()
    assert E.evaluate(_norm(D("F06", "dry", "is_true")), f) == \
        ("yes", "F06 买点前几天（含当天）量比都低于 1：是")
    assert _verdict(D("F06", "dry", "is_false"), f) == "no"
    assert _verdict(D("F06", "vs_latest_run", "at_most", user={"x": 0.5}), f) == "yes"
    assert _verdict(D("F06", "vs_latest_run", "at_least", user={"x": 0.2}), f) == "no"


def test_qmmm_f08_pre_state_numbers():
    """涨前状态:60 日涨幅 +51.3%、40 日振幅 33.1%、已在涨;离 250 日最高回看不够长(null)→ 无法判定。"""
    f = _qmmm()
    assert E.evaluate(_norm(D("F08", "r60", "at_least", user={"x": 0.3})), f) == ("yes", "F08 60 日涨幅 +51.3%")
    assert _verdict(D("F08", "r60", "at_least", user={"x": 0.6}), f) == "no"
    assert _verdict(D("F08", "width40", "between", user={"lo": 0.2, "hi": 0.4}), f) == "yes"
    assert _verdict(D("F08", "pre_state", "is_one_of", user={"values": ["已在涨"]}), f) == "yes"
    assert _verdict(D("F08", "pre_state", "is_one_of", user={"values": ["横盘", "深跌"]}), f) == "no"
    assert E.evaluate(_norm(D("F08", "dd250", "at_most", user={"x": -0.2})), f) == \
        ("unknown", "F08 的收盘离 250 日最高的幅度算不出（回看不够长）")


def test_qmmm_f10_gap():
    """当天跳空:开盘比前一天收盘低 1.22%,不够 2 倍 M → 不算跳空;低开。"""
    f = _qmmm()
    assert E.evaluate(_norm(D("F10", "gap_m_flag", "is_true")), f) == ("no", "F10 开盘跳空够 gap_m 倍 M：否")
    assert _verdict(D("F10", "gap_m_flag", "is_false"), f) == "yes"
    assert _verdict(D("F10", "gap", "at_most", user={"x": 0.0}), f) == "yes"
    assert _verdict(D("F10", "gap", "at_least", user={"x": 0.02}), f) == "no"


def test_qmmm_f12_path_before_buy():
    """买点前一段(最后 20 根):涨 43.45%、收阳 70%、最大回撤 6.29%、R² 0.94。"""
    f = _qmmm()
    assert _verdict(D("F12", "rise", "at_least", user={"x": 0.3}), f) == "yes"
    assert _verdict(D("F12", "r2", "at_least", user={"x": 0.9}), f) == "yes"
    assert _verdict(D("F12", "max_dd", "between", user={"lo": 0.05, "hi": 0.1}), f) == "yes"
    assert E.evaluate(_norm(D("F12", "up_ratio", "at_least", user={"x": 0.8})), f) == \
        ("no", "F12 买点前一段的收阳比例 70%")


def test_qmmm_f14_throwback_and_other_rows():
    """QMMM 窗口里没有回踩企稳段:最近 20 根里有 → 否,没有 → 是。其余行各判一条。"""
    f = _qmmm()
    assert E.evaluate(_norm(D("F14", "segments", "events_any", user={"bars": 20})), f) == \
        ("no", "F14 最近 20 根里有 0 个回踩企稳段；窗口里共 0 个")
    assert _verdict(D("F14", "segments", "events_none"), f) == "yes"
    assert _verdict(D("F09", "up_segments", "events_any", user={"bars": 1}), f) == "yes"      # 当下在上涨段
    assert _verdict(D("F09", "down_segments", "events_any", user={"bars": 10}), f) == "no"   # 6/30 结束,离 10 根
    assert _verdict(D("F09", "down_segments", "events_any", user={"bars": 11}), f) == "yes"
    assert _verdict(D("F15", "events", "events_any", "close", user={"bars": 1}), f) == "yes"
    assert _verdict(D("F04", "bars", "at_least", "high", user={"x": 30}), f) == "yes"         # 33 根
    assert _verdict(D("F04", "bars", "at_most", "close", user={"x": 60}), f) == "no"          # 88 根
    assert _verdict(D("F01", "n_peaks", "at_least", user={"x": 2}), f) == "yes"
    assert _verdict(D("F11", "segments", "events_none"), f) == "yes"


def test_burst_chain_counts_longest_run():
    """最长一串连续突破:相邻两次首次越过相隔 ≤ 间隔才算连着,断开就重新数。"""
    class Ctx:
        p = {"burst_gap_bars": 5}
        c = [0.0] * 50
    peaks = [{"fc": i, "cleared": True} for i in (10, 12, 30, 33, 36)] + [{"fc": None, "cleared": False}]
    fcs, burst, pair, chain = facts._burst(Ctx, peaks)
    assert fcs == [10, 12, 30, 33, 36] and burst and chain == 3
    assert facts._burst(Ctx, [{"fc": 7, "cleared": True}])[3] == 1
    assert facts._burst(Ctx, [])[3] == 0


def test_f14_throwback_with_segment():
    """有回踩企稳段的图:6/16 买点,3/11–3/17 那段最后一根离买点 65 根。"""
    f = compute_facts(make_stock(seed=5, sigma=0.05, end="2025-12-31"), "2025-06-16", None)
    assert _verdict(D("F14", "segments", "events_any", user={"bars": 66}), f) == "yes"
    assert _verdict(D("F14", "segments", "events_any", user={"bars": 65}), f) == "no"
    assert _verdict(D("F14", "segments", "events_any"), f) == "yes"


def test_event_lists_are_complete_not_display_truncated():
    """描述只列几段,可判定的事件列表是窗口里的全部:走势区段 18 段(描述只列 6 段)、
    放量段 5 段(描述只列最大的 3 段,最近那段最小也在列表里)。"""
    f = compute_facts(make_stock(seed=13, sigma=0.05, end="2025-12-31"), "2025-10-15", "2024-03-01")
    r = {x["fid"]: x for x in f["rows"]}
    segs = r["F09"]["value"]["segments"]
    assert len(segs) == 18 and r["F09"]["text"].startswith("（窗口里共 18 段，只列最近 6 段）")
    n_up = sum(s["regime"] == "up" for s in segs)
    assert n_up > sum(s["regime"] == "up" for s in segs[-6:])
    assert _verdict(D("F09", "up_segments", "events_at_least", user={"k": n_up}), f) == "yes"
    assert _verdict(D("F09", "up_segments", "events_at_least", user={"k": n_up + 1}), f) == "no"
    df = make_stock(seed=1, end="2025-12-31")
    for day, mult in (("2025-04-01", 9.0), ("2025-05-01", 8.0), ("2025-06-02", 7.0),
                      ("2025-07-01", 6.0), ("2025-09-25", 3.5)):
        df.loc[pd.Timestamp(day), "volume"] *= mult
    f = compute_facts(df, "2025-09-30", "2025-03-03")
    v = next(x for x in f["rows"] if x["fid"] == "F05")["value"]
    assert len(v["runs"]) == 3 and "2025-09-25" not in [x["start"] for x in v["runs"]]
    assert [x["bars_before"] for x in v["all_runs"]] == [130, 108, 86, 65, 3]
    assert _verdict(D("F05", "runs", "events_any", user={"bars": 5}), f) == "yes"
    assert _verdict(D("F05", "runs", "events_at_least", user={"k": 5}), f) == "yes"


@pytest.mark.parametrize("make,buy,box", [
    (qmmm_synthetic, "2025-07-14", "2025-02-28"),                                     # 放量段、派发、回踩收回
    (lambda: make_stock(seed=1, sigma=0.005, end="2025-12-31"), "2025-09-30", "2025-03-03"),   # 平台段
    (lambda: make_stock(seed=5, sigma=0.05, end="2025-12-31"), "2025-06-16", None),           # 回踩企稳段
])
def test_bars_before_on_every_event_list(make, buy, box):
    """每个声明了离买点根数的事件列表,事件里都有 bars_before,且 = 买点 − 事件最后一根(0 = 买点当天)。"""
    df = make()
    r = {x["fid"]: x["value"] for x in compute_facts(df, buy, box)["rows"]}
    days = [d.strftime("%Y-%m-%d") for d in df.index]
    ib = days.index(buy)
    last = {"F05": "end", "F09": "end", "F11": "end", "F13": "date", "F14": "end", "F15": "low_date"}
    n = 0
    for fid, vals in E.VALUES.items():
        for name, s in vals.items():
            if s["kind"] != "events":
                continue
            for var in s.get("variants") or (None,):
                found, items = E._walk(r[fid], s["path"], var)
                assert found and isinstance(items, list)
                for e in items:
                    assert e["bars_before"] == ib - days.index(e[last[fid]]), (fid, e)
                    n += 1
    assert n > 0


def test_f11_platform_segments():
    """平台段:最后两段的最后一根离买点 20 根、0 根(买点当天还在平台里)。"""
    f = compute_facts(make_stock(seed=1, sigma=0.005, end="2025-12-31"), "2025-09-30", "2025-03-03")
    assert _verdict(D("F11", "segments", "events_at_least", user={"k": 2, "bars": 21}), f) == "yes"
    assert _verdict(D("F11", "segments", "events_at_least", user={"k": 2, "bars": 20}), f) == "no"
    assert _verdict(D("F11", "segments", "events_any", user={"bars": 1}), f) == "yes"


def test_unknown_and_no_when_value_missing():
    f = _qmmm()
    no_f13 = {**f, "rows": [r for r in f["rows"] if r["fid"] != "F13"]}
    assert E.evaluate(_norm(DIST20), no_f13) == ("unknown", "事实表里没有 F13")

    def edit(fid, fn):
        g = json.loads(json.dumps(f))
        fn(next(r for r in g["rows"] if r["fid"] == fid)["value"])
        return g

    old = edit("F05", lambda v: v.pop("all_runs"))                       # 旧快照:没有全部放量段
    assert E.evaluate(_norm(D("F05", "runs", "events_any")), old) == \
        ("unknown", "F05 里没有放量段（旧快照），重算事实表")
    old = edit("F13", lambda v: [e.pop("bars_before") for e in v["events"]])
    assert E.evaluate(_norm(DIST20), old)[0] == "unknown"                 # 要看最近 N 根,没有根数
    assert _verdict(D("F13", "events", "events_any"), old) == "yes"       # 整个窗口不用根数
    assert _verdict(VOL, edit("F07", lambda v: v.update(vr=None))) == "unknown"
    assert E.evaluate(_norm(D("F04", "bars", "at_least", "close", user={"x": 20})),
                      edit("F04", lambda v: v.update(close=None))) == ("no", "F04 没有越过的峰")
    assert E.evaluate(_norm(D("F06", "vs_latest_run", "at_most", user={"x": 0.5})),
                      edit("F06", lambda v: v.update(vs_latest_run=None))) == ("no", "F06 窗口里没有放量段可比")
    assert E.evaluate(_norm(D("F10", "gap_m_flag", "is_false")), edit("F10", lambda v: v.update(M=None))) == \
        ("unknown", "F10 的开盘跳空够 gap_m 倍 M算不出（它要用的 M 回看不够长）")
    assert _verdict(D("F06", "dry", "is_false"), edit("F06", lambda v: v["days"][0].update(vr=None))) == "unknown"
    assert _verdict(D("F07", "vr", "at_least", user={"x": 1}), edit("F07", lambda v: v.update(vr="0.6"))) == "unknown"
    assert _verdict(D("F08", "pre_state", "is_one_of", user={"values": ["横盘"]}),
                    edit("F08", lambda v: v.update(pre_state="大涨"))) == "unknown"


# ── 未来扰动:全部值、全部条件类型 ─────────────────────────────────────────────

ALL_DEFS = [
    PK1, D("F01", "n_peaks", "at_most", user={"x": 1}), D("F02", "n_cleared", "between", user={"lo": 1, "hi": 1}),
    D("F02", "n_peaks", "at_least", user={"x": 2}), BURST2, D("F03", "chain", "at_most", "high", user={"x": 1}),
    D("F04", "bars", "at_least", "close", user={"x": 30}), D("F04", "bars", "between", "high", user={"lo": 5, "hi": 60}),
    D("F05", "runs", "events_any", user={"bars": 10}), D("F05", "runs", "events_none"),
    D("F05", "runs", "events_at_least", user={"k": 2}),
    D("F06", "dry", "is_true"), D("F06", "vs_latest_run", "at_most", default={"x": 0.5}),
    VOL, D("F07", "vr", "between", user={"lo": 0.5, "hi": 1.5}),
    D("F08", "pre_state", "is_one_of", user={"values": ["横盘", "已在涨"]}),
    D("F08", "dd250", "at_most", user={"x": -0.3}), D("F08", "r60", "at_least", user={"x": 0.1}),
    D("F08", "width40", "at_most", user={"x": 0.3}), D("F08", "M", "at_least", user={"x": 0.03}),
    D("F09", "up_segments", "events_any", user={"bars": 1}), D("F09", "down_segments", "events_at_least", user={"k": 2}),
    D("F09", "sideways_segments", "events_none", user={"bars": 30}),
    D("F10", "gap", "at_least", user={"x": 0.01}), D("F10", "gap_m_flag", "is_false"),
    D("F11", "segments", "events_any"),
    D("F12", "rise", "at_least", user={"x": 0.1}), D("F12", "up_ratio", "between", user={"lo": 0.4, "hi": 0.8}),
    D("F12", "max_dd", "at_most", user={"x": 0.1}), D("F12", "r2", "at_least", user={"x": 0.5}),
    DIST20, D("F13", "events", "events_at_least", user={"k": 2, "bars": 60}),
    D("F14", "segments", "events_any", user={"bars": 70}), D("F14", "segments", "events_none", user={"bars": 5}),
    D("F15", "events", "events_any", "close", user={"bars": 5}), D("F15", "events", "events_none", "high"),
]


def test_every_value_and_condition_type_is_covered():
    assert {d["cond"] for d in ALL_DEFS} == set(E.CONDS)
    assert {(d["row"], d["value"]) for d in ALL_DEFS} == \
        {(fid, name) for fid, vals in E.VALUES.items() for name in vals}
    for d in ALL_DEFS:
        _norm(d)


def _verdicts(f):
    return [E.evaluate(_norm(d), f) for d in ALL_DEFS]


@pytest.mark.parametrize("seed,buy,box", [(5, "2025-06-16", None), (7, "2025-03-03", "2024-12-02"),
                                          (11, "2025-09-30", "2025-07-01"), (5, "2025-03-11", None),
                                          (13, "2025-10-15", "2024-03-01"), (1, "2025-09-30", "2025-03-03")])
def test_future_perturbation_changes_no_verdict(seed, buy, box):
    df = make_stock(seed=seed, sigma=0.005 if seed == 1 else 0.05, end="2025-12-31")
    a = compute_facts(df, buy, box)
    for s in (1, 2):
        assert _verdicts(a) == _verdicts(compute_facts(_perturbed(df, buy, s), buy, box))


def test_future_perturbation_qmmm():
    """QMMM 上放量段、派发、回踩收回都有事件,判定里最近 N 根的根数都用上。"""
    df = pd.concat([qmmm_synthetic(), make_stock(start="2025-07-15", end="2025-12-31", price=1.8)])
    seen = set()
    for buy in ("2025-06-23", "2025-07-08", "2025-07-14"):
        a = compute_facts(df, buy, "2025-02-28")
        b = compute_facts(_perturbed(df, buy, 3), buy, "2025-02-28")
        va = _verdicts(a)
        assert va == _verdicts(b)
        seen |= {v for v, _ in va}
    assert seen == {"yes", "no", "unknown"}


# ── 定义的校验:写错当场拒绝 ─────────────────────────────────────────────────

def test_normalize_canonical_form():
    assert _norm(VOL) == {"row": "F07", "value": "vr", "cond": "at_least", "variant": None,
                          "user_params": {}, "default_params": {"x": 3.0}}
    assert _norm(D("F01", "n_cleared", "at_least", user={"x": 2.0}))["user_params"] == {"x": 2}
    assert _norm(D("F07", "vr", "at_least", user={"x": 3}))["user_params"] == {"x": 3.0}
    assert _norm(D("F08", "pre_state", "is_one_of", user={"values": ["横盘", "深跌"]}))["user_params"] == \
        {"values": ["深跌", "横盘"]}
    assert E.definition_text(_norm(BURST2)) == "按收盘最长一串连续越过的峰数至少 2"
    assert E.definition_text(_norm(DIST20)) == "最近 20 根里有派发"
    assert E.definition_text(_norm(D("F13", "events", "events_none"))) == "窗口里没有派发"
    assert E.definition_text(_norm(D("F05", "runs", "events_at_least", user={"k": 2}, default={"bars": 60}))) == \
        "最近 60 根里至少有 2 个放量段"
    assert E.definition_text(_norm(D("F08", "dd250", "at_most", user={"x": -0.3}))) == "收盘离 250 日最高的幅度至多 -30%"
    assert E.definition_text(_norm(D("F08", "pre_state", "is_one_of", user={"values": ["横盘", "其他"]}))) == \
        "涨前状态是横盘 / 其他 之一"
    assert E.definition_text(_norm(D("F06", "dry", "is_true"))) == "买点前几天（含当天）量比都低于 1：是"
    assert E.params_text(_norm(VOL)) == "系统默认（待验证）：阈值 3 倍"
    assert E.params_text(_norm(D("F06", "dry", "is_true"))) == "没有参数"


@pytest.mark.parametrize("d,needle", [
    (D("F99", "x", "at_least", user={"x": 1}), "row 不认识"),
    (D("F05", "max_vr", "at_least", user={"x": 1}), "F05 没有可判定的值 'max_vr'"),
    (D("F07", "vr", "rises_a_lot"), "cond 不认识"),
    (D("F06", "dry", "at_least", user={"x": 1}), "是是非,不能用 at_least(能用 is_true、is_false)"),
    (D("F05", "runs", "at_least", user={"x": 1}), "是事件列表,不能用 at_least"),
    (D("F07", "vr", "is_true"), "是数,不能用 is_true"),
    (D("F08", "pre_state", "at_least", user={"x": 1}), "是类别,不能用 at_least"),
    (D("F07", "vr", "events_any"), "不能用 events_any"),
    (D("F03", "chain", "at_least", user={"x": 2}), "口径 variant 只能是 close/high"),
    (D("F03", "chain", "at_least", "open", user={"x": 2}), "口径 variant 只能是"),
    (D("F01", "n_cleared", "at_least", "close", user={"x": 1}), "不分口径,variant 写 null"),
    (D("F07", "vr", "at_least"), "at_least 缺参数 ['x']"),
    (D("F07", "vr", "between", user={"lo": 1}), "缺参数 ['hi']"),
    (D("F05", "runs", "events_at_least"), "缺参数 ['k']"),
    (D("F07", "vr", "at_least", user={"x": 1, "bars": 3}), "at_least 没有参数 ['bars']"),
    (D("F06", "dry", "is_true", user={"x": 1}), "is_true 没有参数 ['x'](有 无)"),
    (D("F07", "vr", "at_least", user={"x": 1}, default={"x": 2}), "只能在 user_params 或 default_params 其中一处"),
    (D("F08", "pre_state", "is_one_of", default={"values": ["横盘"]}), "只能放 user_params"),
    (D("F08", "pre_state", "is_one_of", user={"values": ["大涨"]}), "没有这些类别"),
    (D("F08", "pre_state", "is_one_of", user={"values": []}), "非空的类别列表"),
    (D("F08", "pre_state", "is_one_of", user={"values": ["横盘", "横盘"]}), "类别重复"),
    (D("F08", "pre_state", "is_one_of", user={"values": list(E.PRE_STATES)}), "选了全部类别,恒成立"),
    (D("F01", "n_cleared", "at_least", user={"x": True}), "必须是数"),
    (D("F07", "vr", "at_least", user={"x": "3"}), "必须是数"),
    (D("F01", "n_cleared", "at_least", user={"x": 1.5}), "必须是整数"),
    (D("F05", "runs", "events_any", user={"bars": 0}), "至少是 1"),
    (D("F05", "runs", "events_any", user={"bars": 2.5}), "必须是整数"),
    (D("F01", "n_cleared", "at_least", user={"x": 0}), "恒成立"),
    (D("F01", "n_cleared", "at_least", user={"x": 5}), "至少 5不可能成立(按收盘越过的峰个数在 0 到 4 之间)"),
    (D("F12", "up_ratio", "at_most", user={"x": 1}), "恒成立"),
    (D("F12", "up_ratio", "at_most", user={"x": -0.1}), "至多 -0.1不可能成立"),
    (D("F08", "dd250", "at_least", user={"x": 0.1}), "至少 0.1不可能成立"),
    (D("F07", "vr", "between", user={"lo": 2, "hi": 1}), "下限要小于上限"),
    (D("F07", "vr", "between", user={"lo": 2, "hi": 2}), "下限要小于上限"),
    (D("F01", "n_cleared", "between", user={"lo": 2, "hi": 1}), "个数可以相等"),
    ({**PK1, "reads": ["F01"]}, "未知字段"),
    ({**PK1, "role": "must"}, "未知字段"),
    ("F01", "必须是对象"),
])
def test_normalize_rejects(d, needle):
    out, errs = E.normalize_definition(d)
    assert out is None and any(needle in e for e in errs), errs


def test_count_between_equal_bounds_means_exactly():
    f = _qmmm()
    assert _verdict(D("F01", "n_cleared", "between", user={"lo": 2, "hi": 2}), f) == "yes"
    assert _verdict(D("F02", "n_cleared", "between", user={"lo": 2, "hi": 2}), f) == "no"


def test_within_n_needs_declared_bars_before(monkeypatch):
    spec = {**E.VALUES["F13"]["events"], "events": {"date": "date"}}
    monkeypatch.setitem(E.VALUES, "F13", {"events": spec})
    out, errs = E.normalize_definition(DIST20)
    assert out is None and any("没有离买点根数,不能限定最近 N 根" in e for e in errs)
    assert _norm(D("F13", "events", "events_any"))["user_params"] == {}


# ── 身份:同一个意思只许一种写法 ──────────────────────────────────────────────

@pytest.mark.parametrize("d,needle", [
    (D("F05", "runs", "events_at_least", user={"k": 1}), "至少 1 个就是 events_any"),
    (D("F01", "n_cleared", "between", user={"lo": 0, "hi": 2}), "等于至多 2:写成 at_most"),
    (D("F12", "up_ratio", "between", user={"lo": 0.5, "hi": 1}), "等于至少 0.5:写成 at_least"),
    (D("F03", "chain", "at_least", "close", user={"x": 1}), "写成 F01 的 n_cleared at_least 1"),
    (D("F03", "chain", "at_least", "high", user={"x": 1}), "写成 F02 的 n_cleared at_least 1"),
    (D("F03", "chain", "at_most", "close", user={"x": 0}), "写成 F01 的 n_cleared at_most 0"),
    (D("F04", "bars", "at_least", "close", user={"x": 1}), "只是在问「按收盘至少越过一个峰"),
    (D("F04", "bars", "between", "close", user={"lo": 1, "hi": 30}), "写成 at_most"),
    (D("F06", "vs_latest_run", "at_least", user={"x": 0}), "只是在问「窗口里有放量段"),
    (D("F05", "runs", "events_any", user={"bars": 1}), "写成 F07 的 vr at_least / at_most"),
    (D("F05", "runs", "events_none", default={"bars": 1}), "写成 F07 的 vr"),
    (D("F08", "pre_state", "is_one_of", user={"values": ["深跌"]}), "写成 F08 的 dd250 at_most"),
    (D("F08", "pre_state", "is_one_of", user={"values": ["其他", "已在涨", "横盘"]}), "写成 F08 的 dd250 at_least"),
])
def test_synonym_forms_rejected_with_canonical_hint(d, needle):
    out, errs = E.normalize_definition(d)
    assert out is None and any(needle in e for e in errs), errs


@pytest.mark.parametrize("d,needle", [
    # 「只是在问有没有」:按值实际能取到的范围判,不只在正好碰到边界时才拒
    (D("F04", "bars", "at_most", "close", user={"x": 9999}), "只是在问「按收盘至少越过一个峰"),
    (D("F04", "bars", "at_most", "close", user={"x": 260}), "只是在问「按收盘至少越过一个峰"),
    (D("F06", "vs_latest_run", "at_least", user={"x": 0.000000001}), "只是在问「窗口里有放量段"),
    (D("F06", "vs_latest_run", "at_most", user={"x": 1000000000}), "只是在问「窗口里有放量段"),
    # 量比、涨幅、比值:合理范围外按近乎恒成立 / 近乎不可能拒绝
    (D("F07", "vr", "at_least", user={"x": 0.000000001}), "近乎恒成立"),
    (D("F07", "vr", "at_most", user={"x": 1000}), "近乎恒成立"),
    (D("F08", "M", "at_least", user={"x": 2}), "近乎不可能成立"),
    # 百分比写成整数:提示单位
    (D("F12", "rise", "at_least", user={"x": 30}), "30% 要写成 0.3"),
    (D("F10", "gap", "at_least", user={"x": 8}), "8% 要写成 0.08"),
    (D("F12", "rise", "between", user={"lo": 0.1, "hi": 30}), "30% 要写成 0.3"),
    # 最近 N 根不比看图窗口短
    (D("F05", "runs", "events_any", user={"bars": 261}), "不比看图窗口短"),
])
def test_bounds_reject_trivial_thresholds(d, needle):
    out, errs = E.normalize_definition(d)
    assert out is None and any(needle in e for e in errs), errs


def test_bounds_keep_reasonable_thresholds():
    for d in (D("F04", "bars", "at_most", "close", user={"x": 30}),
              D("F06", "vs_latest_run", "at_most", user={"x": 0.5}),
              D("F07", "vr", "at_least", user={"x": 50}),
              D("F12", "rise", "at_least", user={"x": 0.3}),
              D("F05", "runs", "events_any", user={"bars": 260})):
        out, errs = E.normalize_definition(d)
        assert errs == [] and out is not None, (d, errs)
    out, errs = E.normalize_definition(D("F07", "vr", "at_least", user={"x": 0.01}))
    assert "买点当天量比的合理范围是 0.05 到 100,待验证" in errs[0] and "%" not in errs[0]   # 倍数不提示百分比


def _charts():
    df = pd.concat([qmmm_synthetic(), make_stock(start="2025-07-15", end="2025-12-31", price=1.8)])
    out = [compute_facts(df, b, "2025-02-28") for b in ("2025-05-28", "2025-06-23", "2025-07-01", "2025-07-14")]
    out += [compute_facts(make_stock(seed=s, sigma=0.05, end="2025-12-31"), b, x)
            for s, b, x in ((5, "2025-06-16", None), (7, "2025-03-03", "2024-12-02"),
                            (11, "2025-09-30", "2025-07-01"), (13, "2025-10-15", "2024-03-01"))]
    return out


def test_rejected_synonyms_really_mean_the_same():
    """被拒的写法与它指过去的规范写法,在一批图上判定一致(拒得有理);不经规范化直接判。"""
    pairs = [
        (D("F03", "chain", "at_least", "close", user={"x": 1}), PK1),
        (D("F03", "chain", "at_least", "high", user={"x": 1}), D("F02", "n_cleared", "at_least", user={"x": 1})),
        (D("F03", "chain", "at_most", "close", user={"x": 0}), D("F01", "n_cleared", "at_most", user={"x": 0})),
        (D("F04", "bars", "at_least", "close", user={"x": 1}), PK1),
        (D("F04", "bars", "at_least", "high", user={"x": 1}), D("F02", "n_cleared", "at_least", user={"x": 1})),
        (D("F06", "vs_latest_run", "at_least", user={"x": 0}), D("F05", "runs", "events_any")),
        (D("F05", "runs", "events_any", user={"bars": 1}),
         D("F07", "vr", "at_least", default={"x": E._facts_cfg()["vol_run_min"]})),
        (D("F05", "runs", "events_at_least", user={"k": 1}), D("F05", "runs", "events_any")),
        (D("F01", "n_cleared", "between", user={"lo": 0, "hi": 1}), D("F01", "n_cleared", "at_most", user={"x": 1})),
    ]
    deep = E._features_cfg()["deep_drop_dd250"]
    pre = [(D("F08", "pre_state", "is_one_of", user={"values": ["深跌"]}), D("F08", "dd250", "at_most", user={"x": deep})),
           (D("F08", "pre_state", "is_one_of", user={"values": ["已在涨", "横盘", "其他"]}),
            D("F08", "dd250", "at_least", user={"x": deep}))]
    verdicts = set()
    for f in _charts():
        for a, b in pairs:
            assert E.evaluate(a, f)[0] == E.evaluate(b, f)[0], (a, b, f["buy_date"])
            verdicts.add(E.evaluate(a, f)[0])
        dd = next(r for r in f["rows"] if r["fid"] == "F08")["value"]["dd250"]
        for a, b in pre:
            if dd is not None:                                             # 回看够长时
                assert E.evaluate(a, f)[0] == E.evaluate(b, f)[0], (a, b, f["buy_date"])
    assert verdicts == {"yes", "no"}


def test_identity_ignores_wording_and_system_defaults():
    assert E.identity(_norm(PK1)) != E.identity(_norm(PK2))                # 至少一个峰 / 两个峰
    assert E.identity(_norm(PK1)) != E.identity(_norm(D("F02", "n_cleared", "at_least", user={"x": 1})))
    assert E.identity(_norm(PK2)) != E.identity(_norm(D("F01", "n_peaks", "at_least", user={"x": 2})))   # 值不同
    assert E.identity(_norm(PK2)) != E.identity(_norm(D("F01", "n_cleared", "at_most", user={"x": 2})))  # 条件不同
    assert E.identity(_norm(BURST2)) != E.identity(_norm({**BURST2, "variant": "high"}))   # 口径不同
    assert E.identity(_norm(D("F01", "n_cleared", "at_least", user={"x": 2.0}))) == E.identity(_norm(PK2))
    assert E.identity(_norm(D("F07", "vr", "at_least", user={"x": 3}))) == \
        E.identity(_norm(D("F07", "vr", "at_least", user={"x": 3.0})))
    assert E.identity(_norm(D("F08", "pre_state", "is_one_of", user={"values": ["横盘", "深跌"]}))) == \
        E.identity(_norm(D("F08", "pre_state", "is_one_of", user={"values": ["深跌", "横盘"]})))
    a = _norm({**VOL, "default_params": {"x": 3.0}})
    b = _norm({**VOL, "default_params": {"x": 4.0}})
    assert E.identity(a) == E.identity(b)                                  # 系统默认值不算身份
    assert E.identity(a) != E.identity(_norm(D("F07", "vr", "at_least", user={"x": 3.0})))
    near = D("F13", "events", "events_any", default={"bars": 20})          # 用户没说多近:窗口 / 默认 20 根同一条
    assert E.identity(_norm(near)) == E.identity(_norm(D("F13", "events", "events_any")))
    assert E.identity(_norm(DIST20)) != E.identity(_norm(D("F13", "events", "events_none", user={"bars": 20})))


# ── 建、别名、修订、合并(经决定文件) ───────────────────────────────────────

def _apply(*ops):
    return shapes.apply(_decision(*ops))


def _els():
    return E.replay(oplog.read_all())


def test_same_definition_refused_and_alias_attached(state_dir):
    _apply(el_op("a", "按收盘至少越过一个峰", PK1), el_op("v", "放量", VOL, user=False))
    with pytest.raises(shapes.ShapeValidationError) as ei:                 # 字面不同、定义相同
        _apply(el_op("b", "收盘站上前面的高点", PK1))
    assert "E001" in str(ei.value) and "alias_element" in str(ei.value)
    with pytest.raises(shapes.ShapeValidationError) as ei:                 # 只差系统默认值
        _apply(el_op("w", "明显放量", {**VOL, "default_params": {"x": 5}}, user=False))
    assert "E002" in str(ei.value)
    with pytest.raises(shapes.ShapeValidationError) as ei:                 # 同一个文件里建两遍也拦
        _apply(el_op("c", "两个峰", PK2), el_op("d", "越过两个峰", PK2))
    assert "E003" in str(ei.value)
    with pytest.raises(shapes.ShapeValidationError) as ei:                 # 换个条件类型写同一个意思:拒绝并指路
        _apply(el_op("e", "连着越过一个峰", D("F03", "chain", "at_least", "close", user={"x": 1})))
    assert "写成 F01 的 n_cleared at_least 1" in str(ei.value)
    _apply({"act": "alias_element", "target": {"element_id": "E001"},
            "value": {"text": "收盘站上前面的高点"}, "actor": "user"})
    el = _els()["E001"]
    assert [a["text"] for a in el["aliases"]] == ["收盘站上前面的高点"] and el["aliases"][0]["op_id"]
    with pytest.raises(shapes.ShapeValidationError, match="已经有这个说法"):
        _apply({"act": "alias_element", "target": {"element_id": "E001"},
                "value": {"text": " 收盘站上前面的高点 "}})
    _apply(el_op("e", "越过两个峰", PK2))                                   # 定义不同:另一条
    assert sorted(_els()) == ["E001", "E002", "E003"]
    assert json.loads((state_dir / "elements" / "E002.json").read_text())["versions"][0][
        "definition"]["default_params"] == {"x": 3.0}


@pytest.mark.parametrize("op,needle", [
    (el_op("x", "", PK1), "value 不能为空"),
    ({**el_op("x", "说法", PK1), "value": {**el_op("x", "说法", PK1)["value"], "said_first_match": ""}},
     "said_first_match"),
    ({**el_op("x", "说法", PK1, user=False),
      "value": {**el_op("x", "说法", PK1, user=False)["value"], "suggested_by": "own_library"}},
     "suggested_by 只能是"),
    (el_op("x", "说法", None), "needs"),
    ({**el_op("x", "说法", PK1), "target": {"element_id": "X1"}}, "element_id 不合法"),
    (el_op("x", "说法", D("F06", "dry", "at_least", user={"x": 1})), "不能用 at_least"),
    (el_op("x", "说法", D("F07", "vr", "at_least")), "缺参数"),
])
def test_create_element_rejects(state_dir, op, needle):
    with pytest.raises(shapes.ShapeValidationError) as ei:
        _apply(op)
    assert needle in str(ei.value)
    assert oplog.read_all() == []


WHO = {"origin": "suggested_adopted", "suggested_by": "session"}       # 写成计算是会话定的


def test_revise_keeps_identity_and_pending_checked_for_duplicates(state_dir):
    _apply(el_op("v", "放量", VOL, user=False), el_op("p", "两个峰", PK2),
           el_op("t", "突破前横着走", None, needs="现有事实没有横走时长"),
           el_op("q", "越过好几个峰", None, needs="要数越过几个峰"))
    _apply({"act": "revise_element", "target": {"element_id": "E001"},
            "value": {"definition": {**VOL, "default_params": {"x": 2.5}}, "change": "默认倍数改 2.5"}})
    el = _els()["E001"]
    assert el["current_version"] == 2 and el["versions"][1]["definition"]["default_params"] == {"x": 2.5}
    assert el["versions"][1]["definition_origin"] == el["versions"][0]["definition_origin"] == DET
    for bad, needle in ((D("F07", "vr", "at_least", user={"x": 2.5}), "定义变了就是另一条要素"),
                        (D("F07", "vr", "between", default={"lo": 2.5, "hi": 9}), "定义变了就是另一条要素"),
                        (D("F07", "vr", "at_least", default={"x": -1}), "恒成立"),
                        (None, "不能改回待写代码")):
        with pytest.raises(shapes.ShapeValidationError, match=needle):
            _apply({"act": "revise_element", "target": {"element_id": "E001"},
                    "value": {"definition": bad, "change": "改"}})
    # 只改系统默认值也不能改成和别的要素同一条(用户说的「量比至少 3」已经有了)
    _apply(el_op("v3", "量比至少 3 倍", D("F07", "vr", "at_least", user={"x": 3})))      # E005
    with pytest.raises(shapes.ShapeValidationError, match="E005.*成了同一条"):
        _apply({"act": "revise_element", "target": {"element_id": "E001"},
                "value": {"definition": {**VOL, "default_params": {"x": 3}}, "change": "改回 3"}})
    # 待写代码的写成计算:和已有的相同 → 拒绝,提示合并;不同 → 变成在用;要带是谁定的
    with pytest.raises(shapes.ShapeValidationError) as ei:
        _apply({"act": "revise_element", "target": {"element_id": "E004"},
                "value": {"definition": PK2, "change": "写成计算", **WHO}})
    assert "E002" in str(ei.value) and "merge_element" in str(ei.value)
    with pytest.raises(shapes.ShapeValidationError, match="写成计算是谁定的.*origin 必填"):
        _apply({"act": "revise_element", "target": {"element_id": "E004"},
                "value": {"definition": D("F01", "n_cleared", "at_least", user={"x": 3}), "change": "写成计算"}})
    _apply({"act": "revise_element", "target": {"element_id": "E004"},
            "value": {"definition": D("F01", "n_cleared", "at_least", user={"x": 3}), "change": "写成计算",
                      **WHO}})
    el = _els()["E004"]
    assert el["status"] == "active" and _els()["E003"]["status"] == "pending_code"
    assert el["versions"][1]["definition_origin"] == WHO and el["versions"][0]["definition_origin"] is None
    assert "定义是谁定的：采纳了会话的推荐（v2）" in E.render(el, oplog.read_all())
    with pytest.raises(shapes.ShapeValidationError, match="change 必填"):
        _apply({"act": "revise_element", "target": {"element_id": "E003"}, "value": {"needs": "还缺"}})


def test_merge_only_same_definitions(state_dir):
    """合并只许发生在定义相同的两条之间:在用的直接比;待写代码的要带写成计算的定义和是谁定的,
    工具核对相同才并;被并的记下写成计算的那一版,名字和别名挂到并入的那条,旧编号照常解析。"""
    _batch(state_dir, "b1", [_ann("a1")])
    _apply(el_op("p", "按收盘至少越过一个峰", PK1),
           el_op("t", "收盘站上前高", None, needs="还没想好怎么算"),
           {"act": "alias_element", "target": {"element_id": "$t"}, "value": {"text": "站上前高"}},
           {"act": "create_shape", "value": {
               "name": {"value": "站上前高", "origin": "user_written"}, "change": "新建", "from_ann": ["a1"],
               "card": {"ingredients": [{"ing_id": "i1", "element": "$t", "role": "must",
                                         "origin": "user_written"}], "triggers": []}}})
    merge = {"act": "merge_element", "target": {"element_id": "E002"}, "actor": "user",
             "value": {"into": "E001", "reason": "用户确认是同一个意思"}}
    with pytest.raises(shapes.ShapeValidationError, match="还是待写代码:合并要带它写成计算的定义"):
        _apply(merge)
    with pytest.raises(shapes.ShapeValidationError, match="不是同一个意思"):
        _apply({**merge, "value": {**merge["value"], "definition": PK2, **WHO}})
    with pytest.raises(shapes.ShapeValidationError, match="origin 必填"):
        _apply({**merge, "value": {**merge["value"], "definition": PK1}})
    _apply({**merge, "value": {**merge["value"], "definition": PK1, **WHO}})
    els = _els()
    assert els["E002"]["status"] == "merged" and els["E002"]["merged_into"] == "E001"
    v2 = els["E002"]["versions"][1]
    assert v2["definition"] == _norm(PK1) and v2["definition_origin"] == WHO and "并入" in v2["change"]
    assert [(a["text"], a.get("from")) for a in els["E001"]["aliases"]] == \
        [("收盘站上前高", "E002"), ("站上前高", "E002")]
    assert els["E002"]["versions"][0]["needs"] and els["E002"]["aliases"]   # 什么都不删
    assert E.resolve(els, "E002") == "E001"
    card = shapes.load_card("s001")                                         # 旧卡照常解析,按卡上记的版本
    assert card["versions"][0]["card"]["ingredients"][0]["element_version"] == 1
    text = shapes.render(card)
    assert "E002「收盘站上前高」（已合并到 E001「按收盘至少越过一个峰」）：卡这一版建立时待写代码" in text
    f = _qmmm()
    assert E.evaluate_element(els, "E002", f)[0] == "yes"                   # 不给版本:按并入的那条判
    assert E.evaluate_element(els, "E002", f, version=1)[0] == "unknown"    # 卡上记的版本:当时待写代码
    with pytest.raises(shapes.ShapeValidationError, match="已合并到 E001"):  # 新版本不能再引用旧编号
        _apply({"act": "revise_shape", "target": {"shape_id": "s001"}, "value": {
            "change": "x", "card": {"ingredients": [{"ing_id": "i1", "element": "E002", "role": "must",
                                                     "origin": "user_written"}], "triggers": []}}})
    for op, needle in (({"act": "merge_element", "target": {"element_id": "E001"}, "value": {"into": "E002"}},
                        "已合并到 E001"),
                       ({"act": "merge_element", "target": {"element_id": "E001"}, "value": {"into": "E001"}},
                        "就是自己"),
                       ({"act": "alias_element", "target": {"element_id": "E002"}, "value": {"text": "x"}},
                        "对 E001 操作")):
        with pytest.raises(shapes.ShapeValidationError, match=needle):
            _apply(op)
    _apply(el_op("two", "两个峰", PK2))                                      # E003:在用,定义不同
    with pytest.raises(shapes.ShapeValidationError, match="只能合并定义相同的两条"):
        _apply({"act": "merge_element", "target": {"element_id": "E003"}, "value": {"into": "E001"}})
    with pytest.raises(shapes.ShapeValidationError, match="在用,合并不用带 definition"):
        _apply({"act": "merge_element", "target": {"element_id": "E003"},
                "value": {"into": "E001", "definition": PK1, **WHO}})
    _apply(el_op("w", "以后再说", None, needs="还没想好"))                   # E004:待写代码
    with pytest.raises(shapes.ShapeValidationError, match="比不了是不是同一个意思"):
        _apply({"act": "merge_element", "target": {"element_id": "E003"}, "value": {"into": "E004"}})
    with pytest.raises(shapes.ShapeValidationError) as ei:                  # 和在用的 E001 相同 → 报 E001
        _apply(el_op("z", "越过一个峰", PK1))
    assert "已有要素 E001" in str(ei.value)


def test_find_same_ignores_merged_definitions():
    """已合并要素的定义不算到并入的那条头上(旧日志里可能有定义不同的合并):照样能建。"""
    els = {"E001": {"element_id": "E001", "status": "active", "merged_into": None, "name": {"value": "两个峰"},
                    "versions": [{"definition": _norm(PK2)}]},
           "E002": {"element_id": "E002", "status": "merged", "merged_into": "E001", "name": {"value": "派发"},
                    "versions": [{"definition": _norm(DIST20)}]}}
    assert E.find_same(els, _norm(DIST20)) is None
    assert E.find_same(els, _norm(PK2)) == "E001"


def test_user_and_default_param_count_as_same(state_dir):
    """同一个参数不论写在用户参数还是系统默认,都按同一条算:不能借换个位置并存。"""
    _apply(el_op("u", "量比至少 3 倍", D("F07", "vr", "at_least", user={"x": 3})))
    with pytest.raises(shapes.ShapeValidationError, match="已有要素 E001"):
        _apply(el_op("d", "放量", D("F07", "vr", "at_least", default={"x": 3}), user=False))
    _apply(el_op("d", "明显放量", D("F07", "vr", "at_least", default={"x": 5}), user=False))     # 值不同:另一条
    with pytest.raises(shapes.ShapeValidationError, match="已有要素 E002"):                      # 系统默认不算身份
        _apply(el_op("d2", "放量了", D("F07", "vr", "at_least", default={"x": 8}), user=False))
    assert E.same_meaning(_norm(D("F05", "runs", "events_at_least", user={"k": 2}, default={"bars": 20})),
                          _norm(D("F05", "runs", "events_at_least", user={"k": 2, "bars": 20})))
    assert not E.same_meaning(_norm(D("F07", "vr", "at_least", user={"x": 3})),
                              _norm(D("F07", "vr", "at_least", user={"x": 4})))


def test_element_files_written_and_in_watermark(state_dir):
    _apply(el_op("p", "按收盘至少越过一个峰", PK1))
    # 写完当场记进水位(先读水位文件,不经任何会重新核对水位的入口)
    wm = json.loads((state_dir / ".watermark.json").read_text())
    assert wm["files"]["elements"] == ["E001.json"]
    p = state_dir / "elements" / "E001.json"
    assert p.read_text() == E.canonical(_els()["E001"])
    p.unlink()
    from chart_workflow.state import StateRootRegressed, state_root
    with pytest.raises(StateRootRegressed):
        state_root()


# ── 查询命令 ───────────────────────────────────────────────────────────────

def test_cli_show_conds_find_eval(state_dir, capsys):
    _batch(state_dir, "b1", [_ann("a1")])
    _apply(el_op("p", "按收盘至少越过一个峰", PK1), el_op("b", "按收盘连续越过两个峰", BURST2),
           el_op("d", "最近 20 根里有派发", DIST20, user=False),
           el_op("t", "突破前横着走", None, needs="现有事实没有横走时长"),
           el_op("r", "买点前 10 根里有放量段", D("F05", "runs", "events_any", user={"bars": 10})),
           {"act": "create_shape", "value": {
               "name": {"value": "二峰", "origin": "user_written"}, "change": "新建", "from_ann": ["a1"],
               "card": {"ingredients": [{"ing_id": "i1", "element": "$b", "role": "must", **DET},
                                        {"ing_id": "i2", "element": "$d", "role": "must_not", **DET}],
                        "triggers": []}}})
    E.main(["show", "E001"])
    out = capsys.readouterr().out
    assert "E001 「按收盘至少越过一个峰」  在用" in out and "读 F01「按收盘越过的峰」的 n_cleared" in out
    assert "你定的：阈值 1" in out and "谁提的：你自己说的" in out
    E.main(["conds"])
    out = capsys.readouterr().out
    assert all(c in out for c in E.CONDS) and all(f"{fid}「" in out for fid in E.VALUES)
    assert "pre_state：涨前状态（类别，取值 深跌 / 已在涨 / 横盘 / 其他）" in out
    E.main(["find", "--row", "F01", "--value", "n_cleared", "--cond", "at_least", "--param", "x=1"])
    assert "已有：E001「按收盘至少越过一个峰」" in capsys.readouterr().out
    E.main(["find", "--row", "F01", "--value", "n_cleared", "--cond", "at_most", "--param", "x=2"])
    out = capsys.readouterr().out
    assert "没有定义相同的要素（按收盘越过的峰个数至多 2）" in out and "相近" in out and "E001" in out
    E.main(["find", "--row", "F08", "--value", "pre_state", "--cond", "is_one_of", "--param", "values=横盘,已在涨"])
    assert "涨前状态是已在涨 / 横盘 之一" in capsys.readouterr().out
    for bad in (["find", "--row", "F01", "--value", "n_cleared", "--cond", "nope"],
                ["find", "--row", "F03", "--value", "chain", "--cond", "at_least", "--variant", "close",
                 "--param", "x=1"]):
        with pytest.raises(SystemExit):
            E.main(bad)
    assert "n_cleared at_least 1" in capsys.readouterr().err
    snap = facts.write_snapshot("b1", [{"ann_id": "a1", "item_id": "QMMM@2025-07-14",
                                        "facts": {**_qmmm(), "symbol": "QMMM"}}])
    rel = snap.relative_to(state_dir).as_posix()
    E.main(["eval", "--facts", rel])
    out = capsys.readouterr().out
    assert "QMMM 买点 2025-07-14（标注 a1）" in out
    assert "E001「按收盘至少越过一个峰」：是" in out and "E002「按收盘连续越过两个峰」：是" in out
    assert "E003「最近 20 根里有派发」：否" in out and "E004" not in out    # 默认只判在用的
    assert "E005「买点前 10 根里有放量段」：是（F05 最近 10 根里有 1 个放量段（2025-06-20）；窗口里共 2 个）" in out
    E.main(["eval", "--facts", str(snap), "--element", "E004"])
    assert "E004「突破前横着走」（待写代码）：无法判定（待写代码（现有事实没有横走时长））" in capsys.readouterr().out
    E.main(["eval", "--facts", rel, "--shape", "s001"])
    out = capsys.readouterr().out
    assert "【必须有】E002「按收盘连续越过两个峰」：是" in out and "【有它就不买】E003「最近 20 根里有派发」：否" in out


# ── 事实行登记 ─────────────────────────────────────────────────────────────

def test_fact_rows_registry_and_sources():
    assert facts.check_rows() == []
    assert all(d["source"] == facts.PRESET for d in facts.ROWS.values())
    bad = {"F99": {"group": "x", "title": "按收盘越过的峰", "reads": ("peaks_close",),
                   "source": {"kind": "user", "date": "2026-10-17"}}}
    errs = facts.check_rows({**facts.ROWS, **bad})
    assert any("said、op_id" in e for e in errs) and any("标题和 F01 重复" in e for e in errs)


def test_check_new_row_hints():
    hints = facts.check_new_row(" 买点当天量倍数 ", ["vol_ratio"])
    assert hints[0] == "同名：F07「买点当天量倍数」"
    assert any(h.startswith("读的量完全相同：F05") for h in hints)
    hints = facts.check_new_row("回踩深度", ["low", "gap_fill"])
    assert any(h.startswith("也读 low：F15") for h in hints)
    assert any("现有行都没读过的量：gap_fill" in h for h in hints)
    assert facts.check_new_row("全新", ["brand_new"]) == [
        f"现有行都没读过的量：brand_new（现有的量：{'、'.join(sorted({x for d in facts.ROWS.values() for x in d['reads']}))}）"]


def test_user_proposed_row_labeled_and_op_checked(state_dir, monkeypatch, capsys):
    src = {"kind": "user", "date": "2026-10-17", "said": "看最近一个月有没有派发", "op_id": "op-1"}
    monkeypatch.setitem(facts.ROWS, "F13", {**facts.ROWS["F13"], "source": src})
    assert facts.source_warnings([]) == ["F13: 出处写的操作日志条目 op-1 不在日志里(或不是 propose_fact)"]
    with pytest.raises(ValueError, match="said"):
        oplog.append([{"act": "propose_fact", "actor": "user", "surface": "chat", "value": {"said": " "}}])
    oplog.append([{"act": "propose_fact", "actor": "user", "surface": "chat", "op_id": "op-1",
                   "value": {"said": "看最近一个月有没有派发"}}])
    assert facts.source_warnings(oplog.read_all()) == []
    oplog.append([{"act": "type", "actor": "user", "surface": "chat", "op_id": "op-2", "value": "随口一句"}])
    monkeypatch.setitem(facts.ROWS, "F05", {**facts.ROWS["F05"], "source": {**src, "op_id": "op-2"}})
    assert facts.source_warnings(oplog.read_all()) == [          # 指到的不是「提出角度」那一条
        "F05: 出处写的操作日志条目 op-2 不在日志里(或不是 propose_fact)"]
    monkeypatch.setitem(facts.ROWS, "F05", {**facts.ROWS["F05"], "source": facts.PRESET})
    facts.main(["--rows"])
    out = capsys.readouterr().out
    assert "F13 派发／近期派发" in out and "你提的角度（2026-10-17，原话「看最近一个月有没有派发」，操作日志 op-1）" in out
    assert "⚠" not in out
    f = _qmmm()
    assert next(r for r in f["rows"] if r["fid"] == "F13")["source"] == src
    assert "⟨你提的角度，2026-10-17⟩" in facts.render({**f, "symbol": "QMMM"})
    ops = oplog.read_all()                                                 # 要素读的是用户提的角度
    assert E.angle({"definition": _norm(DIST20), "op_id": "later"}, ops) == ("user", ["op-1"])
    assert E.angle({"definition": _norm(DIST20), "op_id": "op-1"}, ops) == ("preset", [])   # 不早于这一版
    assert E.angle({"definition": _norm(PK1), "op_id": "later"}, ops) == ("preset", [])
    assert E.angle({"definition": None}, ops) == (None, [])
    facts.main(["--check-row", "近期派发", "--reads", "distribution"])
    assert "同名：F13" in capsys.readouterr().out
