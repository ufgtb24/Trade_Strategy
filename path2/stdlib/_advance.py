"""约束推进核心 —— LEF-DFS(redesign §3,权威)。

`advance_dag` 是 Chain/Dag/Neg 共用的约束推进核心;`advance_kof` 是其
**结构姊妹**(redesign §10:独立 `_kof_dfs`/`_kof_produce_wcc`,复用
同一 key 序 / 非重叠消费 / WCC / `_emit` 框架,仅 4 处差异;`_lef_dfs`
不改)。算法 = **LEF-DFS**(redesign §3):固定拓扑序,
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

from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple

from path2.core import Event, TemporalEdge
from path2.stdlib._graph import Graph, build_graph, topo_order
from path2.stdlib._ids import default_event_id
from path2.stdlib.pattern_match import PatternMatch

# 单 WCC 生产器契约:`_produce_wcc` 直接匹配此 4 参签名;
# `_kof_produce_wcc` 经 advance_kof 内 4 参闭包适配。`_pway_merge`
# 被 advance_dag + advance_kof 共享,契约显式化。
_ProduceFn = Callable[
    [Graph, Dict[str, List[Event]], str, Dict[str, int]],
    Iterator[PatternMatch],
]


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


def _kof_dfs(
    order: List[str],
    k: int,
    assign: Dict[str, Event],
    chosen_idx: Dict[str, int],
    ptr: Dict[str, int],
    streams: Dict[str, List[Event]],
    edges: List[TemporalEdge],
    k_of_n: int,
) -> Optional[Tuple[Dict[str, Event], Dict[str, int]]]:
    """Kof DFS 递归(redesign §10.5 KOF_DFS)。

    LEF-DFS 结构姊妹,**仅 4 处差异 vs `_lef_dfs`**(redesign §10.5):
    1. **无窗口过滤**:候选 = 整后缀 `S[v][ptr[v]:]`(边可不满足,不能据
       某边裁候选)——修 CRITICAL-1;
    2. **叶子 k-of-n 显式接受**:`k==len(order)` 时统计满足边数 `sat`,
       `sat >= k_of_n` 才接受,否则回溯(返回 None);
    3. **关闭 INV-C 前沿割记忆**(无窗口约束 ⇒ 前沿割不表征剩余可行域);
    4. **不做 C1 等-end 塌缩**(gap 看 start 和 end;等-end 不同 start
       对 sat 贡献不同,全候选都要试)。

    复用:start-first key `(start_idx, end_idx, position)` 排序、INV-A
    全后缀新鲜扫描、回溯。**全标签在场**(no partial,redesign §10.4):
    叶子前所有标签均已赋值;某标签后缀为空 ⇒ 其 for 循环不执行 ⇒ 该前缀
    返回 None ⇒ 不产出缺标签部分命中。
    """
    if k == len(order):
        # 叶子:k-of-n 接受谓词(redesign §10.1/§10.5)。
        sat = sum(
            1
            for e in edges
            if e.min_gap
            <= assign[e.later].start_idx - assign[e.earlier].end_idx
            <= e.max_gap
        )
        if sat >= k_of_n:
            return (dict(assign), dict(chosen_idx))
        return None

    v = order[k]
    lst = streams.get(v, [])
    # INV-A:对当前消费前沿后缀 [ptr[v]:] 做新鲜全后缀扫描。
    # 差异 1:无窗口过滤,候选 = 整后缀。
    cands: List[Tuple[Event, int]] = [
        (lst[i], i) for i in range(ptr[v], len(lst))
    ]
    # start-first key 排序(§2.2,与 LEF-DFS 同一把 key)。
    # 差异 4:不做 _collapse_equal_end_keep_keymin。
    cands.sort(key=lambda ei: (ei[0].start_idx, ei[0].end_idx, ei[1]))

    for e, i in cands:
        assign[v] = e
        chosen_idx[v] = i
        r = _kof_dfs(
            order, k + 1, assign, chosen_idx, ptr, streams, edges, k_of_n
        )
        if r is not None:
            return r
        del assign[v]
        del chosen_idx[v]

    return None  # 差异 3:无 INV-C memo 记录


def _kof_produce_wcc(
    g: Graph,
    streams: Dict[str, List[Event]],
    edges: List[TemporalEdge],
    k: int,
    label: str,
    seen_ids: Dict[str, int],
) -> Iterator[PatternMatch]:
    """单 WCC 的 Kof 生产循环(redesign §10.5 KOF_PRODUCE)。

    与 `_produce_wcc` 同构:逐 LEF(此处 `_kof_dfs`)→ 产出 → INV-B
    全成员非重叠消费 → 无命中则推进最早仍有备选的源后重试,直到任一源
    后缀耗尽。**无 INV-C memo**(每次调用不重置 memo —— Kof 不用)。
    """
    order = topo_order(g)
    ptr: Dict[str, int] = {n: 0 for n in g.nodes}
    sources = [n for n in order if g.indeg[n] == 0]

    while True:
        # 任一源后缀耗尽 ⇒ 该分量无更多命中。
        if any(ptr[s] >= len(streams.get(s, [])) for s in sources):
            return
        result = _kof_dfs(order, 0, {}, {}, ptr, streams, edges, k)
        if result is None:
            # 当前消费前沿无新命中。_kof_dfs 已对全节点做完整回溯,证明
            # 当前 ptr 组合下无可行 k-of-n 命中;推进最早仍有备选的源后
            # 重试,所有源耗尽则结束(终止性:每次产出 ≥1 指针严格前移)。
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


def _pway_merge(
    g: Graph,
    streams: Dict[str, List[Event]],
    label: str,
    seen_ids: Dict[str, int],
    produce: _ProduceFn,
) -> Iterator[PatternMatch]:
    """逐 WCC 独立生产 + p 路 end_idx 升序归并(redesign §2.0)。

    `produce(subgraph, streams, label, seen_ids) -> Iterator[PatternMatch]`
    为单 WCC 生产器(`_produce_wcc` / `_kof_produce_wcc` 偏函数)。
    单 WCC 时直接透传(零缓冲);多 WCC 时 ≤(p−1) 结构常数级前沿缓冲。
    """
    comps = _wcc(g)

    if len(comps) == 1:
        # 单 WCC(Chain 恒为此;Kof 经 validate_kof 强制为此):零缓冲透传。
        yield from produce(g, streams, label, seen_ids)
        return

    # 多 WCC:p 路归并,按 emitted end_idx 升序(各分量内已升序)。
    gens = [
        produce(_subgraph(g, set(c)), streams, label, seen_ids)
        for c in comps
    ]
    heads: List[Optional[PatternMatch]] = [next(gen, None) for gen in gens]

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


def advance_kof(
    g: Graph,
    streams: Dict[str, List[Event]],
    edges: List[TemporalEdge],
    k: int,
    label: str,
) -> Iterator[PatternMatch]:
    """k-of-n 边松弛 = **LEF-DFS 结构姊妹**(redesign §10,权威)。

    n = edges 条数,k = 至少须满足的边数。一次命中 = 全标签赋值 `φ` 且
    `|{e: min_gap(e) ≤ φ(e.later).start − φ(e.earlier).end ≤ max_gap(e)}|
    ≥ k`(**全标签在场,no partial**;某标签后缀无候选 ⇒ 该前缀无命中)。

    成员组合枚举/回溯(`_kof_dfs`,修 CRITICAL-1:松弛破坏全满足单调,
    不能逐标签盲取 argmin)+ 叶层 k-of-n 接受 + 全成员非重叠消费(INV-B,
    §6 Part D)。复用 `_wcc`/`_subgraph`/`topo_order`/`_emit`(共享
    detect()-局部 `seen_ids`+`#seq`,与 LEF-DFS **字节一致**)+ 与
    `advance_dag` 同一 p 路 end_idx 归并;`_lef_dfs` 不改(独立
    `_kof_dfs`,不污染已打磨核心)。

    缓冲(诚实账,redesign §10.6):复用 LEF 生产循环 ⇒ §6 Part D 单调性
    证明(仅依赖全成员非重叠消费 + end_idx 升序输入,**与接受谓词无关**)
    对 Kof 成立 ⇒ 缓冲 = **单 WCC 零 / 多 WCC ≤(p−1)**(与 Dag 同);
    产出天然 end_idx 升序。`validate_kof` 已强制单 WCC ⇒ 常态零缓冲。
    **代价转移到时间**:Kof 无窗口剪枝(松弛内在,不能据某边裁候选),
    `_kof_dfs` 最坏 `∏_{L∈V}|后缀(L)|`,**标签数维度指数,且为常态**
    (非如 Dag 仅病态)——诚实承认,不粉饰。
    """
    seen_ids: Dict[str, int] = {}

    def _produce(sub_g, sub_streams, lab, sids):
        return _kof_produce_wcc(sub_g, sub_streams, edges, k, lab, sids)

    yield from _pway_merge(g, streams, label, seen_ids, _produce)


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
    yield from _pway_merge(g, streams, label, seen_ids, _produce_wcc)
