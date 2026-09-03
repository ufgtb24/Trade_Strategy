"""修 part4 的闭包晚绑定:P3 vol 分母 1.5σ 的 V 根分组(循环内当场算 label)。"""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "docs/research/2026-08-17_tb-v4-buypoint-timing/repro"))
import numpy as np, pandas as pd
from path2.calc.atr import calculate_tr_median, rolling_atr_pct_nanmedian
from path2_web.data import slice_window
from full_stats3 import run_machine, label_at, START_TS, END_TS, WIN_START, WIN_END, VOL_W

SCAN = json.load(open(REPO / "outputs/path2_web/scans/20260817T142145.json"))
vr = []
for r in SCAN["results"]:
    events = r["per_pattern"]["bottom_burst"]["analysis"]["events"]
    bo_end = {e["instance_id"]: e["end_idx"] for e in events if e["node_id"] == "bo"}
    df = pd.read_pickle(REPO / f"datasets/pkls/{r['symbol']}.pkl")
    win = slice_window(df, WIN_START, WIN_END).reset_index(drop=True)
    closes = win["close"].to_numpy(float); opens = win["open"].to_numpy(float)
    vol = calculate_tr_median(win["high"], win["low"], win["close"], VOL_W).to_numpy(float)
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).to_numpy(float)
    hi_a, lo_a = win["high"].to_numpy(float), win["low"].to_numpy(float)
    lo_i = int(win["date"].searchsorted(START_TS, "left")); hi_i = int(win["date"].searchsorted(END_TS, "right")) - 1
    n = len(win)
    for b in [e for e in events if e["node_id"] == "burst"]:
        bo = bo_end[b["child_refs"]["members"][-1]]
        gbot = float(closes[b["start_idx"]:b["end_idx"] + 1].min())
        brise = float(closes[b["end_idx"]] - closes[b["start_idx"]])
        m = run_machine(closes, opens, vol, bo, gbot, brise)
        for x in m["ev"]["vbounce"]:
            lab = label_at(closes, hi_a, lo_a, M, x["i"], n, lo_i, hi_i)   # 循环内当场算
            if lab:
                vr.append(dict(**x, **lab))

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
        o["fp_none"]=round(sum(1 for f in fps if f=="none")/den,3)
    return o

out = dict(
    n_vroot_with_label=len(vr),
    shallow15=agg([x for x in vr if x["dd_v"] is not None and x["dd_v"] < 1.5]),
    deep15=agg([x for x in vr if x["dd_v"] is not None and x["dd_v"] >= 1.5]))
p = REPO / "docs/research/2026-08-17_tb-v4-buypoint-timing/repro/stats_part5.json"
json.dump(out, open(p, "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
