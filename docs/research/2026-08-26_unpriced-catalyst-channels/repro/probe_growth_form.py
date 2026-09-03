"""增速函数形式对比探针：比值形式 vs 对称形式，在 bb 微盘票池上的可算性差异。

动机（实测驱动）：analyze_financial_series 显示 11 行的营收 YoY 因「去年同期 = 0」而
定义爆炸（prev_zero），而「0 → 有营收」恰恰是最强的未兑现利好之一。
比值形式 (x_t - x_{t-4}) / |x_{t-4}| 在微盘票池上是错误的函数形式。

对称形式：  D(x_t, x_{t-4}) = (x_t - x_{t-4}) / (|x_t| + |x_{t-4}|)  ∈ [-1, 1]
  · 分母恒 >= |分子|，永不爆炸；只在两期全 0 时无定义
  · 对负基数（净利润、经营现金流）符号语义正确：亏损收窄 -> 正值
  · 单调：改善越多值越大；饱和：从 0 起步 = +1（真的是最强改善）

本探针同时测：TTM（近四季滚动）回退——解决只报年度的 10-K/20-F 申报人。
"""
from __future__ import annotations

import json
import statistics as st
from collections import Counter
from datetime import date, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
CACHE = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-news"
             "/123cb8f3-70f2-4818-9f90-29de07c28fca/scratchpad/companyfacts")
REPO = OUT.parents[3]

CHAINS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "gross_profit": ["GrossProfit"],
    "rnd": ["ResearchAndDevelopmentExpense"],
}


def d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def series(facts, chain, asof, lo, hi):
    gaap = facts.get("facts", {}).get("us-gaap", {})
    best = {}
    for tag in chain:
        node = gaap.get(tag)
        if not node:
            continue
        for rows in node.get("units", {}).values():
            for r in rows:
                if not r.get("start") or not r.get("end") or r.get("val") is None:
                    continue
                f = d(r["filed"])
                if f > asof:
                    continue
                s0, e0 = d(r["start"]), d(r["end"])
                if not (lo <= (e0 - s0).days <= hi):
                    continue
                k = (s0, e0)
                if k not in best or f < best[k][1]:
                    best[k] = (float(r["val"]), f)
        if best:
            break
    return sorted([(k[1], v[0], v[1]) for k, v in best.items()])


def sym(a, b):
    """对称增速 D(cur, prev)。两期全 0 -> None。"""
    den = abs(a) + abs(b)
    return None if den == 0 else (a - b) / den


def ratio(a, b):
    return None if b == 0 else (a - b) / abs(b)


def pair_yoy(q):
    """(cur, prev) 同比配对：end 相差 330~400 天。"""
    if len(q) < 2:
        return None
    cur = q[-1]
    for prev in reversed(q[:-1]):
        if 330 <= (cur[0] - prev[0]).days <= 400:
            return cur[1], prev[1]
    return None


def ttm(q, asof_end):
    """近四季滚动求和；要求四个季度 end 覆盖 ~360 天且无缺口。"""
    sel = [x for x in q if x[0] <= asof_end]
    if len(sel) < 4:
        return None
    last4 = sel[-4:]
    if not (330 <= (last4[-1][0] - last4[0][0]).days <= 400):
        return None
    return sum(x[1] for x in last4), last4[-1][0]


def main() -> None:
    scores = json.loads((REPO / "docs/research/2026-08-16_news-sentiment-path2-integration"
                                "/repro/full_scores_20260816-193559.json").read_text())
    cikmap_raw = json.loads((REPO / "cache/news_sentiment/ticker_cik.json").read_text())
    cikmap = {v["ticker"].upper(): int(v["cik_str"]) for v in cikmap_raw.values()}

    n = len(scores)
    cnt = Counter()
    vals: dict[str, list[float]] = {}
    for r in scores:
        sym_, bd = r["symbol"], d(r["buy_date"])
        cik = cikmap.get(sym_.upper())
        p = CACHE / f"CIK{cik:010d}.json" if cik else None
        if not p or not p.exists():
            continue
        txt = p.read_text()
        if txt.strip() == "null":
            continue
        facts = json.loads(txt)
        for name, chain in CHAINS.items():
            q = series(facts, chain, bd, 80, 100)
            a = series(facts, chain, bd, 350, 380)
            pr = pair_yoy(q)
            if pr:
                cnt[f"{name}:季度配对成功"] += 1
                if ratio(*pr) is not None:
                    cnt[f"{name}:比值形式可算"] += 1
                    vals.setdefault(f"{name}:ratio", []).append(ratio(*pr))
                s = sym(*pr)
                if s is not None:
                    cnt[f"{name}:对称形式可算"] += 1
                    vals.setdefault(f"{name}:sym", []).append(s)
            else:
                # TTM 回退（用季度补齐），再退年度
                t_now = ttm(q, q[-1][0]) if q else None
                t_old = None
                if t_now:
                    tgt = t_now[1]
                    prevq = [x for x in q if 330 <= (tgt - x[0]).days <= 400]
                    if prevq:
                        t_old = ttm(q, prevq[-1][0])
                if t_now and t_old:
                    cnt[f"{name}:TTM 回退成功"] += 1
                    s = sym(t_now[0], t_old[0])
                    if s is not None:
                        cnt[f"{name}:对称形式可算"] += 1
                        vals.setdefault(f"{name}:sym", []).append(s)
                else:
                    pa = pair_yoy(a)
                    if pa:
                        cnt[f"{name}:年度回退成功"] += 1
                        s = sym(*pa)
                        if s is not None:
                            cnt[f"{name}:对称形式可算"] += 1
                            vals.setdefault(f"{name}:sym", []).append(s)

    print(f"分母 = {n} 行 bb 买点\n")
    print("[G] 函数形式 × 回退链的可算性（对称形式 = 本探针推荐）")
    for name in CHAINS:
        keys = [f"{name}:季度配对成功", f"{name}:比值形式可算", f"{name}:TTM 回退成功",
                f"{name}:年度回退成功", f"{name}:对称形式可算"]
        print(f"  {name}")
        for k in keys:
            v = cnt.get(k, 0)
            print(f"    {k.split(':')[1]:16s} {v:3d}/{n} = {v/n:6.1%}")

    print("\n[H] 对称增速分布（[-1,1]，与 outcome 无关）")
    for k in sorted(vals):
        v = sorted(vals[k])
        if len(v) < 5:
            continue
        q = st.quantiles(v, n=4)
        print(f"  {k:22s} n={len(v):3d} q10={v[len(v)//10]:7.3f} q25={q[0]:7.3f} "
              f"med={st.median(v):7.3f} q75={q[2]:7.3f} q90={v[9*len(v)//10]:7.3f}")
    # 比值形式的爆炸程度
    rr = vals.get("revenue:ratio", [])
    if rr:
        print(f"\n  比值形式营收 YoY: max={max(rr):.1f} min={min(rr):.1f} "
              f"|值|>5 的行数 {sum(1 for x in rr if abs(x)>5)}/{len(rr)}"
              "  ← 长尾爆炸，任何均值/回归都会被少数行主导")


if __name__ == "__main__":
    main()
