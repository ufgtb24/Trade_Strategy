"""同 harm_sim，但约束换成 objective.md D2 的版本：删 Z>0，对照差 ≥ 原参数对照差（临时研究脚本）。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import selection_sim as s
from scoring import DEFAULT_POLICY


def feasible_rel(c, ref, pol=DEFAULT_POLICY):
    Z, B = c["Z"], c["B"]
    ok = np.isfinite(Z)
    ok &= c["N"] >= pol["min_buy_days"]
    ok &= c["N"] >= pol["min_reference_fraction"] * ref["N"]
    ok &= c["R"] >= pol["min_recent_buy_days"]
    ok &= c["R"] >= pol["min_recent_reference_fraction"] * ref["R"]
    ok &= np.nan_to_num(Z - B, nan=-9) >= np.nan_to_num(ref["Z"] - ref["B"], nan=9) - 1e-12
    return ok


_orig_feasible, _orig_prepare = s.feasible, s.prepare


def _prepare(*a):
    # 与正式 assess 对账时仍用现行约束，之后再换成相对版本
    s.feasible = _orig_feasible
    try:
        return _orig_prepare(*a)
    finally:
        s.feasible = feasible_rel


s.prepare = _prepare
s.feasible = feasible_rel
s.DELTAS = [-0.10, -0.05, 0.0, 0.03, 0.05, 0.10]
out = {}
for fold in ("fold1", "fold2"):
    df = pd.DataFrame(s.final_check(fold)["per_candidate"]).T
    out[fold] = {}
    for d in s.DELTAS:
        p = df[f"p_prov_delta_{d}"].astype(float)
        out[fold][str(d)] = {"p_provisional": float(p.mean()), "p_keep_two_stage_same_rule": float((p ** 2).mean())}
Path(__file__).with_name("harm_sim_relfloor_results.json").write_text(json.dumps(out, indent=1))
for f, r in out.items():
    for k, v in r.items():
        print(f, k, {a: round(b, 3) for a, b in v.items()})
