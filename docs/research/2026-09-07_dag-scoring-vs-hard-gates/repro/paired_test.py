"""同准入量下「等权分 vs AND 硬闸 vs 单闸 distinct_pk」的配对自助检验。

配对 = 每次自助重抽同一批 symbol,三种准入规则各自在这批重抽样本上重算 ΔFPR,
再取差 —— 三者共享同一批票,票级噪声被抵消,差值 CI 比各自 CI 窄得多。
准入量对齐:每次重抽后,分数路与单闸路各取「分最高的 k 个」,k = 该次重抽下
AND 硬闸放行的行数,保证三路在每一次重抽里准入量都相同。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyze import atr_layers, layer_of, load                      # noqa: E402

FEATS = ["first_drought", "distinct_pk", "vol_spike", "peak_age"]
GATES = {"yaml": dict(first_drought=40, distinct_pk=3, vol_spike=3.0, peak_age=60),
         "dataclass": dict(first_drought=20, distinct_pk=4, vol_spike=8.0, peak_age=125)}
NBOOT = 2000
RNG = np.random.default_rng(20260907)


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
    d["score"] = d[["r_" + f for f in FEATS]].mean(axis=1)
    return d, base


def dfpr(up, dn, lay, base):
    u, d = up.sum(), dn.sum()
    if u + d == 0:
        return np.nan
    w = pd.Series(lay).value_counts(normalize=True)
    return u / (u + d) - sum(w.get(l, 0) * base[l][1] for l in base)


def main():
    for tag in ["w2025", "w2024"]:
        d, base = prep(tag)
        up, dn, lay = d.fp_up.values, d.fp_down.values, d.layer.values
        sc, pk = d.score.values, d["r_distinct_pk"].values
        syms = d.symbol.values
        uniq = np.unique(syms)
        idx = {g: np.where(syms == g)[0] for g in uniq}
        print(f"\n════ {tag} ════  全体宽进 ΔFPR={dfpr(up, dn, lay, base):+.4f}"
              f"(不设任何闸的对照)")
        for gname, G in GATES.items():
            gate = np.logical_and.reduce([d[f].values >= G[f] for f in FEATS])
            k0 = int(gate.sum())
            if k0 < 30:
                print(f"  [{gname}] AND 放行 n={k0} ⚠小样本"); continue
            obs = {}
            obs["AND"] = dfpr(up[gate], dn[gate], lay[gate], base)
            top_sc = np.argsort(-sc, kind="stable")[:k0]
            top_pk = np.argsort(-pk, kind="stable")[:k0]
            obs["score"] = dfpr(up[top_sc], dn[top_sc], lay[top_sc], base)
            obs["pk_only"] = dfpr(up[top_pk], dn[top_pk], lay[top_pk], base)
            ds, dp = [], []
            for _ in range(NBOOT):
                pick = RNG.choice(uniq, size=len(uniq), replace=True)
                sel = np.concatenate([idx[g] for g in pick])
                g_sel = gate[sel]
                k = int(g_sel.sum())
                if k < 10:
                    continue
                a = dfpr(up[sel][g_sel], dn[sel][g_sel], lay[sel][g_sel], base)
                o = np.argsort(-sc[sel], kind="stable")[:k]
                s = dfpr(up[sel][o], dn[sel][o], lay[sel][o], base)
                o2 = np.argsort(-pk[sel], kind="stable")[:k]
                p = dfpr(up[sel][o2], dn[sel][o2], lay[sel][o2], base)
                ds.append(s - a)
                dp.append(p - a)
            ds, dp = np.array(ds), np.array(dp)
            print(f"  [{gname}] 准入量 n={k0}(sym={d.symbol[gate].nunique()}) | "
                  f"AND ΔFPR={obs['AND']:+.4f}  等权分 {obs['score']:+.4f}  "
                  f"只用 distinct_pk {obs['pk_only']:+.4f}")
            print(f"      配对差 等权分−AND      = {ds.mean():+.4f} "
                  f"[{np.percentile(ds,2.5):+.4f},{np.percentile(ds,97.5):+.4f}]  "
                  f"P(>0)={np.mean(ds>0):.3f}")
            print(f"      配对差 distinct_pk−AND = {dp.mean():+.4f} "
                  f"[{np.percentile(dp,2.5):+.4f},{np.percentile(dp,97.5):+.4f}]  "
                  f"P(>0)={np.mean(dp>0):.3f}")


if __name__ == "__main__":
    main()
