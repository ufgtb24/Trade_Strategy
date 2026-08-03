# path2/dag/_solve.py
"""匹配求解核心:约束图编译 + 唯一求解函数 solve(plan, streams)。

语义:枚举所有满足 dag 约束的绑定(_dfs 回溯)+ where 候选预过滤【先于】C1 塌缩 +
前沿割签名按边 signature_fields 自描述(在 _signature.py)。

c1_off 关 C1 节点 5 源(详见 compile_plan 内注释):
  (1) EqualsEdge.src 节点(verdict §6.2);
  (2) 带 dst_selector 入边的 dst 节点(D4);
  (3) 带 src_selector 的 NegationEdge.src 节点(D-final);
  (4) 出边为空的叶子节点(B2 加);
  (5) anchor_field 非空边的 src 节点(B4 加)。

strict_clear/negation 见各自 task;本文件随 task 增量长成。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from path2.dag.edges import DependencyEdge, EqualsEdge, NegationEdge, TemporalEdge
from path2.dag.nodes import NodeSpec
from path2.dag._graph import (pos_preds, neg_out, topo_order, wccs, sub_nodes_edges)
from path2.dag._signature import (frontier_cut_signature, collapse_equal_end_keep_keymin)

INF = float("inf")


@dataclass
class Plan:
    """编译后的求解计划(只读)。每个 WCC 独立求解。"""
    nodes: Dict[str, NodeSpec]                         # node_id -> NodeSpec
    edges: Tuple[DependencyEdge, ...]
    c1_off: frozenset                                  # 须关 C1 的节点(c1_off 5 源总表,详见 compile_plan 内注释)
    leaves: frozenset                                  # 出边为空的叶子节点(B2 加;同时供 B3 reachable-leaves 复用)
    wcc_plans: List["WccPlan"]
    pattern_id: str = "pattern"


@dataclass
class WccPlan:
    comp: List[str]
    order: List[str]
    pred: Dict[str, List[Tuple[str, DependencyEdge]]]  # 正向前驱
    neg: Dict[str, List[NegationEdge]]                 # src -> 否定出边
    sources: List[str]


@dataclass
class Solution:
    assign: Dict[str, object]      # node_id -> Event
    chosen_idx: Dict[str, int]     # node_id -> 流内下标,reify 用


def compile_plan(spec) -> Plan:
    """spec -> Plan。"""
    nodes = {n.node_id: n for n in spec.nodes}
    edges = tuple(spec.edges)

    # 整改二:叶子集合 = 没有正向出边的节点(NegationEdge 不算正向)
    positive_edge_srcs = frozenset(e.src for e in edges if not isinstance(e, NegationEdge))
    leaves = frozenset(n.node_id for n in spec.nodes if n.node_id not in positive_edge_srcs)

    # C1 须关节点(c1_off 5 源总表):
    #   (1) EqualsEdge.src —— window 把 start 钉死、非单调(verdict §6.2);
    #   (2) 带 dst_selector 入边的 dst —— C1 退化按父 end_idx 塌缩,但该入边 satisfies 看的是
    #       候选 child(dst_selector) 端点(尤其 child.end 的 containment 上界),父 end 相同、child
    #       端点不同的候选被误当可互换 → 丢真匹配(reviewer 8000-trial fuzz 抓到,D4 修复);
    #   (3) 带 src_selector 的 NegationEdge 的 src —— C1 按节点出边 signature_fields() 复合键
    #       塌缩候选;但 NegationEdge.signature_fields() 返回空,_build_out_edges 把它过滤掉,
    #       导致 C1 学不到"negation 读了 src.child(key) 端点"。两个 src 候选父 end 相同但
    #       child(key) 端点不同时被误当可互换塌缩 → negation 约束错判 → 漏匹配
    #       (final holistic reviewer fuzz 抓到 3 例,D-final 修复);
    #   (4) 出边为空的叶子节点(plan.leaves)—— 整改二新增:reachable-leaves 兜不住的
    #       局部丢点;同 end 桶内多 leaf 候选不能被 C1 塌缩;
    #   (5) anchor_field 非空边的 src 节点 —— 整改四新增:anchor 边 signature_fields 空被
    #       _build_out_edges 过滤,C1 学不到"src 端身份在 satisfies 里参与"。机理同 NegationEdge.src_selector 关 C1。
    #   当前零 Child selector 业务消费者,关 C1 的剪枝损失不可观测;未来宽 child 业务 spec 再按
    #   D3 monotone_dir 思路细化(同 D3 延后决策)。
    eq_src = spec.eq_src_nodes()
    dst_sel = frozenset(e.dst for e in edges if e.dst_selector is not None)
    neg_src = frozenset(
        e.src for e in edges
        if isinstance(e, NegationEdge) and e.src_selector is not None
    )
    # ★ 整改二第 4 源:出边为空的叶子节点(plan.leaves)
    # ★ 整改四第 5 源:anchor_field 非空边的 src 节点
    anchor_src = frozenset(e.src for e in edges if e.anchor_field is not None)
    c1_off = frozenset.union(eq_src, dst_sel, neg_src, leaves, anchor_src)

    neg_all = neg_out(edges)
    neg_dst = {e.dst for e in edges if isinstance(e, NegationEdge)}
    bound_ids = [nid for nid in nodes if nid not in neg_dst]
    wcc_plans: List[WccPlan] = []
    for comp in wccs(bound_ids, edges):      # 只对可绑节点求 WCC(否定 dst 是约束,不绑定)
        s, sub = sub_nodes_edges(comp, edges)
        order = topo_order(s, sub)
        pred = pos_preds(s, sub)
        indeg = {n: len(pred[n]) for n in s}
        sources = [n for n in order if indeg[n] == 0]
        neg = {src: [e for e in neg_all.get(src, []) if src in s] for src in s}
        wcc_plans.append(WccPlan(comp=comp, order=order, pred=pred, neg=neg, sources=sources))
    return Plan(nodes=nodes, edges=edges, c1_off=c1_off, leaves=leaves,
                wcc_plans=wcc_plans, pattern_id=spec.pattern_id)


# ───────────────────────── helpers ─────────────────────────
def endpoint(binding, edge: DependencyEdge, which: str = "src"):
    """端点提取(两态):
    1. selector 非 None(Child 路径):嵌套事件,返回 binding.child(selector)。
    2. selector=None:直接返回 binding(单 Event)。

    which='src'(默认)→ 读 edge.src_selector;
    which='dst' → 读 edge.dst_selector(D4 接入 dst 端时使用)。"""
    selector = edge.src_selector if which == "src" else edge.dst_selector
    if selector is not None:
        return binding.child(selector)
    return binding


# (where 过滤内联在 _dfs 的候选生成处,不单列函数)


def strict_clear(edge, a, e_dst, streams) -> bool:
    """STRICT next(verdict §5):e_dst 须是窗口内【第一个】同类候选。
    即不存在 other≠e_dst,a.end+min_gap <= other.start < e_dst.start 且 other.start <= a.end+max_gap。
    仅 TemporalEdge.strict 生效;是 feasible_window 之外的独立 bind-time check,不可折进窗口。"""
    if not getattr(edge, "strict", False) or not isinstance(edge, TemporalEdge):
        return True
    lo = a.end_idx + edge.min_gap
    hi = a.end_idx + edge.max_gap
    for other in streams.get(edge.dst, []):
        if other is e_dst:
            continue
        if lo <= other.start_idx < e_dst.start_idx and other.start_idx <= hi:
            return False
    return True


def negation_clear(neg_edges, src_id, assign, streams) -> bool:
    """src 已绑,检查其全部否定出边:窗口内无任何 dst 违禁(全称量词)。
    NegationEdge.satisfies 返 True = 违禁。
    端点走 endpoint()(与正向边一致)。"""
    for e in neg_edges:
        a = endpoint(assign[src_id], e)
        if any(e.satisfies(a, x) for x in streams.get(e.dst, [])):
            return False
    return True


# NodeSpec 查询(Plan 持有 nodes;_dfs 不直接拿 Plan,用闭包传)。
_CUR_NODES: Dict[str, NodeSpec] = {}
# C1 字段级定级(D3):v 的出边列表，供 collapse_equal_end_keep_keymin 按 selector 分组。
# 与 _CUR_NODES 同生命周期，在 solve 入口处统一设置。
_CUR_OUT_EDGES: Dict[str, List[DependencyEdge]] = {}

def wp_node(wp, v, streams):
    return _CUR_NODES.get(v)


def _build_out_edges(plan: Plan) -> Dict[str, List[DependencyEdge]]:
    """plan.edges → {node_id: [出边列表]}（C1 字段级定级用，D3）。
    只保留 signature_fields() 非空的边：空 signature_fields 边（如 NegationEdge）对复合键
    贡献零维，纳入与否行为等价，过滤掉可让 _has_child_selector 不被零贡献边误触发。"""
    out: Dict[str, List[DependencyEdge]] = {}
    for e in plan.edges:
        if e.signature_fields():
            out.setdefault(e.src, []).append(e)
    return out



def _dfs(wp: WccPlan, k, assign, chosen_idx, streams, memo, out, c1_off,
         *, emitted_leaves: Dict[str, set],
         collapse, memo_mode):
    """回溯枚举:ptr 恒不推进(全后缀);到叶子 emit 后继续回溯。返回「本分支是否有完成」。
    memo_mode: 'off' | 'naive'(逐字记,BUGGY) | 'charitable'(仅整棵子树零完成才记)。"""
    if k == len(wp.order):
        out.append(Solution(assign=dict(assign), chosen_idx=dict(chosen_idx)))
        # ★ 整改三:emit 后更新 emitted_leaves(本次 assign 内所有 leaf 节点的 stream_idx 入集)
        for lab in assign:
            if lab in emitted_leaves:
                emitted_leaves[lab].add(chosen_idx[lab])
        return True
    v = wp.order[k]

    sig = None
    if memo_mode != "off":
        sig = frontier_cut_signature(assign, wp.pred, wp.order, k)
        if sig in memo[v]:
            return False

    ps = wp.pred[v]
    lst = streams.get(v, [])
    # 统一窗口交：仅对无 dst_selector 的入边约束本体 start_idx。
    lo, hi = -INF, INF
    for u, e in ps:
        if e.dst_selector is None:
            wlo, whi = e.feasible_window(endpoint(assign[u], e))
            lo, hi = max(lo, wlo), min(hi, whi)
        else:
            wlo, whi = e.feasible_window(endpoint(assign[u], e))
            if wlo > whi:
                if memo_mode != "off":
                    memo[v].add(sig)
                return False
    if lo > hi:
        if memo_mode != "off":
            memo[v].add(sig)
        return False

    node = _CUR_NODES.get(v)

    # 候选 = 全后缀 ∩ 窗口(per-edge dst 投影)，ptr=0 全后缀（ANY 语义）
    def _in_all_windows_any(ev):
        for u, e in ps:
            wlo, whi = e.feasible_window(endpoint(assign[u], e))
            if not (wlo <= endpoint(ev, e, "dst").start_idx <= whi):
                return False
        return True

    cands = [(lst[i], i) for i in range(len(lst)) if _in_all_windows_any(lst[i])]
    cands.sort(key=lambda ei: (ei[0].start_idx, ei[0].end_idx, ei[1]))
    if node is not None and node.where:
        cands = [(e, i) for e, i in cands if all(fn(e) for _, fn in node.where)]
    if collapse and v not in c1_off:                  # ANY 默认关 C1(开则漏)
        cands = collapse_equal_end_keep_keymin(cands, _CUR_OUT_EDGES.get(v))

    # ★ 整改三 leaf 早退:已 emit 的 leaf 不再重复
    if v in emitted_leaves:   # v in plan.leaves(emitted_leaves keys = plan.leaves)
        cands = [(e, i) for e, i in cands if i not in emitted_leaves[v]]
        if not cands:
            if memo_mode != "off":
                memo[v].add(sig)
            return False

    any_completion = False
    for e_dst, i in cands:
        ok = True
        for u, edge in ps:                            # satisfies 充要复核 + anchor 复核 + strict（dst child-aware）
            src_ep = endpoint(assign[u], edge)
            dst_ep = endpoint(e_dst, edge, "dst")
            if not edge.satisfies(src_ep, dst_ep):
                ok = False; break
            if not edge._anchor_ok(src_ep, dst_ep):
                ok = False; break
            if not strict_clear(edge, src_ep, dst_ep, streams):
                ok = False; break
        if not ok:
            continue
        assign[v] = e_dst; chosen_idx[v] = i
        if wp.neg.get(v) and not negation_clear(wp.neg[v], v, assign, streams):
            del assign[v]; del chosen_idx[v]
            continue
        sub = _dfs(wp, k + 1, assign, chosen_idx, streams, memo, out, c1_off,
                   emitted_leaves=emitted_leaves,
                   collapse=collapse, memo_mode=memo_mode)
        any_completion = any_completion or sub
        del assign[v]; del chosen_idx[v]

    if memo_mode == "naive":
        memo[v].add(sig)                              # BUGGY:即便有兄弟完成也记
    elif memo_mode == "charitable":
        if not any_completion:
            memo[v].add(sig)                          # 仅真零完成前沿
    return any_completion


def solve(plan: Plan, streams, *, collapse=False, memo_mode="charitable") -> List[Solution]:
    """path2 DAG 唯一求解函数。

    语义:枚举所有满足 dag 约束的绑定(_dfs 回溯)+ 按 leaf event 跨 prefix 去重(B3 整改三)。
    collapse=True / memo_mode='naive'|'off' 仅供 necessity 差分测试;
    production 默认 collapse=False, memo_mode='charitable'。

    Plan 来自 compile_plan;c1_off 5 源总表见模块 docstring。
    emitted_leaves:跨 WCC 共享(不同 WCC 的 leaf node_id 不重叠,共享安全)。"""
    global _CUR_NODES, _CUR_OUT_EDGES
    _CUR_NODES = plan.nodes
    _CUR_OUT_EDGES = _build_out_edges(plan)
    # ★ 整改三:emitted_leaves 跨 WCC 共享
    emitted_leaves: Dict[str, set] = {leaf: set() for leaf in plan.leaves}
    out: List[Solution] = []
    for wp in plan.wcc_plans:
        memo = {n: set() for n in wp.comp}
        _dfs(wp, 0, {}, {}, streams, memo, out, plan.c1_off,
             emitted_leaves=emitted_leaves,
             collapse=collapse, memo_mode=memo_mode)
    return out
