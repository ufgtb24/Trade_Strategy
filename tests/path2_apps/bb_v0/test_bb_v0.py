"""bb_v0 app 结构 + 冒烟测试(锚 last_bo 的 V1 变体)。

结构断言:克隆 bottom_burst 骨架,唯一区别 = tb node 用 V0 ThrowbackDetectorV0。
冒烟:真实数据 analyze 不炸(不要求有 match——V1 参数下命中与否不是本 app 的契约)。
"""
import pickle

import pytest

from path2.dag.edges import TemporalEdge
from path2.dag.spec import PatternSpec
from path2.atoms.throwback_v0 import ThrowbackDetectorV0, ThrowbackEventV0
from path2_apps.bb_v0.dag_spec import build_pattern, PATTERN_DAG, eval_meta
from path2_apps.bb_v0.params import Params, load_params


def test_pattern_id_and_topology():
    assert PATTERN_DAG.pattern_id == "bb_v0"
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
    assert isinstance(nodes["tb"].detector, ThrowbackDetectorV0)
    assert nodes["tb"].detector.event_cls is ThrowbackEventV0
    # 单条 TemporalEdge,契约与 bottom_burst 相同
    assert len(spec.edges) == 1
    e = spec.edges[0]
    assert isinstance(e, TemporalEdge)
    assert e.src_selector == "last_bo"
    assert e.dst == "tb"
    assert e.min_gap == 1
    assert e.max_gap == Params.default().tb.max_start_gap
    assert e.anchor_field == "anchor_bo_id"


def test_throwback_kwargs_match_v1_signature():
    """throwback_kwargs 的七键必须能一一喂给 V1 detector(V1 __init__ 有 measure 校验)。"""
    p = Params.default()
    d = ThrowbackDetectorV0(**p.throwback_kwargs())
    assert d._kw["max_start_gap"] == 7
    assert d._kw["stop_confirm_bars"] == 1


def test_eval_meta():
    assert eval_meta() == {"end_node": "tb", "head_buffer_trading_days": 63}


def test_analyze_smoke_real_data():
    """真实数据 analyze 不炸(V1 全链路:BO → burst → tb V1)。不要求有 match。"""
    from path2_web.data import slice_window
    from path2_apps.bb_v0.dag_spec import analyze

    df = slice_window(pickle.load(open("datasets/pkls/AA.pkl", "rb")), "2024-09-19", "2026-03-08")
    res = analyze(df, load_params())
    assert res is not None
