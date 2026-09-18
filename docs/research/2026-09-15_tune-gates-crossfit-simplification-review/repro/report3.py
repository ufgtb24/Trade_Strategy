"""v3 汇总：写入门槛（合并确认窗 / 往后段非劣效 / CV 门 / 收缩门）端到端对比 + 写入时报数校正 + 近邻偏好。

用法：uv run python report3.py --tag v3
"""
import argparse

import numpy as np
import pandas as pd

from report2 import BANDS, load
from sim import AT, REF_FLAT

ARMS = [
    ("keep", "K0 维持工作点"),
    ("A_m", "A1 朴素取最大 + 合并确认优效"),
    ("A_mand", "A1' 朴素取最大 + 合并优效 且 往后段≥−δ"),
    ("Acv_m", "朴素取最大 + 整年留出>0 + 合并确认优效"),
    ("pk_loyog+v", "A2 朴素取最大 + 整年留出>0 + 往后段非劣效"),
    ("V2_m", "V2 ρ·d̄排序 + 合并确认优效"),
    ("V2_mand", "V2' ρ·d̄排序 + 合并优效 且 往后段≥−δ"),
    ("V2cv_m", "V2cv ρ·d̄排序 + 整年留出>0 + 合并确认优效"),
    ("V2k_m", "V2k 核平滑后验排序 + 合并确认优效"),
    ("SS_m", "尖峰加平板排序 + 合并确认优效"),
    ("cur_m", "现行规则排序 + 合并确认优效"),
    ("ePz_g", "E3 ρ·d̄>δ 直接换（无确认窗）"),
    ("ePz_lb", "ρ·d̄ 预测下界>0 直接换"),
    ("SS_gd", "尖峰加平板>δ 直接换"),
    ("eb2_gd", "核平滑后验>δ 直接换"),
    ("naive+v", "现行 validate：朴素取最大 + 往后段非劣效"),
    ("cur+v", "现行规则 + 往后段非劣效"),
    ("cur_gated+v", "现行规则 校正后>0 + 往后段非劣效"),
    ("cf_draft+v", "D 草案交叉拟合 + 往后段非劣效"),
    ("cf_draft_g+v", "D' 草案交叉拟合>0 + 往后段非劣效"),
]


def tbl(df, obj, noise):
    d = df[(df.obj == obj) & (df.noise == noise)]
    L = ["| 臂 | " + " | ".join(f"{b}：增益 / 误写 / 抓到 / 写入" for b in BANDS) + " |", "|---|" + "---|" * len(BANDS)]
    for p, name in ARMS:
        cells = []
        for b in BANDS:
            g = d[(d.proc == p) & (d.band == b)]
            if g.empty:
                cells.append("—"); continue
            w = g.cell != REF_FLAT
            # 抓到：同一 rep 里「朴素取最大选中格」平稳真增益 ≥ δ 时，本臂写入了（任何格）的比例
            ref = d[(d.proc == "naive") & (d.band == b)][["sid", "rep", "G_S"]].rename(columns={"G_S": "Gn"})
            gg = g.merge(ref, on=["sid", "rep"])
            big = gg.Gn >= gg.dl
            cap = (gg.cell[big] != REF_FLAT).mean() if big.any() else np.nan
            cells.append(f"{g.G_F.mean():+.2f} / {(w & (g.G_S <= 0)).mean():.0%} / "
                         + ("—" if not np.isfinite(cap) else f"{cap:.0%}") + f" / {w.mean():.0%}")
        L.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def tbl_report(df, obj):
    L = ["| 臂 | 写入时报数 − 部署年真值：原始合并估计（N0 / N1 / N2） | 截断中位无偏校正（N0 / N1 / N2） |", "|---|---|---|"]
    for p, name in ARMS:
        if not p.endswith("_m"):
            continue
        r1, r2 = [], []
        for n in ("N0", "N1", "N2"):
            g = df[(df.obj == obj) & (df.noise == n) & (df.proc == p) & (df.cell != REF_FLAT)]
            r1.append(f"{(g.rep_val - g.G_F).mean():+.2f}")
            e = (g.extra - g.G_F).dropna()
            r2.append(f"{e.mean():+.2f}（中位 {e.median():+.2f}）")
        L.append(f"| {name} | " + " / ".join(r1) + " | " + " / ".join(r2) + " |")
    return "\n".join(L)


def tbl_near(df, obj, noise):
    d = df[(df.obj == obj) & (df.noise == noise)].copy()
    d["dist"] = AT["dist"][REF_FLAT][d.cell.values]
    d["nr"] = AT["cell_mass"][d.cell.values] / AT["cell_mass"][REF_FLAT]
    L = ["| 排序规则 | 曲面 | 选中格离工作点档数（中位 / 均值） | 选中格买点数/工作点（中位） | 平稳增益 |", "|---|---|---|---|---|"]
    for p, name in (("naive", "朴素取最大"), ("cur", "现行规则"), ("ePz", "ρ·d̄ 排序"), ("SS", "尖峰加平板"),
                    ("eb_2way", "核平滑后验"), ("oracle", "oracle")):
        for s in ("mono", "plateau", "peak"):
            g = d[(d.proc == p) & (d.surface == s)]
            L.append(f"| {name} | {s} | {g.dist.median():.0f} / {g.dist.mean():.1f} | {g.nr.median():.2f} | {g.G_S.mean():+.2f} |")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v3")
    a = ap.parse_args()
    df = load(a.tag, 2)
    print(f"# {a.tag} 写入门槛端到端\n\n增益 = 部署年真实增益（相对维持工作点）；误写 = 写入且平稳真增益 ≤ 0；"
          "抓到 = 朴素取最大选中格平稳真增益 ≥ δ 的 rep 里本臂写入的比例；写入 = 写入率。\n")
    for obj in ("Q", "U"):
        for n in ("N1", "N0", "N2"):
            print(f"\n## {obj} {n}\n")
            print(tbl(df, obj, n))
        print(f"\n## 写入时报数 {obj}\n")
        print(tbl_report(df, obj))
        print(f"\n## 近邻偏好 {obj} N1（大小效应合并）\n")
        print(tbl_near(df, obj, "N1"))


if __name__ == "__main__":
    main()
