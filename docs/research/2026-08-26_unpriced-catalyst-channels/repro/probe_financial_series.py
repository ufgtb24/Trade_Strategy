"""point-in-time 财务序列可算性探针。

「tag 存在」≠「同比增速算得出来」。本探针在 112 行真实 bb 买点上，
严格只用 filed <= buy_date 的事实（无前瞻），检验：
  a) 季度营收序列长度是否够算 YoY（需 >=5 个季度点）
  b) 净利润符号分布（回答「是否排除净利润」）
  c) 各量的真实增速分布

companyfacts 原始 JSON 缓存到 scratchpad（体积大，不入 repo）。
"""
from __future__ import annotations

import json
import statistics as st
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
CACHE = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-news"
             "/123cb8f3-70f2-4818-9f90-29de07c28fca/scratchpad/companyfacts")
CACHE.mkdir(parents=True, exist_ok=True)
UA = "TradeStrategy research@example.com"

REV_CHAIN = ["RevenueFromContractWithCustomerExcludingAssessedTax",
             "RevenueFromContractWithCustomerIncludingAssessedTax",
             "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"]
NI_CHAIN = ["NetIncomeLoss", "ProfitLoss"]
CFO_CHAIN = ["NetCashProvidedByUsedInOperatingActivities",
             "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]
GP_CHAIN = ["GrossProfit"]
SH_CHAIN = ["WeightedAverageNumberOfSharesOutstandingBasic",
            "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted",
            "WeightedAverageNumberOfDilutedSharesOutstanding"]
CASH_CHAIN = ["CashAndCashEquivalentsAtCarryingValue",
              "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]


def d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def get_facts(cik: int, s: requests.Session) -> dict | None:
    p = CACHE / f"CIK{cik:010d}.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:                        # noqa: BLE001
            pass
    r = s.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", timeout=60)
    time.sleep(0.15)
    if r.status_code != 200:
        p.write_text("null")
        return None
    p.write_bytes(r.content)
    return r.json()


def duration_series(facts: dict, chain: list[str], asof: date,
                    lo: int, hi: int) -> list[tuple[date, date, float, date]]:
    """取 duration 型事实（start/end/val），只保留 filed<=asof、期长在 [lo,hi] 天内。

    同一 (start,end) 可能被多次申报（原报 + 重述），取 filed<=asof 中最早的那次，
    即「当时真正能看到的数」——重述后的修正值属于前瞻信息，必须丢弃。
    """
    gaap = facts.get("facts", {}).get("us-gaap", {})
    best: dict[tuple[date, date], tuple[float, date]] = {}
    for tag in chain:
        node = gaap.get(tag)
        if not node:
            continue
        for unit, rows in node.get("units", {}).items():
            for r in rows:
                if not r.get("start") or not r.get("end") or r.get("val") is None:
                    continue
                f = d(r["filed"])
                if f > asof:
                    continue
                s0, e0 = d(r["start"]), d(r["end"])
                span = (e0 - s0).days
                if not (lo <= span <= hi):
                    continue
                k = (s0, e0)
                if k not in best or f < best[k][1]:
                    best[k] = (float(r["val"]), f)
        if best:
            break                                 # 回退链：首个有数据的 tag 即用
    return sorted([(k[0], k[1], v[0], v[1]) for k, v in best.items()], key=lambda x: x[1])


def instant_series(facts: dict, chain: list[str], asof: date) -> list[tuple[date, float, date]]:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    best: dict[date, tuple[float, date]] = {}
    for tag in chain:
        node = gaap.get(tag)
        if not node:
            continue
        for rows in node.get("units", {}).values():
            for r in rows:
                if r.get("start") or r.get("val") is None or not r.get("end"):
                    continue
                f = d(r["filed"])
                if f > asof:
                    continue
                e0 = d(r["end"])
                if e0 not in best or f < best[e0][1]:
                    best[e0] = (float(r["val"]), f)
        if best:
            break
    return sorted([(k, v[0], v[1]) for k, v in best.items()])


def yoy(series: list[tuple[date, date, float, date]]) -> tuple[float | None, dict | None]:
    """最新季度 vs 去年同季（end 相差 330~400 天）。返回 (增速, 诊断)。"""
    if not series:
        return None, None
    cur = series[-1]
    for prev in reversed(series[:-1]):
        gap = (cur[1] - prev[1]).days
        if 330 <= gap <= 400:
            if prev[2] == 0:
                return None, {"reason": "prev_zero"}
            g = (cur[2] - prev[2]) / abs(prev[2])
            return g, {"cur_end": cur[1].isoformat(), "cur_val": cur[2],
                       "prev_end": prev[1].isoformat(), "prev_val": prev[2],
                       "cur_filed": cur[3].isoformat()}
    return None, {"reason": "no_yoy_pair", "n_quarters": len(series)}


def main() -> None:
    scores = json.loads((REPO / "docs/research/2026-08-16_news-sentiment-path2-integration"
                                "/repro/full_scores_20260816-193559.json").read_text())
    cikmap_raw = json.loads((REPO / "cache/news_sentiment/ticker_cik.json").read_text())
    cikmap = {v["ticker"].upper(): int(v["cik_str"]) for v in cikmap_raw.values()}
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})

    rows = []
    for i, r in enumerate(scores, 1):
        sym, bd = r["symbol"], d(r["buy_date"])
        cik = cikmap.get(sym.upper())
        rec: dict = {"symbol": sym, "buy_date": r["buy_date"], "fr40": r["fr40"], "cik": cik}
        facts = get_facts(cik, s) if cik else None
        if not facts:
            rec["status"] = "no_xbrl"
            rows.append(rec); continue
        rec["status"] = "ok"
        rev_q = duration_series(facts, REV_CHAIN, bd, 80, 100)
        ni_q = duration_series(facts, NI_CHAIN, bd, 80, 100)
        cfo_q = duration_series(facts, CFO_CHAIN, bd, 80, 100)
        gp_q = duration_series(facts, GP_CHAIN, bd, 80, 100)
        rev_a = duration_series(facts, REV_CHAIN, bd, 350, 380)
        ni_a = duration_series(facts, NI_CHAIN, bd, 350, 380)
        sh_q = duration_series(facts, SH_CHAIN, bd, 80, 100)
        cash = instant_series(facts, CASH_CHAIN, bd)

        rec["n_rev_q"] = len(rev_q); rec["n_rev_a"] = len(rev_a)
        rec["n_ni_q"] = len(ni_q); rec["n_cfo_q"] = len(cfo_q); rec["n_gp_q"] = len(gp_q)
        rec["n_sh_q"] = len(sh_q)
        if rev_q:
            rec["rev_latest"] = rev_q[-1][2]
            rec["rev_latest_end"] = rev_q[-1][1].isoformat()
            rec["rev_latest_filed"] = rev_q[-1][3].isoformat()
            rec["rev_lag_days"] = (bd - rev_q[-1][3]).days
        g, diag = yoy(rev_q); rec["rev_yoy_q"] = g; rec["rev_yoy_diag"] = diag
        ga, _ = yoy(rev_a); rec["rev_yoy_a"] = ga
        if len(rev_q) >= 2:
            p0, p1 = rev_q[-2][2], rev_q[-1][2]
            rec["rev_qoq"] = (p1 - p0) / abs(p0) if p0 else None
        if ni_q:
            rec["ni_latest"] = ni_q[-1][2]
            rec["ni_sign"] = "neg" if ni_q[-1][2] < 0 else "pos"
        elif ni_a:
            rec["ni_latest"] = ni_a[-1][2]
            rec["ni_sign"] = "neg" if ni_a[-1][2] < 0 else "pos"
        if cfo_q:
            rec["cfo_latest"] = cfo_q[-1][2]
            rec["cfo_sign"] = "neg" if cfo_q[-1][2] < 0 else "pos"
        if gp_q and rev_q and rev_q[-1][2]:
            # 只在同一 end 期比较
            gp_by_end = {x[1]: x[2] for x in gp_q}
            e = rev_q[-1][1]
            if e in gp_by_end:
                rec["gm_latest"] = gp_by_end[e] / rev_q[-1][2]
            # 毛利率 YoY
            for prev in reversed(rev_q[:-1]):
                if 330 <= (e - prev[1]).days <= 400 and prev[1] in gp_by_end and prev[2]:
                    if e in gp_by_end:
                        rec["gm_yoy_delta"] = gp_by_end[e]/rev_q[-1][2] - gp_by_end[prev[1]]/prev[2]
                    break
        if len(sh_q) >= 2:
            for prev in reversed(sh_q[:-1]):
                if 330 <= (sh_q[-1][1] - prev[1]).days <= 400 and prev[2]:
                    rec["shares_yoy"] = (sh_q[-1][2] - prev[2]) / prev[2]
                    break
        if cash and cfo_q and cfo_q[-1][2] < 0:
            rec["cash_latest"] = cash[-1][1]
            rec["runway_quarters"] = cash[-1][1] / abs(cfo_q[-1][2])
        rows.append(rec)
        print(f"[{i:3d}/112] {sym:8s} {r['buy_date']} rev_q={rec.get('n_rev_q')} "
              f"yoy={rec.get('rev_yoy_q')} ni={rec.get('ni_sign')}", flush=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = OUT / f"financial_series_{stamp}.json"
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str))
    print(f"\n-> {p}")


if __name__ == "__main__":
    main()
