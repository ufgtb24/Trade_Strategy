"""「困境微盘」与「高成长烧钱」是不是两个物种？—— 给 lead 要的数字支撑。

用户的理由是「很多高成长型股票(创新科技类)的净利润是负的」。我实测 bb 池负利润 79.4%，
但主因看起来是现金枯竭而非投资未来。lead 要求：别用断言，给出可支撑的最强区分证据。

区分维度（两个，都是 point-in-time 可得）：
  · 现金 runway = 现金 / |季度经营现金流|   —— 高成长烧钱有充裕弹药，困境股没有
  · R&D 强度   = R&D / 营收（无营收则记为「无营收」）—— 高成长烧钱把钱投进研发
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
CACHE = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-news"
             "/123cb8f3-70f2-4818-9f90-29de07c28fca/scratchpad/companyfacts")
SER = sorted(OUT.glob("financial_series_*.json"))[-1]
REPO = OUT.parents[3]

RND = ["ResearchAndDevelopmentExpense"]
REV = ["RevenueFromContractWithCustomerExcludingAssessedTax",
       "RevenueFromContractWithCustomerIncludingAssessedTax",
       "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"]


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def latest_q(facts, chain, asof):
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
                if not (80 <= (e0 - s0).days <= 100):
                    continue
                k = (s0, e0)
                if k not in best or f > best[k][1]:      # filed 最晚（已按 Falsifier 更正）
                    best[k] = (float(r["val"]), f)
        if best:
            break
    if not best:
        return None
    k = max(best)
    return k[1], best[k][0]


def main() -> None:
    rows = json.loads(SER.read_text())
    cm = {v["ticker"].upper(): int(v["cik_str"])
          for v in json.loads((REPO / "cache/news_sentiment/ticker_cik.json").read_text()).values()}

    loss = [r for r in rows if r.get("ni_sign") == "neg"]
    print(f"净利亏损行 {len(loss)}/{len(rows)}\n")

    recs = []
    for r in loss:
        cik = cm.get(r["symbol"].upper())
        p = CACHE / f"CIK{cik:010d}.json" if cik else None
        rnd_int = None
        if p and p.exists() and p.read_text().strip() != "null":
            facts = json.loads(p.read_text())
            bd = d(r["buy_date"])
            rq = latest_q(facts, RND, bd)
            vq = latest_q(facts, REV, bd)
            if rq and vq and vq[1] > 0:
                rnd_int = rq[1] / vq[1]
            elif rq and vq and vq[1] == 0:
                rnd_int = float("inf")
        recs.append({"symbol": r["symbol"], "buy_date": r["buy_date"],
                     "runway": r.get("runway_quarters"), "rnd_intensity": rnd_int,
                     "has_rev": r.get("n_rev_q", 0) > 0})

    rw = [x["runway"] for x in recs if x["runway"] is not None]
    print("[S] 亏损行的现金 runway（季度）")
    if rw:
        q = st.quantiles(rw, n=4)
        print(f"    n={len(rw)} q10={sorted(rw)[len(rw)//10]:.2f} q25={q[0]:.2f} "
              f"med={st.median(rw):.2f} q75={q[2]:.2f} q90={sorted(rw)[9*len(rw)//10]:.2f}")
        for th in (1, 2, 4, 8):
            print(f"    runway < {th} 季度: {sum(1 for x in rw if x < th):3d}/{len(rw)} "
                  f"= {sum(1 for x in rw if x < th)/len(rw):5.1%}")
    ri = [x["rnd_intensity"] for x in recs
          if x["rnd_intensity"] is not None and x["rnd_intensity"] != float("inf")]
    print(f"\n[T] 亏损行的 R&D / 营收")
    print(f"    可算 {len(ri)}/{len(recs)}；无营收但有 R&D（比值 = ∞）: "
          f"{sum(1 for x in recs if x['rnd_intensity'] == float('inf'))}")
    if ri:
        q = st.quantiles(ri, n=4)
        print(f"    n={len(ri)} q25={q[0]:.3f} med={st.median(ri):.3f} q75={q[2]:.3f} "
              f"max={max(ri):.2f}")
        print(f"    R&D/营收 > 0.5（高研发强度，典型「投资未来」）: "
              f"{sum(1 for x in ri if x > 0.5)}/{len(ri)}")
        print(f"    R&D/营收 < 0.1（几乎不投研发）: {sum(1 for x in ri if x < 0.1)}/{len(ri)}")

    print("\n[U] 二维交叉：runway（≥4 季 = 弹药充裕）× R&D 强度（>0.5 = 重研发）")
    grid = {(a, b): 0 for a in ("弹药充裕", "弹药紧张") for b in ("重研发", "轻研发", "R&D未知")}
    for x in recs:
        if x["runway"] is None:
            continue
        a = "弹药充裕" if x["runway"] >= 4 else "弹药紧张"
        v = x["rnd_intensity"]
        b = "R&D未知" if v is None else ("重研发" if (v == float("inf") or v > 0.5) else "轻研发")
        grid[(a, b)] += 1
    tot = sum(grid.values())
    for a in ("弹药充裕", "弹药紧张"):
        line = "  ".join(f"{b}={grid[(a,b)]:2d}" for b in ("重研发", "轻研发", "R&D未知"))
        print(f"    {a}: {line}")
    print(f"    合计 {tot} 行")
    print(f"    ⟹ 「高成长烧钱」典型格（弹药充裕 ∧ 重研发）= {grid[('弹药充裕','重研发')]}/{tot} "
          f"= {grid[('弹药充裕','重研发')]/max(tot,1):.1%}")
    print(f"    ⟹ 「困境微盘」典型格（弹药紧张 ∧ 轻研发/未知）= "
          f"{grid[('弹药紧张','轻研发')]+grid[('弹药紧张','R&D未知')]}/{tot} = "
          f"{(grid[('弹药紧张','轻研发')]+grid[('弹药紧张','R&D未知')])/max(tot,1):.1%}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (OUT / f"loss_species_{stamp}.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
