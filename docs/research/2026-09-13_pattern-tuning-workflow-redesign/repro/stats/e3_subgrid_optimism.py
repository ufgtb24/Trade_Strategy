"""E3:同一份长表上,子网格规模 K 与「按股 bootstrap optimism」的关系,并与噪声地板公式/独立噪声零假设模拟对照。
复用 tune-gates 的 region_core(与 tune.find 同一套打分 → 邻域最小 → 排序 → bootstrap),只改档位表。
用法:uv run python e3_subgrid_optimism.py <GRID名> [B]
"""
import sys, json, time, resource
from pathlib import Path
import numpy as np
from scipy import stats
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / ".claude/skills/tune-gates"))
from region_core import prepare_shards, analyze_tensor, bootstrap, split_half_multi, tensor, fp_count, neighbor_min, rank_cells  # noqa: E402

LT = ROOT / "outputs/tune_gates/bb_v1/main/longtable"
FULL = {"bo.exceed_threshold": [0.0015, 0.003, 0.0045, 0.0075], "bo.min_relative_height": [0.1, 0.2, 0.3, 0.5], "burst.gap_max": [4, 8, 12, 20],
        "tb.max_rise_k": [0.75, 1.5, 2.25, 3.75], "tb.max_span": [10, 20, 30, 50], "tb.stop_confirm_bars": [1, 2, 3, 4]}
OPS = {"burst.count": ">=", "burst.distinct_pk": ">=", "burst.first_drought": ">=", "burst.peak_age_max": ">=", "burst.max_bar_vol_ratio": ">=", "tb.max_day_drop": "<"}
FULLP = {"burst.count": [1, 2, 3, 4], "burst.distinct_pk": [1, 3, 5], "burst.first_drought": [0, 40, 80], "burst.peak_age_max": [0, 60, 120],
         "burst.max_bar_vol_ratio": [0, 3, 6], "tb.max_day_drop": [None, 0.2]}
REF = {"bo.exceed_threshold": 0.003, "bo.min_relative_height": 0.2, "burst.gap_max": 8, "tb.max_rise_k": 1.5, "tb.max_span": 20, "tb.stop_confirm_bars": 1,
       "burst.count": 1, "burst.distinct_pk": 1, "burst.first_drought": 0, "burst.peak_age_max": 0, "burst.max_bar_vol_ratio": 0, "tb.max_day_drop": None}
TWO = {"bo.exceed_threshold": [0.003, 0.0075], "bo.min_relative_height": [0.2, 0.5], "burst.gap_max": [8, 4], "tb.max_rise_k": [1.5, 3.75],
       "tb.max_span": [20, 10], "tb.stop_confirm_bars": [1, 3], "burst.count": [1, 3], "burst.distinct_pk": [1, 5], "burst.first_drought": [0, 80],
       "burst.peak_age_max": [0, 120], "burst.max_bar_vol_ratio": [0, 6], "tb.max_day_drop": [None, 0.2]}
THREE = {"bo.exceed_threshold": [0.0015, 0.003, 0.0045], "bo.min_relative_height": [0.1, 0.2, 0.3], "burst.gap_max": [4, 8, 12],
         "tb.max_rise_k": [0.75, 1.5, 2.25], "tb.max_span": [10, 20, 30], "tb.stop_confirm_bars": [1, 2, 3], "burst.count": [1, 2, 3],
         "burst.distinct_pk": [1, 3, 5], "burst.first_drought": [0, 40, 80], "burst.peak_age_max": [0, 60, 120], "burst.max_bar_vol_ratio": [0, 3, 6],
         "tb.max_day_drop": [None, 0.2]}

def grid(varied: dict):
    """varied: {轴: 档位表};未列出的轴固定在参照档(单档)。"""
    combo = {a: varied.get(a, [REF[a]]) for a in FULL}
    preds = [(a, OPS[a], varied.get(a, [REF[a]])) for a in FULLP]
    return combo, preds

GRIDS = {
    "G064_3D": grid({a: FULL[a] for a in ["bo.exceed_threshold", "tb.max_span", "tb.stop_confirm_bars"]}),
    "G648_WF": grid(FULLP),
    "G4096_6D": grid(FULL),
    "G4096_12x2": grid(TWO),
    "G354k_12x3": grid(THREE),
}

def null_max(den, p_ref, axes, reps, rng, min_count_mask):
    """零效应 + 格间独立噪声:每格每折 δ ~ N(0, p(1-p)/den),经折最小 → 邻域最小 → 排序取首格的邻域分。"""
    sig = np.sqrt(p_ref * (1 - p_ref) / np.maximum(den, 1))
    vals = []
    for _ in range(reps):
        dl = sig * rng.standard_normal(sig.shape)
        s = np.where(min_count_mask, dl.min(-1), np.nan)
        snb, ne = neighbor_min(s, min_count_mask, axes)
        order = rank_cells(snb, ne)
        vals.append(float(snb.ravel()[order[0]]))
    return float(np.mean(vals)), float(np.std(vals, ddof=1))

def main():
    name = sys.argv[1]; B = int(sys.argv[2]) if len(sys.argv) > 2 else 100; MC = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    combo, preds = GRIDS[name]
    t0 = time.time()
    shards = sorted(LT.glob("part-*.parquet"))
    prep = prepare_shards(shards, combo, preds, "fold_Y", ["2024", "2025"])
    axes = list(range(prep.n_combo_axes + prep.n_pred_axes))
    ref_index = tuple(combo[a].index(REF[a]) for a in combo) + tuple(lv.index(REF[a]) for a, _, lv in preds)
    R = analyze_tensor(prep, ref_index, MC, axes)
    T = tensor(prep); den = T[..., 0] + T[..., 1] + T[..., 2]
    K = int(np.prod(R["s"].shape)); ev = R["evaluable"]
    c_hat = int(R["order"][0]); cidx = np.unravel_index(c_hat, R["s"].shape)
    naive = float(R["s_nb"].ravel()[c_hat])
    bs = bootstrap(prep, ref_index, MC, axes, B, 0, 20)
    shm = split_half_multi(prep, ref_index, MC, axes, range(10))
    p_ref = R["fp"][ref_index]
    rng = np.random.default_rng(1)
    nm, nsd = null_max(den, p_ref, axes, 30, rng, ev)
    # 事前公式:功效线处 σ × Φ⁻¹(1 − K^(−1/F)),F=2 折取最小
    F = 2
    z_K = float(stats.norm.isf(K ** (-1 / F))) if K > 1 else 0.0
    evc = R["count"].min(-1)[ev]
    se_ci = (bs["ci"][1] - bs["ci"][0]) / 3.92
    res = dict(grid=name, min_count=MC, ci=[round(x, 4) for x in bs["ci"]], se_ci=round(se_ci, 4), opt_over_seci=round(bs["optimism"] / se_ci, 2) if se_ci > 0 else None, K=K, n_eval=int(ev.sum()), rows_kept=int(prep.row_keep.sum()), n_sym=int(prep.n_sym),
               ref_count=[int(x) for x in R["count"][ref_index]], ref_fp=[round(float(x), 4) for x in p_ref],
               c_hat_count=[int(x) for x in R["count"][cidx]], c_hat_fp=[round(float(x), 4) for x in R["fp"][cidx]],
               naive=round(naive, 4), optimism=round(bs["optimism"], 4), optimism_se=round(bs["optimism_se"], 4), n_opt=bs["n_opt"],
               corrected=round(naive - bs["optimism"], 4), stability=round(bs["stability"], 3),
               split_half=round(shm["mean"], 4), split_half_se=round(shm["se"], 4), split_half_valid=shm["n_valid"],
               null_indep_max=round(nm, 4), null_indep_sd=round(nsd, 4),
               formula_zK=round(z_K, 3), formula_floor_n100_p05=round(0.5 / 10 * z_K, 4),
               eval_min_count_q=[int(x) for x in np.percentile(evc, [0, 10, 50, 90])] if len(evc) else None,
               B=B, secs=round(time.time() - t0, 1), peak_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024))
    print(json.dumps(res, ensure_ascii=False))
    with open(HERE / "e3_results.jsonl", "a") as fh:
        fh.write(json.dumps(res, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
