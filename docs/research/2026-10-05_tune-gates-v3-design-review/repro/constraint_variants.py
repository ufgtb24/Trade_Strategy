"""约束变体的反事实：去掉「Z>0」或「Δ≥0」后，两折各选谁、后段如何（临时研究脚本，仅示意）。"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from objective_noise import load, dedupe  # noqa
from scoring import WindowPlan, assess  # noqa

VARIANTS = {"current": [], "no_Z>0": ["positive_direction_floor"], "no_Delta>=0": ["matched_baseline_floor"],
            "no_both": ["positive_direction_floor", "matched_baseline_floor"],
            "supply_only_relative": ["positive_direction_floor", "matched_baseline_floor", "buy_days_floor", "recent_buy_days_floor"]}
out = {}
for fold in ("fold1", "fold2"):
    res = {}
    stage = {}
    for part in ("search", "check"):
        bl, raw = load(fold, part)
        plan = WindowPlan(bl, horizon=40, window_days=21, half_life_days=252, recent_days=126)
        cands = dedupe(raw)
        stage[part] = {c: assess(r, cands["base"], bl, plan, {}) for c, r in cands.items()}
        if part == "check":
            # 后段：每个搜索段候选按参数 id 找后段结果（后段去重可能合并了 id，回退到原始行）
            allc = {cid: raw[raw.candidate_id == cid].drop(columns="candidate_id") for cid in raw.candidate_id.unique()}
            stage["check_all"] = {c: assess(r, allc["base"], bl, plan, {}) for c, r in allc.items()}
    ref = stage["search"]["base"]
    for name, drop in VARIANTS.items():
        feas = []
        for cid, a in stage["search"].items():
            ok = all(v <= 0 for n, v in zip(a["constraint_names"], a["constraints"]) if n not in drop)
            if ok and a["statistics"]["raw_direction_score"] > ref["statistics"]["raw_direction_score"] + 1e-12 and cid != "base":
                feas.append((a["statistics"]["raw_direction_score"], cid))
        if feas:
            best = max(feas)[1]
            ck, cb = stage["check_all"][best]["statistics"], stage["check_all"]["base"]["statistics"]
            res[name] = {"n_feasible_better_than_ref": len(feas), "selected": best,
                         "search_Z": stage["search"][best]["statistics"]["raw_direction_score"],
                         "search_Z_ref": ref["statistics"]["raw_direction_score"],
                         "check_Z": ck["raw_direction_score"], "check_Z_ref": cb["raw_direction_score"],
                         "check_N": ck["count"], "check_N_ref": cb["count"], "check_stocks": ck["stocks"]}
        else:
            res[name] = {"n_feasible_better_than_ref": 0, "selected": "base"}
    out[fold] = res
Path(__file__).with_name("constraint_variants_results.json").write_text(json.dumps(out, indent=1, default=float, ensure_ascii=False))
for f, r in out.items():
    print("==", f)
    for k, v in r.items(): print(k, v)
