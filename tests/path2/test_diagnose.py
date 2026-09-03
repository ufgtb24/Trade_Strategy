# tests/path2/test_diagnose.py
"""per-node 诊断 pass:属性诊断(本 task) + 关系诊断(Task 7)。"""
from path2_apps.bottom_burst import build_pattern
from tests.path2.fixtures.positive_case import positive_case
from path2.dag.result import ClauseWitness


def test_diagnose_attr_covers_all_nodes():
    from path2.dag.diagnose import diagnose
    df, params = positive_case()
    spec = build_pattern(params)
    diag = diagnose(spec, df, params)
    assert set(diag.nodes.keys()) == {n.node_id for n in spec.nodes}   # 每个 node 一份
    # burst 的属性诊断:每个候选 burst 有 first_drought/distinct_pk/vol_spike 三条 clause
    burst = diag.nodes["burst"]
    assert len(burst.attr) >= 1
    cw = burst.attr[0].clauses
    assert "first_drought" in cw and "vol_spike" in cw
    assert isinstance(cw["vol_spike"], ClauseWitness)
    assert cw["vol_spike"].op == ">=" and cw["vol_spike"].threshold is not None


def test_diagnose_burst_attr_has_where_clauses():
    """3 节点后：bo 已无 where(孤立 node)；burst 节点含 ③first_drought/⑤distinct_pk/⑥vol_spike。"""
    from path2.dag.diagnose import diagnose
    df, params = positive_case()
    spec = build_pattern(params)
    diag = diagnose(spec, df, params)
    # bo 现在是孤立 plain node，无 where → attr 为空或无相关 clause
    bo = diag.nodes["bo"]
    assert all(len(row.clauses) == 0 for row in bo.attr)  # bo 无 where 条件
    # burst 节点持有 ③⑤⑥
    burst = diag.nodes["burst"]
    assert len(burst.attr) >= 1
    cw = burst.attr[0].clauses
    assert "first_drought" in cw
    assert "distinct_pk" in cw
    assert "vol_spike" in cw


def test_diagnose_rel_for_tb():
    """3 节点拓扑 bo/burst/tb：tb 持有入边 burst.last_bo→tb(TemporalEdge)。
    bo 无边(孤立 node)→ rel 空。burst 无入边(源)→ rel 空。"""
    from path2.dag.diagnose import diagnose
    df, params = positive_case()
    spec = build_pattern(params)
    diag = diagnose(spec, df, params)
    # tb 有入边 burst→tb(TemporalEdge)
    tb = diag.nodes["tb"]
    assert ("burst", "TemporalEdge") in {(r.src, r.kind) for r in tb.rel}
    for r in tb.rel:
        assert r.total_src >= 0
        assert len(r.ok_src) <= r.total_src               # 合规子集
    # burst 是源(无入边)→ rel 空
    assert diag.nodes["burst"].rel == ()
    # bo 是孤立 node(无边)→ rel 空
    assert diag.nodes["bo"].rel == ()


def test_diagnose_rel_partner_soundness():
    """若某入边 ok_src 非空,则确实存在该上游 event + 一个落入 feasible_window 且 satisfies 的 dst。
    3 节点拓扑：检查 burst.last_bo→tb 边(TemporalEdge，src_selector=last_bo)。"""
    from path2.dag.diagnose import diagnose, _endpoint
    from path2.dag.engine import run_streams
    df, params = positive_case()
    spec = build_pattern(params)
    streams = run_streams(spec, df, params)
    diag = diagnose(spec, df, params)
    # 找 tb 的 burst→tb 入边
    edge = next(e for e in spec.edges if e.dst == "tb")
    tb_stream = streams["tb"]
    for r in diag.nodes["tb"].rel:
        if r.src != "burst":
            continue
        for e_u in r.ok_src:
            a = _endpoint(e_u, _node_by_id(spec, "burst"))
            lo, hi = edge.feasible_window(a)
            assert builtins_any(edge.satisfies(a, e_r) and lo <= e_r.start_idx <= hi
                                for e_r in tb_stream)


def _node_by_id(spec, nid):
    return next(n for n in spec.nodes if n.node_id == nid)


def builtins_any(it):
    import builtins
    return builtins.any(it)


def test_diagnose_is_local_not_global():
    """诊断的 note 明示局部性;且 attr/rel 解耦——不因"某 node 全过"就断言整体可命中。"""
    from path2.dag.diagnose import diagnose
    df, params = positive_case()
    spec = build_pattern(params)
    diag = diagnose(spec, df, params)
    assert "局部" in diag.note                       # 明示边界
    # 解耦性:NodeDiagnostic 不含任何"全局是否成解"字段
    # (produced_by = 物化来源元数据,Task 5 加入,非全局成解字段)
    rd = diag.nodes["bo"]
    assert not hasattr(rd, "global_match")
    assert set(vars(rd).keys()) == {"node_id", "attr", "rel", "produced_by"}


def test_diagnose_exported_from_package():
    import path2.dag as dag
    assert hasattr(dag, "diagnose")
    assert hasattr(dag, "NodeDiagnostics")
    assert hasattr(dag, "ClauseWitness")


def test_diagnose_structural_child_attr_rows():
    """子结构 node(tb_seg)attr 表覆盖父容器槽内事件(段级判定数据源补齐):
    行数 = 各容器段数之和;段直标 node_id/instance_id(物化命名表);
    无 where → vacuous 空 clauses 行(与 bo 同形态,段 tier 升 qualified 深灰)。"""
    from path2.dag.diagnose import diagnose
    from path2.dag.engine import run_streams
    df, params = positive_case()
    spec = build_pattern(params)
    diag = diagnose(spec, df, params)
    streams = run_streams(spec, df, params)
    n_seg = sum(len(e.segments) for e in streams["tb"])
    assert n_seg > 0                                     # fixture 前提:正例产出段
    seg = diag.nodes["tb_seg"]
    assert len(seg.attr) == n_seg
    assert all(row.event.node_id == "tb_seg" for row in seg.attr)
    assert all(row.event.instance_id and row.event.instance_id.startswith("tb_seg_")
               for row in seg.attr)
    assert all(len(row.clauses) == 0 for row in seg.attr)  # 无 where → vacuous


def test_diagnose_structural_child_where_discriminates():
    """子结构 where 判别:tb_seg 挂 where 后同一管道产出段级行,satisfied 真假混合。
    显示与求解正交——gate 语义仍在父 where 的 W.children,不由此引入。"""
    import dataclasses
    from path2.dag import where as W
    from path2.dag.diagnose import diagnose
    df, params = positive_case()
    spec = build_pattern(params)
    nodes = []
    for n in spec.nodes:
        if n.node_id == "tb_seg":
            n = dataclasses.replace(n, where=(
                ("always", W.attr("start_idx", ">=", 0)),
                ("never", W.attr("start_idx", ">=", 10**9))))
        nodes.append(n)
    spec2 = dataclasses.replace(spec, nodes=tuple(nodes))
    diag = diagnose(spec2, df, params)
    rows = diag.nodes["tb_seg"].attr
    assert len(rows) > 0
    assert all("always" in r.clauses and "never" in r.clauses for r in rows)
    assert all(r.clauses["always"].satisfied for r in rows)      # 恒真
    assert not any(r.clauses["never"].satisfied for r in rows)   # 恒假
