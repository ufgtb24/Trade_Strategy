"""bb_v1 app 结构 + 冒烟测试(V1 throwback 完整备份)。

结构断言:克隆 bottom_burst 骨架,唯一区别 = tb node 用 V1 ThrowbackDetectorV1。
冒烟:真实数据 analyze 不炸(不要求有 match——V1 参数下命中与否不是本 app 的契约)。
"""
import pickle

import pytest

from path2.dag.edges import TemporalEdge
from path2.dag.spec import PatternSpec
from path2.atoms.throwback_v1 import ThrowbackDetectorV1, ThrowbackEventV1
from path2_apps.bb_v1.dag_spec import build_pattern, PATTERN_DAG, eval_meta
from path2_apps.bb_v1.params import Params, load_params


def test_pattern_id_and_topology():
    assert PATTERN_DAG.pattern_id == "bb_v1"
    spec = PATTERN_DAG if isinstance(PATTERN_DAG, PatternSpec) else build_pattern(Params.default())
    nodes = {n.node_id: n for n in spec.nodes}
    assert set(nodes) == {"bo", "burst", "pk", "tb"}
    # pk 孤立显示 node:不参与匹配(solve=False)、无 where
    assert nodes["pk"].solve is False
    assert nodes["pk"].where == ()
    # bo 孤立 node:无边(edges 端点不含 bo)、无 where
    endpoints = {ep for e in spec.edges for ep in (e.src, e.dst)}
    assert "bo" not in endpoints
    assert nodes["bo"].where == ()
    # burst 消费 bo 流;tb 消费 burst 流
    assert nodes["burst"].consumes_stream == "bo"
    assert nodes["tb"].consumes_stream == "burst"
    # 唯一区别:tb node 的 detector 是 V1(与 bottom_burst 的 V2 容器版不同)
    assert isinstance(nodes["tb"].detector, ThrowbackDetectorV1)
    assert nodes["tb"].detector.event_cls is ThrowbackEventV1
    # 单条 TemporalEdge,契约与 bottom_burst 相同
    assert len(spec.edges) == 1
    e = spec.edges[0]
    assert isinstance(e, TemporalEdge)
    assert e.src_selector == "last_bo"
    assert e.dst == "tb"
    assert e.min_gap == 1
    assert e.max_gap == Params.default().tb.max_span
    assert e.anchor_field == "anchor_bo_id"


def test_throwback_kwargs_match_v1_signature():
    """throwback_kwargs 五键一一喂给 V1 detector;max_day_drop_pct 是 where 阈值不在其中。"""
    p = Params.default()
    kw = p.throwback_kwargs()
    assert set(kw) == {"max_rise_k", "stop_confirm_bars", "vol_window", "max_span", "measure"}
    d = ThrowbackDetectorV1(**kw)
    assert d._kw["max_span"] == p.tb.max_span and d._kw["measure"] == "close"


def test_tb_where_day_drop():
    """⑨ 资格型闸:tb node where 只有 day_drop,字段 max_day_drop,op '<',阈值来自 params;None 时无 where。"""
    p = Params.default()
    nodes = {n.node_id: n for n in build_pattern(p).nodes}
    where = dict(nodes["tb"].where)
    assert set(where) == {"day_drop"}
    pred = where["day_drop"]
    assert pred.meta["field"] == "max_day_drop" and pred.meta["op"] == "<"
    assert pred.meta["threshold"] == p.tb.max_day_drop_pct == 0.20
    from dataclasses import replace
    p2 = replace(p, tb=replace(p.tb, max_day_drop_pct=None))
    nodes2 = {n.node_id: n for n in build_pattern(p2).nodes}
    assert nodes2["tb"].where == ()


def test_eval_meta():
    assert eval_meta() == {"end_node": "tb", "head_buffer_trading_days": 63}


def test_analyze_smoke_real_data():
    """真实数据 analyze 不炸(V1 全链路:BO → burst → tb V1)。不要求有 match。"""
    from path2_web.data import slice_window
    from path2_apps.bb_v1.dag_spec import analyze

    df = slice_window(pickle.load(open("datasets/pkls/AA.pkl", "rb")), "2024-09-19", "2026-03-08")
    res = analyze(df, load_params())
    assert res is not None


def test_burst_where_has_peak_age():
    """spec 更新:burst where 新增 peak_age(字段 peak_age_max,阈值来自 params)。"""
    p = Params.default()
    spec = build_pattern(p)
    nodes = {n.node_id: n for n in spec.nodes}
    where = dict(nodes["burst"].where)
    pred = where["peak_age"]
    assert pred.meta["kind"] == "attr"
    assert pred.meta["field"] == "peak_age_max"
    assert pred.meta["op"] == ">="
    assert pred.meta["threshold"] == p.burst.peak_age_min
    assert p.burst.peak_age_min == 125


def test_params_yaml_has_peak_age_min():
    """yaml SSoT:peak_age_min 真实存在于 params.yaml burst 段。"""
    import yaml
    from path2_apps.bb_v1.params import DEFAULT_YAML_PATH
    raw = yaml.safe_load(open(DEFAULT_YAML_PATH))
    assert raw["burst"]["peak_age_min"] == 125
