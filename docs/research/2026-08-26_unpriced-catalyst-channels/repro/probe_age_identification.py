"""「财报账龄」能否作为准实验识别源？—— 自我证伪探针。

我在初稿 §6.3 提出「效应随账龄单调衰减 = 准实验证据」。我自己给它写了两条反驳，
其中一条（日历共线）可以用手上的数据直接检验：

  反驳 b：账龄可能只是日历位置的确定性函数（买点集中落在财报季后一个月），
          那么账龄剖面 = 日历效应，不是 PEAD。

检验思路：财政年度结束月（fiscalYearEnd）在公司间是异质的（12 月底占多数，但有
3/6/9 月等）。**在同一个日历周内、跨不同公司，账龄仍有多大离散度？**
若离散度大 ⟹ 账龄含日历之外的外生变异（来自财年异质性）⟹ 识别源成立。
若离散度≈0 ⟹ 账龄 ≡ 日历，反驳 b 成立，§6.3 的设计要废。

同时量化：账龄的总方差里，日历（buy_date 所在周）能解释多少。
"""
from __future__ import annotations

import json
import statistics as st
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
RAW = sorted(OUT.glob("xbrl_coverage_*.json"))[-1]
SCORES = (OUT.parents[1] / "2026-08-16_news-sentiment-path2-integration"
          / "repro" / "full_scores_20260816-193559.json")


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    raw = json.loads(RAW.read_text())["by_symbol"]
    scores = json.loads(SCORES.read_text())

    recs = []
    for r in scores:
        sym, bd = r["symbol"], d(r["buy_date"])
        sub = raw.get(sym, {}).get("submissions") or {}
        cands = [x for x in (sub.get("all_10Q_dates", []) + sub.get("all_10K_dates", []))
                 if d(x) <= bd]
        if not cands:
            continue
        last = max(cands, key=d)
        recs.append({"symbol": sym, "buy_date": bd, "age": (bd - d(last)).days,
                     "fye": sub.get("fiscalYearEnd"), "week": bd.isocalendar()[:2]})

    n = len(recs)
    ages = [r["age"] for r in recs]
    print(f"n = {n} 行有账龄\n")

    # --- 1. 财年结束月的异质性 ---
    fye = Counter(r["fye"] for r in recs)
    print("[1] fiscalYearEnd 分布（MMDD）:")
    for k, v in fye.most_common():
        print(f"    {k}: {v}")
    non_dec = sum(v for k, v in fye.items() if k and not str(k).startswith("12"))
    print(f"    非 12 月财年结束的行: {non_dec}/{n} = {non_dec/n:.1%}")

    # --- 2. 同一日历周内的账龄离散度 ---
    byweek = defaultdict(list)
    for r in recs:
        byweek[r["week"]].append(r["age"])
    multi = {k: v for k, v in byweek.items() if len(v) >= 3}
    print(f"\n[2] 含 >=3 行的日历周: {len(multi)} 个")
    spreads = []
    for k in sorted(multi):
        v = sorted(multi[k])
        sp = max(v) - min(v)
        spreads.append(sp)
        print(f"    {k[0]}-W{k[1]:02d} n={len(v):2d} 账龄 min={min(v):3d} med={st.median(v):5.0f} "
              f"max={max(v):4d} 极差={sp:4d}")
    if spreads:
        print(f"    周内极差中位 = {st.median(spreads):.0f} 日")

    # --- 3. 方差分解：日历周能解释账龄多少方差 ---
    grand = st.mean(ages)
    ss_tot = sum((a - grand) ** 2 for a in ages)
    ss_between = 0.0
    for k, v in byweek.items():
        m = st.mean(v)
        ss_between += len(v) * (m - grand) ** 2
    r2 = ss_between / ss_tot if ss_tot else float("nan")
    print(f"\n[3] 账龄方差分解（以日历周为因子）: R² = {r2:.3f}"
          f"  ⟹ 日历之外的变异占 {1-r2:.1%}")
    # 去掉超长尾（>180 日的延迟申报人）再算一次
    core = [r for r in recs if r["age"] <= 180]
    ac = [r["age"] for r in core]
    g2 = st.mean(ac)
    sst = sum((a - g2) ** 2 for a in ac)
    bw2 = defaultdict(list)
    for r in core:
        bw2[r["week"]].append(r["age"])
    ssb = sum(len(v) * (st.mean(v) - g2) ** 2 for v in bw2.values())
    print(f"    仅账龄<=180 日（n={len(ac)}）: R² = {ssb/sst:.3f} "
          f"⟹ 日历之外的变异占 {1-ssb/sst:.1%}")

    # --- 4. 账龄与 buy_date 在日历上的关系（看是否单调） ---
    print("\n[4] 按 buy_date 月份看账龄中位（若账龄≡日历，应呈锯齿状严格规律）")
    bymon = defaultdict(list)
    for r in recs:
        bymon[(r["buy_date"].year, r["buy_date"].month)].append(r["age"])
    for k in sorted(bymon):
        v = bymon[k]
        print(f"    {k[0]}-{k[1]:02d} n={len(v):3d} 账龄 q25={st.quantiles(v,n=4)[0]:5.0f} "
              f"med={st.median(v):5.0f} q75={st.quantiles(v,n=4)[2]:5.0f}")


if __name__ == "__main__":
    main()
