"""dag 对象 → jsonable dict 投影层(纯函数,不读文件/不起服务)。

消费 path2.dag 只读数据结构(AnalysisResult/PatternMatch/PredicateTrace/ClauseWitness/
EdgeWitness/PatternTopology/NodeDiagnostics),投影成前端 JSON。path2 不引入 JSON 依赖。
"""
from __future__ import annotations

import dataclasses
import inspect
import math

from path2.dag.engine import assign_auto_source_tags


def _jsonable(v):
    """任意值 → json 可序列化。tuple/list 递归;dataclass→dict;numpy 标量→item;
    未知对象 fallback str()。Event 已禁 NaN,measured 的 None 原样保留。"""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if not math.isnan(v) else None
    if hasattr(v, "item") and not isinstance(v, (list, tuple, dict)):   # numpy 标量
        try:
            return v.item()
        except Exception:
            pass
    if isinstance(v, (tuple, list)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if dataclasses.is_dataclass(v):
        return {f.name: _jsonable(getattr(v, f.name)) for f in dataclasses.fields(v)}
    return str(v)


# ── event(全集,含未匹配;子类属性平铺,仅 tooltip 用) ──
def _event_to_dict(e) -> dict:
    """event → dict(全集,含未匹配;子类属性平铺,仅 tooltip 用)。
    child_slots 声明的持有型子 event 引用统一由 child_refs 承载(schema-driven,
    不硬编码字段名);slot 名对应字段在 fields 循环里跳过,避免 payload 冗余。"""
    d = {
        "class_id": type(e).class_id,
        "event_id": e.event_id,
        "start_idx": e.start_idx,
        "end_idx": e.end_idx,
    }
    slots = e.child_slots()
    skip_slots = set(slots.keys())   # BurstEvent -> {"members"}
    for f in dataclasses.fields(e):
        if f.name in ("event_id", "start_idx", "end_idx"):
            continue
        if f.name in skip_slots:
            continue   # 由 child_refs 承载,避免 payload 冗余
        d[f.name] = _jsonable(getattr(e, f.name))
    d["child_refs"] = {
        name: [c.event_id for c in (slot if isinstance(slot, tuple) else (slot,))]
        for name, slot in slots.items()
    }
    return d


# ── per-match 判定(reify 富化产物) ──
def _clause_to_dict(w) -> dict:
    """ClauseWitness → dict。组合子递归携带 children/label(仅非空时出现,叶子保持旧扁平形状)。"""
    d = {
        "satisfied": bool(w.satisfied),
        "measured": _jsonable(w.measured),
        "op": w.op,
        "threshold": _jsonable(w.threshold),
    }
    label = getattr(w, "label", None)
    if label is not None:
        d["label"] = label
    kids = getattr(w, "children", ())
    if kids:
        d["children"] = [_clause_to_dict(c) for c in kids]
    return d


def _edge_witness_to_dict(ew) -> dict:
    return {
        "satisfied": bool(ew.satisfied),
        "measured": _jsonable(ew.measured),
        "src": ew.src_instance.event_id,
        "dst": ew.dst_instance.event_id,
    }


def _trace_to_dict(pt) -> dict:
    return {
        "where_results": {
            nid: {cid: _clause_to_dict(w) for cid, w in clauses.items()}
            for nid, clauses in pt.where_results.items()
        },
        "edge_results": {
            f"{src}→{dst}": _edge_witness_to_dict(ew)   # "src→dst"
            for (src, dst), ew in pt.edge_results.items()
        },
    }


def _match_to_dict(m) -> dict:
    def _node(v):
        return v.event_id

    return {
        "event_id": m.event_id,
        "start_idx": m.start_idx,
        "end_idx": m.end_idx,
        "node_index": {nid: _node(v) for nid, v in (m.node_index or {}).items()},
        "children": [e.event_id for e in m.children],
        "predicate_trace": _trace_to_dict(m.predicate_trace) if m.predicate_trace else None,
    }


def serialize_analysis(res) -> dict:
    """AnalysisResult → {events:[...], matches:[...]}(每只命中股一份,§7.2)。
    每 event 附 source_tag:从 spec 权威 tag 集按 event_id 最长前缀匹配,末级兜底 class_id。
    spec=None(测试假 app)→ tags 空集,全部 event 退回 class_id 兜底。"""
    spec_nodes = res.spec.nodes if res.spec is not None else ()
    tags = sorted({_source_tag_of(n.detector) for n in spec_nodes
                   if hasattr(n.detector, "event_cls")}, key=len, reverse=True)  # 长在前
    def _band(eid):
        for t in tags:
            if eid.startswith(t + "_"):
                return t
        return None
    out_events = []
    for e in res.events:
        d = _event_to_dict(e)
        d["source_tag"] = _band(e.event_id) or type(e).class_id   # 末级兜底 class_id
        out_events.append(d)
    return {"events": out_events, "matches": [_match_to_dict(m) for m in res.matches]}


def summarize(res) -> dict:
    """{class_id: count} ∪ {"matches": n}(命中股列表的计数徽章,§7.3)。"""
    counts: dict = {}
    for e in res.events:
        t = type(e).class_id
        counts[t] = counts.get(t, 0) + 1
    counts["matches"] = len(res.matches)
    return counts


# ── pattern 静态层(拓扑面板数据源,§7.1) ──
# event_styles 兜底调色板:PATTERN_DAG.event_styles 默认空,按 topology.nodes 里 class_id 首次
# 出现顺序 setdefault(见 _event_styles),索引 i 就是"第 i 个新 class_id"。当前拓扑覆盖情况:
#   [0] bo    (bottom_burst / bo_only 的首个 class_id;主图 price-anchored [ids] 方框)
#   [1] burst (bottom_burst 的第二个 class_id;副图 interval)
#   [2] tb    (bottom_burst 的第三个 class_id;副图 point)
#   [3..6]    未占用,给未来新 class_id 兜底(顺序即分配序,i % len 循环)
_PALETTE = ["#16f943", "#2563eb", "#D60000", "#dfa300", "#7c3aed", "#0891b2", "#ca8a04"]

def _rule_from_meta(meta: dict) -> dict:
    """meta 树 → rule 树。and/or/not 递归 children;child/children 保持扁平(§3.1);
    attr 叶子在旧键(op/threshold)外补 kind/field。"""
    kind = meta.get("kind")
    if kind in ("and", "or", "not"):
        return {"kind": kind,
                "children": [_rule_from_meta(m) for m in meta.get("children", ()) if m]}
    if kind in ("child", "children"):
        inner = meta.get("inner") or {}
        return {"kind": kind, "key": meta.get("key"), "field": inner.get("field"),
                "op": inner.get("op"), "threshold": _jsonable(inner.get("threshold"))}
    return {"kind": kind or "attr", "field": meta.get("field"),
            "op": meta.get("op"), "threshold": _jsonable(meta.get("threshold"))}


def _rules_from_where(where_clauses) -> list:
    """(clause_id, fn) 序列 → rule 树列表。fn 无 meta(裸 lambda)跳过。"""
    out = []
    for cid, fn in where_clauses:
        meta = getattr(fn, "meta", None)
        if not meta:
            continue
        rule = _rule_from_meta(meta)
        rule["clause_id"] = cid
        out.append(rule)
    return out


def _edge_rule(edge) -> str:
    """边 → 人类可读规则串(面板展示)。"""
    name = type(edge).__name__
    if name in ("TemporalEdge", "NegationEdge"):
        lo, hi = edge.min_gap, edge.max_gap
        hi_s = "∞" if hi == math.inf else int(hi)   # ∞
        if name == "NegationEdge":
            return f"forbid · gap∈[{lo},{hi_s}]"
        if lo == hi:
            return f"gap={lo}"
        return f"before · gap∈[{lo},{hi_s}]"
    return {"ContainmentEdge": "contains", "StartContainmentEdge": "start_in",
            "OverlapEdge": "overlaps", "EqualsEdge": "equals"}.get(name, name)


def _event_styles(spec, topo) -> dict:
    styles = dict(spec.event_styles or {})
    seen = []
    for n in topo.nodes:
        if n.class_id not in seen:
            seen.append(n.class_id)
    for i, t in enumerate(seen):
        styles.setdefault(t, _PALETTE[i % len(_PALETTE)])
    return styles


def _materialize_keys_of(det) -> list[str]:
    """detector 构造参数键(去 self)= 物化层 yaml 键。

    依据 author 约定:进 detector __init__ 的参数 = 物化层(决定 event 是否生成),
    留在 node.where 的 = where 层(决定是否升 match)。反射 __init__ 签名精确捕获此约定,
    比 params.*_kwargs(手挑、可能漂移)更源头。
    """
    sig = inspect.signature(type(det).__init__)
    return [name for name in sig.parameters if name != "self"]


def _source_tag_of(det):
    return getattr(det, "source_tag", None) or det.event_cls.class_id


def _assert_injective_source_tags(nodes):
    seen = {}
    for n in nodes:
        if not hasattr(n.detector, "event_cls"):
            continue
        tag = _source_tag_of(n.detector)
        if tag in seen:
            raise ValueError(
                f"band-UI 要求每 node 的 source_tag 唯一,但 {seen[tag]!r} 与 {n.node_id!r} "
                f"都映射到 {tag!r}(共享 detector 实例或手动同名 source_tag);请配独立实例/独立 source_tag"
            )
        seen[tag] = n.node_id


def serialize_pattern(spec) -> dict:
    """PatternSpec → {pattern_id, topology{nodes,edges}, event_styles}(§7.1)。
    topology 来自 to_topology() + 每节点 where_rules(静态阈值,无实测值)。"""
    assign_auto_source_tags(spec.nodes)        # 静态序列化补齐 source_tag(幂等)
    _assert_injective_source_tags(spec.nodes)
    topo = spec.to_topology()
    by_id = {n.node_id: n for n in spec.nodes}
    nodes = []
    for tn in topo.nodes:
        n = by_id[tn.node_id]
        node = {
            "node_id": tn.node_id,
            "class_id": tn.class_id,
            "where_rules": _rules_from_where(n.where),
            "source_tag": _source_tag_of(n.detector),
            "render_grid": n.render_grid,   # ★ 新增:透传 NodeSpec.render_grid
            "materialize_keys": _materialize_keys_of(n.detector),
        }
        nodes.append(node)
    # to_topology().edges 与 spec.edges 同序一一对应 → zip(避免多重边 key 冲突)
    edges = [
        {"src": te.src, "dst": te.dst, "kind": te.kind, "rule": _edge_rule(de),
         "anchor_field": de.anchor_field}
        for te, de in zip(topo.edges, spec.edges)
    ]
    # v4 契约 C:派生 debug_enabled_classes(has_debug_hooks=True 的 detector 的 class_id 去重,拓扑序)
    debug_enabled_classes: list[str] = []
    seen: set[str] = set()
    for n in spec.nodes:
        det_cls = type(n.detector)
        if getattr(det_cls, "has_debug_hooks", False) and hasattr(n.detector, "event_cls"):
            cid = n.detector.event_cls.class_id
            if cid not in seen:
                seen.add(cid)
                debug_enabled_classes.append(cid)

    return {
        "pattern_id": spec.pattern_id,
        "topology": {"nodes": nodes, "edges": edges},
        "event_styles": _event_styles(spec, topo),
        "debug_enabled_classes": debug_enabled_classes,
    }


def serialize_per_pattern_result(res, end_node: str, label_horizon: int,
                                  win, start_ts, end_ts,
                                  price_min=None, price_max=None, *,
                                  first_passage_enabled: bool = True,
                                  first_passage_k: float = 5.0) -> dict:
    """单股单 pattern 投影,服务多 pattern worker。

    args:
        res: AnalysisResult(已 analyze 完整 buf_win)
        end_node: pattern 的买点 node(从 eval_meta 取)
        label_horizon: 前瞻收益天数
        win: 已切好的 DataFrame(含 date 列 + OHLC)
        start_ts/end_ts: pd.Timestamp,严格窗左右边界(含)
        price_min/price_max: match 级价格过滤区间(闭区间,None=不限)。锚 end_node
            事件日收盘价——与窗口过滤、forward_return 共用同一个 ev.start_idx。
        first_passage_enabled: 是否累加首次穿越四态计数到 match_fp_counts(默认 True)。
            关闭时 match_fp_counts 为单组全 0 {up,down,both,none}(向后兼容;match 自身永不带 first_passage)。
        first_passage_k: 首次穿越几何对称阈值参数 k(上行 P(1+kM)、下行 P/(1+kM)),
            match_first_passage 内算 M;默认 5.0。

    返回 {summary, analysis, max_forward_return, min_forward_drawdown, match_fp_counts}:
      - analysis.events: 全集照旧(含缓冲段;K 线灰色层数据源)
      - analysis.matches: 仅保留 end_node event 起点 ∈ [start_ts, end_ts] 且
                          close ∈ [price_min, price_max] 的 match,每条注入
                          forward_return + forward_drawdown(mfr 下行镜像)
      - summary["matches"]: 窗内 match 数(覆写)
      - max_forward_return: max over filtered matches 中非 None 的 forward_return;
                            空 / 全 None → None
      - min_forward_drawdown: min over filtered matches 中非 None 的 forward_drawdown
                              (最差下行;与 max_forward_return 的 max 对仗);
                              空 / 全 None → None
      - match_fp_counts: per-pattern 首穿四态计数 单组 {up,down,both,none},
                         遍历各 match span 全买点日累加(first_passage_enabled=False
                         或无 match → 单组全 0);集合级 ratio 的分母=买点日数
    """
    from path2.eval import (match_forward_returns, match_forward_drawdowns,
                            match_first_passage)

    ret_by_id: dict = {}
    dd_by_id: dict = {}
    match_fp_counts = {"up": 0, "down": 0, "both": 0, "none": 0}
    for m in res.matches:
        ev = m.node_index[end_node]
        buy_date = win["date"].iat[ev.start_idx]
        if not (start_ts <= buy_date <= end_ts):
            continue
        # match 级价格过滤:锚 end_node 事件日收盘价(= dev「突破当日价格」的对应物)。
        # 闭区间,照搬 dev BreakoutStrategy/analysis/scanner.py:262-263,不要改成开区间。
        buy_close = win["close"].iat[ev.start_idx]
        if price_min is not None and buy_close < price_min:
            continue
        if price_max is not None and buy_close > price_max:
            continue
        ret_by_id[m.event_id] = match_forward_returns(
            m, end_node, win, [label_horizon])[label_horizon]
        # mfr 下行镜像(min_low):同一买点窗、同一 horizon,与 forward_return 并列。
        dd_by_id[m.event_id] = match_forward_drawdowns(
            m, end_node, win, [label_horizon])[label_horizon]
        # 首穿四态计数:span 全买点日(与 forward_return 同循环、同过滤口径),
        # 累加进 per-pattern match_fp_counts(集合级 ratio 的分母=买点日数)。
        # match_first_passage 内算 M、几何对称 k;返单组 {up,down,both,none}。
        if first_passage_enabled:
            m_counts = match_first_passage(
                m, end_node, win, label_horizon, first_passage_k)
            for s in ("up", "down", "both", "none"):
                match_fp_counts[s] += m_counts[s]
    analysis = serialize_analysis(res)

    def _with_labels(md):
        return {**md,
                "forward_return": ret_by_id[md["event_id"]],
                "forward_drawdown": dd_by_id[md["event_id"]]}

    analysis["matches"] = [_with_labels(md)
                           for md in analysis["matches"] if md["event_id"] in ret_by_id]
    summary = summarize(res)
    summary["matches"] = len(analysis["matches"])

    rets = [md["forward_return"] for md in analysis["matches"]
            if md["forward_return"] is not None]
    max_ret = max(rets) if rets else None

    dds = [md["forward_drawdown"] for md in analysis["matches"]
           if md["forward_drawdown"] is not None]
    min_dd = min(dds) if dds else None

    return {"summary": summary, "analysis": analysis,
            "max_forward_return": max_ret, "min_forward_drawdown": min_dd,
            "match_fp_counts": match_fp_counts}
