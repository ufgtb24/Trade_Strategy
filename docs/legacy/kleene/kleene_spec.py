"""Archived: Kleene 区间绑定 spec(2026-06 归档)。

来源:原 path2/dag/nodes.py。
归档原因 + 算法核心 + 复活路径见 README.md。

约束:本文件不可被任何活跃代码 import;只作为算法存档供未来参考。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple
import math

from path2.core import Event   # 仅允许的 import


@dataclass(frozen=True)
class KleeneSpec:
    """Kleene 闭包:节点绑【一串】同类事件(区间绑定,非单实例 +1)。
    引擎从流取一个连续子序列,整段满足 aggregate_where,作为单个绑定单元参与外层 DAG。

    min_count/max_count: 闭包基数下/上界(② MIN_BOS = min_count)。
    span_from_first:     成簇连续性 —— 成员对【段首】的绝对跨度窗(committed detectors.py:75
                         真实判据 = bo.start − first.start <= max_span,锚段首非相邻对)。
                         形如 (0, max_span);引擎接纳成员 e 须 e.start − seq[0].start ∈ 此区间。
    aggregate_where:     【整串】聚合谓词(② len>=N / ⑤ distinct_pk / ⑥ any vol)。
    endpoint_for_edges:  外层边连本 Kleene 节点时用哪个端点参与 satisfies:
                         'first'=④①(锚串首);'last'=⑦(锚串尾)。
    greedy:              贪心极大段(默认),对标 MATCH_RECOGNIZE greedy 量词。
    """
    min_count: int = 1
    max_count: float = math.inf
    span_from_first: Optional[Tuple[int, float]] = None
    aggregate_where: Tuple[Tuple[str, Callable[[Tuple, "MatchContext"], bool]], ...] = ()
    endpoint_for_edges: str = "first"
    greedy: bool = True
