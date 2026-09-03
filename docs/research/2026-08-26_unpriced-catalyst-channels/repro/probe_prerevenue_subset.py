"""零营收子样本的覆盖率交叉表 + 「首次产生营收」标记的作用面。

动机：营收缺失不是随机缺失——缺的 27 行全是零营收的生物/矿业/概念股，
而这正是 bb 池里最投机、波动最大的一群。若这群票在所有财务量上都缺，
财务通道就有一个与 outcome 相关的结构性盲区，必须显式报告而不是当缺失值丢掉。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
CACHE = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-news"
             "/123cb8f3-70f2-4818-9f90-29de07c28fca/scratchpad/companyfacts")
SER = sorted(OUT.glob("financial_series_*.json"))[-1]
REPO = OUT.parents[3]

REV = ["RevenueFromContractWithCustomerExcludingAssessedTax",
       "RevenueFromContractWithCustomerIncludingAssessedTax",
       "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"]


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def rev_quarters(facts, asof):
    gaap = facts.get("facts", {}).get("us-gaap", {})
    best = {}
    for tag in REV:
        node = gaap.get(tag)
        if not node:
            continue
        for rows in node.get("units", {}).values():
            for r in rows:
                if not r.get("start") or not r.get("end") or r.get("val") is None:
                    continue
                if d(r["filed"]) > asof:
                    continue
                s0, e0 = d(r["start"]), d(r["end"])
                if not (80 <= (e0 - s0).days <= 100):
                    continue
                k = (s0, e0)
                f = d(r["filed"])
                if k not in best or f < best[k][1]:
                    best[k] = (float(r["val"]), f)
        if best:
            break
    return sorted([(k[1], v[0]) for k, v in best.items()])


def main() -> None:
    rows = json.loads(SER.read_text())
    cikmap_raw = json.loads((REPO / "cache/news_sentiment/ticker_cik.json").read_text())
    cikmap = {v["ticker"].upper(): int(v["cik_str"]) for v in cikmap_raw.values()}

    # 分组：有营收 vs 零营收 vs 无 XBRL
    grp = {"有营收": [], "零营收": [], "无XBRL": []}
    first_rev = []
    for r in rows:
        if r.get("status") != "ok":
            grp["无XBRL"].append(r); continue
        if r.get("n_rev_q", 0) == 0:
            grp["零营收"].append(r); continue
        grp["有营收"].append(r)
        # 「首次产生营收」：最近一季 >0 且去年同季 == 0
        cik = cikmap.get(r["symbol"].upper())
        p = CACHE / f"CIK{cik:010d}.json"
        if not p.exists() or p.read_text().strip() == "null":
            continue
        q = rev_quarters(json.loads(p.read_text()), d(r["buy_date"]))
        if len(q) < 2:
            continue
        cur = q[-1]
        for prev in reversed(q[:-1]):
            if 330 <= (cur[0] - prev[0]).days <= 400:
                if prev[1] == 0 and cur[1] > 0:
                    first_rev.append((r["symbol"], r["buy_date"], cur[1]))
                break

    n = len(rows)
    print(f"总 {n} 行  |  有营收 {len(grp['有营收'])} · 零营收 {len(grp['零营收'])} · 无XBRL {len(grp['无XBRL'])}\n")

    fields = [("净利润符号", "ni_sign"), ("CFO 值", "cfo_latest"),
              ("毛利率水平", "gm_latest"), ("股本 YoY", "shares_yoy"),
              ("现金 runway", "runway_quarters")]
    print("[J] 覆盖率交叉表（各量在两个子样本上的可算率）")
    print(f"{'量':14s} {'有营收组':>18s} {'零营收组':>18s}")
    for label, key in fields:
        a = grp["有营收"]; b = grp["零营收"]
        ca = sum(1 for r in a if r.get(key) is not None)
        cb = sum(1 for r in b if r.get(key) is not None)
        print(f"{label:14s} {ca:3d}/{len(a):3d} = {ca/len(a):6.1%}   "
              f"{cb:3d}/{len(b):3d} = {cb/len(b):6.1%}")

    # 零营收组的性质
    b = grp["零营收"]
    neg = sum(1 for r in b if r.get("ni_sign") == "neg")
    print(f"\n[K] 零营收组（{len(b)} 行 / {len({r['symbol'] for r in b})} 只票）：")
    print(f"    净利亏损 {neg}/{sum(1 for r in b if r.get('ni_sign'))}")
    rw = [r["runway_quarters"] for r in b if r.get("runway_quarters") is not None]
    if rw:
        import statistics as st
        print(f"    runway 可算 {len(rw)} 行，中位 {st.median(rw):.2f} 季度")
    print(f"    票: {sorted({r['symbol'] for r in b})}")

    print(f"\n[L] 「首次产生营收」（去年同季 = 0 且本季 > 0）: {len(first_rev)} 行")
    for x in first_rev:
        print(f"    {x[0]:8s} {x[1]}  本季营收 {x[2]:,.0f}")


if __name__ == "__main__":
    main()
