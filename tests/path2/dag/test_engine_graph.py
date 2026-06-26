# tests/path2/dag/test_engine_graph.py
"""图骨架纯函数:拓扑序(确定性)、弱连通分量、子图投影。"""
import pytest
from path2.dag.edges import TemporalEdge, NegationEdge
from path2.dag._graph import pos_preds, neg_out, topo_order, wccs, detector_topo_order


def test_topo_order_chain_deterministic():
    # A->B->C 链:拓扑序唯一且确定(同序破平按 node_id 排序)
    edges = [TemporalEdge("A", "B"), TemporalEdge("B", "C")]
    assert topo_order({"A", "B", "C"}, edges) == ["A", "B", "C"]


def test_topo_order_tiebreak_sorted():
    # 两个源 B,A 都无前驱 -> 按 node_id 字典序 A 先(确定性,非哈希序)
    edges = [TemporalEdge("A", "C"), TemporalEdge("B", "C")]
    order = topo_order({"A", "B", "C"}, edges)
    assert order.index("A") < order.index("C")
    assert order.index("B") < order.index("C")
    assert order[:2] == ["A", "B"]  # 源按字典序


def test_topo_order_cycle_raises():
    edges = [TemporalEdge("A", "B"), TemporalEdge("B", "A")]
    with pytest.raises(ValueError, match="cycle|环"):
        topo_order({"A", "B"}, edges)


def test_isolated_node_in_order():
    # 无边的孤立节点(单节点 pattern)也须在拓扑序里
    assert topo_order({"A"}, []) == ["A"]


def test_pos_preds_excludes_negation():
    # 正向前驱表只含正向边;否定边不进 pos_preds
    edges = [TemporalEdge("A", "B"), NegationEdge("A", "X")]
    pp = pos_preds({"A", "B", "X"}, edges)
    assert pp["B"] == [("A", edges[0])]
    assert pp["X"] == []          # X 的入边是否定边 -> 不在 pos_preds
    assert pp["A"] == []


def test_neg_out_groups_by_src():
    neg = NegationEdge("A", "X")
    edges = [TemporalEdge("A", "B"), neg]
    no = neg_out(edges)
    assert no["A"] == [neg]
    assert "B" not in no or no["B"] == []


def test_wccs_splits_disconnected():
    edges = [TemporalEdge("A", "B"), TemporalEdge("C", "D")]
    comps = wccs({"A", "B", "C", "D"}, edges)
    comps_sorted = sorted([sorted(c) for c in comps])
    assert comps_sorted == [["A", "B"], ["C", "D"]]


def test_detector_topo_order_respects_consumes_stream():
    # tb 消费 bo 流 -> bo 必须先跑
    from path2.dag.nodes import NodeSpec
    bo = NodeSpec(node_id="bo", detector=object())
    tb = NodeSpec(node_id="tb", detector=object(), consumes_stream="bo")
    order = detector_topo_order((tb, bo))      # 故意乱序输入
    assert order.index("bo") < order.index("tb")
