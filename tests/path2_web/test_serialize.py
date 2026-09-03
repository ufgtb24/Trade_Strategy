from dataclasses import dataclass
from typing import Tuple

from tests.path2.dag._oracle import Ev
from tests.path2.fixtures.positive_case import positive_case
from path2 import Event
from path2_apps.bottom_burst import dag_spec
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
    # F14 修正:out_events 追加容器 child(V4 一容器多段 → +全部容器段数总和)
    tb_containers = [e for e in res.events if getattr(e, "node_id", "") == "tb"]
    n_children = sum(len(c.segments) for c in tb_containers)
    assert n_children >= 1
    assert len(out["events"]) == len(res.events) + n_children
    e0 = out["events"][0]
    assert {"instance_id", "node_id", "instance_idx", "start_idx", "end_idx"} <= set(e0)
    # 子类属性平铺(burst event 必有 count/distinct_pk)
    burst = next(e for e in out["events"] if e["node_id"] == "burst")
    assert "count" in burst and "distinct_pk" in burst
    assert isinstance(burst["distinct_pk"], int)


def test_serialize_match_node_index_and_trace():
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    assert len(out["matches"]) >= 1
    m = out["matches"][0]
    assert {"match_id", "start_idx", "end_idx", "node_index", "children", "predicate_trace"} <= set(m)
    # 实例流:node_index 每节点值 = instance_id 字符串(与事件行同源);bo 不进 node_index(isolated)
    assert isinstance(m["node_index"]["burst"], str) and "#" in m["node_index"]["burst"]
    assert isinstance(m["node_index"]["tb"], str) and "#" in m["node_index"]["tb"]
    assert "bo" not in m["node_index"]
    # children = node_index 展平,instance_id 列表
    assert isinstance(m["children"], list) and all(isinstance(c, str) for c in m["children"])
    # trace:where_results 是富化 witness(measured/op/threshold)
    pt = m["predicate_trace"]
    # burst 的 3 个 where 子句:distinct_pk 有 measured/op/threshold
    burst_wr = pt["where_results"]["burst"]
    assert set(burst_wr) >= {"first_drought", "distinct_pk", "vol_spike"}
    dpk = burst_wr["distinct_pk"]
    assert dpk["op"] == ">=" and "measured" in dpk and "satisfied" in dpk
    # edge witness:"src→dst" key + src/dst instance_id + measured
    assert any("→" in k for k in pt["edge_results"])
    ew = next(iter(pt["edge_results"].values()))
    assert {"satisfied", "measured", "src", "dst"} <= set(ew)


def test_summarize_counts_by_node_id_plus_matches():
    res = _analyze_positive()
    s = serialize.summarize(res)
    assert s["matches"] == len(res.matches)
    assert "burst" in s and "bo" in s
    # 计数 == events 全集里该 node_id 数量
    n_bo = sum(1 for e in res.events if e.node_id == "bo")
    assert s["bo"] == n_bo


def test_serialize_pattern_topology_and_rules():
    from path2_apps.bottom_burst.dag_spec import PATTERN_DAG
    out = serialize.serialize_pattern(PATTERN_DAG)
    assert out["pattern_id"] == "bottom_burst"
    topo = out["topology"]
    ids = {n["node_id"] for n in topo["nodes"]}
    assert ids == {"bo", "burst", "pk", "tb", "tb_seg"}   # 4 独立 node + 子结构 tb_seg
    # 子结构 node(无 detector):materialize_keys 空
    seg = next(n for n in topo["nodes"] if n["node_id"] == "tb_seg")
    assert seg["materialize_keys"] == []
    # produced_by 透传:子结构 tb_seg 的物化来源 = 父容器 tb
    assert seg["produced_by"] == "tb"
    # bo 节点:isolated plain node
    bo = next(n for n in topo["nodes"] if n["node_id"] == "bo")
    assert bo["produced_by"] is None     # 独立 node 物化来源为空
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
    from path2_apps.bottom_burst.dag_spec import PATTERN_DAG
    out = serialize.serialize_pattern(PATTERN_DAG)
    # PATTERN_DAG.event_styles 为空 → 后端按 node_id 兜底补齐
    styles = out["event_styles"]
    assert set(styles) >= {"burst", "bo", "tb"}
    assert all(isinstance(c, str) and c.startswith("#") for c in styles.values())


def test_serialize_child_combinator_rule():
    from path2.dag import where as W
    from path2_web.serialize import _rules_from_where
    # W.child 返回 _Pred,meta={'kind':'child','key':'first_bo','inner':{...}}
    pred = W.child("first_bo", W.attr("drought", ">=", 60))
    rules = _rules_from_where([("c1", pred)])
    assert any(r.get("kind") == "child" and r.get("key") == "first_bo" for r in rules)


from path2_web.serialize import serialize_pattern


def test_serialize_pattern_nodes_have_render_grid():
    """serialize_pattern 节点 dict 透传 render_grid; bo='price', 其余='time'。"""
    from path2_apps.bottom_burst.dag_spec import PATTERN_DAG
    out = serialize.serialize_pattern(PATTERN_DAG)
    by = {n["node_id"]: n for n in out["topology"]["nodes"]}
    assert by["bo"]["render_grid"] == "price"
    assert by["burst"]["render_grid"] == "time"
    assert by["tb"]["render_grid"] == "time"


def test_burst_event_dict_child_refs_protocol():
    """child_refs 承载 BurstEvent.members(schema-driven,不硬编码字段名);
    顶层 members 字段消失(不留兼容层)。"""
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    events = out["events"]
    burst = next(e for e in events if e["node_id"] == "burst")
    # 顶层无 members
    assert "members" not in burst, "payload 里不再有顶层 members 字段(由 child_refs 承载)"
    # child_refs["members"] 是 instance_id 列表
    assert "child_refs" in burst, "所有 event 必须携带 child_refs"
    assert burst["child_refs"].get("members"), "BurstEvent child_refs.members 非空"
    assert all(isinstance(x, str) and "#" in x for x in burst["child_refs"]["members"])
    bo_ids = {e["instance_id"] for e in events if e["node_id"] == "bo"}
    for mid in burst["child_refs"]["members"]:
        assert mid in bo_ids


def test_leaf_event_child_refs_empty():
    """叶子 event(BOEvent)child_refs 是空 dict;容器(tb)child_refs 承载 segments 引用。

    注意:段(ThrowbackSegment)与容器(ThrowbackEvent)同 node_id"tb"(annotate_instances
    嵌套 child 继承父 node_id),二者以 child_refs 区分——容器非空、段为空。"""
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    events = out["events"]
    # 叶子:bo 事件 child_refs 空
    for e in events:
        if e["node_id"] == "bo":
            assert e.get("child_refs") == {}, f"{e['instance_id']}: 叶子 event child_refs 必须为空 dict"
    # 容器:携带非空 segments 引用的 tb 事件(段与容器同 node_id,以 child_refs 区分)
    containers = [e for e in events if e["node_id"] == "tb"
                  and e.get("child_refs", {}).get("segments")]
    assert containers, "应有携带 segments 的 tb 容器"
    for c in containers:
        assert set(c["child_refs"].keys()) == {"segments"}


def test_serialize_pattern_edges_anchor_field():
    """topology.edges 每条边携带 anchor_field(str 或 None);bottom_burst 的 burst→tb 边
    anchor_field = 'anchor_bo_id'。"""
    from path2_apps.bottom_burst.dag_spec import PATTERN_DAG
    result = serialize.serialize_pattern(PATTERN_DAG)
    edges = result["topology"]["edges"]
    assert len(edges) >= 1
    for e in edges:
        assert "anchor_field" in e, f"每条边必须携带 anchor_field 键(值可为 None): {e!r}"
    # burst→tb 边 anchor_field 为 'anchor_bo_id'
    burst_tb = next(e for e in edges if e["src"] == "burst" and e["dst"] == "tb")
    assert burst_tb["anchor_field"] == "anchor_bo_id"


def test_serialize_analysis_bo_events_have_ref_ids():
    """serialize_analysis 的 bo/pk event dict 输出 ref_ids(取代原始引用对象递归展开)。
    引用走 ref_slots 协议:broken_refs/superseded_refs 已由引擎物化收编进
    e.ref_ids,_event_to_dict 跳过这两个原始字段、末尾统一从 ref_ids 生成
    dict 形 {槽名: [instance_id, ...]}。"""
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    bo_events = [e for e in out["events"] if e["node_id"] == "bo"]
    assert len(bo_events) >= 1
    for bo in bo_events:
        assert "referenced_points" not in bo
        assert "broken_refs" not in bo
        assert "ref_ids" in bo
        broken = bo["ref_ids"]["broken"]   # 每个 bo 恒突破 >=1 个峰,非空
        assert isinstance(broken, list) and broken
        for iid in broken:
            assert isinstance(iid, str) and iid   # 翻译为 instance_id 字符串,非嵌套 dict
    pk_events = [e for e in out["events"] if e["node_id"] == "pk"]
    assert len(pk_events) >= 1
    for pk in pk_events:
        assert "superseded_refs" not in pk
        assert "ref_ids" in pk   # 多数峰未被吃,ref_ids 可为 {}


def test_serialize_analysis_events_no_nested_event_dict():
    """payload 去递归嵌套:json.dumps(out["events"]) 里不出现嵌套事件 dict——任何
    事件 dict 的字段值(递归穿透 list)都不含"instance_id 键的 dict"(旧实现把
    broken_refs 里的 PeakEvent 对象递归展开成嵌套 dict,现改为 ref_ids 引用槽,
    总长度相对旧实现显著缩小,无需断言具体数字)。"""
    import json

    def _has_nested_event_dict(v):
        if isinstance(v, dict):
            return "instance_id" in v or any(_has_nested_event_dict(x) for x in v.values())
        if isinstance(v, list):
            return any(_has_nested_event_dict(x) for x in v)
        return False

    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    dumped = json.loads(json.dumps(out["events"]))   # sanity:仍可 json 序列化
    assert dumped   # 下限:fixture 必须真产出事件,否则下面的循环空转恒绿
    for e in dumped:
        for v in e.values():   # 只检查顶层 event dict 的字段值,不含事件 dict 自身的 instance_id 键
            assert not _has_nested_event_dict(v), f"字段值中出现嵌套事件 dict: {e}"


def test_ref_field_skip_survives_unresolvable_forward_ref():
    """_ref_field_names 的 typing.get_type_hints 解析失败时(局部类前向引用,
    类所在模块 globalns 里找不到该局部名)必须回退到字面注解字符串判据,而不是
    "不跳过"——不跳过 = 原始引用对象重新递归展开进 payload,即本 task 要修的
    嵌套膨胀 bug 复发。

    构造手法:字段类型写成显式字符串前向引用,指向一个只在本函数局部存在的
    名字(_UndefinedLocalEvent,故意不定义)。get_type_hints 用 cls.__module__
    的 globalns 解析注解,该模块顶部已 `from typing import Tuple`(排除
    Tuple 本身不可解析的干扰),但 _UndefinedLocalEvent 是纯局部名,globalns
    里必然没有 → NameError,精确覆盖到 _ref_field_names 的 except 回退分支。
    """
    @dataclass(frozen=True)
    class _LocalRefEvent(Event):
        refs: "Tuple[_UndefinedLocalEvent, ...]" = ()   # noqa: F821 (故意不可解析,测回退路径)

        def ref_slots(self):
            return {"x": self.refs} if self.refs else {}

    ev = _LocalRefEvent(start_idx=0, end_idx=0, confirm_idx=0)
    row = serialize._event_to_dict(ev)
    assert "refs" not in row


def test_clause_to_dict_recursive():
    from path2.dag import where as W
    from path2_web.serialize import _clause_to_dict

    @dataclass(frozen=True)
    class _E:
        pk: int = 0
        vol: float = 0.0

    w = W.any(W.attr("pk", ">=", 4), W.attr("vol", ">=", 8.0)).witness(_E(pk=5))
    d = _clause_to_dict(w)
    assert d["satisfied"] is True and d["label"] == "or"
    assert [c["label"] for c in d["children"]] == ["pk", "vol"]
    assert [c["measured"] for c in d["children"]] == [5, 0.0]
    assert "children" not in d["children"][0]          # 叶子不带空 children 键


def test_clause_to_dict_flat_leaf_unchanged():
    from dataclasses import dataclass
    from path2.dag import where as W
    from path2_web.serialize import _clause_to_dict

    @dataclass(frozen=True)
    class _E:
        pk: int = 0

    d = _clause_to_dict(W.attr("pk", ">=", 4).witness(_E(pk=3)))
    assert d["satisfied"] is False and d["measured"] == 3
    assert d["op"] == ">=" and d["threshold"] == 4
    assert "children" not in d


def test_rules_from_where_recursive():
    from path2.dag import where as W
    from path2_web.serialize import _rules_from_where
    pred = W.any(W.attr("pk", ">=", 4), W.attr("vol", ">=", 8.0))
    rules = _rules_from_where([("pk_or_vol", pred),
                               ("first_drought", W.attr("first_drought", ">=", 20))])
    assert rules[0]["clause_id"] == "pk_or_vol" and rules[0]["kind"] == "or"
    kids = rules[0]["children"]
    assert [k["field"] for k in kids] == ["pk", "vol"]
    assert [k["op"] for k in kids] == [">=", ">="]
    # 叶子顶层 rule:旧键保留 + 新增 kind/field
    assert rules[1]["clause_id"] == "first_drought"
    assert rules[1]["op"] == ">=" and rules[1]["threshold"] == 20
    assert rules[1]["kind"] == "attr" and rules[1]["field"] == "first_drought"


def test_serialize_match_has_leaf_instance_id():
    """每个被过滤的 match dict 注入 leaf(= end_node 事件 instance_id 字符串)。
    win 取 positive_case df 全量 + 合成 date 列(serialize 用 win['date'] 定位买点日)。"""
    import pandas as pd
    df, params = positive_case()
    res = dag_spec.analyze(df, params)
    win = df.copy()
    win["date"] = pd.date_range("2024-01-01", periods=len(win))
    start_ts = pd.to_datetime(win["date"].iat[0])
    end_ts = pd.to_datetime(win["date"].iat[-1])
    out = serialize.serialize_per_pattern_result(
        res, end_node="tb", label_horizon=5,
        win=win, start_ts=start_ts, end_ts=end_ts)
    assert out["analysis"]["matches"]
    for md in out["analysis"]["matches"]:
        assert isinstance(md.get("leaf"), str) and "#" in md["leaf"]
        assert "leaf_event_id" not in md, "leaf_event_id 兼容字段已随 event_id 体系删除"


def _make_price_df(n=30):
    """单调上行日线(买点窗内首穿四态全 none,便于断言累加总数)。"""
    import numpy as np
    import pandas as pd
    closes = 100.0 + np.arange(n) * 1.0
    return pd.DataFrame({
        'open': closes - 0.3,
        'high': closes + 0.2,
        'low': closes - 0.2,
        'close': closes,
        'volume': np.full(n, 1e6),
        'date': pd.date_range("2024-01-01", periods=n),
    })


def test_fp_counts_dedup_shared_leaf():
    """共享 leaf 的多 match:首穿四态只按 leaf 累加一次(买点日是物理属性)。"""
    from tests.path2.dag._oracle import Ev
    from path2.dag._solve import Solution, compile_plan
    from path2.dag.nodes import NodeSpec
    from path2.dag.edges import TemporalEdge
    from path2.dag.spec import PatternSpec
    from path2.dag._reify import reify
    from path2.dag.result import AnalysisResult
    from path2_web.serialize import serialize_per_pattern_result

    class _StubDetector:
        """占位 detector:只声明 event_cls(compile_plan 不调 detect,streams 直给)。"""
        event_cls = Ev

    # 两上游(A)共享同一 leaf(B),span 相同:放宽后两个 match 可见
    nodes = [NodeSpec("A", detector=_StubDetector()), NodeSpec("B", detector=_StubDetector())]
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    plan = compile_plan(PatternSpec(pattern_id="p", nodes=tuple(nodes), edges=tuple(edges)))
    a1, a2 = Ev("a_1", 0, 5), Ev("a_2", 0, 5)
    b = Ev("b_1", 25, 27)   # 买点窗置于 df 后段:rolling(20) 的 M 样本充足(前 19 根为 NaN)
    m1 = reify(Solution(assign={"A": a1, "B": b}, chosen_idx={}), streams={}, plan=plan)
    m2 = reify(Solution(assign={"A": a2, "B": b}, chosen_idx={}), streams={}, plan=plan)
    res = AnalysisResult(events=(), matches=(m1, m2), spec=None)
    win = _make_price_df(30)
    out = serialize_per_pattern_result(res, end_node="B", label_horizon=2,
                                       win=win, start_ts=win["date"].iat[0],
                                       end_ts=win["date"].iat[-1],
                                       first_passage_enabled=True, first_passage_k=5.0)
    assert out["match_fp_counts"] == {"up": 0, "down": 0, "both": 0, "none": 3}


# ── 实例流:契约层实例视图(instance_id / match leaf) ──

class _FakeDet:
    """合成 detector:忽略输入源,直接吐已构造好的 canned 事件序列(多实例流用)。"""
    event_cls = Ev

    def __init__(self, evs):
        self._evs = evs

    def detect(self, *source):
        return iter(self._evs)


def _analyze_dup_stream():
    """src 流内同 node_id 同 span 两实例(仅 pos 不同)→ 多实例 res(engine 全流程)。

    与 test_engine_match_id_disambiguate 同构:两实例各产一个 match(match id 碰撞
    由 engine 消歧为 #0/#1);events = (s0×2, d0)。"""
    from path2.dag.engine import analyze
    from path2.dag.spec import PatternSpec
    from path2.dag.nodes import NodeSpec
    from path2.dag.edges import TemporalEdge
    spec = PatternSpec(pattern_id="dup", nodes=(
        NodeSpec(node_id="src", detector=_FakeDet(
            [Ev("s0", 5, 10, pos=0), Ev("s0", 5, 10, pos=1)])),
        NodeSpec(node_id="dst", detector=_FakeDet([Ev("d0", 20, 20)])),
    ), edges=(TemporalEdge("src", "dst", min_gap=0, max_gap=100),))
    return analyze(spec, None)


def test_serialize_events_instance_id_contract():
    """事件行新契约:instance_id/node_id/instance_idx 恒在;无 event_id/
    source_tag/instance_key/class_id。"""
    payload = serialize.serialize_analysis(_analyze_dup_stream())
    for r in payload["events"]:
        assert {"instance_id", "node_id", "instance_idx"} <= set(r)
        assert "#" in r["instance_id"]         # 恒带 #idx
        for banned in ("event_id", "source_tag", "instance_key", "class_id"):
            assert banned not in r, f"{banned} 残留"


def test_serialize_match_instance_refs():
    """match 行:node_index 值为 instance_id 字符串;children 全实例化;match_id。"""
    payload = serialize.serialize_analysis(_analyze_dup_stream())
    for m in payload["matches"]:
        assert "match_id" in m and "event_id" not in m
        for nid, ref in m["node_index"].items():
            assert isinstance(ref, str) and "#" in ref
        for c in m["children"]:
            assert isinstance(c, str) and "#" in c


def test_serialize_child_refs_instanced():
    """事件行 child_refs 值全实例化(instance_id 列表)。"""
    from tests.path2.dag._oracle import WideEv
    from path2.dag.result import AnalysisResult
    # 带 child 的容器(实例化标注),child_refs 才有非空断言面(Ev 无 child_slots)
    w1 = WideEv("w0", 0, 5, node_id="w0", instance_idx=0, instance_id="w0_0_5#0",
                kids=(Ev("k0", 0, 0, node_id="k0", instance_idx=0, instance_id="k0_0#0"),))
    res = AnalysisResult(events=(w1,), matches=(), spec=None)
    payload = serialize.serialize_analysis(res)
    for r in payload["events"]:
        for slot, ids in (r.get("child_refs") or {}).items():
            for i in ids:
                assert isinstance(i, str) and "#" in i


def test_serialize_events_multi_instance_rows():
    """同 node_id 多实例序列化为多行,instance_id(#idx)区分;单实例也恒输出 #idx。"""
    from tests.path2.dag._oracle import WideEv
    from path2.dag.result import AnalysisResult
    # 同 node_id 两容器实例,各带一个同 node_id 的 child(挖取路径验证不丢多实例)
    w1 = WideEv("w0", 0, 5, node_id="w0", instance_idx=0, instance_id="w0_0_5#0",
                kids=(Ev("k0", 0, 0, node_id="k0", instance_idx=0, instance_id="k0_0#0"),))
    w2 = WideEv("w0", 10, 15, node_id="w0", instance_idx=1, instance_id="w0_10_15#1",
                kids=(Ev("k0", 10, 10, node_id="k0", instance_idx=1, instance_id="k0_10#1"),))
    res = AnalysisResult(events=(w1, w2), matches=(), spec=None)
    out = serialize.serialize_analysis(res)
    rows = [r for r in out["events"] if r["node_id"] == "w0"]
    assert len(rows) == 2, f"多实例应序列化 2 行,got {len(rows)}"
    assert {r["instance_id"] for r in rows} == {"w0_0_5#0", "w0_10_15#1"}
    # child 挖取:两个 child 都保留(不丢多实例),各自 instance_id
    kids = [r for r in out["events"] if r["node_id"] == "k0"]
    assert len(kids) == 2, f"child 挖取不应丢多实例,got {len(kids)}"
    assert {r["instance_id"] for r in kids} == {"k0_0#0", "k0_10#1"}
    # 实例级字段各自保留:child_refs 各指其 own kid
    by_id = {r["instance_id"]: r for r in rows}
    assert by_id["w0_0_5#0"]["child_refs"]["kids"] == ["k0_0#0"]
    assert by_id["w0_10_15#1"]["child_refs"]["kids"] == ["k0_10#1"]


def test_serialize_match_multi_instance_leaf():
    """match 行 leaf = end_node 事件 instance_id 字符串(与事件行同源)。"""
    import pandas as pd
    res = _analyze_dup_stream()
    win = pd.DataFrame({"open": [100.0] * 30, "high": [101.0] * 30,
                        "low": [99.0] * 30, "close": [100.0] * 30,
                        "date": pd.date_range("2024-01-01", periods=30)})
    start_ts = win["date"].iat[0]
    end_ts = win["date"].iat[-1]
    out = serialize.serialize_per_pattern_result(
        res, end_node="dst", label_horizon=2,
        win=win, start_ts=start_ts, end_ts=end_ts)
    evs = out["analysis"]["events"]
    # events:s0 两实例 #0/#1;d0 单实例也恒输出 #0
    assert {r["instance_id"] for r in evs if r["node_id"] == "src"} == {"src_5_10#0", "src_5_10#1"}
    d0 = next(r for r in evs if r["node_id"] == "dst")
    assert d0["instance_id"] == "dst_20#0"
    # 两 match 共享 leaf d0:leaf = d0 行的 instance_id 字符串(与事件行同源)
    assert len(out["analysis"]["matches"]) == 2
    for md in out["analysis"]["matches"]:
        assert md["leaf"] == "dst_20#0"
        assert "leaf_event_id" not in md
    # end_node 锚到多实例 src:两 match 的 leaf 各自定位到具体实例(instance_id 区分)
    out2 = serialize.serialize_per_pattern_result(
        res, end_node="src", label_horizon=2,
        win=win, start_ts=start_ts, end_ts=end_ts)
    leafs = {md["leaf"] for md in out2["analysis"]["matches"]}
    assert leafs == {"src_5_10#0", "src_5_10#1"}


def test_serialize_match_node_index_instanced():
    """match node_index 每节点值 = instance_id 字符串,与事件行 instance_id 同源。"""
    res = _analyze_dup_stream()   # 同 node_id(s0)双实例 + 两 match,node_index 引用它们
    payload = serialize.serialize_analysis(res)
    matches = payload["matches"]
    assert len(matches) == 2
    ev_rows = {r["instance_id"]: r for r in payload["events"]}
    for m in matches:
        for nid, ref in m["node_index"].items():
            assert isinstance(ref, str), f"node_index[{nid}] 应为 instance_id 字符串, 实为 {ref!r}"
            assert ref in ev_rows, f"{ref} 不在事件行(instance_id 编号不同源)"
    # 双实例场景:src 节点的 instance_id 能区分两个实例(两 match 各引用一个)
    src_refs = [ref for m in matches for nid, ref in m["node_index"].items()
                if nid == "src"]
    assert len({r for r in src_refs}) >= 2, "同 node_id 双实例的 instance_id 应区分"
