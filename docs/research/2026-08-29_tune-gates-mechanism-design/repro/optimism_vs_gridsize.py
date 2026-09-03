# -*- coding: utf-8 -*-
"""必要性分析 Q3 的量级模拟:optimism 随候选格数 m 怎么变。

问题:第二轮把某维从网格里删掉(新网格 ⊂ 旧网格),报告出来的 optimism 是按新网格(小 m)算的,
真实搜索空间是旧网格(大 m)。低估多少?

做法:用 region_core 真实的 bootstrap(),在**纯 null 合成数据**(格与结果完全独立)上,
对同一份数据用不同大小的网格各跑一次,比较 optimism。null 是选择偏差的最大情形
(有真实结构时 optimism 期望值可为负,见 region_core.bootstrap 文档),且合成数据里
各格样本互相独立——真实长表里同一个 match 会出现在很多格、格间强相关,等效独立候选数
远小于 m,所以本模拟给出的是「m 的影响」的**上界**。

注:真实长表上的对照实验是 critic 做的 critic_optimism_vs_gridsize.py(同目录),
两者互补——本脚本便宜可复现、覆盖 m 的连续变化;那个贵但有真实结构。
"""
from __future__ import annotations
import subprocess, sys, time
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
from region_core import prepare, bootstrap, analyze_tensor, split_half  # noqa: E402

N_AXES, N_LEV = 5, 4          # 全网格 4^5 = 1024 格
N_SYM, ROWS_PER_SYM = 400, 1000
FOLDS = ["2024", "2025"]
MIN_COUNT = 100
B, SEED_BOOT = 200, 0
R = 8                          # 数据重复次数


def make_null(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = N_SYM * ROWS_PER_SYM
    d = {f"d{a}": rng.integers(0, N_LEV, n) for a in range(N_AXES)}
    up = rng.random(n) < 0.5                      # 与格坐标完全独立 = null
    return pd.DataFrame({**d,
                         "symbol": np.repeat(np.arange(N_SYM), ROWS_PER_SYM).astype(str),
                         "fold_Y": rng.choice(FOLDS, n),
                         "fp_up": up.astype(int), "fp_down": (~up).astype(int),
                         "fp_both": 0, "fp_none": 0})


def run(df, n_free_axes: int):
    """n_free_axes 个轴保留 N_LEV 档,其余轴锁死 1 档 → m = N_LEV**n_free_axes 格。"""
    combo = {f"d{a}": list(range(N_LEV)) if a < n_free_axes else [0] for a in range(N_AXES)}
    prep = prepare(df, combo, [], "fold_Y", FOLDS)
    axes = list(range(N_AXES))
    ref = (0,) * N_AXES
    base = analyze_tensor(prep, ref, MIN_COUNT, axes)
    c = int(base["order"][0])
    naive = float(base["s_nb"].ravel()[c])
    bs = bootstrap(prep, ref, MIN_COUNT, axes, B, SEED_BOOT, 20)
    sh = split_half(prep, ref, MIN_COUNT, axes, SEED_BOOT)
    return dict(m=N_LEV ** n_free_axes, naive=naive, optimism=bs["optimism"],
                opt_se=bs["optimism_se"], stability=bs["stability"], split_half=sh)


def main():
    t0 = time.time()
    recs = []
    for r in range(R):
        df = make_null(1000 + r)
        for k in (1, 2, 3, 4, 5):
            rec = run(df, k); rec["rep"] = r; recs.append(rec)
            print(f"rep{r} m={rec['m']:5d} naive={rec['naive']:+.4f} opt={rec['optimism']:+.4f}"
                  f" (se {rec['opt_se']:.4f}) split_half={rec['split_half']:+.4f} stab={rec['stability']:.2f}"
                  f"  [{time.time()-t0:.0f}s]")
    out = pd.DataFrame(recs)
    g = out.groupby("m").agg(naive=("naive", "mean"), optimism=("optimism", "mean"),
                             opt_sd=("optimism", "std"), split_half=("split_half", "mean"))
    g["sqrt2lnm"] = np.sqrt(2 * np.log(g.index.values))
    g["opt/sqrt2lnm"] = g["optimism"] / g["sqrt2lnm"]
    print("\n=== 汇总(R={} 次重复的均值) ===".format(R))
    print(g.to_string(float_format=lambda x: f"{x:+.4f}"))
    out.to_csv(Path(__file__).parent / "optimism_vs_gridsize.csv", index=False)
    print("\n=== 关键差值(m 缩小时 optimism 被低估多少) ===")
    for a, b in ((1024, 256), (1024, 64), (256, 64), (256, 16)):
        d = g.loc[a, "optimism"] - g.loc[b, "optimism"]
        print(f"  m {a}→{b}({a//b}×收缩): optimism 差 {d:+.4f} "
              f"(相对 m={a} 的 {100*d/g.loc[a,'optimism']:.1f}%)")


if __name__ == "__main__":
    main()
