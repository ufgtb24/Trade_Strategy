"""第二批统计:整合 principle P1-P5+P3′ / skeptic E1-E5 / architect B/F 方案 / lead ABOS 假想买点表。

全部基于 HEAD(OR)版语义手写复刻(与 full_stats.py 同口径,scan 段级 442/442 已锁)。
输出 repro/stats_part3.json。
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

import numpy as np
import pandas as pd
from path2.calc.atr import calculate_tr_median, rolling_atr_pct_nanmedian
from path2.eval import _first_passage_at
from path2_web.data import slice_window

SCAN = json.load(open(REPO / "outputs/path2_web/scans/20260817T142145.json"))
WIN_START, WIN_END = SCAN["scan"]["win_start"], SCAN["scan"]["win_end"]
START_TS = pd.to_datetime(SCAN["scan"]["start_date"])
END_TS = pd.to_datetime(SCAN["scan"]["end_date"])
HORIZON, FP_K = SCAN["scan"]["label_horizon"], SCAN["scan"]["first_passage_k"]
STOP_K, MAX_SPAN, VOL_W = 1, 60, 14


def label_at(closes, hi_a, lo_a, M, t, n, lo_i, hi_i):
    if not (lo_i <= t <= hi_i and t + HORIZON < n):
        return None
    return dict(ep=closes[t + HORIZON] / closes[t] - 1.0,
                mfr=float(hi_a[t + 1:t + HORIZON + 1].max()) / closes[t] - 1.0,
                mfd=float(lo_a[t + 1:t + HORIZON + 1].min()) / closes[t] - 1.0,
                fp=_first_passage_at(hi_a, lo_a, closes, M, t, HORIZON, FP_K))


def run_machine(closes, opens, vol, bo, gbot, brise, *, mode="head", theta=None,
                volumes=None, bstart=None, bend=None):
    """HEAD(OR) 复刻 + 变体:mode='B'(浅回撤快通,θ·brise)/'F'(段活过反弹)。

    返回 segs/outcome + 逐根事件(vbounce/enter/enter_offset/micro_refresh/
    down_span_vol)——各事件带 dd(burst 分母)与 dd_v(vol 分母)双口径。
    """
    n = len(closes)
    end = min(bo + MAX_SPAN, n - 1)
    state, peak, trough, cnt, enter = "UP", float(closes[bo]), float("inf"), 0, -1
    g = float(gbot)
    segs, ev = [], {"vbounce": [], "enter": [], "micro": [0, 0]}
    down_v_sum, down_cnt = 0.0, 0
    down_start = None
    burst_v = (float(np.mean(volumes[bstart:bend + 1]))
               if volumes is not None and bend is not None and bend >= bstart else None)
    for i in range(bo + 1, end + 1):
        c = float(closes[i])
        v = vol[i]
        if volumes is not None and down_start is not None:
            down_v_sum += float(volumes[i])
            down_cnt += 1
        if c < g:
            if state == "STABLE":
                segs.append((enter, i - 1, "break"))
            return dict(segs=tuple(segs), outcome="break", ev=ev,
                        down_v_ratio=(down_v_sum / down_cnt / burst_v)
                        if burst_v and down_cnt else None)
        if state == "UP":
            if c > peak:
                peak = c
            if (c < float(opens[i])) or c < float(closes[i - 1]):
                state, trough, cnt = "DOWN", c, 0
                down_start = i
        elif state == "DOWN":
            dd = (peak - trough) / brise if brise > 0 else None
            if c < trough:
                if v == v and (trough - c) / v < 0.3:
                    ev["micro"][0] += 1
                ev["micro"][1] += 1
                trough, cnt = c, 0
            elif v == v and c > trough + 1.5 * v:
                if mode == "B" and theta is not None and dd is not None and dd < theta:
                    state, enter = "STABLE", i      # 浅回撤快通:rise 根当根入段
                    ev["enter"].append(dict(
                        i=i, dd=dd, dd_v=(peak - trough) / v,
                        off=(c - trough) / v, new_vs_head=True,
                        vshrink=(down_v_sum / down_cnt / burst_v)
                        if burst_v and down_cnt else None))
                else:
                    state = "UP"
                    ev["vbounce"].append(dict(
                        i=i, dd=dd, dd_v=(peak - trough) / v,
                        off=(c - trough) / v,
                        vshrink=(down_v_sum / down_cnt / burst_v)
                        if burst_v and down_cnt else None))
            else:
                cnt += 1
                if cnt >= STOP_K:
                    state, enter = "STABLE", i
                    ev["enter"].append(dict(
                        i=i, dd=dd, dd_v=(peak - trough) / v, off=(c - trough) / v,
                        new_vs_head=(mode == "B"),
                        vshrink=(down_v_sum / down_cnt / burst_v)
                        if burst_v and down_cnt else None))
        else:  # STABLE
            if c < trough:
                segs.append((enter, i - 1, "weak"))
                state, trough, cnt = "DOWN", c, 0
                down_start = i
            elif mode == "F":
                if (c < float(opens[i])) or c < float(closes[i - 1]):
                    segs.append((enter, i - 1, "rise"))
                    g = trough
                    state, trough, cnt = "DOWN", c, 0
                    down_start = i
            else:  # head:OR 收口
                if (v == v and c > trough + 1.5 * v) or (c > peak):
                    segs.append((enter, i - 1, "rise"))
                    g = trough
                    state = "UP"
                    if c > peak:
                        peak = c
    if state == "STABLE":
        segs.append((enter, end, "timeout"))
    return dict(segs=tuple(segs), outcome="budget", ev=ev,
                down_v_ratio=(down_v_sum / down_cnt / burst_v)
                if burst_v and down_cnt else None)


# ── 主循环 ──
head_machines = []          # (sym, m, ctx) ctx=重算 label 所需
abos_done = False
for r in SCAN["results"]:
    sym = r["symbol"]
    events = r["per_pattern"]["bottom_burst"]["analysis"]["events"]
    bo_end = {e["instance_id"]: e["end_idx"] for e in events if e["node_id"] == "bo"}
    bursts = [e for e in events if e["node_id"] == "burst"]
    df = pd.read_pickle(REPO / f"datasets/pkls/{sym}.pkl")
    win = slice_window(df, WIN_START, WIN_END).reset_index(drop=True)
    closes = win["close"].to_numpy(float)
    opens = win["open"].to_numpy(float)
    vols = win["volume"].to_numpy(float)
    vol = calculate_tr_median(win["high"], win["low"], win["close"], VOL_W).to_numpy(float)
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).to_numpy(float)
    hi_a, lo_a = win["high"].to_numpy(float), win["low"].to_numpy(float)
    lo_i = int(win["date"].searchsorted(START_TS, "left"))
    hi_i = int(win["date"].searchsorted(END_TS, "right")) - 1
    n = len(win)
    dts = [str(d)[:10] for d in win["date"]]

    def L(t):
        return label_at(closes, hi_a, lo_a, M, t, n, lo_i, hi_i)

    if sym == "ABOS" and not abos_done:
        abos_rows = []
        for t in range(258, 265):
            lab = L(t)
            abos_rows.append(dict(i=t, date=dts[t], close=round(float(closes[t]), 3),
                                  **({k: round(x, 4) if isinstance(x, float) else x
                                     for k, x in lab.items()} if lab else {})))
        out_abos = abos_rows
        abos_done = True

    for b in bursts:
        bo = bo_end[b["child_refs"]["members"][-1]]
        gbot = float(closes[b["start_idx"]:b["end_idx"] + 1].min())
        brise = float(closes[b["end_idx"]] - closes[b["start_idx"]])
        ctx = dict(sym=sym, closes=closes, hi_a=hi_a, lo_a=lo_a, M=M, n=n,
                   lo_i=lo_i, hi_i=hi_i, dts=dts, bo=bo, brise=brise,
                   bstart=b["start_idx"], bend=b["end_idx"],
                   burst_rel_v=(float(vols[b["start_idx"]:b["end_idx"] + 1].mean()
                                      / vols[max(0, b["start_idx"] - 63):b["start_idx"]].mean())
                                if b["start_idx"] >= 63 and
                                vols[max(0, b["start_idx"] - 63):b["start_idx"]].mean() > 0
                                else None))
        m = run_machine(closes, opens, vol, bo, gbot, brise, volumes=vols,
                        bstart=b["start_idx"], bend=b["end_idx"])
        head_machines.append((m, ctx, closes, opens, vol, bo, gbot, brise))

# ── 通用小工具 ──
def agg(recs, keys=("ep", "mfr", "mfd"), fp_key="fp"):
    if not recs:
        return None
    o = dict(n=len(recs))
    for k in keys:
        vals = [x[k] for x in recs if x.get(k) is not None]
        if vals:
            o[f"{k}_med"] = round(float(np.median(vals)), 4)
            if k == "mfd":
                o["mfd_q10"] = round(float(np.percentile(vals, 10)), 4)
    fps = [x[fp_key] for x in recs if x.get(fp_key)]
    den = len(fps)
    if den:
        o["fp_up"] = round(sum(1 for f in fps if f == "up") / den, 3)
        o["fp_down"] = round(sum(1 for f in fps if f == "down") / den, 3)
        o["fp_none"] = round(sum(1 for f in fps if f == "none") / den, 3)
    return o


def half(rec):
    """E1 双窗:买点日期 2025H1 / 2025H2(+2026 缓冲归 H2)。"""
    return "H1" if rec["date"] < "2025-07-01" else "H2"


def enrich(recs, ctx_of):
    """给事件 rec 注入 label + 日期 + 半窗。ctx_of: rec -> ctx。"""
    out = []
    for rec in recs:
        ctx = ctx_of(rec)
        lab = label_at(ctx["closes"], ctx["hi_a"], ctx["lo_a"], ctx["M"],
                       rec["i"], ctx["n"], ctx["lo_i"], ctx["hi_i"])
        if lab:
            rec = dict(rec, **lab, date=ctx["dts"][rec["i"]], half=half(
                dict(date=ctx["dts"][rec["i"]])))
        out.append(rec)
    return out


out = {"abos_hyp": out_abos}

# ══ E3/P3/P3′:V 根与其次根的配对口径 ══
v_recs, e_recs = {}, {}
for m, ctx, *_ in head_machines:
    for x in m["ev"]["vbounce"]:
        v_recs.setdefault((ctx["sym"], x["i"]), []).append((x, m, ctx))
    for x in m["ev"]["enter"]:
        e_recs.setdefault((ctx["sym"], x["i"]), []).append((x, m, ctx))

pairs_V, pairs_next = [], []
for key, lst in v_recs.items():
    x, m, ctx = lst[0]
    lab = label_at(ctx["closes"], ctx["hi_a"], ctx["lo_a"], ctx["M"],
                   x["i"], ctx["n"], ctx["lo_i"], ctx["hi_i"])
    lab_nxt = label_at(ctx["closes"], ctx["hi_a"], ctx["lo_a"], ctx["M"],
                       x["i"] + 1, ctx["n"], ctx["lo_i"], ctx["hi_i"])
    # 同机器现行段根 label 均值(配对基准)
    ent_labs = [label_at(ctx["closes"], ctx["hi_a"], ctx["lo_a"], ctx["M"],
                         e["i"], ctx["n"], ctx["lo_i"], ctx["hi_i"])
                for e in m["ev"]["enter"]]
    ent_labs = [e for e in ent_labs if e]
    base = {k: float(np.mean([e[k] for e in ent_labs]))
            for k in ("ep", "mfr", "mfd")} if ent_labs else None
    date = ctx["dts"][x["i"]]
    rec = dict(sym=key[0], i=x["i"], dd=x["dd"], dd_v=x["dd_v"], date=date,
               half=half(dict(date=date)), n_ent=len(ent_labs))
    if lab:
        rec.update(dict(ep=lab["ep"], mfr=lab["mfr"], mfd=lab["mfd"], fp=lab["fp"]))
        if base:
            rec.update({f"pdiff_{k}": lab[k] - base[k] for k in ("ep", "mfr", "mfd")})
        pairs_V.append(rec)
    if lab_nxt:
        rec2 = dict(rec, ep=lab_nxt["ep"], mfr=lab_nxt["mfr"], mfd=lab_nxt["mfd"],
                    fp=lab_nxt["fp"], date=ctx["dts"][x["i"] + 1],
                    half=half(dict(date=ctx["dts"][x["i"] + 1])))
        if base:
            rec2.update({f"pdiff_{k}": lab_nxt[k] - base[k] for k in ("ep", "mfr", "mfd")})
        pairs_next.append(rec2)

def shallow_deep(recs, dkey="dd"):
    s = [x for x in recs if x.get(dkey) is not None and x[dkey] < 0.2]
    d = [x for x in recs if x.get(dkey) is not None and x[dkey] >= 0.2]
    return dict(shallow=agg(s), deep=agg(d),
                shallow_H1=agg([x for x in s if x["half"] == "H1"]),
                shallow_H2=agg([x for x in s if x["half"] == "H2"]),
                deep_H1=agg([x for x in d if x["half"] == "H1"]),
                deep_H2=agg([x for x in d if x["half"] == "H2"]),
                dd_missing=sum(1 for x in recs if x.get(dkey) is None))

def pdiff_med(recs, dkey="dd"):
    o = {}
    for grp, sel in (("shallow", lambda x: x.get(dkey) is not None and x[dkey] < 0.2),
                     ("deep", lambda x: x.get(dkey) is not None and x[dkey] >= 0.2)):
        sub = [x for x in recs if sel(x) and "pdiff_ep" in x]
        if sub:
            o[grp] = dict(n=len(sub),
                          pdiff_ep_med=round(float(np.median([x["pdiff_ep"] for x in sub])), 4),
                          pdiff_mfd_med=round(float(np.median([x["pdiff_mfd"] for x in sub])), 4),
                          pdiff_mfr_med=round(float(np.median([x["pdiff_mfr"] for x in sub])), 4))
    return o

out["P3_vroot"] = dict(burst_denom=shallow_deep(pairs_V), vol_denom=shallow_deep(pairs_V, "dd_v"),
                       paired=pdiff_med(pairs_V))
out["P3prime_nextroot"] = dict(burst_denom=shallow_deep(pairs_next),
                               vol_denom=shallow_deep(pairs_next, "dd_v"),
                               paired=pdiff_med(pairs_next))
out["P3_vroot"]["dd_v_def"] = "(peak-trough)/vol(i) at V root"

# ══ P2:现行段根 dd 三桶 + 量能萎缩子条件 ══
enter_flat = []
for m, ctx, *_ in head_machines:
    for x in m["ev"]["enter"]:
        lab = label_at(ctx["closes"], ctx["hi_a"], ctx["lo_a"], ctx["M"],
                       x["i"], ctx["n"], ctx["lo_i"], ctx["hi_i"])
        if lab:
            enter_flat.append(dict(**x, **lab, date=ctx["dts"][x["i"]],
                                   half=half(dict(date=ctx["dts"][x["i"]]))))
p2 = dict(
    lt02=agg([x for x in enter_flat if x["dd"] is not None and x["dd"] < 0.2]),
    mid_02_05=agg([x for x in enter_flat if x["dd"] is not None and 0.2 <= x["dd"] < 0.5]),
    ge05=agg([x for x in enter_flat if x["dd"] is not None and x["dd"] >= 0.5]),
    vol_denom=dict(shallow15=agg([x for x in enter_flat if x["dd_v"] is not None and x["dd_v"] < 1.5]),
                   deep15=agg([x for x in enter_flat if x["dd_v"] is not None and x["dd_v"] >= 1.5])),
)
sh = [x for x in enter_flat if x["dd"] is not None and x["dd"] < 0.2 and x.get("vshrink")]
vs = sorted(x["vshrink"] for x in sh)
if vs:
    med = vs[len(vs) // 2]
    p2["shallow_volshrink_split"] = dict(
        median_ratio=round(med, 3),
        shrink_lt_med=agg([x for x in sh if x["vshrink"] < med]),
        shrink_ge_med=agg([x for x in sh if x["vshrink"] >= med]))
out["P2_enter"] = p2

# ══ P4:enter 根相对 trough 偏移 ══
off = [x for x in enter_flat if x["off"] is not None]
out["P4_offset"] = dict(
    off_pct={p: round(float(np.percentile([x["off"] for x in off], p)), 3)
             for p in (10, 25, 50, 75, 90)},
    gt05vol=agg([x for x in off if x["off"] > 0.5]),
    le05vol=agg([x for x in off if x["off"] <= 0.5]),
    le02vol=agg([x for x in off if x["off"] <= 0.2]),
    share_gt05=round(sum(1 for x in off if x["off"] > 0.5) / len(off), 4),
    share_gt10=round(sum(1 for x in off if x["off"] > 1.0) / len(off), 4))

# ══ P1:burst 涨幅/量能 vs break/段级表现 ══
mach_rows = []
for m, ctx, *_ in head_machines:
    mach_rows.append(dict(sym=ctx["sym"], brise=ctx["brise"],
                          burst_rel_v=ctx["burst_rel_v"], outcome=m["outcome"],
                          n_seg=len(m["segs"]))
    )
br = [x["brise"] for x in mach_rows if x["brise"] > 0]
q25, q50, q75 = (float(np.percentile(br, p)) for p in (25, 50, 75))


def br_bucket(x):
    if x <= q25:
        return "Q1"
    if x <= q50:
        return "Q2"
    if x <= q75:
        return "Q3"
    return "Q4"


p1 = {}
for bucket in ("Q1", "Q2", "Q3", "Q4"):
    sub = [x for x in mach_rows if x["brise"] > 0 and br_bucket(x["brise"]) == bucket]
    p1[bucket] = dict(n=len(sub),
                      brise_med=round(float(np.median([x["brise"] for x in sub])), 4),
                      break_rate=round(sum(1 for x in sub if x["outcome"] == "break") / len(sub), 3) if sub else None)
rv = [x["burst_rel_v"] for x in mach_rows if x["burst_rel_v"]]
if rv:
    r25, r50, r75 = (float(np.percentile(rv, p)) for p in (25, 50, 75))

    def rv_bucket(x):
        if x <= r25:
            return "Q1"
        if x <= r50:
            return "Q2"
        if x <= r75:
            return "Q3"
        return "Q4"
    for bucket in ("Q1", "Q2", "Q3", "Q4"):
        sub = [x for x in mach_rows if x["burst_rel_v"] is not None
               and rv_bucket(x["burst_rel_v"]) == bucket]
        p1[f"relvol_{bucket}"] = dict(
            n=len(sub),
            break_rate=round(sum(1 for x in sub if x["outcome"] == "break") / len(sub), 3) if sub else None)
out["P1_burst"] = p1
brs = np.array([x["brise"] for x in mach_rows])
brk = np.array([1 if x["outcome"] == "break" else 0 for x in mach_rows])
out["P1_burst"]["corr_brise_break_spearman"] = round(float(
    pd.Series(brs).corr(pd.Series(brk), method="spearman")), 4)
if rv:
    rvs = np.array([x["burst_rel_v"] for x in mach_rows if x["burst_rel_v"] is not None])
    brk2 = np.array([brk[i] for i, x in enumerate(mach_rows) if x["burst_rel_v"] is not None])
    out["P1_burst"]["corr_relvol_break_spearman"] = round(float(
        pd.Series(rvs).corr(pd.Series(brk2), method="spearman")), 4)

# ══ P5:微刷新占比(浅回撤机器) ══
micro_all = [m for m, *_ in head_machines]
tot_micro = sum(m["ev"]["micro"][0] for m in micro_all)
tot_refresh = sum(m["ev"]["micro"][1] for m in micro_all)
out["P5_micro"] = dict(
    total_refresh=tot_refresh,
    micro_lt03vol_share=round(tot_micro / tot_refresh, 4) if tot_refresh else None)
# 机器级浅回撤(dd 定义:机器内最深一轮 dd<0.2)→ 单独占比
# (用首段前 max_dd 更贴任务3口径,但此处用事件级即可)

# ══ architect B 方案(θ 三档)+ F 方案 ══
head_enters = {(ctx["sym"], x["i"]) for m, ctx, *_ in head_machines
               for x in m["ev"]["enter"]}
bf = {}
for label_mode, theta in (("B_0.1", 0.1), ("B_0.2", 0.2), ("B_0.3", 0.3), ("F", None)):
    new_recs, all_recs, widths = [], [], []
    abos_segs = None
    n_ent = 0
    for m, ctx, closes, opens, vol, bo, gbot, brise in head_machines:
        mm = run_machine(closes, opens, vol, bo, gbot, brise,
                         mode=("B" if label_mode.startswith("B") else "F"),
                         theta=theta, volumes=None, bstart=ctx["bstart"], bend=ctx["bend"])
        for s in mm["segs"]:
            widths.append(s[1] - s[0] + 1)
        for x in mm["ev"]["enter"]:
            n_ent += 1
            lab = label_at(ctx["closes"], ctx["hi_a"], ctx["lo_a"], ctx["M"],
                           x["i"], ctx["n"], ctx["lo_i"], ctx["hi_i"])
            if lab:
                rec = dict(sym=ctx["sym"], **x, **lab, date=ctx["dts"][x["i"]],
                           half=half(dict(date=ctx["dts"][x["i"]])))
                all_recs.append(rec)
                if (ctx["sym"], x["i"]) not in head_enters:
                    rec = dict(rec, new=True)
                    new_recs.append(rec)
        if ctx["sym"] == "ABOS" and bo == 257:
            abos_segs = dict(segs=[tuple(s) for s in mm["segs"]],
                             enters=[x["i"] for x in mm["ev"]["enter"]])
    dedup_all = {(r["sym"], r["i"]): r for r in all_recs}
    dedup_new = {(r["sym"], r["i"]): r for r in new_recs}
    all_list = list(dedup_all.values())
    new_list = list(dedup_new.values())
    bf[label_mode] = dict(
        n_enter_raw=n_ent, n_enter_dedup=len(all_list),
        n_new_dedup=len(new_list),
        width_med=round(float(np.median(widths)), 2) if widths else None,
        width_pct={p: round(float(np.percentile(widths, p)), 1) for p in (25, 50, 75, 90)} if widths else None,
        all=agg(all_list), new_only=agg(new_list),
        new_shallow=agg([x for x in new_list if x["dd"] is not None and x["dd"] < 0.2]),
        new_deep=agg([x for x in new_list if x["dd"] is not None and x["dd"] >= 0.2]),
        abos=abos_segs)
out["architect_BF"] = bf

# head 段宽(对照)
head_widths = [s[1] - s[0] + 1 for m, *_ in head_machines for s in m["segs"]]
out["architect_BF"]["head_width_pct"] = {p: round(float(np.percentile(head_widths, p)), 1)
                                         for p in (25, 50, 75, 90)}

# ══ E2:重叠日比例 ══
out["E2_overlap"] = dict(
    enter_raw=1935, enter_dedup=len(e_recs),
    overlap_rec_share=round(1 - len(e_recs) / 1935, 4),
    vbounce_raw=sum(len(lst) for lst in v_recs.values()), vbounce_dedup=len(v_recs))

path = REPO / "docs/research/2026-08-17_tb-v4-buypoint-timing/repro/stats_part3.json"
with open(path, "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
