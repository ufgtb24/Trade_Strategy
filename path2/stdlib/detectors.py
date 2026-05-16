"""四个标准 PatternDetector 公开类(design §4)。

流在构造期绑定;detect(source=None) 忽略 source,由 run(detector) 驱动。
只实现各 Detector 的 design 默认锚定;非默认 anchoring -> ValueError。
"""
from __future__ import annotations

from typing import Callable, Iterator, Optional

from path2.core import Event
from path2.stdlib._advance import advance_dag, advance_kof
from path2.stdlib._graph import build_graph, validate_chain, validate_dag, validate_kof
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
                f"Chain 仅支持默认 anchoring='earliest-feasible', "
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


class Dag:
    """任意 DAG(多入度多出度、多 WCC 合法)。复用 LEF-DFS 核心(advance_dag),逐 WCC 独立 + p 路 end_idx 归并;诚实复杂度见 redesign §5(Chain f=1 近线性,病态宽前沿 DAG 时间空间同指数)。"""

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
                f"Dag 仅支持默认 anchoring='earliest-feasible', "
                f"收到 {anchoring!r}"
            )

        self._edges = list(edges)
        self._label = label or "dag"

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
        validate_dag(self._graph)
        self._streams = resolve_labels(
            positional=positional_streams,
            named=named_streams,
            key=key,
            strict_key=strict_key,
            endpoint_labels=_endpoint_labels(self._edges),
        )

    def detect(self, source=None) -> Iterator[PatternMatch]:
        yield from advance_dag(self._graph, self._streams, self._label)


class Kof:
    """k-of-n 边松弛 Detector(redesign §3.3/§5)。

    n = edges 条数,k = 至少须满足的边数;满足 = 两端均有实例且 gap 在
    [min_gap, max_gap] 内。算法为滑窗计数,复杂度 O(ΣN·n)。与 Chain/Dag
    不同:Kof 不要求所有 edge 同时满足,只要 >= k 条满足即命中。

    锚定语义:非重叠贪心(`non-overlapping-greedy`,唯一支持值)。
    """

    def __init__(
        self,
        *positional_streams,
        edges,
        k: int,
        key=None,
        strict_key: bool = False,
        label: Optional[str] = None,
        anchoring: str = "non-overlapping-greedy",
        **named_streams,
    ):
        # anchoring 非默认值 → 拒绝
        if anchoring != "non-overlapping-greedy":
            raise ValueError(
                f"Kof 仅支持默认 anchoring='non-overlapping-greedy',"
                f"收到 {anchoring!r}"
            )

        self._edges = list(edges)
        self._k = k
        self._label = label or "kof"

        # redesign §7:pattern_label 不得含 '#'(event_id 消歧分隔符)
        if "#" in self._label:
            raise ValueError(
                f"pattern_label 不得含 '#'(它是 event_id 消歧分隔符):{self._label!r}"
            )

        # key 与具名流(kwarg)互斥
        if key is not None and named_streams:
            raise ValueError(
                "key 与具名流(kwarg)不可同时使用:"
                "二者是互斥的标签解析机制(redesign §1.2 三段解析优先级)"
            )

        self._graph = build_graph(self._edges)
        validate_kof(self._graph, k=k, n_edges=len(self._edges))
        self._streams = resolve_labels(
            positional=positional_streams,
            named=named_streams,
            key=key,
            strict_key=strict_key,
            endpoint_labels=_endpoint_labels(self._edges),
        )

    def detect(self, source=None) -> Iterator[PatternMatch]:
        yield from advance_kof(
            self._graph, self._streams, self._edges, self._k, self._label
        )
