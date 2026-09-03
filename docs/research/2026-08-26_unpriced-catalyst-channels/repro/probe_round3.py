# -*- coding: utf-8 -*-
"""第三轮：幸存者偏差 + 「窗内 0 条」复核（用全局 id 标定直接跳转，不再二分）。

背景：round2 的 C 段对稀疏票二分不收敛（BGDE 用满 16 次预算 + 翻 25 页仍 0 条），
所以「0 条」可能是探针失败的假 0。这里改用**全局 id↔日期标定表**线性插值直接落点，
并把窗口放宽到 ±45 天，用来区分「那段时间真没人讨论」vs「探针没落对地方」。

同时测幸存者偏差：退市/破产票的 symbol 是否还在（决定能否无偏回测）。
"""
import json
import time
from bisect import bisect_left
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-probe ufgtb0@proton.me"}
BASE = "https://api.stocktwits.com/api/2/streams/symbol/{}.json"

# 来自 stocktwits_window_20260826-054745.json 的 B 段标定（AAPL 密集流，误差 < 数分钟）
ANCHORS = [
    (530290374, "2023-06-01T18:25:52Z"),
    (596576671, "2024-12-16T10:47:21Z"),
    (629719819, "2025-09-23T19:06:14Z"),
    (642977078, "2026-01-27T10:33:38Z"),
    (656234338, "2026-06-12T09:02:45Z"),
    (662200105, "2026-08-18T18:07:00Z"),
]
A_IDS = [a[0] for a in ANCHORS]
A_TS = [datetime.fromisoformat(a[1].replace("Z", "+00:00")).timestamp()
        for a in ANCHORS]

DEAD = ["BBBYQ", "SIVBQ", "FRCB", "WEWKQ", "SPRT", "HTZGQ", "ATERQ", "TUEM",
        "MULN", "AMTD"]
UNKNOWN = ["FUST", "SRGZ"]
ZERO_CASES = [("FOCL", "2025-09-05"), ("BGDE", "2025-10-06"), ("COBA", "2025-12-02")]


def id_for(date_str: str) -> int:
    """按标定表线性插值：日期 -> 全局 message id。"""
    t = datetime.fromisoformat(date_str + "T23:59:59+00:00").timestamp()
    k = bisect_left(A_TS, t)
    if k <= 0:
        return A_IDS[0]
    if k >= len(A_TS):
        return A_IDS[-1]
    f = (t - A_TS[k - 1]) / (A_TS[k] - A_TS[k - 1])
    return int(A_IDS[k - 1] + f * (A_IDS[k] - A_IDS[k - 1]))


def get(sym, max_id=None, limit=30):
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


def collect(sym, start, end, max_pages=40):
    """收集 [start, end] 区间内的全部消息（从 end 之后落点往回翻）。"""
    cur = id_for(end)
    lo, hi = dt(start + "T00:00:00+00:00"), dt(end + "T23:59:59+00:00")
    got, pages, trace = [], 0, []
    while pages < max_pages:
        st, j = get(sym, cur, limit=30)
        if st != 200:
            trace.append({"status": st})
            break
        ms = msgs_of(j)
        if not ms:
            trace.append({"empty_at": cur})
            break
        pages += 1
        trace.append({"page": pages, "top": ms[0]["t"], "bot": ms[-1]["t"]})
        got += [m for m in ms if lo <= dt(m["t"]) <= hi]
        if dt(ms[-1]["t"]) < lo:
            break
        cur = ms[-1]["id"]
        time.sleep(0.3)
    return got, pages, trace


def main():
    res = {"meta": {"probed_at": datetime.now().isoformat(timespec="seconds")}}

    print("== A. 幸存者偏差：退市/破产票 symbol 是否保留 ==")
    res["survivorship"] = {}
    for grp, syms in (("dead", DEAD), ("unknown404", UNKNOWN)):
        res["survivorship"][grp] = {}
        for s in syms:
            st, j = get(s, limit=3)
            rec = {"status": st}
            if st == 200:
                sy = j.get("symbol") or {}
                ms = msgs_of(j)
                rec.update({"title": sy.get("title"), "exch": sy.get("exchange"),
                            "watchlist": sy.get("watchlist_count"),
                            "newest": ms[0]["t"] if ms else None})
            else:
                rec["body"] = json.dumps(j, ensure_ascii=False)[:120]
            res["survivorship"][grp][s] = rec
            print(f"  [{grp:10s}] {s:6s} {st} {str(rec.get('title'))[:30]:30s} "
                  f"exch={rec.get('exch')} newest={rec.get('newest')}")
            time.sleep(0.8)

    print("\n== B. 退市票的历史消息是否可回溯（取其停牌前一年的窗口）==")
    res["dead_history"] = {}
    for s, win in [("BBBYQ", ("2023-04-01", "2023-04-30")),
                   ("SIVBQ", ("2023-03-01", "2023-03-31")),
                   ("SPRT", ("2021-08-20", "2021-08-31"))]:
        if res["survivorship"]["dead"].get(s, {}).get("status") != 200:
            print(f"  {s}: symbol 不存在，跳过")
            continue
        got, pages, trace = collect(s, win[0], win[1], max_pages=6)
        res["dead_history"][s] = {"window": win, "n": len(got), "pages": pages,
                                  "trace_head": trace[:2]}
        print(f"  {s} {win}: {len(got)} 条 (翻 {pages} 页)")
        time.sleep(0.8)

    print("\n== C. 「窗内 0 条」复核（标定跳转 + 放宽到 ±45 天）==")
    res["zero_recheck"] = {}
    for sym, buy in ZERO_CASES:
        b = datetime.strptime(buy, "%Y-%m-%d")
        narrow = ((b - timedelta(days=7)).strftime("%Y-%m-%d"), buy)
        wide = ((b - timedelta(days=45)).strftime("%Y-%m-%d"),
                (b + timedelta(days=45)).strftime("%Y-%m-%d"))
        g1, p1, t1 = collect(sym, *narrow, max_pages=8)
        time.sleep(0.5)
        g2, p2, t2 = collect(sym, *wide, max_pages=15)
        res["zero_recheck"][sym] = {
            "narrow": {"win": narrow, "n": len(g1), "pages": p1,
                       "trace_head": t1[:2]},
            "wide": {"win": wide, "n": len(g2), "pages": p2,
                     "sent": dict(Counter(m["s"] or "none" for m in g2)),
                     "trace_head": t2[:2]}}
        print(f"  {sym}: 7天窗 {len(g1)} 条 / ±45天窗 {len(g2)} 条 "
              f"(landing top={t2[0].get('top') if t2 else '-'})")
        time.sleep(0.8)

    print("\n== D. 标定跳转的落点精度校验（对 3 只覆盖票复算 7 天窗，与二分法对照）==")
    res["calib_check"] = {}
    for sym, buy, ref in [("WWR", "2025-10-06", 106), ("HOWL", "2025-10-01", 24),
                          ("CATO", "2025-09-04", 1)]:
        b = datetime.strptime(buy, "%Y-%m-%d")
        got, pages, trace = collect(
            sym, (b - timedelta(days=7)).strftime("%Y-%m-%d"), buy, max_pages=12)
        res["calib_check"][sym] = {"n": len(got), "ref_bisect": ref,
                                   "pages": pages, "calls": pages}
        print(f"  {sym}: 标定法 {len(got)} 条 vs 二分法 {ref} 条 (翻 {pages} 页)")
        time.sleep(0.8)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"round3_{ts}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
