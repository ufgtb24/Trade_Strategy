"""补丁统计:B2 去重修正后的 task2 + AND 版(工作树)对比 + V→下一段延迟 + 随机基线。

复用 full_stats.py 的重放框架;task1/3/4 不受去重影响(机器级/事件级口径),
只有 task2 的逐根统计必须按 (symbol, 行号) 去重。
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


def run_machine(closes, opens, vol, bo, gbot, brise, max_rise_k, stable_or):
    n = len(closes)
    end = min(bo + MAX_SPAN, n - 1)
    state, peak, trough, cnt, enter = "UP", float(closes[bo]), float("inf"), 0, -1
    g = float(gbot)
    segs, ev = [], {"vbounce": [], "enter": []}
    for i in range(bo + 1, end + 1):
        c = float(closes[i])
        if c < g:
            if state == "STABLE":
                segs.append((enter, i - 1, "break"))
            return dict(segs=tuple(segs), ev=ev)
        if state == "UP":
            if c > peak:
                peak = c
            if (c < float(opens[i])) or c < float(closes[i - 1]):
                state, trough, cnt = "DOWN", c, 0
        elif state == "DOWN":
            v = vol[i]
            if c < trough:
                trough, cnt = c, 0
            elif v == v and c > trough + max_rise_k * v:
                state = "UP"
                ev["vbounce"].append((i, (peak - trough) / brise if brise > 0 else None))
            else:
                cnt += 1
                if cnt >= STOP_K:
                    state, enter = "STABLE", i
                    ev["enter"].append((i, (peak - trough) / brise if brise > 0 else None))
        else:
            v = vol[i]
            rise_arm = v == v and c > trough + max_rise_k * v
            if (rise_arm or c > peak) if stable_or else (rise_arm and c > peak):
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
    return dict(segs=tuple(segs), ev=ev)


v_recs, e_recs = {}, {}          # (symbol,i) -> rec(同键覆盖,信息相同)
machines = []
and_enter_dedup = set()
and_first_eps = []
v_to_next_enter = []             # (symbol, V根i, 下一 enter 根 i' 或 None, 延迟)
rand_cnt = {"up": 0, "down": 0, "both": 0, "none": 0}
rand_n = 0
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

    def label_of(t):
        if not (lo_i <= t <= hi_i and t + HORIZON < n):
            return None
        return dict(ep=closes[t + HORIZON] / closes[t] - 1.0,
                    mfr=float(hi_a[t + 1:t + HORIZON + 1].max()) / closes[t] - 1.0,
                    mfd=float(lo_a[t + 1:t + HORIZON + 1].min()) / closes[t] - 1.0,
                    fp=_first_passage_at(hi_a, lo_a, closes, M, t, HORIZON, FP_K))

    if r.get("random_first_passage"):
        rc = r["random_first_passage"]
        rand_n += rc["n_sampled"]
        for k in rand_cnt:
            rand_cnt[k] += rc["counts"][k]

    for b in bursts:
        bo = bo_end[b["child_refs"]["members"][-1]]
        gbot = float(closes[b["start_idx"]:b["end_idx"] + 1].min())
        brise = float(closes[b["end_idx"]] - closes[b["start_idx"]])
        m = run_machine(closes, opens, vol, bo, gbot, brise, 1.5, stable_or=True)
        machines.append((sym, closes, opens, vol, bo, gbot, brise, m))
        for (i, dd) in m["ev"]["vbounce"]:
            lab = label_of(i)
            v_recs[(sym, i)] = dict(i=i, dd=dd, **(lab or {}), has_label=lab is not None)
        enters = m["ev"]["enter"]
        for (i, dd) in enters:
            lab = label_of(i)
            e_recs[(sym, i)] = dict(i=i, dd=dd, **(lab or {}), has_label=lab is not None)
        for (vi, _) in m["ev"]["vbounce"]:
            nxt = next((ei for (ei, _) in enters if ei > vi), None)
            v_to_next_enter.append((sym, vi, nxt, (nxt - vi) if nxt is not None else None))
        # AND 版(工作树口径)
        ma = run_machine(closes, opens, vol, bo, gbot, brise, 1.5, stable_or=False)
        for (i, _) in ma["ev"]["enter"]:
            and_enter_dedup.add((sym, i))
        if ma["ev"]["enter"]:
            lab = label_of(ma["ev"]["enter"][0][0])
            if lab:
                and_first_eps.append(lab["ep"])

roles = {}
for k in v_recs:
    roles[k] = roles.get(k, set()) | {"V"}
for k in e_recs:
    roles[k] = roles.get(k, set()) | {"E"}


def group(recs, role):
    rows = [rec for k, rec in recs.items()
            if roles[k] == {role} and rec["has_label"]]
    def agg(sub):
        if not sub:
            return None
        eps = [x["ep"] for x in sub]
        fps = [x["fp"] for x in sub if x["fp"]]
        cnt = {s: sum(1 for f in fps if f == s) for s in ("up", "down", "both", "none")}
        den = sum(cnt.values())
        return dict(n=len(sub), ep_med=round(float(np.median(eps)), 4),
                    mfr_med=round(float(np.median([x["mfr"] for x in sub])), 4),
                    mfd_med=round(float(np.median([x["mfd"] for x in sub])), 4),
                    fp_up=round(cnt["up"] / den, 3) if den else None,
                    fp_down=round(cnt["down"] / den, 3) if den else None,
                    fp_none=round(cnt["none"] / den, 3) if den else None)
    return dict(all=agg(rows),
                shallow_dd_lt02=agg([x for x in rows if x["dd"] is not None and x["dd"] < 0.2]),
                deep_dd_ge02=agg([x for x in rows if x["dd"] is not None and x["dd"] >= 0.2]))


out = {
    "dedup_n": {"V": len(v_recs), "E": len(e_recs),
                "both": sum(1 for v in roles.values() if v == {"V", "E"}),
                "V_with_label": sum(1 for x in v_recs.values() if x["has_label"]),
                "E_with_label": sum(1 for x in e_recs.values() if x["has_label"])},
    "task2_dedup": {"vbounce": group(v_recs, "V"), "enter": group(e_recs, "E")},
    "random_baseline": {"n": rand_n,
                        "fp_up": round(rand_cnt["up"] / rand_n, 3) if rand_n else None,
                        "fp_down": round(rand_cnt["down"] / rand_n, 3) if rand_n else None,
                        "fp_none": round(rand_cnt["none"] / rand_n, 3) if rand_n else None},
    "v_to_next_enter": {
        "n_v": len(v_to_next_enter),
        "never_pct": round(sum(1 for x in v_to_next_enter if x[3] is None)
                           / len(v_to_next_enter), 4) if v_to_next_enter else None,
        "delay_med": round(float(np.median([x[3] for x in v_to_next_enter
                                            if x[3] is not None])), 2)
        if any(x[3] is not None for x in v_to_next_enter) else None,
        "delay_pct": {p: round(float(np.percentile([x[3] for x in v_to_next_enter
                                                   if x[3] is not None], p)), 1)
                      for p in (25, 50, 75, 90)}
        if any(x[3] is not None for x in v_to_next_enter) else None},
    "and_version": {
        "enter_dedup": len(and_enter_dedup),
        "first_ep_med": round(float(np.median(and_first_eps)), 4) if and_first_eps else None,
        "first_n": len(and_first_eps)},
}

path = REPO / "docs/research/2026-08-17_tb-v4-buypoint-timing/repro/stats_part2.json"
with open(path, "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
