"""2×2 析因的 Δ(格 − 波动率层匹配基线)与整簇自助 CI。

Δ 的自助:每次重抽 symbol(整簇),同时重算格内 FPR / med_fr 与该次重抽下的层权
重加权基线,取差 —— 基线随权重一起抖,CI 才覆盖「层分布本身不确定」这部分。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyze import atr_layers, layer_of, load                      # noqa: E402

NBOOT = 2000
RNG = np.random.default_rng(20260907)


def cell_delta(sub, base_by_layer, nboot=NBOOT):
    """返回 (ΔFPR, ΔFPR_CI, Δmed_fr, Δmed_fr_CI, n)。"""
    if len(sub) < 5:
        return dict(n=len(sub))
    lay = sub.layer.values
    up, dn, fr = sub.fp_up.values, sub.fp_down.values, sub.fr.values
    syms = sub.symbol.values
    uniq = np.unique(syms)
    idx = {g: np.where(syms == g)[0] for g in uniq}

    def one(sel):
        u, d = up[sel].sum(), dn[sel].sum()
        f = u / (u + d) if (u + d) else np.nan
        m = np.median(fr[sel])
        w = pd.Series(lay[sel]).value_counts(normalize=True)
        bf = sum(w.get(l, 0) * base_by_layer[l][1] for l in base_by_layer)
        bm = sum(w.get(l, 0) * base_by_layer[l][0] for l in base_by_layer)
        return f - bf, m - bm

    d_fpr, d_fr = one(np.arange(len(sub)))
    bs = []
    for _ in range(nboot):
        pick = RNG.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx[g] for g in pick])
        bs.append(one(sel))
    bs = np.array([b for b in bs if np.isfinite(b[0])])
    return dict(n=len(sub), n_sym=len(uniq),
                d_fpr=d_fpr, d_fpr_ci=(np.percentile(bs[:, 0], 2.5), np.percentile(bs[:, 0], 97.5)),
                d_fr=d_fr, d_fr_ci=(np.percentile(bs[:, 1], 2.5), np.percentile(bs[:, 1], 97.5)))


def main():
    pairs = [("vol_spike", "distinct_pk"), ("vol_spike", "first_drought"),
             ("vol_spike", "peak_age"), ("distinct_pk", "first_drought"),
             ("distinct_pk", "peak_age"), ("first_drought", "peak_age")]
    GATES = {"yaml": dict(first_drought=40, distinct_pk=3, vol_spike=3.0, peak_age=60),
             "dataclass": dict(first_drought=20, distinct_pk=4, vol_spike=8.0, peak_age=125)}
    for tag in ["w2025", "w2024"]:
        d, b = load(tag)
        cuts = atr_layers(b)
        d["layer"] = layer_of(d.atr_pct.values, cuts)
        b["layer"] = layer_of(b.atr_pct.values, cuts)
        base_by_layer = {}
        for l, g in b.groupby("layer"):
            u, dn = (g.fp == "up").sum(), (g.fp == "down").sum()
            base_by_layer[int(l)] = (float(g.fr.median()), u / (u + dn), len(g))
        print(f"\n════ {tag} · Δ = 格 − 波动率层匹配基线(整簇自助 95% CI, symbol 为簇) ════")
        for gname, G in GATES.items():
            for a, bb in pairs:
                ta, tb_ = G[a], G[bb]
                print(f"\n  [{gname}] {a}>={ta} × {bb}>={tb_}")
                hi_a, hi_b = d[a] >= ta, d[bb] >= tb_
                for na, ma in [("高", hi_a), ("低", ~hi_a)]:
                    for nb, mb in [("高", hi_b), ("低", ~hi_b)]:
                        r = cell_delta(d[ma & mb], base_by_layer)
                        nm = f"{a[:4]}{na}·{bb[:4]}{nb}"
                        if "d_fpr" not in r:
                            print(f"    {nm:<20} n={r['n']}")
                            continue
                        s = " ⚠小样本" if r["n"] < 30 else ""
                        print(f"    {nm:<20} n={r['n']:>5} sym={r['n_sym']:>4} | "
                              f"ΔFPR={r['d_fpr']:+.4f} [{r['d_fpr_ci'][0]:+.4f},{r['d_fpr_ci'][1]:+.4f}] | "
                              f"Δmed_fr={r['d_fr']:+.4f} [{r['d_fr_ci'][0]:+.4f},{r['d_fr_ci'][1]:+.4f}]{s}")


if __name__ == "__main__":
    main()
