"""两件事，均由 Falsifier 红队意见触发：

(1) **重述取值规则**。我原先取「filed ≤ t 中 filed 最早」（= 原始申报值），
    Falsifier 指出应取「filed ≤ t 中 filed 最晚」（= 决策时点上真正能看到的最新值）。
    本探针把两种规则都跑一遍，量化差异：受影响的行数、值的相对偏离、覆盖率是否变化。

(2) **净利润的第三种表示：ΔROA = NI_t/Assets_t − NI_{t-4}/Assets_{t-4}**。
    Falsifier 主张净利润增长率应排除（0 附近发散），我主张对称形式已修好发散；
    但对称形式对「亏转盈」会饱和到 +1、丢失强弱。ROA 的分母（总资产）恒 > 0，
    既不发散也不饱和，且天然 size-normalized。测它的可算率与分布。
"""
from __future__ import annotations

import json
import statistics as st
from datetime import date, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
CACHE = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-news"
             "/123cb8f3-70f2-4818-9f90-29de07c28fca/scratchpad/companyfacts")
REPO = OUT.parents[3]

REV = ["RevenueFromContractWithCustomerExcludingAssessedTax",
       "RevenueFromContractWithCustomerIncludingAssessedTax",
       "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"]
NI = ["NetIncomeLoss", "ProfitLoss"]
ASSETS = ["Assets"]


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def dur(facts, chain, asof, lo, hi, rule):
    """rule: 'first' = filed 最早（原始申报值） · 'last' = filed 最晚（决策时可见的最新值）。"""
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
                if k not in best:
                    best[k] = (float(r["val"]), f)
                else:
                    better = f < best[k][1] if rule == "first" else f > best[k][1]
                    if better:
                        best[k] = (float(r["val"]), f)
        if best:
            break
    return sorted([(k[1], v[0], v[1]) for k, v in best.items()])


def inst(facts, chain, asof, rule):
    gaap = facts.get("facts", {}).get("us-gaap", {})
    best = {}
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
                if e0 not in best:
                    best[e0] = (float(r["val"]), f)
                else:
                    better = f < best[e0][1] if rule == "first" else f > best[e0][1]
                    if better:
                        best[e0] = (float(r["val"]), f)
        if best:
            break
    return dict(sorted(best.items()))


def pair(q):
    if len(q) < 2:
        return None
    cur = q[-1]
    for prev in reversed(q[:-1]):
        if 330 <= (cur[0] - prev[0]).days <= 400:
            return cur, prev
    return None


def symd(a, b):
    den = abs(a) + abs(b)
    return None if den == 0 else (a - b) / den


def main() -> None:
    scores = json.loads((REPO / "docs/research/2026-08-16_news-sentiment-path2-integration"
                                "/repro/full_scores_20260816-193559.json").read_text())
    cm = {v["ticker"].upper(): int(v["cik_str"])
          for v in json.loads((REPO / "cache/news_sentiment/ticker_cik.json").read_text()).values()}

    diff_rows, rel = [], []
    cov = {"first": 0, "last": 0}
    roa_vals, roa_rows = [], 0
    ni_sym_first, ni_sym_last = [], []
    n = len(scores)
    for r in scores:
        cik = cm.get(r["symbol"].upper())
        p = CACHE / f"CIK{cik:010d}.json" if cik else None
        if not p or not p.exists() or p.read_text().strip() == "null":
            continue
        facts = json.loads(p.read_text())
        bd = d(r["buy_date"])
        for rule, sink in (("first", ni_sym_first), ("last", ni_sym_last)):
            q = dur(facts, REV, bd, 80, 100, rule)
            pr = pair(q)
            if pr:
                cov[rule] += 1
            qn = dur(facts, NI, bd, 80, 100, rule)
            pn = pair(qn)
            if pn:
                v = symd(pn[0][1], pn[1][1])
                if v is not None:
                    sink.append(v)
        # 差异量化：营收最新季度值
        qf = dur(facts, REV, bd, 80, 100, "first")
        ql = dur(facts, REV, bd, 80, 100, "last")
        if qf and ql and qf[-1][0] == ql[-1][0]:
            a, b = qf[-1][1], ql[-1][1]
            if a != b:
                diff_rows.append((r["symbol"], r["buy_date"], a, b))
                if abs(a) > 0:
                    rel.append(abs(b - a) / abs(a))
        # ΔROA
        qn = dur(facts, NI, bd, 80, 100, "last")
        pn = pair(qn)
        A = inst(facts, ASSETS, bd, "last")
        if pn and A:
            e_cur, e_prev = pn[0][0], pn[1][0]
            a_cur = A.get(e_cur)[0] if A.get(e_cur) else None
            a_prev = A.get(e_prev)[0] if A.get(e_prev) else None
            if a_cur and a_prev and a_cur > 0 and a_prev > 0:
                roa_rows += 1
                roa_vals.append(pn[0][1] / a_cur - pn[1][1] / a_prev)

    print(f"分母 {n} 行\n")
    print("[M] 重述取值规则的实际影响")
    print(f"  营收 YoY 可配对行数：first={cov['first']}  last={cov['last']}  "
          f"⟹ 覆盖率{'不变' if cov['first']==cov['last'] else '有变化'}")
    print(f"  最新季度营收值在两规则下不同的行数：{len(diff_rows)}/{n}")
    if rel:
        print(f"  相对偏离 |last-first|/|first|: med={st.median(rel):.4f} max={max(rel):.4f}")
        for x in diff_rows[:6]:
            print(f"    {x[0]:8s} {x[1]}  first={x[2]:,.0f}  last={x[3]:,.0f}")
    print(f"  净利润对称增速分布 first: n={len(ni_sym_first)} med={st.median(ni_sym_first):.4f}"
          if ni_sym_first else "")
    print(f"  净利润对称增速分布 last : n={len(ni_sym_last)} med={st.median(ni_sym_last):.4f}"
          if ni_sym_last else "")

    print(f"\n[N] ΔROA（净利/总资产 的同比变化，分母恒 >0）")
    print(f"  可算 {roa_rows}/{n} = {roa_rows/n:.1%}")
    if roa_vals:
        v = sorted(roa_vals)
        q = st.quantiles(v, n=4)
        print(f"  分布 q10={v[len(v)//10]:.4f} q25={q[0]:.4f} med={st.median(v):.4f} "
              f"q75={q[2]:.4f} q90={v[9*len(v)//10]:.4f}  min={v[0]:.3f} max={v[-1]:.3f}")
        print(f"  |ΔROA| > 1 的行数（即变化超过总资产的 100%）：{sum(1 for x in v if abs(x)>1)}")


if __name__ == "__main__":
    main()
