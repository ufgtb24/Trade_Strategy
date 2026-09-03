# -*- coding: utf-8 -*-
"""情绪/讨论热度候选源 —— 一轮可达性总探针（2026-08-26）。

目的：对「非财务的情绪热度通道」的每个候选源，实测：
  HTTP 状态 / 是否需要 auth / 返回条数 / 是否含历史 / 限流信号。
只做**可达性 + 契约**层，覆盖率与历史深度留给 probe_wiki_coverage.py 等专项脚本。

纪律：实测 > 文档。任何「可用/不可用」的断言都必须落在本脚本的输出 JSON 里。
"""
import json
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml

OUT_DIR = Path(__file__).resolve().parent
ROOT = OUT_DIR.parents[3]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-probe ufgtb0@proton.me"}
TIMEOUT = 15

KEYS = yaml.safe_load((ROOT / "configs" / "api_keys.yaml").read_text())


def probe(name: str, url: str, headers=None, params=None, note: str = "") -> dict:
    """单次 GET 探针，返回结构化结果（永不抛异常）。"""
    rec = {"name": name, "url": url, "note": note}
    t0 = time.time()
    try:
        r = requests.get(url, headers=headers or UA, params=params, timeout=TIMEOUT)
        rec["status"] = r.status_code
        rec["elapsed_s"] = round(time.time() - t0, 2)
        rec["ctype"] = r.headers.get("Content-Type", "")
        # 限流相关 header
        rec["ratelimit_headers"] = {
            k: v for k, v in r.headers.items()
            if "rate" in k.lower() or "limit" in k.lower() or "retry" in k.lower()
        }
        body = r.text
        rec["bytes"] = len(body)
        try:
            j = r.json()
            rec["json_top"] = list(j)[:12] if isinstance(j, dict) else f"list[{len(j)}]"
            rec["sample"] = json.dumps(j, ensure_ascii=False)[:600]
        except Exception:
            rec["sample"] = body[:600]
    except Exception as e:
        rec["status"] = None
        rec["elapsed_s"] = round(time.time() - t0, 2)
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def main():
    results = []

    # ---------- 1. StockTwits ----------
    results.append(probe(
        "stocktwits_public_stream",
        "https://api.stocktwits.com/api/2/streams/symbol/AAPL.json",
        note="曾经的公开只读端点（无 key）"))
    results.append(probe(
        "stocktwits_smallcap_stream",
        "https://api.stocktwits.com/api/2/streams/symbol/SRGZ.json",
        note="小票覆盖抽测"))
    results.append(probe(
        "stocktwits_trending",
        "https://api.stocktwits.com/api/2/trending/symbols.json",
        note="热榜端点"))

    # ---------- 2. Reddit ----------
    results.append(probe(
        "reddit_unauth_search",
        "https://www.reddit.com/r/wallstreetbets/search.json",
        params={"q": "GME", "restrict_sr": 1, "limit": 5, "sort": "new"},
        note="未鉴权 .json 端点现行政策"))
    results.append(probe(
        "reddit_unauth_listing",
        "https://www.reddit.com/r/pennystocks/new.json", params={"limit": 5},
        note="未鉴权 listing"))
    results.append(probe(
        "pushshift_legacy",
        "https://api.pushshift.io/reddit/search/submission/",
        params={"q": "GME", "size": 5}, note="旧 Pushshift 公共 API（预期已关）"))
    results.append(probe(
        "arctic_shift_posts",
        "https://arctic-shift.photon-reddit.com/api/posts/search",
        params={"subreddit": "wallstreetbets", "limit": 5},
        note="Pushshift 后继存档（社区维护）"))
    results.append(probe(
        "arctic_shift_hist",
        "https://arctic-shift.photon-reddit.com/api/posts/search",
        params={"subreddit": "pennystocks", "limit": 5,
                "after": "2025-09-01", "before": "2025-09-08"},
        note="存档历史回溯能力"))
    results.append(probe(
        "tradestie_wsb_hist",
        "https://tradestie.com/api/v1/apps/reddit",
        params={"date": "2025-09-05"}, note="第三方 WSB 每日 mention 榜（历史）"))
    results.append(probe(
        "apewisdom_all",
        "https://apewisdom.io/api/v1.0/filter/all-stocks",
        note="第三方 Reddit mention 聚合（快照）"))

    # ---------- 3. X / Twitter ----------
    results.append(probe(
        "x_api_recent_search",
        "https://api.twitter.com/2/tweets/search/recent",
        params={"query": "$AAPL"}, note="无 bearer token 时的行为"))

    # ---------- 4. Google Trends ----------
    results.append(probe(
        "gtrends_explore",
        "https://trends.google.com/trends/api/explore",
        params={"hl": "en-US", "tz": "0",
                "req": json.dumps({"comparisonItem": [
                    {"keyword": "GameStop", "geo": "US", "time": "today 12-m"}],
                    "category": 0, "property": ""})},
        note="非官方 explore 入口（pytrends 走这条）"))
    results.append(probe(
        "gtrends_dailytrends",
        "https://trends.google.com/trends/api/dailytrends",
        params={"hl": "en-US", "tz": "0", "geo": "US"},
        note="每日热搜端点"))

    # ---------- 5. Wikipedia pageviews ----------
    results.append(probe(
        "wiki_pageviews_bigcap",
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        "en.wikipedia/all-access/user/Apple_Inc./daily/20250101/20250115",
        note="官方 REST，日级浏览量"))
    results.append(probe(
        "wiki_pageviews_deep",
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        "en.wikipedia/all-access/user/Apple_Inc./daily/20150701/20150710",
        note="历史起点探测（2015-07）"))

    # ---------- 6. 中文股吧 ----------
    results.append(probe(
        "xueqiu_timeline",
        "https://xueqiu.com/statuses/stock_timeline.json",
        params={"symbol_id": "AAPL", "count": 5}, note="雪球（需 cookie？）"))
    results.append(probe(
        "eastmoney_guba_us",
        "https://guba.eastmoney.com/list,USAAPL.html", note="东财美股股吧"))

    # ---------- 7. Yahoo / SA / iHub ----------
    results.append(probe(
        "yahoo_conversations",
        "https://finance.yahoo.com/quote/AAPL/community",
        note="Yahoo conversations 页面"))
    results.append(probe(
        "seekingalpha_api",
        "https://seekingalpha.com/api/v3/symbols/AAPL/news",
        note="SA 内部 API（预期 Cloudflare）"))
    results.append(probe(
        "investorshub_board",
        "https://investorshub.advfn.com/Sagebrush-Gold-Ltd-SRGZ/",
        note="iHub 小票板块页"))

    # ---------- 8. 市场内代理量 ----------
    results.append(probe(
        "finra_regsho_daily",
        "https://cdn.finra.org/equity/regsho/daily/CNMSshvol20250905.txt",
        note="FINRA 每日做空成交量（全市场逐票）"))
    results.append(probe(
        "finra_regsho_old",
        "https://cdn.finra.org/equity/regsho/daily/CNMSshvol20200902.txt",
        note="历史深度探测（5 年前）"))
    results.append(probe(
        "cboe_options_chain",
        "https://cdn.cboe.com/api/global/delayed_quotes/options/AAPL.json",
        note="CBOE 期权链（含 volume/OI，快照）"))
    results.append(probe(
        "finnhub_social_sentiment",
        "https://finnhub.io/api/v1/stock/social-sentiment",
        params={"symbol": "AAPL", "token": KEYS["finnhub"]},
        note="Finnhub Reddit+Twitter mention 计数（免费档？）"))
    results.append(probe(
        "finnhub_insider",
        "https://finnhub.io/api/v1/stock/insider-transactions",
        params={"symbol": "AAPL", "token": KEYS["finnhub"]},
        note="对照：另一个可能收费的端点"))
    results.append(probe(
        "stooq_daily_smallcap",
        "https://stooq.com/q/d/l/",
        params={"s": "srgz.us", "i": "d"},
        note="免费日线（量能来源备用，小票覆盖）"))

    # ---------- 9. SEC EDGAR 关注度代理 ----------
    results.append(probe(
        "edgar_efts_hits",
        "https://efts.sec.gov/LATEST/search-index",
        headers={"User-Agent": "TradeStrategy research ufgtb0@proton.me"},
        params={"q": '"Sagebrush Gold"', "dateRange": "custom",
                "startdt": "2025-09-01", "enddt": "2025-12-31"},
        note="全文检索命中量（机构侧关注度代理）"))
    results.append(probe(
        "edgar_logfile_index",
        "https://www.sec.gov/files/edgar-log-file-data-set.html",
        headers={"User-Agent": "TradeStrategy research ufgtb0@proton.me"},
        note="EDGAR 访问日志数据集现状"))

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"sentiment_sources_probe_{ts}.json"
    out.write_text(json.dumps(
        {"probed_at": ts, "results": results}, ensure_ascii=False, indent=1))

    for r in results:
        print(f"{r['name']:32s} {str(r.get('status')):6s} "
              f"{r.get('elapsed_s')}s {r.get('bytes','-')}B "
              f"{r.get('error','')[:60] if r.get('error') else ''}")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
