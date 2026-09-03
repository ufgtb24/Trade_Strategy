"""独立审核:final_report §5.3「半年 4 折下收紧配置没有任何一格能过功效线 100」只在参照格上实算过。
本脚本在全部 OAT 宽进 scan 文件(tune-*-buf250,where=fd0/dpk1/vsp0/dpct None)上,按 burst 特征
事后套 FINAL(fd20/dpk4/vsp15)与 B(fd20/dpk3/vsp10)两套 where,数每个 OAT 格按半年 / 年的 match 数。
注意:事后套 where 不含 max_day_drop_pct 毒药闸(scan 文件无 day_drop 列),所以是真实收紧格计数的**上界**;
若上界都 < 功效线,则「无一格可评估」成立(对 OAT 格而言);若某格上界 ≥ 100,原句就需要收窄。
同时把 scan-FINAL / scan-B 两个真实收紧文件按同一代码数一遍,作为与 tight_fold_counts.py 的一致性校验。
用法:`uv run python docs/research/2026-08-24_region-search-budget/repro/audit_tight_fold_oat.py`
"""
from __future__ import annotations
import json, pathlib, subprocess, sys
from collections import Counter
REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))
import pandas as pd
from path2_web.data import slice_window
from path2.atoms.throwback_v1 import _revert_max_day_drop


def main():
    DATA_DIR = pathlib.Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
    SCAN_DIR = REPO / "outputs/path2_web/scans"
    PID = "bb_v1"
    WHERES = {"FINAL": dict(first_drought=20, distinct_pk=4, max_bar_vol_ratio=15),
              "B": dict(first_drought=20, distinct_pk=3, max_bar_vol_ratio=10)}
    DAY_DROP = 0.20      # 毒药闸:事后用 _revert_max_day_drop(w, burst.end_idx(=last_bo.end_idx), tb.start_idx) 精确复算
    POWER = 100
    files = sorted(p.stem for p in SCAN_DIR.glob("tune-*-buf250.json")) + ["scan-FINAL-bb_v1-202401-202601", "scan-B-bb_v1-202401-202601"]
    date_cache = {}
    worst = {}
    for name in files:
        b = json.load(open(SCAN_DIR / f"{name}.json"))
        meta = b["scan"]; snap = b["per_pattern"][PID]["params_snapshot"]
        is_tight = name.startswith("scan-")
        tags = ["asis"] if is_tight else [t + sfx for t in WHERES for sfx in ("(上界)", "(含毒药闸)")]
        half = {t: Counter() for t in tags}; year = {t: Counter() for t in tags}
        for r in b["results"]:
            pr = (r.get("per_pattern") or {}).get(PID)
            if not pr or not pr["analysis"]["matches"]:
                continue
            sym = r["symbol"]
            ck = (sym, meta["win_start"], meta["win_end"])
            if ck not in date_cache:
                date_cache[ck] = slice_window(pd.read_pickle(DATA_DIR / f"{sym}.pkl"), meta["win_start"], meta["win_end"])
            w = date_cache[ck]; dates = w["date"]
            ev = {e["instance_id"]: e for e in pr["analysis"]["events"]}
            for m in pr["analysis"]["matches"]:
                tb = ev[m["node_index"]["tb"]]; bu = ev[m["node_index"]["burst"]]
                d = dates.iat[tb["start_idx"]]
                hk = f"{d.year}H{1 if d.month <= 6 else 2}"; yk = str(d.year)
                dd = None
                for t in tags:
                    if t != "asis":
                        base_t = t.split("(")[0]
                        if not all(bu[f] >= v for f, v in WHERES[base_t].items()):
                            continue
                        if t.endswith("(含毒药闸)"):
                            if dd is None:
                                dd = _revert_max_day_drop(w, bu["end_idx"], tb["start_idx"])
                            if dd >= DAY_DROP:
                                continue
                    half[t][hk] += 1; year[t][yk] += 1
        for t in tags:
            h = dict(sorted(half[t].items())); y = dict(sorted(year[t].items()))
            print(f"{name:42s} where={t:12s} total={sum(y.values()):5d} 半年折 {h} 年折 {y}")
            if t != "asis":
                worst.setdefault(t, []).append((h.get("2024H1", 0), min(h.values()) if h else 0, min(y.values()) if y else 0, name))
    for t, rows in worst.items():
        rows.sort(reverse=True)
        n_half = sum(1 for r in rows if r[1] >= POWER); n_year = sum(1 for r in rows if r[2] >= POWER)
        print(f"== where={t}: OAT 格数={len(rows)}; 半年 4 折全过线(min fold ≥{POWER})的格数={n_half}; 年 2 折全过线的格数={n_year}; "
              f"2024H1 最高={rows[0][0]}({rows[0][3]})")


if __name__ == "__main__":
    main()
