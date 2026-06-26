# tests/path2/test_diagnose.py
"""per-role 诊断 pass:属性诊断(本 task) + 关系诊断(Task 7)。"""
from path2_apps.bottom_breakout_burst import build_pattern
from tests.path2.fixtures.positive_case import positive_case
from path2.dag.result import ClauseWitness


def test_diagnose_attr_covers_all_roles():
    from path2.dag.diagnose import diagnose
    df, params = positive_case()
    spec = build_pattern(params)
    diag = diagnose(spec, df, params)
    assert set(diag.roles.keys()) == {n.node_id for n in spec.nodes}   # 每个 role 一份
    # burst 的属性诊断:每个候选 burst 有 first_drought/distinct_pk/vol_spike 三条 clause
    burst = diag.roles["burst"]
    assert len(burst.attr) >= 1
    cw = burst.attr[0].clauses
    assert "first_drought" in cw and "vol_spike" in cw
    assert isinstance(cw["vol_spike"], ClauseWitness)
    assert cw["vol_spike"].op == ">=" and cw["vol_spike"].threshold is not None


def test_diagnose_burst_attr_has_where_clauses():
    """3 节点后：bo 已无 where(孤立 role)；burst 节点含 ③first_drought/⑤distinct_pk/⑥vol_spike。"""
    from path2.dag.diagnose import diagnose
    df, params = positive_case()
    spec = build_pattern(params)
    diag = diagnose(spec, df, params)
    # bo 现在是孤立 plain node，无 where → attr 为空或无相关 clause
    bo = diag.roles["bo"]
    assert all(len(row.clauses) == 0 for row in bo.attr)  # bo 无 where 条件
    # burst 节点持有 ③⑤⑥
    burst = diag.roles["burst"]
    assert len(burst.attr) >= 1
    cw = burst.attr[0].clauses
    assert "first_drought" in cw
    assert "distinct_pk" in cw
    assert "vol_spike" in cw


def test_diagnose_rel_for_tb():
    """3 节点拓扑 bo/burst/tb：tb 持有入边 burst.last_bo→tb(TemporalEdge)。
    bo 无边(孤立 role)→ rel 空。burst 无入边(源)→ rel 空。"""
    from path2.dag.diagnose import diagnose
    df, params = positive_case()
    spec = build_pattern(params)
    diag = diagnose(spec, df, params)
    # tb 有入边 burst→tb(TemporalEdge)
    tb = diag.roles["tb"]
    assert ("burst", "TemporalEdge") in {(r.src, r.kind) for r in tb.rel}
    for r in tb.rel:
        assert r.total_src >= 0
        assert len(r.ok_src) <= r.total_src               # 合规子集
    # burst 是源(无入边)→ rel 空
    assert diag.roles["burst"].rel == ()
    # bo 是孤立 role(无边)→ rel 空
    assert diag.roles["bo"].rel == ()


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
    for r in diag.roles["tb"].rel:
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
    """诊断的 note 明示局部性;且 attr/rel 解耦——不因"某 role 全过"就断言整体可命中。"""
    from path2.dag.diagnose import diagnose
    df, params = positive_case()
    spec = build_pattern(params)
    diag = diagnose(spec, df, params)
    assert "局部" in diag.note                       # 明示边界
    # 解耦性:RoleDiagnostic 不含任何"全局是否成解"字段
    rd = diag.roles["bo"]
    assert not hasattr(rd, "global_match")
    assert set(vars(rd).keys()) == {"node_id", "attr", "rel"}


def test_diagnose_exported_from_package():
    import path2.dag as dag
    assert hasattr(dag, "diagnose")
    assert hasattr(dag, "RoleDiagnostics")
    assert hasattr(dag, "ClauseWitness")
