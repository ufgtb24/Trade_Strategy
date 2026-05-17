"""四个标准 PatternDetector 公开类(design §4)。

流在构造期绑定;detect(source=None) 忽略 source,由 run(detector) 驱动。
只实现各 Detector 的 design 默认锚定;非默认 anchoring -> ValueError。
"""
from __future__ import annotations

from typing import Callable, Iterator, Optional

from path2.core import Event
from path2.stdlib._advance import advance_dag, advance_kof, advance_neg
from path2.stdlib._graph import build_graph, validate_chain, validate_dag, validate_kof, validate_neg
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
    """k-of-n 边松弛 Detector —— **LEF-DFS 结构姊妹**(redesign §10,权威)。

    n = edges 条数,k = 至少须满足的边数。与 Chain/Dag 不同:Kof 不要求
    所有 edge 同时满足,只要 >= k 条满足即命中(但**全标签必在场**,
    no partial)。算法 = 成员组合枚举/回溯 + 叶层 k-of-n 接受 + 全成员
    非重叠消费;复用 LEF-DFS 的 key 序 / WCC / `#seq` 框架(`_kof_dfs`
    独立,不改 `_lef_dfs`)。

    缓冲(诚实账,redesign §10.6):单 WCC 零 / 多 WCC ≤(p−1)(与 Dag
    同);`validate_kof` 强制单 WCC ⇒ 常态零缓冲;产出天然 end_idx 升序。
    时间标签数维度**诚实指数**(松弛无窗口剪枝,内在不可消除,**常态**
    非仅病态)。

    锚定语义:`non-overlapping-greedy`(唯一支持值,冻结面)。"greedy"
    指**生产循环按全成员非重叠贪进**;**成员选择是枚举/回溯**,非贪心
    单选。
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


class Neg:
    """正向子图 + forbid 谓词过滤 Detector(redesign §11,权威)。

    语义:在正向 edges 上跑 LEF-DFS(advance_dag),对每个正向匹配 m,
    评估每条 forbid 边:若否定标签流中存在落在 [min_gap, max_gap] 窗口
    内的事件则否决(多条 forbid 合取);未被任一否决则产出 m。

    端点角色识别 = 成员资格(与 earlier/later 声明方向无关,§11.1):
      - forbid 边上 ∈ forward.nodes 的端点 = 正向锚(anchor)
      - ∉ 的端点 = 否定标签(neg)
    两端皆∈ / 两端皆∉ → 构造期 validate_neg ValueError。

    gap 按 forbid 边声明方向原样代入 spec §1.3.1(§11.2):
      - anchor=earlier(forbid(A→N)):gap = e_n.start − e_anchor.end
      - anchor=later(never_before forbid(N→A)):gap = e_anchor.start − e_n.end

    N 不进 children/role_index:结构性保证(N 不在正向 edges,LEF-DFS
    定义域不含 N,_emit 输出不含 N;advance_neg 对 N 仅只读)。

    缓冲继承正向:Chain 正向 ⇒ 零缓冲;Dag(多 WCC)正向 ⇒ ≤(p−1)(§11.5)。

    已知边界(诚实,§11.6):
      - 否定流须以 kwarg 显式传入(可空 `N=[]`);漏传 ⇒ 构造期 missing 报错。
      - never_before min_gap=0 含 gap=0;想严格之前用 min_gap=1。
      - 同名复用一律拒绝(validate_neg):同标签不可既是正向成员又是否定条件。
    """

    def __init__(
        self,
        *positional_streams,
        edges,
        forbid,
        key: Optional[Callable[[Event], str]] = None,
        strict_key: bool = False,
        label: Optional[str] = None,
        anchoring: str = "earliest-feasible",
        **named_streams,
    ):
        # Guard 1:anchoring 非默认值 → 拒绝
        if anchoring != "earliest-feasible":
            raise ValueError(
                f"Neg 仅支持默认 anchoring='earliest-feasible', "
                f"收到 {anchoring!r}"
            )

        self._edges = list(edges)
        self._forbid = list(forbid)
        self._label = label or "neg"

        # Guard 2:pattern_label 不得含 '#'(event_id 消歧分隔符,redesign §7)
        if "#" in self._label:
            raise ValueError(
                f"pattern_label 不得含 '#'(它是 event_id 消歧分隔符):{self._label!r}"
            )

        # Guard 3:key 与具名流(kwarg)互斥(BEFORE resolve_labels)
        if key is not None and named_streams:
            raise ValueError(
                "key 与具名流(kwarg)不可同时使用:"
                "二者是互斥的标签解析机制(redesign §1.2 三段解析优先级)"
            )

        self._graph = build_graph(self._edges)
        validate_dag(self._graph)
        validate_neg(self._graph, self._forbid)
        self._streams = resolve_labels(
            positional=positional_streams,
            named=named_streams,
            key=key,
            strict_key=strict_key,
            endpoint_labels=_endpoint_labels(self._edges, self._forbid),
        )

    def detect(self, source=None) -> Iterator[PatternMatch]:
        yield from advance_neg(
            self._graph, self._streams, self._forbid, self._label
        )
