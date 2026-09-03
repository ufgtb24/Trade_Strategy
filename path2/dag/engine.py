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

from path2 import config
from path2.core import Event
from path2.dag.result import AnalysisResult
from path2.dag._graph import detector_topo_order
from path2.dag._solve import compile_plan, solve
from path2.dag._reify import reify


def annotate_stream(counts: dict, nid: str, events, children_of: dict | None = None) -> None:
    """标注单条流(含其嵌套 child):桶 (nid, start, end) 内流序从 0 起。
    counts 跨流持久(键含 nid,跨 node 不串扰);首现 node 获胜(已标注跳过)。
    行为与原批量 annotate_instances 逐字一致——只是调用点从循环外挪入循环内
    (run_streams 逐流交错标注:每条流 detect 完立刻标注,使下游 detector 在
    detect 期即可读上游 instance_id)。

    children_of({node_id: {slot名: 子node_id}},spec 的 children 声明)= 未标注
    child 的命名表:按容器槽名查映射,有声明 → 用声明的子结构 node_id(如
    tb.segments → tb_seg);无声明/槽未覆盖 → 继承容器流 nid 兜底(旧 app 行为
    不变,声明即启用)。声明漂移由 _check_children_declarations(C1/C3) 抓,
    不会静默错名。已标注跳过保证"槽引用独立 node 实例"(burst.members→bo,
    独立流先物化先标注)不被重标。"""
    cmap_all = children_of or {}

    def _annotate(e, nid: str) -> None:
        if e.node_id is not None:
            return
        key = (nid, e.start_idx, e.end_idx)
        idx = counts.get(key, 0)
        object.__setattr__(e, "node_id", nid)
        object.__setattr__(e, "instance_idx", idx)
        # 塌缩规则(原 id 函数唯一处,现已内联):点事件(start==end)塌缩为 {nid}_{start},
        # 区间保留 {nid}_{start}_{end}。
        prefix = (
            f"{nid}_{e.start_idx}"
            if e.start_idx == e.end_idx
            else f"{nid}_{e.start_idx}_{e.end_idx}"
        )
        object.__setattr__(e, "instance_id", f"{prefix}#{idx}")
        counts[key] = idx + 1

    def _annotate_children(e, nid: str) -> None:   # 递归补标嵌套 child
        cmap = cmap_all.get(nid, {})
        for slot_name, slot in e.child_slots().items():
            child_nid = cmap.get(slot_name, nid)
            members = slot if isinstance(slot, tuple) else (slot,)
            for c in members:
                if c.node_id is not None:
                    continue
                _annotate(c, child_nid)
                _annotate_children(c, child_nid)

    for e in events:           # 第一遍:流内事件
        _annotate(e, nid)
    for e in events:           # 第二遍:嵌套 child(按 children 声明命名,兜底继承)
        _annotate_children(e, nid)


def _translate_refs(streams) -> None:
    """统一翻译阶段:所有流标注完后,把各事件的 ref_slots() 对象引用翻译成 instance_id,
    写入 Event.ref_ids(按槽名字典序排列的 (槽名,(instance_id,...)) 对)。引用事件
    池外对象(instance_id 仍为 None)视为 detect bug,报错。"""
    for events in streams.values():
        for e in events:
            slots = e.ref_slots()
            if not slots:
                continue
            pairs = []
            for slot_name, refs in slots.items():
                refs = (refs,) if isinstance(refs, Event) else refs   # 归一化单-Event 槽位(与 annotate_stream 一致)
                ids = []
                for ref in refs:
                    if ref.instance_id is None:
                        raise ValueError(
                            f"引用的事件没有 instance_id(不在任何已绑定流里):{type(ref).__name__} "
                            f"@bar {ref.start_idx}(ref_slots[{slot_name}]);PatternSpec 已校验全绑定,"
                            f"此处只剩 detect 引用了池外对象")
                    ids.append(ref.instance_id)
                pairs.append((slot_name, tuple(ids)))
            object.__setattr__(e, "ref_ids", tuple(sorted(pairs)))


def _check_children_declarations(spec, streams) -> None:
    """运行期 C1/C2/C3: 声明 children vs 实例 child_slots 双向对照 + 类型核对。

    挂 run_streams 出口(RUNTIME_CHECKS 门控), analyze 与 diagnose 共用路径双覆盖。
    - C1(正向): 声明 slot key ⊆ 实例 child_slots key(声明了但没物化 → 报错)。
    - C2(反向): 实例 key ⊆ 声明 key(未声明 → 隐藏生产者, 报错基准)。
    - C3(类型): slot 元素 isinstance 子 node 的 event_cls(参照=归一化解析结果)。
    """
    if not config.RUNTIME_CHECKS:
        return
    by_id = {n.node_id: n for n in spec.nodes}
    for nid, events in streams.items():
        node = by_id[nid]
        if not node.children or node.detector is None:
            continue
        declared = set(node.children)
        for e in events:
            inst = set(e.child_slots())
            missing = declared - inst
            if missing:
                raise RuntimeError(
                    f"node {nid!r}: 声明 children 未物化 {sorted(missing)}; "
                    f"实际 slot: {sorted(inst)}(C1)")
            extra = inst - declared
            if extra:
                raise RuntimeError(
                    f"node {nid!r}: 实例有未声明 children {sorted(extra)}; "
                    f"请同步到 children 声明(C2 隐藏生产者)")
            for slot_name, child_nid in node.children.items():
                child_cls = by_id[child_nid].event_cls
                slot = e.child_slots().get(slot_name)
                if slot is None:
                    continue
                for c in (slot if isinstance(slot, tuple) else (slot,)):
                    if not isinstance(c, child_cls):
                        raise RuntimeError(
                            f"node {nid!r} slot {slot_name!r}: 期望 {child_cls.__name__} "
                            f"实际 {type(c).__name__}; children 引用疑似错 node(C3)")


def run_streams(spec, df, params=None):
    """阶段1:detector 依赖排序 + 跑流。返回 {node_id: [Event]}。
    analyze 与 diagnose(path2/dag/diagnose.py)共用,避免重复 detect。

    交错标注:每条流 detect 完立刻标注,使下游 detector 在 detect 期即可读上游
    instance_id(anchor_bo_id 据此写真实 instance_id,而非 span 回退)。计数器
    counts 跨迭代持久(键含 nid,跨 node 不串扰)。

    去重:同一 detector 对象在同一 consumes_stream 上只物化一次(key=(id(detector),consumes_stream))。
    多个 node_id 共享同一 detector 时,它们的 streams[nid] 指向同一个 list 对象。"""
    by_id = {n.node_id: n for n in spec.nodes}
    # children 声明 → 未标注 child 的命名表(见 annotate_stream docstring)
    children_of = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    streams = {}
    materialized = {}
    counts: dict = {}   # 标注桶计数器,跨流持久
    siblings: dict = {}   # (id(det), consumes) -> [NodeSpec] 按声明序
    for n in spec.nodes:
        if n.detector is not None:
            siblings.setdefault((id(n.detector), n.consumes_stream), []).append(n)

    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        if node.detector is None or nid in streams:
            continue                                # 后者:已被兄弟那一趟填好
        key = (id(node.detector), node.consumes_stream)      # ★ 键不变:detect 调用的身份
        if key not in materialized:
            from path2.runner import run_bundle
            if node.consumes_stream is None:
                materialized[key] = run_bundle(node.detector, df)
            else:
                materialized[key] = run_bundle(node.detector, streams[node.consumes_stream], df)
        bundle = materialized[key]
        for sib in siblings[key]:                   # ★ 同一调用的全部兄弟一次填完 + 立刻标注
            if sib.node_id in streams:
                continue
            if sib.produces_stream not in bundle:
                raise ValueError(f"node {sib.node_id!r}: detector 无流 {sib.produces_stream!r}")
            streams[sib.node_id] = bundle[sib.produces_stream]
            annotate_stream(counts, sib.node_id, streams[sib.node_id], children_of)
    _translate_refs(streams)
    _check_children_declarations(spec, streams)
    return streams


def _node_bits_of(match) -> str:
    """match id 消歧的排序段:node_index 的 (nid, instance_id) 规范串(reify 同款拼接)。"""
    ni = match.node_index or {}
    return "|".join(f"{nid}:{e.instance_id}" for nid, e in sorted(ni.items()))


def analyze(spec, df, params=None) -> AnalysisResult:
    """DAG 走势包 analyze:抽出 streams → compile plan → solve → reify matches。
    返回 AnalysisResult(events / matches / spec / gate_failures)。

    求解集由 compile_plan 的 K2 三要素判据决定(edge 端点并集 ∩ 非 neg_dst ∩
    detector 非空)——孤立未消费 node 不求解,matches 直通无出口过滤。"""
    streams = run_streams(spec, df, params)                 # 阶段1(抽出)
    plan = compile_plan(spec)                                # 阶段2
    sols = solve(plan, streams)                               # 阶段3
    matches_out = tuple(reify(s, streams, plan) for s in sols)  # 阶段4
    # res.events 按 stream 身份(id(s))去重:共享 detector 时多个 node_id 指同一 list,
    # 朴素平铺会重复计入;按 id 去重确保每条唯一流只计一遍。
    seen_streams = {}
    for s in streams.values():
        seen_streams.setdefault(id(s), s)
    events = tuple(e for s in seen_streams.values() for e in s)
    # 实例流协议:match 身份含上游组合,必须唯一。match_id 的 node_bits 段用
    # instance_id(标注后恒含 #idx),同流多实例组合天然可区分;但不同实例组合
    # 仍可能产出同 id 的 match(碰撞)→ 惰性消歧:仅碰撞组、按
    # (start, end, node_bits) 排序附 #idx;不碰撞零差异。消歧后断言必成立。
    from collections import defaultdict
    from dataclasses import replace as _replace
    groups = defaultdict(list)
    for i, m in enumerate(matches_out):
        groups[m.match_id].append(i)
    if any(len(v) > 1 for v in groups.values()):
        new_matches = list(matches_out)
        for ids in groups.values():
            if len(ids) < 2:
                continue
            ids.sort(key=lambda i: (new_matches[i].start_idx, new_matches[i].end_idx,
                                    _node_bits_of(new_matches[i])))
            for idx, i in enumerate(ids):
                m = new_matches[i]
                new_matches[i] = _replace(m, match_id=f"{m.match_id}#{idx}")
        matches_out = tuple(new_matches)
    mid = [m.match_id for m in matches_out]
    assert len(mid) == len(set(mid)), \
        f"match match_id 重复: {len(mid) - len(set(mid))} 个(违反 match 唯一协议)"
    return AnalysisResult(events=events, matches=matches_out, spec=spec)


def matches(spec, df, params=None) -> bool:
    return len(analyze(spec, df, params).matches) > 0
