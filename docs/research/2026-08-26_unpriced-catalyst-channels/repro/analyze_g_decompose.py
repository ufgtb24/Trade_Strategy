"""g 的分段拆解：财报日 -> burst 起点（旱期段） vs burst 起点 -> 买点（爆发段）。

聚合的 g（中位 +75%）会误导：它跨越了旱期和 burst 两段。
必须拆开才知道「股价没涨」在哪一段成立、在哪一段不成立。
"""
from __future__ import annotations

import json
import statistics as st
from datetime import date, datetime
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent
PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
SRC = sorted(OUT.glob("baserate_and_g_*.json"))[-1]


def d(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def i_after(dates, t):
    lo, hi = 0, len(dates)
    while lo < hi:
        m = (lo + hi) // 2
        if dates[m] < t: lo = m + 1
        else: hi = m
    return lo if lo < len(dates) else None


def i_before(dates, t):
    lo, hi = 0, len(dates)
    while lo < hi:
        m = (lo + hi) // 2
        if dates[m] <= t: lo = m + 1
        else: hi = m
    return lo - 1 if lo > 0 else None


def rep(label, v):
    if len(v) < 4:
        print(f"  {label:26s} n={len(v)} 太少"); return
    v = sorted(v); q = st.quantiles(v, n=4)
    print(f"  {label:26s} n={len(v):3d} q10={v[len(v)//10]:+.3f} q25={q[0]:+.3f} "
          f"med={st.median(v):+.3f} q75={q[2]:+.3f} q90={v[9*len(v)//10]:+.3f}")
    print(f"  {'':26s} |x|<=10%: {sum(1 for x in v if abs(x)<=.10)/len(v):5.1%} · "
          f"|x|<=20%: {sum(1 for x in v if abs(x)<=.20)/len(v):5.1%} · "
          f"x>0: {sum(1 for x in v if x>0)/len(v):5.1%}")


def main() -> None:
    recs = json.loads(SRC.read_text())
    cache = {}
    out = []
    for r in recs:
        if "g_raw" not in r:
            continue
        sym = r["symbol"]
        if sym not in cache:
            p = PKL / f"{sym}.pkl"
            if not p.exists():
                cache[sym] = None
            else:
                df = pd.read_pickle(p).reset_index()
                df["_d"] = pd.to_datetime(df["date"]).dt.date
                cache[sym] = df
        df = cache[sym]
        if df is None:
            continue
        dates = df["_d"].tolist()
        i_f = i_after(dates, d(r["filed"]))
        i_bs = i_before(dates, d(r["burst_start"]))
        i_buy = i_before(dates, d(r["buy_date"]))
        if None in (i_f, i_bs, i_buy):
            continue
        c = df["close"]
        rec = {"symbol": sym, "buy_date": r["buy_date"], "seg": r["seg"]}
        # 旱期段：财报日 -> burst 起点（仅当财报在 burst 之前才有意义）
        if i_bs > i_f and c.iat[i_f]:
            rec["g_drought"] = c.iat[i_bs] / c.iat[i_f] - 1
            rec["td_drought"] = i_bs - i_f
            hi = df["high"].values[i_f:i_bs + 1].max()
            rec["g_drought_maxpath"] = hi / c.iat[i_f] - 1
        # 爆发段：burst 起点 -> 买点
        if i_buy > i_bs and c.iat[i_bs]:
            rec["g_burst"] = c.iat[i_buy] / c.iat[i_bs] - 1
            rec["td_burst"] = i_buy - i_bs
        rec["g_total"] = r["g_raw"]
        out.append(rec)

    print(f"n = {len(out)}\n")
    dr = [x["g_drought"] for x in out if "g_drought" in x]
    bu = [x["g_burst"] for x in out if "g_burst" in x]
    print("[C] g 的分段拆解（原始，未减基准）")
    rep("① 财报日 → burst 起点", dr)
    rep("② burst 起点 → 买点", bu)
    rep("①+② 合计 = g_total", [x["g_total"] for x in out])
    print(f"\n  段长中位: 旱期段 {st.median([x['td_drought'] for x in out if 'td_drought' in x]):.0f} 交易日"
          f" · 爆发段 {st.median([x['td_burst'] for x in out if 'td_burst' in x]):.0f} 交易日")

    print("\n[D] 只看财报落在旱期内的行（主口径，n=37）")
    sel = [x for x in out if x["seg"] == "旱期内"]
    rep("① 财报日 → burst 起点", [x["g_drought"] for x in sel if "g_drought" in x])
    rep("  其中窗内最高价涨幅", [x["g_drought_maxpath"] for x in sel if "g_drought_maxpath" in x])
    rep("② burst 起点 → 买点", [x["g_burst"] for x in sel if "g_burst" in x])

    print("\n[E] 归因：g_total 里 burst 段贡献多少")
    both = [x for x in out if "g_drought" in x and "g_burst" in x]
    frac = []
    for x in both:
        lt = abs(st.log(1 + max(x["g_total"], -0.99)) if x["g_total"] > -1 else 0)
        lb = abs(st.log(1 + max(x["g_burst"], -0.99)) if x["g_burst"] > -1 else 0)
        if lt > 1e-9:
            frac.append(min(lb / lt, 2.0))
    if frac:
        print(f"  burst 段占全程对数涨幅的比例: med={st.median(frac):.1%} "
              f"q25={st.quantiles(frac,n=4)[0]:.1%} q75={st.quantiles(frac,n=4)[2]:.1%}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (OUT / f"g_decompose_{stamp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\n-> g_decompose_{stamp}.json")


if __name__ == "__main__":
    import math
    st.log = math.log
    main()
