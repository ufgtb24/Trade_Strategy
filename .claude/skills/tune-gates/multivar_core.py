# -*- coding: utf-8 -*-
"""multivar_scan 的纯函数层(无 I/O):参数分类探针 / 影响集 / 组合展开 / 单股反转循环。

设计(spec v2 §3):pattern 无关——只依赖 PatternRegistry 暴露的 mod(build_pattern / Params /
eval_meta)、NodeSpec.consumes_stream 拓扑与 Params 的 section 约定。

参数四类(spec §1):W where 阈值(联合空间免费轴)/ F 过滤型(detector 声明 filter_params,
按最松档构造、事后按字段谓词切)/ D detector 构造参数(结构型与状态机型统一处理:上游流缓存、
本级及下游重跑)/ E 只改 edge(只影响 solve)。分类靠**探针**:把某维改成另一档,比较两份
PatternSpec 里各 node detector 的实例属性、where 子句阈值与 edges 哪些变了——不猜签名、不看名字。
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian
from path2.dag._graph import detector_topo_order
from path2.dag._reify import reify
from path2.dag._solve import compile_plan, solve
from path2.dag.edges import NegationEdge
from path2.dag.engine import annotate_stream
from path2.eval import (_resolve_end_events, match_first_passage, match_forward_drawdowns,
                        match_forward_returns)
from path2.runner import run

Dim = tuple[str, str]  # (section, field)
STATES = ("up", "down", "both", "none")


def col_of(dim: Dim) -> str:
    return f"{dim[0]}.{dim[1]}"


def node_col(node_id: str, field: str) -> str:
    return f"{node_id}.{field}"


# ---------------------------------------------------------------- 探针分类
def _det_state(det) -> str:
    """detector 实例的可比较状态:非可调用实例属性的 repr(排序)。"""
    items = sorted((k, repr(v)) for k, v in vars(det).items() if not callable(v))
    return repr(items)


def _iter_attr_preds(pred):
    """递归展开 where 组合子,产出 meta.kind=='attr' 的叶谓词 meta。"""
    meta = getattr(pred, "meta", None) or {}
    if meta.get("kind") == "attr":
        yield meta
    for c in getattr(pred, "children", ()):
        yield from _iter_attr_preds(c)


def _where_table(spec) -> dict[tuple[str, str, str], list]:
    """{(node, field, op): [threshold, ...]}(同一 (node,field,op) 可能多子句)。"""
    out: dict = {}
    for n in spec.nodes:
        for _cid, fn in n.where:
            for m in _iter_attr_preds(fn):
                out.setdefault((n.node_id, m["field"], m["op"]), []).append(m["threshold"])
    return out


@dataclass(frozen=True)
class Probe:
    detector_nodes: tuple      # 该维改变了哪些 node 的 detector 实例状态
    where_clauses: tuple       # 该维改变了哪些 where 子句 (node, field, op)
    edges_changed: bool


def apply_overrides(base_dict: dict, wide_overrides: dict, assignments: dict) -> dict:
    d = copy.deepcopy(base_dict)
    for sec, kv in (wide_overrides or {}).items():
        d.setdefault(sec, {}).update(kv)
    for (sec, field), v in assignments.items():
        d.setdefault(sec, {})[field] = v
    return d


def probe_dim(mod, base_dict: dict, dim: Dim, alt_value) -> Probe:
    p0 = mod.Params.from_dict(base_dict, strict=True)
    p1 = mod.Params.from_dict(apply_overrides(base_dict, {}, {dim: alt_value}), strict=True)
    s0, s1 = mod.build_pattern(p0), mod.build_pattern(p1)
    by0 = {n.node_id: n for n in s0.nodes}
    det_nodes = tuple(n.node_id for n in s1.nodes
                      if n.detector is not None and by0[n.node_id].detector is not None
                      and _det_state(n.detector) != _det_state(by0[n.node_id].detector))
    w0, w1 = _where_table(s0), _where_table(s1)
    clauses = tuple(sorted(k for k in set(w0) | set(w1) if w0.get(k) != w1.get(k)))
    return Probe(det_nodes, clauses, repr(s0.edges) != repr(s1.edges))


@dataclass(frozen=True)
class Classification:
    kinds: dict            # Dim → "W" | "F" | "D" | "E"
    detector_nodes: dict   # Dim → tuple[node_id]
    where_fields: dict     # W 维 → (node, field, op)
    filter_fields: dict    # F 维 → (node, field, op)


def _alt_of(levels, base_v):
    for v in levels:
        if v != base_v:
            return v
    raise ValueError(f"档位 {levels} 与底座值 {base_v} 无差异,无法探针")


def loosest_level(levels, op: str):
    """按运算符语义算某档位表里的「最松」档:F 维契约(见 BurstDetector.filter_params
    docstring)要求以最松档构造、事后按字段谓词切,该判据必须 op-aware——不能写死
    min(levels):`<=`/`<` 语义下最松档是取值上界(或 None=不设闸,若档位表含 None)。

    classify 的底座自检、Task 7 的 F 维构造步共用本函数,避免两处各写一遍而漂移。
    """
    if op in (">=", ">"):
        return min(levels)
    if op in ("<=", "<"):
        return None if None in levels else max(levels)
    raise ValueError(f"未知运算符 {op!r}(合法 >=/>/<=/<)")


def classify(mod, base_dict: dict, scan_grid: dict, where_levels: dict) -> Classification:
    kinds, det_nodes, where_fields, filter_fields = {}, {}, {}, {}
    spec0 = mod.build_pattern(mod.Params.from_dict(base_dict, strict=True))
    dets = {n.node_id: n.detector for n in spec0.nodes if n.detector is not None}
    for dim, levels in list(scan_grid.items()) + list(where_levels.items()):
        base_v = base_dict[dim[0]][dim[1]]
        pr = probe_dim(mod, base_dict, dim, _alt_of(levels, base_v))
        det_nodes[dim] = pr.detector_nodes
        if pr.where_clauses and not pr.detector_nodes and not pr.edges_changed:
            if len(pr.where_clauses) != 1:
                raise ValueError(f"{col_of(dim)} 同时驱动多条 where 子句 {pr.where_clauses},不能作单轴")
            kinds[dim] = "W"; where_fields[dim] = pr.where_clauses[0]
        elif pr.detector_nodes:
            fp = None
            for nid in pr.detector_nodes:
                decl = getattr(type(dets[nid]), "filter_params", {}) or {}
                if dim[1] in decl:
                    fp = (nid,) + tuple(decl[dim[1]])
            if fp is not None and len(pr.detector_nodes) == 1 and not pr.edges_changed:
                # 底座/网格一致性提醒(复审 M-4):这条闸查的是 base_dict 的原始底座值,而
                # scan_one_stock 实际构造用的是 base ∘ wide_overrides ∘ filter_min——后者
                # 随后无条件把 F 维覆盖成最松档,所以即使这里报错,工具本来也会自动改对、
                # 不是真的跑不动。保留这条闸不是因为底座值不最松会算错(它不会),而是提醒
                # "底座 json 与网格档位表不一致"这件事本身通常意味着某处配置写漂了——
                # 静默自动纠正会让这种漂移一直不可见。
                loose = loosest_level(levels, fp[2])
                if base_v != loose:
                    raise ValueError(
                        f"{col_of(dim)} 是过滤型(F)维:底座值={base_v!r},但按运算符 {fp[2]!r} 算出"
                        f"的最松档={loose!r}(档位={levels})——两者不一致。工具会自动把它改成最松档来跑"
                        f"(scan_one_stock 无条件覆盖),这条闸只是提醒你底座与网格档位表不一致,请确认是否"
                        f"符合预期;确认没问题就把底座改成 {loose!r},或把该档从网格里去掉。"
                    )
                kinds[dim] = "F"; filter_fields[dim] = fp
            else:
                kinds[dim] = "D"
        elif pr.edges_changed:
            kinds[dim] = "E"
        else:
            raise ValueError(f"{col_of(dim)} 改档后 detector/where/edges 都没变:参数未被消费或 detector 未把它存为实例属性")
    for dim in scan_grid:
        if kinds[dim] == "W":
            raise ValueError(f"{col_of(dim)} 是 where 阈值(W),不进 SCAN_GRID;放 WHERE_LEVELS")
    for dim in where_levels:
        if kinds[dim] != "W":
            raise ValueError(f"{col_of(dim)} 不是纯 where 阈值(探针:{kinds[dim]}),不能作 WHERE_LEVELS 轴")
    return Classification(kinds, det_nodes, where_fields, filter_fields)


def check_predicate_axes(spec, fields: dict) -> None:
    """守卫 W/F 两类谓词轴(复审 I-4):spec §3.3 要求把 where/filter_params 当长表列谓词
    与"引擎施加"等价,前提是该 node 不是任何 NegationEdge 的目标——否则收紧谓词减少被
    否定的事件、反而增加 match,事后按行过滤(只能减行)方向就错了。W 维(NodeSpec.where)
    与 F 维(detector.filter_params)在 region 侧走的是同一条谓词轴(FILTER_PREDS +
    WHERE_PREDS 一起进 prepare 的 pred_specs),必须一起守——调用方须传入两类字段的并集
    (`{**cls.where_fields, **cls.filter_fields}`),不能只喂 where_fields。"""
    neg_dst = {e.dst for e in spec.edges if isinstance(e, NegationEdge)}
    for dim, (nid, field, _op) in fields.items():
        if nid in neg_dst:
            raise ValueError(f"{col_of(dim)} 所在 node {nid!r} 是 NegationEdge 目标,谓词轴收紧可能增加 match,"
                             "不能作长表谓词轴(where/filter 均适用);改为真扫维")


# ---------------------------------------------------------------- 拓扑 / 影响集 / 组合
def upstream_closure(spec, node_id: str) -> tuple:
    by = {n.node_id: n for n in spec.nodes}
    out, cur = [], node_id
    while cur is not None:
        out.append(cur)
        cur = by[cur].consumes_stream
    return tuple(out)


def influence_dims(spec, cls: Classification, scan_grid: dict) -> dict:
    out = {}
    for n in spec.nodes:
        if n.detector is None:
            continue
        closure = set(upstream_closure(spec, n.node_id))
        out[n.node_id] = tuple(d for d in scan_grid
                               if cls.kinds[d] == "D" and closure & set(cls.detector_nodes[d]))
    return out


def detection_combos(scan_grid: dict, cls: Classification) -> list:
    dims = [d for d in scan_grid if cls.kinds[d] != "F"]
    return [dict(zip(dims, vals)) for vals in itertools.product(*(scan_grid[d] for d in dims))]


# ---------------------------------------------------------------- 单股反转循环
@dataclass(frozen=True)
class ScanConfig:
    module_path: str
    base_dict: dict
    wide_overrides: dict
    scan_grid: dict
    where_levels: dict
    end_node: str
    label_horizon: int
    fp_k: float
    price_min: Optional[float] = None
    price_max: Optional[float] = None


def _import(path: str):
    import importlib
    return importlib.import_module(path)


def row_columns(cfg: ScanConfig, cls: Classification, spec) -> list:
    """列 = scan_one_stock 实际写入 row 的键集(同源,修复轮 1 · Important 1)。节点列必须
    与 `m.node_index`(reify 的 `dict(assign)`)同一集合——不能用 `n.detector is not None`
    (spec.nodes 全量)代替,因为 compile_plan 的 K2 判据(求解=edge 连通分量∩非neg_dst∩
    detector非空)会把孤立 node(如 bb_v1 的 `bo`,无边、只被 consumes_stream 消费)排除出
    `node_index`——那种 node 不会出现在任何一行里,若仍纳入列会在 Task 8 的 parquet 分片
    里变成恒 NaN 的幽灵列(或 pyarrow 严格 schema 直接报错)。直接复用 compile_plan(spec)
    的 wcc_plans(而非在此重复 K2 公式)保证与 solve/reify 侧同源、不会随 _solve.py 演进
    而漂移——`wccs()` 保证每个 bound node 恰好落在一个分量里(孤立 bound node 自成单元素
    分量),故 `union(w.comp for w in plan.wcc_plans) == compile_plan 内部的 bound_ids`。"""
    cols = ["symbol"] + [col_of(d) for d in cfg.scan_grid if cls.kinds[d] != "F"]
    cols += [node_col(n, f) for (n, f, _) in cls.filter_fields.values()]
    cols += [node_col(n, f) for (n, f, _) in cls.where_fields.values()]
    bound = {nid for w in compile_plan(spec).wcc_plans for nid in w.comp}
    for n in spec.nodes:
        if n.node_id in bound:
            cols += [node_col(n.node_id, "start"), node_col(n.node_id, "end")]
    return cols + ["buy_date", "fr", "dd", "fp_up", "fp_down", "fp_both", "fp_none"]


def scan_one_stock(symbol: str, win: pd.DataFrame, start_ts, end_ts, cfg: ScanConfig, mod=None) -> list:
    """一只股票上跑完整个设计:上游流按影响集缓存、每个检测组合 solve、label 按 end_node span 记忆化。
    返回 rows(list[dict],列 = row_columns)。where 一律宽进(谓词留给 region 阶段),F 维按最松档构造
    (loosest_level,op-aware——不能写死 min(),F 维档位可能含 None 代表"不设闸")。"""
    mod = mod or _import(cfg.module_path)
    cls = classify(mod, cfg.base_dict, cfg.scan_grid, cfg.where_levels)
    filter_min = {d: loosest_level(cfg.scan_grid[d], cls.filter_fields[d][2])
                  for d in cfg.scan_grid if cls.kinds[d] == "F"}
    base = apply_overrides(cfg.base_dict, cfg.wide_overrides, filter_min)
    spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))
    # 复审 I-2:run_streams 的物化键是 (id(node.detector), consumes_stream)——多个 node 共享
    # 同一 detector 实例时它们的流指向同一份物化,而本函数的缓存键只按 nid 区分,会让共享
    # detector 的两个 node 各跑一份独立事件列表、instance_id 与生产不同,靠 anchor_field
    # 成边的拓扑可能整体失配。这不是假想拓扑(dag_spec 出现过 down/side 共享 trend_det),
    # 拒绝而非静默给出不同答案。
    det_nodes = [n for n in spec0.nodes if n.detector is not None]
    if len({id(n.detector) for n in det_nodes}) != len(det_nodes):
        raise ValueError("本工具不支持多 node 共享 detector 实例(run_streams 会折叠物化、反转循环不会),"
                         "请拆成独立实例或改走逐格 scan")
    # I-4:F 维(filter_params)与 W 维在 region 侧走同一条谓词轴,守卫必须覆盖两类的并集
    # (如 tb.max_day_drop_pct 现被 classify() 判成 W 维——守卫若只覆盖 F 维就会漏掉它;
    # 覆盖两类并集才不会因某个字段被判成另一类而漏检)。
    check_predicate_axes(spec0, {**cls.where_fields, **cls.filter_fields})
    infl = influence_dims(spec0, cls, cfg.scan_grid)
    order = [nid for nid in detector_topo_order(spec0.nodes)]
    children_of = {n.node_id: dict(n.children) for n in spec0.nodes if n.children}
    leaf = cfg.end_node.split(".")[0]
    H, K = cfg.label_horizon, cfg.fp_k

    # 窗口与 multivar_scan.py:_worker 里 random_day_first_passage 前那次独立计算耦合
    # (Task 8 修复轮 1 Important——纯浪费非口径分裂:同 win、值恒等,但改一侧不改另一侧会
    # 静默分叉首穿判定用的波动率尺度)。彻底修需要本函数把 M 返出来给 _worker 复用,已裁定
    # 推迟(会碰 Task 7 已验证代码),此处先留痕。窗口本身改引用 path2.calc.atr.FP_ATR_WINDOW
    # 单点导出(复审 I-5),不再是散落的字面量 20——谁调它,四处一起变。
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], FP_ATR_WINDOW).values
    lo = int(win["date"].searchsorted(start_ts, "left"))
    hi = int(win["date"].searchsorted(end_ts, "right")) - 1
    dates = win["date"]
    closes = win["close"]
    stream_cache: dict = {}
    label_memo: dict = {}
    rows: list = []

    for combo in detection_combos(cfg.scan_grid, cls):
        p = mod.Params.from_dict(apply_overrides(base, {}, combo), strict=True)
        spec = mod.build_pattern(p)
        by_id = {n.node_id: n for n in spec.nodes}
        streams, counts = {}, {}
        for nid in order:
            node = by_id[nid]
            if node.detector is None:
                continue
            key = (nid, tuple(combo[d] for d in infl[nid]))
            if key not in stream_cache:
                if node.consumes_stream is None:
                    evs = list(run(node.detector, win))
                else:
                    evs = list(run(node.detector, streams[node.consumes_stream], win))
                annotate_stream(counts, nid, evs, children_of)     # 已标注的上游流会被跳过
                stream_cache[key] = evs
            streams[nid] = stream_cache[key]
        plan = compile_plan(spec)
        combo_cols = {col_of(d): v for d, v in combo.items()}
        # serialize.py:381-389 同款去重(修复轮 1 · Minor 1):同一个 end_node 事件物理实例
        # (leaf_ev.instance_id)只在本 combo 内第一次出现的那一行落非零四态,后续行落零——
        # 与 serialize_per_pattern_result 每次调用(=每个 combo 各自一次)内部的 seen_fp_leaves
        # 语义对齐。必须按 combo 重置(不能像 stream_cache/label_memo 那样跨 combo 共享):
        # instance_id = f"{node_id}_{start}[_{end}]#{instance_idx}"(path2/core.py)只由本股
        # 窗口内的 (node_id, span, 桶内序号) 决定,不同 combo 各自重跑 detector 完全可能撞出
        # 同一个 instance_id 字符串(纯偶然同 span),跨 combo 共享去重集会把两个毫不相干的
        # combo 错误地当成"同一物理事件的重复引用"、误清零。bb_v1 当前拓扑(reviewer 给出
        # 的三条闩:① BurstDetector 的 all_ends 物化对簇内每个 k 只 emit 一个前缀实例 ⟹
        # 两个 burst 不可能共享同一 last_bo;② 唯一的边 TemporalEdge(Child("burst",
        # "last_bo"), "tb", anchor_field="anchor_bo_id") 是身份标量相等;③ bo 是孤立 node、
        # 不进 node_index,不参与笛卡尔拼接)下本去重不会真正触发(387 股实测验证过零命中)。
        #
        # 这条去重与 serialize.py 等价,前提严格是"同一个 leaf 物理实例至多属于本 combo 内
        # 一个 match"——三条闩正是在保证这条前提。若未来拓扑打破了它(同一 leaf 出现在
        # ≥2 个 match 里),这个去重不是"防失配"的保险,而恰恰是**引入**失配的那一环:两
        # 处的谓词过滤时机不同——serialize 侧 where 由引擎在物化前施加,去重发生在已经被
        # where 筛过的 match 集合上;长表侧 where 一律宽进、region 阶段才按列做谓词过滤,
        # 若携带非零四态的那一行恰好被收紧的谓词滤掉、另一行(已被清零)留下,该 leaf 的
        # 四态会整体丢失、长表在收紧档上的 FP 分母比引擎口径**静默偏小**。前提破了必须
        # 走真扫维(把该维放进 SCAN_GRID/detection_combos),而不能继续留在谓词轴上事后过滤。
        # 复审 I-1:把"零命中"这条当前事实前提做成硬断言,前提一旦被打破就响亮失败(见下方
        # raise),不再指望三条闩长期不被违反而不设防。
        seen_fp_leaves: set = set()
        for sol in solve(plan, streams):
            m = reify(sol, streams, plan)
            events = _resolve_end_events(m, cfg.end_node)
            if not any(start_ts <= dates.iat[ev.start_idx] <= end_ts for ev in events):
                continue
            cl = [closes.iat[ev.start_idx] for ev in events]
            if not any((cfg.price_min is None or c >= cfg.price_min)
                       and (cfg.price_max is None or c <= cfg.price_max) for c in cl):
                continue
            span_key = tuple((ev.start_idx, ev.end_idx) for ev in events)
            if span_key not in label_memo:
                # 缓存前提(修复轮 1 · Minor 5):span_key=(start_idx,end_idx) 要充分决定
                # fr/dd/fp,隐含要求 end_node 事件的 sample_bar_indices() 没有被 override 成
                # 依赖 span 之外的状态——path2/core.py:112 docstring 允许嵌套容器 override
                # 展开 child(与 span 全量不同);bb_v1 的 tb 未 override(用默认 range(start,
                # end+1)),此前提当前成立,若未来 end_node 换成会 override 的容器需重新审视。
                fr = match_forward_returns(m, cfg.end_node, win, [H], sample_window=(lo, hi))[H]
                dd = match_forward_drawdowns(m, cfg.end_node, win, [H], sample_window=(lo, hi))[H]
                fp = match_first_passage(m, cfg.end_node, win, H, K, sample_window=(lo, hi), M=M)
                label_memo[span_key] = (fr, dd, fp)
            fr, dd, fp = label_memo[span_key]
            leaf_ev = m.node_index[leaf]
            if leaf_ev.instance_id in seen_fp_leaves:
                # 命中即三条闩已被打破(见上方注释)——把静默偏小的四态改成响亮失败,而不是
                # 悄悄落零行继续跑(复审 I-1)。
                raise ValueError(
                    f"symbol={symbol}: end_node 事件物理实例 {leaf_ev.instance_id!r} 在同一"
                    "检测组合内被 seen_fp_leaves 判为重复——这只在当前拓扑的三条闩(见上方注释)"
                    "成立时才不发生,命中说明闸已被打破,长表 FP 会在收紧谓词档上静默偏小。"
                    "本工具不支持这种拓扑,请把相关维度改走真扫维(SCAN_GRID/detection_combos)"
                    "而非谓词轴,或重新核实该拓扑是否真的会让同一 leaf 出现在多个 match 里。"
                )
            seen_fp_leaves.add(leaf_ev.instance_id)
            fp_row = fp
            row = {"symbol": symbol, **combo_cols}
            for (n, f, _) in cls.filter_fields.values():
                row[node_col(n, f)] = getattr(m.node_index[n], f)
            for (n, f, _) in cls.where_fields.values():
                row[node_col(n, f)] = getattr(m.node_index[n], f)
            for nid, ev in m.node_index.items():
                row[node_col(nid, "start")] = ev.start_idx; row[node_col(nid, "end")] = ev.end_idx
            row["buy_date"] = str(pd.to_datetime(dates.iat[leaf_ev.start_idx]).date())
            row["fr"] = fr; row["dd"] = dd
            for s in STATES:
                row[f"fp_{s}"] = int(fp_row[s])
            rows.append(row)
    return rows
