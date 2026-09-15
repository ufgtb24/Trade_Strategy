"""放宽闸之后求解扛不扛得住:硬闸 vs 打分 的求解耗时/候选量对照(临时脚本)。

用法: uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_solve_cost.py
"""
from __future__ import annotations

import sys, time
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_scoring_where import build_scored          # noqa: E402
from path2_apps.bb_v1 import dag_spec as bb           # noqa: E402
from path2.dag.engine import analyze as engine_analyze, run_streams   # noqa: E402
from path2.dag._solve import compile_plan, solve      # noqa: E402


def main() -> None:
    DATA_DIR = REPO / "datasets" / "pkls"
    START, END = "2024-01-01", "2026-01-01"
    N_STOCK = 120
    # ================
    # 两套参数源都跑:dataclass 默认值(非 SSoT)与 params.yaml(SSoT,load_params)
    import os
    src = os.environ.get("PARAM_SRC", "yaml")
    params = bb.load_params() if src == "yaml" else bb.Params.default()
    print(f"参数源 = {src}  burst 闸 = "
          f"first_drought>={params.burst.first_drought_min} distinct_pk>={params.burst.distinct_pk_min} "
          f"vol_spike>={params.burst.vol_spike_min} peak_age>={params.burst.peak_age_min}")
    specs = {"硬闸(4 道 AND)": bb.build_pattern(params), "打分(1 条加权)": build_scored(params)}

    stats = {k: dict(t_detect=0.0, t_solve=0.0, n_burst=0, n_qual=0, n_sol=0, n_match=0, t_all=0.0)
             for k in specs}
    n_ok = 0
    for p in sorted(DATA_DIR.glob("*.pkl"))[:N_STOCK]:
        try:
            df = pd.read_pickle(p)
            df = df[(df["date"] >= START) & (df["date"] < END)].reset_index(drop=True) \
                if "date" in df.columns else df.loc[START:END]
            if len(df) < 200:
                continue
            for name, spec in specs.items():
                st = stats[name]
                t0 = time.perf_counter()
                streams = run_streams(spec, df, params)
                t1 = time.perf_counter()
                plan = compile_plan(spec)
                sols = solve(plan, streams)
                t2 = time.perf_counter()
                st["t_detect"] += t1 - t0
                st["t_solve"] += t2 - t1
                st["n_burst"] += len(streams.get("burst", []))
                bnode = next(n for n in spec.nodes if n.node_id == "burst")
                st["n_qual"] += sum(1 for e in streams.get("burst", [])
                                    if all(fn(e) for _, fn in bnode.where))
                st["n_sol"] += len(sols)
                t3 = time.perf_counter()
                st["n_match"] += len(engine_analyze(spec, df, params).matches)
                st["t_all"] += time.perf_counter() - t3
        except Exception as e:                          # noqa: BLE001
            print(f"  [skip] {p.stem}: {type(e).__name__}: {e}")
            continue
        n_ok += 1

    print(f"\n股票数 = {n_ok}\n")
    hdr = f"{'':16}{'burst 事件':>10}{'qualify':>9}{'solution':>10}{'match':>8}" \
          f"{'检测 s':>9}{'求解 s':>9}{'全链路 s':>10}"
    print(hdr)
    for name, st in stats.items():
        print(f"{name:16}{st['n_burst']:>10}{st['n_qual']:>9}{st['n_sol']:>10}{st['n_match']:>8}"
              f"{st['t_detect']:>9.2f}{st['t_solve']:>9.3f}{st['t_all']:>10.2f}")


if __name__ == "__main__":
    main()
