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
import hashlib
import itertools
import json
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from path2.calc.atr import FP_ATR_WINDOW, prev_bar_atr_pct, rolling_atr_pct_nanmedian
from path2.core import Event
from path2.dag._reify import reify
from path2.dag._solve import compile_plan, solve
from path2.dag.edges import NegationEdge
from path2.dag.engine import run_streams
from path2.eval import (_resolve_end_events, match_first_passage, match_forward_drawdowns,
                        match_forward_returns)

Dim = tuple[str, str]  # (section, field)
STATES = ("up", "down", "both", "none")
LABEL_MODES = ("full", "deferred")
LABEL_COLS = ("fr", "dd", "fp_up", "fp_down", "fp_both", "fp_none")   # 完整标签模式才有的列
C0_ATR_PERIOD = 14


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


def _build_level(mod, base_dict: dict, dim: Dim, value):
    """某一维取某一档时构造 (Params, PatternSpec, eval_meta)。非法档的异常原样抛出,由调用方决定怎么处理。"""
    p = mod.Params.from_dict(apply_overrides(base_dict, {}, {dim: value}), strict=True)
    spec = mod.build_pattern(p)
    return p, spec, mod.eval_meta(params=p)


def spec_state_key(spec) -> str:
    """PatternSpec 的等价键:各 node 的 detector 实例状态(_det_state)+ where 表 + edges 的确定性 repr,
    取 sha256(classification.json 里要存每一档的键,原文太长)。两档键相同 = 构造出同一个 pattern。"""
    nodes = sorted((n.node_id, None if n.detector is None else _det_state(n.detector)) for n in spec.nodes)
    wheres = sorted((k, repr(v)) for k, v in _where_table(spec).items())
    return hashlib.sha256(repr((nodes, wheres, repr(spec.edges))).encode()).hexdigest()


def probe_levels(mod, base_dict: dict, dim: Dim, levels) -> list[dict]:
    """逐档合法性:每档在底座上单改这一维,走 Params.from_dict(strict) + build_pattern + eval_meta。

    每档输出 {"value","legal","error","state_key","end_node","head_buffer"}:非法档 legal=False、
    error 带异常类型与原文、其余为 None;合法档带等价键(见 spec_state_key,键相同即等价档)、
    买点 node 与首部缓冲交易日数。某档抛异常不影响其他档。"""
    out = []
    for v in levels:
        try:
            _p, spec, meta = _build_level(mod, base_dict, dim, v)
        except Exception as e:  # noqa: BLE001 —— app 用什么异常表达"这组参数不合法"是它的自由
            out.append({"value": v, "legal": False, "error": f"{type(e).__name__}: {e}",
                        "state_key": None, "end_node": None, "head_buffer": None})
            continue
        out.append({"value": v, "legal": True, "error": None, "state_key": spec_state_key(spec),
                    "end_node": meta["end_node"], "head_buffer": meta["head_buffer_trading_days"]})
    return out


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


def _alt_of(mod, base_dict: dict, dim: Dim, levels, base_v):
    """探针用的替代档 = 档位表里第一个不等于底座值、且构造得出来的档。"""
    alts = [v for v in levels if v != base_v]
    if not alts:
        raise ValueError(f"档位 {levels} 与底座值 {base_v} 无差异,无法探针")
    errors = []
    for v in alts:
        try:
            _build_level(mod, base_dict, dim, v)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{v!r}({type(e).__name__}: {e})")
            continue
        return v
    raise ValueError(f"{col_of(dim)} 除底座值 {base_v!r} 以外的档位全都构造不出来,判断不了它属于哪一类:"
                     + ";".join(errors))


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
        pr = probe_dim(mod, base_dict, dim, _alt_of(mod, base_dict, dim, levels, base_v))
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
            # 为什么上游造流参数(bo.*)不能走 F 维:不是「暂时没人声明 filter_params」,
            # 而是 F 契约在这类参数上机制性不成立。F 契约要求「该参数只控制发不发射、
            # 不改变事件字段」,于是工具能以最松档构造一次、事后按字段谓词切。实测 26 股:
            # 2 股连「松档 ⊇ 紧档」这个包含关系都不成立;18 股在两档共同 span 上事件字段
            # 就不同(drought / peak_age_max / peak_vol_max——恰好是 where 闸读的那几个)。
            # 且 bo / pk 是只显示 node、不进 node_index,长表的行里根本取不到它们的字段。
            # 后果不是「答案错」,是该维退回真扫维、检测组合数成倍膨胀(该网格 ×4)。
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


def detection_combos(scan_grid: dict, cls: Classification, design: str = "grid",
                     ref_point: dict | None = None) -> list:
    """研究设计展开出的检测组合(键为 Dim;F 维不进组合,按最松档构造、事后切)。

    grid:非 F 维笛卡尔积。
    screen:围绕工作点只扫必要的组合。ref_point = 参数键(section.field)→ 工作点值;每维的「替代档」
    = 档位表里不等于工作点值的档。输出顺序固定:[工作点] + 逐维逐替代档的单翻转 + 逐对维度 × 各自
    替代档的两两翻转(维按 SCAN_GRID 序、档按档位表序)。每维 3 档时共 1 + 2N + 4·C(N,2) 个。
    """
    dims = [d for d in scan_grid if cls.kinds[d] != "F"]
    if design == "grid":
        return [dict(zip(dims, vals)) for vals in itertools.product(*(scan_grid[d] for d in dims))]
    if design != "screen":
        raise ValueError(f"未知研究设计 {design!r}(合法 grid / screen)")
    if ref_point is None:
        raise ValueError("screen 设计需要工作点(ref_point)")
    work, alts = {}, {}
    for d in dims:
        key = col_of(d)
        if key not in ref_point or ref_point[key] not in scan_grid[d]:
            raise ValueError(f"screen 设计的工作点必须给出 {key} 且取值在档位 {scan_grid[d]} 里,"
                             f"实际 {ref_point.get(key, '(缺)')!r}")
        work[d] = ref_point[key]
        alts[d] = [v for v in scan_grid[d] if v != work[d]]
    out = [dict(work)]
    out += [{**work, d: v} for d in dims for v in alts[d]]
    out += [{**work, a: va, b: vb} for a, b in itertools.combinations(dims, 2)
            for va in alts[a] for vb in alts[b]]
    return out


# ---------------------------------------------------------------- 买点事件键 / 买点日 / 波动率尺度
def span_key_json(span_key) -> str:
    """买点事件键的规范文本:[[start, end], ...] 紧凑 JSON。seg_id 由它哈希而来,买点事件表也存它。"""
    return json.dumps([[int(s), int(e)] for s, e in span_key], separators=(",", ":"))


def seg_id_of(span_key) -> int:
    """买点事件键 → 有符号 64 位整数(长表 seg_id 列)。

    span_key = 买点 node 解析出的事件区间组 tuple((start_idx, end_idx), ...),顺序即解析顺序。
    取 blake2b(8 字节)摘要按小端解释为有符号整数:与进程、机器、PYTHONHASHSEED 无关,重算恒同值;
    不同区间组撞键的概率可忽略(scan_one_stock 仍逐股核一遍,撞了响亮失败)。"""
    raw = span_key_json(span_key).encode()
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "little", signed=True)


def entry_idx_of(events, lo: int, hi: int) -> int:
    """买点事件的入场 bar = 各事件样本 bar 里落在 [lo, hi] 内的最早一根(与 feature-study 抽取同口径)。

    用 sample_bar_indices() 而非 start_idx:买点 node 是「父 node.槽名」时,首部缓冲允许更早的
    事件存在,那一段从未进过标签采样,取它当入场 bar 会让波动率列算在窗外。"""
    return min(t for ev in events for t in ev.sample_bar_indices() if lo <= t <= hi)


def stock_scales(win: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """一只股票的两把波动率尺度,与 win 等长:
    M = 首次穿越用的波动率尺度(rolling_atr_pct_nanmedian,窗长 FP_ATR_WINDOW);
    c0 = 前一根 ATR 占收盘价比例(prev_bar_atr_pct,周期 C0_ATR_PERIOD)。
    长表行与逐日基线行都从这里取,两边同一个算式。"""
    h, l, c = win["high"], win["low"], win["close"]
    M = rolling_atr_pct_nanmedian(h, l, c, FP_ATR_WINDOW).to_numpy(dtype=float)
    return M, prev_bar_atr_pct(h, l, c, C0_ATR_PERIOD)


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
    design: str = "grid"                  # 研究设计,见 detection_combos
    ref_point: Optional[dict] = None      # 工作点(参数键 → 值);screen 设计必填
    label_mode: str = "full"              # full = 行内带标签;deferred = 只记买点事件,标签留到验证时现算

    def __post_init__(self):
        if self.label_mode not in LABEL_MODES:
            raise ValueError(f"未知标签模式 {self.label_mode!r}(合法 {LABEL_MODES})")


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
    cols += ["buy_date", "seg_id", "M", "c0_atr_pct"]
    return cols + list(LABEL_COLS) if cfg.label_mode == "full" else cols


def scan_one_stock(symbol: str, win: pd.DataFrame, start_ts, end_ts, cfg: ScanConfig, mod=None) -> tuple:
    """一只股票上跑完整个设计:上游流按影响集缓存、每个检测组合 solve、label 按 end_node span 记忆化。
    返回 (rows, segs):rows 是 list[dict](列 = row_columns);segs = {seg_id: span_key},本股出现过的
    全部买点事件(延迟标签模式据此落买点事件表,验证时按它现算标签)。where 一律宽进(谓词留给
    region 阶段),F 维按最松档构造(loosest_level,op-aware——不能写死 min(),F 维档位可能含 None
    代表"不设闸")。

    deferred 模式不调用任何标签函数;买点 node 的事件类若覆写了 sample_bar_indices → ValueError——
    验证时只凭区间组现算标签,覆写后样本 bar 不再由区间决定,现算出来的就不是扫描时那批 bar。"""
    mod = mod or _import(cfg.module_path)
    cls = classify(mod, cfg.base_dict, cfg.scan_grid, cfg.where_levels)
    filter_min = {d: loosest_level(cfg.scan_grid[d], cls.filter_fields[d][2])
                  for d in cfg.scan_grid if cls.kinds[d] == "F"}
    base = apply_overrides(cfg.base_dict, cfg.wide_overrides, filter_min)
    spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))
    # I-4:F 维(filter_params)与 W 维在 region 侧走同一条谓词轴,守卫必须覆盖两类的并集
    # (如 tb.max_day_drop_pct 现被 classify() 判成 W 维——守卫若只覆盖 F 维就会漏掉它;
    # 覆盖两类并集才不会因某个字段被判成另一类而漏检)。
    check_predicate_axes(spec0, {**cls.where_fields, **cls.filter_fields})
    infl = influence_dims(spec0, cls, cfg.scan_grid)
    leaf = cfg.end_node.split(".")[0]
    H, K = cfg.label_horizon, cfg.fp_k

    # 与 multivar_scan._worker 的逐日基线同一个 stock_scales:长表行与基线行的波动率列必须同一把尺子
    M, c0 = stock_scales(win)
    lo = int(win["date"].searchsorted(start_ts, "left"))
    hi = int(win["date"].searchsorted(end_ts, "right")) - 1
    dates = win["date"]
    closes = win["close"]
    deferred = cfg.label_mode == "deferred"
    stream_cache: dict = {}
    label_memo: dict = {}
    seg_memo: dict = {}      # span_key → (seg_id, entry_idx)
    segs: dict = {}          # seg_id → span_key
    rows: list = []

    for combo in detection_combos(cfg.scan_grid, cls, cfg.design, cfg.ref_point):
        p = mod.Params.from_dict(apply_overrides(base, {}, combo), strict=True)
        spec = mod.build_pattern(p)
        # 产流交给引擎(path2/dag/engine.py 的 run_streams),工具只管缓存:把已经算好的
        # 流当预置流递进去,引擎跳过这些 node、其余照常产。这样工具的产流行为定义上
        # 等于引擎——多流 detector 一趟产多条流、交错标注、引用槽翻译、children 校验
        # 全部自动继承,不再有第二份实现会漂。
        # 缓存键是语义键 (node_id, 该 node 的影响维取值);引擎内部那个含 id(detector)
        # 的物化键只在单次调用内有效,跨参数组合必然失配,绝不能拿来当缓存键。
        det_nids = [n.node_id for n in spec.nodes if n.detector is not None]
        keys = {nid: (nid, tuple(combo[d] for d in infl[nid])) for nid in det_nids}
        streams = run_streams(spec, win, preset={
            nid: stream_cache[k] for nid, k in keys.items() if k in stream_cache})
        # 不变式:写回必须整份,不得挑。漏写任何一条都会在下个组合里造成半截预置——
        # 同一趟 detect 只预置一部分,那一趟会白跑一遍;若该趟内有跨兄弟引用还会直接抛。
        for nid, k in keys.items():
            stream_cache.setdefault(k, streams[nid])
        plan = compile_plan(spec)
        combo_cols = {col_of(d): v for d, v in combo.items()}
        # 计数口径:本循环不清零任何行的四态——同一买点 span 的每一行都带该 span 的满额四态
        # (label_memo 按 span 共享)。「同一段买点只计一次」发生在下游,且与引擎侧同一个键:
        # serialize_per_pattern_result 按 buy_span 去重(seen_fp_spans),region_core 的买点事件
        # 口径与 compare_longtable 按 study_io.segment_cols 去重。去重都发生在 where 过滤之后
        # (引擎侧 where 在物化前施加;长表侧宽进、按列事后过滤),一段买点只要有任一行留下就计一次,
        # 两侧一致。
        #
        # 下面按 end_node 实例的查重是拓扑前提断言,不参与计数:bb_v1 当前拓扑(三条闩:
        # ① BurstDetector 的 all_ends 物化对簇内每个 k 只 emit 一个前缀实例 ⟹ 两个 burst 不可能
        # 共享同一 last_bo;② 唯一的边 TemporalEdge(Child("burst", "last_bo"), "tb",
        # anchor_field="anchor_bo_id") 是身份标量相等;③ bo 是孤立 node、不进 node_index,不参与
        # 笛卡尔拼接)下,同一个 end_node 实例在一个检测组合内至多属于一个 match(387 股实测零命中)。
        # 命中说明拓扑变了,长表的行模型需要重新核对,故响亮失败(复审 I-1)。必须按 combo 重置:
        # instance_id 只由本股窗口内的 (node_id, span, 桶内序号) 决定,不同 combo 各自重跑 detector
        # 可能撞出同一个字符串。
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
            if deferred:
                bad = [type(ev).__name__ for ev in events if type(ev).sample_bar_indices is not Event.sample_bar_indices]
                if bad:
                    raise ValueError(
                        f"symbol={symbol}: 买点 node {cfg.end_node!r} 的事件类 {bad[0]} 自定义了样本 bar 的取法,"
                        "样本 bar 不再由事件区间决定——延迟标签只记区间、验证时按区间现算,算出来的不是扫描时那批 bar。"
                        "这个走势不能在留作验证的数据上扫描。")
            if span_key not in seg_memo:
                sid = seg_id_of(span_key)
                if segs.setdefault(sid, span_key) != span_key:
                    raise ValueError(f"symbol={symbol}: 两个不同的买点事件 {segs[sid]} 与 {span_key} 算出了同一个 "
                                     f"seg_id={sid}")
                seg_memo[span_key] = (sid, entry_idx_of(events, lo, hi))
            sid, entry = seg_memo[span_key]
            if not deferred and span_key not in label_memo:
                # 缓存前提(修复轮 1 · Minor 5):span_key=(start_idx,end_idx) 要充分决定
                # fr/dd/fp,隐含要求 end_node 事件的 sample_bar_indices() 没有被 override 成
                # 依赖 span 之外的状态——path2/core.py:112 docstring 允许嵌套容器 override
                # 展开 child(与 span 全量不同);bb_v1 的 tb 未 override(用默认 range(start,
                # end+1)),此前提当前成立,若未来 end_node 换成会 override 的容器需重新审视。
                fr = match_forward_returns(m, cfg.end_node, win, [H], sample_window=(lo, hi))[H]
                dd = match_forward_drawdowns(m, cfg.end_node, win, [H], sample_window=(lo, hi))[H]
                fp = match_first_passage(m, cfg.end_node, win, H, K, sample_window=(lo, hi), M=M)
                label_memo[span_key] = (fr, dd, fp)
            leaf_ev = m.node_index[leaf]
            if leaf_ev.instance_id in seen_fp_leaves:
                # 命中即三条闩已被打破(见上方注释)——把静默偏小的四态改成响亮失败,而不是
                # 悄悄落零行继续跑(复审 I-1)。
                raise ValueError(
                    f"symbol={symbol}: end_node 事件物理实例 {leaf_ev.instance_id!r} 在同一"
                    "检测组合内出现在多个 match 里——这只在当前拓扑的三条闩(见上方注释)"
                    "成立时才不发生,命中说明拓扑已变,长表的行模型需要重新核对。"
                    "本工具不支持这种拓扑,请把相关维度改走真扫维(SCAN_GRID/detection_combos)"
                    "而非谓词轴,或重新核实该拓扑是否真的会让同一 leaf 出现在多个 match 里。"
                )
            seen_fp_leaves.add(leaf_ev.instance_id)
            row = {"symbol": symbol, **combo_cols}
            for (n, f, _) in cls.filter_fields.values():
                row[node_col(n, f)] = getattr(m.node_index[n], f)
            for (n, f, _) in cls.where_fields.values():
                row[node_col(n, f)] = getattr(m.node_index[n], f)
            for nid, ev in m.node_index.items():
                row[node_col(nid, "start")] = ev.start_idx; row[node_col(nid, "end")] = ev.end_idx
            row["buy_date"] = str(pd.to_datetime(dates.iat[leaf_ev.start_idx]).date())
            row["seg_id"] = sid; row["M"] = float(M[entry]); row["c0_atr_pct"] = float(c0[entry])
            if not deferred:
                fr, dd, fp = label_memo[span_key]
                row["fr"] = fr; row["dd"] = dd
                for s in STATES:
                    row[f"fp_{s}"] = int(fp[s])
            rows.append(row)
    return rows, segs
