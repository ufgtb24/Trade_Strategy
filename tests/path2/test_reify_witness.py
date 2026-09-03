# tests/path2/test_reify_witness.py
"""ClauseWitness 自身 + reify 富化(Task 3 追加)。"""
from path2.dag.result import ClauseWitness
from tests.path2.fixtures.positive_case import positive_case


def test_clause_witness_bool_compat():
    cw = ClauseWitness(satisfied=True, measured=0.42, op=">=", threshold=0.30)
    assert bool(cw) is True                       # 向后兼容:if/assert where_results[..][..]
    assert cw.satisfied is True
    assert cw.measured == 0.42
    assert cw.op == ">=" and cw.threshold == 0.30


def test_reify_where_results_are_clause_witness():
    from path2_apps.bottom_burst import analyze
    df, params = positive_case()
    res = analyze(df, params)
    assert len(res.matches) >= 1, "fixture 应至少命中 1 次"
    m = res.matches[0]
    wr = m.predicate_trace.where_results
    # burst 节点的 vol_spike clause 是富化的 ClauseWitness(带实测值/阈值),且 bool 兼容
    burst_cw = wr["burst"]["vol_spike"]
    assert isinstance(burst_cw, ClauseWitness)
    assert bool(burst_cw) is True                       # 命中 ⇒ satisfied
    assert burst_cw.op == ">=" and burst_cw.threshold is not None
    assert isinstance(burst_cw.measured, (int, float))  # 实测 vol 比值数值


def test_reify_includes_burst_where():
    """B4 迁移后：③⑤⑥ 条件移入 burst node where。"""
    from path2_apps.bottom_burst import analyze
    df, params = positive_case()
    m = analyze(df, params).matches[0]
    burst_clauses = m.predicate_trace.where_results["burst"]
    # ③ first_drought + ⑤ distinct_pk + ⑥ vol_spike 都在 burst 的 where_results
    assert "first_drought" in burst_clauses
    assert "distinct_pk" in burst_clauses
    assert "vol_spike" in burst_clauses
    assert bool(burst_clauses["distinct_pk"]) is True     # 命中 ⇒ 谓词满足
    assert bool(burst_clauses["vol_spike"]) is True       # 命中 ⇒ 谓词满足
