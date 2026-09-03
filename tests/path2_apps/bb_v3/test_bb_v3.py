"""bb_v3 app 结构 + 冒烟测试(V3 re-entry 多段 throwback)。

结构断言:克隆 bb_v1 骨架,唯一区别 = tb node 用 V3 ThrowbackDetectorV3。
冒烟:真实数据 analyze 不炸(不要求有 match——V3 参数下命中与否不是本 app 的契约)。
"""
import pickle


from path2.dag.edges import TemporalEdge
from path2.dag.spec import PatternSpec
from path2.atoms.throwback_v3 import ThrowbackDetectorV3, ThrowbackEventV3, ThrowbackSegmentV3
from path2_apps.bb_v3.dag_spec import build_pattern, PATTERN_DAG, eval_meta
from path2_apps.bb_v3.params import Params, load_params


def test_pattern_id_and_topology():
    assert PATTERN_DAG.pattern_id == "bb_v3"
    spec = PATTERN_DAG if isinstance(PATTERN_DAG, PatternSpec) else build_pattern(Params.default())
    nodes = {n.node_id: n for n in spec.nodes}
    assert set(nodes) == {"bo", "burst", "pk", "tb", "tb_seg_v3"}
    assert nodes["pk"].solve is False   # pk 孤立显示 node:不参与匹配
    endpoints = {ep for e in spec.edges for ep in (e.src, e.dst)}
    assert "bo" not in endpoints
    assert nodes["bo"].where == ()
    assert nodes["burst"].consumes_stream == "bo"
    assert nodes["tb"].consumes_stream == "burst"
    assert nodes["tb"].children == {"segments": "tb_seg_v3"}
    assert nodes["tb_seg_v3"].event_cls is ThrowbackSegmentV3
    assert nodes["tb_seg_v3"].produced_by == "tb"
    assert isinstance(nodes["tb"].detector, ThrowbackDetectorV3)
    assert nodes["tb"].detector.event_cls is ThrowbackEventV3
    assert len(spec.edges) == 1
    e = spec.edges[0]
    assert isinstance(e, TemporalEdge)
    assert e.src_selector == "last_bo"
    assert e.dst == "tb"
    assert e.min_gap == 1
    assert e.max_gap == Params.default().tb.max_start_gap
    assert e.anchor_field == "anchor_bo_id"


def test_throwback_kwargs_match_v3_signature():
    """throwback_kwargs 的九键必须能一一喂给 V3 detector(V3 __init__ 有 measure 校验)。"""
    p = Params.default()
    d = ThrowbackDetectorV3(**p.throwback_kwargs())
    assert d._kw["max_start_gap"] == 15
    assert d._kw["stop_confirm_bars"] == 1
    assert d._kw["judged_measure"] == "close"
    assert d._kw["reference_measure"] == "close"
    assert d._kw["anchor_mode"] == "span_min"


def test_eval_meta():
    assert eval_meta() == {"end_node": "tb.segments", "head_buffer_trading_days": 63}


def test_analyze_smoke_real_data():
    """真实数据 analyze 不炸(V3 全链路:BO → burst → tb V3)。不要求有 match。"""
    from path2_web.data import slice_window
    from path2_apps.bb_v3.dag_spec import analyze

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
    from path2_apps.bb_v3.params import DEFAULT_YAML_PATH
    raw = yaml.safe_load(open(DEFAULT_YAML_PATH))
    assert raw["burst"]["peak_age_min"] == 125
