# -*- coding: utf-8 -*-
"""StockTwits 幸存者偏差专项探针（回测有效性的生死线）。

问题：13 只试金石里 FUST / SRGZ 返回 404 "Symbol not found"。
若 StockTwits 在退市/更名后**删除 symbol**，那么用它回测历史买点会
系统性丢掉「后来退市/归零」的那批票 —— 正是 bb 假阳最集中的一群，
回测结果会向上偏。这条不查清，整条通道的回测结论都不可信。

做法：拿一批**确知已退市/破产**的 ticker（含加 Q 后缀的破产代码）与
一批仍在交易的对照，看 StockTwits 是否仍保留其 symbol 与历史消息。
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-probe ufgtb0@proton.me"}
BASE = "https://api.stocktwits.com/api/2/streams/symbol/{}.json"

# 已退市/破产（历史上曾在 StockTwits 被热议）
DEAD = ["BBBYQ", "BBBY", "SIVBQ", "SIVB", "FRCB", "FRC", "WEWKQ", "WE",
        "SPRT", "MULN", "AMTD", "HTZGQ", "REVRQ", "TUEM", "ATERQ"]
# 试金石里 404 的两只
UNKNOWN = ["FUST", "SRGZ"]
# 对照：仍在交易
ALIVE = ["AAPL", "CATO", "WWR"]


def probe(sym):
    try:
        r = requests.get(BASE.format(sym), headers=UA,
                         params={"limit": 5}, timeout=20)
        j = r.json() if r.headers.get("Content-Type", "").startswith(
            "application/json") else {}
        rec = {"status": r.status_code}
        if r.status_code == 200:
            s = j.get("symbol") or {}
            ms = j.get("messages") or []
            rec.update({
                "title": s.get("title"), "exchange": s.get("exchange"),
                "watchlist": s.get("watchlist_count"),
                "n_msgs": len(ms),
                "newest": ms[0]["created_at"] if ms else None,
            })
            if ms:
                t = datetime.fromisoformat(ms[0]["created_at"].replace("Z", "+00:00"))
                rec["newest_age_days"] = round(
                    (datetime.now(timezone.utc) - t).total_seconds() / 86400, 1)
        else:
            rec["body"] = json.dumps(j, ensure_ascii=False)[:150]
        return rec
    except Exception as e:
        return {"status": None, "err": f"{type(e).__name__}"}


def main():
    res = {"meta": {"probed_at": datetime.now().isoformat(timespec="seconds")}}
    for group, syms in (("dead", DEAD), ("unknown_404", UNKNOWN), ("alive", ALIVE)):
        res[group] = {}
        for s in syms:
            rec = probe(s)
            res[group][s] = rec
            print(f"[{group:11s}] {s:6s} {rec.get('status')} "
                  f"title={str(rec.get('title'))[:28]:28s} "
                  f"exch={rec.get('exchange')} n={rec.get('n_msgs')} "
                  f"newest={rec.get('newest_age_days')}d")
            time.sleep(1.2)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"survivorship_{ts}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
