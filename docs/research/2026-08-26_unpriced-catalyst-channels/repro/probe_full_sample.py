# -*- coding: utf-8 -*-
"""全样本实测：StockTwits 在 bb_v1 **全部 210 个买点**上的覆盖率 / 密度 / 极性分布。

前面几轮用的是 13 只「新闻零覆盖微盘」—— 那是刻意挑的最难人群，
覆盖率会被低估，也不能代表实际要过闸的总体。这一轮换成**真实总体**：
`outputs/path2_eval/bb_v1_eval_20260810-235006.json` 的 210 行 (symbol, buy_date)。

同时量化两件红队一定会问的事：
  - **幸存者偏差的量级**：210 行里有多少 symbol 已经 404（= 回测时会被静默丢掉）；
  - **极性作用面**：Bearish 占比是多少（对照新闻通道的负向率 4.5%）。

只读主目录的 eval JSON，不写任何主目录文件。
"""
import json
import statistics
import time
from bisect import bisect_left
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent
EVAL = Path("/home/yu/PycharmProjects/Trade_Strategy/outputs/path2_eval/"
            "bb_v1_eval_20260810-235006.json")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-probe ufgtb0@proton.me"}
BASE = "https://api.stocktwits.com/api/2/streams/symbol/{}.json"
SLEEP = 0.35
WIN_DAYS = 7          # 买点前 7 天，与新闻通道口径一致
LAND_BUFFER = 5       # 落点后移，修正 round3 D 段发现的系统性少计

# 全局 id↔日期标定（AAPL 密集流实测，probe_stocktwits_window B 段 + probe_depth_ext）
ANCHORS = [
    (13257282, "2013-04-26T18:29:14Z"), (66286410, "2016-11-04T03:22:40Z"),
    (132572821, "2018-08-03T15:48:20Z"), (198859231, "2020-03-07T21:20:51Z"),
    (265145642, "2020-12-17T18:18:09Z"), (331432052, "2021-05-17T16:54:41Z"),
    (397718463, "2021-10-28T22:17:00Z"), (464004873, "2022-06-04T19:35:37Z"),
    (530290374, "2023-06-01T18:25:52Z"), (596576671, "2024-12-16T10:47:21Z"),
    (629719819, "2025-09-23T19:06:14Z"), (642977078, "2026-01-27T10:33:38Z"),
    (656234338, "2026-06-12T09:02:45Z"), (662200105, "2026-08-18T18:07:00Z"),
]
A_ID = [a[0] for a in ANCHORS]
A_TS = [datetime.fromisoformat(a[1].replace("Z", "+00:00")).timestamp()
        for a in ANCHORS]
CALLS = {"n": 0}


def id_for(when: datetime) -> int:
    t = when.timestamp()
    k = bisect_left(A_TS, t)
    if k <= 0:
        return A_ID[0]
    if k >= len(A_TS):
        return A_ID[-1]
    f = (t - A_TS[k - 1]) / (A_TS[k] - A_TS[k - 1])
    return int(A_ID[k - 1] + f * (A_ID[k] - A_ID[k - 1]))


def get(sym, max_id=None, limit=30):
    CALLS["n"] += 1
    for a in range(3):
        try:
            p = {"limit": limit}
            if max_id is not None:
                p["max"] = max_id
            r = requests.get(BASE.format(sym), headers=UA, params=p, timeout=20)
            return r.status_code, (r.json() if r.text.startswith("{") else {})
        except Exception:
            time.sleep(2 ** a * 2)
    return -1, {}


def msgs_of(j):
    out = []
    for m in j.get("messages", []) or []:
        s = (m.get("entities") or {}).get("sentiment") or {}
        out.append({"id": m["id"], "t": m["created_at"],
                    "s": s.get("basic") if isinstance(s, dict) else None})
    return out


def dt(x):
    return datetime.fromisoformat(x.replace("Z", "+00:00"))


def main():
    rows = json.loads(EVAL.read_text())["results"]
    pairs = [(r["symbol"], r["buy_date"]) for r in rows]
    syms = sorted({s for s, _ in pairs})
    print(f"样本：{len(pairs)} 个买点 / {len(syms)} 只 unique symbol")

    # ---- 第一步：symbol 存活性（幸存者偏差量级）----
    alive = {}
    for s in syms:
        st, j = get(s, limit=1)
        sy = j.get("symbol") or {}
        alive[s] = {"status": st, "title": sy.get("title"),
                    "exchange": sy.get("exchange"),
                    "watchlist": sy.get("watchlist_count")}
        time.sleep(SLEEP)
    n_alive = sum(1 for v in alive.values() if v["status"] == 200)
    dead_syms = sorted(s for s, v in alive.items() if v["status"] != 200)
    dead_rows = sum(1 for s, _ in pairs if alive[s]["status"] != 200)
    print(f"symbol 存活 {n_alive}/{len(syms)}；"
          f"受影响买点 {dead_rows}/{len(pairs)} "
          f"({dead_rows/len(pairs)*100:.1f}%)")
    print(f"404 名单: {dead_syms}")

    # ---- 第二步：逐买点取窗内消息 ----
    per_row = []
    for i, (sym, buy) in enumerate(pairs):
        if alive[sym]["status"] != 200:
            per_row.append({"symbol": sym, "buy": buy, "symbol_404": True})
            continue
        b = datetime.fromisoformat(buy + "T23:59:59+00:00")
        lo = b - timedelta(days=WIN_DAYS)
        cur = id_for(b + timedelta(days=LAND_BUFFER))
        got, pages = [], 0
        while pages < 12:
            st, j = get(sym, cur, limit=30)
            if st != 200:
                break
            ms = msgs_of(j)
            if not ms:
                break
            pages += 1
            got += [m for m in ms if lo <= dt(m["t"]) <= b]
            if dt(ms[-1]["t"]) < lo:
                break
            cur = ms[-1]["id"]
            time.sleep(SLEEP)
        sent = Counter(m["s"] or "none" for m in got)
        per_row.append({"symbol": sym, "buy": buy, "symbol_404": False,
                        "n": len(got), "pages": pages, "sent": dict(sent)})
        if i % 20 == 0:
            print(f"  [{i}/{len(pairs)}] {sym} {buy} -> {len(got)} 条 "
                  f"(累计调用 {CALLS['n']})")
        time.sleep(SLEEP)

    # ---- 汇总 ----
    ok = [r for r in per_row if not r["symbol_404"]]
    ns = [r["n"] for r in ok]
    nz = [n for n in ns if n > 0]
    tot = Counter()
    for r in ok:
        tot.update(r["sent"])
    tagged = tot["Bullish"] + tot["Bearish"]
    summary = {
        "n_buypoints": len(pairs), "n_unique_symbols": len(syms),
        "symbol_alive": n_alive, "symbol_404": len(dead_syms),
        "dead_symbols": dead_syms,
        "buypoints_lost_to_404": dead_rows,
        "buypoints_lost_pct": round(dead_rows / len(pairs) * 100, 1),
        "coverage_nonzero": len(nz),
        "coverage_pct_of_all": round(len(nz) / len(pairs) * 100, 1),
        "coverage_pct_of_alive": round(len(nz) / max(len(ok), 1) * 100, 1),
        "msgs_median_all": statistics.median(ns) if ns else None,
        "msgs_median_nonzero": statistics.median(nz) if nz else None,
        "msgs_mean": round(statistics.mean(ns), 1) if ns else None,
        "msgs_max": max(ns) if ns else None,
        "msgs_p90": (statistics.quantiles(ns, n=10)[8] if len(ns) > 10 else None),
        "sentiment_total": dict(tot),
        "bearish_share_of_tagged": (round(tot["Bearish"] / tagged * 100, 1)
                                    if tagged else None),
        "tagged_share": (round(tagged / sum(tot.values()) * 100, 1)
                         if tot else None),
        "total_calls": CALLS["n"],
    }
    print("\n=== 汇总 ===")
    for k, v in summary.items():
        if k != "dead_symbols":
            print(f"  {k}: {v}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"full_sample_{ts}.json"
    out.write_text(json.dumps(
        {"summary": summary, "alive": alive, "per_row": per_row},
        ensure_ascii=False, indent=1))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
