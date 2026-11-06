"""skeptic 临时脚本:长框的「认出」有多少是碰巧。

对每个「站上新平台」框,按 spec 6.2 的认出判法(交叠,且 event 起点或终点落在 [框起-2, 框止+2])
看真框认没认出阶跃(burst),再把同宽的框随机挪 40 次(种子=框起点序号),数被判认出的比例。
burst 分两档:detected(全部检测出来的)、qualified(过了 new_step 两条 where)。
另报框的三段构成:框起→阶跃首根(旧平台那截)、阶跃、阶跃末根→框止(新平台那截),以及框止与样本日的关系。
"""
import random
import numpy as np
import pandas as pd
from common import load_state, load_win, d2i, i2d
from path2_apps.new_step import dag_spec as app

TOL = 2
st, fname = load_state()
p = app.load_params()
rows = []
for c in st["charts"]:
    sym = c["symbol"]
    boxes = [b for b in c["boxes"] if fname.get(b["feature"]) == "站上新平台"]
    if not boxes:
        continue
    win = load_win(sym)
    res = app.analyze(win, p)
    bursts = [e for e in res.events if e.node_id == "burst"]
    det = sorted({(e.start_idx, e.end_idx) for e in bursts})
    qual = sorted({(e.start_idx, e.end_idx) for e in bursts
                   if getattr(e, "distinct_pk", 0) >= p.burst.distinct_pk_min
                   and getattr(e, "max_bar_vol_ratio", 0) >= p.burst.vol_spike_min})
    sdates = sorted(s["date"] for s in c["samples"])
    n = len(win)
    head = app.eval_meta(p)["head_buffer_trading_days"]

    def rec(s, e, evs):
        return any(not (ee < s or es > e) and (s - TOL <= es <= e + TOL or s - TOL <= ee <= e + TOL)
                   for es, ee in evs)

    for b in boxes:
        s, e = d2i(win, b["start"]), d2i(win, b["end"])
        L = e - s + 1
        inside = [(es, ee) for es, ee in qual if s <= es <= e] or [(es, ee) for es, ee in det if s <= es <= e]
        step = max(inside, key=lambda x: x[0]) if inside else None
        rng = random.Random(s)
        pos = [rng.randint(head, n - L) for _ in range(40)]
        ch_det = np.mean([rec(x, x + L - 1, det) for x in pos])
        ch_q = np.mean([rec(x, x + L - 1, qual) for x in pos])
        end_is_sample = b["end"] in sdates
        rows.append(dict(sym=sym, box=b["id"], L=L,
                         old=(step[0] - s) if step else None,
                         step_len=(step[1] - step[0] + 1) if step else None,
                         new=(e - step[1]) if step else None,
                         end_eq_sample=end_is_sample,
                         rec_det=rec(s, e, det), rec_q=rec(s, e, qual),
                         chance_det=round(ch_det, 2), chance_q=round(ch_q, 2),
                         bursts_per_100bars_det=round(100 * len(det) / (n - head), 2),
                         bursts_per_100bars_q=round(100 * len(qual) / (n - head), 2)))
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df.to_string(index=False))
print("median chance det/q:", df.chance_det.median(), df.chance_q.median())
