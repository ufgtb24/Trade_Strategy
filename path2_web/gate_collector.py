"""GateFailure buffer · worker 处理某 symbol 时挂到 spec 里各 detector 的 on_gate · 结束时收进 result。

承 spec §3.2.2 · Sprint 2 入口 A(scope=time)数据源:三 atom(BurstDetector/BODetector/
ThrowbackDetector,Task 10-12)detect() 内部短路失败时调 self.on_gate(GateFailure(...))
(默认 on_gate=None,生产路径零开销)。worker(scan.py/eval_runner.py)在跑 analyze 前用
attach_and_collect(spec) 把 collector.add 接到 spec.nodes 每个 node.detector.on_gate 上,
跑完立即 detach(spec) 重置回 None,避免同 worker 进程(ProcessPoolExecutor 复用)下一个
symbol/pattern 串扰。

PatternSpec 无 spec.detectors 属性 —— detector 挂在 NodeSpec.detector 上,故按
spec.nodes 遍历取。同一 detector 对象可能被多个 node 共享(如同 detector 消费同一流的
多角色场景),重复赋值同一 collector.add 天然幂等。
"""
from __future__ import annotations

from typing import Tuple

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
    """遍历 spec.nodes,把每个 node.detector.on_gate 接到新建 collector.add。返回该 collector。"""
    collector = GateCollector()
    for node in spec.nodes:
        node.detector.on_gate = collector.add
    return collector


def detach(spec) -> None:
    """跑完 analyze 后清空 on_gate(= None),回到生产路径零开销默认值。"""
    for node in spec.nodes:
        node.detector.on_gate = None
