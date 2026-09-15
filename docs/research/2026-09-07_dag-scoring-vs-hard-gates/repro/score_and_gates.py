"""Q3 放宽代价曲线 + Q5 单闸阈值扫描 + Q4 时间外推。

- 单闸扫描:每个 burst 量沿自身分位扫阈值,报「过闸子集 ΔFPR / Δmed_fr(层匹配基线)」
  与样本量,回答「这道闸有没有实证支持、阈值该不该在这」。
- 加权分:先用等权分位秩(0..1 各量),再扫总阈值,画样本量 ↔ 收益的权衡曲线,
  与同样本量下的 AND 硬闸、单闸 distinct_pk 对照。
- 时间外推:2024 窗调权重 → 2025 窗验证,看衰减。
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
from factorial_ci import cell_delta                                 # noqa: E402

FEATS = ["first_drought", "distinct_pk", "vol_spike", "peak_age"]
GATES = {"yaml": dict(first_drought=40, distinct_pk=3, vol_spike=3.0, peak_age=60),
         "dataclass": dict(first_drought=20, distinct_pk=4, vol_spike=8.0, peak_age=125)}


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


def quick(sub, base):
    """无 CI 的快速 Δ(扫曲线用)。"""
    if len(sub) == 0:
        return dict(n=0, d_fpr=np.nan, d_fr=np.nan, fpr=np.nan, med_fr=np.nan, n_sym=0)
    u, dn = sub.fp_up.sum(), sub.fp_down.sum()
    fpr = u / (u + dn) if (u + dn) else np.nan
    med = float(sub.fr.median())
    w = sub.layer.value_counts(normalize=True)
    bf = sum(w.get(l, 0) * base[l][1] for l in base)
    bm = sum(w.get(l, 0) * base[l][0] for l in base)
    return dict(n=len(sub), n_sym=sub.symbol.nunique(), fpr=fpr, med_fr=med,
                d_fpr=fpr - bf, d_fr=med - bm)


def main():
    print("═══════ Q5 · 单闸阈值扫描(过闸子集 vs 波动率层匹配基线) ═══════")
    for tag in ["w2025", "w2024"]:
        d, base = prep(tag)
        allr = quick(d, base)
        print(f"\n── {tag} · 全体宽进 n={allr['n']} ΔFPR={allr['d_fpr']:+.4f} "
              f"Δmed_fr={allr['d_fr']:+.4f} ──")
        for f in FEATS:
            print(f"  [{f}]  (现役 yaml 阈值 {GATES['yaml'][f]} / 代码兜底 {GATES['dataclass'][f]})")
            ths = sorted(set(np.round(d[f].quantile(np.arange(0.1, 1.0, 0.1)).values, 4)))
            ths += [GATES["yaml"][f], GATES["dataclass"][f]]
            for t in sorted(set(ths)):
                r = quick(d[d[f] >= t], base)
                if r["n"] < 30:
                    continue
                mark = ""
                if t == GATES["yaml"][f]:
                    mark += " ←yaml"
                if t == GATES["dataclass"][f]:
                    mark += " ←dataclass"
                print(f"    >={t:>10.4g}  n={r['n']:>5} sym={r['n_sym']:>4}  "
                      f"ΔFPR={r['d_fpr']:+.4f}  Δmed_fr={r['d_fr']:+.4f}{mark}")

    print("\n\n═══════ Q3 · 等权分位秩加权分的放宽代价曲线 ═══════")
    for tag in ["w2025", "w2024"]:
        d, base = prep(tag)
        d["score"] = d[["r_" + f for f in FEATS]].mean(axis=1)
        allr = quick(d, base)
        print(f"\n── {tag} · 全体 n={allr['n']} ΔFPR={allr['d_fpr']:+.4f} "
              f"Δmed_fr={allr['d_fr']:+.4f}(这是「完全不设闸」的对照) ──")
        for q in [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.92, 0.95, 0.97, 0.99]:
            t = d.score.quantile(q)
            r = quick(d[d.score >= t], base)
            print(f"  score>=P{int(q*100):<3} n={r['n']:>5} sym={r['n_sym']:>4}  "
                  f"ΔFPR={r['d_fpr']:+.4f}  Δmed_fr={r['d_fr']:+.4f}")
        # 同样本量对照
        for gname, G in GATES.items():
            m = np.logical_and.reduce([d[f] >= G[f] for f in FEATS])
            rg = quick(d[m], base)
            if rg["n"] == 0:
                continue
            k = rg["n"]
            r_sc = quick(d.nlargest(k, "score"), base)
            r_pk = quick(d.nlargest(k, "r_distinct_pk"), base)
            print(f"  ▶ 同准入量 n≈{k} 三路对照 [{gname}]:  "
                  f"AND 硬闸 ΔFPR={rg['d_fpr']:+.4f} | "
                  f"等权分 ΔFPR={r_sc['d_fpr']:+.4f} | "
                  f"只用 distinct_pk ΔFPR={r_pk['d_fpr']:+.4f}")

    print("\n\n═══════ Q4 · 时间外推:2024 调权重 → 2025 验证 ═══════")
    d24, b24 = prep("w2024")
    d25, b25 = prep("w2025")
    grid = [0, 1, 2, 3]
    best, rows = None, []
    K24 = 400   # 固定准入量,只让权重变(否则等于同时调阈值)
    for w in itertools.product(grid, repeat=4):
        if sum(w) == 0:
            continue
        s24 = sum(wi * d24["r_" + f] for wi, f in zip(w, FEATS)) / sum(w)
        r = quick(d24.assign(s=s24).nlargest(K24, "s"), b24)
        rows.append((w, r["d_fpr"]))
        if best is None or r["d_fpr"] > best[1]:
            best = (w, r["d_fpr"])
    rows.sort(key=lambda x: -x[1])
    print(f"  2024 窗上按 ΔFPR 择优(准入量固定 {K24}),共 {len(rows)} 组权重")
    for w, v in rows[:5]:
        s25 = sum(wi * d25["r_" + f] for wi, f in zip(w, FEATS)) / sum(w)
        K25 = int(round(K24 / len(d24) * len(d25)))
        r25 = quick(d25.assign(s=s25).nlargest(K25, "s"), b25)
        print(f"    w={w}  2024 ΔFPR={v:+.4f}  →  2025 ΔFPR={r25['d_fpr']:+.4f} (n={r25['n']})")
    eq = (1, 1, 1, 1)
    s24e = sum(d24["r_" + f] for f in FEATS) / 4
    s25e = sum(d25["r_" + f] for f in FEATS) / 4
    K25 = int(round(K24 / len(d24) * len(d25)))
    print(f"    w={eq} 等权   2024 ΔFPR={quick(d24.assign(s=s24e).nlargest(K24,'s'), b24)['d_fpr']:+.4f}"
          f"  →  2025 ΔFPR={quick(d25.assign(s=s25e).nlargest(K25,'s'), b25)['d_fpr']:+.4f}")
    print(f"    2024 最优权重在 2024 上的 ΔFPR = {rows[0][1]:+.4f};"
          f" 2024 全部 {len(rows)} 组权重在 2024 上的 ΔFPR 分布: "
          f"p50={np.median([v for _, v in rows]):+.4f} max={rows[0][1]:+.4f} min={rows[-1][1]:+.4f}")
    # 2025 上的真最优,量「本可以拿到多少」
    best25 = max(
        ((w, quick(d25.assign(s=sum(wi * d25['r_' + f] for wi, f in zip(w, FEATS)) / sum(w))
                   .nlargest(K25, "s"), b25)["d_fpr"])
         for w in itertools.product(grid, repeat=4) if sum(w) > 0),
        key=lambda x: x[1])
    print(f"    2025 窗自身最优权重 w={best25[0]} ΔFPR={best25[1]:+.4f}"
          f"(= 事后诸葛的上限,与上面「2024 选出的权重在 2025 的表现」之差 = 过拟合代价)")


if __name__ == "__main__":
    main()
