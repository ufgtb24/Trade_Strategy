# -*- coding: utf-8 -*-
"""任务3+4:核心配对对照 + v4 内部分解 → core_report.json。

口径纪律(昨日结论):日级统计按 (symbol,date) 去重;ep/mfd/mfr 三口径同报;
首穿率 = up/(up+down)(down 含四态中 down;none 不入分母)。
median 一律日级(另附 match 级复核列)。
"""
import json
import statistics as st
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
S = json.loads((HERE / "daily_samples.json").read_text())["samples"]
D = json.loads((HERE / "extracted.json").read_text())


def med(xs):
    return st.median(xs) if xs else None


def q(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    i = (len(xs) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def block(rows, label):
    """一组日级(已去重)样本的三口径 + 首穿。"""
    if not rows:
        return {label: {"n_days": 0}}
    out = {"n_days": len(rows)}
    for k in ("mfr40", "mfd40", "ep40"):
        vals = [r[k] for r in rows if k in r]
        out[k] = {"median": med(vals), "q25": q(vals, .25), "q75": q(vals, .75),
                  "n": len(vals)}
    fp = defaultdict(int)
    for r in rows:
        if "fp" in r:
            fp[r["fp"]] += 1
    ud = fp["up"] + fp["down"]
    out["fp"] = {"up": fp["up"], "down": fp["down"], "none": fp["none"],
                 "ratio": fp["up"] / ud if ud else None, "n_fp": sum(fp.values())}
    return {label: out}


def dedup(rows):
    """(symbol,date) 去重(跨 match/段)。"""
    best = {}
    for r in rows:
        key = (r["symbol"], r["date"])
        if key not in best:
            best[key] = r
    return list(best.values())


# ── 0. 全体日级总览 ──
rep = {}
v4_all = dedup([r for r in S if r["gen"] == "v4"])
v1_all = dedup([r for r in S if r["gen"] == "v1"])
rep["overall_daily"] = {**block(v4_all, "v4"), **block(v1_all, "v1")}

# match 级复核(scan stats 口径)
mv4 = [m["fr"] for sym, v in D["v4"].items() for m in v["matches"] if m["fr"] is not None]
mv1 = [m["fr"] for sym, v in D["v1"].items() for m in v["matches"] if m["fr"] is not None]
rep["overall_match_level_mfr_median"] = {"v4": med(mv4), "v1": med(mv1)}

# ── 3a. 共同 burst 内配对 ──
# burst 键:从样本的 match_id 反查 burst span
def burst_key_map(gen):
    out = {}
    for sym, v in D[gen].items():
        for m in v["matches"]:
            b = next(x for x in v["burst"] if x[0] == m["burst_iid"])
            out[m["match_id"]] = (sym, b[1], b[2])
    return out

bk4, bk1 = burst_key_map("v4"), burst_key_map("v1")
set1 = set(bk1.values())
common_bursts = {bk for bk in bk4.values() if bk in set1}
rep["common_bursts_n"] = len(common_bursts)

v4_c = dedup([r for r in S if r["gen"] == "v4" and bk4[r["match_id"]] in common_bursts])
v1_c = dedup([r for r in S if r["gen"] == "v1" and bk1[r["match_id"]] in common_bursts])
rep["common_burst_daily"] = {**block(v4_c, "v4"), **block(v1_c, "v1")}

# burst 级配对差:每 burst 内各代日级 mfr median,差分布
def per_burst_med(rows, bk):
    g = defaultdict(list)
    for r in rows:
        g[bk[r["match_id"]]].append(r)
    return {k: med([r["mfr40"] for r in v if "mfr40" in r]) for k, v in g.items()}

pm4 = per_burst_med([r for r in S if r["gen"] == "v4"], bk4)
pm1 = per_burst_med([r for r in S if r["gen"] == "v1"], bk1)
pairs = [(pm1[k], pm4[k]) for k in common_bursts if k in pm1 and k in pm4
         and pm1[k] is not None and pm4[k] is not None]
diffs = [b - a for a, b in pairs]
rep["per_burst_paired_mfr_median"] = {
    "n_pairs": len(pairs),
    "v1_median_of_burst_medians": med([a for a, _ in pairs]),
    "v4_median_of_burst_medians": med([b for _, b in pairs]),
    "median_diff_v4_minus_v1": med(diffs),
    "n_v4_worse": sum(1 for d in diffs if d < 0),
    "n_v4_better": sum(1 for d in diffs if d > 0),
}

# ── 3b. 同日/邻近配对(同 burst 内,±2 bar)──
days4 = defaultdict(set)   # burst -> {t}
days1 = defaultdict(set)
for r in S:
    if r["gen"] == "v4":
        days4[bk4[r["match_id"]]].add(r["t"])
    else:
        days1[bk1[r["match_id"]]].add(r["t"])
n_same = n_near = n_v1_only_day = 0
v1_only_days_rows = []
v4_only_days_rows = []
for bk in common_bursts:
    d4, d1 = days4.get(bk, set()), days1.get(bk, set())
    for t in d1:
        if t in d4:
            n_same += 1
        elif any(abs(t - u) <= 2 for u in d4):
            n_near += 1
        else:
            n_v1_only_day += 1
            v1_only_days_rows.append(
                next(r for r in S if r["gen"] == "v1" and r["match_id"] in
                     [m for m, b in bk1.items() if b == bk] and r["t"] == t))
    for t in d4 - d1:
        if not any(abs(t - u) <= 2 for u in d1):
            v4_only_days_rows.append(
                next(r for r in S if r["gen"] == "v4" and r["match_id"] in
                     [m for m, b in bk4.items() if b == bk] and r["t"] == t))
rep["overlap_common_burst"] = {
    "v1_days_total": sum(len(days1.get(bk, set())) for bk in common_bursts),
    "same_day": n_same, "near_pm2": n_near, "v1_only": n_v1_only_day,
    "v4_days_total": sum(len(days4.get(bk, set())) for bk in common_bursts),
    "v4_only": len(v4_only_days_rows)}

# 同日样本结果一致性检查(同一物理日两代应同值)
same_rows_1 = [r for r in S if r["gen"] == "v1" and r["t"] in
               {t for bk in common_bursts for t in (days1.get(bk, set()) & days4.get(bk, set()))}
               and bk1[r["match_id"]] in common_bursts]

# v1-only 日(共同 burst 内)画像 + 指标
rep["v1_only_days"] = block(dedup(v1_only_days_rows), "v1_only_common_burst")
rep["v4_only_days"] = block(dedup(v4_only_days_rows), "v4_only_common_burst")

# ── 3c. v4 全体独有买点(相对 v1 全体日集)位置画像 ──
all1 = {(r["symbol"], r["t"]) for r in S if r["gen"] == "v1"}
v4_only_all = [r for r in v4_all if (r["symbol"], r["t"]) not in all1
               and not any((r["symbol"], r["t"] + d) in all1 for d in (-2, -1, 1, 2))]
v4_shared_all = [r for r in v4_all if r not in v4_only_all]
rep["v4_vs_v1day_universe"] = {
    "v4_days": len(v4_all),
    "v4_days_same_or_near_v1": len(v4_all) - len(v4_only_all),
    "v4_days_far_from_any_v1": len(v4_only_all)}
rep["v4_split_by_v1_overlap"] = {
    **block(dedup(v4_only_all), "v4_far_from_v1"),
    **block(dedup(v4_shared_all), "v4_same_or_near_v1")}

# ── 4. v4 内部分解 ──
first = [r for r in v4_all if r["seg_ord"] == 0]
later = [r for r in v4_all if r["seg_ord"] > 0]
rep["v4_first_vs_later_seg"] = {**block(dedup(first), "first_seg"),
                                **block(dedup(later), "later_seg")}
early = [r for r in v4_all if r["dist_burst_end"] <= 20]
late = [r for r in v4_all if r["dist_burst_end"] > 20]
rep["v4_early_vs_late"] = {**block(dedup(early), "dist<=20"), **block(dedup(late), "dist>20")}
# 交叉表
cross = {}
for a, an in ((early, "e"), (late, "l")):
    for b, bn in ((first, "F"), (later, "L")):
        rows = [r for r in a if r in b]
        cross[f"{bn}_{an}"] = block(dedup(rows), f"{bn}_{an}")[f"{bn}_{an}"]
rep["v4_cross_firstXdist"] = cross

# 段内位置:enter 前 3 根 vs 其余
head = [r for r in v4_all if r["seg_off"] <= 2]
tail = [r for r in v4_all if r["seg_off"] > 2]
rep["v4_head_vs_tail_of_seg"] = {**block(dedup(head), "seg_off<=2"),
                                 **block(dedup(tail), "seg_off>2")}

# v1 内部对照:同在 ≤20 域内,两代差
rep["v1_within20"] = block([r for r in v1_all if r["dist_burst_end"] <= 20], "v1_all")
v4_e = dedup([r for r in S if r["gen"] == "v4" and r["dist_burst_end"] <= 20])
rep["v4_within20"] = block(v4_e, "v4_within20")

# v1 事件 outcome 分解(上下文)
rep["v1_outcome"] = {}
for oc in ("rise", "break", "weak", "timeout"):
    rows = [r for r in v1_all if r["seg_outcome"] == oc]
    rep["v1_outcome"][oc] = block(rows, oc)[oc]
rep["v4_seg_outcome"] = {}
for oc in ("rise", "break", "weak", "timeout"):
    rows = [r for r in v4_all if r["seg_outcome"] == oc]
    rep["v4_seg_outcome"][oc] = block(rows, oc)[oc]

(HERE / "core_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
print(json.dumps(rep, ensure_ascii=False, indent=1))
