from tests.path2.fixtures.positive_case import positive_case
from path2_apps.bottom_breakout_burst import dag_spec
from path2_web import serialize


def _analyze_positive():
    df, params = positive_case()
    return dag_spec.analyze(df, params)   # 宽松 params → 必有 >=1 match


def test_jsonable_handles_tuple_none_nan_nested():
    assert serialize._jsonable((1, 2, 3)) == [1, 2, 3]
    assert serialize._jsonable(None) is None
    assert serialize._jsonable(3.5) == 3.5
    # 嵌套对象 fallback 不抛
    class X: pass
    assert isinstance(serialize._jsonable(X()), str)


def test_serialize_events_flatten_subclass_attrs():
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    assert len(out["events"]) == len(res.events)
    e0 = out["events"][0]
    assert {"class_id", "event_id", "start_idx", "end_idx"} <= set(e0)
    # 子类属性平铺(burst event 必有 count/distinct_pk)
    burst = next(e for e in out["events"] if e["class_id"] == "burst")
    assert "count" in burst and "distinct_pk" in burst
    assert isinstance(burst["distinct_pk"], int)


def test_serialize_burst_members_as_event_ids():
    """burst.members 序列化为 event_id 字符串列表(非嵌套 dict),供前端 matchedIds 沿 members 递归展开。
    与 broken_peak_ids 不同:broken_peak_ids 是 int 列表,members 是 event_id str 列表。"""
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    burst = next(e for e in out["events"] if e["class_id"] == "burst")
    assert "members" in burst, "burst event dict 必须含 members 字段"
    assert isinstance(burst["members"], list)
    assert len(burst["members"]) >= 1
    assert all(isinstance(m, str) for m in burst["members"]), "members 内每项必须是 event_id 字符串(非 dict)"
    # members 内所有 event_id 都能在 events 集中找到对应 bo event
    bo_ids = {e["event_id"] for e in out["events"] if e["class_id"] == "bo"}
    for mid in burst["members"]:
        assert mid in bo_ids, f"burst.members 内 event_id {mid!r} 必须存在于顶层 bo events 中"


def test_serialize_match_role_index_and_trace():
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    assert len(out["matches"]) >= 1
    m = out["matches"][0]
    assert {"event_id", "start_idx", "end_idx", "role_index", "children", "predicate_trace"} <= set(m)
    # burst 是 ONCE role → str;tb 也是 ONCE role → str;bo 不进 role_index(isolated)
    assert isinstance(m["role_index"]["burst"], str)
    assert isinstance(m["role_index"]["tb"], str)
    assert "bo" not in m["role_index"]
    # children = role_index 展平,event_id 列表
    assert isinstance(m["children"], list) and all(isinstance(c, str) for c in m["children"])
    # trace:where_results 是富化 witness(measured/op/threshold)
    pt = m["predicate_trace"]
    # burst 的 3 个 where 子句:distinct_pk 有 measured/op/threshold
    burst_wr = pt["where_results"]["burst"]
    assert set(burst_wr) >= {"first_drought", "distinct_pk", "vol_spike"}
    dpk = burst_wr["distinct_pk"]
    assert dpk["op"] == ">=" and "measured" in dpk and "satisfied" in dpk
    # edge witness:"src→dst" key + src/dst event_id + measured
    assert any("→" in k for k in pt["edge_results"])
    ew = next(iter(pt["edge_results"].values()))
    assert {"satisfied", "measured", "src", "dst"} <= set(ew)


def test_summarize_counts_by_class_id_plus_matches():
    res = _analyze_positive()
    s = serialize.summarize(res)
    assert s["matches"] == len(res.matches)
    assert "burst" in s and "bo" in s
    # 计数 == events 全集里该 class_id 数量
    n_bo = sum(1 for e in res.events if type(e).class_id == "bo")
    assert s["bo"] == n_bo


def test_serialize_pattern_topology_and_rules():
    from path2_apps.bottom_breakout_burst.dag_spec import PATTERN_DAG
    out = serialize.serialize_pattern(PATTERN_DAG)
    assert out["pattern_id"] == "bottom_breakout_burst"
    topo = out["topology"]
    ids = {n["node_id"] for n in topo["nodes"]}
    assert ids == {"bo", "burst", "tb"}   # 3 nodes: bo isolated + burst/tb ONCE
    # bo 节点:isolated plain node
    bo = next(n for n in topo["nodes"] if n["node_id"] == "bo")
    # burst 节点:ONCE,where_rules 含 3 个阈值(first_drought/distinct_pk/vol_spike)
    burst = next(n for n in topo["nodes"] if n["node_id"] == "burst")
    burst_rules = {r["clause_id"]: r for r in burst["where_rules"]}
    assert {"first_drought", "distinct_pk", "vol_spike"} <= set(burst_rules)
    assert burst_rules["first_drought"]["op"] == ">=" and isinstance(burst_rules["first_drought"]["threshold"], (int, float))
    assert burst_rules["distinct_pk"]["op"] == ">=" and isinstance(burst_rules["distinct_pk"]["threshold"], (int, float))
    assert burst_rules["vol_spike"]["op"] == ">=" and isinstance(burst_rules["vol_spike"]["threshold"], float)
    # 唯一边: burst.last_bo → tb (TemporalEdge, anchor)
    edge_rules = {(e["src"], e["dst"]): e for e in topo["edges"]}
    assert edge_rules[("burst", "tb")]["kind"] == "TemporalEdge"  # 回踩锚末 bo
    assert "gap" in edge_rules[("burst", "tb")]["rule"]


def test_serialize_pattern_event_styles_fallback():
    from path2_apps.bottom_breakout_burst.dag_spec import PATTERN_DAG
    out = serialize.serialize_pattern(PATTERN_DAG)
    # PATTERN_DAG.event_styles 为空 → 后端按 class_id 兜底补齐
    styles = out["event_styles"]
    assert set(styles) >= {"burst", "bo", "tb"}
    assert all(isinstance(c, str) and c.startswith("#") for c in styles.values())


def test_serialize_child_combinator_rule():
    from path2.dag import where as W
    from path2_web.serialize import _rules_from_where
    # W.child 返回 _Pred，meta={'kind':'child','key':'first_bo','inner':{...}}
    pred = W.child("first_bo", W.attr("drought", ">=", 60))
    rules = _rules_from_where([("c1", pred)])
    assert any(r.get("kind") == "child" and r.get("key") == "first_bo" for r in rules)



import pytest
from path2_web.serialize import serialize_pattern, _assert_injective_source_tags
from path2_apps.bottom_breakout_burst.dag_spec import build_pattern
from path2_apps.bottom_breakout_burst.params import Params
from path2.dag.nodes import NodeSpec
from path2.atoms.trend import TrendSegmentDetector


def test_serialize_pattern_nodes_have_source_tag():
    sp = serialize_pattern(build_pattern(Params.default()))
    tags = {n["node_id"]: n["source_tag"] for n in sp["topology"]["nodes"]}
    # 3-node topology: bo / burst / tb
    assert tags["bo"] == "bo" and tags["burst"] == "burst" and tags["tb"] == "tb"
    assert all(n["source_tag"] for n in sp["topology"]["nodes"])  # 非空


def test_injective_assert_raises_on_same_tag_distinct_instances():
    # 两个不同实例、手动设同名 source_tag → 实例不同但 band 会坍缩 → 必须 RAISE
    d1 = TrendSegmentDetector(); d1.source_tag = "dup"
    d2 = TrendSegmentDetector(); d2.source_tag = "dup"
    nodes = (NodeSpec("a", d1), NodeSpec("b", d2))
    with pytest.raises(ValueError, match="source_tag"):
        _assert_injective_source_tags(nodes)


def test_serialize_analysis_events_have_band_source_tag():
    import pickle
    df = pickle.load(open("datasets/pkls/ACRS.pkl", "rb"))
    from path2_apps.bottom_breakout_burst.dag_spec import analyze
    from path2_web.serialize import serialize_analysis
    res = analyze(df)
    sa = serialize_analysis(res)
    tags = {e["source_tag"] for e in sa["events"]}
    assert tags <= {"bo", "burst", "tb"}      # 全归权威 band
    assert all(e.get("source_tag") for e in sa["events"])          # 无 None/缺失


def test_burst_event_dict_members_as_event_ids():
    """burst event dict 的 members 是 event_id 字符串列表(不是嵌套 BOEvent dict);
    供前端 matchedIds 沿 members 递归展开(matched composite event 的 constituent 也 matched)。
    预算标量(count/distinct_pk)仍并存。"""
    import pickle
    df = pickle.load(open("datasets/pkls/ACRS.pkl", "rb"))
    from path2_apps.bottom_breakout_burst.dag_spec import analyze
    from path2_web.serialize import serialize_analysis
    sa = serialize_analysis(analyze(df))
    burst = next(e for e in sa["events"] if e["class_id"] == "burst")
    assert "members" in burst
    assert isinstance(burst["members"], list)
    assert all(isinstance(m, str) for m in burst["members"])    # event_id 字符串非嵌套 dict
    assert burst["count"] >= 1 and "distinct_pk" in burst   # 预算标量仍在


def test_serialize_pattern_nodes_have_render_grid():
    """serialize_pattern 节点 dict 透传 render_grid; bo='price', 其余='time'。"""
    from path2_apps.bottom_breakout_burst.dag_spec import PATTERN_DAG
    out = serialize.serialize_pattern(PATTERN_DAG)
    by = {n["node_id"]: n for n in out["topology"]["nodes"]}
    assert by["bo"]["render_grid"] == "price"
    assert by["burst"]["render_grid"] == "time"
    assert by["tb"]["render_grid"] == "time"


def test_serialize_analysis_bo_events_have_referenced_points():
    """serialize_analysis 的 bo event dict 含 referenced_points (list of [bar_idx, price, label])。
    通过 _event_to_dict 的 fields 遍历自动透传, 验证 _jsonable 把 tuple of tuples 正确转 list of lists。"""
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    bo_events = [e for e in out["events"] if e["class_id"] == "bo"]
    assert len(bo_events) >= 1
    for bo in bo_events:
        assert "referenced_points" in bo
        rp = bo["referenced_points"]
        assert isinstance(rp, list)
        for item in rp:
            assert isinstance(item, list)
            assert len(item) == 3
            bar_idx, price, label = item
            assert isinstance(bar_idx, int)
            assert isinstance(price, float)
            assert isinstance(label, str) and label.startswith("pk")
