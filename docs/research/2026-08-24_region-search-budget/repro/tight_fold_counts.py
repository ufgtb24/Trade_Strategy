"""收紧态 match 数按 fold 实算(integrator-final 核验 methods-survey §0 第 4 条「每 fold 33-65」的来源)。

来源文件:scan-FINAL-bb_v1-202401-202601(131 match)与 scan-B-bb_v1-202401-202601(260 match),窗 2024-01..2026-01。
scan 文件无 buy_date,用各命中股 pkl 切同一 buffered 窗后按 tb.start_idx 取日期,分半年 4 折 / 年 2 折计数;
同时给命中股数(按股 cluster bootstrap 的簇数)。
用法:`uv run python docs/research/2026-08-24_region-search-budget/repro/tight_fold_counts.py`
"""
from __future__ import annotations
import json, pathlib, subprocess, sys
from collections import Counter
REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))
import pandas as pd
from path2_web.data import slice_window


def main():
    DATA_DIR = pathlib.Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
    FILES = ["scan-FINAL-bb_v1-202401-202601", "scan-B-bb_v1-202401-202601", "20260818T223413", "tune-burst-min_bos-1-buf250", "tune-burst-min_bos-4-buf250"]
    PID = "bb_v1"
    for name in FILES:
        b = json.load(open(REPO / "outputs/path2_web/scans" / f"{name}.json"))
        meta = b["scan"]; snap = b["per_pattern"][PID]["params_snapshot"]
        half = Counter(); year = Counter(); syms = set(); n = 0
        for r in b["results"]:
            pr = (r.get("per_pattern") or {}).get(PID)
            if not pr or not pr["analysis"]["matches"]: continue
            w = slice_window(pd.read_pickle(DATA_DIR / f"{r['symbol']}.pkl"), meta["win_start"], meta["win_end"])
            ev = {e["instance_id"]: e for e in pr["analysis"]["events"]}
            for m in pr["analysis"]["matches"]:
                d = w["date"].iat[ev[m["node_index"]["tb"]]["start_idx"]]
                half[f"{d.year}H{1 if d.month <= 6 else 2}"] += 1; year[str(d.year)] += 1
                syms.add(r["symbol"]); n += 1
        print(f"{name}: 窗 {meta['start_date']}..{meta['end_date']} where=fd{snap['burst']['first_drought_min']}/dpk{snap['burst']['distinct_pk_min']}"
              f"/vsp{snap['burst']['vol_spike_min']}/pa{snap['burst']['peak_age_min']}/dpct{snap['tb']['max_day_drop_pct']}"
              f" | match={n} 命中股={len(syms)} | 半年折 {dict(sorted(half.items()))} | 年折 {dict(sorted(year.items()))}")


if __name__ == "__main__":
    main()
