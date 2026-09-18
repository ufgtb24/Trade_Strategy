"""v4 汇总：合并门三种写法 + 幸存者平移对照；red-team 的三种开窗前门。

用法：uv run python report4.py --tag v4
"""
import argparse

import numpy as np
import pandas as pd

from report2 import BANDS, load
from sim import REF_FLAT

MERGED = [("A_m", "只合并优效"), ("A_mand", "合并优效 且 往后段点估计≥−δ"), ("A_mnil", "合并优效 且 往后段非劣效下界≥−δ"),
          ("A_mb0", "只合并优效（往前段无幸存者平移）"), ("naive+v", "现行 validate（往后段非劣效+同号）")]


def cap_table(df, obj):
    """真增益≥δ 时的写入率（朴素取最大选中格平稳真增益 ≥ δ 的 rep）、纯噪声（全平）写入率、部署年增益。"""
    L = ["| 写法 | " + " | ".join(f"{n}：抓到 / 全平写入 / 工作点最优写入 / 增益(小/大/最优)" for n in ("N0", "N1", "N2")) + " |",
         "|---|---|---|---|"]
    for p, name in MERGED:
        cells = []
        for n in ("N0", "N1", "N2"):
            d = df[(df.obj == obj) & (df.noise == n)]
            g = d[d.proc == p]
            ref = d[d.proc == "naive"][["sid", "rep", "G_S"]].rename(columns={"G_S": "Gn"})
            gg = g.merge(ref, on=["sid", "rep"])
            big = gg.Gn >= gg.dl
            cap = (gg.cell[big] != REF_FLAT).mean()
            wflat = (g[g.band == "全平"].cell != REF_FLAT).mean()
            wopt = (g[g.band == "工作点即最优"].cell != REF_FLAT).mean()
            gain = "/".join(f"{g[g.band == b].G_F.mean():+.2f}" for b in ("小效应", "大效应", "工作点即最优"))
            cells.append(f"{cap:.0%} / {wflat:.0%} / {wopt:.0%} / {gain}")
        L.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def pregate_table(df, obj, noise):
    d = df[(df.obj == obj) & (df.noise == noise)]
    bands = ["全平", "小效应", "大效应", "工作点即最优"]
    L = ["| 排序 · 开窗前门 | " + " | ".join(f"{b}：开窗 / 误写 / 增益" for b in bands) + " |", "|---|" + "---|" * len(bands)]
    for r, rn in (("A", "argmax"), ("V2", "ρ·d̄")):
        for pg, pn in (("none", "不设门"), ("m2", "跨年二阶矩>0"), ("rho", "最高格 ρ·d̄>0"), ("cv", "整年留出 CV>0")):
            cells = []
            for b in bands:
                g = d[(d.proc == f"{r}_pre_{pg}") & (d.band == b)]
                w = g.cell != REF_FLAT
                cells.append(f"{g.extra.mean():.0%} / {(w & (g.G_S <= 0)).mean():.1%} / {g.G_F.mean():+.2f}")
            L.append(f"| {rn} · {pn} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v4")
    a = ap.parse_args()
    df = load(a.tag, 2)
    for obj in ("Q", "U"):
        print(f"\n## 合并门写法 {obj}\n")
        print(cap_table(df, obj))
        for n in ("N1", "N0", "N2"):
            print(f"\n## 开窗前门（后接合并优效门 + 往后段显著劣于则撤回）{obj} {n}\n")
            print(pregate_table(df, obj, n))


if __name__ == "__main__":
    main()
