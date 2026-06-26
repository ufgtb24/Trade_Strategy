"""声明容器 PatternSpec + 面板投影 to_topology + 校验。

app 声明的全部 = nodes(NodeSpec) + edges(DependencyEdge 子类) + root。
nodes/edges 即类型级 DAG,to_topology() 零派生直投(对比旧 build_topology 反推)。
__post_init__ 做三类校验:DAG(环/端点)、detector-DAG(consumes_stream)、where(clause_id 同 node 内唯一)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Tuple

from path2.dag.edges import DependencyEdge, EqualsEdge
from path2.dag.nodes import NodeSpec


@dataclass(frozen=True)
class TopoNode:
    node_id: str
    class_id: str
    label: str = ""


@dataclass(frozen=True)
class TopoEdge:
    src: str
    dst: str
    kind: str         # 边子类名(TemporalEdge/ContainmentEdge/...),面板按此分流渲染


@dataclass(frozen=True)
class PatternTopology:
    """面板的类型级数据源:节点 + 类型化有向边。"""
    nodes: Tuple[TopoNode, ...]
    edges: Tuple[TopoEdge, ...]


@dataclass(frozen=True)
class PatternSpec:
    """app 声明的全部。nodes/edges 即类型级 DAG(面板直接吃,零派生)。"""
    pattern_id: str
    display_name: str
    nodes: Tuple[NodeSpec, ...]
    edges: Tuple[DependencyEdge, ...]
    root: str
    event_styles: Mapping[str, object] = field(default_factory=dict)
    stock_list_columns: Tuple[object, ...] = ()

    def __post_init__(self) -> None:
        self._validate_node_ids()        # 必先于下列校验:它们都用去重后的 _node_ids() set,会掩盖重复
        self._validate_dag()
        self._validate_detector_dag()
        self._validate_where_clauses()
        self._validate_anchor()   # ★ 整改四新增
        self._validate_render_grid()   # ★ 新增:render_grid='price' 需 event_cls.is_point=True

    # ── 校验 ──
    def _node_ids(self) -> set:
        return {n.node_id for n in self.nodes}

    def _validate_node_ids(self) -> None:
        """node_id 是拓扑主键,须全局唯一 —— 否则求解层 5 处 {node_id: NodeSpec} 字典后写覆盖
        前写(静默丢节点/detector),而 to_topology 遍历 tuple 不去重 → 求解层与面板层裂脑。"""
        ids = [n.node_id for n in self.nodes]
        if len(set(ids)) != len(ids):
            dups = sorted({x for x in ids if ids.count(x) > 1})
            raise ValueError(f"node_id 重复: {dups}(拓扑主键须唯一)")

    def _validate_dag(self) -> None:
        ids = self._node_ids()
        if self.root not in ids:
            raise ValueError(f"root={self.root!r} 不是已声明 node")
        for e in self.edges:
            if e.src not in ids:
                raise ValueError(f"edge src={e.src!r} 不是已声明 node")
            if e.dst not in ids:
                raise ValueError(f"edge dst={e.dst!r} 不是已声明 node")
        if self._has_cycle(ids):
            raise ValueError("edges 检测到环,拓扑非 DAG")

    def _has_cycle(self, ids: set) -> bool:
        """Kahn 拓扑削平:削不平则有环。"""
        indeg = {n: 0 for n in ids}
        adj: dict = {n: [] for n in ids}
        for e in self.edges:
            adj[e.src].append(e.dst)
            indeg[e.dst] += 1
        q = [n for n in ids if indeg[n] == 0]
        seen = 0
        while q:
            u = q.pop()
            seen += 1
            for v in adj[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        return seen != len(ids)

    def _validate_detector_dag(self) -> None:
        ids = self._node_ids()
        for n in self.nodes:
            if n.consumes_stream is not None and n.consumes_stream not in ids:
                raise ValueError(
                    f"{n.node_id}: consumes_stream={n.consumes_stream!r} 不是已声明 node"
                )

    def _validate_where_clauses(self) -> None:
        """同 node 内 where 的 clause_id 须唯一 —— clause_id 唯一用途是 predicate_trace 的 key,
        重复会在 reify 的 {cid: ...} 字典推导里后写覆盖前写,静默丢一条诊断(匹配不受影响)。
        跨 node 复用同名 clause_id 合法(trace 外层按 node_id 分桶)。"""
        for n in self.nodes:
            seen = set()
            for cid, _ in n.where:
                if cid in seen:
                    raise ValueError(f"{n.node_id}: where clause_id={cid!r} 重复(同 node 内须唯一)")
                seen.add(cid)

    def _validate_anchor(self) -> None:
        """整改四:校验 anchor_field / anchor_src_field 在 dst/src 端 detector.event_cls 上存在,
        拒绝 anchor_src_field 指向单调坐标字段(引导改用 EqualsEdge)。详见 spec §3.5。"""
        from dataclasses import fields as dc_fields
        nodes_by_id = {n.node_id: n for n in self.nodes}
        for e in self.edges:
            if e.anchor_field is None:
                continue
            # 校验 3:anchor_src_field 不允许单调坐标(应当走 EqualsEdge 结构剪枝)
            if e.anchor_src_field in ("start_idx", "end_idx"):
                raise ValueError(
                    f"PatternSpec._validate_anchor: anchor_src_field='{e.anchor_src_field}' "
                    f"指向单调坐标字段;走结构剪枝路径应用 EqualsEdge,不要 anchor 旁路;edge: {e}"
                )
            # 校验 1:anchor_field 在 dst event_cls 上
            dst_node = nodes_by_id[e.dst]
            dst_cls = dst_node.detector.event_cls
            dst_field_names = {f.name for f in dc_fields(dst_cls)}
            if e.anchor_field not in dst_field_names:
                raise ValueError(
                    f"PatternSpec._validate_anchor: anchor_field='{e.anchor_field}' "
                    f"not in dst node '{e.dst}' event_cls {dst_cls.__name__} fields "
                    f"(have: {sorted(dst_field_names)}); edge: {e}"
                )
            # 校验 2:anchor_src_field 在 src event_cls 上(default 'event_id')
            src_attr = e.anchor_src_field or "event_id"
            src_node = nodes_by_id[e.src]
            src_cls = src_node.detector.event_cls
            src_field_names = {f.name for f in dc_fields(src_cls)} | {"event_id", "start_idx", "end_idx"}
            if src_attr not in src_field_names:
                raise ValueError(
                    f"PatternSpec._validate_anchor: anchor_src_field='{src_attr}' "
                    f"not in src node '{e.src}' event_cls {src_cls.__name__} fields; edge: {e}"
                )

    def _validate_render_grid(self) -> None:
        """render_grid='price' 当前只允许 point 几何 (event_cls.is_point=True)。
        span × price 落入未定义渲染象限 — 显式拒绝, 避免静默吞 span 信息。
        未来若需 span × price (端点钉价格 + 区间淡色), 见 design §未来扩展路径 E1。"""
        for n in self.nodes:
            if n.render_grid != "price":
                continue
            event_cls = getattr(n.detector, "event_cls", None)
            if event_cls is None:
                raise ValueError(
                    f"PatternSpec._validate_render_grid: node {n.node_id!r} "
                    f"detector has no event_cls — cannot determine geometry"
                )
            if not getattr(event_cls, "is_point", False):
                raise ValueError(
                    f"PatternSpec._validate_render_grid: NodeSpec({n.node_id!r}).render_grid='price' "
                    f"requires point geometry (event_cls.is_point=True), but "
                    f"{event_cls.__name__} is span event. "
                    f"若需 span × price, 见 design §未来扩展路径 E1。"
                )

    # ── 面板投影 + 引擎判据 ──
    def to_topology(self) -> PatternTopology:
        """零派生直投 nodes/edges(对比旧 build_topology 从谓词元数据反推)。"""
        return PatternTopology(
            nodes=tuple(
                TopoNode(n.node_id, n.detector.event_cls.class_id, n.label)
                for n in self.nodes
            ),
            edges=tuple(TopoEdge(e.src, e.dst, type(e).__name__) for e in self.edges),
        )

    def eq_src_nodes(self) -> frozenset:
        """作为任何 EqualsEdge 之 src 的 node_id 集合。
        Phase 2 引擎据此对这些节点关闭 C1 等-end 塌缩(verdict §6.2,否则漏匹配)。"""
        return frozenset(e.src for e in self.edges if isinstance(e, EqualsEdge))
