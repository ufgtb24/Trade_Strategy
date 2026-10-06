"""评分口径评审补充核查（临时研究脚本）。

1. 近期加权的「逐买点直接平均」PR（不分窗口）与 Z、P 的对比：候选间一致性、重抽波动、搜索→后段预测；
2. 每个日期在 Z 中的总权重形状（均匀密度时）——看首尾月的欠权；
3. 普通池方向 vs 当日波动分位：五档配比后残余的混杂；候选买点落在各档内部的位置；
4. 未触线比例随波动档与时间的变化。
输出 repro/objective_extra_results.json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from objective_noise import DATA, StockMatrix, dedupe, load  # noqa: E402
from scoring import WindowPlan  # noqa: E402

OUT = Path(__file__).with_name("objective_extra_results.json")
RNG = np.random.default_rng(7)
N_BOOT = 2000


def recency_pooled(plan: WindowPlan, rows: pd.DataFrame, half_life=252.0):
    idx = plan._indices_checked(rows)
    d = plan._date_indices[idx]
    age = len(plan.dates) - 1 - d
    a = np.exp2(-age / half_life)
    y = plan._direction[idx]
    b = plan._matched_direction[idx]
    return float(a @ y / a.sum()), float(a @ b / a.sum())


def pr_boot(sm: StockMatrix, m: np.ndarray, half_life=252.0):
    p = sm.plan
    age = len(p.dates) - 1 - np.arange(len(p.dates))
    a = np.exp2(-age / half_life)
    dc, dd = m @ sm.cnt, m @ sm.dir
    return (dd @ a) / (dc @ a)


def date_weight_profile(plan: WindowPlan):
    """均匀密度（每天同样多买点）下，各日期在 Z 中的总权重，相对逐日近期权重的比值。"""
    n = len(plan.dates)
    L = plan.window_days
    w = plan._time_weights / plan._time_weights.sum()
    prefix = np.concatenate(([0], np.cumsum(w)))
    d = np.arange(n)
    lo, hi = np.clip(d - L + 1, 0, len(w)), np.clip(d + 1, 0, len(w))
    per_date = (prefix[hi] - prefix[lo]) / L  # 均匀密度时每窗 n_w 相同，1/n_w 为常数
    direct = np.exp2(-(n - 1 - d) / plan.half_life_days)
    direct = direct / direct.sum()
    ratio = per_date / direct
    return {
        "n_dates": n,
        "last_day_ratio": float(ratio[-1]), "last_5_mean_ratio": float(ratio[-5:].mean()),
        "last_21_mean_ratio": float(ratio[-21:].mean()), "first_21_mean_ratio": float(ratio[:21].mean()),
        "interior_ratio_median": float(np.median(ratio[21:-21])),
        "share_of_weight_last_21_Z": float(per_date[-21:].sum()),
        "share_of_weight_last_21_direct": float(direct[-21:].sum()),
    }


def main():
    out = {}
    for fold in ("fold1", "fold2"):
        res = {}
        tabs = {}
        for part in ("search", "check"):
            baseline, raw = load(fold, part)
            plan = WindowPlan(baseline, horizon=40, window_days=21, half_life_days=252, recent_days=126)
            cands = dedupe(raw)
            tab = {}
            for cid, rows in cands.items():
                if not len(rows):
                    continue
                s = plan.summarize(rows)
                pr, prb = recency_pooled(plan, rows)
                tab[cid] = {"Z": s["raw_direction_score"], "P": s["pooled_direction_score"], "PR": pr,
                            "B": s["matched_direction_score"], "PRB": prb, "N": s["count"]}
            tabs[part] = tab
            res[part + "_weight_profile"] = date_weight_profile(plan)
            if part == "search":
                df = pd.DataFrame(tab).T
                res["search_corr"] = {
                    "spearman_Z_P": float(df.Z.astype(float).corr(df.P.astype(float), method="spearman")),
                    "spearman_Z_PR": float(df.Z.astype(float).corr(df.PR.astype(float), method="spearman")),
                    "argmax_Z": df.Z.astype(float).idxmax(), "argmax_P": df.P.astype(float).idxmax(),
                    "argmax_PR": df.PR.astype(float).idxmax(),
                    "spread_Z_sd_across_cands": float(df.Z.astype(float).std()),
                    "spread_P_sd_across_cands": float(df.P.astype(float).std()),
                }
                symbols = sorted(baseline.symbol.unique())
                m = RNG.multinomial(len(symbols), np.full(len(symbols), 1 / len(symbols)), size=N_BOOT).astype(float)
                sds = {}
                base_sm = StockMatrix(plan, cands["base"], symbols)
                base_pr = pr_boot(base_sm, m)
                base_sc = base_sm.scores(m)
                for cid, rows in cands.items():
                    sm = StockMatrix(plan, rows, symbols)
                    pr_b = pr_boot(sm, m)
                    sc = sm.scores(m)
                    sds[cid] = {"sd_Z": float(np.nanstd(sc["Z"])), "sd_P": float(np.nanstd(sc["P"])),
                                "sd_PR": float(np.nanstd(pr_b)),
                                "sd_vs_base_Z": float(np.nanstd(sc["Z"] - base_sc["Z"])),
                                "sd_vs_base_PR": float(np.nanstd(pr_b - base_pr))}
                res["boot_sd"] = sds
                # 普通池：方向 vs 当日波动百分位
                bl = baseline.copy()
                bl["dir"] = bl.up - bl.down
                bl["mpct"] = bl.groupby("date").M.rank(pct=True)
                bl["mdec"] = np.minimum((bl.mpct * 10).astype(int), 9)
                res["pool_dir_by_M_decile"] = bl.groupby("mdec").dir.mean().round(4).to_dict()
                res["pool_none_by_M_decile"] = bl.groupby("mdec").none.mean().round(4).to_dict()
                bl["month"] = pd.to_datetime(bl.date).dt.to_period("M").astype(str)
                res["pool_none_by_month"] = bl.groupby("month").none.mean().round(3).to_dict()
                res["pool_dir_by_month"] = bl.groupby("month").dir.mean().round(3).to_dict()
                # 候选买点的当日波动百分位
                base_rows = cands["base"].merge(bl[["symbol", "date", "mpct"]], on=["symbol", "date"])
                res["base_buy_M_pct_quantiles"] = base_rows.mpct.quantile([0.1, 0.25, 0.5, 0.75, 0.9]).round(3).to_dict()
                # 顶档 (≥0.8) 内部：方向随百分位
                top = bl[bl.mpct > 0.8]
                res["pool_dir_top_quintile_split"] = {
                    "0.8-0.9": float(top[top.mpct <= 0.9].dir.mean()),
                    "0.9-0.95": float(top[(top.mpct > 0.9) & (top.mpct <= 0.95)].dir.mean()),
                    "0.95-1": float(top[top.mpct > 0.95].dir.mean())}
        # 搜索→后段
        common = [c for c in tabs["search"] if c in tabs["check"]]
        pred = {}
        for key in ("Z", "P", "PR"):
            x = pd.Series([tabs["search"][c][key] for c in common], dtype=float)
            y = pd.Series([tabs["check"][c][key] for c in common], dtype=float)
            pred[key] = {"n": len(common), "spearman": float(x.corr(y, method="spearman")),
                         "pearson": float(x.corr(y))}
        res["search_to_check"] = pred
        res["tables"] = tabs
        out[fold] = res
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float))
    for fold, r in out.items():
        print("=====", fold)
        for k, v in r.items():
            if k in ("tables", "boot_sd"):
                continue
            print(k, v)
        print(pd.DataFrame(r["boot_sd"]).T.round(4).describe().round(4).to_string())


if __name__ == "__main__":
    main()
