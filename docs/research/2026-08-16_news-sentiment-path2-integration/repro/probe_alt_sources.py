# -*- coding: utf-8 -*-
"""多源新闻可得性探针: 覆盖 × 历史深度 双维度。

源: Google News RSS / SEC EDGAR(8-K) / GDELT / AlphaVantage(已集成)
准则(用户定): ① 小票覆盖 ② 新闻保留历史时长; 其余因素测试中发现。

- 覆盖: 13 只 Finnhub 零覆盖小票 × 各自买点前7天窗口(2025-09..12)
- 深度: 大票(Apple, 恒有海量新闻)× 距今阶梯 → 纯测源保留边界;
        小票(Westwater) 同阶梯 → 分辨「源不留」vs「本来没有」
"""
import json
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yaml

OUT_DIR = Path(__file__).resolve().parent
UA = {"User-Agent": "TradeStrategy research@example.com"}

# Finnhub 零覆盖小票 (prefill_n30 实测) + 买点
TARGETS = [
    ("CATO", "2025-09-04"), ("FOCL", "2025-09-05"), ("HOWL", "2025-10-01"),
    ("BGDE", "2025-10-06"), ("WWR", "2025-10-06"), ("MTC", "2025-11-10"),
    ("LRDC", "2025-11-12"), ("COHN", "2025-11-14"), ("FUST", "2025-11-18"),
    ("COBA", "2025-12-02"), ("CALC", "2025-12-03"), ("SRGZ", "2025-12-09"),
    ("SPQS", "2025-12-12"),
]
# 深度阶梯: (距今月数, 说明)
DEPTH_LADDER = [(0, "最近一周"), (3, "3个月前"), (8, "8个月前"), (12, "12个月前"),
                (18, "18个月前"), (24, "24个月前"), (36, "36个月前")]
REF_DATE = datetime(2026, 8, 16)  # 探针日


def win_months_ago(months: int) -> tuple[str, str]:
    end = REF_DATE - timedelta(days=30 * months)
    start = end - timedelta(days=7)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


# ---------------- 各源 ----------------

def gnews_rss(query: str, d_from: str, d_to: str) -> list[dict]:
    before = (datetime.strptime(d_to, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    url = (f"https://news.google.com/rss/search?q={requests.utils.quote(query)}"
           f"+after:{d_from}+before:{before}&hl=en-US&gl=US&ceid=US:en")
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    return [{"title": i.findtext("title", ""), "pub": i.findtext("pubDate", ""),
             "src": (i.findtext("source") or "")} for i in root.iter("item")]


def edgar_efts(ticker: str, d_from: str, d_to: str, use_entity: bool = False) -> list[dict]:
    if use_entity:
        params = {"dateRange": "custom", "startdt": d_from, "enddt": d_to,
                  "forms": "8-K", "entity": ticker}
    else:
        params = {"q": f'"{ticker}"', "dateRange": "custom", "startdt": d_from,
                  "enddt": d_to, "forms": "8-K"}
    r = requests.get("https://efts.sec.gov/LATEST/search-index", params=params,
                     headers=UA, timeout=15)
    r.raise_for_status()
    hits = r.json().get("hits", {}).get("hits", [])
    return [{"title": f"{h.get('_source', {}).get('entity_name', '?')} - 8-K "
                      f"({h.get('_source', {}).get('file_date', '')})",
             "pub": h.get("_source", {}).get("file_date", ""),
             "src": h.get("_source", {}).get("entity_name", "")} for h in hits]


def gdelt(query: str, d_from: str, d_to: str) -> list[dict]:
    s = d_from.replace("-", "") + "120000"
    e = d_to.replace("-", "") + "120000"
    url = ("https://api.gdeltproject.org/api/v2/doc/doc?"
           f"query={requests.utils.quote(chr(34) + query + chr(34))}"
           f"&mode=artlist&maxrecords=30&sort=dateasc"
           f"&startdatetime={s}&enddatetime={e}&format=json")
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    if not r.text.strip().startswith("{"):
        return []
    return [{"title": a.get("title", ""), "pub": a.get("seendate", ""),
             "src": a.get("domain", "")} for a in r.json().get("articles", [])]


def alphavantage(ticker: str, d_from: str, d_to: str) -> list[dict]:
    key = yaml.safe_load(open("configs/api_keys.yaml"))["alphavantage"]
    params = {
        "function": "NEWS_SENTIMENT", "tickers": ticker, "limit": "50",
        "time_from": d_from.replace("-", "") + "T0000",
        "time_to": d_to.replace("-", "") + "T2359",
        "apikey": key,
    }
    r = requests.get("https://www.alphavantage.co/query", params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "Information" in data or "Note" in data or "Error Message" in data:
        raise RuntimeError(f"AV: {str(data)[:120]}")
    feed = data.get("feed", [])
    return [{"title": a.get("title", ""), "pub": a.get("time_published", ""),
             "src": a.get("source", "")} for a in feed]


def probe(label: str, fn) -> object:
    try:
        items = fn()
        return len(items) if not isinstance(items, str) else items
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:60]}"


# ---------------- 主流程 ----------------

def run_coverage() -> list[dict]:
    conn = sqlite3.connect("cache/news_sentiment/cache.db")
    names = dict(conn.execute("SELECT ticker, name FROM company_names").fetchall())
    report = []
    for sym, buy in TARGETS:
        d_from = (datetime.strptime(buy, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        d_to = buy
        name = names.get(sym, "")
        row = {"symbol": sym, "company": name, "window": [d_from, d_to]}
        cases = [
            ("gnews_ticker", lambda: gnews_rss(sym, d_from, d_to)),
            ("gnews_name", lambda: gnews_rss(name, d_from, d_to) if name else []),
            ("edgar_q", lambda: edgar_efts(sym, d_from, d_to)),
            ("edgar_entity", lambda: edgar_efts(sym, d_from, d_to, use_entity=True)),
            # gdelt 剔除: api.gdeltproject.org 本机直连不通(curl 12s 超时)、proxy 已挂
            # ("gdelt_name", lambda: gdelt(name, d_from, d_to) if name else []),
        ]
        for label, fn in cases:
            row[label] = probe(label, fn)
            if isinstance(row[label], int) and label == "edgar_entity":
                row[f"{label}_sample"] = [i["title"][:55] for i in fn()[:2]]
            time.sleep(1.0)
        report.append(row)
        print(f"[cov] {sym:5s} {name[:22]:22s} gT={row['gnews_ticker']!s:>4} "
              f"gN={row['gnews_name']!s:>4} eQ={row['edgar_q']!s:>4} "
              f"eE={row['edgar_entity']!s:>4}")
    return report


def run_depth() -> list[dict]:
    # 大票=纯深度边界; 小票=深度×覆盖叠加; AV 只测大票(省配额)
    report = []
    for months, note in DEPTH_LADDER:
        d_from, d_to = win_months_ago(months)
        row = {"months_ago": months, "note": note, "window": [d_from, d_to]}
        row["gnews_apple"] = probe("g", lambda: gnews_rss("Apple Inc", d_from, d_to))
        time.sleep(1.0)
        row["gnews_wwr"] = probe("g", lambda: gnews_rss("Westwater Resources", d_from, d_to))
        time.sleep(1.0)
        row["edgar_aapl"] = probe("e", lambda: edgar_efts("AAPL", d_from, d_to))
        time.sleep(0.4)
        row["edgar_wwr"] = probe("e", lambda: edgar_efts("WWR", d_from, d_to))
        time.sleep(0.4)
        row["av_aapl"] = probe("av", lambda: alphavantage("AAPL", d_from, d_to))
        time.sleep(1.0)
        report.append(row)
        print(f"[dep] -{months:2d}月 {d_from}..{d_to} gA={row['gnews_apple']!s:>4} "
              f"gW={row['gnews_wwr']!s:>4} eA={row['edgar_aapl']!s:>4} "
              f"eW={row['edgar_wwr']!s:>4} avA={row['av_aapl']!s:>4}")
    return report


def main():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    cov = run_coverage()
    dep = run_depth()
    out = {"coverage": cov, "depth": dep,
           "meta": {"probe_date": "2026-08-16",
                    "targets": "13 Finnhub-uncovered microcaps, buy windows",
                    "ladder": [m for m, _ in DEPTH_LADDER]}}
    path = OUT_DIR / f"alt_sources_probe_{stamp}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nsaved: {path}")
    print(f"非零覆盖票数(共{len(cov)}): "
          + ", ".join(f"{k}={sum(1 for r in cov if isinstance(r.get(k), int) and r[k] > 0)}"
                      for k in ("gnews_ticker", "gnews_name", "edgar_q",
                                "edgar_entity")))


if __name__ == "__main__":
    main()
