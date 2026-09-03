"""独立审核:scan-FINAL / scan-B(win_start 2023-09-19,head buffer ≈ 70 交易日)与 tune-*-buf250(buffer 250)
窗口不同。final_report §5.3 断言「2024H1 只有 5/10 个……不是数据窗问题」——本脚本用**当前代码**在两种窗口上
对同一组股票、同一套 FINAL / B 参数各跑一次 analyze,数 2024H1 与年折 match 数,直接检验 head buffer 是否是 2024H1 塌陷的原因。
股票集 = scan-FINAL / scan-B 命中股 ∪ buf250 参照格事后套 FINAL/B where 后的命中股(audit_tight_fold_oat 口径)。
用法:`uv run python docs/research/2026-08-24_region-search-budget/repro/audit_head_buffer_effect.py`
"""
from __future__ import annotations
import json, pathlib, subprocess, sys
from collections import Counter
REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))
import pandas as pd
from path2 import config
from path2.dag.engine import analyze
from path2_web.data import slice_window
from path2_apps.bb_v1.dag_spec import build_pattern
from path2_apps.bb_v1.params import Params


def main():
    DATA_DIR = pathlib.Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
    SCAN_DIR = REPO / "outputs/path2_web/scans"
    PID = "bb_v1"
    CASES = [("FINAL", "scan-FINAL-bb_v1-202401-202601"), ("B", "scan-B-bb_v1-202401-202601")]
    WIDE_REF = "tune-burst-min_bos-1-buf250"          # 参照格宽进 scan(buf250),提供股票候选与 buf250 窗口
    START, END = pd.Timestamp("2024-01-01"), pd.Timestamp("2026-01-01")
    config.set_runtime_checks(False)
    wide = json.load(open(SCAN_DIR / f"{WIDE_REF}.json"))
    win_long = (wide["scan"]["win_start"], wide["scan"]["win_end"])
    wide_syms = {r["symbol"] for r in wide["results"] if (r.get("per_pattern") or {}).get(PID) and r["per_pattern"][PID]["analysis"]["matches"]}
    for tag, name in CASES:
        b = json.load(open(SCAN_DIR / f"{name}.json"))
        win_short = (b["scan"]["win_start"], b["scan"]["win_end"])
        snap = b["per_pattern"][PID]["params_snapshot"]
        p = Params.from_dict(snap); spec = build_pattern(p)
        tight_syms = {r["symbol"] for r in b["results"] if (r.get("per_pattern") or {}).get(PID) and r["per_pattern"][PID]["analysis"]["matches"]}
        syms = sorted(tight_syms | wide_syms)
        print(f"[{tag}] {name}: 短窗 {win_short} / 长窗(buf250) {win_long}; 股票集={len(syms)}(收紧命中 {len(tight_syms)} ∪ 宽进参照格命中 {len(wide_syms)})")
        print(f"      params where=fd{snap['burst']['first_drought_min']}/dpk{snap['burst']['distinct_pk_min']}/vsp{snap['burst']['vol_spike_min']}/dpct{snap['tb']['max_day_drop_pct']} cell=g{snap['burst']['gap_max']}/m{snap['burst']['min_bos']}/K{snap['tb']['stop_confirm_bars']}/k{snap['tb']['big_rise_k']}")
        for wtag, (ws, we) in (("短窗≈70", win_short), ("长窗250", win_long)):
            half = Counter(); year = Counter(); n = 0; hit = set()
            for sym in syms:
                pk = DATA_DIR / f"{sym}.pkl"
                if not pk.exists():
                    continue
                w = slice_window(pd.read_pickle(pk), ws, we)
                if len(w) < 60:
                    continue
                res = analyze(spec, w, p)
                for m in res.matches:
                    d = w["date"].iat[m.node_index["tb"].start_idx]
                    if not (START <= d <= END):
                        continue
                    half[f"{d.year}H{1 if d.month <= 6 else 2}"] += 1; year[str(d.year)] += 1; n += 1; hit.add(sym)
            print(f"   {wtag}: match={n} 命中股={len(hit)} 半年折 {dict(sorted(half.items()))} 年折 {dict(sorted(year.items()))}")


if __name__ == "__main__":
    main()
