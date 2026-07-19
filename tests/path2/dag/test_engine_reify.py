# tests/path2/dag/test_engine_reify.py
"""reify:Solution -> PatternMatch(node_index/children/trace/EdgeWitness)。"""
from tests.path2.dag._oracle import E, Ev, WideEv
from path2.dag.edges import TemporalEdge, ContainmentEdge, Child
from path2.dag.nodes import NodeSpec, MatchContext
from path2.dag.spec import PatternSpec
from path2.dag.result import PatternMatch
from path2.dag._solve import compile_plan, solve
from path2.dag._reify import reify


def _spec(nodes, edges):
    return PatternSpec(pattern_id="p", nodes=tuple(nodes),
                       edges=tuple(edges))


def test_reify_node_index_and_children():
    nodes = [NodeSpec("A", detector=None), NodeSpec("B", detector=None)]
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(5, 8)])}
    plan = compile_plan(_spec(nodes, edges))
    sol = solve(plan, streams)[0]
    ctx = MatchContext(df=None, params=None)
    m = reify(sol, streams, plan, ctx)
    assert isinstance(m, PatternMatch)
    assert m.node_index["A"].start_idx == 0
    assert m.node_index["B"].end_idx == 8
    assert m.start_idx == 0 and m.end_idx == 8          # 跨度=children 包络
    assert [c.start_idx for c in m.children] == [0, 5]   # start 升序扁平


def test_reify_edge_witness_measured():
    nodes = [NodeSpec("A", detector=None), NodeSpec("B", detector=None)]
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    streams = {"A": E("A", [(0, 2)]), "B": E("B", [(5, 8)])}
    plan = compile_plan(_spec(nodes, edges))
    sol = solve(plan, streams)[0]
    m = reify(sol, streams, plan, MatchContext(df=None, params=None))
    w = m.predicate_trace.edge_results[("A", "B")]
    assert w.satisfied is True
    # 硬伤 E · Task 13:measured 升级为 kind-aware(MeasuredKindAware),非裸 float
    assert w.measured.kind == 'gap'
    assert w.measured.value == 5 - 2                       # dst.start - src.end = gap
    assert w.measured.label == 'gap'


def test_reify_where_results_recorded():
    from path2.dag.where import attr as W_attr
    nodes = [NodeSpec("A", detector=None,
                      where=(("nonneg", W_attr("start_idx", ">=", 0)),)),
             NodeSpec("B", detector=None)]
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(5, 5)])}
    plan = compile_plan(_spec(nodes, edges))
    sol = solve(plan, streams, MatchContext(df=None, params=None))[0]
    m = reify(sol, streams, plan, MatchContext(df=None, params=None))
    assert m.predicate_trace.where_results["A"]["nonneg"]


def test_reify_diagnose_child_aware_endpoint():
    """D5：reify edge_results 两端 + diagnose rel 两端都按 Child selector 投影。

    构造：
      - src "wrapper"：[0, 100]
      - dst "burst"：本体 [0, 200]，first_kid [10, 20]，last_kid [150, 180]
      - 边：ContainmentEdge("wrapper", Child("burst", "first_kid"))
        = wrapper 应包含 burst 的 first_kid，而非整个 burst

    若展示层用父整体 (burst [0,200])：ContainmentEdge.satisfies → 200>100 → False
    若展示层用 child 投影 (first_kid [10,20])：20<=100 → True

    断言 (a)：reify 的 edge_results dst_instance 是 first_kid（child 投影，非父）
    断言 (b)：reify 的 edge_results.satisfied == True（child 投影后关系成立）
    断言 (c)：diagnose 的 rel ok_src 非空（有合规 wrapper 能通过 child 投影边）
    断言 (d)：无 selector 时 reify 行为不变（字节等价）
    """
    # 构造宽 child 事件
    first_kid = Ev("fk0", 10, 20, pos=0)
    last_kid = Ev("lk0", 150, 180, pos=1)
    burst = WideEv("burst0", 0, 200, pos=0, kids=(first_kid, last_kid))
    wrapper = Ev("wrapper0", 0, 100, pos=0)

    # 边：wrapper 包含 burst 的 first_kid（dst child projection）
    edge = ContainmentEdge("wrapper", Child("burst", "first_kid"))

    nodes = [NodeSpec("wrapper", detector=None), NodeSpec("burst", detector=None)]
    spec = _spec(nodes, [edge])
    streams = {"wrapper": [wrapper], "burst": [burst]}

    plan = compile_plan(spec)
    sols = solve(plan, streams)
    # 前提：求解层已找到匹配（D4 已实现）
    assert len(sols) == 1, f"求解层应有 1 个匹配，得 {len(sols)} — D4 前提不满足"

    m = reify(sols[0], streams, plan, MatchContext(df=None, params=None))
    ew = m.predicate_trace.edge_results[("wrapper", "burst")]

    # (a) dst_instance 是 first_kid（child 投影），非父 burst
    assert ew.dst_instance is first_kid, (
        f"reify dst_instance 应为 first_kid，得 {ew.dst_instance!r}（展示层未做 dst child 投影？）"
    )
    # (b) 关系在 child 投影后成立
    assert ew.satisfied is True, (
        f"reify satisfied 应为 True（child 投影后 ContainmentEdge 成立），"
        f"得 False（展示层可能用父整体 [0,200] 计算）"
    )
    # src_instance 同样用 endpoint 投影（wrapper 无 selector，返回 wrapper 本体）
    assert ew.src_instance is wrapper

    # (c) diagnose rel：wrapper 能通过 child 投影边找到 burst → ok_src 非空
    # 直接调 _rel_rows（绕过 run_streams / detector=None），只验证展示层 endpoint 逻辑
    from path2.dag.diagnose import _rel_rows
    burst_node = next(n for n in spec.nodes if n.node_id == "burst")
    rel_rows_list = _rel_rows(burst_node, spec, streams)
    rel_rows_map = {r.src: r for r in rel_rows_list}
    assert "wrapper" in rel_rows_map, "diagnose 应有 wrapper→burst 的 rel row"
    rel = rel_rows_map["wrapper"]
    assert len(rel.ok_src) >= 1, (
        f"diagnose rel ok_src 应非空（wrapper 通过 child 投影满足边），"
        f"得 {len(rel.ok_src)}（diagnose _endpoint 未做 dst child 投影？）"
    )

    # (d) 无 selector 的边，reify 不变（字节等价）
    plain_edge = ContainmentEdge("wrapper", "burst")
    plain_burst = WideEv("burst1", 10, 20, pos=1, kids=(first_kid, last_kid))
    plain_wrapper = Ev("wrapper1", 0, 100, pos=1)
    plain_spec = _spec(nodes, [plain_edge])
    plain_streams = {"wrapper": [plain_wrapper], "burst": [plain_burst]}
    plain_plan = compile_plan(plain_spec)
    plain_sols = solve(plain_plan, plain_streams)
    # plain_burst [10,20] ⊆ [0,100]: ContainmentEdge 以父整体就满足
    assert len(plain_sols) == 1
    plain_m = reify(plain_sols[0], plain_streams, plain_plan, MatchContext(df=None, params=None))
    plain_ew = plain_m.predicate_trace.edge_results[("wrapper", "burst")]
    # 无 selector → dst_instance 是 burst 父整体（不是 child）
    assert plain_ew.dst_instance is plain_burst, (
        "无 selector 时 reify dst_instance 应为父整体（字节等价），"
        f"得 {plain_ew.dst_instance!r}"
    )
