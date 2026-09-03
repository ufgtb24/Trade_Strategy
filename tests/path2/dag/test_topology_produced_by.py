"""to_topology 子结构 node 的 produced_by 显示 + diagnose 提示。"""
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.atoms.throwback import ThrowbackSegment


class FakeDetector:
    event_cls = ThrowbackSegment


def test_topology_carries_produced_by():
    spec = PatternSpec(pattern_id="t", nodes=(
        NodeSpec("tb", FakeDetector(), children={"segments": "tb_seg"}),
        NodeSpec("tb_seg", event_cls=ThrowbackSegment),
    ), edges=())
    topo = spec.to_topology()
    tb_seg = next(n for n in topo.nodes if n.node_id == "tb_seg")
    assert tb_seg.produced_by == "tb"
    assert tb_seg.child_slot == "segments"   # 子结构 node 在父的槽名(children 反查)
    # TopoNode 零派生直投,node 身份全部以 node_id 为准(无类型维度)
    # 独立 node 的 child_slot 为 None
    tb = next(n for n in topo.nodes if n.node_id == "tb")
    assert tb.child_slot is None


def test_topology_parent_refs_covers_standalone_ref():
    """children 逆映射全量:独立 node 被容器引用(情况一)也进入 parent_refs。"""
    spec = PatternSpec(pattern_id="t", nodes=(
        NodeSpec("burst", FakeDetector(), children={"members": "bo"}),
        NodeSpec("bo", FakeDetector()),
    ), edges=())
    topo = spec.to_topology()
    bo = next(n for n in topo.nodes if n.node_id == "bo")
    assert bo.produced_by is None          # 独立 node 无物化来源(语义不变)
    assert bo.parent_refs == (("burst", "members"),)
    burst = next(n for n in topo.nodes if n.node_id == "burst")
    assert burst.parent_refs == ()         # 容器自身不被引用


def test_topology_parent_refs_multi_parent():
    """独立 node 可被多容器引用(多父合法)——parent_refs 收录全部。"""
    spec = PatternSpec(pattern_id="t", nodes=(
        NodeSpec("a", FakeDetector(), children={"x": "bo"}),
        NodeSpec("b", FakeDetector(), children={"y": "bo"}),
        NodeSpec("bo", FakeDetector()),
    ), edges=())
    topo = spec.to_topology()
    bo = next(n for n in topo.nodes if n.node_id == "bo")
    assert set(bo.parent_refs) == {("a", "x"), ("b", "y")}
