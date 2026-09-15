"""打分制可补偿性分析:边际形状 / 2×2 析因 / 加权分放宽曲线 / 时间外推。

输入 = extract_wide.py 产出的 wide_*.csv(宽进 match 行)+ baseline_*.csv(随机日)。
所有「好/坏」判断都对着两条基线说:
  - 无条件随机日基线(全宇宙、同窗、每票 20 日);
  - 波动率层匹配基线(按买点日 ATR% 三分层重加权,FC-004 要求)。

指标:median(forward_return) 与 首次穿越率 FPR = up/(up+down)(池化到买点日)。
CI = 按 symbol 整簇自助(1000 次),因同一票的多个 match 高度相关。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RNG = np.random.default_rng(20260907)
NBOOT = 1000


def load(tag):
    d = pd.read_csv(HERE / f"wide_{tag}.csv", keep_default_na=False, na_values=[""])
    b = pd.read_csv(HERE / f"baseline_{tag}.csv", keep_default_na=False, na_values=[""])
    d = d[d.n_buy_bars > 0].copy()
    d["cluster"] = d.symbol + "|" + d.first_bo_idx.astype(str)
    return d, b


def atr_layers(b):
    """基线池的 ATR% 三分位切点(全宇宙无条件分布,作层的定义)。"""
    q = b.atr_pct.dropna()
    return [float(q.quantile(1 / 3)), float(q.quantile(2 / 3))]


def layer_of(x, cuts):
    return np.where(np.isnan(x), -1, np.where(x <= cuts[0], 0, np.where(x <= cuts[1], 1, 2)))


def boot_med_ci(vals, groups, n=NBOOT):
    """按 group 整簇自助的 median CI(95%)。"""
    vals = np.asarray(vals, float)
    if len(vals) < 5:
        return (np.nan, np.nan)
    gs = pd.Series(groups).values
    uniq = np.unique(gs)
    idx = {g: np.where(gs == g)[0] for g in uniq}
    out = []
    for _ in range(n):
        pick = RNG.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx[g] for g in pick])
        out.append(np.median(vals[sel]))
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)))


def boot_fpr_ci(up, dn, groups, n=NBOOT):
    up, dn = np.asarray(up, float), np.asarray(dn, float)
    gs = pd.Series(groups).values
    uniq = np.unique(gs)
    if len(uniq) < 5:
        return (np.nan, np.nan)
    idx = {g: np.where(gs == g)[0] for g in uniq}
    out = []
    for _ in range(n):
        pick = RNG.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx[g] for g in pick])
        u, d = up[sel].sum(), dn[sel].sum()
        out.append(u / (u + d) if (u + d) else np.nan)
    out = [o for o in out if np.isfinite(o)]
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))) if out else (np.nan, np.nan)


def stats(sub, base_by_layer, ci=True):
    """一个格子的口径统一汇总。base_by_layer = {layer: (med_fr, fpr, n)}。"""
    n = len(sub)
    if n == 0:
        return dict(n=0)
    up, dn = sub.fp_up.sum(), sub.fp_down.sum()
    fpr = up / (up + dn) if (up + dn) else np.nan
    med = float(sub.fr.median())
    r = dict(n=n, n_sym=sub.symbol.nunique(), n_clu=sub.cluster.nunique(),
             med_fr=med, fpr=fpr, buy_bars=int(up + dn + sub.fp_both.sum() + sub.fp_none.sum()),
             med_dd=float(sub.dd.median()))
    if ci:
        r["fr_ci"] = boot_med_ci(sub.fr.values, sub.symbol.values)
        r["fpr_ci"] = boot_fpr_ci(sub.fp_up.values, sub.fp_down.values, sub.symbol.values)
    # 波动率层匹配基线:按本格 ATR% 层分布对基线重加权
    w = sub.groupby("layer").size()
    w = w / w.sum()
    r["base_fr_matched"] = float(sum(w.get(l, 0) * base_by_layer[l][0] for l in base_by_layer))
    r["base_fpr_matched"] = float(sum(w.get(l, 0) * base_by_layer[l][1] for l in base_by_layer))
    return r


def fmt(name, r):
    if r.get("n", 0) == 0:
        return f"{name:<28} n=0"
    small = " ⚠小样本" if r["n"] < 30 else ""
    ci = r.get("fr_ci", (np.nan, np.nan))
    ci2 = r.get("fpr_ci", (np.nan, np.nan))
    return (f"{name:<28} n={r['n']:>5} sym={r['n_sym']:>4} clu={r['n_clu']:>4} | "
            f"med_fr={r['med_fr']:+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}] (基线匹配 {r['base_fr_matched']:+.4f}) | "
            f"FPR={r['fpr']:.4f} [{ci2[0]:.4f},{ci2[1]:.4f}] (基线匹配 {r['base_fpr_matched']:.4f}) | "
            f"med_dd={r['med_dd']:+.4f}{small}")


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "w2025"
    d, b = load(tag)
    cuts = atr_layers(b)
    d["layer"] = layer_of(d.atr_pct.values, cuts)
    b["layer"] = layer_of(b.atr_pct.values, cuts)
    base_by_layer = {}
    for l, g in b.groupby("layer"):
        u, dn = (g.fp == "up").sum(), (g.fp == "down").sum()
        base_by_layer[int(l)] = (float(g.fr.median()), u / (u + dn) if (u + dn) else np.nan, len(g))

    print(f"════ {tag} ════")
    print(f"ATR% 三分层切点(基线池): {cuts[0]:.4f} / {cuts[1]:.4f}")
    for l, (m, f, n) in sorted(base_by_layer.items()):
        print(f"  随机日基线 layer{l}: n={n:>6} med_fr={m:+.4f} FPR={f:.4f}")
    ub, ud = (b.fp == "up").sum(), (b.fp == "down").sum()
    print(f"  随机日基线 无条件: n={len(b)} med_fr={b.fr.median():+.4f} FPR={ub/(ub+ud):.4f}")
    print()
    print("── 全体宽进 match ──")
    print(fmt("ALL(4 闸全松)", stats(d, base_by_layer)))
    print()

    GATES = {
        "yaml(现役 SSoT)": dict(first_drought=40, distinct_pk=3, vol_spike=3.0, peak_age=60),
        "dataclass(代码兜底)": dict(first_drought=20, distinct_pk=4, vol_spike=8.0, peak_age=125),
    }
    for gname, G in GATES.items():
        m = ((d.first_drought >= G["first_drought"]) & (d.distinct_pk >= G["distinct_pk"]) &
             (d.vol_spike >= G["vol_spike"]) & (d.peak_age >= G["peak_age"]))
        print(f"── 四闸全过 · {gname} {G} ──")
        print(fmt("PASS_ALL", stats(d[m], base_by_layer)))
        for k, v in G.items():
            sub = d[d[k] >= v]
            print(fmt(f"  单闸 {k}>={v}", stats(sub, base_by_layer)))
        print()

    # Q1 边际形状:五分位分箱
    print("── Q1 边际形状(五分位分箱;med_dd 同列以甄别波动率读数) ──")
    for k in ["first_drought", "distinct_pk", "vol_spike", "peak_age"]:
        print(f"  [{k}]")
        try:
            qs = pd.qcut(d[k], 5, duplicates="drop")
        except ValueError:
            continue
        for lab, g in d.groupby(qs, observed=True):
            print("   " + fmt(f"{lab}", stats(g, base_by_layer)))
        print(f"   spearman(fr) = {d[k].corr(d.fr, method='spearman'):+.4f}   "
              f"spearman(dd) = {d[k].corr(d.dd, method='spearman'):+.4f}   "
              f"spearman(|dd|)= {d[k].corr(d.dd.abs(), method='spearman'):+.4f}")
        print()

    # Q2 2×2 析因
    print("── Q2 2×2 析因(可补偿性直测) ──")
    for gname, G in GATES.items():
        for a, bb in [("vol_spike", "distinct_pk"), ("vol_spike", "first_drought"),
                      ("vol_spike", "peak_age"), ("distinct_pk", "first_drought"),
                      ("distinct_pk", "peak_age"), ("first_drought", "peak_age")]:
            ta, tb_ = G[a], G[bb]
            hi_a, hi_b = d[a] >= ta, d[bb] >= tb_
            print(f"  {gname} · {a}>={ta} × {bb}>={tb_}")
            for na, ma in [("高", hi_a), ("低", ~hi_a)]:
                for nb, mb in [("高", hi_b), ("低", ~hi_b)]:
                    print("   " + fmt(f"{a[:4]}{na}·{bb[:4]}{nb}", stats(d[ma & mb], base_by_layer)))
            print()


if __name__ == "__main__":
    main()
