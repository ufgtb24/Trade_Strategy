"""锚放宽新增买点的判断:层匹配基线 + 整簇自助 CI + 因果性拆分。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyze import layer_of                                        # noqa: E402

NBOOT = 2000
RNG = np.random.default_rng(20260907)
KS = [(4.0, "up4", "dn4"), (5.0, "fp_up", "fp_down"), (6.0, "up6", "dn6")]


def prep(tag):
    d = pd.read_csv(HERE / f"stats_anchor_{tag}.csv", keep_default_na=False, na_values=[""])
    b = pd.read_csv(HERE / f"stats_anchor_base_{tag}.csv", keep_default_na=False, na_values=[""])
    d = d[d.n_buy_bars > 0].copy()
    cuts = [float(b.atr_pct.quantile(1 / 3)), float(b.atr_pct.quantile(2 / 3))]
    d["layer"] = layer_of(d.atr_pct.values, cuts)
    b["layer"] = layer_of(b.atr_pct.values, cuts)
    d = d[d.layer >= 0].copy()
    base = {}
    for l, g in b[b.layer >= 0].groupby("layer"):
        u, dn = (g.fp == "up").sum(), (g.fp == "down").sum()
        base[int(l)] = (float(g.fr.median()), u / (u + dn))
    return d, base


def dfpr(sub, base, ucol, dcol):
    u, dn = sub[ucol].sum(), sub[dcol].sum()
    if u + dn == 0:
        return np.nan
    w = sub.layer.value_counts(normalize=True)
    return u / (u + dn) - sum(w.get(l, 0) * base[l][1] for l in base)


def dfr(sub, base):
    w = sub.layer.value_counts(normalize=True)
    return float(sub.fr.median()) - sum(w.get(l, 0) * base[l][0] for l in base)


def ci(sub, base, fn, nboot=NBOOT):
    syms = sub.symbol.values
    uniq = np.unique(syms)
    if len(uniq) < 5:
        return (np.nan, np.nan)
    idx = {g: np.where(syms == g)[0] for g in uniq}
    out = []
    for _ in range(nboot):
        sel = np.concatenate([idx[g] for g in RNG.choice(uniq, size=len(uniq), replace=True)])
        v = fn(sub.iloc[sel], base)
        if np.isfinite(v):
            out.append(v)
    return (np.percentile(out, 2.5), np.percentile(out, 97.5)) if out else (np.nan, np.nan)


def row(name, sub, base):
    if len(sub) == 0:
        return f"  {name:<30} n=0"
    f5 = dfpr(sub, base, "fp_up", "fp_down")
    c5 = ci(sub, base, lambda s, b: dfpr(s, b, "fp_up", "fp_down"))
    m = dfr(sub, base)
    cm = ci(sub, base, dfr)
    u, dn = sub.fp_up.sum(), sub.fp_down.sum()
    s = " ⚠小样本" if len(sub) < 30 else ""
    return (f"  {name:<30} n={len(sub):>4} 票={sub.symbol.nunique():>4} "
            f"买点日={int(sub.n_buy_bars.sum()):>5} | "
            f"ΔFPR={f5:+.4f} [{c5[0]:+.4f},{c5[1]:+.4f}] | "
            f"Δmed_fr={m:+.4f} [{cm[0]:+.4f},{cm[1]:+.4f}] | "
            f"原始 FPR={u/(u+dn):.3f} med_fr={sub.fr.median():+.3f} "
            f"med_dd={sub.dd.median():+.3f}{s}")


def paired(a, b_, base, label):
    d = pd.concat([a.assign(_g=0), b_.assign(_g=1)])
    syms = d.symbol.values
    uniq = np.unique(syms)
    idx = {g: np.where(syms == g)[0] for g in uniq}

    def two(sub):
        x, y = sub[sub._g == 0], sub[sub._g == 1]
        if len(x) == 0 or len(y) == 0:
            return np.nan, np.nan
        return (dfpr(x, base, "fp_up", "fp_down") - dfpr(y, base, "fp_up", "fp_down"),
                dfr(x, base) - dfr(y, base))
    o = two(d)
    bs = []
    for _ in range(NBOOT):
        sel = np.concatenate([idx[g] for g in RNG.choice(uniq, size=len(uniq), replace=True)])
        v = two(d.iloc[sel])
        if np.isfinite(v[0]):
            bs.append(v)
    bs = np.array(bs)
    print(f"    ↳ 配对差 {label}: ΔFPR {o[0]:+.4f} "
          f"[{np.percentile(bs[:,0],2.5):+.4f},{np.percentile(bs[:,0],97.5):+.4f}] | "
          f"Δmed_fr {o[1]:+.4f} "
          f"[{np.percentile(bs[:,1],2.5):+.4f},{np.percentile(bs[:,1],97.5):+.4f}]")


def main():
    for tag in ["w2025", "w2024"]:
        d, base = prep(tag)
        cur, new = d[d.group == "原有"], d[d.group == "新增"]
        print(f"\n{'='*118}\n════ {tag} · 买点 {len(d)}（原有 {len(cur)} / 新增 {len(new)}）"
              f" · 票 {d.symbol.nunique()} ════")
        print(row("原有（现状 spec）", cur, base))
        print(row("新增（放宽独有）", new, base))
        paired(new, cur, base, "新增 − 原有")

        print("\n  【因果性拆分】burst 是回顾型（confirm_idx = end_idx）")
        print(f"    新增里「买点时至少有一个 burst 已确认」= {int(new.causal.sum())} / {len(new)}；"
              f"原有 = {int(cur.causal.sum())} / {len(cur)}")
        nc, nn = new[new.causal], new[~new.causal]
        print(row("新增·因果（买点时已确认）", nc, base))
        print(row("新增·非因果（买点后才确认）", nn, base))
        if len(nc) >= 30 and len(nn) >= 30:
            paired(nn, nc, base, "新增非因果 − 新增因果")
        if len(nc) >= 30:
            paired(nc, cur, base, "新增·因果 − 原有")

        print("\n  【机械续涨】买点当日或之后仍有成员 bo 的个数 n_bo_after")
        print(f"    原有 n_bo_after 分布 {cur.n_bo_after.value_counts().sort_index().head(4).to_dict()}"
              f"；新增 {new.n_bo_after.value_counts().sort_index().head(6).to_dict()}")
        for v, nm in [(0, "=0（买点后无后续 bo）"), (1, ">=1（买点后仍有 bo）")]:
            g = new[new.n_bo_after == 0] if v == 0 else new[new.n_bo_after >= 1]
            print(row(f"新增 n_bo_after {nm}", g, base))
        g0, g1 = new[new.n_bo_after == 0], new[new.n_bo_after >= 1]
        if len(g0) >= 30 and len(g1) >= 30:
            paired(g1, g0, base, "新增·有后续bo − 新增·无后续bo")
        if len(g0) >= 30:
            paired(g0, cur, base, "新增·无后续bo − 原有")

        print("\n  【三档 k】ΔFPR vs 层匹配基线")
        for nm, sub in [("原有", cur), ("新增", new), ("新增·因果", nc),
                        ("新增·因果且无后续bo", new[new.causal & (new.n_bo_after == 0)])]:
            if len(sub) == 0:
                continue
            line = f"    {nm:<22} n={len(sub):>4}"
            for k, uc, dc in KS:
                line += f" | k={k:.0f}: {dfpr(sub, base, uc, dc):+.4f}"
            print(line)


if __name__ == "__main__":
    main()
