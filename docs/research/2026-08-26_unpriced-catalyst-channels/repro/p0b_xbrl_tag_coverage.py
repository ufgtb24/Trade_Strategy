"""
⚠ 本脚本【未跑完即中止】，无结果，不构成任何结论。
中止原因：FinChannel 已独立完成同一探针（`analyze_xbrl_coverage.py` / `xbrl_coverage_20260826-052429.json`，
结论见 `channel_financial.md` §4.3-4.5），本脚本属重复劳动。保留仅作口径参考。
注：companyfacts 单票 payload 可达数 MB，142 票串行耗时过长；若要重跑，改用 companyconcept 逐 tag 小请求。

P0-b（红队代跑）：XBRL 营收 tag 在本票池上的覆盖率。
小票常用非标 tag；若标准 tag 覆盖率低，样本会被**非随机**截断（能报标准 tag 的是更规范的公司）。
两个池子：① 112 行样本的 82 个 symbol ② 全宇宙随机 60 只（估计全宇宙可用率）。
SEC 请求绕过本机代理（§8.1）。
"""
import json, time, glob, os, random, urllib.request
from collections import Counter
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
UA = {"User-Agent": "research ufgtb0@proton.me"}
cikmap = {v["ticker"].upper(): v["cik_str"]
          for v in json.load(open("cache/news_sentiment/ticker_cik.json")).values()}
REV = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
       "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
       "SalesRevenueGoodsNet", "SalesRevenueServicesNet"]
SHARES = ["WeightedAverageNumberOfSharesOutstandingBasic",
          "WeightedAverageNumberOfDilutedSharesOutstanding",
          "CommonStockSharesOutstanding"]
def facts(cik):
    u = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    with OPENER.open(urllib.request.Request(u, headers=UA), timeout=40) as r: return json.load(r)

def probe(syms, label):
    hit_rev, hit_sh, nofact, err = 0, 0, 0, 0
    which, nq = Counter(), []
    for s in syms:
        cik = cikmap.get(s.upper())
        if cik is None: err += 1; continue
        try:
            d = facts(cik); time.sleep(0.15)
        except Exception:
            nofact += 1; continue
        g = d.get("facts", {}).get("us-gaap", {})
        if not g:
            nofact += 1; continue
        found = [t for t in REV if t in g]
        if found:
            hit_rev += 1; which[found[0]] += 1
            # 该 tag 下有多少个季度点(10-Q/10-K, form 带 filed)
            units = g[found[0]].get("units", {})
            pts = next(iter(units.values()), [])
            nq.append(len([p for p in pts if p.get("form", "").startswith("10-")]))
        if any(t in g for t in SHARES): hit_sh += 1
    n = len(syms)
    print(f"\n[{label}] n={n}  (无 CIK {err} / 无 us-gaap facts {nofact})")
    print(f"  营收 tag 命中率  = {hit_rev}/{n} = {hit_rev/n*100:.1f}%")
    print(f"  股本 tag 命中率  = {hit_sh}/{n} = {hit_sh/n*100:.1f}%")
    print(f"  首选 tag 构成: {dict(which)}")
    if nq:
        nq.sort(); print(f"  每票的 10-x 营收数据点数: median={nq[len(nq)//2]} min={nq[0]} max={nq[-1]}")

rows = json.load(open("docs/research/2026-08-16_news-sentiment-path2-integration/repro/full_metrics_20260816-193657.json"))
probe(sorted({r["symbol"].upper() for r in rows}), "112 行样本的独立 symbol")
random.seed(42)
allp = [os.path.basename(p)[:-4].upper() for p in glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl")]
probe(random.sample(allp, 60), "全宇宙随机 60 只")
