"""补充检查:§3 推荐的 3 阶段 racing(20/50/100%)与 5 阶段在 D=3 上的预算/误淘汰对比。

用法:uv run python docs/research/2026-08-24_region-search-budget/repro/racing_stages_check.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from racing_sim import gen_universe, neighbor_lists, scores_from_counts, run_racing, make_effect  # noqa: E402


def main():
    N_STOCKS, LAM, SIGMA_U, L = 6000, 0.92, 0.5, 4
    RHOS = [0.8, 0.75, 0.85]
    BASE_FOLD = [0.46, 0.49, 0.55, 0.58]
    BETA, MIN_COUNT, B = 0.30, 100, 300
    DELTA, ALPHA = 0.01, 0.02
    STAGE_SETS = {"5阶段": [0.10, 0.20, 0.35, 0.55, 0.80, 1.0],
                  "3阶段": [0.20, 0.50, 1.0],
                  "2阶段": [0.30, 1.0]}
    N_SEEDS = 20
    SCENARIOS = ["strong", "plateau", "mostlybad", "collapse", "null"]
    D = 3
    print(f"D={D} seeds={N_SEEDS} δ={DELTA} α={ALPHA}")
    for scen in SCENARIOS:
        t0 = time.time()
        acc = {k: {"cost": [], "lost": [], "agree": [], "stages_evaluated": []} for k in STAGE_SETS}
        for seed in range(N_SEEDS):
            rng = np.random.default_rng(seed)
            counts, cell_arr = gen_universe(rng, n_stocks=N_STOCKS, lam=LAM, sigma_u=SIGMA_U, D=D, L=L,
                                            rhos=RHOS, base_fold=BASE_FOLD, effect_fn=make_effect(scen, BETA))
            nbrs = neighbor_lists(cell_arr, L)
            full = scores_from_counts(counts.sum(axis=0)[None], nbrs, ref=0, min_count=MIN_COUNT)[0]
            oracle_arg = int(np.argmax(full))
            oracle_region = full >= full.max() - DELTA
            for name, phis in STAGE_SETS.items():
                res = run_racing(rng, counts, nbrs, phis=phis, B=B, delta=DELTA, alpha=ALPHA,
                                 ref=0, min_count=MIN_COUNT)
                a = acc[name]
                a["cost"].append(res["cost_frac"])
                a["lost"].append(1 - np.mean(res["active"][oracle_region]))
                a["agree"].append(int(np.argmax(res["final"])) == oracle_arg)
                # 每阶段被评估格数之和(× t_fix 即固定开销)
                a["stages_evaluated"].append(sum(e for _, e, *_ in res["log"]) + int(res["active"].sum()))
        print(f"-- {scen} ({time.time() - t0:.0f}s)")
        for name in STAGE_SETS:
            a = acc[name]
            print(f"   {name}: cost {np.mean(a['cost']):.3f}  lost {np.mean(a['lost']):.3f}  "
                  f"agree {np.mean(a['agree']):.2f}  Σ(每阶段评估格数) {np.mean(a['stages_evaluated']):.0f}")


if __name__ == "__main__":
    main()
