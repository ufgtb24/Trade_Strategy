"""汇总 fold_broad.py 的 jsonl:每 app × node × 档位 × 规则,行数分布(中位 / p90 / 最大)与误折、档位混杂合计。

用法: uv run python docs/research/2026-11-05_band-folding-design/repro/fold_broad_summary.py <jsonl>
"""
import collections
import json
import sys

import numpy as np

RULES = ["R0_none", "R1_same_span", "R2_start", "R3_end", "R4_start_or_end", "R5_parent"]


def q(xs, p):
    return float(np.percentile(xs, p)) if xs else 0.0


def main():
    rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
    agg = collections.defaultdict(lambda: collections.defaultdict(list))
    tot = collections.defaultdict(lambda: collections.Counter())
    nsym = collections.Counter()
    for r in rows:
        nsym[r["app"]] += 1
        for nid, nd in r["nodes"].items():
            for level in ("detected", "qualified", "in_hit"):
                for rule in RULES:
                    x = nd[level][rule]
                    if x["items"] == 0:
                        continue
                    k = (r["app"], nid, level, rule)
                    agg[k]["rows"].append(x["rows"])
                    for f in ("misfold", "misfold_strict", "mixed_tier", "multi_day", "days", "fams", "items", "non_nested"):
                        tot[k][f] += x.get(f, 0)
                    tot[k]["syms_misfold"] += 1 if x["misfold"] else 0
                    tot[k]["syms_misfold_strict"] += 1 if x.get("misfold_strict", 0) else 0
    print("股票数:", dict(nsym))
    for level in ("detected", "in_hit"):
        print(f"\n### level={level}: 行数 中位/p90/最大 (有该 node event 的股票数) | 误折族(其中跨度不同)/涉及股票 | 档位混杂族 | 非嵌套族")
        for app in ("new_step", "bottom_burst", "bb_v1"):
            nodes = sorted({k[1] for k in agg if k[0] == app})
            for nid in nodes:
                parts = []
                for rule in RULES:
                    k = (app, nid, level, rule)
                    if k not in agg:
                        continue
                    xs = agg[k]["rows"]
                    t = tot[k]
                    s = f"{rule.split('_')[0]}={np.median(xs):.0f}/{q(xs, 90):.0f}/{max(xs)}"
                    if rule != "R0_none":
                        s += f"[mis {t['misfold']}({t['misfold_strict']})/{t['syms_misfold']}s, mix {t['mixed_tier']}, nn {t['non_nested']}]"
                    parts.append(s)
                n = len(agg[(app, nid, level, "R0_none")]["rows"]) if (app, nid, level, "R0_none") in agg else 0
                print(f"{app:12s} {nid:9s} (n={n:3d})  " + "  ".join(parts))
    print("\n### hit 层")
    for app in ("new_step", "bottom_burst", "bb_v1"):
        hs = [r["hit"] for r in rows if r["app"] == app]
        withhit = [h for h in hs if h["n"] > 0]
        if not withhit:
            print(app, "无 hit"); continue
        br0 = [h["bracket_rows_now"] for h in withhit]
        br1 = [h["bracket_rows_fold_start"] for h in withhit]
        print(f"{app:12s} 有hit股={len(withhit)} hits合计={sum(h['n'] for h in withhit)} 买入日合计={sum(h['buy_days'] for h in withhit)} "
              f"bracket行 中位/p90/最大 {np.median(br0):.0f}/{q(br0,90):.0f}/{max(br0)} -> {np.median(br1):.0f}/{q(br1,90):.0f}/{max(br1)}  "
              f"多hit日合计={sum(h['days_multi_hit'] for h in withhit)}(涉及{sum(1 for h in withhit if h['days_multi_hit'])}股) "
              f"max hit/日={max(h['max_hits_per_day'] for h in withhit)}  多族同日买={sum(h['days_multi_family'] for h in withhit)}(涉及{sum(1 for h in withhit if h['days_multi_family'])}股)")


if __name__ == "__main__":
    main()
