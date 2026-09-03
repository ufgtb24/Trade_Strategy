# -*- coding: utf-8 -*-
"""补充分析 → extra_report.json:
① v4 独有 burst(111 个)样本质量 vs 共同 burst(burst 池差异贡献)
② v4 far_from_v1 日 × dist≤20/>20 交叉(域外扩内部结构)
③ v1 vs v4 邻近日相位差(v1 日相对 v4 日早/晚)
④ 首段 enter/confirm 距 burst 末分布(两代相位对比)
⑤ 同日两代值一致性抽验
⑥ v4 far 日的段序构成(v1 判死的首段 vs 后段)
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


def block(rows, label):
    if not rows:
        return {label: {"n_days": 0}}
    out = {"n_days": len(rows)}
    for k in ("mfr40", "ep40", "mfd40"):
        vals = [r[k] for r in rows if k in r]
        out[k] = round(med(vals), 4) if vals else None
    fp = defaultdict(int)
    for r in rows:
        if "fp" in r:
            fp[r["fp"]] += 1
    ud = fp["up"] + fp["down"]
    out["fp_ratio"] = round(fp["up"] / ud, 3) if ud else None
    return {label: out}


def burst_key_map(gen):
    out = {}
    for sym, v in D[gen].items():
        for m in v["matches"]:
            b = next(x for x in v["burst"] if x[0] == m["burst_iid"])
            out[m["match_id"]] = (sym, b[1], b[2])
    return out


bk4, bk1 = burst_key_map("v4"), burst_key_map("v1")
common = {bk for bk in bk4.values() if bk in set(bk1.values())}

v4_all = list({(r["symbol"], r["date"]): r for r in S if r["gen"] == "v4"}.values())
v1_all = list({(r["symbol"], r["date"]): r for r in S if r["gen"] == "v1"}.values())
rep = {}

# ① v4 独有 burst vs 共同 burst
v4_common = [r for r in v4_all if bk4[r["match_id"]] in common]
v4_excl = [r for r in v4_all if bk4[r["match_id"]] not in common]
rep["v4_burst_pool_split"] = {**block(v4_common, "v4_on_common_bursts"),
                             **block(v4_excl, "v4_on_v4only_bursts")}

# ② v4 far_from_v1 × dist
all1 = {(r["symbol"], r["t"]) for r in S if r["gen"] == "v1"}
far = [r for r in v4_all if not any((r["symbol"], r["t"] + d) in all1
                                    for d in (-2, -1, 0, 1, 2))]
rep["v4_far_from_v1_X_dist"] = {
    **block([r for r in far if r["dist_burst_end"] <= 20], "far_e(<=20)"),
    **block([r for r in far if r["dist_burst_end"] > 20], "far_l(>20)")}

# ③ 相位差:共同 burst 内,v1 日 vs 最近 v4 日
days4, days1 = defaultdict(set), defaultdict(set)
for r in S:
    if r["gen"] == "v4":
        days4[bk4[r["match_id"]]].add(r["t"])
    else:
        days1[bk1[r["match_id"]]].add(r["t"])
shift = defaultdict(int)
for bk in common:
    d4 = sorted(days4.get(bk, set()))
    for t in days1.get(bk, set()):
        near = [u for u in d4 if abs(u - t) <= 2 and u != t]
        if t in d4:
            shift["same"] += 1
        elif near:
            u = near[0]
            shift["v4_earlier" if u < t else "v4_later"] += 1
        else:
            shift["no_v4_day"] += 1
rep["phase_shift_v1_vs_v4"] = dict(shift)

# ④ 两代首买点距 burst 末(confirm/enter 相位)
ent4, ent1 = [], []
for sym, v in D["v4"].items():
    for m in v["matches"]:
        tb = next(t for t in v["tb"] if t[0] == m["tb_iid"])
        b = next(x for x in v["burst"] if x[0] == m["burst_iid"])
        ent4.append(tb[1] - b[2])
for sym, v in D["v1"].items():
    for m in v["matches"]:
        tb = next(t for t in v["tb"] if t[0] == m["tb_iid"])
        b = next(x for x in v["burst"] if x[0] == m["burst_iid"])
        ent1.append(tb[1] - b[2])
rep["first_buy_dist_from_burst_end"] = {
    "v4_match_median": med(ent4), "v1_match_median": med(ent1),
    "v4_p25": sorted(ent4)[len(ent4) // 4], "v4_p75": sorted(ent4)[3 * len(ent4) // 4],
    "v1_p25": sorted(ent1)[len(ent1) // 4], "v1_p75": sorted(ent1)[3 * len(ent1) // 4]}

# ⑤ 同日两代值一致性抽验(同物理日应同值)
same_day_pairs = mismatch = 0
for r1 in S:
    if r1["gen"] != "v1":
        continue
    if r1["t"] in days4.get(bk1[r1["match_id"]], set()):
        same_day_pairs += 1
        r4 = next((r for r in S if r["gen"] == "v4" and r["symbol"] == r1["symbol"]
                   and r["t"] == r1["t"] and "mfr40" in r), None)
        if r4 is not None and "mfr40" in r1 and abs(r4["mfr40"] - r1["mfr40"]) > 1e-12:
            mismatch += 1
rep["same_day_value_check"] = {"n_pairs": same_day_pairs, "mismatch": mismatch}

# ⑥ v4 far 日的段序构成(v1 判死的首段 vs 后段)
far_ids = {id(r) for r in far}
rep["far_seg_ord"] = {
    "first": sum(1 for r in far if r["seg_ord"] == 0),
    "later": sum(1 for r in far if r["seg_ord"] > 0)}
rep["near_seg_ord"] = {
    "first": sum(1 for r in v4_all if id(r) not in far_ids and r["seg_ord"] == 0),
    "later": sum(1 for r in v4_all if id(r) not in far_ids and r["seg_ord"] > 0)}

(HERE / "extra_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
print(json.dumps(rep, ensure_ascii=False, indent=1))
