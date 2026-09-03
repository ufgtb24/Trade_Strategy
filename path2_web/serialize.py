"""dag 对象 → jsonable dict 投影层(纯函数,不读文件/不起服务)。

消费 path2.dag 只读数据结构(AnalysisResult/PatternMatch/PredicateTrace/ClauseWitness/
EdgeWitness/PatternTopology/NodeDiagnostics),投影成前端 JSON。path2 不引入 JSON 依赖。

实例化契约:事件已由引擎物化标注(node_id/instance_idx/instance_id),serialize 层
只做纯投影、不再编号;match 行按 match_id 投影、node_index/children 值统一为
instance_id 字符串。身份契约统一为 node_id/instance_id 双轴(旧 event_id/
source_tag/instance_key 等字段已全部消灭),不在任何输出中出现。
"""
from __future__ import annotations

import dataclasses
import functools
import inspect
import math
import typing

import pandas as pd

from path2 import Event
from path2.eval import _resolve_end_events   # end_node 路径解析(与 eval 同一函数,无循环依赖)


def _mentions_event(tp) -> bool:
    """类型对象(不是字符串)是否在其结构中提及 Event(含子类)。递归
    typing.get_args 穿透 Tuple/tuple/Optional/Sequence/Mapping 等泛型容器。"""
    if tp is None:
        return False
    if isinstance(tp, type):
        try:
            return issubclass(tp, Event)
        except TypeError:
            return False
    return any(_mentions_event(a) for a in typing.get_args(tp))


@functools.lru_cache(maxsize=None)
def _ref_field_names(cls) -> "frozenset[str]":
    """cls 声明类型里"提及 Event"的字段名集合——ref_slots() 协议底层引用字段
    (如 broken_refs/superseded_refs)的结构性判据:字段类型出现 Event(含子类)
    就跳过 fields 平铺,不依赖字段名单/槽名字符串(槽名与字段名并不同名,如
    "broken"≠"broken_refs"),也不依赖 ref_slots() 运行期是否 populated(未
    populated 时 ref_slots() 返回空 dict,取不到字段名)。

    typing.get_type_hints 需要解析注解到真实类型对象,对函数局部定义的类
    (前向引用在类所在模块的 globalns 里找不到局部名)会抛 NameError 等异常;
    此时退回按字面注解字符串判断(是否含 "Event" token)——退回绝不能是"不
    跳过":不跳过 = 原始事件对象重新递归展开进 payload,即本 task 要修的
    39.8%/6 层嵌套膨胀原样复发。按 cls 缓存,每个事件类只解析一次。"""
    try:
        hints = typing.get_type_hints(cls)
    except Exception:
        return frozenset(
            f.name for f in dataclasses.fields(cls)
            if isinstance(f.type, str) and "Event" in f.type
        )
    return frozenset(
        f.name for f in dataclasses.fields(cls) if _mentions_event(hints.get(f.name))
    )


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

    事件行新契约:instance_id/node_id/instance_idx 恒在(引擎物化标注,serialize
    不再编号);持有型 child 走 child_refs、引用型 ref 走 ref_ids,原始对象字段
    一律不进 payload(schema-driven,不硬编码字段名):child_slots 声明的槽名
    对应字段在 fields 循环里跳过(slot 名与字段名同名,如 members/segments);
    ref_slots 协议持有的原始引用字段(broken_refs/superseded_refs 等)按声明
    类型结构性跳过(_ref_field_names:字段类型里出现 Event 就跳过,不区分具体
    写法 Tuple[Event,...]/Optional[Event]/前向引用)——不依赖 ref_slots() 的
    槽名(与字段名不同名,如 broken_refs 槽名是 "broken")、也不依赖 ref_slots()
    在未 populated 时返回空 dict(跳过判据需对空/非空一致生效)。ref_ids 字段
    本身亦跳过 fields 平铺,由末尾显式赋值产生。旧身份字段(测试 fixture 自带
    的 event_id 等)不再输出。
    """
    d = {
        "instance_id": e.instance_id,
        "node_id": e.node_id,
        "instance_idx": e.instance_idx,
        "start_idx": e.start_idx,
        "end_idx": e.end_idx,
    }
    slots = e.child_slots()
    skip_slots = set(slots.keys())   # BurstEvent -> {"members"}
    ref_fields = _ref_field_names(type(e))   # {"broken_refs"} / {"superseded_refs"} 等
    for f in dataclasses.fields(e):
        if f.name in ("event_id", "start_idx", "end_idx", "instance_id",
                      "node_id", "instance_idx", "ref_ids"):
            continue   # event_id 亦跳过:测试 fixture 自带,保证 payload 零 event_id;
                       # ref_ids 见下方末尾显式赋值,不走 fields 平铺
        if f.name in skip_slots:
            continue   # 由 child_refs 承载,避免 payload 冗余
        if f.name in ref_fields:
            continue   # ref_slots() 协议底层字段;由 ref_ids 承载
        d[f.name] = _jsonable(getattr(e, f.name))
    d["child_refs"] = {
        name: [c.instance_id for c in (slot if isinstance(slot, tuple) else (slot,))]
        for name, slot in slots.items()
    }
    d["ref_ids"] = {slot: list(ids) for slot, ids in e.ref_ids}
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
        "src": ew.src_instance.instance_id,
        "dst": ew.dst_instance.instance_id,
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
    """match → dict。match_id 为 match 唯一键;node_index 每节点值 = instance_id
    字符串(与事件行同源);children = instance_id 列表。旧身份字段不再输出。"""
    return {
        "match_id": m.match_id,
        "start_idx": m.start_idx,
        "end_idx": m.end_idx,
        "node_index": {
            nid: e.instance_id
            for nid, e in (m.node_index or {}).items()
        },
        "children": [e.instance_id for e in m.children],
        "predicate_trace": _trace_to_dict(m.predicate_trace) if m.predicate_trace else None,
    }


def serialize_analysis(res) -> dict:
    """AnalysisResult → {events:[...], matches:[...]}(每只命中股一份,§7.2)。

    纯投影:事件行/匹配行直接读引擎标注的 instance_id/node_id/instance_idx/match_id,
    serialize 层不编号、不附加任何旧身份字段。容器 child(如 tb.segments)不在
    res.events/match.children,主动从各容器的 child_slots 挖出追加(非递归,仅一级;
    schema 稳定,老 scan 兼容),去重键 = 对象身份 id(c)。
    """
    out_events = [_event_to_dict(e) for e in res.events]
    extra = []
    seen = {id(e) for e in res.events}
    for e in res.events:
        for slot in e.child_slots().values():
            members = slot if isinstance(slot, tuple) else (slot,)
            for c in members:
                if id(c) not in seen:
                    seen.add(id(c))
                    extra.append(_event_to_dict(c))
    out_events.extend(extra)
    return {"events": out_events, "matches": [_match_to_dict(m) for m in res.matches]}


def summarize(res) -> dict:
    """{node_id: count} ∪ {"matches": n}(命中股列表的计数徽章,§7.3)。
    node_id 为 None(未标注事件)跳过。"""
    counts: dict = {}
    for e in res.events:
        if e.node_id is None:
            continue
        counts[e.node_id] = counts.get(e.node_id, 0) + 1
    counts["matches"] = len(res.matches)
    return counts


# ── pattern 静态层(拓扑面板数据源,§7.1) ──
# event_styles 兜底调色板:PATTERN_DAG.event_styles 默认空,按 topology.nodes 里 node_id
# 首次出现顺序 setdefault(见 _event_styles),索引 i 就是"第 i 个新 node_id"。当前拓扑覆盖
# (apps 均无显式 event_styles 声明,全走兜底;bottom_burst 首现序 bo/burst/tb/tb_seg):
#   [0] bo     (bottom_burst / bo_only 的首个 node_id;主图 price-anchored [ids] 方框)
#   [1] burst  (bottom_burst 的第二个 node_id;副图 interval)
#   [2] tb     容器红(用户手调值;tb_seg 用饱和绿——与 bo 兜底绿同色会触发
#   [3] tb_seg deriveNodeColors 明度散开,段被分到过浅的亮端)
#   [4..6]     未占用,给未来新 node_id 兜底(顺序即分配序,i % len 循环)
_PALETTE = ["#16f943", "#2563eb", "#FF1500", "#14b24e", "#7c3aed", "#0891b2", "#ca8a04"]

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
    """事件样式:spec.event_styles 显式值优先,未覆盖的 node_id 按 topology.nodes
    首现序 setdefault 兜底调色板。键 = node_id。"""
    styles = dict(spec.event_styles or {})
    seen = []
    for n in topo.nodes:
        if n.node_id not in seen:
            seen.append(n.node_id)
    for i, t in enumerate(seen):
        styles.setdefault(t, _PALETTE[i % len(_PALETTE)])
    return styles


def _materialize_keys_of(det) -> list[str]:
    """detector 构造参数键(去 self)= 物化层 yaml 键。

    依据 author 约定:进 detector __init__ 的参数 = 物化层(决定 event 是否生成),
    留在 node.where 的 = where 层(决定是否升 match)。反射 __init__ 签名精确捕获此约定,
    比 params.*_kwargs(手挑、可能漂移)更源头。
    子结构 node(produced_by 非空)无 detector → 无物化层参数,返回空。
    """
    if det is None:
        return []
    sig = inspect.signature(type(det).__init__)
    return [name for name in sig.parameters if name != "self"]


def serialize_pattern(spec) -> dict:
    """PatternSpec → {pattern_id, topology{nodes,edges}, event_styles}(§7.1)。
    topology 来自 to_topology() + 每节点 where_rules(静态阈值,无实测值)。
    节点以 node_id 为唯一键(旧身份字段体系已消灭,不再输出)。"""
    topo = spec.to_topology()
    by_id = {n.node_id: n for n in spec.nodes}
    nodes = []
    for tn in topo.nodes:
        n = by_id[tn.node_id]
        node = {
            "node_id": tn.node_id,
            "solve": bool(getattr(n, "solve", True)),   # 求解参与标志(solve=False 只显示;前端 level 免疫判据)
            "where_rules": _rules_from_where(n.where),
            "render_grid": n.render_grid,   # ★ 新增:透传 NodeSpec.render_grid
            "materialize_keys": _materialize_keys_of(n.detector),
            "produced_by": n.produced_by,   # 子结构 node 物化来源(独立 node 为 None)
            "child_slot": tn.child_slot,    # 子结构 node 在父的 slot 名(独立 node 为 None)
            "parent_refs": [list(r) for r in tn.parent_refs],  # 被哪些父 children 引用(独立 node 也收录)
        }
        nodes.append(node)
    # to_topology().edges 与 spec.edges 同序一一对应 → zip(避免多重边 key 冲突)
    edges = [
        {"src": te.src, "dst": te.dst, "kind": te.kind, "rule": _edge_rule(de),
         "anchor_field": de.anchor_field}
        for te, de in zip(topo.edges, spec.edges)
    ]
    # v4 契约 C:派生 debug_enabled_nodes(has_debug_hooks=True 的 detector 的 node_id 去重,拓扑序)
    debug_enabled_nodes: list[str] = []
    seen: set[str] = set()
    for n in spec.nodes:
        if n.detector is None:
            continue   # 子结构 node 无 detector,无 debug hooks
        det_cls = type(n.detector)
        if getattr(det_cls, "has_debug_hooks", False) and n.event_cls is not None:
            nid = n.node_id
            if nid not in seen:
                seen.add(nid)
                debug_enabled_nodes.append(nid)

    return {
        "pattern_id": spec.pattern_id,
        "topology": {"nodes": nodes, "edges": edges},
        "event_styles": _event_styles(spec, topo),
        "debug_enabled_nodes": debug_enabled_nodes,
    }


def serialize_per_pattern_result(res, end_node: str, label_horizon: int,
                                  win, start_ts, end_ts,
                                  price_min=None, price_max=None, *,
                                  first_passage_enabled: bool = True,
                                  first_passage_k: float = 5.0,
                                  sample_window=None) -> dict:
    """单股单 pattern 投影,服务多 pattern worker。

    args:
        res: AnalysisResult(已 analyze 完整 buf_win)
        end_node: pattern 的买点 node(从 eval_meta 取)
        label_horizon: 前瞻收益天数
        win: 已切好的 DataFrame(含 date 列 + OHLC)
        start_ts/end_ts: pd.Timestamp,严格窗左右边界(含)
        price_min/price_max: match 级价格过滤区间(闭区间,None=不限)。锚 end_node
            事件日收盘价(路径=任一段起点日)——与窗口过滤、forward_return 共用
            同一 _resolve_end_events 解析。
        first_passage_enabled: 是否累加首次穿越四态计数到 match_fp_counts(默认 True)。
            关闭时 match_fp_counts 为单组全 0 {up,down,both,none};每条 match 的
            first_passage 字段恒为 None。
        first_passage_k: 首次穿越几何对称阈值参数 k(上行 P(1+kM)、下行 P/(1+kM)),
            match_first_passage 内算 M;默认 5.0。
        sample_window: 样本消费窗(spec §10 截取),win 行号双边含端 (lo, hi)——
            forward_return / forward_drawdown / first_passage 的买点日 t 仅当
            lo <= t <= hi 计样本,跨界段只取窗内部分;None = 全量(向后兼容)。
            label 前瞻窗不受截取影响(仍看未来 N 根)。matches 过滤口径不变
            (任一段起点 ∈ [start_ts, end_ts])。

    返回 {summary, analysis, max_forward_return, min_forward_drawdown, match_fp_counts}:
      - analysis.events: 全集照旧(含缓冲段;K 线灰色层数据源)
      - analysis.matches: 仅保留 end_node 事件**任一**起点 ∈ [start_ts, end_ts] 且
                          **任一**收盘价 ∈ [price_min, price_max] 的 match(任一过滤,
                          统一标准协议;路径=各 child span bar 并集),每条注入
                          forward_return + forward_drawdown(mfr 下行镜像)+ buy_date
                          (end_node 事件起始日,YYYY-MM-DD)+ first_passage(该 match
                          leaf 首次出现时的四态 dict,同 leaf 的后续 match 为 None,
                          first_passage_enabled=False 时恒 None;逐 match 非 None
                          四态求和 = match_fp_counts)
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
    leaf_by_id: dict = {}
    fp_by_id: dict = {}
    date_by_id: dict = {}
    seen_fp_leaves: set = set()
    match_fp_counts = {"up": 0, "down": 0, "both": 0, "none": 0}
    for m in res.matches:
        events = _resolve_end_events(m, end_node)          # 统一解析(与 eval 同函数)
        if not any(start_ts <= win["date"].iat[ev.start_idx] <= end_ts
                   for ev in events):
            continue
        # match 级价格过滤: 任一 tb_seg 起点日收盘价 ∈ [price_min, price_max]。
        # 闭区间,照搬 dev BreakoutStrategy/analysis/scanner.py:262-263,不要改成开区间。
        closes = [win["close"].iat[ev.start_idx] for ev in events]
        if not any((price_min is None or c >= price_min)
                   and (price_max is None or c <= price_max) for c in closes):
            continue
        # leaf 锚容器(match 身份; tb_seg 段渲染已由 serialize_analysis 挖 child 承担)。
        # 实例流:leaf = end_node 事件 instance_id 字符串(instance_id 已含组内 #idx,
        # 无需 indexer 再编号)。
        leaf_ev = m.node_index[end_node.split(".")[0]]
        leaf_by_id[m.match_id] = leaf_ev.instance_id
        date_by_id[m.match_id] = str(pd.to_datetime(win["date"].iat[leaf_ev.start_idx]).date())
        ret_by_id[m.match_id] = match_forward_returns(
            m, end_node, win, [label_horizon],
            sample_window=sample_window)[label_horizon]
        # mfr 下行镜像(min_low):同一买点窗、同一 horizon,与 forward_return 并列
        # (Task 7 裁定 a:dd 同窗截取,避免 ret 截/dd 全量的样本日分裂破坏 ret ≥ dd 不变量)。
        dd_by_id[m.match_id] = match_forward_drawdowns(
            m, end_node, win, [label_horizon],
            sample_window=sample_window)[label_horizon]
        # 首穿四态计数:span 全买点日(与 forward_return 同循环、同过滤口径)。
        # 共享 leaf 的多 match 只累加一次(买点日是物理属性,与上游 match 数无关),
        # 保持「ratio 分母=买点日数」契约(scan.py:169-170 与随机基线同口径)。
        # 实例流:去重键 = leaf_ev.instance_id(含 #idx,同事件不同实例天然可区分)。
        # match_first_passage 内算 M、几何对称 k;返单组 {up,down,both,none}。
        fp_by_id[m.match_id] = None
        if first_passage_enabled:
            if leaf_ev.instance_id not in seen_fp_leaves:
                seen_fp_leaves.add(leaf_ev.instance_id)
                m_counts = match_first_passage(
                    m, end_node, win, label_horizon, first_passage_k,
                    sample_window=sample_window)
                for s in ("up", "down", "both", "none"):
                    match_fp_counts[s] += m_counts[s]
                fp_by_id[m.match_id] = {s: int(m_counts[s]) for s in ("up", "down", "both", "none")}
    analysis = serialize_analysis(res)

    def _with_labels(md):
        return {**md,
                "forward_return": ret_by_id[md["match_id"]],
                "forward_drawdown": dd_by_id[md["match_id"]],
                "leaf": leaf_by_id[md["match_id"]],   # instance_id 字符串
                "buy_date": date_by_id[md["match_id"]],
                "first_passage": fp_by_id[md["match_id"]]}

    analysis["matches"] = [_with_labels(md)
                           for md in analysis["matches"] if md["match_id"] in ret_by_id]
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
