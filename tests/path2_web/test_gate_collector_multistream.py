"""gate_collector 路由表:(detector, 流名) → node_id(spec §4.5(b)-(e))。

- 单流路径:gf.stream 恒 None + node.produces_stream 恒 None → 路由表 == {None:[node]},
  与旧 per-node wrapper 逐字等价。
- 多流:同 detector 产多条命名流,各归各 node(gf.stream 决定归属)。
- 未绑流:挂 collector 时(诊断路径)声明但未被任何 node 绑定的流 → attach 即报错,不静默丢 gf。
"""
import types
from dataclasses import dataclass

import pytest

from path2.core import Event
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2_web.gate_collector import GateCollector, attach_and_collect, detach


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


def _gf(stream=None):
    return GateFailure(
        failure_event_window=(0, 0), start_idx=0, gate_idx=0, anchor_bar=0,
        gate_name="g", measured=MeasuredKindAware(kind="count", value=1, label="x"),
        threshold=1, op=None, threshold_param=None, evaluation_lookback=None,
        symbol="TEST", stream=stream)


def test_single_flow_node_id_injected():
    class S:
        event_cls = _E
        def detect(self, source): ...
    det = S()
    spec = PatternSpec("p", edges=(), nodes=[NodeSpec("bo", det)])
    collector = attach_and_collect(spec)
    det.on_gate(_gf())                       # 单流 gf.stream=None
    detach(spec)
    assert [f.node_id for f in collector.snapshot()] == ["bo"]


def test_multi_flow_routes_by_stream():
    class D:
        produces = {"bo": _E, "pk": _E}
        def __init__(self): self.on_gate = None
        def detect(self, source): ...
    det = D()
    spec = PatternSpec("p", edges=(), nodes=[
        NodeSpec("bo", det, produces_stream="bo"),
        NodeSpec("pk", det, produces_stream="pk"),
    ])
    collector = attach_and_collect(spec)
    det.on_gate(_gf(stream="pk"))            # ★ pk 流的 gate → pk node
    det.on_gate(_gf(stream="bo"))            # bo 流的 gate → bo node
    detach(spec)
    assert [f.node_id for f in collector.snapshot()] == ["pk", "bo"]
    assert collector.snapshot()[0].stream == "pk"


def test_unbound_stream_attach_raises():
    # PatternSpec 现在构造期就拒(Task 3 全绑定校验,契约 C3),测不到 attach_and_collect
    # 的兜底检查——改用 types.SimpleNamespace 伪 spec 绕过 PatternSpec 校验,直接喂
    # attach_and_collect,保住 collector 兜底检查的覆盖。
    class D:
        produces = {"bo": _E, "pk": _E}
        def detect(self, source): ...
    det = D()
    spec = types.SimpleNamespace(nodes=[NodeSpec("bo", det, produces_stream="bo")])
    with pytest.raises(ValueError, match="pk"):
        attach_and_collect(spec)             # pk 声明了但无 node 绑定 + 挂 collector → 报错
    detach(spec)


def test_bo_pk_shared_detector_peak_gates_route_to_pk_node():
    """4c(契约 C6):真 BODetector + bb_pk 拓扑(bo/pk 共享同一 detector)——峰类 gate
    (stream="pk")经 attach_and_collect 路由到 pk node,no_active_peak_broken 归 bo node。
    fixture 复用 test_bo_on_gate.py 的单调下跌 df(无 peak)。"""
    import pandas as pd
    from path2_apps.bb_pk.dag_spec import build_pattern
    from path2_apps.bb_pk.params import Params

    n = 50
    df = pd.DataFrame({
        'open': [100 - i for i in range(n)],
        'close': [100 - i - 0.5 for i in range(n)],
        'high': [100 - i + 0.5 for i in range(n)],
        'low': [100 - i - 1 for i in range(n)],
        'volume': [1000.0] * n,
    })
    spec = build_pattern(Params.default())
    collector = attach_and_collect(spec)
    bo_node = next(node for node in spec.nodes if node.node_id == "bo")
    list(bo_node.detector.detect(df))
    detach(spec)
    gates = collector.snapshot()
    peak_gates = [g for g in gates if g.gate_name.startswith("peak_")]
    napb_gates = [g for g in gates if g.gate_name == "no_active_peak_broken"]
    assert peak_gates, "单调下跌应触发 peak_* gate"
    assert napb_gates, "单调下跌无 active peak,应触发 no_active_peak_broken"
    assert all(g.node_id == "pk" for g in peak_gates)
    assert all(g.node_id == "bo" for g in napb_gates)
