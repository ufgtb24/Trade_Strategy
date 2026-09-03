"""per-node 诊断的 web 封装。

两条路径并存(Sprint 1 Task 8):
- legacy:`diagnose_symbol` / `serialize_diagnostics`——调 path2.dag.diagnose → 序列化整包
  NodeDiagnostics(§7.4)。现有 `/diagnose`(无 scope 参数)endpoint 走这条路,字节等价不变。
- 新版:`derive_response(query, diag=..., spec=...)`——scope-based query router(§3.1),
  4 scope(time / nodes / candidate / pair)按需只算一小片、附 caveats 说明哪些还没接上。
  Sprint 1 只落 scope=nodes 完整(消费 Task 1/3 的 RelRow.anchor_ok_count + miss_reasons +
  example_failed_pairs);其余 3 scope 落 stub,待 Sprint 2/3(Task 9-20)补齐。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

from path2.dag import diagnose as _diagnose
from path2.dag._solve import strict_clear, endpoint as _solve_endpoint
from path2.dag.edges import NegationEdge
from path2.dag.gate_failure import GateFailure
from path2_web.serialize import _clause_to_dict


def _attr_row(row) -> dict:
    return {
        "instance_id": row.event.instance_id,
        "node_id": row.event.node_id,
        "start_idx": row.event.start_idx,
        "end_idx": row.event.end_idx,
        "clauses": {cid: _clause_to_dict(w) for cid, w in row.clauses.items()},
    }


def _rel_row(row) -> dict:
    return {
        "src": row.src,
        "kind": row.kind,
        "total_src": row.total_src,
        "ok_count": len(row.ok_src),
        "ok_src_ids": [e.instance_id for e in row.ok_src],
    }


def serialize_diagnostics(diag) -> dict:
    """NodeDiagnostics → {nodes:{node_id:{attr,rel,produced_by}}, note}。

    实例流:attr 行直接读引擎物化标注的 instance_id/node_id(run_streams 内
    annotate_stream 注入),serialize 层不再编号——analyze 与 diagnose 共用
    run_streams(同 spec/df/params 下流完全一致),标注自动同源。"""
    return {
        "nodes": {
            nid: {
                "attr": [_attr_row(r) for r in rd.attr],
                "rel": [_rel_row(r) for r in rd.rel],
                "produced_by": rd.produced_by,   # 子结构 node 物化来源(独立 node 为 None)
            }
            for nid, rd in diag.nodes.items()
        },
        "note": diag.note,
    }


def diagnose_symbol(spec, df, params, *, symbol: str, pattern_id: str) -> dict:
    """对单股跑 per-node 诊断并序列化。spec 须与 params 一致(where 在 build_pattern 时闭合 params)。"""
    diag = _diagnose(spec, df, params)
    out = serialize_diagnostics(diag)
    out["symbol"] = symbol
    out["pattern_id"] = pattern_id
    return out


# ─── Sprint 1 Task 8:scope-based query router(§3.1) ─────────────────────────

@dataclass
class Query:
    """derive_response 的入参。symbol/scope 必填,其余按 scope 各取所需(未用字段留 None)。"""
    symbol: str
    scope: Literal["time", "nodes", "pair"]
    start_bar: Optional[int] = None
    end_bar: Optional[int] = None
    node: Optional[str] = None   # scope=time · 按 node_id 过滤 gate failure
    src_node: Optional[str] = None
    dst_node: Optional[str] = None
    event_id: Optional[str] = None
    src_event_id: Optional[str] = None
    dst_event_id: Optional[str] = None
    edge_id: Optional[str] = None


@dataclass
class Caveat:
    """挂在 Response 上的免责声明:哪块数据还没接上 · 为什么。"""
    code: str
    message: str
    affected_fields: List[str] = field(default_factory=list)


@dataclass
class PairFailure:
    """一对候选(src_event_id, dst_event_id)的失败归因。measured/threshold 待 Stage 2/3
    (on_gate,Task 13)落地后才有真值,Sprint 1 恒 None。"""
    src_event_id: str
    dst_event_id: str
    subcheck_stage: str
    measured: Optional[dict] = None
    threshold: Any = None
    edge_kind: str = "unknown"


@dataclass
class NodesPayload:
    """scope=nodes 的载荷:某条 node 边(src_node→dst_node)的通过率 + miss 分布 + 失败样例。"""
    edge_id: str
    total_pair: int
    ok_pair: int
    miss_reasons: Dict[str, int]
    example_failed_pairs: List[PairFailure]
    per_pair: Optional[List[PairFailure]] = None


@dataclass
class Response:
    scope: str
    payload: Any
    caveats: List[Caveat] = field(default_factory=list)


def derive_response(query: Query, *, diag=None, spec=None, result=None) -> Response:
    """一入口按 scope 分派。diag(NodeDiagnostics)/spec(PatternSpec)/result(AnalysisResult,
    Task 15 起可选,须已挂 collector 收过 gate_failures)由调用方注入(decoupled · 本函数不
    重算 / 不碰 registry·config——那是 endpoint 层的事)。scope=nodes 消费 diag;scope=time
    消费 result.gate_failures;其余 2 scope Sprint 2/3 落 stub,不需要 result。"""
    if query.scope == "nodes":
        return _derive_nodes_response(query, diag, spec)
    if query.scope == "time":
        return _derive_time_response(query, result=result, spec=spec)
    if query.scope == "pair":
        return _derive_pair_response(query, spec=spec, result=result)
    raise ValueError(f"unknown scope: {query.scope}")


def _derive_nodes_response(query: Query, diag, spec) -> Response:
    edge_id = f"{query.src_node}_to_{query.dst_node}"
    rd = diag.nodes.get(query.dst_node) if diag is not None else None
    rel_row = next((r for r in rd.rel if r.src == query.src_node), None) if rd is not None else None
    if rel_row is None:
        return Response(
            scope="nodes",
            payload=NodesPayload(edge_id=edge_id, total_pair=0, ok_pair=0,
                                 miss_reasons={}, example_failed_pairs=[]),
            caveats=[Caveat(code="no_such_edge",
                            message=f"dag_spec 中无 {edge_id} edge · src_node/dst_node 拼错或该边不存在")],
        )
    # edge_kind 直接取 rel_row.kind(diagnose.py::_rel_rows 已存 type(edge).__name__),
    # 不必像 brief 设想那样反查 spec.edges——RelRow 早已携带这条信息。
    example_pairs = [
        PairFailure(src_event_id=u, dst_event_id=v, subcheck_stage=stage,
                    measured=None, threshold=None, edge_kind=rel_row.kind)
        for (u, v, stage) in rel_row.example_failed_pairs
    ][:5]   # 双重兜底:_rel_rows 已 cap ≤5,这里再 slice 一次防未来产出方漏 cap
    return Response(
        scope="nodes",
        payload=NodesPayload(
            edge_id=edge_id,
            total_pair=rel_row.total_src,
            ok_pair=rel_row.anchor_ok_count,
            miss_reasons=dict(rel_row.miss_reasons),
            example_failed_pairs=example_pairs,
        ),
        caveats=_collect_caveats(spec),
    )


@dataclass
class TimePayload:
    """scope=time 载荷:用户框选窗口([start_bar, end_bar])内(严格 ⊆)的 gate 失败样例
    (Task 9-12 三 atom on_gate 吐出、worker 挂 collector 收进 result.gate_failures,Task 15)。
    all_nodes:该 pattern 全部 node_id 全集——前端下拉选项锚,让"存在但本区间无失败"
    的 node 可见(置灰)而非消失。过滤契约面是 gf.node_id(gate_collector wrapper 注入),
    故 all_nodes 取 spec node_id 与之对齐。"""
    frame: Tuple[int, int]
    failed_attempts: List[GateFailure]
    all_nodes: List[str] = field(default_factory=list)


def _in_frame_strict(fw: Tuple[int, int], frame: Tuple[int, int]) -> bool:
    """failure_event_window 严格 ⊆ user frame:两端都落在框内才算"真属于这段"。"""
    ws, we = fw
    fs, fe = frame
    return ws >= fs and we <= fe


def _derive_time_response(query: Query, *, result=None, spec=None) -> Response:
    """scope=time:消费 result.gate_failures(Task 15 起由 worker/端点挂 collector 收集),
    按 [query.start_bar, query.end_bar] 框严格过滤 + node 可选过滤。result 未注入
    (如端点层尚未 recompute+attach,Task 15 范围内不改 api.py)→ 空 payload +
    说明性 caveat,而非报错。"""
    frame = (query.start_bar if query.start_bar is not None else 0,
             query.end_bar if query.end_bar is not None else 0)
    # node 全集:该 pattern 全部 node(含子结构 node)——取 spec node_id(与 GateFailure.node_id
    # 的注入值同源);前端下拉据此显示"存在但本区间无失败"的选项(置灰)。
    spec_nodes = spec.nodes if spec is not None else ()
    all_nodes = sorted({n.node_id for n in spec_nodes})
    gate_failures = getattr(result, "gate_failures", None) if result is not None else None
    if gate_failures is None:
        return Response(
            scope="time",
            payload=TimePayload(frame=frame, failed_attempts=[], all_nodes=all_nodes),
            caveats=[Caveat(code="no_analysis_result",
                            message="未提供挂 collector 的 AnalysisResult · scope=time 需 endpoint 层 "
                                     "recompute + attach gate_failures(Task 15 范围外,留待接线)")],
        )

    def _node_ok(gf: GateFailure) -> bool:
        return query.node is None or gf.node_id == query.node

    filtered = [gf for gf in gate_failures
                if _in_frame_strict(gf.failure_event_window, frame) and _node_ok(gf)]
    caveats = _collect_caveats(spec)
    return Response(
        scope="time",
        payload=TimePayload(frame=frame, failed_attempts=filtered, all_nodes=all_nodes),
        caveats=caveats,
    )


# ─── Sprint 2 Task 16:pair 层 4 通道 subcheck helper ──────────────────────────
# 4 通道各自独立可评估:某个 (u, v) pair 在一条 edge 上
# feasible_window / satisfies / anchor / strict 是否分别过 gate。
# Task 17(scope=pair 消费)· Task 20(scope=candidate 复用,去重复代码)的共用基础设施。

@dataclass
class SubCheck:
    """单通道评估结果。measured 用 MeasuredKindAware-shape dict(承 Task 13 kind-aware,
    硬伤 E)——{"kind", "value", "label"};无实测量(anchor/strict)则 None。"""
    channel: str        # 'feasible_window' / 'satisfies' / 'anchor' / 'strict'
    passed: bool
    measured: Optional[dict]
    threshold: Any
    reason: Optional[str]


def _check_feasible_window(edge, u, v) -> SubCheck:
    """通道① feasible_window:v.start_idx 是否落 edge.feasible_window(u) 的闭区间内。
    每条 DependencyEdge 子类都实现 feasible_window(基类默认 (-inf,inf) 不剪枝),
    hasattr 分支纯防御性(理论上恒真)。"""
    gap = v.start_idx - u.end_idx
    measured = {"kind": "gap", "value": gap, "label": "gap"}
    if not hasattr(edge, "feasible_window"):
        return SubCheck(channel="feasible_window", passed=True, measured=None,
                        threshold=None, reason=None)
    lo, hi = edge.feasible_window(u)
    passed = lo <= v.start_idx <= hi
    return SubCheck(channel="feasible_window", passed=passed, measured=measured,
                    threshold={"min": lo, "max": hi},
                    reason=None if passed else f"gap {gap} 出 [{lo}, {hi}]")


def _check_satisfies(edge, u, v) -> SubCheck:
    """通道② satisfies:edge kind 自身的充要判据(见 edges.py 各子类 satisfies)。"""
    gap = v.start_idx - u.end_idx
    passed = edge.satisfies(u, v)
    return SubCheck(channel="satisfies", passed=passed,
                    measured={"kind": "gap", "value": gap, "label": "gap"},
                    threshold=None,
                    reason=None if passed else "satisfies 判据 fail")


def _check_anchor(edge, u, v) -> SubCheck:
    """通道③ anchor:dst 端 anchor_field 值是否等于 src 端 anchor_src_field 值
    (edges.py:91 DependencyEdge._anchor_ok,整改四 B4)。real API 是 edge 的实例方法、
    无 edge_ok_map 参数(与 brief 早期设想不同);anchor_field 未声明(None)时 _anchor_ok
    自身恒 True,不必在此重复判断。hasattr 兜底: 若某 edge 对象没有 _anchor_ok(理论上只有
    DependencyEdge 及其子类才有 —— 即所有真实 edge),视为通过。"""
    if hasattr(edge, "_anchor_ok"):
        passed = edge._anchor_ok(u, v)
    else:
        passed = True
    return SubCheck(channel="anchor", passed=passed, measured=None, threshold=None,
                    reason=None if passed else "anchor 破位")


def _check_strict(edge, u, v, streams: dict) -> SubCheck:
    """通道④ strict:next 语义严格清空(仅 TemporalEdge.strict=True 生效),
    复用 _solve.py:137 strict_clear。非 strict 边直接 pass,不必跑 strict_clear
    (streams 可能不完整/为空,strict_clear 内部也会因 getattr(edge,'strict',False)
    为 False 而短路返回 True——这里提前短路只是省一次函数调用,行为一致)。"""
    if not getattr(edge, "strict", False):
        return SubCheck(channel="strict", passed=True, measured=None, threshold=None, reason=None)
    passed = strict_clear(edge, u, v, streams)
    return SubCheck(channel="strict", passed=passed, measured=None, threshold=None,
                    reason=None if passed else "strict 有更早候选")


# ─── Sprint 2 Task 17:scope=pair 完整实现(auto swap + 4 subcheck 短路 + 5 invalid_reason) ──
# 用户 shift+click 两个 marker → (src_event_id, dst_event_id) → 查两 node 间是否有 edge 直连、
# 若有则跑 4 通道 subcheck(短路)。forward 无 edge 但 reverse 有 → 自动切换方向(auto swap),
# payload 保留 original_first_click/original_second_click 供前端撤回提示。

@dataclass
class PairPayload:
    """scope=pair 的载荷。src/dst_event_id 是"生效方向"(auto swap 后可能与用户实际点击顺序
    相反);original_first_click/original_second_click 恒等于用户真实点击顺序,供前端渲染
    "已为你交换方向"提示 + 撤回。invalid 时 edge_id/edge_kind/subchecks 恒 None。"""
    src_event_id: str
    dst_event_id: str
    applied_swap: bool
    original_first_click: str
    original_second_click: str
    valid: bool
    invalid_reason: Optional[str]
    edge_id: Optional[str]
    edge_kind: Optional[str]
    subchecks: Optional[List[SubCheck]] = None
    hint: Optional[dict] = None


def _load_event_by_id(result, event_id: Optional[str]):
    """从 result.events(去重平铺流)按 instance_id 找单个 Event;找不到 / result 未注入 → None。
    参数名保留 event_id(前端 query 字段名),值/查找用 instance_id。"""
    if result is None or event_id is None:
        return None
    return next((e for e in result.events if e.instance_id == event_id), None)


def _node_of_event(spec, event) -> Optional[str]:
    """event 所属 node(node_id):直接读物化标注的 event.node_id(run_streams 内
    annotate_stream 注入)。找不到(spec/result 不一致的防御性场景)→ None。"""
    return event.node_id


def _find_edge(spec, src_node: str, dst_node: str, *, exclude_negation: bool = True):
    """spec.edges 里找 src_node→dst_node 方向的正向依赖边。exclude_negation=True(默认):
    NegationEdge 是全称约束(禁止关系),不是用户可"通/不通"逐 pair 导航的依赖边,故 pair 层
    only_negation_edge 单列一个 invalid_reason,不当普通 edge 用。"""
    for e in spec.edges:
        if exclude_negation and isinstance(e, NegationEdge):
            continue
        if e.src == src_node and e.dst == dst_node:
            return e
    return None


def _only_negation_between(spec, u_node: str, v_node: str) -> bool:
    """两 node 间(不分方向)是否*只*有 NegationEdge、没有任何正向依赖边。"""
    has_neg = False
    for e in spec.edges:
        if {e.src, e.dst} == {u_node, v_node}:
            if isinstance(e, NegationEdge):
                has_neg = True
            else:
                return False
    return has_neg


def _invalid_pair_response(query: Query, invalid_reason: str) -> Response:
    hint = None
    if invalid_reason == "no_edge_between_nodes":
        hint = {"suggestion": "两 node 在 dag_spec 中无直连 edge"}
    elif invalid_reason == "only_negation_edge":
        hint = {"suggestion": "两 node 间只有 NegationEdge(全称禁止约束,非可导航依赖边)"}
    return Response(
        scope="pair",
        payload=PairPayload(
            src_event_id=query.src_event_id, dst_event_id=query.dst_event_id,
            applied_swap=False,
            original_first_click=query.src_event_id,
            original_second_click=query.dst_event_id,
            valid=False, invalid_reason=invalid_reason,
            edge_id=None, edge_kind=None, subchecks=None, hint=hint,
        ),
        caveats=[],
    )


def _pair_response_with(query, edge, u, v, subchecks, applied_swap, spec) -> Response:
    """valid=True 分支的 Response 组装。src/dst_event_id 取生效方向的 u.instance_id/v.instance_id
    (auto swap 时已是交换后的顺序);original_*_click 恒是用户真实点击顺序。"""
    return Response(
        scope="pair",
        payload=PairPayload(
            src_event_id=u.instance_id, dst_event_id=v.instance_id,
            applied_swap=applied_swap,
            original_first_click=query.src_event_id,
            original_second_click=query.dst_event_id,
            valid=True, invalid_reason=None,
            edge_id=f"{edge.src}_to_{edge.dst}",
            edge_kind=type(edge).__name__,
            subchecks=subchecks,
        ),
        caveats=_collect_caveats(spec),
    )


def _check_pair_and_respond(query, edge, u, v, *, applied_swap, spec, result) -> Response:
    """合法 pair(edge 已定方向)· 4 subcheck 短路 · 组装 Response。

    端点投影(承 path2/dag/diagnose.py::_rel_rows 真实引擎口径,非 brief 字面 pseudocode):
    edge 可能带 Child selector(如 bottom_burst 的 burst→tb 边,
    src_selector='last_bo')——feasible_window/satisfies/anchor 必须吃*投影后*的端点
    (a=endpoint(u,'src'),b=endpoint(v,'dst')),否则 anchor 复核会拿 burst 自身身份
    去比对 tb.anchor_bo_id(恒错,anchor_bo_id 语义是"触发 bo 的 span 身份"而非"burst 的
    身份")。strict 通道例外:引擎真实调用是 strict_clear(edge, a, e_r, streams)——
    e_r 是 dst 流里的*原始整体*事件(next 语义比较的是候选在 dst 流中的位置,不是投影后的
    子对象),故这里传原始 v 而非投影 b,与 _rel_rows 逐字一致。"""
    a = _solve_endpoint(u, edge, which="src")
    b = _solve_endpoint(v, edge, which="dst")
    streams = getattr(result, "event_streams", {}) if result is not None else {}
    subchecks: List[SubCheck] = []
    for check, args in (
        (_check_feasible_window, (edge, a, b)),
        (_check_satisfies, (edge, a, b)),
        (_check_anchor, (edge, a, b)),
    ):
        sc = check(*args)
        subchecks.append(sc)
        if not sc.passed:
            return _pair_response_with(query, edge, u, v, subchecks, applied_swap, spec)
    sc = _check_strict(edge, a, v, streams)
    subchecks.append(sc)
    return _pair_response_with(query, edge, u, v, subchecks, applied_swap, spec)


def _derive_pair_response(query: Query, *, spec=None, result=None) -> Response:
    """scope=pair 主入口。spec/result 由 endpoint 层注入(同 scope=time 的 decoupled 模式,
    Task 15);spec 未显式传入时兜底 result.spec(AnalysisResult 自带 spec 字段)。二者皆缺
    (端点层尚未 recompute+attach,同 Task 15/16 遗留的系统性 gap)→ 诚实降级 stub + caveat,
    不臆造 domain 判定。"""
    spec = spec if spec is not None else getattr(result, "spec", None)
    if result is None or spec is None:
        return Response(
            scope="pair", payload={"stub": True},
            caveats=[Caveat(code="no_analysis_result",
                            message="scope=pair 需注入 spec + 已挂 collector 的 AnalysisResult · "
                                     "endpoint 层尚未 recompute+attach(同 Task 15/16 遗留 gap)")],
        )

    u = _load_event_by_id(result, query.src_event_id)
    v = _load_event_by_id(result, query.dst_event_id)
    if u is None or v is None:
        return _invalid_pair_response(query, "event_not_found")

    u_node = _node_of_event(spec, u)
    v_node = _node_of_event(spec, v)
    if u_node is not None and u_node == v_node:
        return _invalid_pair_response(query, "same_node")

    forward_edge = _find_edge(spec, u_node, v_node, exclude_negation=True)
    reverse_edge = _find_edge(spec, v_node, u_node, exclude_negation=True)

    if forward_edge is not None:
        return _check_pair_and_respond(query, forward_edge, u, v,
                                       applied_swap=False, spec=spec, result=result)
    if reverse_edge is not None:
        return _check_pair_and_respond(query, reverse_edge, v, u,
                                       applied_swap=True, spec=spec, result=result)
    if _only_negation_between(spec, u_node, v_node):
        return _invalid_pair_response(query, "only_negation_edge")
    return _invalid_pair_response(query, "no_edge_between_nodes")


def _collect_caveats(spec=None) -> List[Caveat]:
    caveats: List[Caveat] = []
    # 硬伤 E · Sprint 2 Task 13 修 · 未修则挂(EdgeWitness.measured 尚未 kind-aware)
    if not _kind_aware_measured_available():
        caveats.append(Caveat(code="measured_not_kind_aware",
                              message="EdgeWitness.measured 未升级 kind-aware(硬伤 E)"))
    return caveats


def _kind_aware_measured_available() -> bool:
    # Task 13 已修 EdgeWitness.measured kind-aware · probe 指向真实定义处(path2.dag.gate_failure)
    try:
        from path2.dag.gate_failure import MeasuredKindAware  # noqa: F401
        return True
    except ImportError:
        return False
