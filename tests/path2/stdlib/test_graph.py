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


def test_validate_neg_requires_forbid_and_later_in_forward():
    fwd = build_graph([TemporalEdge("A", "B")])
    validate_neg(fwd, forbid=[TemporalEdge("N", "A")])  # later=A 在正向
    with pytest.raises(ValueError, match="至少需"):
        validate_neg(fwd, forbid=[])
    with pytest.raises(ValueError, match="正向子图"):
        validate_neg(fwd, forbid=[TemporalEdge("N", "Z")])  # Z 不在正向
