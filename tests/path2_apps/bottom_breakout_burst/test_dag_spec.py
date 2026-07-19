"""bottom_breakout_burst dag 声明结构测试。"""
from path2.dag.edges import TemporalEdge
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback import ThrowbackDetector
from path2_apps.bottom_breakout_burst.dag_spec import build_pattern
from path2_apps.bottom_breakout_burst.params import Params


def _spec():
    return build_pattern(Params.default())


def test_dag_spec_three_nodes_bo_node_burst_consumes():
    """dag 含 3 nodes：bo/burst/tb；burst consumes bo 流，tb 仍 consumes bo。"""
    from path2_apps.bottom_breakout_burst.dag_spec import PATTERN_DAG
    ids = {n.node_id for n in PATTERN_DAG.nodes}
    assert ids == {"bo", "burst", "tb"}
    by = {n.node_id: n for n in PATTERN_DAG.nodes}
    assert by["burst"].consumes_stream == "bo"          # burst consumes bo 流
    assert by["tb"].consumes_stream == "bo"             # tb 仍 consumes bo(ThrowbackDetector 吃 BOEvent)
    # bo 无边 = 孤立 node(残缺 match 由 analyze 出口过滤)
    endpoints = {ep for e in PATTERN_DAG.edges for ep in (e.src, e.dst)}
    assert "bo" not in endpoints


def test_nodes_present_and_typed():
    """3 nodes(bo/burst/tb)，各 detector 类型和 class_id 验证。"""
    spec = _spec()
    by = {n.node_id: n for n in spec.nodes}
    assert set(by) == {"bo", "burst", "tb"}
    assert by["bo"].detector.event_cls.class_id == "bo"
    assert by["burst"].detector.event_cls.class_id == "burst"
    assert by["tb"].detector.event_cls.class_id == "tb"
    assert isinstance(by["bo"].detector, BODetector)
    assert isinstance(by["burst"].detector, BurstDetector)
    assert isinstance(by["tb"].detector, ThrowbackDetector)


def test_bo_is_plain_isolated_node():
    """bo 是孤立 plain node（无 where、无边）。"""
    bo = {n.node_id: n for n in _spec().nodes}["bo"]
    assert bo.where == ()                                  # 无 where（孤立 node）


def test_burst_node_structure():
    """burst consumes bo 流，where 包含三个条件(③⑤⑥)，vol_spike 字段为 max_bar_vol_ratio。"""
    burst = {n.node_id: n for n in _spec().nodes}["burst"]
    assert burst.consumes_stream == "bo"
    assert {cid for cid, _ in burst.where} == {"first_drought", "distinct_pk", "vol_spike"}  # ③⑤⑥
    # ⑥ 字段名已更新为 max_bar_vol_ratio
    vol_spike_pred = dict(burst.where)["vol_spike"]
    assert vol_spike_pred.meta["field"] == "max_bar_vol_ratio"
    assert isinstance(burst.detector, BurstDetector)


def test_tb_consumes_bo_stream():
    """ThrowbackDetector 吃 BOEvent，tb 仍 consumes bo 流（非 burst 流）。"""
    tb = {n.node_id: n for n in _spec().nodes}["tb"]
    assert tb.consumes_stream == "bo"


def test_edges_calibrated():
    """单边 burst.last_bo→tb：TemporalEdge + anchor_field="anchor_bo_id"。"""
    spec = _spec()
    assert len(spec.edges) == 1
    edge = spec.edges[0]
    assert isinstance(edge, TemporalEdge)
    assert edge.src_selector == "last_bo"              # ⑦ 锚末 bo
    assert edge.dst == "tb"
    assert edge.min_gap == 1
    assert edge.max_gap == Params.default().tb.max_start_gap
    assert edge.anchor_field == "anchor_bo_id"


def test_to_topology_three_nodes_one_edge():
    """topo 含 3 nodes，1 边 TemporalEdge(burst→tb)。"""
    topo = _spec().to_topology()
    assert {n.node_id for n in topo.nodes} == {"bo", "burst", "tb"}
    kinds = {(e.src, e.dst): e.kind for e in topo.edges}
    assert kinds == {("burst", "tb"): "TemporalEdge"}


def test_bo_node_declares_render_grid_price():
    """bo 节点声明 render_grid='price' (上 K线主图); 其余节点保持默认 'time'。
    PatternSpec 构造不报错 = 载入期校验 (point + price) 通过。"""
    spec = _spec()
    by = {n.node_id: n for n in spec.nodes}
    assert by["bo"].render_grid == "price"
    assert by["burst"].render_grid == "time"
    assert by["tb"].render_grid == "time"


import pickle
from path2_apps.bottom_breakout_burst.dag_spec import analyze
