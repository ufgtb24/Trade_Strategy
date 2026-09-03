# -*- coding: utf-8 -*-
"""② 区分度试验 · 统计与报告(预注册口径, 见 preregistration.md)。

分组: G_neg(score<-0.15) / G_mid(覆盖且|score|≤0.15) / G_pos(>0.15) / G_nocov(无覆盖)
主检验: G_neg vs G_rest(全部-G_neg, 实盘闸语义) fr median 差 + FPR_k6 差, bootstrap 95% CI
作用面上限: p_neg × Δ。判定按预注册三条件。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

OUT_DIR = Path(__file__).resolve().parent
N_BOOT = 10000
RNG = np.random.default_rng(42)  # 固定种子, 结果可复现


def boot_ci_median_diff(a: list, b: list) -> tuple[float, float, float]:
    """median(b) - median(a) 的点估计与 percentile 95% CI。"""
    a, b = np.array(a, float), np.array(b, float)
    point = float(np.median(b) - np.median(a))
    if len(a) < 2 or len(b) < 2:
        return point, float("nan"), float("nan")
    idx_a = RNG.integers(0, len(a), (N_BOOT, len(a)))
    idx_b = RNG.integers(0, len(b), (N_BOOT, len(b)))
    diffs = np.median(b[idx_b], axis=1) - np.median(a[idx_a], axis=1)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return point, float(lo), float(hi)


def fpr(states: list) -> tuple[float, int, int]:
    """组级 FPR = Σup/(Σup+Σdown); 返回 (ratio, up, down)。none/both 剔除。"""
    up = sum(1 for s in states if s == "up")
    down = sum(1 for s in states if s == "down")
    return (up / (up + down) if up + down else float("nan"), up, down)


def boot_ci_fpr_diff(sa: list, sb: list) -> tuple[float, float, float]:
    """FPR(b) - FPR(a) 行级重采样 CI。"""
    ra, ua, da = fpr(sa)
    rb, ub, db = fpr(sb)
    point = rb - ra
    if len(sa) < 2 or len(sb) < 2:
        return point, float("nan"), float("nan")
    a = np.array([1 if s == "up" else 0 if s == "down" else -1 for s in sa])  # -1=剔除
    b = np.array([1 if s == "up" else 0 if s == "down" else -1 for s in sb])
    idx_a = RNG.integers(0, len(a), (N_BOOT, len(a)))
    idx_b = RNG.integers(0, len(b), (N_BOOT, len(b)))
    ratios = []
    for ia, ib in zip(idx_a, idx_b):
        xa, xb = a[ia], b[ib]
        na = int((xa >= 0).sum())   # 有效样本数(up+down; -1=none/both 剔除)
        nb = int((xb >= 0).sum())
        if na + nb == 0:
            continue
        f_a = (xa == 1).sum() / na if na else float("nan")
        f_b = (xb == 1).sum() / nb if nb else float("nan")
        if np.isnan(f_a) or np.isnan(f_b):
            continue
        ratios.append(f_b - f_a)
    if len(ratios) < 100:
        return point, float("nan"), float("nan")
    lo, hi = np.percentile(ratios, [2.5, 97.5])
    return point, float(lo), float(hi)


def main():
    metrics_path = sorted(OUT_DIR.glob("full_metrics_*.json"))[-1]
    rows = json.loads(metrics_path.read_text())
    print(f"loaded {len(rows)} rows from {metrics_path.name}")

    # 分组(预注册)
    g = {"G_neg": [], "G_mid": [], "G_pos": [], "G_nocov": []}
    for r in rows:
        if r["total_count"] == 0:
            g["G_nocov"].append(r)
        elif r["sentiment_score"] < -0.15:
            g["G_neg"].append(r)
        elif r["sentiment_score"] > 0.15:
            g["G_pos"].append(r)
        else:
            g["G_mid"].append(r)

    n = len(rows)
    table = []
    for name, rs in g.items():
        frs = [r["fr_recalc"] for r in rs]
        fp6 = [r["fp"]["6"] for r in rs if r["fp"]["6"] is not None]
        ratio, up, down = fpr(fp6)
        table.append({
            "group": name, "n": len(rs), "pct": round(len(rs) / n * 100, 1),
            "fr_median": round(float(np.median(frs)), 4) if frs else None,
            "fr_q25_q75": [round(float(np.percentile(frs, 25)), 4),
                           round(float(np.percentile(frs, 75)), 4)] if frs else None,
            "fpr_k6": round(ratio, 4) if up + down else None,
            "fp6_up_down_none": [up, down, len(fp6) - up - down],
        })
        print(f"{name:8s} n={len(rs):3d} ({len(rs)/n*100:4.1f}%) fr_med={table[-1]['fr_median']} "
              f"q={table[-1]['fr_q25_q75']} FPR6={table[-1]['fpr_k6']} (u/d/n={table[-1]['fp6_up_down_none']})")

    # 主检验: G_neg vs G_rest(实盘闸语义: 保留其余全部)
    rest = g["G_mid"] + g["G_pos"] + g["G_nocov"]
    tests = {}
    frs_neg = [r["fr_recalc"] for r in g["G_neg"]]
    frs_rest = [r["fr_recalc"] for r in rest]
    pt, lo, hi = boot_ci_median_diff(frs_neg, frs_rest)
    tests["fr_median_rest_minus_neg"] = {"point": round(pt, 4), "ci95": [round(lo, 4), round(hi, 4)]}
    fp_neg = [r["fp"]["6"] for r in g["G_neg"] if r["fp"]["6"] is not None]
    fp_rest = [r["fp"]["6"] for r in rest if r["fp"]["6"] is not None]
    pt2, lo2, hi2 = boot_ci_fpr_diff(fp_neg, fp_rest)
    tests["fpr_k6_rest_minus_neg"] = {"point": round(pt2, 4), "ci95": [round(lo2, 4), round(hi2, 4)]}

    # 混杂检查: G_nocov vs G_cov; H2 附检: G_pos vs G_mid
    cov = g["G_neg"] + g["G_mid"] + g["G_pos"]
    t_nocov = boot_ci_median_diff([r["fr_recalc"] for r in g["G_nocov"]],
                                  [r["fr_recalc"] for r in cov])
    t_h2 = boot_ci_median_diff([r["fr_recalc"] for r in g["G_mid"]],
                               [r["fr_recalc"] for r in g["G_pos"]])
    tests["confound_nocov_vs_cov_fr"] = {"point": round(t_nocov[0], 4),
                                         "ci95": [round(t_nocov[1], 4), round(t_nocov[2], 4)]}
    tests["h2_pos_vs_mid_fr"] = {"point": round(t_h2[0], 4),
                                 "ci95": [round(t_h2[1], 4), round(t_h2[2], 4)]}

    # 稳健性: k=4/5 方向
    for k in ("4", "5"):
        fpn = [r["fp"][k] for r in g["G_neg"] if r["fp"][k] is not None]
        fpr_ = [r["fp"][k] for r in rest if r["fp"][k] is not None]
        tests[f"fpr_k{k}_rest_minus_neg"] = round(fpr(fpr_)[0] - fpr(fpn)[0], 4) \
            if (fpr(fpn)[2] + fpr(fpr_)[2]) else None

    # 作用面上限
    p_neg = len(g["G_neg"]) / n
    tests["neg_rate"] = round(p_neg, 4)
    tests["impact_ceiling"] = {
        "fr_median_all_change_upper": round(p_neg * pt, 4),
        "fpr_all_change_upper": round(p_neg * pt2, 4),
    }

    # 判定(预注册三条件)
    c1 = lo > 0 or hi < 0  # CI 不跨 0
    c2 = pt2 < 0  # G_neg FPR 更低
    c3 = p_neg >= 0.05
    verdict = "接入" if (c1 and c2 and c3) else "不接入"
    print(f"\n主检验 fr_med(rest-neg) = {pt:+.4f} CI[{lo:+.4f},{hi:+.4f}]")
    print(f"主检验 FPR6(rest-neg) = {pt2:+.4f} CI[{lo2:+.4f},{hi2:+.4f}]")
    print(f"p_neg = {p_neg:.1%} | 判定: {verdict} (c1={c1} c2={c2} c3={c3})")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = {"meta": {"n": n, "source": metrics_path.name, "n_boot": N_BOOT,
                    "prereg": "preregistration.md", "date": "2026-08-16"},
           "groups": table, "tests": tests,
           "verdict": {"decision": verdict, "c1_ci_excludes_zero": c1,
                       "c2_fpr_direction": c2, "c3_neg_rate": c3}}
    path = OUT_DIR / f"discrimination_result_{stamp}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"saved: {path}")


if __name__ == "__main__":
    main()
