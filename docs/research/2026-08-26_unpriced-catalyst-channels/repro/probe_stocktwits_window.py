# -*- coding: utf-8 -*-
"""StockTwits 专项探针 2：限流阈值 + 能否精确回溯到 2025 买点窗。

三段：
  A. 限流 —— 无 key 连打，找 429 的阈值（决定回填 112 行买点的可行性）。
  B. 游标语义 —— message id 是否全局单调？能否当时间游标二分跳转
     （决定回溯成本是 O(density×days) 还是 O(log N)）。
  C. 密度对照 —— 11 只覆盖小票各自「买点前 7 天」窗口内的消息条数，
     与新闻源同窗口中位 1-2 条直接对照。

买点来自 2026-08-16 的 bb_v1 eval 样本（同一批 13 只 Finnhub 零新闻覆盖小票）。
"""
import json
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-probe ufgtb0@proton.me"}
BASE = "https://api.stocktwits.com/api/2/streams/symbol/{}.json"

BUYS = [("CATO", "2025-09-04"), ("FOCL", "2025-09-05"), ("HOWL", "2025-10-01"),
        ("BGDE", "2025-10-06"), ("WWR", "2025-10-06"), ("MTC", "2025-11-10"),
        ("LRDC", "2025-11-12"), ("COHN", "2025-11-14"), ("COBA", "2025-12-02"),
        ("CALC", "2025-12-03"), ("SPQS", "2025-12-12")]

CALLS = {"n": 0}


def get(sym, max_id=None, limit=30, retries=3):
    """带退避重试的 GET。StockTwits 限流表现为 TLS 层 EOF 而非 429，故须捕获异常。"""
    CALLS["n"] += 1
    params = {"limit": limit}
    if max_id is not None:
        params["max"] = max_id
    last = None
    for a in range(retries):
        try:
            r = requests.get(BASE.format(sym), headers=UA, params=params,
                             timeout=20)
            try:
                j = r.json()
            except Exception:
                j = {}
            return r.status_code, j, dict(r.headers)
        except Exception as e:
            last = f"{type(e).__name__}"
            time.sleep(2 ** a * 3)
    return -1, {"error": last}, {}


def msgs_of(j):
    out = []
    for m in j.get("messages", []) or []:
        s = (m.get("entities") or {}).get("sentiment") or {}
        out.append({"id": m["id"], "t": m["created_at"],
                    "s": s.get("basic") if isinstance(s, dict) else None})
    return out


def dt(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


# ---------------- A. 限流 ----------------
def sec_a():
    print("== A. 限流连打（无 sleep）==")
    log = []
    for i in range(60):
        st, j, h = get("AAPL", limit=2, retries=1)
        rl = {k: v for k, v in h.items()
              if "rate" in k.lower() or "retry" in k.lower()}
        log.append({"i": i, "status": st, "rl": rl})
        if st != 200:
            print(f"  第 {i+1} 次请求 -> {st} {rl} "
                  f"{json.dumps(j, ensure_ascii=False)[:120]}")
        time.sleep(0.2)
    fails = [x for x in log if x["status"] != 200]
    first_fail = fails[0]["i"] + 1 if fails else None
    print(f"  60 次 @0.2s 间隔：失败 {len(fails)} 次，首次失败在第 {first_fail} 次")
    time.sleep(20)
    return {"n_calls": 60, "interval_s": 0.2, "n_fail": len(fails),
            "first_fail_at": first_fail, "log": log}


# ---------------- B. 游标语义 ----------------
def bisect_to_date(sym, target, lo, hi, budget=16):
    """二分 max 游标，把 sym 的流定位到 target 日期附近。返回 (max_id, trace)。"""
    trace = []
    tgt = dt(target + "T23:59:59+00:00")
    best = hi
    for _ in range(budget):
        mid = (lo + hi) // 2
        st, j, _ = get(sym, mid, limit=5)
        if st != 200:
            trace.append({"mid": mid, "status": st})
            break
        ms = msgs_of(j)
        if not ms:
            hi = mid
            trace.append({"mid": mid, "n": 0})
            continue
        top = dt(ms[0]["t"])
        trace.append({"mid": mid, "top": ms[0]["t"]})
        if top > tgt:
            hi = mid
        else:
            lo, best = mid, mid
        if abs((top - tgt).total_seconds()) < 6 * 3600:
            break
        time.sleep(0.4)
    return best, trace


def sec_b():
    print("== B. 游标语义（全局 id 单调性 + 二分跳转）==")
    st, j, _ = get("AAPL", limit=1)
    hi = msgs_of(j)[0]["id"]
    print(f"  当前最大 id ≈ {hi}")
    # 用 AAPL（密集）标定 id->date 曲线的几个点
    cal = []
    for frac in (0.999, 0.99, 0.97, 0.95, 0.90, 0.80):
        mid = int(hi * frac)
        st, jj, _ = get("AAPL", mid, limit=1)
        ms = msgs_of(jj)
        cal.append({"frac": frac, "id": mid, "status": st,
                    "t": ms[0]["t"] if ms else None})
        print(f"  frac={frac} id={mid} -> {cal[-1]['t']}")
        time.sleep(0.4)
    # 跨 symbol 检验：把标定得到的老 id 用在小票上
    old_id = cal[-1]["id"]
    st, jj, _ = get("CATO", old_id, limit=5)
    ms = msgs_of(jj)
    cross = {"used_id": old_id, "status": st,
             "cato_top": ms[0]["t"] if ms else None}
    print(f"  跨 symbol：max={old_id} 用于 CATO -> {cross['cato_top']}")
    return {"max_id_now": hi, "calibration": cal, "cross_symbol": cross}


# ---------------- C. 买点窗密度 ----------------
def sec_c(max_id_now):
    print("== C. 买点前 7 天窗口内消息条数 ==")
    out = {}
    for sym, buy in BUYS:
        t0 = time.time()
        land, trace = bisect_to_date(sym, buy, int(max_id_now * 0.5), max_id_now)
        lo_t = dt(buy + "T00:00:00+00:00") - timedelta(days=7)
        hi_t = dt(buy + "T23:59:59+00:00")
        cur, got, pages = land, [], 0
        while pages < 25:
            st, j, _ = get(sym, cur, limit=30)
            if st != 200:
                break
            ms = msgs_of(j)
            if not ms:
                break
            pages += 1
            for m in ms:
                if lo_t <= dt(m["t"]) <= hi_t:
                    got.append(m)
            if dt(ms[-1]["t"]) < lo_t:
                break
            cur = ms[-1]["id"]
            time.sleep(0.4)
        out[sym] = {"buy": buy, "n_in_window": len(got), "pages_used": pages,
                    "bisect_calls": len(trace), "secs": round(time.time() - t0, 1),
                    "sentiment": dict(Counter(m["s"] or "none" for m in got)),
                    "landed_trace_tail": trace[-2:]}
        print(f"  {sym:5s} buy={buy} 窗内 {len(got):4d} 条 "
              f"(二分 {len(trace)} + 翻页 {pages} 次, {out[sym]['secs']}s) "
              f"{out[sym]['sentiment']}")
        time.sleep(0.5)
    return out


def main():
    res = {"meta": {"probed_at": datetime.now().isoformat(timespec="seconds")}}
    res["A_ratelimit"] = sec_a()
    res["B_cursor"] = sec_b()
    res["C_window_density"] = sec_c(res["B_cursor"]["max_id_now"])
    res["meta"]["total_calls"] = CALLS["n"]
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"stocktwits_window_{ts}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"\n总调用 {CALLS['n']} 次 -> {out}")


if __name__ == "__main__":
    main()
