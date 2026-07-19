"""PatternSpec 声明 + __post_init__ 校验(DAG 环/detector-DAG)+ to_topology + eq_src_nodes。"""
import pytest
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, ContainmentEdge, EqualsEdge
from path2.dag.spec import (
    PatternSpec, PatternTopology, TopoNode, TopoEdge,
)


class _FakeEventCls:
    class_id = "t"


class _Det:
    event_cls = _FakeEventCls
    def detect(self, source, df=None):
        return iter(())


def _node(nid, **kw):
    return NodeSpec(node_id=nid, detector=_Det(), **kw)


def _ok_spec(**overrides):
    nodes = (_node("down"), _node("bo"))
    edges = (TemporalEdge("down", "bo", min_gap=0, max_gap=120),)
    base = dict(pattern_id="p", nodes=nodes, edges=edges)
    base.update(overrides)
    return PatternSpec(**base)


def test_valid_spec_constructs():
    s = _ok_spec()
    assert s.pattern_id == "p"

def test_cycle_rejected():
    nodes = (_node("a"), _node("b"))
    edges = (TemporalEdge("a", "b"), TemporalEdge("b", "a"))   # 环
    with pytest.raises(ValueError):
        PatternSpec(pattern_id="p", nodes=nodes, edges=edges)

def test_edge_endpoint_must_be_declared_node():
    nodes = (_node("a"),)
    edges = (TemporalEdge("a", "ghost"),)                      # ghost 未声明
    with pytest.raises(ValueError):
        PatternSpec(pattern_id="p", nodes=nodes, edges=edges)

def test_detector_dag_consumes_stream_must_exist():
    nodes = (_node("tb", consumes_stream="ghost"),)           # 吃不存在的流
    with pytest.raises(ValueError):
        PatternSpec(pattern_id="p", nodes=nodes, edges=())

def test_duplicate_clause_id_in_node_where_rejected():
    """同 node 内 where 的 clause_id 重复 → fail-fast(否则 predicate_trace 后写覆盖前写,静默丢诊断)。"""
    dup = (("vol", lambda e, c: True), ("vol", lambda e, c: False))   # 同 node 两条 "vol"
    nodes = (_node("bo", where=dup),)
    with pytest.raises(ValueError, match="clause_id"):
        PatternSpec(pattern_id="p", nodes=nodes, edges=())

def test_duplicate_node_id_rejected():
    """重复 node_id → fail-fast。node_id 是拓扑主键:求解层 5 处 {node_id: NodeSpec} 字典
    后写覆盖前写(静默丢节点、丢 detector),而 to_topology 遍历 tuple 不去重 →
    求解层只认最后一个、面板层却显示全部,裂脑。故构造期即拒。"""
    nodes = (_node("down"), _node("down"))                    # 两个同名 node
    with pytest.raises(ValueError, match="node_id"):
        PatternSpec(pattern_id="p", nodes=nodes, edges=())

def test_shared_detector_distinct_node_ids_allowed():
    """不同 node_id 共享同一个 detector 对象(down/side 共享 trend_det = 共享一套 events)合法:
    唯一性校验只看 node_id,不波及 detector 复用 —— 否则会砸掉'多 node 共享生产者'的能力。"""
    det = _Det()                                          # 同一个 detector 对象
    nodes = (NodeSpec("down", det), NodeSpec("side", det))   # 不同 node_id 共享之
    edges = (TemporalEdge("down", "side"),)
    s = PatternSpec(pattern_id="p", nodes=nodes, edges=edges)
    assert s.pattern_id == "p"                            # 构造成功,不抛

def test_same_clause_id_across_nodes_allowed():
    """跨 node 复用同名 clause_id 合法(trace 外层按 node_id 分桶,无碰撞)。"""
    nodes = (
        _node("down", where=(("vol", lambda e, c: True),)),
        _node("bo",   where=(("vol", lambda e, c: True),)),  # 与 down 同名但不同 node
    )
    edges = (TemporalEdge("down", "bo"),)
    s = PatternSpec(pattern_id="p", nodes=nodes, edges=edges)
    assert s.pattern_id == "p"                                # 构造成功,不抛

def test_to_topology_zero_derivation():
    s = _ok_spec()
    topo = s.to_topology()
    assert isinstance(topo, PatternTopology)
    assert TopoNode("down", "t") in topo.nodes
    assert TopoNode("bo", "t") in topo.nodes
    assert TopoEdge("down", "bo", "TemporalEdge") in topo.edges  # 子类名即 kind

def test_eq_src_nodes():
    """EqualsEdge 的 src 节点集合(Phase 2 引擎据此关 C1)。"""
    nodes = (_node("a"), _node("b"), _node("d"))
    edges = (TemporalEdge("a", "b"), EqualsEdge("b", "d"))
    s = PatternSpec(pattern_id="p", nodes=nodes, edges=edges)
    assert s.eq_src_nodes() == frozenset({"b"})

def test_eq_src_nodes_empty_when_no_equals():
    assert _ok_spec().eq_src_nodes() == frozenset()


# ── render_grid × is_point 校验 (新增) ─────────────────────────────────

class _PointEventCls:
    """假 point 几何事件类"""
    class_id = "fakept"
    is_point = True

class _SpanEventCls:
    """假 span 几何事件类 (默认 is_point=False)"""
    class_id = "fakespan"

class _PointDet:
    event_cls = _PointEventCls
    def detect(self, source, df=None):
        return iter(())

class _SpanDet:
    event_cls = _SpanEventCls
    def detect(self, source, df=None):
        return iter(())


def test_render_grid_default_time_passes_for_span_detector():
    """默认 render_grid='time' 不触发 is_point 校验。"""
    nodes = (NodeSpec(node_id="x", detector=_SpanDet()),)
    PatternSpec(pattern_id="p", nodes=nodes, edges=())


def test_render_grid_price_passes_for_point_detector():
    """render_grid='price' + point 几何 → 通过。"""
    nodes = (NodeSpec(node_id="x", detector=_PointDet(), render_grid="price"),)
    PatternSpec(pattern_id="p", nodes=nodes, edges=())


def test_render_grid_price_rejects_span_detector():
    """render_grid='price' + span 几何 (is_point=False) → 抛 ValueError。"""
    nodes = (NodeSpec(node_id="x", detector=_SpanDet(), render_grid="price"),)
    with pytest.raises(ValueError, match="render_grid='price'"):
        PatternSpec(pattern_id="p", nodes=nodes, edges=())
