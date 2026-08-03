# path2/dag/engine.py
"""公开入口:analyze(spec, df, params) -> AnalysisResult。app 零参与。

阶段1 detector 编排(按 consumes_stream 排序,run 产流);
阶段2 compile_plan;阶段3 solve() 唯一求解函数;阶段4 reify。

detector 按真实入参调用:root(consumes_stream=None)只吃 df → detect(df);
消费者吃 (上游流, df) → detect(bos, df)。对照 path2/atoms:bo/trend/distribution/
platform.detect(self, df);throwback/burst.detect(self, bos, df)。run(detector, *source)
透传给 detect,故按 consumes_stream 决定传 1 个还是 2 个 source。
"""
from __future__ import annotations

from path2.runner import run
from path2.dag.result import AnalysisResult, DroppedMatch
from path2.dag._graph import detector_topo_order
from path2.dag._solve import compile_plan, solve
from path2.dag._reify import reify


def assign_auto_source_tags(nodes) -> None:
    """同 class_id 有 ≥2 个 distinct detector 对象时,按 nodes 首现序给未显式设 source_tag
    的对象填 f"{class_id}{i}",使 event_id 前缀不撞。单实例/共享对象/已显式 source_tag 的
    不动 → event_id 向后兼容逐字不变。幂等。"""
    by_class: dict = {}                         # dict 保留插入序(Py3.7+)
    for n in nodes:
        det = n.detector
        if not hasattr(det, "event_cls"):        # 不参与 class_id 身份体系的 detector 无 event_id 可撞,跳过
            continue
        cid = det.event_cls.class_id
        bucket = by_class.setdefault(cid, [])
        if all(d is not det for d in bucket):   # 按对象身份去重
            bucket.append(det)
    for cid, dets in by_class.items():
        if len(dets) < 2:
            continue
        for i, det in enumerate(dets):
            if not hasattr(det, "source_tag"):
                raise ValueError(
                    f"{type(det).__name__} 产 class_id={cid!r} 出现多实例,"
                    f"但无 source_tag 钩子无法自动消歧;请给该 detector 加 source_tag 支持"
                )
            if det.source_tag is None:           # 仅填未显式设的(尊重手动命名)
                det.source_tag = f"{cid}{i}"


def run_streams(spec, df, params=None):
    """阶段1:detector 依赖排序 + 跑流。返回 {node_id: [Event]}。
    analyze 与 diagnose(path2/dag/diagnose.py)共用,避免重复 detect。

    去重:同一 detector 对象在同一 consumes_stream 上只物化一次(key=(id(detector),consumes_stream))。
    多个 node_id 共享同一 detector 时,它们的 streams[nid] 指向同一个 list 对象。"""
    assign_auto_source_tags(spec.nodes)          # 同类多实例自动消歧(单/共享→no-op)
    by_id = {n.node_id: n for n in spec.nodes}
    streams = {}
    materialized = {}
    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        key = (id(node.detector), node.consumes_stream)  # 两元都必需:同一 detector 喂不同输入流不可折叠(裸 id 会串错流)
        if key not in materialized:
            if node.consumes_stream is None:
                materialized[key] = list(run(node.detector, df))
            else:
                materialized[key] = list(run(node.detector, streams[node.consumes_stream], df))
        streams[nid] = materialized[key]
    return streams


def analyze(spec, df, params=None) -> AnalysisResult:
    """DAG 走势包 analyze:抽出 streams → compile plan → solve → reify matches。
    返回 AnalysisResult(events / matches / spec / dropped_matches / gate_failures)。"""
    streams = run_streams(spec, df, params)                 # 阶段1(抽出)
    plan = compile_plan(spec)                                # 阶段2
    sols = solve(plan, streams)                               # 阶段3
    matches_out = tuple(reify(s, streams, plan) for s in sols)  # 阶段4
    # A2:丢弃「node_index 只含『孤立无边 AND 被消费』node」的残缺 match。
    # 原意:流源 node(被别 node 的 consumes_stream 引用)单独命中是"被回显"的噪声、
    # 非业务 pattern。判据加 consumes_stream 反向引用过滤,避免误伤「全孤立 pattern」
    # (如 bo_only,单节点零边、无消费者)——其平凡 match 是唯一业务命中,合法保留。
    isolated_consumed = (
        {n.node_id for n in spec.nodes}
        - {ep for edge in spec.edges for ep in (edge.src, edge.dst)}
    ) & {n.consumes_stream for n in spec.nodes if n.consumes_stream is not None}
    dropped_matches: tuple = ()
    if isolated_consumed:
        surviving, dropped = [], []
        for m in matches_out:
            if set((m.node_index or {}).keys()).issubset(isolated_consumed):
                dropped.append(DroppedMatch(
                    match_id=m.event_id,
                    node_events={r: e.event_id for r, e in (m.node_index or {}).items()},
                    drop_reason="isolated_consumed",
                ))
            else:
                surviving.append(m)
        matches_out = tuple(surviving)
        dropped_matches = tuple(dropped)
    # res.events 按 stream 身份(id(s))去重:共享 detector 时多个 node_id 指同一 list,
    # 朴素平铺会重复计入;按 id 去重确保每条唯一流只计一遍。
    seen_streams = {}
    for s in streams.values():
        seen_streams.setdefault(id(s), s)
    events = tuple(e for s in seen_streams.values() for e in s)
    return AnalysisResult(events=events, matches=matches_out, spec=spec,
                           dropped_matches=dropped_matches)


def matches(spec, df, params=None) -> bool:
    return len(analyze(spec, df, params).matches) > 0
