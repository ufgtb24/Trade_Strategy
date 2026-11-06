"""compare-ui 临时脚本:对比两种「认出」判法在「站上新平台」框上的结论与碰巧率。
R1 = spec 6.2 现行:交叠,且事件起点或终点(一端就够)落在 [框起-TOL, 框止+TOL];
R2 = 终点覆盖:事件跨度盖住框的终点(放宽 TOL 根),即 es <= 框止+TOL 且 ee >= 框止-TOL,起点不看。
碰巧率:同宽框随机挪 40 次(种子=框起点序号,与 skeptic_chance_overlap.py 相同),被判认出的比例。只读。
"""
import random
import numpy as np
import pandas as pd
from common import load_state, load_win, d2i
from path2_apps.new_step import dag_spec as app

TOL = 2
st, fname = load_state()
p = app.load_params()
rows = []
for c in st["charts"]:
    boxes = [b for b in c["boxes"] if fname.get(b["feature"]) == "站上新平台"]
    if not boxes:
        continue
    win = load_win(c["symbol"])
    res = app.analyze(win, p)
    bursts = [e for e in res.events if e.node_id == "burst"]
    det = sorted({(e.start_idx, e.end_idx) for e in bursts})
    qual = sorted({(e.start_idx, e.end_idx) for e in bursts
                   if getattr(e, "distinct_pk", 0) >= p.burst.distinct_pk_min
                   and getattr(e, "max_bar_vol_ratio", 0) >= p.burst.vol_spike_min})
    n = len(win)
    head = app.eval_meta(p)["head_buffer_trading_days"]

    def r1(s, e, evs):
        return any(not (ee < s or es > e) and (s - TOL <= es <= e + TOL or s - TOL <= ee <= e + TOL) for es, ee in evs)

    def r2(s, e, evs):
        return any(es <= e + TOL and ee >= e - TOL and not (ee < s or es > e) for es, ee in evs)

    for b in boxes:
        s, e = d2i(win, b["start"]), d2i(win, b["end"])
        L = e - s + 1
        rng = random.Random(s)
        pos = [rng.randint(head, n - L) for _ in range(40)]
        near = min((abs(e - ee) for es, ee in det if not (ee < s or es > e)), default=None)
        rows.append(dict(sym=c["symbol"], box=b["id"], L=L, end_gap_to_nearest_burst_end=near,
                         r1_det=r1(s, e, det), r2_det=r2(s, e, det), r2_q=r2(s, e, qual),
                         ch_r1_det=round(np.mean([r1(x, x + L - 1, det) for x in pos]), 2),
                         ch_r2_det=round(np.mean([r2(x, x + L - 1, det) for x in pos]), 2),
                         ch_r2_q=round(np.mean([r2(x, x + L - 1, qual) for x in pos]), 2)))
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df.to_string(index=False))
print("recognized r1_det / r2_det / r2_q:", int(df.r1_det.sum()), int(df.r2_det.sum()), int(df.r2_q.sum()), "of", len(df))
print("median chance r1_det / r2_det / r2_q:", df.ch_r1_det.median(), df.ch_r2_det.median(), df.ch_r2_q.median())
