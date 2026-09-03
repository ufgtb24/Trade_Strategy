# -*- coding: utf-8 -*-
"""agentA:候选规则稳健性验证——阈值±20% 敏感性 / 按股 cluster bootstrap(2000) /
leave-one-stock-out / 删除样本股票集中度。输出控制台报告。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DF = pd.read_csv(HERE / "features.csv")
RNG = np.random.default_rng(20260818)
N_BOOT = 2000

# (规则名, [(feat,op,t), ...], 组合方式)  op: '>=' 或 '<='
RULES = [
    ("R1 drop20",        [("max_drop_pct", ">=", 0.20)], "any"),
    ("R1b drop15",       [("max_drop_pct", ">=", 0.15)], "any"),
    ("R2 bear2",         [("max_bear_body_atr", ">=", 2.0)], "any"),
    ("R3 drop20|bear2",  [("max_drop_pct", ">=", 0.20), ("max_bear_body_atr", ">=", 2.0)], "any"),
    ("R4 tr2&bear1.5",   [("max_drop_tr", ">=", 2.0), ("max_bear_body_atr", ">=", 1.5)], "all"),
    ("R5 tr1.5&ds.03",   [("max_drop_tr", ">=", 1.5), ("down_slope", ">=", 0.03)], "all"),
    ("R6 drop10&bear1",  [("max_drop_pct", ">=", 0.10), ("max_bear_body_atr", ">=", 1.0)], "all"),
]


def drop_mask(df: pd.DataFrame, conds: list, mode: str) -> np.ndarray:
    ms = []
    for f, op, t in conds:
        v = df[f].to_numpy()
        ms.append(v >= t if op == ">=" else v <= t)
    m = ms[0]
    for x in ms[1:]:
        m = (m | x) if mode == "any" else (m & x)
    return m


def stats_of(df: pd.DataFrame, drop: np.ndarray) -> tuple:
    kept = df[~drop]
    med = float(kept.fr.median()) if len(kept) else np.nan
    up, dn, bt = kept.fp_up.sum(), kept.fp_down.sum(), kept.fp_both.sum()
    fp = up / (up + dn + bt) if up + dn + bt else np.nan
    return med, fp


def base_stats(df: pd.DataFrame) -> tuple:
    return stats_of(df, np.zeros(len(df), dtype=bool))


def boot_ci(conds: list, mode: str) -> tuple:
    """按股 cluster bootstrap:Δmed/Δfp 的 95% CI(重采样内规则组-基线组)。"""
    syms = DF.symbol.unique()
    groups = {s: DF[DF.symbol == s] for s in syms}
    d_meds, d_fps = [], []
    for _ in range(N_BOOT):
        pick = RNG.choice(syms, size=len(syms), replace=True)
        parts = [groups[s] for s in pick]
        b = pd.concat(parts, ignore_index=True)
        bm, bf = base_stats(b)
        rm, rf = stats_of(b, drop_mask(b, conds, mode))
        if np.isnan(bm) or np.isnan(rm):
            continue
        d_meds.append(rm - bm)
        if not (np.isnan(bf) or np.isnan(rf)):
            d_fps.append(rf - bf)
    def ci(a):
        return np.percentile(a, 2.5), np.percentile(a, 97.5)
    lo_m, hi_m = ci(d_meds)
    lo_f, hi_f = ci(d_fps)
    pos_m = np.mean(np.array(d_meds) > 0)
    pos_f = np.mean(np.array(d_fps) > 0)
    return lo_m, hi_m, pos_m, lo_f, hi_f, pos_f


def loso(conds: list, mode: str) -> tuple:
    """leave-one-stock-out:去任一股后 Δmed/Δfp 的最小值。"""
    worst_m, worst_f = np.inf, np.inf
    for s in DF.symbol.unique():
        d = DF[DF.symbol != s]
        bm, bf = base_stats(d)
        rm, rf = stats_of(d, drop_mask(d, conds, mode))
        worst_m = min(worst_m, rm - bm)
        if not (np.isnan(bf) or np.isnan(rf)):
            worst_f = min(worst_f, rf - bf)
    return worst_m, worst_f


def sensitivity(conds: list, mode: str) -> list:
    """阈值整体 ±20% 的 (med, fp, n_keep)。"""
    out = []
    for scale in (0.8, 0.9, 1.0, 1.1, 1.2):
        cs = [(f, op, t * scale if op == ">=" else t * scale) for f, op, t in conds]
        m = drop_mask(DF, cs, mode)
        med, fp = stats_of(DF, m)
        out.append((scale, int(m.sum()), len(DF) - int(m.sum()), med, fp))
    return out


def concentration(conds: list, mode: str) -> None:
    d = DF[drop_mask(DF, conds, mode)]
    vc = d.symbol.value_counts()
    print(f"    删除 {len(d)} 样本 / {d.symbol.nunique()} 股;"
          f"单股最多删 {vc.iloc[0] if len(vc) else 0} 个({vc.index[0] if len(vc) else '-'});"
          f"删除样本 fr: mean={d.fr.mean():.3f} med={d.fr.median():.3f}")


def main() -> None:
    bm, bf = base_stats(DF)
    print(f"base: med={bm:.4f} fp={bf:.4f}")
    for name, conds, mode in RULES:
        m = drop_mask(DF, conds, mode)
        med, fp = stats_of(DF, m)
        print(f"\n== {name} [{conds} {mode}] drop={m.sum()} keep={len(DF)-m.sum()} "
              f"med={med:.4f}(Δ{med-bm:+.4f}) fp={fp:.4f}(Δ{fp-bf:+.4f})")
        print("    敏感性(阈值×0.8..1.2): " + " | ".join(
            f"×{s:.1f}:{n}→med {md:.4f},fp {f_:.4f}"
            for s, _, n, md, f_ in sensitivity(conds, mode)))
        lo_m, hi_m, pos_m, lo_f, hi_f, pos_f = boot_ci(conds, mode)
        print(f"    bootstrap2000: Δmed CI[{lo_m:+.4f},{hi_m:+.4f}] P(>0)={pos_m:.2f} | "
              f"Δfp CI[{lo_f:+.4f},{hi_f:+.4f}] P(>0)={pos_f:.2f}")
        wm, wf = loso(conds, mode)
        print(f"    LOSO 最差: Δmed={wm:+.4f} Δfp={wf:+.4f}")
        concentration(conds, mode)


if __name__ == "__main__":
    main()
