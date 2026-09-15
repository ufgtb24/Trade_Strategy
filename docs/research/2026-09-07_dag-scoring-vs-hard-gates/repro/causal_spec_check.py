"""对 framework 加了因果闸的 spec 产出做统计判断:
  ① 与我事后按因果性筛出的买点集是否逐个相同(spec 级修法 vs 事后过滤);
  ② 层匹配基线下 原有 vs causal·新增 的 ΔFPR / Δmed_fr + 整簇自助配对 CI(三档 k);
  ③ 控制「入场时点」这个混杂:按 causal_gap(买点距 burst 确认根的 bar 数)与
     bo_rank_in_burst(锚 bo 在簇内序位)分层后,新增是否仍与原有齐平。
"""
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
KS = [(4, "fp4_up", "fp4_down"), (5, "fp_up", "fp_down"), (6, "fp6_up", "fp6_down")]


def load(tag):
    d = pd.read_csv(HERE / f"causal_{tag}.csv", keep_default_na=False, na_values=[""])
    b = pd.read_csv(HERE / f"anchor_baseline_{tag}.csv", keep_default_na=False,
                    na_values=[""])
    cuts = [float(b.atr_pct.quantile(1 / 3)), float(b.atr_pct.quantile(2 / 3))]
    d["layer"] = layer_of(d.atr_pct.values, cuts)
    b["layer"] = layer_of(b.atr_pct.values, cuts)
    d = d[(d.n_buy_bars > 0) & (d.layer >= 0)].copy()
    base = {}
    for l, g in b[b.layer >= 0].groupby("layer"):
        base[int(l)] = {}
        for k, _, _ in KS:
            col = "fp" if k == 5 else f"fp{k}"
            u, dn = (g[col] == "up").sum(), (g[col] == "down").sum()
            base[int(l)][k] = u / (u + dn) if (u + dn) else np.nan
        base[int(l)]["fr"] = float(g.fr.median())
    return d, base


def dfpr(sub, base, k, uc, dc):
    u, dn = sub[uc].sum(), sub[dc].sum()
    if u + dn == 0:
        return np.nan
    w = sub.layer.value_counts(normalize=True)
    return u / (u + dn) - sum(w.get(l, 0) * base[l][k] for l in base)


def dfr(sub, base):
    w = sub.layer.value_counts(normalize=True)
    return float(sub.fr.median()) - sum(w.get(l, 0) * base[l]["fr"] for l in base)


def paired(a, b_, base, label, k=5, uc="fp_up", dc="fp_down"):
    d = pd.concat([a.assign(_g=0), b_.assign(_g=1)])
    syms = d.symbol.values
    uniq = np.unique(syms)
    idx = {g: np.where(syms == g)[0] for g in uniq}

    def two(sub):
        x, y = sub[sub._g == 0], sub[sub._g == 1]
        if len(x) == 0 or len(y) == 0:
            return np.nan, np.nan
        return (dfpr(x, base, k, uc, dc) - dfpr(y, base, k, uc, dc),
                dfr(x, base) - dfr(y, base))
    o = two(d)
    bs = []
    for _ in range(NBOOT):
        sel = np.concatenate([idx[g] for g in RNG.choice(uniq, size=len(uniq), replace=True)])
        v = two(d.iloc[sel])
        if np.isfinite(v[0]):
            bs.append(v)
    bs = np.array(bs)
    print(f"    ↳ 配对差 {label}: ΔFPR(k={k}) {o[0]:+.4f} "
          f"[{np.percentile(bs[:,0],2.5):+.4f},{np.percentile(bs[:,0],97.5):+.4f}] | "
          f"Δmed_fr {o[1]:+.4f} "
          f"[{np.percentile(bs[:,1],2.5):+.4f},{np.percentile(bs[:,1],97.5):+.4f}]")


def line(nm, sub, base):
    if len(sub) == 0:
        return f"  {nm:<32} n=0"
    s = " ⚠小样本" if len(sub) < 30 else ""
    ks = " ".join(f"k{k}={dfpr(sub, base, k, u, dd):+.4f}" for k, u, dd in KS)
    return (f"  {nm:<32} n={len(sub):>4} 票={sub.symbol.nunique():>4} | {ks} | "
            f"Δmed_fr={dfr(sub, base):+.4f} | med_dd={sub.dd.median():+.3f}{s}")


def main():
    for tag in ["w2025", "w2024"]:
        d, base = load(tag)
        cau = d[d.variant == "causal"]
        wide = d[d.variant == "wide"]
        cur = cau[cau.group == "原有"]
        new = cau[cau.group == "新增"]
        print(f"\n{'='*112}\n════ {tag} · causal spec 买点 {len(cau)}"
              f"（原有 {len(cur)} / 新增 {len(new)}） ════")

        # ① spec 级修法 vs 我的事后过滤
        mine = pd.read_csv(HERE / f"stats_anchor_{tag}.csv", keep_default_na=False,
                           na_values=[""])
        mine_causal = set(zip(mine[mine.causal].symbol, mine[mine.causal].tb_id))
        theirs = set(zip(cau.symbol, cau.tb_id))
        print(f"  ① 买点集对拍：我的事后因果过滤 {len(mine_causal)} vs 加闸 spec {len(theirs)}"
              f"；只在我 {len(mine_causal-theirs)}，只在他 {len(theirs-mine_causal)}")
        print(f"     causal 变体内 causal_gap 最小值 = {cau.causal_gap.min()}"
              f"（须 ≥1）；n_bo_after 最大值 = {cau.n_bo_after.max()}（须 =0）")

        # ② 质量
        print("  ② 质量（ΔFPR vs 波动率层匹配基线，三档 k）")
        print(line("原有（现状 spec）", cur, base))
        print(line("causal·新增", new, base))
        for k, uc, dc in KS:
            paired(new, cur, base, "causal新增 − 原有", k, uc, dc)
        print(line("wide·非因果（作反例对照）",
                   wide[(wide.group == "新增") & (wide.causal_gap < 1)], base))

        # ③ 控制入场时点
        print("  ③ 控制入场时点（causal_gap = 买点距 burst 确认根的 bar 数）")
        print(f"     causal_gap 中位：原有 {cur.causal_gap.median():.0f} / "
              f"新增 {new.causal_gap.median():.0f}；"
              f"分布 原有 {cur.causal_gap.value_counts().sort_index().head(4).to_dict()} "
              f"新增 {new.causal_gap.value_counts().sort_index().head(4).to_dict()}")
        for lo_, hi_, nm in [(1, 3, "gap 1~3（贴着确认根买）"),
                             (4, 8, "gap 4~8"), (9, 99, "gap ≥9")]:
            gc = cur[(cur.causal_gap >= lo_) & (cur.causal_gap <= hi_)]
            gn = new[(new.causal_gap >= lo_) & (new.causal_gap <= hi_)]
            print(line(f"  原有·{nm}", gc, base))
            print(line(f"  新增·{nm}", gn, base))
            if len(gc) >= 30 and len(gn) >= 30:
                paired(gn, gc, base, f"层内 新增 − 原有（{nm}）")


if __name__ == "__main__":
    main()
