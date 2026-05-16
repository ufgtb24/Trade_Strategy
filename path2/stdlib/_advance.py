"""约束推进核心 —— LEF-DFS(redesign §3,权威)。

`advance_dag` 是四 Detector 共用的约束推进核心(Chain/Dag/Neg 复用,
Kof 另有滑窗实现)。算法 = **LEF-DFS**(redesign §3):固定拓扑序,
对当前消费前沿后缀做带回溯的深度优先搜索,按
`key=(start_idx, end_idx, position_in_S[L])` 字典序取最早可行赋值
(earliest-feasible,redesign §2.2),产出后对每个用到的标签做
**全成员非重叠消费**(按被选实例真实整数下标推进)。

三态分离(redesign §3.4,**永不混淆**):
- **INV-A** 逐节点访问的 scan 指针:每次节点访问对当前消费前沿后缀做
  **新鲜全后缀扫描**,无 `start_idx` 早停,不跨 anchor / 不跨回溯携带
  (修 CRITICAL-4 mode-i)。
- **INV-B** 持久消费指针 `ptr[L]`:整个 detect() 携带;产出后
  `ptr[L] = 被选实例真实整数下标 + 1`,绝不用 `.index()` / `__eq__`
  (修 IMPORTANT-1)。
- **INV-C** FAILED 前沿割记忆:每个 LEF 调用内有效,LEF 调用间重置,
  不跨生产循环相继 LEF 携带;签名 = 跨"已赋值→未赋值后缀"边的尾端
  `end_idx` 集合;同签名 ⇒ 剩余可行域相同 ⇒ 健全剪。

逐弱连通分量(WCC)独立处理(redesign §2.0 / §6):每个 WCC 是独立
子问题(各自 ptr / 拓扑序 / LEF 序列),Detector 输出 = 各分量序列按
emitted `end_idx` 升序的 p 路归并(避免跨分量消费耦合扼杀匹配)。

`event_id`(redesign §7):无条件、四 Detector 共享的 detect()-局部
`seen_ids`;`base=f"{label}_{s}_{e}"`,撞则 `base#<n>`(n 从 1 起)。
常见无撞情形 id 保持干净的 `{label}_{s}_{e}`(修 CRITICAL-3)。

复杂度(诚实账,redesign §5;旧失实的"单调双指针 O(ΣN) 永不回退"
**已被推翻并移除**):设 `f` = 前沿割宽度(类 pathwidth 的图参数,
**非**最大入度)。时间 `Θ(M·m·Δ^f·w)`,空间 `Θ(Δ^f)` 每 LEF 调用
(LEF 调用结束即释放,峰值非跨生产循环累积)。
- **Chain**:结构 `f=1`(单边前沿割)⇒ 标量签名 ⇒ 多项式 / 近线性
  (承重的常见情形结论)。
- **病态宽前沿 DAG**:时间与空间**同为指数**(内在 interval-CSP-over-DAG
  难度,显式承认,不做"指数时间换有界空间"的隐瞒)。
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Set, Tuple

from path2.core import Event, TemporalEdge
from path2.stdlib._graph import Graph, build_graph, topo_order
from path2.stdlib._ids import default_event_id
from path2.stdlib.pattern_match import PatternMatch


def _preds(g: Graph) -> Dict[str, List[Tuple[str, TemporalEdge]]]:
    """label -> [(pred_label, edge)]。"""
    pred: Dict[str, List[Tuple[str, TemporalEdge]]] = {n: [] for n in g.nodes}
    for u in g.nodes:
        for v, e in g.adj[u]:
            pred[v].append((u, e))
    return pred


def _wcc(g: Graph) -> List[List[str]]:
    """弱连通分量(无向连通)。返回每个分量的节点列表(节点序确定)。

    redesign §2.0:每个 WCC 是独立子问题。分量按其最小节点标签排序,
    保证可复现。
    """
    undirected: Dict[str, Set[str]] = {n: set() for n in g.nodes}
    for e in g.edges:
        undirected[e.earlier].add(e.later)
        undirected[e.later].add(e.earlier)
    seen: Set[str] = set()
    comps: List[List[str]] = []
    for n in sorted(g.nodes):
        if n in seen:
            continue
        stack = [n]
        comp: List[str] = []
        seen.add(n)
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in undirected[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        comps.append(sorted(comp))
    comps.sort(key=lambda c: c[0])
    return comps


def _subgraph(g: Graph, nodes: Set[str]) -> Graph:
    """仅含 `nodes` 内部边的子图(逐 WCC 独立推进用)。"""
    sub_edges = [
        e for e in g.edges if e.earlier in nodes and e.later in nodes
    ]
    if sub_edges:
        return build_graph(sub_edges)
    # 每个 Graph 节点都源自一条 edge 端点(build_graph 不变式);一个 WCC
    # 至少含一条内部边 ⇒ sub_edges 永不为空。空 = 上游不变式被破坏,
    # 显式炸而非静默吞掉(否则会用空子图掩盖未来的不变式回归)。
    raise AssertionError(
        "unreachable: every Graph node originates from an edge endpoint"
    )


def _emit(
    assign: Dict[str, Event],
    label: str,
    seen_ids: Dict[str, int],
) -> PatternMatch:
    """构造 PatternMatch,event_id 经共享 seen_ids 去重(redesign §7)。"""
    members = sorted(assign.values(), key=lambda e: e.start_idx)
    s = members[0].start_idx
    end = max(e.end_idx for e in members)
    base = default_event_id(label, s, end)
    if base not in seen_ids:
        seen_ids[base] = 0
        eid = base
    else:
        n = seen_ids[base] + 1
        seen_ids[base] = n
        eid = f"{base}#{n}"
    return PatternMatch(
        event_id=eid,
        start_idx=s,
        end_idx=end,
        children=tuple(members),
        role_index={lab: (assign[lab],) for lab in assign},
        pattern_label=label,
    )


def _frontier_cut_signature(
    assign: Dict[str, Event],
    pred: Dict[str, List[Tuple[str, TemporalEdge]]],
    order: List[str],
    k: int,
) -> Tuple[Tuple[str, int], ...]:
    """前沿割签名(INV-C,redesign §3.1)。

    = 每个已赋值且为 ≥1 条边 u→w(w 在未赋值后缀)尾端的 u 的
    `(u, φ(u).end_idx)`,按标签排序。健全性:未赋值节点上每条约束都是
    一条边、其已赋值尾端必在割中 ⇒ 相同签名 ⇒ 剩余可行域完全相同。
    """
    unassigned = set(order[k:])
    sig: Set[Tuple[str, int]] = set()
    for w in unassigned:
        for u, _e in pred[w]:
            if u in assign:
                sig.add((u, assign[u].end_idx))
    return tuple(sorted(sig))


def _collapse_equal_end_keep_keymin(
    cands: List[Tuple[Event, int]],
) -> List[Tuple[Event, int]]:
    """等-end_idx 簇塌缩,保留簇内 key=(start,end,position) argmin(C1)。

    输入已按 key 升序。同一 admissible 集合内只对不同 end_idx 递归
    (值相等簇只探一次)。因输入按 key 升序、key 首字段为 start_idx,
    每个 end_idx 簇内第一个出现者即为该簇 key argmin。
    """
    out: List[Tuple[Event, int]] = []
    seen_end: Set[int] = set()
    for e, i in cands:
        if e.end_idx in seen_end:
            continue
        seen_end.add(e.end_idx)
        out.append((e, i))
    return out


def _lef_dfs(
    order: List[str],
    k: int,
    assign: Dict[str, Event],
    chosen_idx: Dict[str, int],
    ptr: Dict[str, int],
    streams: Dict[str, List[Event]],
    pred: Dict[str, List[Tuple[str, TemporalEdge]]],
    memo: Dict[str, Set[Tuple[Tuple[str, int], ...]]],
) -> Optional[Tuple[Dict[str, Event], Dict[str, int]]]:
    """LEF-DFS 递归(redesign §3.3 伪代码)。

    返回 (assign, chosen_idx) 或 None(本前沿无完成)。
    """
    if k == len(order):
        return (dict(assign), dict(chosen_idx))
    v = order[k]

    sig = _frontier_cut_signature(assign, pred, order, k)
    if sig in memo[v]:  # INV-C:已证此前沿割无完成 → 健全剪
        return None

    ps = pred[v]
    lst = streams[v]

    if not ps:  # 源节点:无窗口约束,后缀全体按 key 序为候选
        lo: float = float("-inf")
        hi: float = float("inf")
    else:
        # 多前驱窗口:lo=max(pred.end+min_gap),hi=min(pred.end+max_gap)
        lo = max(assign[u].end_idx + e.min_gap for u, e in ps)
        hi = min(assign[u].end_idx + e.max_gap for u, e in ps)
        if lo > hi:
            memo[v].add(sig)
            return None

    # INV-A:对当前消费前沿后缀 [ptr[v]:] 做新鲜全后缀扫描,无 start 早停。
    # C-ORDER:admissibility 过滤 MUST 严格先于等-end 塌缩。
    cands: List[Tuple[Event, int]] = [
        (lst[i], i)
        for i in range(ptr[v], len(lst))
        if lo <= lst[i].start_idx <= hi
    ]
    # C-KEY:按 key=(start_idx, end_idx, position) 字典序排序。
    cands.sort(key=lambda ei: (ei[0].start_idx, ei[0].end_idx, ei[1]))
    # C1:等-end 塌缩,代表 = 簇内 key argmin(过滤之后才塌缩)。
    cands = _collapse_equal_end_keep_keymin(cands)

    for e, i in cands:
        assign[v] = e
        chosen_idx[v] = i
        r = _lef_dfs(
            order, k + 1, assign, chosen_idx, ptr, streams, pred, memo
        )
        if r is not None:
            return r
        del assign[v]
        del chosen_idx[v]

    memo[v].add(sig)  # 记 FAILED 前沿割(INV-C)
    return None


def _produce_wcc(
    g: Graph,
    streams: Dict[str, List[Event]],
    label: str,
    seen_ids: Dict[str, int],
) -> Iterator[PatternMatch]:
    """单 WCC 的 LEF 生产循环(redesign §3.3 PRODUCE)。"""
    order = topo_order(g)
    pred = _preds(g)
    ptr: Dict[str, int] = {n: 0 for n in g.nodes}
    sources = [n for n in order if g.indeg[n] == 0]

    while True:
        # 任一源后缀耗尽 ⇒ 该分量无更多 LEF。
        if any(ptr[s] >= len(streams.get(s, [])) for s in sources):
            return
        memo: Dict[str, Set[Tuple[Tuple[str, int], ...]]] = {
            n: set() for n in g.nodes
        }  # INV-C:每个 LEF 调用重置
        result = _lef_dfs(order, 0, {}, {}, ptr, streams, pred, memo)
        if result is None:
            # 当前消费前沿无新 LEF。按非重叠语义推进最早仍有备选的源后重试;
            # 所有源耗尽则结束(终止性:每次产出 ≥1 指针严格前移)。
            # 只推进第一个源是无损的:_lef_dfs 已对全节点做完整回溯,证明
            # 当前 ptr 组合下不存在任何可行匹配;故向前滑动任一个源都不会
            # 跳过匹配,后续 LEF 调用会对所有节点备选重新探索。
            advanced = False
            for s in sources:
                if ptr[s] + 1 < len(streams.get(s, [])):
                    ptr[s] += 1
                    advanced = True
                    break
            if not advanced:
                return
            continue
        assign, chosen_idx = result
        yield _emit(assign, label, seen_ids)
        # INV-B:全成员非重叠消费,按被选实例真实整数下标推进。
        for lab in assign:
            ptr[lab] = chosen_idx[lab] + 1


def advance_kof(
    g: Graph,
    streams: Dict[str, List[Event]],
    edges: List[TemporalEdge],
    k: int,
    label: str,
) -> Iterator[PatternMatch]:
    """k-of-n 边松弛滑窗计数(redesign §3.3/§5)。

    n = edges 条数,k = 至少须满足的边数;满足条件 = 两端事件均已选且
    gap 在 [min_gap, max_gap] 内。算法为**滑窗计数**,非 LEF-DFS:

    - 锚 = `topo_order(g)[0]`(最早拓扑序源节点)的每个实例;
    - 对每个锚实例:窗口 `[a.start_idx, a.start_idx + horizon]`;
    - 每个非锚标签:在窗口内用 start-first key `(start_idx, end_idx, position)`
      取最小的候选(redesign §2.2);
    - 统计满足的边数,>= k 即命中;
    - `event_id` 消歧共享 detect()-局部 `seen_ids`(redesign §7,不再 Kof
      专属),复用 `_emit` — 保证 `#<seq>` 约定与 LEF-DFS 字节级一致;
    - 封口:`buffer` 按 end_idx 排序;锚前移后 `end_idx <= 本锚 start` 的
      匹配弹出;最终全量弹出;输出保证 end_idx 非递减。

    复杂度 O(ΣN·n),n=边数(非 LEF-DFS 指数情形)。
    """
    order = topo_order(g)
    finite_max = [e.max_gap for e in edges if e.max_gap != float("inf")]
    horizon = max(finite_max) if finite_max else None

    buffer: List[PatternMatch] = []
    seen_ids: Dict[str, int] = {}

    def _flush(upto_end: Optional[int]) -> Iterator[PatternMatch]:
        buffer.sort(key=lambda m: m.end_idx)
        keep: List[PatternMatch] = []
        for m in buffer:
            if upto_end is None or m.end_idx <= upto_end:
                yield m
            else:
                keep.append(m)
        buffer[:] = keep

    anchor_label = order[0]
    anchor_stream = streams[anchor_label]

    for a in anchor_stream:
        assign: Dict[str, Event] = {anchor_label: a}
        # 候选下界:只要事件在锚之后开始即纳入(保证非重叠;无上界过滤,
        # gap 约束由 sat 计数来评估)。horizon 仅用于 buffer 封口。
        win_lo = a.start_idx

        # 每个非锚标签:取 win_lo 之后 start-first key 最小的候选
        for lab in order:
            if lab == anchor_label:
                continue
            lab_stream = streams[lab]
            # start-first 候选:遍历 end_idx-sorted 流,筛出 start >= win_lo 的,
            # 取 key=(start_idx, end_idx, position) 最小(redesign §2.2)。
            best: Optional[Tuple[Event, int]] = None
            for i, cand in enumerate(lab_stream):
                if cand.start_idx >= win_lo:
                    key = (cand.start_idx, cand.end_idx, i)
                    if best is None or key < (
                        best[0].start_idx, best[0].end_idx, best[1]
                    ):
                        best = (cand, i)
            if best is not None:
                assign[lab] = best[0]

        # 统计满足的边数
        sat = 0
        for e in edges:
            if e.earlier in assign and e.later in assign:
                gap = assign[e.later].start_idx - assign[e.earlier].end_idx
                if e.min_gap <= gap <= e.max_gap:
                    sat += 1

        if sat >= k:
            buffer.append(_emit(assign, label, seen_ids))

        # 锚前移后封口:end_idx <= 本锚 start_idx 的匹配已无后续可超越
        yield from _flush(a.start_idx)

    yield from _flush(None)  # 收尾全量弹出


def advance_dag(
    g: Graph,
    streams: Dict[str, List[Event]],
    label: str,
) -> Iterator[PatternMatch]:
    """LEF-DFS 约束推进核心入口(Chain/Dag/Neg 复用)。

    逐 WCC 独立跑 LEF 生产循环,各分量产出按 emitted `end_idx` 升序做
    p 路归并(redesign §2.0)。`seen_ids` 为本次调用(detect()-局部)
    共享,保证单 run event_id 唯一(redesign §7)。
    """
    seen_ids: Dict[str, int] = {}
    comps = _wcc(g)

    if len(comps) == 1:
        # 单 WCC(Chain 恒为此;含全连通 Dag):无需归并。
        yield from _produce_wcc(g, streams, label, seen_ids)
        return

    # 多 WCC:p 路归并,按 emitted end_idx 升序(各分量内已升序)。
    gens = [
        _produce_wcc(_subgraph(g, set(c)), streams, label, seen_ids)
        for c in comps
    ]
    heads: List[Optional[PatternMatch]] = []
    for gen in gens:
        heads.append(next(gen, None))

    while True:
        best = -1
        for idx, h in enumerate(heads):
            if h is None:
                continue
            if best == -1 or h.end_idx < heads[best].end_idx:
                best = idx
        if best == -1:
            return
        yield heads[best]
        heads[best] = next(gens[best], None)
