"""财报公布日落在 bb_v1 形态的哪一段？（旱期 / burst / 回踩）

bb_v1 的几何：旱期(first_drought >= 40 bar 无突破) → burst(突破簇) → tb(回踩企稳, <=7 bar) → 买点。
若财报落在**旱期**内，则「财报出来后价格明确没有突破」被写进了形态条件本身——
这正是用户原命题「营收大幅增长但股价没涨」的几何实现。本探针量化这个占比。
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
BURST = sorted(OUT.glob("burst_start_*.json"))[-1]
COV = sorted(OUT.glob("xbrl_coverage_*.json"))[-1]


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    rows = json.loads(BURST.read_text())["rows"]
    by = json.loads(COV.read_text())["by_symbol"]

    seg = {"旱期内": 0, "burst 期内": 0, "回踩期内": 0, "旱期之前": 0}
    dr, prog, ages = [], [], []
    detail = []
    for r in rows:
        if "bars_since_burst_start" not in r or not r.get("drought_start_date"):
            continue
        sym, bd = r["symbol"], d(r["buy_date"])
        sub = by.get(sym, {}).get("submissions") or {}
        cands = [x for x in (sub.get("all_10Q_dates", []) + sub.get("all_10K_dates", []))
                 if d(x) <= bd]
        if not cands:
            continue
        f = d(max(cands, key=d))
        ds, bs, be = d(r["drought_start_date"]), d(r["burst_start_date"]), d(r["burst_end_date"])
        if f < ds:
            k = "旱期之前"
        elif f < bs:
            k = "旱期内"
        elif f <= be:
            k = "burst 期内"
        else:
            k = "回踩期内"
        seg[k] += 1
        dr.append(r["first_drought"]); prog.append(r["bars_since_drought_start"])
        ages.append((bd - f).days)
        detail.append({"symbol": sym, "buy_date": r["buy_date"], "filed": f.isoformat(),
                       "drought_start": r["drought_start_date"],
                       "burst_start": r["burst_start_date"],
                       "burst_end": r["burst_end_date"], "seg": k,
                       "first_drought": r["first_drought"]})

    n = sum(seg.values())
    print(f"n = {n} 行（重扫 match ∩ 有 first_drought ∩ 有财报日）\n")
    print("[O] 最近一次 10-Q/10-K 落在形态的哪一段")
    for k in ("旱期之前", "旱期内", "burst 期内", "回踩期内"):
        print(f"    {k:10s} {seg[k]:3d}/{n} = {seg[k]/n:6.1%}")
    if dr:
        q = st.quantiles(dr, n=4)
        print(f"\n[P] first_drought（簇首 bo 距上一根 bo 的 bar 数，bb_v1 要求 >= 40）")
        print(f"    min={min(dr)} q25={q[0]:.0f} med={st.median(dr):.0f} q75={q[2]:.0f} max={max(dr)}")
        qp = st.quantiles(prog, n=4)
        print(f"\n[Q] 买点距**旱期起点**的 bar 数（= 整个形态的真实跨度）")
        print(f"    min={min(prog)} q25={qp[0]:.0f} med={st.median(prog):.0f} "
              f"q75={qp[2]:.0f} max={max(prog)}")
        qa = st.quantiles(ages, n=4)
        print(f"\n[R] 同批行的财报账龄（自然日） med={st.median(ages):.0f} "
              f"q25={qa[0]:.0f} q75={qa[2]:.0f}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (OUT / f"filing_in_drought_{stamp}.json").write_text(
        json.dumps({"counts": seg, "rows": detail}, ensure_ascii=False, indent=1))
    print(f"\n-> filing_in_drought_{stamp}.json")


if __name__ == "__main__":
    main()
