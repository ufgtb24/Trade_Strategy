"""评分口径评审的数值核查（临时研究脚本，不入正式代码）。

用 2026-10-02 bb 训练对照的 parquet，比较 v3 主分 Z（窗口内买点等权、窗口间近期加权）
与「合并买点直接平均」P 的：
  1. 每个买点日在 Z 里的实际权重形状（有效样本量、按股票的有效股票数）；
  2. 按股票整只重抽（cluster bootstrap）下的波动大小、候选间配对差的波动、排名稳定性；
  3. 搜索段分数对后段分数的预测力（28 个去重候选，非独立，只作方向性参考）；
  4. 各约束在两折里分别卡掉多少候选。
输出写 repro/objective_noise_results.json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".claude/skills/tune-gates-v3/scripts"))
from scoring import WindowPlan, assess  # noqa: E402

DATA = ROOT / "docs/research/2026-10-02_v3-bb-training-calibration"
OUT = Path(__file__).with_name("objective_noise_results.json")
N_BOOT = 2000
RNG = np.random.default_rng(20261005)


def load(fold: str, part: str):
    base = pd.read_parquet(DATA / f"{fold}_{part}_baseline.parquet")
    cands = pd.read_parquet(DATA / f"{fold}_{part}_candidates.parquet")
    return base, cands


def dedupe(cands: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """按买点集合去重，base 优先，其余按出现顺序（与原协议一致）。"""
    seen, out = {}, {}
    order = ["base"] + [c for c in dict.fromkeys(cands.candidate_id) if c != "base"]
    for cid in order:
        rows = cands[cands.candidate_id == cid].drop(columns="candidate_id").reset_index(drop=True)
        key = tuple(sorted(zip(rows.symbol, rows.date)))
        if key in seen:
            continue
        seen[key] = cid
        out[cid] = rows
    return out


def effective_weights(plan: WindowPlan, rows: pd.DataFrame) -> np.ndarray:
    """每个买点日在 Z 中的实际权重：sum_{窗口∋该日, 非空} omega_w / n_w。"""
    stats = plan.window_statistics(rows)
    active, w, n = stats["active"], stats["weights"], stats["count"]
    per_window = np.zeros(len(n))
    per_window[active] = w[active] / n[active]
    # 日期 d 属于起点 s∈[d-L+1, d] 的窗口
    prefix = np.concatenate(([0], np.cumsum(per_window)))
    L = plan.window_days
    n_dates = len(plan.dates)
    d = np.arange(n_dates)
    lo = np.clip(d - L + 1, 0, len(per_window))
    hi = np.clip(d + 1, 0, len(per_window))
    per_date = prefix[hi] - prefix[lo]
    idx = plan._date_indices[plan._indices_checked(rows)]
    return per_date[idx]


class StockMatrix:
    """把一个候选的买点按 股票×日期 摊开，便于整只股票重抽时快速重算。"""

    def __init__(self, plan: WindowPlan, rows: pd.DataFrame, symbols: list[str]):
        idx = plan._indices_checked(rows)
        date_ids = plan._date_indices[idx]
        sym_pos = pd.Index(symbols).get_indexer(rows.symbol)
        nd = len(plan.dates)
        self.cnt = np.zeros((len(symbols), nd))
        self.dir = np.zeros((len(symbols), nd))
        self.mat = np.zeros((len(symbols), nd))
        np.add.at(self.cnt, (sym_pos, date_ids), 1)
        np.add.at(self.dir, (sym_pos, date_ids), plan._direction[idx])
        np.add.at(self.mat, (sym_pos, date_ids), plan._matched_direction[idx])
        self.plan = plan

    def scores(self, m: np.ndarray) -> dict:
        """m: (B, n_symbols) 每只股票被抽中的次数。返回 Z、B、P、PB 各 (B,)。"""
        p = self.plan
        dc, dd, dm = m @ self.cnt, m @ self.dir, m @ self.mat  # (B, n_dates)
        def roll(x):
            pre = np.concatenate([np.zeros((x.shape[0], 1)), np.cumsum(x, axis=1)], axis=1)
            return pre[:, p.ends + 1] - pre[:, p.starts]
        c, s, sm = roll(dc), roll(dd), roll(dm)
        active = c > 0
        a = np.where(active, p._time_weights[None, :], 0.0)
        denom = a.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            z = np.where(active, s / np.where(active, c, 1), 0.0)
            b = np.where(active, sm / np.where(active, c, 1), 0.0)
            Z = (a * z).sum(axis=1) / denom
            B = (a * b).sum(axis=1) / denom
            N = dc.sum(axis=1)
            P = dd.sum(axis=1) / N
            PB = dm.sum(axis=1) / N
        return {"Z": Z, "B": B, "P": P, "PB": PB, "N": N}


def constraint_table(cands: dict, plan, baseline) -> dict:
    ref = cands["base"]
    out = {}
    for cid, rows in cands.items():
        res = assess(rows, ref, baseline, plan, {})
        st = res["statistics"]
        out[cid] = {
            "feasible": res["feasible"],
            "failed": [n for n, v in zip(res["constraint_names"], res["constraints"]) if v > 0],
            "N": st["count"], "stocks": st["stocks"],
            "Z": st["raw_direction_score"], "P": st["pooled_direction_score"],
            "B": st["matched_direction_score"], "Delta": st["direction_difference"],
            "resolved": st["resolved_fraction"], "q": st["direction"],
            "recent": st["coverage"]["recent_buy_days"],
            "active_windows": st["window"]["active"], "total_windows": st["window"]["total"],
        }
    return out


def kish(w: np.ndarray) -> float:
    w = w / w.sum()
    return float(1.0 / (w ** 2).sum())


def analyze_fold(fold: str) -> dict:
    res = {}
    for part in ("search", "check"):
        baseline, raw = load(fold, part)
        plan = WindowPlan(baseline, horizon=40, window_days=21, half_life_days=252, recent_days=126)
        cands = dedupe(raw)
        table = constraint_table(cands, plan, baseline)
        # 实际权重形状
        shapes = {}
        for cid, rows in cands.items():
            if not len(rows):
                continue
            w = effective_weights(plan, rows)
            z_check = float(w @ plan._direction[plan._indices_checked(rows)])
            stock_w = pd.Series(w).groupby(rows.symbol.values).sum()
            stock_n = rows.symbol.value_counts()
            shapes[cid] = {
                "N": len(rows), "kish_rows_Z": kish(w), "z_reconstructed_minus_Z": z_check - table[cid]["Z"],
                "eff_stocks_Z": float(1 / ((stock_w / stock_w.sum()) ** 2).sum()),
                "eff_stocks_pooled": float(1 / ((stock_n / stock_n.sum()) ** 2).sum()),
                "max_row_weight_x_N": float(w.max() / w.sum() * len(rows)),
                "top_stock_share_Z": float(stock_w.max() / stock_w.sum()),
                "top_stock_share_pooled": float(stock_n.max() / stock_n.sum()),
                "row_weight_p10_p90_x_N": [float(np.quantile(w / w.sum() * len(rows), q)) for q in (0.1, 0.5, 0.9)],
            }
        res[part] = {"table": table, "shapes": shapes}
        if part == "search":
            symbols = sorted(baseline.symbol.unique())
            mats = {cid: StockMatrix(plan, rows, symbols) for cid, rows in cands.items() if len(rows)}
            m = RNG.multinomial(len(symbols), np.full(len(symbols), 1 / len(symbols)), size=N_BOOT).astype(float)
            boot = {cid: sm.scores(m) for cid, sm in mats.items()}
            # 原样本（m=1）复核与 WindowPlan 一致
            ones = np.ones((1, len(symbols)))
            check = {cid: {k: float(v[0]) for k, v in sm.scores(ones).items()} for cid, sm in mats.items()}
            res[part]["bootstrap_identity_check"] = {
                cid: [check[cid]["Z"] - table[cid]["Z"], check[cid]["P"] - table[cid]["P"],
                      check[cid]["B"] - table[cid]["B"]] for cid in check}
            sd = {}
            for cid, b in boot.items():
                ok = np.isfinite(b["Z"]) & np.isfinite(b["P"])
                sd[cid] = {
                    "N": table[cid]["N"], "stocks": table[cid]["stocks"],
                    "sd_Z": float(np.nanstd(b["Z"][ok])), "sd_P": float(np.nanstd(b["P"][ok])),
                    "sd_Delta_Z": float(np.nanstd((b["Z"] - b["B"])[ok])),
                    "sd_Delta_P": float(np.nanstd((b["P"] - b["PB"])[ok])),
                    "sd_vs_base_Z": float(np.nanstd((b["Z"] - boot["base"]["Z"])[ok])),
                    "sd_vs_base_P": float(np.nanstd((b["P"] - boot["base"]["P"])[ok])),
                    "frac_empty": float((~ok).mean()),
                }
            res[part]["bootstrap_sd"] = sd
            # 排名稳定性：全部去重候选（不加约束）在重抽中的 argmax 与原样本 argmax 一致的比例，
            # 以及重抽分数与原样本分数的 Spearman 平均
            ids = list(boot)
            for key in ("Z", "P"):
                M = np.vstack([boot[c][key] for c in ids]).T  # (B, C)
                orig = np.array([table[c][key] for c in ids])
                M = np.where(np.isfinite(M), M, -np.inf)
                top = np.argmax(M, axis=1)
                ranks_o = pd.Series(orig).rank().to_numpy()
                sp = [np.corrcoef(pd.Series(r).rank().to_numpy(), ranks_o)[0, 1] for r in M[:200]]
                res[part][f"rank_{key}"] = {
                    "orig_top": ids[int(np.argmax(orig))],
                    "same_top_frac": float((top == int(np.argmax(orig))).mean()),
                    "n_distinct_tops": int(len(np.unique(top))),
                    "mean_spearman_vs_orig": float(np.mean(sp)),
                }
    # 搜索→后段 预测力
    s_tab, c_tab = res["search"]["table"], res["check"]["table"]
    common = [c for c in s_tab if c in c_tab]
    pred = {}
    for key in ("Z", "P", "Delta"):
        x = np.array([s_tab[c][key] for c in common], dtype=float)
        y = np.array([c_tab[c][key] for c in common], dtype=float)
        ok = np.isfinite(x) & np.isfinite(y)
        pred[key] = {"n": int(ok.sum()),
                     "pearson": float(np.corrcoef(x[ok], y[ok])[0, 1]) if ok.sum() > 2 else None,
                     "spearman": float(pd.Series(x[ok]).corr(pd.Series(y[ok]), method="spearman")) if ok.sum() > 2 else None}
    # 用 P 作 Delta 的配对口径
    x = np.array([s_tab[c]["P"] - s_tab[c]["B"] for c in common])
    res["search_to_check"] = pred
    return res


def main():
    out = {fold: analyze_fold(fold) for fold in ("fold1", "fold2")}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float))
    for fold, r in out.items():
        print("=====", fold)
        for part in ("search", "check"):
            t = r[part]["table"]
            print(part, "feasible:", sum(v["feasible"] for v in t.values()), "/", len(t))
            fails = pd.Series([f for v in t.values() for f in v["failed"]]).value_counts()
            print(fails.to_dict())
        print("base shape search:", r["search"]["shapes"]["base"])
        sd = pd.DataFrame(r["search"]["bootstrap_sd"]).T
        print(sd.round(4).to_string())
        print("rank Z", r["search"]["rank_Z"]); print("rank P", r["search"]["rank_P"])
        print("search->check", r["search_to_check"])
        print("identity max", np.max(np.abs(np.array(list(r["search"]["bootstrap_identity_check"].values())))))


if __name__ == "__main__":
    main()
