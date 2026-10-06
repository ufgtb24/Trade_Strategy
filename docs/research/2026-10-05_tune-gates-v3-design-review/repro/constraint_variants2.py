"""补充反事实：Z>0 删除 + 「Δ≥0」改为「Δ≥原参数 Δ」（临时研究脚本）。"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from objective_noise import load, dedupe  # noqa
from scoring import WindowPlan, assess  # noqa
out = {}
for fold in ("fold1", "fold2"):
    bl, raw = load(fold, "search")
    plan = WindowPlan(bl, horizon=40, window_days=21, half_life_days=252, recent_days=126)
    cands = dedupe(raw)
    a = {c: assess(r, cands["base"], bl, plan, {}) for c, r in cands.items()}
    ref = a["base"]["statistics"]
    sel = []
    for c, x in a.items():
        if c == "base":
            continue
        s = x["statistics"]
        supply = all(v <= 0 for n, v in zip(x["constraint_names"], x["constraints"])
                     if n not in ("positive_direction_floor", "matched_baseline_floor"))
        if supply and s["raw_direction_score"] > ref["raw_direction_score"] + 1e-12 and \
                s["direction_difference"] >= ref["direction_difference"]:
            sel.append((round(s["raw_direction_score"], 4), round(s["direction_difference"], 4), c))
    out[fold] = {"ref_Z": ref["raw_direction_score"], "ref_Delta": ref["direction_difference"],
                 "n_feasible_better": len(sel), "selected": max(sel) if sel else None, "all": sorted(sel, reverse=True)}
Path(__file__).with_name("constraint_variants2_results.json").write_text(json.dumps(out, indent=1, default=float))
print(json.dumps(out, indent=1, default=float))
