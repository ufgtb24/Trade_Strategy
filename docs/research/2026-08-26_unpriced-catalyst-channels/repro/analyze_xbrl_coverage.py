"""汇总 probe_xbrl_coverage.py 的原始 JSON：逐 concept 覆盖率 + filing 节奏 + 报告体裁分布。"""
from __future__ import annotations

import json
import statistics as st
from collections import Counter
from datetime import date, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
RAW = sorted(OUT.glob("xbrl_coverage_*.json"))[-1]
SCORES = (OUT.parents[1] / "2026-08-16_news-sentiment-path2-integration"
          / "repro" / "full_scores_20260816-193559.json")


def d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    raw = json.loads(RAW.read_text())
    by = raw["by_symbol"]
    syms = sorted(by)
    n = len(syms)
    print(f"源文件 {RAW.name} · {n} 只 bb 票\n")

    # --- 0. 基础可达性 ---
    no_cik = [s for s in syms if by[s].get("cik") is None]
    facts_404 = [s for s in syms if by[s].get("companyfacts_http") == 404]
    facts_ok = [s for s in syms if by[s].get("companyfacts_http") == 200]
    print(f"[0] CIK 解析失败 {len(no_cik)}/{n}: {no_cik}")
    print(f"[0] companyfacts 404（有 CIK 但无 XBRL）{len(facts_404)}/{n}: {facts_404}")
    print(f"[0] companyfacts 200 {len(facts_ok)}/{n} = {len(facts_ok)/n:.1%}\n")

    # --- 1. 报告体裁 / 交易所 ---
    ent = Counter(by[s].get("submissions", {}).get("entityType") for s in syms)
    print(f"[1] entityType: {dict(ent)}")
    exch = Counter()
    for s in syms:
        e = by[s].get("submissions", {}).get("exchanges") or []
        exch[tuple(e) if e else ("<none/OTC>",)] += 1
    print(f"[1] exchanges: {dict(exch)}")
    f20 = [s for s in syms if by[s].get("submissions", {}).get("last_20F")]
    print(f"[1] 交过 20-F（外国私人发行人，年报-only）{len(f20)}/{n}: {f20}")
    no10q = [s for s in syms if not by[s].get("submissions", {}).get("last_10Q")]
    print(f"[1] 从未交过 10-Q {len(no10q)}/{n}: {no10q}\n")

    # --- 2. 逐 concept 覆盖率（全体 n 为分母，含 404/无 CIK，即实盘真实可用率）---
    print("[2] concept 覆盖率（分母 = 全部 82 只 bb 票；recent = 最近一次 filed >= 2025-01-01）")
    chains = raw["concept_chains"]
    rows = []
    for name in chains:
        hit = [s for s in syms if (by[s].get("facts", {}).get("concepts", {}) or {}).get(name)]
        rec = [s for s in hit if by[s]["facts"]["concepts"][name]["recent"]]
        tags = Counter(by[s]["facts"]["concepts"][name]["tag"] for s in rec)
        rows.append((name, len(hit), len(rec), tags))
    rows.sort(key=lambda r: -r[2])
    for name, nhit, nrec, tags in rows:
        top = "; ".join(f"{t}={c}" for t, c in tags.most_common(3))
        print(f"  {name:16s} any={nhit:3d} ({nhit/n:5.1%})  recent={nrec:3d} ({nrec/n:5.1%})  | {top}")

    # --- 2b. revenue 回退链的边际贡献 ---
    print("\n[2b] revenue 回退链逐级边际贡献（recent 口径）")
    covered: set[str] = set()
    for tag in chains["revenue"]:
        add = set()
        for s in syms:
            c = (by[s].get("facts", {}).get("concepts", {}) or {}).get("revenue")
            if c and c["recent"] and c["tag"] == tag:
                add.add(s)
        # 上面只记录了链上首个 recent 命中，故直接累加即可
        covered |= add
        print(f"  +{tag:52s} 新增 {len(add):2d} → 累计 {len(covered):2d} ({len(covered)/n:.1%})")
    miss = [s for s in syms if s not in covered]
    print(f"  revenue recent 缺失 {len(miss)}/{n}: {miss}")

    # --- 3. filing 节奏：buy_date 时点上最近一次 10-Q/10-K 的账龄 ---
    scores = json.loads(SCORES.read_text())
    ages, in_window, no_prior = [], 0, []
    per_row = []
    for r in scores:
        sym, bd = r["symbol"], d(r["buy_date"])
        sub = by.get(sym, {}).get("submissions") or {}
        cands = [x for x in (sub.get("all_10Q_dates", []) + sub.get("all_10K_dates", []))
                 if d(x) <= bd]
        if not cands:
            no_prior.append(sym)
            continue
        last = max(cands, key=d)
        age = (bd - d(last)).days
        ages.append(age)
        per_row.append((sym, r["buy_date"], last, age, r["fr40"]))
        if age <= 120:          # ~ bb 形态跨度（60-100 交易日 ≈ 90-140 自然日）
            in_window += 1
    print(f"\n[3] buy_date 时点最近 10-Q/10-K 账龄（自然日），n={len(ages)}/112 有值")
    if ages:
        qs = st.quantiles(ages, n=4)
        print(f"    min={min(ages)} q25={qs[0]:.0f} median={st.median(ages):.0f} "
              f"q75={qs[2]:.0f} max={max(ages)}")
        for th in (30, 45, 60, 90, 120, 180):
            print(f"    账龄 ≤{th:3d} 日: {sum(a<=th for a in ages):3d}/{len(ages)} "
                  f"= {sum(a<=th for a in ages)/len(ages):5.1%}")
    print(f"    无任何 buy_date 之前的 10-Q/10-K: {len(no_prior)} 行 -> {sorted(set(no_prior))}")

    # --- 4. Form 4 / 13D/G 作用面 ---
    n4 = [(s, (by[s].get("submissions") or {}).get("n_form4", 0)) for s in syms]
    has4 = [s for s, c in n4 if c > 0]
    print(f"\n[4] Form 4（内部人交易）：近期流水中出现过 {len(has4)}/{n} = {len(has4)/n:.1%}")
    print(f"    Form 4 条数中位（全体）= {st.median([c for _, c in n4]):.0f}，"
          f"有值者中位 = {st.median([c for _, c in n4 if c>0]) if has4 else 0:.0f}")
    # buy_date 前 90 天内是否有 Form 4
    f4_in90 = 0
    f4_rows = 0
    for r in scores:
        sub = by.get(r["symbol"], {}).get("submissions") or {}
        if "all_4_dates" not in sub:
            continue
        f4_rows += 1
        bd = d(r["buy_date"])
        if any(0 <= (bd - d(x)).days <= 90 for x in sub["all_4_dates"]):
            f4_in90 += 1
    print(f"    买点前 90 日内存在 Form 4 的行数 {f4_in90}/{f4_rows} = "
          f"{f4_in90/max(f4_rows,1):.1%}  （注意：recent 流水最多 ~1000 条、已截断到 60 条）")
    n13 = [(s, (by[s].get("submissions") or {}).get("n_SC13D", 0)
            + (by[s].get("submissions") or {}).get("n_SC13G", 0)) for s in syms]
    print(f"[4] SC 13D/G：出现过 {sum(1 for _, c in n13 if c>0)}/{n}")

    # --- 5. 净利润符号分布（回答「是否排除净利润」）---
    print("\n[5] 见 analyze_profitability.py")


if __name__ == "__main__":
    main()
