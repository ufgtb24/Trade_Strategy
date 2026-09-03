# -*- coding: utf-8 -*-
"""StockTwits 专项探针：小票覆盖 × 历史深度 × 限流 × 字段。

试金石与新闻源一致：13 只 Finnhub 零新闻覆盖的小票（2026-08-16 实测得到），
外加 2 只大票作对照。

三问：
  Q1 覆盖 —— 这些小票在 StockTwits 有 symbol 吗？首页有几条消息？最老一条多久前？
  Q2 深度 —— 用 max= 游标能翻回多久？（决定能否回测 2025-09..12 的买点）
  Q3 密度 —— 日均消息条数量级（对照新闻的「7 天窗中位 2 条」）
另记录 messages[].entities.sentiment（用户自标 Bullish/Bearish）的填充率。
"""
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-probe ufgtb0@proton.me"}
BASE = "https://api.stocktwits.com/api/2/streams/symbol/{}.json"

SMALL = ["CATO", "FOCL", "HOWL", "BGDE", "WWR", "MTC", "LRDC",
         "COHN", "FUST", "COBA", "CALC", "SRGZ", "SPQS"]
BIG = ["AAPL", "GME"]
DEEP_TARGETS = ["WWR", "CATO", "AAPL"]   # 翻页深度测试
MAX_PAGES = 12
SLEEP = 1.2


def get_page(sym: str, max_id=None) -> tuple[int, dict, dict]:
    params = {"limit": 30}
    if max_id is not None:
        params["max"] = max_id
    r = requests.get(BASE.format(sym), headers=UA, params=params, timeout=20)
    try:
        j = r.json()
    except Exception:
        j = {}
    rl = {k: v for k, v in r.headers.items()
          if "rate" in k.lower() or "retry" in k.lower()}
    return r.status_code, j, rl


def parse_msgs(j: dict) -> list[dict]:
    out = []
    for m in j.get("messages", []) or []:
        ent = m.get("entities") or {}
        sent = (ent.get("sentiment") or {})
        out.append({
            "id": m.get("id"),
            "created_at": m.get("created_at"),
            "sentiment": sent.get("basic") if isinstance(sent, dict) else None,
            "likes": (m.get("likes") or {}).get("total", 0),
        })
    return out


def age_days(iso: str) -> float:
    if not iso:
        return -1
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return round((datetime.now(timezone.utc) - t).total_seconds() / 86400, 2)


def main():
    res = {"coverage": {}, "depth": {}, "meta": {
        "probed_at": datetime.now().isoformat(timespec="seconds")}}

    # ---- Q1/Q3 覆盖 + 密度 ----
    for sym in SMALL + BIG:
        st, j, rl = get_page(sym)
        rec = {"status": st, "ratelimit": rl}
        if st == 200:
            msgs = parse_msgs(j)
            rec["n_first_page"] = len(msgs)
            rec["watchlist_count"] = (j.get("symbol") or {}).get("watchlist_count")
            rec["title"] = (j.get("symbol") or {}).get("title")
            if msgs:
                rec["newest_age_days"] = age_days(msgs[0]["created_at"])
                rec["oldest_age_days"] = age_days(msgs[-1]["created_at"])
                span = rec["oldest_age_days"] - rec["newest_age_days"]
                rec["msgs_per_day_est"] = (round(len(msgs) / span, 2)
                                           if span > 0 else None)
                rec["sentiment_fill"] = dict(Counter(
                    m["sentiment"] or "none" for m in msgs))
        else:
            rec["body"] = json.dumps(j, ensure_ascii=False)[:200]
        res["coverage"][sym] = rec
        print(f"[cov] {sym:6s} {st} n={rec.get('n_first_page','-')} "
              f"oldest={rec.get('oldest_age_days','-')}d "
              f"perday={rec.get('msgs_per_day_est','-')} "
              f"sent={rec.get('sentiment_fill','-')}")
        time.sleep(SLEEP)

    # ---- Q2 深度 ----
    for sym in DEEP_TARGETS:
        pages, max_id, hit = [], None, None
        for p in range(MAX_PAGES):
            st, j, rl = get_page(sym, max_id)
            if st != 200:
                hit = {"page": p, "status": st,
                       "body": json.dumps(j, ensure_ascii=False)[:200],
                       "ratelimit": rl}
                break
            msgs = parse_msgs(j)
            if not msgs:
                hit = {"page": p, "status": 200, "body": "empty"}
                break
            pages.append({"page": p, "n": len(msgs),
                          "oldest": msgs[-1]["created_at"],
                          "oldest_age_days": age_days(msgs[-1]["created_at"])})
            max_id = msgs[-1]["id"]
            print(f"[deep] {sym} p{p} n={len(msgs)} "
                  f"oldest={pages[-1]['oldest_age_days']}d rl={rl}")
            time.sleep(SLEEP)
        res["depth"][sym] = {"pages": pages, "stopped": hit}

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"stocktwits_depth_{ts}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
