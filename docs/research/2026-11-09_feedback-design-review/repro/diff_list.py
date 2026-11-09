"""临时:new_step 标注 vs app 买点逐日对拍,列出差异与卡住的条件。不入库。"""
import json
from path2_web.config import load_config, view_dataset_dir
from path2_web.annotation.store import read_annotations
from path2_web.data import read_bars, slice_window, TRAIN_END
from path2_apps.new_step.dag_spec import build_pattern, load_params
from path2_apps.new_step.plateau import PlateauDetector

params = load_params()
spec = build_pattern(params)
WHERE = dict(next(n for n in spec.nodes if n.node_id == "plateau").where)

def leaves(w, out):
    if not w.children:
        out.append(w)
    for c in w.children:
        leaves(c, out)
    return out

def fails(ev):
    r = {}
    for name, pred in WHERE.items():
        if pred(ev):
            continue
        wit = pred.witness(ev)
        bad = [l for l in leaves(wit, []) if not l.satisfied]
        r[name] = [(l.label, l.measured, l.op, l.threshold) for l in bad]
    return r

cfg = load_config()
st = read_annotations(cfg)["state"]
out = []
for ch in st["charts"]:
    sams = [s for s in ch["samples"] if s.get("pattern") == "new_step"]
    if not sams:
        continue
    win = slice_window(read_bars(view_dataset_dir(cfg), ch["symbol"]), "1900-01-01", TRAIN_END)
    D = [str(x)[:10] for x in win["date"]]
    evs = list(PlateauDetector(**params.plateau_kwargs()).detect(win))
    rows = []
    for ev in evs:
        st_ = ev.child("step"); td = ev.child("today")
        rows.append(dict(t=D[td.start_idx], s=D[st_.start_idx], e=D[st_.end_idx], days=ev.days,
                         fails=fails(ev),
                         f=dict(height=ev.height, old_flat=ev.old_flat_ratio, rise=st_.rise, vs_left=st_.vs_left,
                                vs_right=ev.vs_right, vol=st_.vol_ratio, keep=ev.keep_ratio, calm=ev.calm_ratio,
                                vs_high=ev.vs_high, body=td.body)))
    out.append(dict(symbol=ch["symbol"], samples=[s["date"] for s in sams], boxes=ch["boxes"], rows=rows))
json.dump(out, open("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/bb41a4fd-4350-46f3-b781-d37b145f06a1/scratchpad/diff/rows.json", "w"), ensure_ascii=False, default=float)
for c in out:
    print(c["symbol"], "instances", len(c["rows"]), "buy days", len({r["t"] for r in c["rows"] if not r["fails"]}))
