"""四个标准 PatternDetector 公开类(design §4)。

流在构造期绑定;detect(source=None) 忽略 source,由 run(detector) 驱动。
只实现各 Detector 的 design 默认锚定;非默认 anchoring -> ValueError。
"""
from __future__ import annotations

from typing import Callable, Iterator, Optional

from path2.core import Event, TemporalEdge
from path2.stdlib._advance import advance_dag
from path2.stdlib._graph import build_graph, validate_chain
from path2.stdlib._labels import resolve_labels
from path2.stdlib.pattern_match import PatternMatch


def _endpoint_labels(edges, forbid=()):
    """从 edges(+ 可选 forbid)中提取所有端点标签集合。"""
    s = set()
    for e in list(edges) + list(forbid):
        s.add(e.earlier)
        s.add(e.later)
    return s


class Chain:
    """线性链 a→b→c。复用 LEF-DFS 核心(advance_dag);validate_chain 强制 p=1 ⇒ f=1 ⇒ 多项式/近线性(redesign §5/§6)。"""

    def __init__(
        self,
        *positional_streams,
        edges,
        key: Optional[Callable[[Event], str]] = None,
        strict_key: bool = False,
        label: Optional[str] = None,
        anchoring: str = "earliest-feasible",
        **named_streams,
    ):
        # anchoring 非默认值 → 拒绝
        if anchoring != "earliest-feasible":
            raise ValueError(
                f"Chain 仅支持默认 anchoring='earliest-feasible',"
                f"收到 {anchoring!r}"
            )

        self._edges = list(edges)
        self._label = label or "chain"

        # redesign §7:pattern_label 不得含 '#'(event_id 消歧分隔符)
        if "#" in self._label:
            raise ValueError(
                f"pattern_label 不得含 '#'(它是 event_id 消歧分隔符):{self._label!r}"
            )

        # key 与具名流(kwarg)互斥(carried-forward Task 3 review footgun)
        if key is not None and named_streams:
            raise ValueError(
                "key 与具名流(kwarg)不可同时使用:"
                "二者是互斥的标签解析机制(redesign §1.2 三段解析优先级)"
            )

        self._graph = build_graph(self._edges)
        validate_chain(self._graph)
        self._streams = resolve_labels(
            positional=positional_streams,
            named=named_streams,
            key=key,
            strict_key=strict_key,
            endpoint_labels=_endpoint_labels(self._edges),
        )

    def detect(self, source=None) -> Iterator[PatternMatch]:
        yield from advance_dag(self._graph, self._streams, self._label)
