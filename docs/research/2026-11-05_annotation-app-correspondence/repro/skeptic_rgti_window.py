"""skeptic 临时脚本:同一只 RGTI,全段跑与「框起点往前 200 天」截窗跑,burst 属性与 hit 是否一样。"""
import pandas as pd
from common import load_win, i2d
from path2_apps.new_step import dag_spec as app
p = app.load_params()
full = load_win("RGTI")
for name, w in [("full", full), ("cut200", full[full["date"] >= pd.Timestamp("2024-11-05") - pd.Timedelta(days=200)].reset_index(drop=True))]:
    res = app.analyze(w, p)
    print("==", name, "bars", len(w))
    for e in res.events:
        if e.node_id == "burst" and "2024-10-01" <= i2d(w, e.start_idx) <= "2024-12-31":
            print("  burst", i2d(w, e.start_idx), i2d(w, e.end_idx), "distinct_pk", e.distinct_pk, "vol", round(e.max_bar_vol_ratio, 1))
    for h in res.hits:
        if "2024-10-01" <= i2d(w, h.start_idx) <= "2024-12-31":
            tb = h.node_index["tb"]
            print("  HIT", i2d(w, h.start_idx), i2d(w, h.end_idx), [(i2d(w, s.start_idx), i2d(w, s.end_idx), s.outcome) for s in tb.segments])
