"""
P0-a（红队独立复核，与 FinChannel 可能的结果互为验证）：
bb 买点距最近一次 10-Q/10-K `filed` 日有多少个**交易日**？
命题接缝：PEAD 漂移窗典型 ~60 交易日。若中位数 >60，「营收利好在 bb 点仍未兑现」的时间对齐前提破产。
只读；SEC 请求必须绕过本机代理（见 §8.1）。
"""
import json, time, pickle, urllib.request, datetime as dt, numpy as np, pandas as pd
from collections import Counter
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 绕过代理
UA = {"User-Agent": "research ufgtb0@proton.me"}
PKL = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/{}.pkl"

cikmap = {v["ticker"].upper(): v["cik_str"]
          for v in json.load(open("cache/news_sentiment/ticker_cik.json")).values()}
rows = [r for r in json.load(open(
  "docs/research/2026-08-16_news-sentiment-path2-integration/repro/full_metrics_20260816-193657.json"))
  if r.get("fr_recalc") is not None]

def submissions(cik):
    u = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    req = urllib.request.Request(u, headers=UA)
    with OPENER.open(req, timeout=30) as r: return json.load(r)

cache, out, errs = {}, [], []
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "20-F", "40-F", "10-KT", "10-QT"}
for r in rows:
    sym = r["symbol"].upper(); cik = cikmap.get(sym)
    if cik is None: errs.append((sym, "no cik")); continue
    if cik not in cache:
        try:
            cache[cik] = submissions(cik); time.sleep(0.15)
        except Exception as e:
            errs.append((sym, f"{type(e).__name__}")); cache[cik] = None
    d = cache[cik]
    if not d: continue
    rec = d["filings"]["recent"]
    buy = dt.date.fromisoformat(r["buy_date"])
    best = None
    for form, fdate in zip(rec["form"], rec["filingDate"]):
        if form not in FORMS: continue
        fd = dt.date.fromisoformat(fdate)
        if fd <= buy and (best is None or fd > best[1]): best = (form, fd)
    if best is None: errs.append((sym, "no periodic filing<=buy")); continue
    with open(PKL.format(sym), "rb") as f: px = pickle.load(f)
    idx = px.index
    i_buy = idx.get_indexer([pd.Timestamp(buy)], method="ffill")[0]
    i_fil = idx.get_indexer([pd.Timestamp(best[1])], method="bfill")[0]
    if i_buy < 0 or i_fil < 0: errs.append((sym, "date oob")); continue
    out.append(dict(sym=sym, buy=str(buy), form=best[0], filed=str(best[1]),
                    td=int(i_buy - i_fil), cd=(buy - best[1]).days, fr=r["fr_recalc"]))

print(f"[完成] {len(out)}/{len(rows)} 行；错误 {len(errs)}")
if errs: print("  错误样例:", errs[:8])
df = pd.DataFrame(out)
td = df.td.values
print(f"\n=== 买点距最近 10-Q/10-K filed 的交易日数 ===")
print(f"  median = {np.median(td):.0f}  mean = {td.mean():.1f}")
print(f"  q10={np.percentile(td,10):.0f} q25={np.percentile(td,25):.0f} "
      f"q75={np.percentile(td,75):.0f} q90={np.percentile(td,90):.0f} max={td.max()}")
for th in (20, 40, 60, 90):
    print(f"  ≤{th:>2} 交易日内的占比: {(td<=th).mean()*100:5.1f}%")
print(f"\n  表单构成: {dict(Counter(df.form))}")
print(f"\n[红灯判据] 中位数 > 60 交易日 ⟹ 时间对齐前提破产 → "
      f"实测中位数 = {np.median(td):.0f} ⟹ **{'红灯' if np.median(td)>60 else '绿灯'}**")
# 距离 vs fr：漂移窗内的买点是否 fr 更高？
df["bin"] = pd.cut(df.td, [-1, 20, 60, 10**9], labels=["≤20 交易日", "21-60", ">60"])
print("\n=== 按距财报远近分组的 fr median（探索性，非预注册）===")
print(df.groupby("bin", observed=True).agg(n=("fr","size"), fr_median=("fr","median"),
                                           td_median=("td","median")).to_string())
df.to_json("docs/research/2026-08-26_unpriced-catalyst-channels/repro/p0a_filing_distance.json",
           orient="records", indent=1)
print("\n结果已存 repro/p0a_filing_distance.json")
