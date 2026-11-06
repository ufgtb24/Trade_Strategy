"""研究用临时代码(skeptic):在真实股票上量 new_step 第二版各 band 的嵌套与并存,检验折叠规则的反例。

只读训练段副本(经 path2_web.data.read_bars / view_dataset_dir = datasets/pkls_until_20251231)。
口径与 compare 相同:每只股票截到训练段末日的全部 K 线。

量什么(每只股票,再汇总):
  1. plateau 各档(detected = 全部实例;in_hit = 进了 hit 的实例)的行数:
     现状 = greedy lane packing 的 lane 数(与前端 packLanes 同法);
     按「同 node 同起点」折叠后 = 把同起点的实例并成一条 [起点, 最远终点] 再 packing 的 lane 数。
  2. 同一天几个实例:同一个当天 t 上的 in_hit 实例数,拆成「同起点(同一段阶跃的不同前缀)」与「不同起点(两段阶跃并存)」。
  3. 起点相同终点也相同的实例对(几何完全重合、只差子段)占比。
  4. step / new_plat / today 三个子段 band 同样量现状 lane 数与同起点折叠后的 lane 数。
  5. bracket(hit 跨度)同样量。
"""
from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict

import pandas as pd

from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars, slice_window, TRAIN_END
from path2_apps.new_step import dag_spec as app

ANNOTATED = ["CRNC", "GEVO", "INDO", "QBTS", "RGTI", "SMX"]


def pack_lanes(spans):
    """与 path2_web_ui/src/render/geometry.ts packLanes 同法:按起点升序贪心放入第一个末端 < 本起点的 lane。"""
    ends = []
    for s, e in sorted(spans):
        for k, end in enumerate(ends):
            if end < s:
                ends[k] = e
                break
        else:
            ends.append(e)
    return len(ends)


def fold_by_start(spans):
    g = defaultdict(int)
    for s, e in spans:
        g[s] = max(g[s], e)
    return list(g.items())


def children(ev):
    out = []
    for v in ev.child_slots().values():
        out.extend(v if isinstance(v, tuple) else (v,))
    return out


def analyze_symbol(cfg, sym, p):
    win = slice_window(read_bars(view_dataset_dir(cfg), sym), "1900-01-01", TRAIN_END)
    if len(win) < 100:
        return None
    res = app.analyze(win, p)
    plats = [e for e in res.events if e.node_id == "plateau"]
    hit_ids = set()
    for h in res.hits:
        hit_ids.add(h.node_index["plateau"].instance_id)
    # 子段按对象去重(与 serialize_analysis 同:同一对象只出一次)
    sub = defaultdict(dict)
    for e in plats:
        for c in children(e):
            sub[c.node_id][id(c)] = c
    hit_sub = defaultdict(dict)
    for e in plats:
        if e.instance_id in hit_ids:
            for c in children(e):
                hit_sub[c.node_id][id(c)] = c

    def lanes(evs):
        spans = [(x.start_idx, x.end_idx) for x in evs]
        if not spans:
            return 0, 0, 0
        return len(spans), pack_lanes(spans), pack_lanes(fold_by_start(spans))

    r = {"sym": sym, "n_bars": len(win)}
    det = plats
    hit = [e for e in plats if e.instance_id in hit_ids]
    r["plateau_det"] = lanes(det)
    r["plateau_hit"] = lanes(hit)
    for nid in ("old_plat", "step", "new_plat", "today"):
        r[f"{nid}_det"] = lanes(sub[nid].values())
        r[f"{nid}_hit"] = lanes(hit_sub[nid].values())
    r["bracket"] = lanes(res.hits)
    # 同一天多实例(in_hit)
    by_t = defaultdict(list)
    for e in hit:
        by_t[e.end_idx].append(e)
    same_s_multi = 0      # 当天里同起点 >1 个前缀
    diff_s_multi = 0      # 当天里来自 >1 个起点
    per_day = Counter()
    for t, evs in by_t.items():
        per_day[len(evs)] += 1
        starts = Counter(x.start_idx for x in evs)
        if any(c > 1 for c in starts.values()):
            same_s_multi += 1
        if len(starts) > 1:
            diff_s_multi += 1
    r["hit_days"] = len(by_t)
    r["hit_days_same_s_multi"] = same_s_multi
    r["hit_days_diff_s_multi"] = diff_s_multi
    r["hits_per_day"] = dict(per_day)
    # detected 档同样
    by_t_d = defaultdict(list)
    for e in det:
        by_t_d[e.end_idx].append(e)
    r["det_days"] = len(by_t_d)
    r["det_days_same_s_multi"] = sum(1 for evs in by_t_d.values()
                                     if any(c > 1 for c in Counter(x.start_idx for x in evs).values()))
    r["det_days_diff_s_multi"] = sum(1 for evs in by_t_d.values()
                                     if len({x.start_idx for x in evs}) > 1)
    # 每段阶跃(同起点)几个前缀、每个前缀几天
    pref = defaultdict(set)
    fam_days = defaultdict(int)
    fam_hit_days = defaultdict(int)
    for e in det:
        pref[e.start_idx].add(e.step.end_idx)
        fam_days[(e.start_idx, e.step.end_idx)] += 1
    for e in hit:
        fam_hit_days[(e.start_idx, e.step.end_idx)] += 1
    r["prefixes_per_start"] = Counter(len(v) for v in pref.values())
    r["fam_days"] = list(fam_days.values())
    r["fam_hit_days"] = list(fam_hit_days.values())
    # 有 hit 的族里,hit 天是否连续(族内断档数)
    gaps = []
    fam_t = defaultdict(list)
    for e in hit:
        fam_t[(e.start_idx, e.step.end_idx)].append(e.end_idx)
    for k, ts in fam_t.items():
        ts = sorted(ts)
        gaps.append(sum(1 for a, b in zip(ts, ts[1:]) if b - a > 1))
    r["hit_fam_gaps"] = gaps
    # 族跨两段阶跃:不同起点的族在时间上重叠(旧族未结束新族已开)
    fam_span = defaultdict(lambda: [10**9, -1])
    for e in det:
        k = e.start_idx
        fam_span[k][0] = min(fam_span[k][0], e.start_idx)
        fam_span[k][1] = max(fam_span[k][1], e.end_idx)
    r["start_rows_overlapping"] = pack_lanes([tuple(v) for v in fam_span.values()]) if fam_span else 0
    return r


def main():
    cfg = load_config()
    p = app.load_params()
    n_random = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    syms = sorted(x.stem for x in view_dataset_dir(cfg).glob("*.pkl"))
    random.seed(20261105)
    rand = random.sample([s for s in syms if s not in ANNOTATED], n_random)
    rows = []
    for sym in ANNOTATED + rand:
        try:
            r = analyze_symbol(cfg, sym, p)
        except Exception as ex:  # noqa: BLE001 研究脚本:坏股票跳过
            print("skip", sym, type(ex).__name__, ex)
            continue
        if r is None:
            continue
        r["group"] = "annot" if sym in ANNOTATED else "random"
        rows.append(r)
    pd.to_pickle(rows, "/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/"
                       "bb41a4fd-4350-46f3-b781-d37b145f06a1/scratchpad/skeptic_fold_rows.pkl")
    for r in rows:
        if r["group"] == "annot":
            print(r["sym"], {k: v for k, v in r.items() if k.endswith(("_det", "_hit")) or k == "bracket"},
                  "hit_days", r["hit_days"], "same_s_multi", r["hit_days_same_s_multi"],
                  "diff_s_multi", r["hit_days_diff_s_multi"], "per_day", r["hits_per_day"])


if __name__ == "__main__":
    main()
