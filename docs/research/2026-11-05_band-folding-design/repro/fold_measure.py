"""研究用临时脚本(不入正式代码):量各候选折叠规则下副图 band 的行数、族大小与误折。

口径(与 compare 同口径):每只股票截到训练段末日的全部 K 线(slice_window 1900-01-01..TRAIN_END),
跑 app 的 analyze;event 走 path2_web.serialize.serialize_analysis(含一级 child 挖出),
档位按前端口径复刻:in_hit = hit.node_index 精确实例 + child_refs 闭包;qualified = diagnose 的 attr 行全 clause 通过。
副图 band = render_grid != 'price' 的 node。行数 = 前端 packLanes(按 start 升序贪心首适)的 lane 数。

规则(折叠键 → 一族;族的跨度 = [成员最小 start, 成员最大 end],再对族跑 packLanes):
  R0 none        : 不折(现状)
  R1 same_span   : (node, start, end) 完全相同才折
  R2 start       : (node, start)
  R3 end         : (node, end)
  R4 start|end   : 同 start 或同 end 连通分量
  R5 parent      : 子结构 node 的 event 随父族(父按 R2 认族);独立 node 用 R2
误折(只为量,不是规则的一部分):用 app 知识给每个 event 标「来源」——new_step 按阶跃段起点 s,
burst 系按 chain 簇首 bo;一族里出现 ≥2 个来源即算一次误折。

用法: uv run python docs/research/2026-11-05_band-folding-design/repro/fold_measure.py [SYM ...]
"""
from __future__ import annotations

import collections
import importlib
import json
import sys

import pandas as pd

from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars, slice_window, TRAIN_END
from path2_web.serialize import serialize_analysis
from path2.dag.diagnose import diagnose

APPS = ["new_step", "bottom_burst", "bb_v1", "bo_only"]
DEFAULT_SYMS = ["CRNC", "RGTI", "INDO", "QBTS", "GEVO"]
LEVELS = ["detected", "qualified", "in_hit"]
RANK = {"detected": 0, "qualified": 1, "in_hit": 2}
RULES = ["R0_none", "R1_same_span", "R2_start", "R3_end", "R4_start_or_end", "R5_parent"]

_cfg = load_config()


def load_win(sym: str) -> pd.DataFrame:
    return slice_window(read_bars(view_dataset_dir(_cfg), sym), "1900-01-01", TRAIN_END)


def pack_lanes(items):
    """复刻 geometry.ts packLanes:按 start 升序(稳定),首个 laneEnd < start 的 lane,否则新开。"""
    order = sorted(range(len(items)), key=lambda i: (items[i][0], i))
    lane_ends = []
    out = [0] * len(items)
    for i in order:
        s, e = items[i]
        lane = next((k for k, end in enumerate(lane_ends) if end < s), -1)
        if lane == -1:
            lane = len(lane_ends)
            lane_ends.append(e)
        else:
            lane_ends[lane] = e
        out[i] = lane
    return out, len(lane_ends)


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def f(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def u(self, a, b):
        a, b = self.f(a), self.f(b)
        if a != b:
            self.p[a] = b


def analyze_one(app_name: str, sym: str):
    mod = importlib.import_module(f"path2_apps.{app_name}.dag_spec")
    params = mod.load_params()
    spec = mod.build_pattern(params)
    win = load_win(sym)
    res = mod.analyze(win, params)
    ser = serialize_analysis(res)
    events = ser["events"]
    hits = ser["hits"]
    byid = {e["instance_id"]: e for e in events}

    # in_hit 闭包(node_index + child_refs;anchor 弱引用只影响 bo,bo 在主图,不影响副图 band)
    inhit = set()
    q = []
    for h in hits:
        for ref in h["node_index"].values():
            if ref not in inhit:
                inhit.add(ref); q.append(ref)
    while q:
        ev = byid.get(q.pop())
        if not ev:
            continue
        for ids in ev["child_refs"].values():
            for c in ids:
                if c not in inhit:
                    inhit.add(c); q.append(c)
    # qualified(diagnose attr 行全通过)
    diag = diagnose(spec, win, params)
    qual = set()
    for nid, nd in diag.nodes.items():
        for row in nd.attr:
            if all(bool(w.satisfied) for w in row.clauses.values()):
                qual.add(row.event.instance_id)

    def tier(e):
        if e["instance_id"] in inhit:
            return "in_hit"
        if e["instance_id"] in qual:
            return "qualified"
        return "detected"

    sub_nodes = [n.node_id for n in spec.nodes if n.render_grid != "price"]
    solve_free = {n.node_id for n in spec.nodes if not n.solve}
    child_node = {}       # 子结构 node -> 父 node
    for n in spec.nodes:
        for slot, cid in (n.children or {}).items():
            if n.node_id != cid:
                child_node.setdefault(cid, n.node_id)

    # 父映射(子 instance -> 父 instance 列表)
    parents = collections.defaultdict(list)
    for e in events:
        for ids in e["child_refs"].values():
            for c in ids:
                parents[c].append(e["instance_id"])

    # 来源(只为量误折)
    origin = {}
    if app_name == "new_step":
        for e in events:
            if e["node_id"] == "plateau":
                st = byid[e["child_refs"]["step"][0]]
                origin[e["instance_id"]] = st["start_idx"]
        for e in events:
            nid = e["node_id"]
            if nid == "old_plat":
                origin[e["instance_id"]] = e["end_idx"] + 1
            elif nid == "step":
                origin[e["instance_id"]] = e["start_idx"]
            elif nid in ("new_plat", "today"):
                ps = {origin[p] for p in parents[e["instance_id"]]}
                origin[e["instance_id"]] = min(ps) if len(ps) == 1 else ("multi", tuple(sorted(ps)))
    elif app_name in ("bottom_burst", "bb_v1"):
        head_of_bo = {}
        for e in events:
            if e["node_id"] == "burst":
                mem = e["child_refs"]["members"]
                for b in mem:
                    head_of_bo.setdefault(b, mem[0])
        for e in events:
            nid = e["node_id"]
            if nid == "burst":
                origin[e["instance_id"]] = e["child_refs"]["members"][0]
            elif nid == "tb":
                origin[e["instance_id"]] = head_of_bo.get(e.get("anchor_bo_id"), ("?", e.get("anchor_bo_id")))
            elif nid == "tb_seg":
                origin[e["instance_id"]] = head_of_bo.get(e.get("anchor_bo_id"), ("?", e.get("anchor_bo_id")))
    return dict(win=win, events=events, hits=hits, tier=tier, sub_nodes=sub_nodes, solve_free=solve_free,
                child_node=child_node, parents=parents, origin=origin, byid=byid, params=params, mod=mod)


def family_keys(rule, evs, ctx, fam_of_parent):
    """返回每个 event 的族编号列表(同号 = 折成一行)。"""
    n = len(evs)
    if rule == "R0_none":
        return list(range(n))
    if rule == "R1_same_span":
        keys = [(e["start_idx"], e["end_idx"]) for e in evs]
    elif rule == "R2_start":
        keys = [e["start_idx"] for e in evs]
    elif rule == "R3_end":
        keys = [e["end_idx"] for e in evs]
    elif rule == "R4_start_or_end":
        uf = UF(n)
        first_s, first_e = {}, {}
        for i, e in enumerate(evs):
            if e["start_idx"] in first_s:
                uf.u(i, first_s[e["start_idx"]])
            else:
                first_s[e["start_idx"]] = i
            if e["end_idx"] in first_e:
                uf.u(i, first_e[e["end_idx"]])
            else:
                first_e[e["end_idx"]] = i
        keys = [uf.f(i) for i in range(n)]
    elif rule == "R5_parent":
        keys = []
        for e in evs:
            ps = ctx["parents"].get(e["instance_id"], [])
            if e["node_id"] in ctx["child_node"] and ps:
                fams = sorted({fam_of_parent.get(p, ("?", p)) for p in ps}, key=str)
                keys.append(("P",) + tuple(fams))
            else:
                keys.append(("S", e["start_idx"]))
    else:
        raise ValueError(rule)
    remap = {}
    return [remap.setdefault(k, len(remap)) for k in keys]


def measure(app_name, sym):
    ctx = analyze_one(app_name, sym)
    events, tier = ctx["events"], ctx["tier"]
    out = {"app": app_name, "sym": sym, "bars": len(ctx["win"]), "hits": len(ctx["hits"]), "nodes": {}}
    # 父 node 的 R2 族(给 R5 用)
    fam_of_parent = {}
    for e in events:
        if e["node_id"] not in ctx["child_node"]:
            fam_of_parent[e["instance_id"]] = (e["node_id"], e["start_idx"])
    for nid in ctx["sub_nodes"]:
        evs_all = [e for e in events if e["node_id"] == nid]
        node_out = {"n_events": len(evs_all), "tiers": dict(collections.Counter(tier(e) for e in evs_all))}
        for level in LEVELS:
            if nid in ctx["solve_free"]:
                evs = evs_all
            else:
                evs = [e for e in evs_all if RANK[tier(e)] >= RANK[level]]
            lv = {}
            for rule in RULES:
                fk = family_keys(rule, evs, ctx, fam_of_parent)
                fams = collections.defaultdict(list)
                for i, k in enumerate(fk):
                    fams[k].append(evs[i])
                spans = [(min(x["start_idx"] for x in m), max(x["end_idx"] for x in m)) for m in fams.values()]
                _, rows = pack_lanes(spans)
                sizes = [len(m) for m in fams.values()]
                # 误折:族内来源 ≥ 2
                mis = 0
                mis_strict = 0   # 来源不同且跨度也不同的成员对(跨度完全相同的不算,折了不丢几何)
                for m in fams.values():
                    os_ = {str(ctx["origin"].get(x["instance_id"], "na")) for x in m}
                    if len(os_) > 1:
                        mis += 1
                        if any(str(ctx["origin"].get(a["instance_id"], "na")) != str(ctx["origin"].get(b["instance_id"], "na"))
                               and (a["start_idx"], a["end_idx"]) != (b["start_idx"], b["end_idx"])
                               for a in m for b in m):
                            mis_strict += 1
                # 族内档位混杂
                mixed = sum(1 for m in fams.values() if len({tier(x) for x in m}) > 1)
                # 同一天多成员:族内按 end 计数 >1 的 end 个数 / 族内 end 个数
                multi_day = 0; days = 0; max_per_day = 0
                for m in fams.values():
                    c = collections.Counter(x["end_idx"] for x in m)
                    days += len(c); multi_day += sum(1 for v in c.values() if v > 1)
                    max_per_day = max(max_per_day, max(c.values()) if c else 0)
                # 族的形状:成员是否两两嵌套(全序包含)
                non_nested = 0
                for m in fams.values():
                    ss = sorted(m, key=lambda x: (x["start_idx"], -x["end_idx"]))
                    ok = all(a["start_idx"] <= b["start_idx"] and b["end_idx"] <= a["end_idx"] or
                             b["start_idx"] <= a["start_idx"] and a["end_idx"] <= b["end_idx"]
                             for a, b in zip(ss, ss[1:]))
                    # 两两嵌套更严,这里查相邻(按起点排序后),足以抓出部分交叠
                    if not ok:
                        non_nested += 1
                lv[rule] = dict(items=len(evs), fams=len(fams), rows=rows, max_fam=max(sizes) if sizes else 0,
                                misfold=mis, misfold_strict=mis_strict, mixed_tier=mixed, multi_day=multi_day, days=days,
                                max_per_day=max_per_day, non_nested=non_nested)
            node_out[level] = lv
        out["nodes"][nid] = node_out
    # hit 层:bracket 行数、同日多 hit
    hits = ctx["hits"]
    hspans = [(h["start_idx"], h["end_idx"]) for h in hits]
    _, hrows0 = pack_lanes(hspans)
    by_start = collections.defaultdict(list)
    for h in hits:
        by_start[h["start_idx"]].append(h)
    _, hrows_fold = pack_lanes([(min(x["start_idx"] for x in m), max(x["end_idx"] for x in m))
                                for m in by_start.values()])
    # 买入日:按 eval_meta 的 end_node
    em = ctx["mod"].eval_meta(ctx["params"])
    endn = em["end_node"]
    node, _, slot = endn.partition(".")
    buys = collections.defaultdict(set)   # day -> set(hit start 族)
    hit_per_day = collections.Counter()
    for h in hits:
        ev = ctx["byid"].get(h["node_index"].get(node))
        if ev is None:
            continue
        targets = [ctx["byid"][c] for c in ev["child_refs"].get(slot, [])] if slot else [ev]
        ds = set()
        for t in targets:
            ds.update(range(t["start_idx"], t["end_idx"] + 1))
        for d in ds:
            buys[d].add(h["start_idx"])
            hit_per_day[d] += 1
    out["hit"] = dict(n=len(hits), bracket_rows_now=hrows0, fams_by_start=len(by_start),
                      bracket_rows_fold_start=hrows_fold, buy_days=len(buys),
                      days_multi_hit=sum(1 for v in hit_per_day.values() if v > 1),
                      max_hits_per_day=max(hit_per_day.values()) if hit_per_day else 0,
                      days_multi_family=sum(1 for v in buys.values() if len(v) > 1))
    return out


def main():
    syms = sys.argv[1:] or DEFAULT_SYMS
    results = []
    for app in APPS:
        for sym in syms:
            try:
                r = measure(app, sym)
            except Exception as ex:   # noqa: BLE001
                print("ERR", app, sym, repr(ex), file=sys.stderr)
                continue
            results.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
