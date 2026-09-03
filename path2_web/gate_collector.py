"""GateFailure buffer · worker 处理某 symbol 时挂到 spec 里各 detector 的 on_gate · 结束时收进 result。

承 spec §3.2.2 · Sprint 2 入口 A(scope=time)数据源:三 atom(BurstDetector/BODetector/
ThrowbackDetector,Task 10-12)detect() 内部短路失败时调 self.on_gate(GateFailure(...))
(默认 on_gate=None,生产路径零开销)。worker(scan.py/eval_runner.py)在跑 analyze 前用
attach_and_collect(spec) 把 collector.add 接到 spec.nodes 每个 node.detector.on_gate 上,
跑完立即 detach(spec) 重置回 None,避免同 worker 进程(ProcessPoolExecutor 复用)下一个
symbol/pattern 串扰。

PatternSpec 无 spec.detectors 属性 —— detector 挂在 NodeSpec.detector 上,故按
spec.nodes 遍历取。attach_and_collect 把 (detector, 流名) → node_id 建成路由表,收到
GateFailure 按 gf.stream 路由注入 node_id 再进 collector(spec §4.5(b))。挂雷收窄为
「同一条流被 ≥2 node 绑定」:绑同一 detector 的不同流归属明确、合法放行;同一流绑多
node 首条 gf 到达即报错。声明但未被任何 node 绑定的流 → PatternSpec 构造期已校验
(契约 C3);此处保留作兜底(伪 spec / 测试路径)。单流路径(gf.stream 恒 None +
produces_stream 恒 None)与旧 per-node wrapper 逐字等价,零行为变化。
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Tuple

from path2 import config
from path2.dag.gate_failure import GateFailure


class GateCollector:
    """单次 analyze() 调用期间的 GateFailure 累积 buffer。"""

    def __init__(self):
        self._buf: list = []

    def add(self, gf: GateFailure) -> None:
        self._buf.append(gf)

    def snapshot(self) -> Tuple[GateFailure, ...]:
        return tuple(self._buf)

    def clear(self) -> None:
        self._buf.clear()


def attach_and_collect(spec) -> GateCollector:
    """遍历 spec.nodes,给每个 detector 挂 per-call wrapper:收到 GateFailure 后按
    (detector, 流名) 路由表注入 node_id 再进 collector。单流路径与旧 per-node wrapper 逐字相同。

    挂雷收窄为「同一条流被 ≥2 node 绑定」(原「同一 detector 被 ≥2 node 引用」)。
    声明但未被任何 node 绑定的流 → PatternSpec 构造期已校验(契约 C3);此处保留
    作兜底(伪 spec / 测试路径),防「gf 无处归属」静默丢失。"""
    from path2.core import stream_schema
    collector = GateCollector()
    routes: dict[int, dict[Optional[str], list[str]]] = {}
    first_det: dict[int, object] = {}
    for node in spec.nodes:
        if node.detector is None:
            continue
        det_id = id(node.detector)
        first_det.setdefault(det_id, node.detector)
        routes.setdefault(det_id, {}).setdefault(
            getattr(node, "produces_stream", None), []).append(node.node_id)
    for det_id, by_stream in routes.items():
        try:
            schema = stream_schema(first_det[det_id])
        except ValueError:
            # 仅测试假 spec(无 event_cls/produces 的裸 detector)会走到;真 spec 的
            # NodeSpec.__post_init__ 已校验 schema 可反射,到不了这里。
            schema = {}
        unbound = set(schema) - set(by_stream)
        if unbound:
            raise ValueError(
                f"detector 声明流未被任何 node 绑定,其 gate failure 将无处归属:"
                f"{sorted(unbound)};请为它建 node 或改用不产 gf 的配置")
    def make_route(det_id):
        def _route(gf: GateFailure) -> None:
            nids = routes[det_id].get(gf.stream)
            if not nids:
                if config.RUNTIME_CHECKS:
                    raise ValueError(f"gate failure 流 {gf.stream!r} 无绑定 node")
                return
            if len(nids) > 1:
                raise RuntimeError(
                    f"流 {gf.stream!r} 被 {len(nids)} 个 node 绑定,gate failure 归属无真值;"
                    f"产 gate failure 的 detector 须一 node 一实例,请每流一 node")
            collector.add(dataclasses.replace(gf, node_id=nids[0]))
        return _route
    seen: set[int] = set()
    for node in spec.nodes:
        if node.detector is None:
            continue
        det_id = id(node.detector)
        if det_id not in seen:
            seen.add(det_id)
            node.detector.on_gate = make_route(det_id)
    return collector


def detach(spec) -> None:
    """跑完 analyze 后清空 on_gate(= None),回到生产路径零开销默认值。"""
    for node in spec.nodes:
        if node.detector is None:
            continue
        node.detector.on_gate = None
