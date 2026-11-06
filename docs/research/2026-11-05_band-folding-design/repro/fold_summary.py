"""把 fold_measure.py 的 jsonl 汇成表(研究用临时脚本)。

用法: uv run python docs/research/2026-11-05_band-folding-design/repro/fold_summary.py <jsonl> [level ...]
"""
import json
import sys

RULES = ["R0_none", "R1_same_span", "R2_start", "R3_end", "R4_start_or_end", "R5_parent"]
SHORT = {"R0_none": "R0", "R1_same_span": "R1", "R2_start": "R2", "R3_end": "R3",
         "R4_start_or_end": "R4", "R5_parent": "R5"}


def main():
    path = sys.argv[1]
    levels = sys.argv[2:] or ["detected", "qualified", "in_hit"]
    rows = [json.loads(l) for l in open(path) if l.strip()]
    for level in levels:
        print(f"\n### level={level}  每格: 行数/族数 [误折族数,档位混杂族数,同日多成员天数/族内天数,max/日,非嵌套族]")
        for r in rows:
            for nid, nd in r["nodes"].items():
                lv = nd[level]
                cells = []
                for rule in RULES:
                    x = lv[rule]
                    extra = f"[{x['misfold']},{x['mixed_tier']},{x['multi_day']}/{x['days']},{x['max_per_day']},{x['non_nested']}]"
                    cells.append(f"{SHORT[rule]}={x['rows']}/{x['fams']}{extra if rule != 'R0_none' else ''}")
                print(f"{r['app']:12s} {r['sym']:5s} {nid:9s} n={lv['R0_none']['items']:5d}  " + "  ".join(cells))
    print("\n### hit 层")
    for r in rows:
        h = r["hit"]
        print(f"{r['app']:12s} {r['sym']:5s} hits={h['n']:4d} bracket_rows {h['bracket_rows_now']}->{h['bracket_rows_fold_start']} "
              f"(族 {h['fams_by_start']})  买入日={h['buy_days']} 多hit日={h['days_multi_hit']} max/日={h['max_hits_per_day']} 多族同日={h['days_multi_family']}")


if __name__ == "__main__":
    main()
