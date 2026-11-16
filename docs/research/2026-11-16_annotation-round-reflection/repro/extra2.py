"""一次性：S3 前缀成族在样本 / 反馈视野的报出数；涨幅版前高（阶跃最猛一根 vs 阶跃前 60 根最猛一根）在正样本上的撞车数；
以及「一致的样本里有多少张的阶跃按新认法会挪」。"""
import numpy as np
from collections import defaultdict
import signals as S
import tabulate as T

def s3_of(sym, evl):
    """evl 里的 hit：当天是否同一段阶跃有 ≥2 个前缀都在买（看全部 hit）。"""
    hits = S.hits_of(sym)
    out = False
    for ev in evl:
        same = {h["e"] for h in hits if h["t"] == ev["t"] and h["s"] == ev["s"]}
        if len(same) >= 2:
            out = True
    return out

V = T.views()
for vname in ("样本16", "反馈10"):
    names = [n for n, sym, evl in V[vname] if s3_of(sym, evl)]
    print(vname, "S3 报出", len(names), names)

# 一族里短前缀的 hit：新平台里夹着「同一段阶跃剩下的根」
print("== 涨幅版前高：阶跃最猛一根 r 是否 < 阶跃前 60 根里最猛一根 r（是 → 涨幅版会挡）==")
for sym, d, ok, *_ in S.SAMPLES:
    day, o, h, cl, evs = S.arrays(sym)
    i = day.index(d)
    hs = sorted([ev for ev in S.hits_of(sym) if abs(ev["t"] - i) <= S.POS_TOL], key=lambda ev: abs(ev["t"] - i))
    evl = hs[:1] if hs else sorted([ev for ev in evs if ev["t"] == i], key=lambda ev: -ev["step_rise"])[:1]
    if not evl:
        print(" ", sym, d, "无候选"); continue
    ev = evl[0]
    r = np.concatenate([[np.nan], np.log(cl[1:] / cl[:-1])])
    s = ev["s"]
    prior = np.nanmax(r[max(1, s - 60):s])
    price_ratio = h[max(0, s - 60):s].max() / cl[ev["e"]]
    print(f"  {sym} {d} step={day[s]}..{day[ev['e']]} 阶跃最猛 {ev['step_max_ret']:.3f} 前60根最猛 {prior:.3f} "
          f"涨幅版挡={prior >= ev['step_max_ret']}  价格版(前60根最高价/阶跃末根收盘)={price_ratio:.2f}")
