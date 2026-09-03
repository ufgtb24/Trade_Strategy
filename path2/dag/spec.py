"""声明容器 PatternSpec + 面板投影 to_topology + 校验。

app 声明的全部 = nodes(NodeSpec) + edges(DependencyEdge 子类)。
nodes/edges 即类型级 DAG,to_topology() 零派生直投(对比旧 build_topology 反推)。
__post_init__ 做三类校验:DAG(环/端点)、detector-DAG(consumes_stream)、where(clause_id 同 node 内唯一)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

from path2.dag.edges import DependencyEdge, EqualsEdge, NegationEdge
from path2.dag.nodes import NodeSpec


@dataclass(frozen=True)
class TopoNode:
    node_id: str
    produced_by: Optional[str] = None   # 子结构 node 的物化来源父 node_id(独立 node 为 None)
    child_slot: Optional[str] = None    # 子结构 node 在父 children 中的 slot 名(独立 node 为 None)
    parent_refs: Tuple[Tuple[str, str], ...] = ()  # 被哪些父的 children 引用(父, slot)全量逆映射


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
    nodes: Tuple[NodeSpec, ...]
    edges: Tuple[DependencyEdge, ...]
    event_styles: Mapping[str, object] = field(default_factory=dict)
    stock_list_columns: Tuple[object, ...] = ()

    def __post_init__(self) -> None:
        self._normalize_produced_by()    # ★ 归一化先于 R1-R4(孤儿/多父在此报错)
        self._validate_node_ids()        # 必先于下列校验:它们都用去重后的 _node_ids() set,会掩盖重复
        self._validate_substructure()   # ★ 子结构死字段(where/consumes_stream/render_grid)
        self._validate_dag()
        self._validate_detector_dag()
        self._validate_where_clauses()
        self._validate_anchor()   # ★ 整改四新增
        self._validate_render_grid()   # ★ 新增:render_grid='price' 需 event_cls.is_point=True
        self._validate_no_self_feed()   # ★ 新增:禁止 consumes_stream 指向共享同一 detector 的 node
        self._validate_streams_bound()  # ★ 新增(契约 C3):多流 detector 的每条流都必须被 node 认领

    # ── 校验 ──
    def _normalize_produced_by(self) -> None:
        """children 逆映射回填子结构 node 的 produced_by(单父确定/孤儿报错/多父报错)。

        2026-08-06 agent team 定稿: produced_by 与父 children 是同一物化关系的双向
        声明,children 是唯一事实源;逆映射先于 R1-R4 执行(孤儿须在 R1 前报错)。
        """
        by_id = {n.node_id: n for n in self.nodes}
        sub_ids = {nid for nid, n in by_id.items() if n.detector is None}
        derived: dict[str, str] = {}
        for n in self.nodes:
            for child_id in n.children.values():
                if child_id not in by_id:
                    raise ValueError(
                        f"NodeSpec({n.node_id!r}).children 引用不存在的 node_id: {child_id!r}")
                if child_id in sub_ids:
                    if child_id in derived:
                        raise ValueError(
                            f"子结构 node {child_id!r} 被多父引用: {derived[child_id]!r} 与 "
                            f"{n.node_id!r}(物化来源须唯一)")
                    derived[child_id] = n.node_id
        orphans = sub_ids - set(derived)
        if orphans:
            raise ValueError(
                f"子结构 node 未被任何父 children 引用(孤儿): {sorted(orphans)}; "
                f"请确认某父的 children 引用了它")
        for n in self.nodes:
            if n.detector is not None:
                continue
            derived_pb = derived.get(n.node_id)   # 安全访问:重复 node_id 后写 detector 会遮蔽
            if derived_pb is None:                # by_id 条目,导致 derived 查不到(报干净错误而非 KeyError)
                raise ValueError(
                    f"NodeSpec({n.node_id!r}) 的 produced_by 无法推导(重复 node_id 或孤儿)")
            pb = n.produced_by
            if pb is None:
                object.__setattr__(n, "produced_by", derived_pb)
            elif pb != derived_pb:
                raise ValueError(
                    f"NodeSpec({n.node_id!r}): 显式 produced_by={pb!r} 与推导 "
                    f"{derived_pb!r} 不一致")

    def _node_ids(self) -> set:
        return {n.node_id for n in self.nodes}

    def _validate_node_ids(self) -> None:
        """node_id 是拓扑主键,须全局唯一 —— 否则求解层 5 处 {node_id: NodeSpec} 字典后写覆盖
        前写(静默丢节点/detector),而 to_topology 遍历 tuple 不去重 → 求解层与面板层裂脑。"""
        ids = [n.node_id for n in self.nodes]
        if len(set(ids)) != len(ids):
            dups = sorted({x for x in ids if ids.count(x) > 1})
            raise ValueError(f"node_id 重复: {dups}(拓扑主键须唯一)")

    def _validate_substructure(self) -> None:
        """子结构 node(produced_by 非空)只有 node_id/event_cls/children/where 有意义。

        where 语义 = 诊断层判定(diagnose 从父容器槽内事件产 attr 行 → 前端
        段级 tier),不进求解;gate match 用父 where 的 W.children(正交分层)。"""
        for n in self.nodes:
            if n.produced_by is None:
                continue
            if n.consumes_stream is not None:
                raise ValueError(
                    f"子结构 NodeSpec({n.node_id!r}): consumes_stream 是死字段(无独立流)")
            if n.render_grid != "time":
                raise ValueError(
                    f"子结构 NodeSpec({n.node_id!r}): render_grid 是死字段(默认 'time')")

    def _validate_dag(self) -> None:
        ids = self._node_ids()
        sub_ids = {n.node_id for n in self.nodes if n.produced_by is not None}
        neg_dsts = {e.dst for e in self.edges if isinstance(e, NegationEdge)}
        for e in self.edges:
            if e.src not in ids:
                raise ValueError(f"edge src={e.src!r} 不是已声明 node")
            if e.dst not in ids:
                raise ValueError(f"edge dst={e.dst!r} 不是已声明 node")
            for ep in (e.src, e.dst):
                if ep in sub_ids:
                    raise ValueError(
                        f"子结构 node {ep!r} 不得作为边端点({type(e).__name__}); 子结构不求解")
                if not isinstance(e, NegationEdge) and ep in neg_dsts:
                    raise ValueError(
                        f"neg_dst {ep!r} 被正向边引用(否定 dst 是约束,不能同时是正向边端点)")
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
        sub_ids = {n.node_id for n in self.nodes if n.produced_by is not None}
        for n in self.nodes:
            if n.consumes_stream is not None and n.consumes_stream not in ids:
                raise ValueError(
                    f"{n.node_id}: consumes_stream={n.consumes_stream!r} 不是已声明 node"
                )
            if n.consumes_stream in sub_ids:
                raise ValueError(
                    f"NodeSpec({n.node_id!r}).consumes_stream 指向子结构 node "
                    f"{n.consumes_stream!r}(子结构无独立流)")

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
        """整改四(Ruling H):校验 anchor_field 在 dst 端 node.event_cls 上存在。
        src 端身份由 _anchor_ok 按 src_ep.instance_id 计算(交错标注后 detect 期即就位),
        不再读任何 src 字段 → 原 anchor_src_field 校验(src 字段存在性/单调坐标闸)
        已随 anchor_src_field 退役一并删除。详见 spec §3.5 / Ruling H。"""
        from dataclasses import fields as dc_fields
        nodes_by_id = {n.node_id: n for n in self.nodes}
        for e in self.edges:
            if e.anchor_field is None:
                continue
            # anchor_field 在 dst event_cls 上(anchor 只约束 dst 端读哪个字段)
            dst_node = nodes_by_id[e.dst]
            dst_cls = dst_node.event_cls
            dst_field_names = {f.name for f in dc_fields(dst_cls)}
            if e.anchor_field not in dst_field_names:
                raise ValueError(
                    f"PatternSpec._validate_anchor: anchor_field='{e.anchor_field}' "
                    f"not in dst node '{e.dst}' event_cls {dst_cls.__name__} fields "
                    f"(have: {sorted(dst_field_names)}); edge: {e}"
                )

    def _validate_render_grid(self) -> None:
        """render_grid='price' 当前只允许 point 几何 (event_cls.is_point=True)。
        span × price 落入未定义渲染象限 — 显式拒绝, 避免静默吞 span 信息。
        未来若需 span × price (端点钉价格 + 区间淡色), 见 design §未来扩展路径 E1。"""
        for n in self.nodes:
            if n.render_grid != "price":
                continue
            event_cls = n.event_cls
            if event_cls is None:
                raise ValueError(
                    f"PatternSpec._validate_render_grid: node {n.node_id!r} "
                    f"has no event_cls — cannot determine geometry"
                )
            if not getattr(event_cls, "is_point", False):
                raise ValueError(
                    f"PatternSpec._validate_render_grid: NodeSpec({n.node_id!r}).render_grid='price' "
                    f"requires point geometry (event_cls.is_point=True), but "
                    f"{event_cls.__name__} is span event. "
                    f"若需 span × price, 见 design §未来扩展路径 E1。"
                )

    def _validate_no_self_feed(self) -> None:
        """禁止「自喂」:node X 的 consumes_stream 指向与 X 共享同一 detector 的 node。
        多流下最可能的误写是让 bo 节点 consumes_stream='pk' 以为读同趟 pk 流;
        实际那是 (id(det),'pk') 的第二次 detect 调用,白跑一整趟。"""
        det_of = {}
        for n in self.nodes:
            if n.detector is not None:
                det_of.setdefault(id(n.detector), []).append(n.node_id)
        for n in self.nodes:
            if n.consumes_stream is not None and n.detector is not None:
                if n.consumes_stream in det_of.get(id(n.detector), []):
                    raise ValueError(
                        f"NodeSpec({n.node_id!r}): consumes_stream={n.consumes_stream!r} "
                        f"指向共享同一 detector 的 node(自喂;会触发第二次 detect 调用)")

    def _validate_streams_bound(self) -> None:
        """多流 detector 声明的每条流都必须被组内某 node 的 produces_stream 认领(契约 C3)。

        分组键 = (id(detector), consumes_stream) —— 与 _validate_no_self_feed 同款:
        同一 detector 以不同 consumes_stream 调用是独立的两次 detect,各自的流认领
        互不相干。声明但未建 node 认领的流此前只会在引擎 _translate_refs 阶段以一句
        误导性的「事件池外」报错现身;提前到构造期,报一句说人话的错。"""
        from path2.core import stream_schema
        groups: dict = {}
        for n in self.nodes:
            if n.detector is None:   # 子结构 node 不参与(无 detector,无流可言)
                continue
            groups.setdefault((id(n.detector), n.consumes_stream), []).append(n)
        for group in groups.values():
            declared = set(stream_schema(group[0].detector))
            bound = {n.produces_stream for n in group}
            missing = declared - bound
            if missing:
                missing_list = sorted(missing, key=lambda s: (s is None, s))
                group_ids = sorted(n.node_id for n in group)
                raise ValueError(
                    f"detector 声明的流 {missing_list} 没有 node 认领(node 组 {group_ids});"
                    f"多流 detector 的每条流都必须建 node,只显示不匹配用 solve=False"
                )

    # ── 面板投影 + 引擎判据 ──
    def to_topology(self) -> PatternTopology:
        """零派生直投 nodes/edges(对比旧 build_topology 从谓词元数据反推)。"""
        by_id = {n.node_id: n for n in self.nodes}
        # children 全量逆映射:被引用的 node → [(父 node_id, slot), ...]。
        # 含独立 node(情况一:burst children={"members": "bo"})与子结构 node
        # (情况二:tb children={"segments": "tb_seg"});独立 node 可多父。
        refs: dict[str, list[tuple[str, str]]] = {}
        for p in self.nodes:
            for slot, child_id in p.children.items():
                refs.setdefault(child_id, []).append((p.node_id, slot))
        return PatternTopology(
            nodes=tuple(
                TopoNode(
                    n.node_id,
                    n.produced_by,
                    # child_slot: 子结构 node 在父 children 中的 slot 名(children 反查)
                    None if n.produced_by is None else next(
                        (k for k, v in by_id[n.produced_by].children.items()
                         if v == n.node_id), None),
                    tuple(refs.get(n.node_id, ())),
                )
                for n in self.nodes
            ),
            edges=tuple(TopoEdge(e.src, e.dst, type(e).__name__) for e in self.edges),
        )

    def eq_src_nodes(self) -> frozenset:
        """作为任何 EqualsEdge 之 src 的 node_id 集合。
        Phase 2 引擎据此对这些节点关闭 C1 等-end 塌缩(verdict §6.2,否则漏匹配)。"""
        return frozenset(e.src for e in self.edges if isinstance(e, EqualsEdge))
