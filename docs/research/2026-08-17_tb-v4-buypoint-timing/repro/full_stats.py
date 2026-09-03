"""全量统计:214 命中股 × 457 过闸 burst,OR 版机器(scan 20260817T142145 口径)。

burst 事实直接信 scan json(机器输入 = 过闸 burst);TB 状态机本地重放
(OR 版 rise 收段 = HEAD 版即 scan 运行代码;工作树已改 AND,勿混)。

四组统计:
  1. UP→DOWN 触发幅度分布(|Δc|/vol、|Δc|/burst 涨幅、浅震荡占比)
  2. V 反弹根 vs STABLE 入段根的 40 日后续表现(endpoint/mfr/首穿;(symbol,date) 去重;
     浅/深回撤分组)
  3. 浅回撤直接震荡占比(首段 enter 前 max 跌幅/burst 涨幅 < 0.1/0.2/0.3)
  4. max_rise_k 敏感性(DOWN 根 (c-tr)/vol 分布;1.5/1.0/0.8 三档重跑对比)
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
WIN_START = SCAN["scan"]["win_start"]
WIN_END = SCAN["scan"]["win_end"]
START_TS = pd.to_datetime(SCAN["scan"]["start_date"])
END_TS = pd.to_datetime(SCAN["scan"]["end_date"])
HORIZON = SCAN["scan"]["label_horizon"]
FP_K = SCAN["scan"]["first_passage_k"]
STOP_K, MAX_SPAN, VOL_W = 1, 60, 14


def run_machine(closes, opens, vol, bo, gbot, brise, max_rise_k):
    """OR 版(scan 口径)状态机重放:段序列 + 逐根事件记录。"""
    n = len(closes)
    end = min(bo + MAX_SPAN, n - 1)
    state, peak, trough, cnt, enter = "UP", float(closes[bo]), float("inf"), 0, -1
    g = float(gbot)
    segs, ev = [], {"updown": [], "vbounce": [], "enter": [], "down_ratio": [],
                    "first_nonrefresh": []}
    first_enter = None
    run_peak, max_dd = float(closes[bo]), 0.0
    for i in range(bo + 1, end + 1):
        c = float(closes[i])
        if first_enter is None:
            run_peak = max(run_peak, c)
            max_dd = max(max_dd, run_peak - c)
        if c < g:
            if state == "STABLE":
                segs.append((enter, i - 1, "break"))
            return dict(segs=tuple(segs), outcome="break", ev=ev,
                        first_enter=first_enter, max_dd=max_dd)
        if state == "UP":
            if c > peak:
                peak = c
            red = c < float(opens[i])
            if red or c < float(closes[i - 1]):
                dc = c - float(closes[i - 1])
                ev["updown"].append(dict(
                    i=i, dc=dc, arm="yin" if red else "down_close",
                    d_over_v=abs(dc) / vol[i] if vol[i] == vol[i] else None,
                    d_over_burst=abs(dc) / brise if brise > 0 else None))
                state, trough, cnt = "DOWN", c, 0
        elif state == "DOWN":
            v = vol[i]
            r = (c - trough) / v if v == v else None
            if r is not None:
                ev["down_ratio"].append(r)
            if c < trough:
                trough, cnt = c, 0
            elif v == v and c > trough + max_rise_k * v:
                state = "UP"
                ev["vbounce"].append(dict(
                    i=i, ratio=r, dd=(peak - trough) / brise if brise > 0 else None))
            else:
                cnt += 1
                if cnt == 1:
                    ev["first_nonrefresh"].append(
                        dict(i=i, dd=(peak - trough) / brise if brise > 0 else None))
                if cnt >= STOP_K:
                    state, enter = "STABLE", i
                    ev["enter"].append(
                        dict(i=i, dd=(peak - trough) / brise if brise > 0 else None))
                    if first_enter is None:
                        first_enter = i
        else:  # STABLE · OR 版(HEAD/scan 语义)
            v = vol[i]
            if (v == v and c > trough + max_rise_k * v) or (c > peak):
                segs.append((enter, i - 1, "rise"))
                g = trough
                state = "UP"
                if c > peak:
                    peak = c
            elif c < trough:
                segs.append((enter, i - 1, "weak"))
                state, trough, cnt = "DOWN", c, 0
    if state == "STABLE":
        segs.append((enter, end, "timeout"))
    return dict(segs=tuple(segs), outcome="budget", ev=ev,
                first_enter=first_enter, max_dd=max_dd)


# ── 逐股重放 ──
updown_all, vbounce_all, enter_all, down_ratio_all = [], [], [], []
machines = []
seg_check = {"match": 0, "differ": 0}
for r in SCAN["results"]:
    sym = r["symbol"]
    events = r["per_pattern"]["bottom_burst"]["analysis"]["events"]
    bo_end = {e["instance_id"]: e["end_idx"] for e in events if e["node_id"] == "bo"}
    bursts = [e for e in events if e["node_id"] == "burst"]
    df = pd.read_pickle(REPO / f"datasets/pkls/{sym}.pkl")
    win = slice_window(df, WIN_START, WIN_END).reset_index(drop=True)
    closes = win["close"].to_numpy(float)
    opens = win["open"].to_numpy(float)
    vol = calculate_tr_median(win["high"], win["low"], win["close"], VOL_W).to_numpy(float)
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).to_numpy(float)
    hi_a, lo_a = win["high"].to_numpy(float), win["low"].to_numpy(float)
    lo_i = int(win["date"].searchsorted(START_TS, "left"))
    hi_i = int(win["date"].searchsorted(END_TS, "right")) - 1
    n = len(win)

    def label_of(t, _c=closes, _hi=hi_a, _lo=lo_a, _M=M, _n=n, _lo_i=lo_i, _hi_i=hi_i):
        if not (_lo_i <= t <= _hi_i and t + HORIZON < _n):
            return None
        return dict(
            ep=_c[t + HORIZON] / _c[t] - 1.0,
            mfr=float(_hi[t + 1:t + HORIZON + 1].max()) / _c[t] - 1.0,
            mfd=float(_lo[t + 1:t + HORIZON + 1].min()) / _c[t] - 1.0,
            fp=_first_passage_at(_hi, _lo, _c, _M, t, HORIZON, FP_K))

    scan_segs = {}
    for e in events:
        if e["node_id"] == "tb":
            scan_segs[e["anchor_bo_id"]] = tuple(
                (x["start_idx"], x["end_idx"]) for x in events
                if x["node_id"] == "tb_seg" and x["anchor_bo_id"] == e["anchor_bo_id"])
    for b in bursts:
        last_bo_id = b["child_refs"]["members"][-1]
        bo = bo_end[last_bo_id]
        gbot = float(closes[b["start_idx"]:b["end_idx"] + 1].min())
        brise = float(closes[b["end_idx"]] - closes[b["start_idx"]])
        m = run_machine(closes, opens, vol, bo, gbot, brise, max_rise_k=1.5)
        m.update(symbol=sym, bo=bo, brise=brise, label_of=label_of,
                 closes=closes, opens=opens, vol=vol, gbot=gbot)
        machines.append(m)
        if last_bo_id in scan_segs:
            got = tuple((s[0], s[1]) for s in m["segs"])
            (seg_check.__setitem__("match", seg_check["match"] + 1) if got == scan_segs[last_bo_id]
             else seg_check.__setitem__("differ", seg_check["differ"] + 1))
        updown_all += [dict(symbol=sym, **x) for x in m["ev"]["updown"]]
        for x in m["ev"]["vbounce"]:
            lab = label_of(x["i"])
            vbounce_all.append(dict(symbol=sym, i=x["i"], ratio=x["ratio"],
                                    dd=x["dd"], **(lab or {})))
        for x in m["ev"]["enter"]:
            lab = label_of(x["i"])
            enter_all.append(dict(symbol=sym, i=x["i"], dd=x["dd"], **(lab or {})))
        down_ratio_all += m["ev"]["down_ratio"]

per_date = {}
for rec in vbounce_all:
    per_date.setdefault((rec["symbol"], rec["i"]), set()).add("V")
for rec in enter_all:
    per_date.setdefault((rec["symbol"], rec["i"]), set()).add("E")

qs = lambda a, p: float(np.percentile(a, p)) if len(a) else None
out = {"n_machines": len(machines), "seg_check": seg_check,
       "n_updown": len(updown_all), "n_vbounce_raw": len(vbounce_all),
       "n_enter_raw": len(enter_all),
       "n_date_dedup": len(per_date)}

# ── 1. UP→DOWN 触发幅度分布 ──
dv = [x["d_over_v"] for x in updown_all if x["d_over_v"] is not None]
db = [x["d_over_burst"] for x in updown_all if x["d_over_burst"] is not None]
arm_cnt = pd.Series([x["arm"] for x in updown_all]).value_counts().to_dict()
out["task1"] = {
    "arm": arm_cnt,
    "d_over_v_pct": {p: round(qs(dv, p), 3) for p in (10, 25, 50, 75, 90)},
    "d_over_burst_pct": {p: round(qs(db, p), 4) for p in (10, 25, 50, 75, 90)},
    "share_lt_burst_pct": {t: round(sum(1 for x in db if x < t / 100) / len(db), 4)
                           for t in (5, 10, 20, 30)},
    "share_lt_vol": {str(t): round(sum(1 for x in dv if x < t) / len(dv), 4)
                     for t in (0.25, 0.5, 1.0)},
}

# ── 2. V 反弹根 vs 入段根(去重)──
def group_stats(recs, role):
    rows = [rec for rec in recs
            if per_date[(rec["symbol"], rec["i"])] == {role}
            and rec.get("ep") is not None]
    def agg(sub):
        if not sub:
            return None
        eps = [x["ep"] for x in sub]
        fps = [x["fp"] for x in sub if x["fp"]]
        cnt = {s: sum(1 for f in fps if f == s) for s in ("up", "down", "both", "none")}
        den = sum(cnt.values())
        return dict(n=len(sub),
                    ep_med=round(float(np.median(eps)), 4),
                    mfr_med=round(float(np.median([x["mfr"] for x in sub])), 4),
                    mfd_med=round(float(np.median([x["mfd"] for x in sub])), 4),
                    fp_up=round(cnt["up"] / den, 3) if den else None,
                    fp_down=round(cnt["down"] / den, 3) if den else None,
                    fp_none=round(cnt["none"] / den, 3) if den else None)
    return dict(all=agg(rows),
                shallow_dd_lt02=agg([x for x in rows if x.get("dd") is not None and x["dd"] < 0.2]),
                deep_dd_ge02=agg([x for x in rows if x.get("dd") is not None and x["dd"] >= 0.2]),
                dd_missing=sum(1 for x in rows if x.get("dd") is None))

out["task2"] = {"vbounce": group_stats(vbounce_all, "V"),
                "enter": group_stats(enter_all, "E"),
                "n_both_role": sum(1 for v in per_date.values() if v == {"V", "E"})}

# ── 3. 浅回撤直接震荡 ──
task3 = {"n_machines": len(machines),
         "n_brise_nonpos": sum(1 for m in machines if m["brise"] <= 0)}
for t in (0.1, 0.2, 0.3):
    sub = [m for m in machines if m["brise"] > 0 and m["max_dd"] / m["brise"] < t]
    labs = []
    for m in sub:
        fnr = m["ev"]["first_nonrefresh"]
        if fnr:
            lab = m["label_of"](fnr[0]["i"])
            if lab:
                labs.append(lab)
    fps = [x["fp"] for x in labs if x["fp"]]
    den = len(fps)
    task3[f"lt_{t}"] = dict(
        n_mach=len(sub), share=round(len(sub) / len(machines), 4),
        buy_n=len(labs),
        ep_med=round(float(np.median([x["ep"] for x in labs])), 4) if labs else None,
        mfr_med=round(float(np.median([x["mfr"] for x in labs])), 4) if labs else None,
        fp_up=round(sum(1 for f in fps if f == "up") / den, 3) if den else None,
        fp_down=round(sum(1 for f in fps if f == "down") / den, 3) if den else None,
        fp_n=den)
out["task3"] = task3

# ── 4. max_rise_k 敏感性 ──
out["task4"] = {
    "n_down_roots": len(down_ratio_all),
    "ratio_pct": {p: round(qs(down_ratio_all, p), 3) for p in (5, 10, 25, 50, 75, 90)},
    "share_band": {f"({lo},{hi}]": round(
        sum(1 for x in down_ratio_all if lo < x <= hi) / len(down_ratio_all), 4)
        for lo, hi in ((-99, 0.0), (0.0, 0.8), (0.8, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 99.0))},
}
sens = {}
for k2 in (1.5, 1.0, 0.8):
    n_enters = n_vb = n_mach_seg = 0
    first_eps, first_fps = [], []
    dedup_enters = set()
    for m in machines:
        mm = run_machine(m["closes"], m["opens"], m["vol"], m["bo"], m["gbot"],
                         m["brise"], max_rise_k=k2)
        n_enters += len(mm["ev"]["enter"])
        n_vb += len(mm["ev"]["vbounce"])
        if mm["segs"]:
            n_mach_seg += 1
        for x in mm["ev"]["enter"]:
            dedup_enters.add((m["symbol"], x["i"]))
        if mm["first_enter"] is not None:
            lab = m["label_of"](mm["first_enter"])
            if lab:
                first_eps.append(lab["ep"])
                if lab["fp"]:
                    first_fps.append(lab["fp"])
    den = len(first_fps)
    sens[str(k2)] = dict(
        n_enter_roots=n_enters, n_enter_dedup=len(dedup_enters),
        n_vbounce=n_vb, n_mach_with_seg=n_mach_seg,
        first_enter_n=len(first_eps),
        first_ep_med=round(float(np.median(first_eps)), 4) if first_eps else None,
        first_fp_up=round(sum(1 for f in first_fps if f == "up") / den, 3) if den else None,
        first_fp_down=round(sum(1 for f in first_fps if f == "down") / den, 3) if den else None)
out["task4"]["sens"] = sens

path = REPO / "docs/research/2026-08-17_tb-v4-buypoint-timing/repro/stats_part1.json"
with open(path, "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
