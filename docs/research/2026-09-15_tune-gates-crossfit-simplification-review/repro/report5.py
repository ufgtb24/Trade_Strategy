"""v5 汇总：推荐形态端到端（A1 / A1τ / A1τ+G1 / A1τ+G2 / 现行 validate），Q 口径。

用法：uv run python report5.py --tag v5
"""
import argparse

import numpy as np

from report2 import load
from sim import REF_FLAT

BANDS = ["全平", "小效应", "大效应", "工作点即最优"]
ARMS = [("A_m", "A1 朴素取最大 + 两段合并优效"), ("A1t", "A1τ 合并 SE 加 τ̂²"), ("A1t_G1", "A1τ + G1 选中格 ρ·d̄>δ"),
        ("A1t_G2", "A1τ + G2 bootstrap 校正后>0"), ("naive+v", "现行 validate（往后段非劣效+同号）")]


def perf(df, obj, noise):
    d = df[(df.obj == obj) & (df.noise == noise)]
    L = ["| 臂 | " + " | ".join(f"{b}：增益±MC SE / 差出δ / 写入 / 开窗" for b in BANDS) + " |", "|---|" + "---|" * len(BANDS)]
    for p, name in ARMS:
        cells = []
        for b in BANDS:
            g = d[(d.proc == p) & (d.band == b)]
            op = g.extra.mean() if p.startswith("A1t") else 1.0
            cells.append(f"{g.G_F.mean():+.2f}±{g.G_F.std(ddof=1) / np.sqrt(len(g)):.2f} / {(g.G_F < -g.dl).mean():.1%} / "
                         f"{(g.cell != REF_FLAT).mean():.0%} / {op:.0%}")
        L.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def report_bias(df, obj):
    L = ["| 臂 | 噪声 | 写入次数 | 原始合并估计 − 部署年真值：均值 / 中位 | 截断中位无偏校正 − 部署年真值：均值 / 中位 |",
         "|---|---|---|---|---|"]
    for p, name in ARMS[:4]:
        for n in ("N0", "N1", "N2"):
            d = df[(df.obj == obj) & (df.noise == n)]
            g = d[(d.proc == p) & (d.cell != REF_FLAT)]
            e1 = g.rep_val - g.G_F
            if p == "A_m":
                e2 = (g.extra - g.G_F).dropna(); tag = "（SE 只含抽样）"
            else:
                m = d[(d.proc == p + "_mue") & (d.cell != REF_FLAT)]
                e2 = m.rep_val - m.G_F; tag = "（SE 含 τ̂²）"
            L.append(f"| {name} | {n} | {len(g)} | {e1.mean():+.2f} / {e1.median():+.2f} | "
                     f"{e2.mean():+.2f} / {e2.median():+.2f}{tag} |")
    for n in ("N0", "N1", "N2"):
        g = df[(df.obj == obj) & (df.noise == n) & (df.proc == "naive+v") & (df.cell != REF_FLAT)]
        e1 = g.rep_val - g.G_F
        L.append(f"| 现行 validate（往后段估计） | {n} | {len(g)} | {e1.mean():+.2f} / {e1.median():+.2f} | — |")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v5")
    a = ap.parse_args()
    df = load(a.tag, 2)
    t = df[(df.proc == "A1t_mue") & (df.obj == "Q")].groupby("noise").extra.mean()
    print("τ̂² 训练期估计均值（Q，点²）：" + ", ".join(f"{k}={v:.2f}" for k, v in t.items()))
    for n in ("N0", "N1", "N2"):
        print(f"\n## Q {n}\n")
        print(perf(df, "Q", n))
    print("\n## 写入时报数 Q\n")
    print(report_bias(df, "Q"))


if __name__ == "__main__":
    main()
