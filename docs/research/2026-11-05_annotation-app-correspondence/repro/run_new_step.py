"""临时:在标注过的几张图上跑 new_step,打印 burst / tb_seg / hit 的跨度,和用户框对比。只读。"""
import pandas as pd
from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars, slice_window
from path2_web.annotation.store import read_annotations
from path2_apps.new_step import dag_spec as app

cfg = load_config()
st = read_annotations(cfg)["state"]
feats = {f["id"]: f["name"] for f in st["features"]}
p = app.load_params()

for c in st["charts"]:
    if not c["samples"]:
        continue
    sym = c["symbol"]
    dates = sorted([b["start"] for b in c["boxes"]] + [s["date"] for s in c["samples"]])
    lo = pd.Timestamp(dates[0]) - pd.Timedelta(days=200)
    hi = pd.Timestamp(max(s["date"] for s in c["samples"])) + pd.Timedelta(days=60)
    win = slice_window(read_bars(view_dataset_dir(cfg), sym), lo.date(), hi.date())
    d = lambda i: str(win["date"].iloc[i].date())
    res = app.analyze(win, p)
    print("##", sym)
    for b in sorted(c["boxes"], key=lambda b: b["start"]):
        print("  BOX", feats.get(b["feature"]), b["start"], "→", b["end"])
    for s in sorted(c["samples"], key=lambda s: s["date"]):
        print("  SAMPLE", s["date"])
    win_lo = pd.Timestamp(dates[0]) - pd.Timedelta(days=30)
    for e in res.events:
        if e.node_id in ("burst",) and win["date"].iloc[e.end_idx] >= win_lo:
            print(f"  burst {d(e.start_idx)}→{d(e.end_idx)} nbo={len(e.members)} distinct_pk={getattr(e,'distinct_pk',None)} vol={getattr(e,'max_bar_vol_ratio',None):.1f}")
    for h in res.hits:
        tb = h.node_index["tb"]
        segs = [(d(s.start_idx), d(s.end_idx), s.outcome) for s in tb.segments]
        print(f"  HIT {d(h.start_idx)}→{d(h.end_idx)} burst={d(h.node_index['burst'].start_idx)}→{d(h.node_index['burst'].end_idx)} segs={segs}")
