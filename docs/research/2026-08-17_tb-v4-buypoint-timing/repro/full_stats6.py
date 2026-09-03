"""第三批:F/B 三口径(E4 升级)+ G2 派发子集 + P4 双尺度 + P6 损耗结构。

E4 三口径(锁定):fr_max(mfr)/fr_close(ep)median+q10/首穿率。
全部循环内算 label(无闭包晚绑定),OR(HEAD)版手写复刻。输出 stats_part6.json。
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


def run_machine(closes, opens, highs, vol, bo, gbot, brise, gain_bo,
                *, mode="head", theta=None, theta_v=None):
    """OR(HEAD) 复刻。mode: head / B(浅快通 θ·gain_bo 或 θ_v·vol)/ F。
    enter 记录 off_v=(c-trough)/vol、off_g=(c-trough)/gain_bo。"""
    n = len(closes)
    end = min(bo + MAX_SPAN, n - 1)
    state, peak, trough, cnt, enter = "UP", float(closes[bo]), float("inf"), 0, -1
    g = float(gbot)
    segs, ev = [], {"vbounce": [], "enter": []}
    bo_close, bo_high = float(closes[bo]), float(highs[bo])
    for i in range(bo + 1, end + 1):
        c = float(closes[i])
        v = vol[i]
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
            dd_g = (peak - trough) / gain_bo if gain_bo and gain_bo > 0 else None
            dd_v = (peak - trough) / v if v == v and v > 0 else None
            fast = False
            if mode == "B":
                if theta is not None and dd_g is not None and dd_g < theta:
                    fast = True
                if theta_v is not None and dd_v is not None and dd_v < theta_v:
                    fast = True
            if c < trough:
                trough, cnt = c, 0
            elif v == v and c > trough + 1.5 * v:
                if fast:
                    state, enter = "STABLE", i
                    ev["enter"].append(dict(
                        i=i, dd=dd_g, off_v=(c - trough) / v if v else None,
                        off_g=(c - trough) / gain_bo if gain_bo else None,
                        new=True, dist_before=(float(highs[bo + 1:i + 1].max()) if i > bo else bo_high) <= bo_high and c < bo_close))
                else:
                    state = "UP"
                    ev["vbounce"].append(i)
            else:
                cnt += 1
                if cnt >= STOP_K:
                    state, enter = "STABLE", i
                    ev["enter"].append(dict(
                        i=i, dd=dd_g, off_v=(c - trough) / v if v else None,
                        off_g=(c - trough) / gain_bo if gain_bo else None,
                        new=(mode == "B"),
                        dist_before=(float(highs[bo + 1:i + 1].max()) if i > bo else bo_high) <= bo_high and c < bo_close))
        else:
            if c < trough:
                segs.append((enter, i - 1, "weak"))
                state, trough, cnt = "DOWN", c, 0
            elif mode == "F":
                if (c < float(opens[i])) or c < float(closes[i - 1]):
                    segs.append((enter, i - 1, "rise"))
                    g = trough
                    state, trough, cnt = "DOWN", c, 0
            else:
                if (v == v and c > trough + 1.5 * v) or (c > peak):
                    segs.append((enter, i - 1, "rise"))
                    g = trough
                    state = "UP"
                    if c > peak:
                        peak = c
    if state == "STABLE":
        segs.append((enter, end, "timeout"))
    return dict(segs=tuple(segs), ev=ev)


def agg(recs):
    """E4 三口径:fr_max median + fr_close median/q10 + 首穿率。"""
    if not recs:
        return None
    o = dict(n=len(recs))
    for k in ("ep", "mfr", "mfd"):
        vals = [x[k] for x in recs if x.get(k) is not None]
        if vals:
            o[f"{k}_med"] = round(float(np.median(vals)), 4)
            o[f"{k}_q10"] = round(float(np.percentile(vals, 10)), 4)
    fps = [x["fp"] for x in recs if x.get("fp")]
    den = len(fps)
    if den:
        for s in ("up", "down", "none"):
            o[f"fp_{s}"] = round(sum(1 for f in fps if f == s) / den, 3)
    return o


# ── 主循环:每股跑 6 变体,循环内算 label ──
head_enter, variants = [], {k: [] for k in ("B_0.1", "B_0.2", "B_0.3", "Bv_1.5", "F")}
head_enters_raw = set()
p6 = []          # (sym, first_v, first_enter)
p6_noseg = []    # 0 段机器:(有V吗, 有enter吗)
p4_rows = []     # enter 根双尺度 + label + gain_bo
for r in SCAN["results"]:
    sym = r["symbol"]
    events = r["per_pattern"]["bottom_burst"]["analysis"]["events"]
    bo_end = {e["instance_id"]: e["end_idx"] for e in events if e["node_id"] == "bo"}
    df = pd.read_pickle(REPO / f"datasets/pkls/{sym}.pkl")
    win = slice_window(df, WIN_START, WIN_END).reset_index(drop=True)
    closes = win["close"].to_numpy(float)
    opens = win["open"].to_numpy(float)
    highs = win["high"].to_numpy(float)
    vol = calculate_tr_median(win["high"], win["low"], win["close"], VOL_W).to_numpy(float)
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).to_numpy(float)
    hi_a, lo_a = win["high"].to_numpy(float), win["low"].to_numpy(float)
    lo_i = int(win["date"].searchsorted(START_TS, "left"))
    hi_i = int(win["date"].searchsorted(END_TS, "right")) - 1
    n = len(win)

    def L(t):
        if not (lo_i <= t <= hi_i and t + HORIZON < n):
            return None
        return dict(ep=closes[t + HORIZON] / closes[t] - 1.0,
                    mfr=float(hi_a[t + 1:t + HORIZON + 1].max()) / closes[t] - 1.0,
                    mfd=float(lo_a[t + 1:t + HORIZON + 1].min()) / closes[t] - 1.0,
                    fp=_first_passage_at(hi_a, lo_a, closes, M, t, HORIZON, FP_K))

    for b in [e for e in events if e["node_id"] == "burst"]:
        bo = bo_end[b["child_refs"]["members"][-1]]
        bstart, bend = b["start_idx"], b["end_idx"]
        gbot = float(closes[bstart:bend + 1].min())
        brise = float(closes[bend] - closes[bstart])
        gain_bo = float(closes[bo] - closes[bstart - 1]) if bstart >= 1 else None
        if gain_bo is not None and gain_bo <= 0:
            gain_bo = None
        base = dict(closes=closes, opens=opens, highs=highs, vol=vol, bo=bo,
                    gbot=gbot, brise=brise, gain_bo=gain_bo)
        # head
        m = run_machine(**base)
        firsts_v = [i for i in m["ev"]["vbounce"]]
        firsts_e = [x["i"] for x in m["ev"]["enter"]]
        p6.append(dict(sym=sym,
                       first_v=min(firsts_v) if firsts_v else None,
                       first_enter=min(firsts_e) if firsts_e else None))
        if not m["segs"]:
            p6_noseg.append(dict(sym=sym, has_v=bool(firsts_v)))
        for x in m["ev"]["enter"]:
            head_enters_raw.add((sym, x["i"]))
            lab = L(x["i"])
            if lab:
                head_enter.append(dict(sym=sym, **x, **lab, gain_bo=gain_bo))
        # 变体
        for name, kw in (("B_0.1", dict(mode="B", theta=0.1)),
                         ("B_0.2", dict(mode="B", theta=0.2)),
                         ("B_0.3", dict(mode="B", theta=0.3)),
                         ("Bv_1.5", dict(mode="B", theta_v=1.5)),
                         ("F", dict(mode="F"))):
            mm = run_machine(**base, **kw)
            for x in mm["ev"]["enter"]:
                lab = L(x["i"])
                if lab:
                    variants[name].append(dict(sym=sym, **x, **lab, gain_bo=gain_bo))

# dedup(按 (sym,i),保留首个)
def dedup(recs):
    d = {}
    for x in recs:
        d.setdefault((x["sym"], x["i"]), x)
    return list(d.values())


head_dedup = dedup(head_enter)
head_keys = {(x["sym"], x["i"]) for x in head_dedup}
out = {}

# ══ 1. F 三口径(最优先)══
f_all = dedup(variants["F"])
f_new = [x for x in f_all if (x["sym"], x["i"]) not in head_keys]
out["F_triple"] = dict(pool=agg(f_all), new_only=agg(f_new),
                       head_pool=agg(head_dedup))
out["F_triple"]["note"] = "new_only=F 版买点中现行版没有的(段内反弹根)"

# ══ 2. B 三档 + per-σ 变体三口径 + G2 派发子集 ══
b_out = {}
for name in ("B_0.1", "B_0.2", "B_0.3", "Bv_1.5"):
    allr = dedup(variants[name])
    newr = [x for x in allr if (x["sym"], x["i"]) not in head_keys]
    dist = [x for x in newr if x.get("dist_before")]      # 慢性派发型(G2)
    strong = [x for x in newr if not x.get("dist_before")]
    b_out[name] = dict(new_only=agg(newr),
                       g2_dist_before=agg(dist), g2_strong=agg(strong),
                       n_dist=len(dist), n_strong=len(strong))
out["B_triple"] = b_out

# ══ 3. P4 双尺度 ══
rows = [x for x in head_dedup if x.get("off_g") is not None and x.get("mfd") is not None]
ov = [x for x in rows if x.get("off_v") is not None]
sp = lambda a, b: float(pd.Series(a).corr(pd.Series(b), method="spearman"))
out["P4_dual"] = dict(
    n=len(rows),
    spearman_offv_mfd=round(sp([x["off_v"] for x in ov], [x["mfd"] for x in ov]), 4),
    spearman_offv_ep=round(sp([x["off_v"] for x in ov], [x["ep"] for x in ov]), 4),
    spearman_offg_mfd=round(sp([x["off_g"] for x in rows], [x["mfd"] for x in rows]), 4),
    spearman_offg_ep=round(sp([x["off_g"] for x in rows], [x["ep"] for x in rows]), 4),
    offg_buckets={
        "lt0.1": agg([x for x in rows if x["off_g"] < 0.1]),
        "0.1-0.2": agg([x for x in rows if 0.1 <= x["off_g"] < 0.2]),
        "ge0.2": agg([x for x in rows if x["off_g"] >= 0.2])},
    offv_buckets={
        "lt0.5": agg([x for x in ov if x["off_v"] < 0.5]),
        "ge0.5": agg([x for x in ov if x["off_v"] >= 0.5])},
)
# 跨股稳健性:按 gain_bo 四分位分层,各层内 off_g 与 mfd 的 Spearman
gq = [x["gain_bo"] for x in rows if x["gain_bo"]]
q1, q2, q3 = (float(np.percentile(gq, p)) for p in (25, 50, 75))


def g_bucket(x):
    if x <= q1:
        return "Q1"
    if x <= q2:
        return "Q2"
    if x <= q3:
        return "Q3"
    return "Q4"


rob = {}
for bk in ("Q1", "Q2", "Q3", "Q4"):
    sub = [x for x in rows if g_bucket(x["gain_bo"]) == bk]
    rob[bk] = dict(n=len(sub),
                   gain_bo_med=round(float(np.median([x["gain_bo"] for x in sub])), 3),
                   offg_med=round(float(np.median([x["off_g"] for x in sub])), 4),
                   spearman_offg_mfd=round(sp([x["off_g"] for x in sub],
                                              [x["mfd"] for x in sub]), 4) if len(sub) > 10 else None,
                   spearman_offv_mfd=round(sp([x["off_v"] for x in sub],
                                              [x["mfd"] for x in sub]), 4) if len(sub) > 10 else None)
out["P4_dual"]["robust_by_gainq"] = rob
out["P4_dual"]["note"] = "off_g=(close_enter-trough)/gain_bo, gain_bo=burst前夜close→bo根close(ABOS=0.44 口径)"

# ══ 4. P6 损耗结构 ══
deltas = [p["first_enter"] - p["first_v"] for p in p6
          if p["first_v"] is not None and p["first_enter"] is not None
          and p["first_v"] < p["first_enter"]]
v_after_e = sum(1 for p in p6 if p["first_v"] is not None and p["first_enter"] is not None
                and p["first_v"] > p["first_enter"])
out["P6"] = dict(
    n_machines=len(p6),
    n_with_both_v_e=sum(1 for p in p6 if p["first_v"] is not None and p["first_enter"] is not None),
    firstV_before_firstE_n=len(deltas),
    firstV_after_firstE_n=v_after_e,
    delta_pct={p: round(float(np.percentile(deltas, p)), 1) for p in (10, 25, 50, 75, 90)},
    delta_med=float(np.median(deltas)),
    zero_seg_machines=len(p6_noseg),
    zero_seg_with_v=sum(1 for x in p6_noseg if x["has_v"]),
)
p = REPO / "docs/research/2026-08-17_tb-v4-buypoint-timing/repro/stats_part6.json"
json.dump(out, open(p, "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
