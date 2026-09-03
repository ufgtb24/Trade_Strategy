# -*- coding: utf-8 -*-
"""重跑 detector 链(手动组装 BO→burst→tb,参数=scan params_snapshot)→ gates_report.json。

A. v1-only 6 symbol(7 个 v1 burst-match):跑 v4 状态机,看为何零段。
B. v4-only 111 burst:跑 v1 evaluate_throwback(带 on_gate),死因分类。
   对照:共同 73 burst 上 v1 的死因(应全部产事件)。

链组装:BO/Burst detector 原始 detect → burst where 闸(first_drought/distinct_pk/
max_bar_vol_ratio,v1 另有恒真 peak_age_min=0)→ 逐 burst tb。与 dag 引擎同源
(detector 同代码、参数同 snapshot),仅绕开 match 物化。
"""
import json
import sys
from pathlib import Path
from collections import Counter, defaultdict

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from path2.atoms.breakout import BODetector, BurstDetector          # noqa: E402
from path2.atoms.throwback_v1 import evaluate_throwback            # noqa: E402
from path2.atoms.throwback_v4 import enumerate_segments_v4         # noqa: E402
from path2.calc.measure import measure_at, measure_series          # noqa: E402
from path2.calc.atr import calculate_tr_median                     # noqa: E402
from path2_web.data import slice_window                            # noqa: E402

WIN_START, WIN_END = "2024-09-19", "2026-03-08"
SCAN = json.loads((REPO / "outputs/path2_web/scans/20260818T102540.json").read_text())
SCAN1 = json.loads((REPO / "outputs/path2_web/scans/20260818T103730.json").read_text())
PS4 = SCAN["per_pattern"]["bottom_burst"]["params_snapshot"]
PS1 = SCAN1["per_pattern"]["bb_v1"]["params_snapshot"]

D = json.loads((HERE / "extracted.json").read_text())


def burst_key_map(gen):
    out = {}
    for sym, v in D[gen].items():
        for m in v["matches"]:
            b = next(x for x in v["burst"] if x[0] == m["burst_iid"])
            out[m["match_id"]] = (sym, b[1], b[2])
    return out


bk4, bk1 = burst_key_map("v4"), burst_key_map("v1")
common = {bk for bk in bk4.values() if bk in set(bk1.values())}
v4only = {bk for bk in bk4.values() if bk not in common}
v1only_syms = sorted(set(s for s, _, _ in set(bk1.values()))
                     - set(D["v4"]))
print("v1-only symbols:", v1only_syms)


def bursts_of(sym):
    """重跑 BO→burst(含 where 闸),返回 burst 列表(原始对象)。"""
    df = pd.read_pickle(REPO / "datasets/pkls" / f"{sym}.pkl")
    win = slice_window(df, WIN_START, WIN_END)
    bo_kw = dict(PS4["bo"])
    bo = list(BODetector(**bo_kw).detect(win))
    bw = PS4["burst"]
    bursts = list(BurstDetector(gap_max=bw["gap_max"], min_bos=bw["min_bos"],
                                vol_baseline_period=bw["vol_baseline_period"])
                  .detect(bo, win))
    kept = [b for b in bursts
            if b.first_drought >= bw["first_drought_min"]
            and b.distinct_pk >= bw["distinct_pk_min"]
            and b.max_bar_vol_ratio >= bw["vol_spike_min"]]
    return win, kept


def main():
    rep = {"A_v1only_on_v4": [], "B_v4only_on_v1": {}, "C_common_on_v1": {}}

    # ── A:6 个 v1-only symbol,v4 状态机为何零段 ──
    for sym in v1only_syms:
        win, kept = bursts_of(sym)
        tbkw = PS4["tb"]
        vol = calculate_tr_median(win["high"], win["low"], win["close"],
                                  tbkw["vol_window"]).values
        mc = measure_series(win, tbkw["measure"]).values
        for b in kept:
            key = (sym, b.start_idx, b.end_idx)
            was_v1 = key in set(bk1.values())
            last_bo = b.members[-1]
            gbot = min(measure_at(win, i, tbkw["measure"])
                       for i in range(b.start_idx, b.end_idx + 1))
            res = enumerate_segments_v4(
                mc, win["open"].values, last_bo.end_idx, float(gbot), vol,
                max_rise_k=tbkw["max_rise_k"],
                stop_confirm_bars=tbkw["stop_confirm_bars"],
                max_span=tbkw["max_span"], vol_window=tbkw["vol_window"],
                real_closes=win["close"].values)
            rep["A_v1only_on_v4"].append({
                "symbol": sym, "burst": [b.start_idx, b.end_idx],
                "was_v1_match": was_v1, "n_segs": len(res.segments),
                "machine_outcome": res.machine_outcome})

    # ── B/C:v1 evaluate 在 v4-only / 共同 burst 上的死因 ──
    tbkw1 = dict(PS1["tb"])
    anchor_mode = tbkw1.pop("anchor_mode")
    assert anchor_mode == "span_min"
    need = defaultdict(set)      # sym -> {burst key}
    for src, keys in (("B", v4only), ("C", common)):
        for sym, s, e in keys:
            need[sym].add((s, e))

    counts = {"B": Counter(), "C": Counter()}
    for sym in sorted(need):
        win, kept = bursts_of(sym)
        gates = []

        def collect(g, sym=sym):
            gates.append(g)

        for b in kept:
            key = (sym, b.start_idx, b.end_idx)
            grp = "B" if key in v4only else ("C" if key in common else None)
            if grp is None:
                continue
            last_bo = b.members[-1]
            anchor = min(measure_at(win, i, tbkw1["reference_measure"])
                         for i in range(b.start_idx, b.end_idx + 1))
            r = evaluate_throwback(last_bo, win, anchor=anchor,
                                   on_gate=collect, **tbkw1)
            if r is not None:
                counts[grp][f"event:{r.outcome}"] += 1
            else:
                gn = gates[-1].gate_name if gates else "?"
                counts[grp][f"gate:{gn}"] += 1
    rep["B_v4only_on_v1"] = dict(counts["B"])
    rep["C_common_on_v1"] = dict(counts["C"])

    (HERE / "gates_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
