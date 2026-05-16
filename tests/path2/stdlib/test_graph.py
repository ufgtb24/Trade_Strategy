import pytest

from path2.core import TemporalEdge
from path2.stdlib._graph import (
    build_graph,
    validate_chain,
    validate_dag,
    validate_kof,
    validate_neg,
    topo_order,
)


def test_build_graph_collects_nodes_and_adj():
    edges = [TemporalEdge("A", "B"), TemporalEdge("B", "C")]
    g = build_graph(edges)
    assert g.nodes == {"A", "B", "C"}
    assert g.indeg["A"] == 0 and g.indeg["C"] == 1
    assert g.outdeg["C"] == 0


def test_topo_order_linear():
    g = build_graph([TemporalEdge("A", "B"), TemporalEdge("B", "C")])
    assert topo_order(g) == ["A", "B", "C"]


def test_topo_order_diamond_deterministic_and_multiedge_safe():
    diamond = build_graph(
        [
            TemporalEdge("A", "B"),
            TemporalEdge("A", "C"),
            TemporalEdge("B", "D"),
            TemporalEdge("C", "D"),
        ]
    )
    assert topo_order(diamond) == ["A", "B", "C", "D"]
    multiedge = build_graph(
        [
            TemporalEdge("A", "B", min_gap=1),
            TemporalEdge("A", "B", min_gap=2),
            TemporalEdge("B", "C"),
        ]
    )
    assert topo_order(multiedge) == ["A", "B", "C"]


def test_validate_chain_ok():
    validate_chain(build_graph([TemporalEdge("A", "B"), TemporalEdge("B", "C")]))


def test_validate_chain_branching_raises():
    g = build_graph([TemporalEdge("A", "B"), TemporalEdge("A", "C")])
    with pytest.raises(ValueError, match="线性路径"):
        validate_chain(g)


def test_validate_chain_cycle_raises():
    g = build_graph([TemporalEdge("A", "B"), TemporalEdge("B", "A")])
    with pytest.raises(ValueError, match="环"):
        validate_chain(g)


def test_validate_dag_ok_multi_indegree():
    g = build_graph([TemporalEdge("A", "C"), TemporalEdge("B", "C")])
    validate_dag(g)


def test_validate_dag_cycle_raises():
    g = build_graph([TemporalEdge("A", "B"), TemporalEdge("B", "A")])
    with pytest.raises(ValueError, match="环"):
        validate_dag(g)


def test_validate_kof_k_range():
    edges = [TemporalEdge("A", "B"), TemporalEdge("B", "C")]
    validate_kof(build_graph(edges), k=1, n_edges=2)
    with pytest.raises(ValueError, match="k"):
        validate_kof(build_graph(edges), k=3, n_edges=2)
    with pytest.raises(ValueError, match="k"):
        validate_kof(build_graph(edges), k=0, n_edges=2)


def test_validate_kof_single_wcc_required():
    """redesign §10.7:Kof edges 必须弱连通(单 WCC),否则构造期 ValueError。

    跨 WCC 的 k-of-n 在逐 WCC 分解下无法统计且无明确表达意义。
    """
    # 单 WCC(A-B-C 弱连通):通过
    validate_kof(
        build_graph([TemporalEdge("A", "B"), TemporalEdge("B", "C")]),
        k=1, n_edges=2,
    )
    # 多 WCC(A→B 与 C→D 不连通):拒绝
    with pytest.raises(ValueError, match="连通"):
        validate_kof(
            build_graph([TemporalEdge("A", "B"), TemporalEdge("C", "D")]),
            k=1, n_edges=2,
        )


def test_validate_neg_requires_forbid_and_later_in_forward():
    fwd = build_graph([TemporalEdge("A", "B")])
    validate_neg(fwd, forbid=[TemporalEdge("N", "A")])  # later=A 在正向
    with pytest.raises(ValueError, match="至少需"):
        validate_neg(fwd, forbid=[])
    with pytest.raises(ValueError, match="正向子图"):
        validate_neg(fwd, forbid=[TemporalEdge("N", "Z")])  # Z 不在正向


def test_validate_dag_isolated_node_raises():
    """度为 0 的孤立节点(indeg==0 AND outdeg==0)应被 validate_dag 拒绝。

    build_graph 本身无法产生度-0 节点(每个节点均源自 edge 端点),
    因此直接构造 Graph 以测试防御性契约(design §3.0.1)。
    """
    from path2.stdlib._graph import Graph
    g = Graph(
        nodes={"A", "B", "iso"},
        adj={"A": [("B", TemporalEdge("A", "B"))], "B": [], "iso": []},
        indeg={"A": 0, "B": 1, "iso": 0},
        outdeg={"A": 1, "B": 0, "iso": 0},
        edges=[TemporalEdge("A", "B")],
    )
    with pytest.raises(ValueError, match="孤立节点"):
        validate_dag(g)


def test_validate_dag_multi_wcc_ok():
    """多弱连通分量(各节点度 >= 1 的不连通子 DAG)应合法。"""
    g = build_graph([TemporalEdge("A", "B"), TemporalEdge("C", "D")])
    validate_dag(g)  # 不应抛出
