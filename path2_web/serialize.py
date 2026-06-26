"""dag 对象 → jsonable dict 投影层(纯函数,不读文件/不起服务)。

消费 path2.dag 只读数据结构(AnalysisResult/PatternMatch/PredicateTrace/ClauseWitness/
EdgeWitness/PatternTopology/RoleDiagnostics),投影成前端 JSON。path2 不引入 JSON 依赖。
"""
from __future__ import annotations

import dataclasses
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
    d = {
        "class_id": type(e).class_id,
        "event_id": e.event_id,
        "start_idx": e.start_idx,
        "end_idx": e.end_idx,
    }
    for f in dataclasses.fields(e):
        if f.name in ("event_id", "start_idx", "end_idx"):
            continue
        val = getattr(e, f.name)
        # composite event 的 members:扁平为 event_id 列表(供前端 matchedIds 沿 members 递归展开)
        if (f.name == "members" and isinstance(val, tuple) and val
                and hasattr(val[0], "event_id")):
            d[f.name] = [m.event_id for m in val]
        else:
            d[f.name] = _jsonable(val)
    return d


# ── per-match 判定(reify 富化产物) ──
def _clause_to_dict(w) -> dict:
    """ClauseWitness → dict(satisfied/measured/op/threshold)。"""
    return {
        "satisfied": bool(w.satisfied),
        "measured": _jsonable(w.measured),
        "op": w.op,
        "threshold": _jsonable(w.threshold),
    }


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
    def _role(v):
        return v.event_id

    return {
        "event_id": m.event_id,
        "start_idx": m.start_idx,
        "end_idx": m.end_idx,
        "role_index": {nid: _role(v) for nid, v in (m.role_index or {}).items()},
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
# event_styles 兜底调色板:PATTERN_DAG.event_styles 默认空,按 topology 出现的 class_id 确定性补齐。
_PALETTE = ["#f59e0b", "#2563eb", "#16a34a", "#dc2626", "#7c3aed", "#0891b2", "#ca8a04"]


def _rules_from_where(where_clauses) -> list:
    """(clause_id, fn) 序列 → [{clause_id, op, threshold}]。
    fn 是 W.* 的 _Pred,带 .meta={'kind','field','op','threshold'};组合子 meta=None,跳过。
    W.child/W.children 额外携带 kind/key + inner 的 field/op/threshold(扁平 rule,§3.1)。"""
    out = []
    for cid, fn in where_clauses:
        meta = getattr(fn, "meta", None)
        if not meta:
            continue
        kind = meta.get("kind")
        if kind in ("child", "children"):
            inner = meta.get("inner") or {}
            out.append({
                "clause_id": cid,
                "kind": kind,
                "key": meta.get("key"),
                "field": inner.get("field"),
                "op": inner.get("op"),
                "threshold": _jsonable(inner.get("threshold")),
            })
        else:
            out.append({"clause_id": cid, "op": meta.get("op"),
                        "threshold": _jsonable(meta.get("threshold"))})
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
    """PatternSpec → {pattern_id, display_name, topology{nodes,edges}, event_styles}(§7.1)。
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
            "label": tn.label,
            "where_rules": _rules_from_where(n.where),
            "source_tag": _source_tag_of(n.detector),
            "render_grid": n.render_grid,   # ★ 新增:透传 NodeSpec.render_grid
        }
        nodes.append(node)
    # to_topology().edges 与 spec.edges 同序一一对应 → zip(避免多重边 key 冲突)
    edges = [
        {"src": te.src, "dst": te.dst, "kind": te.kind, "rule": _edge_rule(de)}
        for te, de in zip(topo.edges, spec.edges)
    ]
    return {
        "pattern_id": spec.pattern_id,
        "display_name": spec.display_name,
        "topology": {"nodes": nodes, "edges": edges},
        "event_styles": _event_styles(spec, topo),
    }
