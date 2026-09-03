# -*- coding: utf-8 -*-
"""critic 量级实验:optimism 对「候选集大小」的敏感度 vs split-half 自身的噪声地板。

问题:跨轮数据暴露(第二轮换网格/删维)如果要进 optimism 公式,它能改动多少?
做法:拿 2026-08-25 已提交的真实长表,人为缩小候选集(逐条塌缩轴 = 该维没搜过),
     用**同一 seed**做配对比较,量 optimism 随候选集大小的变化幅度;
     再用多个 seed 量 split-half 的 seed 间散布,作为"精度地板"。
只读,不写 skill 目录。
"""
from __future__ import annotations

import json, subprocess, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import study_io as S  # noqa: E402
from region_core import analyze_tensor, bootstrap, prepare, split_half  # noqa: E402


def main() -> None:
    LT = REPO / "docs/research/2026-08-25_multivar-bb_v1/longtable"
    FOLD_COL, FOLDS = "fold_Y", ["2024", "2025"]
    MIN_COUNT, SEED = 100, 0
    B = 300
    SPLIT_SEEDS = list(range(20))

    cl = json.loads((REPO / ".claude/skills/tune-gates/apps/bb_v1/classification.json").read_text())
    combo_full, preds_full = S.derived_axes(cl)
    df = pd.concat([pd.read_parquet(p) for p in sorted(LT.glob("part-*.parquet"))], ignore_index=True)
    print(f"长表 {len(df)} 行 / {df['symbol'].nunique()} 股", flush=True)

    def run(combo, preds, tag, do_boot=True):
        t0 = time.time()
        prep = prepare(df, combo, preds, FOLD_COL, FOLDS)
        n_ax = prep.n_combo_axes + prep.n_pred_axes
        axes = list(range(n_ax))
        ref_index = tuple(combo[c].index(cl["ref_point"][c]) for c in combo) + (0,) * prep.n_pred_axes
        R = analyze_tensor(prep, ref_index, MIN_COUNT, axes)
        shape = R["s_nb"].shape; n_cells = int(np.prod(shape))
        c_hat = int(R["order"][0]); naive = float(R["s_nb"].ravel()[c_hat])
        row = dict(tag=tag, n_cells=n_cells, shape=shape, naive=naive)
        if do_boot:
            bs = bootstrap(prep, ref_index, MIN_COUNT, axes, B, SEED, 20)
            row.update(optimism=bs["optimism"], opt_se=bs["optimism_se"], n_opt=bs["n_opt"],
                       stability=bs["stability"])
            row["split_half"] = split_half(prep, ref_index, MIN_COUNT, axes, SEED)
        print(f"  [{tag}] cells={n_cells} naive={naive:.4f} "
              f"opt={row.get('optimism', float('nan')):.4f}±{row.get('opt_se', float('nan')):.4f} "
              f"sh={row.get('split_half', float('nan')):.4f}  ({time.time()-t0:.0f}s)", flush=True)
        return row, prep, ref_index, axes

    print("\n=== 1. 全网格(应复现已提交的 naive=0.0705 / opt=0.1263 / sh=-0.1319) ===", flush=True)
    full, prep_f, ref_f, axes_f = run(combo_full, preds_full, "full")

    print("\n=== 2. 逐条塌缩一根轴(= 该维这轮没搜)——配对同 seed ===", flush=True)
    rows = [full]
    combo_names = list(combo_full)
    for c in combo_names:
        sub = {k: (v if k != c else [cl["ref_point"][k]]) for k, v in combo_full.items()}
        rows.append(run(sub, preds_full, f"drop_combo:{c}")[0])
    for j, (col, op, lv) in enumerate(preds_full):
        sub_p = [(c2, o2, (l2 if i != j else [l2[0]])) for i, (c2, o2, l2) in enumerate(preds_full)]
        rows.append(run(combo_full, sub_p, f"drop_pred:{col}")[0])

    print("\n=== 3. 大幅缩小候选集(同时塌缩多根轴) ===", flush=True)
    for k in (2, 4, 6):
        sub_c = {kk: (vv if i >= k else [cl["ref_point"][kk]]) for i, (kk, vv) in enumerate(combo_full.items())}
        sub_p = preds_full if k <= len(combo_full) else preds_full
        rows.append(run(sub_c, sub_p, f"collapse_first_{k}_combo")[0])

    print("\n=== 4. split-half 的 seed 间散布(噪声地板) ===", flush=True)
    shs = []
    for sd in SPLIT_SEEDS:
        v = split_half(prep_f, ref_f, MIN_COUNT, axes_f, sd)
        shs.append(v); print(f"  seed={sd:>2} split_half={v:.4f}", flush=True)
    shs = np.array(shs, dtype=float)
    fin = shs[np.isfinite(shs)]
    print(f"\nsplit_half over {len(fin)} seeds: mean={fin.mean():.4f} sd={fin.std(ddof=1):.4f} "
          f"min={fin.min():.4f} max={fin.max():.4f} range={fin.max()-fin.min():.4f}", flush=True)

    out = Path(__file__).parent / "optimism_vs_gridsize.json"
    out.write_text(json.dumps({"rows": [{k: (list(v) if isinstance(v, tuple) else v) for k, v in r.items()} for r in rows],
                               "split_half_seeds": {"seeds": SPLIT_SEEDS, "values": shs.tolist(),
                                                    "sd": float(fin.std(ddof=1)), "mean": float(fin.mean())}},
                              ensure_ascii=False, indent=1))
    print(f"\n写入 {out}")


if __name__ == "__main__":
    main()
