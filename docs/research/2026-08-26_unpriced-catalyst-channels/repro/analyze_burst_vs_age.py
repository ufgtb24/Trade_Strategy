"""反驳 a 的裁定：财报账龄 vs「距 burst 起点的形态进展」。

输入：
  burst_start_*.json          本次重扫得到的 bb_v1 match（含 burst/tb 的 bar 索引与日期）
  xbrl_coverage_*.json        各票的 10-Q/10-K 申报日流水
输出：
  · bars_since_burst_start 的分布（形态进展的实际跨度）
  · Spearman(账龄, bars_since_burst_start)
  · 账龄方差中被形态进展解释的比例
  · 两个样本上各算一遍：exact-overlap（与原 112 行精确对上的行）与 full-rerun
"""
from __future__ import annotations

import json
import statistics as st
from datetime import date, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
BURST = sorted(OUT.glob("burst_start_*.json"))[-1]
COV = sorted(OUT.glob("xbrl_coverage_*.json"))[-1]
SCORES = (OUT.parents[1] / "2026-08-16_news-sentiment-path2-integration"
          / "repro" / "full_scores_20260816-193559.json")


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def spearman(xs, ys):
    n = len(xs)
    if n < 4:
        return float("nan")
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else float("nan")


def r2_by_factor(vals, groups):
    """以离散因子解释的方差比例（同 probe_age_identification 的口径）。"""
    if len(vals) < 4:
        return float("nan")
    grand = st.mean(vals)
    sst = sum((v - grand) ** 2 for v in vals)
    if sst == 0:
        return float("nan")
    buckets = {}
    for v, g in zip(vals, groups):
        buckets.setdefault(g, []).append(v)
    ssb = sum(len(b) * (st.mean(b) - grand) ** 2 for b in buckets.values())
    return ssb / sst


def main() -> None:
    burst = json.loads(BURST.read_text())
    by = json.loads(COV.read_text())["by_symbol"]
    scores = json.loads(SCORES.read_text())
    orig_pairs = {(r["symbol"], r["buy_date"]) for r in scores}

    recs = []
    for r in burst["rows"]:
        if "bars_since_burst_start" not in r:
            continue
        sym, bd = r["symbol"], d(r["buy_date"])
        sub = by.get(sym, {}).get("submissions") or {}
        cands = [x for x in (sub.get("all_10Q_dates", []) + sub.get("all_10K_dates", []))
                 if d(x) <= bd]
        if not cands:
            continue
        age = (bd - d(max(cands, key=d))).days
        recs.append({
            "symbol": sym, "buy_date": r["buy_date"],
            "age_cal": age,
            "age_td": round(age * 0.69),                      # 自然日 -> 交易日近似
            "bars_burst": r["bars_since_burst_start"],
            "bars_burst_end": r["bars_since_burst_end"],
            "exact": (sym, r["buy_date"]) in orig_pairs,
        })

    print(f"重扫 match {len(burst['rows'])} 行；其中有财报账龄的 {len(recs)} 行\n")

    for label, sel in (("full-rerun", recs), ("exact-overlap（与原 112 行对上）",
                                              [x for x in recs if x["exact"]])):
        if len(sel) < 4:
            print(f"[{label}] n={len(sel)} 太少，跳过\n"); continue
        bb = [x["bars_burst"] for x in sel]
        ag = [x["age_td"] for x in sel]
        agc = [x["age_cal"] for x in sel]
        print(f"=== {label} · n={len(sel)} ===")
        q = st.quantiles(bb, n=4)
        print(f"  买点距 burst 起点的 bar 数: min={min(bb)} q25={q[0]:.0f} "
              f"med={st.median(bb):.0f} q75={q[2]:.0f} max={max(bb)}")
        be = [x["bars_burst_end"] for x in sel]
        print(f"  买点距 burst 终点的 bar 数: min={min(be)} med={st.median(be):.0f} max={max(be)}")
        qa = st.quantiles(agc, n=4)
        print(f"  财报账龄(自然日):          min={min(agc)} q25={qa[0]:.0f} "
              f"med={st.median(agc):.0f} q75={qa[2]:.0f} max={max(agc)}")
        print(f"  Spearman(账龄, 距 burst 起点 bar 数) = {spearman(agc, bb):+.3f}")
        # 以「距 burst 起点 bar 数」为因子，解释账龄多少方差
        print(f"  账龄方差被「形态进展」解释的比例 R² = {r2_by_factor(agc, bb):.3f}")
        # 反向：形态进展方差被账龄分箱解释多少
        bins = [min(a // 15, 6) for a in agc]
        print(f"  形态进展方差被「账龄分箱(15日)」解释的比例 R² = {r2_by_factor(bb, bins):.3f}")
        # 关键量：两者的量纲对比
        print(f"  ⟹ 形态进展跨度 {max(bb)-min(bb)} bar vs 账龄跨度 "
              f"{max(agc)-min(agc)} 自然日（≈{round((max(agc)-min(agc))*0.69)} bar）")
        print()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (OUT / f"burst_vs_age_{stamp}.json").write_text(
        json.dumps(recs, ensure_ascii=False, indent=1))
    print(f"-> burst_vs_age_{stamp}.json")


if __name__ == "__main__":
    main()
