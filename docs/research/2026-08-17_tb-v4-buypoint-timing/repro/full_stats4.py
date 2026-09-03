"""补口:P3 vol分母1.5σ / B方案丢失旧根质量 / P2三桶双窗。复用 part3 的数据结构。"""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
import numpy as np, pandas as pd
from path2.calc.atr import calculate_tr_median, rolling_atr_pct_nanmedian
from path2.eval import _first_passage_at
from path2_web.data import slice_window
sys.path.insert(0, str(REPO / "docs/research/2026-08-17_tb-v4-buypoint-timing/repro"))
from full_stats3 import run_machine, label_at, HORIZON, FP_K, START_TS, END_TS, WIN_START, WIN_END, VOL_W

SCAN = json.load(open(REPO / "outputs/path2_web/scans/20260817T142145.json"))
head_enters, head_v = set(), []
mach = []
for r in SCAN["results"]:
    sym = r["symbol"]
    events = r["per_pattern"]["bottom_burst"]["analysis"]["events"]
    bo_end = {e["instance_id"]: e["end_idx"] for e in events if e["node_id"] == "bo"}
    df = pd.read_pickle(REPO / f"datasets/pkls/{sym}.pkl")
    win = slice_window(df, WIN_START, WIN_END).reset_index(drop=True)
    closes = win["close"].to_numpy(float); opens = win["open"].to_numpy(float)
    vol = calculate_tr_median(win["high"], win["low"], win["close"], VOL_W).to_numpy(float)
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).to_numpy(float)
    hi_a, lo_a = win["high"].to_numpy(float), win["low"].to_numpy(float)
    lo_i = int(win["date"].searchsorted(START_TS, "left")); hi_i = int(win["date"].searchsorted(END_TS, "right")) - 1
    n = len(win); dts = [str(d)[:10] for d in win["date"]]
    L = lambda t: label_at(closes, hi_a, lo_a, M, t, n, lo_i, hi_i)
    for b in [e for e in events if e["node_id"] == "burst"]:
        bo = bo_end[b["child_refs"]["members"][-1]]
        gbot = float(closes[b["start_idx"]:b["end_idx"] + 1].min())
        brise = float(closes[b["end_idx"]] - closes[b["start_idx"]])
        ctx = dict(sym=sym, dts=dts)
        m = run_machine(closes, opens, vol, bo, gbot, brise)
        mach.append((m, ctx, closes, opens, vol, bo, gbot, brise, L, dts))
        for x in m["ev"]["enter"]:
            head_enters.add((sym, x["i"]))
            lab = L(x["i"])
            if lab: head_v.append(dict(**x, **lab, date=dts[x["i"]],
                                       half="H1" if dts[x["i"]] < "2025-07-01" else "H2"))

def agg(recs):
    if not recs: return None
    o = dict(n=len(recs))
    for k in ("ep","mfr","mfd"):
        v=[x[k] for x in recs if x.get(k) is not None]
        if v: o[f"{k}_med"]=round(float(np.median(v)),4)
    fps=[x["fp"] for x in recs if x.get("fp")]; den=len(fps)
    if den:
        o["fp_up"]=round(sum(1 for f in fps if f=="up")/den,3)
        o["fp_down"]=round(sum(1 for f in fps if f=="down")/den,3)
    return o

out={}
# P3 vol 分母 1.5σ(V 根)
vrecs=[x for m,ctx,*_ in mach for x in m["ev"]["vbounce"]]
vr=[]
for x in vrecs:
    pass
# 需 label:重走一遍(带 ctx)
vr=[]
for m, ctx, closes, opens, vol, bo, gbot, brise, L, dts in mach:
    for x in m["ev"]["vbounce"]:
        lab=L(x["i"])
        if lab: vr.append(dict(**x, **lab))
out["P3_vroot_vol15"]=dict(
    shallow15=agg([x for x in vr if x["dd_v"] is not None and x["dd_v"]<1.5]),
    deep15=agg([x for x in vr if x["dd_v"] is not None and x["dd_v"]>=1.5]))
# P2 三桶双窗
sel=lambda lo,hi:[x for x in head_v if x["dd"] is not None and lo<=x["dd"]<hi]
out["P2_dualwin"]=dict(
    lt02_H1=agg([x for x in sel(0,0.2) if x["half"]=="H1"]), lt02_H2=agg([x for x in sel(0,0.2) if x["half"]=="H2"]),
    mid_H1=agg([x for x in sel(0.2,0.5) if x["half"]=="H1"]), mid_H2=agg([x for x in sel(0.2,0.5) if x["half"]=="H2"]),
    ge05_H1=agg([x for x in head_v if x["dd"] is not None and x["dd"]>=0.5 and x["half"]=="H1"]),
    ge05_H2=agg([x for x in head_v if x["dd"] is not None and x["dd"]>=0.5 and x["half"]=="H2"]))
# B 方案丢失旧根
for theta in (0.1,0.2,0.3):
    ent=set()
    for m, ctx, closes, opens, vol, bo, gbot, brise, L, dts in mach:
        mm=run_machine(closes,opens,vol,bo,gbot,brise,mode="B",theta=theta)
        for x in mm["ev"]["enter"]: ent.add((ctx["sym"],x["i"]))
    lost=[(s,i) for (s,i) in head_enters if (s,i) not in ent]
    out[f"B_lost_theta{theta}"]=dict(n=len(lost))
p=REPO/"docs/research/2026-08-17_tb-v4-buypoint-timing/repro/stats_part4.json"
json.dump(out,open(p,"w"),ensure_ascii=False,indent=1,default=str)
print(json.dumps(out,ensure_ascii=False,indent=1,default=str))
