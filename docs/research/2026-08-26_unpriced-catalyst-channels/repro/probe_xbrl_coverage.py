"""SEC XBRL 可得性探针：在真实 bb 买点票池（82 只）上实测财务量覆盖率。

用途（纯研究探针，不属于生产代码）：
- 回答「哪些财务 concept 在 bb 的微盘/OTC 票池上真的取得到」，而非引用文档断言。
- 同时测 filing 节奏（10-Q/10-K 是否季度更新、最近一次距 buy_date 多少天），
  用于判断财务量的更新频率与 bb 形态时间尺度是否匹配。

数据源：
- ticker→CIK：cache/news_sentiment/ticker_cik.json（SEC company_tickers.json 快照）
- https://data.sec.gov/submissions/CIK{cik:010d}.json         —— 申报流水
- https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json —— 全部 XBRL 事实

注意：本机 http(s)_proxy 指向 clash 端口，SEC 走代理会 TLS 挂死，必须 trust_env=False 直连。
SEC 限流 10 req/s，沿用 collector 的 sleep 0.15s。
"""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
UA = "TradeStrategy research@example.com"

# 候选财务量 → XBRL concept 回退链（顺序即优先级）
CONCEPT_CHAINS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets"],
    "deferred_revenue": ["ContractWithCustomerLiabilityCurrent",
                         "DeferredRevenueCurrent"],
    "rpo": ["RevenueRemainingPerformanceObligation"],
    "receivables": ["AccountsReceivableNetCurrent",
                    "AccountsReceivableGrossCurrent",
                    "ReceivablesNetCurrent"],
    "inventory": ["InventoryNet", "InventoryGross"],
    "rnd": ["ResearchAndDevelopmentExpense"],
    "shares_wavg": ["WeightedAverageNumberOfSharesOutstandingBasic",
                    "WeightedAverageNumberOfDilutedSharesOutstanding",
                    "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "assets": ["Assets"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
}

# 「近期仍在用」的判据：该 tag 至少有一个事实的 filed 日期在此之后
RECENT_CUTOFF = date(2025, 1, 1)


def session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False          # 关键：绕开本机 clash 代理
    s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    return s


def load_cik_map() -> dict[str, int]:
    raw = json.loads((REPO / "cache/news_sentiment/ticker_cik.json").read_text())
    return {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}


def fetch(s: requests.Session, url: str) -> tuple[int, dict | None, int]:
    try:
        r = s.get(url, timeout=30)
        time.sleep(0.15)
        if r.status_code != 200:
            return r.status_code, None, len(r.content)
        return 200, r.json(), len(r.content)
    except Exception as exc:                       # noqa: BLE001
        time.sleep(0.15)
        return -1, {"error": str(exc)}, 0


def analyse_facts(facts: dict) -> dict:
    """从 companyfacts 提取：各 concept 链的命中情况 + 最新事实日期 + 季度粒度。"""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    ifrs = facts.get("facts", {}).get("ifrs-full", {})
    out: dict = {
        "n_gaap_tags": len(gaap),
        "n_ifrs_tags": len(ifrs),
        "taxonomies": sorted(facts.get("facts", {}).keys()),
        "concepts": {},
    }
    for name, chain in CONCEPT_CHAINS.items():
        hit = None
        for tag in chain:
            node = gaap.get(tag)
            if not node:
                continue
            filed = []
            forms = Counter()
            for unit_rows in node.get("units", {}).values():
                for row in unit_rows:
                    if row.get("filed"):
                        filed.append(row["filed"])
                    forms[row.get("form", "?")] += 1
            if not filed:
                continue
            last = max(filed)
            recent = datetime.strptime(last, "%Y-%m-%d").date() >= RECENT_CUTOFF
            if hit is None or (recent and not hit["recent"]):
                hit = {"tag": tag, "last_filed": last, "recent": recent,
                       "n_facts": sum(forms.values()), "forms": dict(forms.most_common(4))}
            if recent:
                break
        out["concepts"][name] = hit
    return out


def analyse_submissions(sub: dict) -> dict:
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    per_form: dict[str, list[str]] = defaultdict(list)
    for f, d in zip(forms, dates):
        per_form[f].append(d)
    return {
        "entityType": sub.get("entityType"),
        "sic": sub.get("sic"),
        "sicDescription": sub.get("sicDescription"),
        "name": sub.get("name"),
        "exchanges": sub.get("exchanges"),
        "fiscalYearEnd": sub.get("fiscalYearEnd"),
        "form_counts": dict(Counter(forms).most_common(12)),
        "last_10Q": max(per_form.get("10-Q", []), default=None),
        "last_10K": max(per_form.get("10-K", []), default=None),
        "last_20F": max(per_form.get("20-F", []), default=None),
        "all_10Q_dates": sorted(per_form.get("10-Q", []), reverse=True)[:10],
        "all_10K_dates": sorted(per_form.get("10-K", []), reverse=True)[:5],
        "all_4_dates": sorted(per_form.get("4", []), reverse=True)[:60],
        "n_form4": len(per_form.get("4", [])),
        "n_SC13D": len(per_form.get("SC 13D", [])) + len(per_form.get("SC 13D/A", [])),
        "n_SC13G": len(per_form.get("SC 13G", [])) + len(per_form.get("SC 13G/A", [])),
    }


def main() -> None:
    scores = json.loads((REPO / "docs/research/2026-08-16_news-sentiment-path2-integration"
                                "/repro/full_scores_20260816-193559.json").read_text())
    symbols = sorted({r["symbol"] for r in scores})
    cik_map = load_cik_map()
    s = session()

    result: dict[str, dict] = {}
    unresolved: list[str] = []
    t0 = time.time()
    for i, sym in enumerate(symbols, 1):
        cik = cik_map.get(sym.upper())
        if cik is None:
            unresolved.append(sym)
            result[sym] = {"cik": None}
            continue
        rec: dict = {"cik": cik}
        code, sub, _ = fetch(s, f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        rec["submissions_http"] = code
        if code == 200 and sub:
            rec["submissions"] = analyse_submissions(sub)
        code, facts, nbytes = fetch(
            s, f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        rec["companyfacts_http"] = code
        rec["companyfacts_bytes"] = nbytes
        if code == 200 and facts:
            rec["facts"] = analyse_facts(facts)
        result[sym] = rec
        print(f"[{i:3d}/{len(symbols)}] {sym:8s} cik={cik:<8} "
              f"sub={rec.get('submissions_http')} facts={rec.get('companyfacts_http')} "
              f"({nbytes/1024:.0f}KB)", flush=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = OUT / f"xbrl_coverage_{stamp}.json"
    path.write_text(json.dumps(
        {"generated": stamp, "n_symbols": len(symbols), "unresolved": unresolved,
         "recent_cutoff": RECENT_CUTOFF.isoformat(),
         "concept_chains": CONCEPT_CHAINS, "by_symbol": result},
        ensure_ascii=False, indent=1))
    print(f"\nelapsed {time.time()-t0:.0f}s -> {path}")


if __name__ == "__main__":
    main()
