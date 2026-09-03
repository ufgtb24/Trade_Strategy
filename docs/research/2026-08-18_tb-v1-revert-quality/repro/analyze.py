# -*- coding: utf-8 -*-
"""好坏样本对比 + 单特征阈值过滤模拟。

基线指标(全 80 样本): median_fr / FP=up/(up+down) / n_bars。
好/坏组 = fr 的 top/bottom 25%(各 20)。
产出:控制台报告 + repro/analysis_report.txt。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
DF = pd.read_csv(HERE / "features.csv")
REPORT = HERE / "analysis_report.txt"
LINES: list[str] = []


def p(*args) -> None:
    line = " ".join(str(a) for a in args)
    print(line)
    LINES.append(line)


FEATURES = [
    # (特征名, 方向:'>'=值大=越坏)
    ("max_bear_body_atr", ">"), ("max_body_ratio", ">"),
    ("max_upper_atr", ">"), ("max_upper_ratio", ">"),
    ("max_consec_bear", ">"), ("bear_count", ">"), ("max_consec_down", ">"),
    ("dd_low", "<"), ("dd_close", "<"), ("anchor_margin", "<"),
    ("revert_pct", "<"), ("dd_vs_up", "<"),
    ("max_drop_pct", ">"), ("max_drop_tr", ">"), ("max_drop_atr", ">"),
    ("down_slope", ">"), ("slope_ratio", ">"), ("rev_days", ">"),
    ("up_pct", "?"), ("up_slope", "?"), ("up_days", "?"), ("atr", "?"),
]


def auc_bad(feature: str) -> float:
    """AUC(P(坏样本特征值 > 好样本特征值)):>0.5 = 特征大 = 坏。"""
    bad = DF[DF.group == "bad"][feature].to_numpy()
    good = DF[DF.group == "good"][feature].to_numpy()
    u = stats.mannwhitneyu(bad, good, alternative="greater").statistic
    return u / (len(bad) * len(good))


def metrics(df: pd.DataFrame) -> tuple:
    frs = df["fr"].to_numpy()
    up, down = df["fp_up"].sum(), df["fp_down"].sum()
    both = df["fp_both"].sum()
    ratio = up / (up + down + both) if up + down + both else np.nan
    n_bars = int(df[["fp_up", "fp_down", "fp_both", "fp_none"]].to_numpy().sum())
    return len(df), float(np.median(frs)), ratio, n_bars


def scan_thresholds(feature: str, direction: str) -> list[dict]:
    """对候选阈值 t 删样本(direction '>' 删 feature>=t;'<' 删 feature<=t),返回指标变化表。"""
    out = []
    qs = np.unique(np.quantile(DF[feature], np.linspace(0.05, 0.95, 19)))
    for t in qs:
        drop = DF[feature] >= t if direction == ">" else DF[feature] <= t
        kept = DF[~drop]
        if len(kept) < 40:      # 保留过半以下不考虑(过度过滤)
            continue
        n, med, ratio, n_bars = metrics(kept)
        dropped_fr = DF[drop]["fr"]
        out.append(dict(feature=feature, op=">=" if direction == ">" else "<=",
                        t=float(t), n_drop=int(drop.sum()), n_keep=n,
                        med=med, fp=ratio, n_bars=n_bars,
                        dropped_mean_fr=float(dropped_fr.mean()),
                        dropped_med_fr=float(dropped_fr.median())))
    return out


def main() -> None:
    DF["group"] = pd.qcut(DF["fr"], [0, .25, .75, 1], labels=["bad", "mid", "good"])
    n, med, ratio, n_bars = metrics(DF)
    p(f"基线: n={n} median_fr={med:.4f} FP={ratio:.4f} (up/down/both/none="
      f"{DF.fp_up.sum()}/{DF.fp_down.sum()}/{DF.fp_both.sum()}/{DF.fp_none.sum()}) n_bars={n_bars}")

    # ── 1 好坏组对比 + AUC + 全样本 Spearman ──
    p("\n== 好坏组对比 (bad=fr bottom20 / good=fr top20;AUC>0.5=值大→坏) ==")
    p(f"{'feature':<18}{'bad_med':>9}{'good_med':>10}{'AUC':>7}{'rho_all':>8}{'rho_p':>9}")
    rows = []
    for f, _d in FEATURES:
        rho, rp = stats.spearmanr(DF[f], DF["fr"], nan_policy="omit")
        rows.append((f, auc_bad(f), rho, rp))
    for f, a, rho, rp in sorted(rows, key=lambda x: -abs(x[1] - 0.5)):
        bm, gm = DF[DF.group == "bad"][f].median(), DF[DF.group == "good"][f].median()
        p(f"{f:<18}{bm:>9.3f}{gm:>10.3f}{a:>7.3f}{rho:>8.3f}{rp:>9.3g}")

    # ── 2 阈值扫描(按 median 提升排序,同时看 FP) ──
    p("\n== 阈值过滤扫描(按 median 提升排序;top15;drop_mean_fr=被删样本平均fr) ==")
    cands = []
    for f, d in FEATURES:
        if d == "?":
            continue
        cands.extend(scan_thresholds(f, d))
    cands.sort(key=lambda r: r["med"], reverse=True)
    p(f"{'feature':<18}{'op':>3}{'t':>8}{'drop':>5}{'med':>8}{'fp':>8}{'drop_mfr':>9}{'drop_x':>8}")
    for r in cands[:15]:
        p(f"{r['feature']:<18}{r['op']:>3}{r['t']:>8.3f}{r['n_drop']:>5}"
          f"{r['med']:>8.4f}{r['fp']:>8.4f}{r['dropped_mean_fr']:>9.3f}"
          f"{r['dropped_med_fr']:>8.3f}")

    # ── 3 最差 20 样本画像 ──
    p("\n== 最差 20 样本(fr 升序) ==")
    worst = DF.nsmallest(20, "fr")
    cols = ["symbol", "fr", "outcome", "dd_low", "dd_vs_up", "max_drop_tr",
            "max_consec_bear", "max_bear_body_atr", "max_upper_atr", "slope_ratio",
            "anchor_margin", "revert_pct"]
    p(worst[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    REPORT.write_text("\n".join(LINES))


if __name__ == "__main__":
    main()
