# -*- coding: utf-8 -*-
"""必要性分析 Q3(直答版):两轮搜索、第二轮删掉一维,第二轮报告的 optimism 低估了多少?

被模拟的真实场景(前序报告 §3.2 点名的"最隐蔽的一种"):
  第一轮 在全网格上跑 → 看到某维全负 → 第二轮把该维从网格里删掉(锁死在它最好的档)
  → 在子网格上取 argmax、报告 optimism。

三个数字:
  opt_sub   = 第二轮实际报告的值(bootstrap 只在子网格上取 argmax)——现状
  opt_2stage= 把"删维"本身当成流程的一部分、每个 bootstrap 副本都重跑整套两段流程后的值
              ——这才是这个流程真实的选择偏差(正确估计量)
  opt_full  = 直接在全网格上取 argmax 的值(删维决策的信息上界)
低估量 = opt_2stage − opt_sub。数据同 optimism_vs_gridsize.py:纯 null + 格间独立(上界口径)。
"""
from __future__ import annotations
import subprocess, sys, time
from pathlib import Path
import os
import numpy as np, pandas as pd

KEEP_RULE = os.environ.get("KEEP_RULE", "best")   # best=锁在该维当前最好的档;base=锁在底座档(下标 0)

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
from region_core import prepare, analyze_tensor  # noqa: E402

N_AXES, N_LEV = 5, 4
N_SYM, ROWS_PER_SYM = 400, 1000
FOLDS = ["2024", "2025"]
MIN_COUNT, B, R = 100, 200, 5
AXES = list(range(N_AXES))
REF = (0,) * N_AXES


def make_null(seed):
    rng = np.random.default_rng(seed)
    n = N_SYM * ROWS_PER_SYM
    d = {f"d{a}": rng.integers(0, N_LEV, n) for a in range(N_AXES)}
    up = rng.random(n) < 0.5
    return pd.DataFrame({**d, "symbol": np.repeat(np.arange(N_SYM), ROWS_PER_SYM).astype(str),
                         "fold_Y": rng.choice(FOLDS, n), "fp_up": up.astype(int),
                         "fp_down": (~up).astype(int), "fp_both": 0, "fp_none": 0})


def full_levels():
    return {f"d{a}": list(range(N_LEV)) for a in range(N_AXES)}


def sub_levels(drop_ax, keep_lv):
    return {f"d{a}": ([keep_lv] if a == drop_ax else list(range(N_LEV))) for a in range(N_AXES)}


def choose_drop(res_full):
    """删维规则(对齐"看到某维全负/没影响就删掉"这个真实决策):
    对每条轴算"逐档均值"(在其余轴上取 nanmean),该轴的影响力 = 逐档均值的极差;
    影响力最小的轴 = 换档基本不改变分数的那条轴,删之。锁死的档位:
      KEEP_RULE=best → 该轴逐档均值最高的档;KEEP_RULE=base → 底座档(下标 0)。
    注意:第一版规则(每轴取"该轴上 s_nb 的最大值")是**错的**——它对每条轴都等于全网格
    的同一个全局最大值,argmin 恒返回 0 号轴,决策与数据无关、两段式退化成固定子网格
    (低估量恒等于 0,是算术恒等式而不是实证结论)。
    """
    s_ = res_full["s_nb"]
    s_fin = np.where(np.isfinite(s_), s_, np.nan)
    level_mean = []
    for a in AXES:
        others = tuple(i for i in AXES if i != a)
        with np.errstate(invalid="ignore"):
            m = np.nanmean(s_fin, axis=others)          # 长度 N_LEV:该轴每一档的均值
        level_mean.append(np.where(np.isfinite(m), m, -np.inf))
    influence = [float(np.max(m) - np.min(m)) for m in level_mean]
    drop = int(np.argmin(influence))
    keep_lv = int(np.argmax(level_mean[drop])) if KEEP_RULE == "best" else 0
    return drop, keep_lv


def main():
    t0 = time.time(); recs = []
    for r in range(R):
        df = make_null(2000 + r)
        prep_full = prepare(df, full_levels(), [], "fold_Y", FOLDS)
        preps = {(a, l): prepare(df, sub_levels(a, l), [], "fold_Y", FOLDS)
                 for a in AXES for l in range(N_LEV)}
        assert all(p.n_sym == prep_full.n_sym for p in preps.values()), "子网格丢了 symbol,权重对不齐"
        n_sym = prep_full.n_sym

        base_full = analyze_tensor(prep_full, REF, MIN_COUNT, AXES)
        drop0, lv0 = choose_drop(base_full)                     # 原始数据上人做的那次删维
        prep_sub0 = preps[(drop0, lv0)]
        base_sub0 = analyze_tensor(prep_sub0, REF, MIN_COUNT, AXES)
        c_sub0 = int(base_sub0["order"][0])
        s0_sub0 = base_sub0["s_nb"].ravel()
        s0_full = base_full["s_nb"].ravel()

        rng = np.random.default_rng(0)
        o_sub, o_2s, o_full = [], [], []
        for _ in range(B):
            w = rng.multinomial(n_sym, np.full(n_sym, 1.0 / n_sym))
            # (1) 现状:只在固定子网格上重跑
            rb = analyze_tensor(prep_sub0, REF, MIN_COUNT, AXES, weights=w)
            cb = int(rb["order"][0])
            if np.isfinite(rb["s_nb"].ravel()[cb]) and np.isfinite(s0_sub0[cb]):
                o_sub.append(rb["s_nb"].ravel()[cb] - s0_sub0[cb])
            # (2) 正确估计量:整套两段流程(全网格 → 删维 → 子网格 argmax)每副本重跑
            rf = analyze_tensor(prep_full, REF, MIN_COUNT, AXES, weights=w)
            db, lb = choose_drop(rf)
            p2 = preps[(db, lb)]
            r2b = analyze_tensor(p2, REF, MIN_COUNT, AXES, weights=w)
            r20 = analyze_tensor(p2, REF, MIN_COUNT, AXES)       # 同网格、原始数据
            c2 = int(r2b["order"][0])
            if np.isfinite(r2b["s_nb"].ravel()[c2]) and np.isfinite(r20["s_nb"].ravel()[c2]):
                o_2s.append(r2b["s_nb"].ravel()[c2] - r20["s_nb"].ravel()[c2])
            # (3) 全网格 argmax
            cf = int(rf["order"][0])
            if np.isfinite(rf["s_nb"].ravel()[cf]) and np.isfinite(s0_full[cf]):
                o_full.append(rf["s_nb"].ravel()[cf] - s0_full[cf])
        rec = dict(rep=r, drop_axis=drop0, keep_lv=lv0,
                   naive_sub=float(s0_sub0[c_sub0]),
                   opt_sub=float(np.mean(o_sub)), opt_2stage=float(np.mean(o_2s)),
                   opt_full=float(np.mean(o_full)),
                   se_sub=float(np.std(o_sub, ddof=1) / np.sqrt(len(o_sub))),
                   se_2stage=float(np.std(o_2s, ddof=1) / np.sqrt(len(o_2s))))
        rec["under"] = rec["opt_2stage"] - rec["opt_sub"]
        recs.append(rec)
        print(f"rep{r} 删轴 d{drop0}@档{lv0} | naive {rec['naive_sub']:+.4f} | "
              f"opt_sub {rec['opt_sub']:+.4f}±{rec['se_sub']:.4f}  "
              f"opt_2stage {rec['opt_2stage']:+.4f}±{rec['se_2stage']:.4f}  "
              f"opt_full {rec['opt_full']:+.4f} | 低估 {rec['under']:+.4f}  [{time.time()-t0:.0f}s]")
    out = pd.DataFrame(recs); out.to_csv(Path(__file__).parent / f"two_stage_optimism_{KEEP_RULE}.csv", index=False)
    print("\n=== 均值(R={}) ===".format(R))
    print(out[["naive_sub", "opt_sub", "opt_2stage", "opt_full", "under"]].mean().to_string(float_format=lambda x: f"{x:+.4f}"))
    print(f"\n低估量 / opt_2stage = {out['under'].mean() / out['opt_2stage'].mean():.1%}")


if __name__ == "__main__":
    main()
