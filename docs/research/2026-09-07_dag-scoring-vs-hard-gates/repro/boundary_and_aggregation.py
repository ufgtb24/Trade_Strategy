"""三件事,都以现役 SSoT 阈值(40 / 3 / 3 / 60)为中心:

A. **最强项 vs 最弱项**:四个量各取分位秩,比较 max(秩) 与 min(秩) 对 label 的解释力。
   谁强,组合规则就该偏向谁(max 强 → OR / 取最优;min 强 → AND / 短板决定)。
B. **只差一闸的天然对照组**:其余三闸都过、仅被这一闸拦下的 match，与四闸全过的
   match 比收益。唯一变量就是那一道闸。再按相对差距分档看断层在哪。
C. **阈值邻域断层**:在每个量自身的轴上,取阈值两侧的窄带比收益(问的是「刚差一点」
   和「刚够」是不是同一批东西)。
D. `peak_age` 的聚合口径:现役 where 读 max(存在性),对照 median / min。
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
SSOT = dict(first_drought=40, distinct_pk=3, vol_spike=3.0, peak_age=60)
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
    R = d[["r_" + f for f in FEATS]]
    d["q_max"], d["q_min"] = R.max(axis=1), R.min(axis=1)
    d["q_mean"], d["q_med"] = R.mean(axis=1), R.median(axis=1)
    return d, base


def stat(sub, base, ci=True, nboot=NBOOT):
    n = len(sub)
    if n == 0:
        return dict(n=0)
    up, dn = sub.fp_up.values, sub.fp_down.values
    lay, fr = sub.layer.values, sub.fr.values

    def one(sel):
        u, dd = up[sel].sum(), dn[sel].sum()
        f = u / (u + dd) if (u + dd) else np.nan
        w = pd.Series(lay[sel]).value_counts(normalize=True)
        bf = sum(w.get(l, 0) * base[l][1] for l in base)
        bm = sum(w.get(l, 0) * base[l][0] for l in base)
        return f - bf, np.median(fr[sel]) - bm, f, np.median(fr[sel])
    d_fpr, d_fr, fpr, med = one(np.arange(n))
    r = dict(n=n, n_sym=sub.symbol.nunique(), fpr=fpr, med_fr=med,
             d_fpr=d_fpr, d_fr=d_fr)
    if ci:
        syms = sub.symbol.values
        uniq = np.unique(syms)
        if len(uniq) >= 5:
            idx = {g: np.where(syms == g)[0] for g in uniq}
            bs = []
            for _ in range(nboot):
                sel = np.concatenate([idx[g] for g in
                                      RNG.choice(uniq, size=len(uniq), replace=True)])
                a, c, _, _ = one(sel)
                if np.isfinite(a):
                    bs.append((a, c))
            bs = np.array(bs)
            r["ci_fpr"] = (np.percentile(bs[:, 0], 2.5), np.percentile(bs[:, 0], 97.5))
            r["ci_fr"] = (np.percentile(bs[:, 1], 2.5), np.percentile(bs[:, 1], 97.5))
    return r


def line(name, r):
    if r.get("n", 0) == 0:
        return f"    {name:<26} n=0"
    cf = r.get("ci_fpr", (np.nan, np.nan))
    cm = r.get("ci_fr", (np.nan, np.nan))
    s = " ⚠小样本" if r["n"] < 30 else ""
    return (f"    {name:<26} n={r['n']:>5} sym={r['n_sym']:>4} | "
            f"ΔFPR={r['d_fpr']:+.4f} [{cf[0]:+.4f},{cf[1]:+.4f}] | "
            f"Δmed_fr={r['d_fr']:+.4f} [{cm[0]:+.4f},{cm[1]:+.4f}] | "
            f"(原始 FPR={r['fpr']:.3f} med_fr={r['med_fr']:+.3f}){s}")


def paired_diff(sub_a, sub_b, base, label):
    """两个不相交子集的 ΔFPR / Δmed_fr 之差,同批重抽票的配对自助。"""
    d = pd.concat([sub_a.assign(_g=0), sub_b.assign(_g=1)])
    syms = d.symbol.values
    uniq = np.unique(syms)
    if len(uniq) < 5:
        return
    idx = {g: np.where(syms == g)[0] for g in uniq}
    up, dn, lay, fr, gg = (d.fp_up.values, d.fp_down.values, d.layer.values,
                           d.fr.values, d._g.values)

    def one(sel, grp):
        m = sel[gg[sel] == grp]
        if len(m) == 0:
            return np.nan, np.nan
        u, dd = up[m].sum(), dn[m].sum()
        f = u / (u + dd) if (u + dd) else np.nan
        w = pd.Series(lay[m]).value_counts(normalize=True)
        return (f - sum(w.get(l, 0) * base[l][1] for l in base),
                np.median(fr[m]) - sum(w.get(l, 0) * base[l][0] for l in base))
    full = np.arange(len(d))
    o0f, o0m = one(full, 0)
    o1f, o1m = one(full, 1)
    bs = []
    for _ in range(NBOOT):
        sel = np.concatenate([idx[g] for g in RNG.choice(uniq, size=len(uniq), replace=True)])
        a0, b0 = one(sel, 0)
        a1, b1 = one(sel, 1)
        if np.isfinite(a0) and np.isfinite(a1):
            bs.append((a0 - a1, b0 - b1))
    bs = np.array(bs)
    print(f"    ↳ 配对差 {label}: ΔFPR {o0f-o1f:+.4f} "
          f"[{np.percentile(bs[:,0],2.5):+.4f},{np.percentile(bs[:,0],97.5):+.4f}] | "
          f"Δmed_fr {o0m-o1m:+.4f} "
          f"[{np.percentile(bs[:,1],2.5):+.4f},{np.percentile(bs[:,1],97.5):+.4f}]")


def main():
    for tag in ["w2025", "w2024"]:
        d, base = prep(tag)
        allpass = np.logical_and.reduce([d[f] >= SSOT[f] for f in FEATS])
        print(f"\n{'='*100}\n════ {tag} · n={len(d)} sym={d.symbol.nunique()} · "
              f"SSoT 阈值 {SSOT} ════")
        print(line("全体宽进(不设任何闸)", stat(d, base)))
        print(line("四闸全过", stat(d[allpass], base)))

        # ── A. 最强项 vs 最弱项 ──
        print("\n  【A】最强项 vs 最弱项:四量分位秩的 max / min / mean 谁更能解释 label")
        for col, nm in [("q_max", "max(四量分位秩)=最强项"),
                        ("q_min", "min(四量分位秩)=最弱项"),
                        ("q_mean", "mean(四量分位秩)")]:
            print(f"    {nm:<26} spearman(fr)={d[col].corr(d.fr,method='spearman'):+.4f}"
                  f"  spearman(|dd|)={d[col].corr(d.dd.abs(),method='spearman'):+.4f}")
        for col, nm in [("q_max", "最强项"), ("q_min", "最弱项"), ("q_mean", "均值")]:
            print(f"    · 按 {nm} 三分:")
            for lab, g in d.groupby(pd.qcut(d[col], 3, duplicates="drop"), observed=True):
                print(line(f"  {lab}", stat(g, base)))
            hi = d[d[col] >= d[col].quantile(2/3)]
            lo = d[d[col] <= d[col].quantile(1/3)]
            paired_diff(hi, lo, base, f"{nm}高 − {nm}低")

        # ── B. 只差一闸的天然对照组 ──
        print("\n  【B】只差一闸(其余三闸都过)vs 四闸全过")
        for f in FEATS:
            others = np.logical_and.reduce([d[g] >= SSOT[g] for g in FEATS if g != f])
            only = others & (d[f] < SSOT[f])
            r = stat(d[only], base)
            print(line(f"只差 {f}", r))
            if r.get("n", 0) >= 30:
                paired_diff(d[only], d[allpass], base, f"只差{f} − 四闸全过")

        # ── C. 阈值邻域断层 ──
        print("\n  【C】阈值邻域:各量自身轴上阈值两侧窄带(全体宽进池内,不限其余闸)")
        for f in FEATS:
            t = SSOT[f]
            sd = d[f].std()
            for frac in [0.25, 0.5]:
                w = frac * sd
                below = d[(d[f] >= t - w) & (d[f] < t)]
                above = d[(d[f] >= t) & (d[f] < t + w)]
                if len(below) < 30 or len(above) < 30:
                    print(f"    {f} ±{frac}σ(σ={sd:.3g}): "
                          f"下侧 n={len(below)} 上侧 n={len(above)} —— 样本不足,不判定")
                    continue
                print(f"    {f} 带宽 ±{frac}σ (σ={sd:.3g}, 带宽={w:.3g}):")
                print(line("  刚没过线", stat(below, base)))
                print(line("  刚过线", stat(above, base)))
                paired_diff(above, below, base, "刚过 − 刚没过")

        # ── D. peak_age 聚合口径 ──
        print("\n  【D】peak_age 聚合口径:现役 max(存在性) vs median vs min(全员)")
        for col in ["peak_age", "peak_age_med", "peak_age_min"]:
            if col not in d.columns:
                continue
            print(f"    [{col}] spearman(fr)={d[col].corr(d.fr,method='spearman'):+.4f}"
                  f"  三分位组 ΔFPR:", end="")
            try:
                q = pd.qcut(d[col], 3, duplicates="drop")
            except ValueError:
                print(" 分位不可切"); continue
            outs = []
            for lab, g in d.groupby(q, observed=True):
                r = stat(g, base, ci=False)
                outs.append(f"{r['d_fpr']:+.4f}(n={r['n']})")
            print("  " + " / ".join(outs))
            hi = d[d[col] >= d[col].quantile(2/3)]
            lo = d[d[col] <= d[col].quantile(1/3)]
            paired_diff(hi, lo, base, f"{col} 高 − 低")


if __name__ == "__main__":
    main()
