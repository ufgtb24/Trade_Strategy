"""最后检查/复核对「真实变差」的拦截力（临时研究脚本）：复用 selection_sim.final_check，δ 取负值。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import selection_sim as s

s.DELTAS = [-0.20, -0.10, -0.05, -0.03, 0.0, 0.03, 0.05, 0.10]
res = s.final_check("fold2")
df = pd.DataFrame(res["per_candidate"]).T
out = {}
for d in s.DELTAS:
    p = df[f"p_prov_delta_{d}"].astype(float)
    out[str(d)] = {"p_provisional": float(p.mean()), "p_keep_two_stage_same_rule": float((p ** 2).mean())}
Path(__file__).with_name("harm_sim_results.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(k, {a: round(b, 3) for a, b in v.items()})
