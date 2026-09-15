"""Q4 过拟合预算:权重可辨识性 + 选择偏差的量化。

三个数:
  ① 单个配置的 ΔFPR 自助 CI 半宽 —— 调参时能分辨的最小差异;
  ② 2024 窗上 255 组权重的 ΔFPR 极差 —— 权重选择"看起来"值多少;
  ③ 2024 择优出的权重落在 2025 全部权重结果分布的哪个分位 —— 选择偏差实测。
①≥② 即「权重不可辨识」:排名差异全在噪声内,拟合权重买不到东西。
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyze import atr_layers, layer_of, load                      # noqa: E402

FEATS = ["first_drought", "distinct_pk", "vol_spike", "peak_age"]
RNG = np.random.default_rng(20260907)
NBOOT = 2000
GRID = [0, 1, 2, 3]


def prep(tag):
    d, b = load(tag)
    cuts = atr_layers(b)
    d["layer"] = layer_of(d.atr_pct.values, cuts)
    b["layer"] = layer_of(b.atr_pct.values, cuts)
    base = {}
    for l, g in b.groupby("layer"):
        u, dn = (g.fp == "up").sum(), (g.fp == "down").sum()
        base[int(l)] = (float(g.fr.median()), u / (u + dn), len(g))
    for f in FEATS:
        d["r_" + f] = d[f].rank(pct=True)
    return d, base


def dfpr(up, dn, lay, base):
    u, d = up.sum(), dn.sum()
    if u + d == 0:
        return np.nan
    w = pd.Series(lay).value_counts(normalize=True)
    return u / (u + d) - sum(w.get(l, 0) * base[l][1] for l in base)


def top_dfpr(d, base, w, k):
    s = sum(wi * d["r_" + f].values for wi, f in zip(w, FEATS)) / sum(w)
    o = np.argsort(-s, kind="stable")[:k]
    return dfpr(d.fp_up.values[o], d.fp_down.values[o], d.layer.values[o], base)


if __name__ == "__main__":
    d24, b24 = prep("w2024")
    d25, b25 = prep("w2025")
    K24 = 400
    K25 = int(round(K24 / len(d24) * len(d25)))
    combos = [w for w in itertools.product(GRID, repeat=4) if sum(w) > 0]
    v24 = {w: top_dfpr(d24, b24, w, K24) for w in combos}
    v25 = {w: top_dfpr(d25, b25, w, K25) for w in combos}
    best24 = max(v24, key=v24.get)
    eq = (1, 1, 1, 1)

    syms = d25.symbol.values
    uniq = np.unique(syms)
    idx = {g: np.where(syms == g)[0] for g in uniq}
    up, dn, lay = d25.fp_up.values, d25.fp_down.values, d25.layer.values
    r_eq = sum(d25["r_" + f].values for f in FEATS) / 4
    r_b24 = sum(wi * d25["r_" + f].values for wi, f in zip(best24, FEATS)) / sum(best24)
    bs_eq, bs_diff = [], []
    for _ in range(NBOOT):
        pick = RNG.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx[g] for g in pick])
        oe = np.argsort(-r_eq[sel], kind="stable")[:K25]
        ob = np.argsort(-r_b24[sel], kind="stable")[:K25]
        a = dfpr(up[sel][oe], dn[sel][oe], lay[sel][oe], b25)
        c = dfpr(up[sel][ob], dn[sel][ob], lay[sel][ob], b25)
        bs_eq.append(a)
        bs_diff.append(c - a)
    bs_eq, bs_diff = np.array(bs_eq), np.array(bs_diff)

    print("═══ Q4 · 过拟合预算 ═══")
    print(f"准入量:2024 取分最高 {K24} 行(共 {len(d24)}),2025 取 {K25} 行(共 {len(d25)});"
          f"权重网格 {GRID}^4 去零 = {len(combos)} 组")
    print(f"\n① 单个配置的分辨力(等权分在 2025,按票整簇自助 {NBOOT} 次):")
    print(f"   ΔFPR = {v25[eq]:+.4f}  95%CI [{np.percentile(bs_eq,2.5):+.4f},"
          f"{np.percentile(bs_eq,97.5):+.4f}]  半宽 ≈ "
          f"{(np.percentile(bs_eq,97.5)-np.percentile(bs_eq,2.5))/2:.4f}")
    print(f"\n② 权重选择「看起来」值多少(2024 窗内 {len(combos)} 组的 ΔFPR 分布):")
    a24 = np.array(list(v24.values()))
    print(f"   min={a24.min():+.4f} p25={np.percentile(a24,25):+.4f} "
          f"p50={np.median(a24):+.4f} p75={np.percentile(a24,75):+.4f} max={a24.max():+.4f}"
          f"  (极差 {a24.max()-a24.min():.4f},max−p50 = {a24.max()-np.median(a24):.4f})")
    print(f"\n③ 2024 择优 w={best24}(2024 ΔFPR={v24[best24]:+.4f})拿到 2025:")
    a25 = np.array(list(v25.values()))
    pct = (a25 < v25[best24]).mean()
    print(f"   2025 ΔFPR={v25[best24]:+.4f},落在 2025 全部 {len(combos)} 组结果分布的 "
          f"第 {pct*100:.0f} 分位(2025 组内 min={a25.min():+.4f} p50={np.median(a25):+.4f} "
          f"max={a25.max():+.4f})")
    print(f"   等权 w={eq}:2024 ΔFPR={v24[eq]:+.4f} → 2025 ΔFPR={v25[eq]:+.4f}")
    print(f"   配对差(2024 择优权重 − 等权,同在 2025 上、同批重抽票)= {bs_diff.mean():+.4f} "
          f"[{np.percentile(bs_diff,2.5):+.4f},{np.percentile(bs_diff,97.5):+.4f}]  "
          f"P(>0)={np.mean(bs_diff>0):.3f}")
    print(f"\n④ 有效样本:准入 {K25} 个 match / {d25.iloc[np.argsort(-r_eq)[:K25]].symbol.nunique()} 只票"
          f" / {d25.iloc[np.argsort(-r_eq)[:K25]].cluster.nunique()} 个 burst 前缀族;"
          f"自由超参 = 4 权重(尺度不变 ⟹ 3 自由)+ 1 总阈值 = 4")
