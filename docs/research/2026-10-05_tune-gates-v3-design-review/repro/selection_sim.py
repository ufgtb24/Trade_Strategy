"""选参链（训练挑选 → 一次最后检查 → 暂用/复核）的数值核查（临时研究脚本，不入正式代码）。

数据：2026-10-02 bb 训练对照的 parquet（两折 × 搜索段/后段），28 个去重候选。
噪声模型：按股票整只重抽（普通池固定不抽，只重抽候选买点所在股票的倍数）。
问题：
  A. 训练挑选的虚高：真实世界 bootstrap（Efron optimism）与「全部候选都不比原参数好」的零假设世界
     下，赢家训练改善有多大；与实际观察到的赢家改善对比。
  B. 最大值挑选是否偏向「噪声大」的候选（买点少、离原参数远）。
  C. 最后检查一次的判别力：真实改善为 0 / δ 时进入「暂用」的概率；两段串联（若复核也用同一规则）。
  D. 候选在后段与原参数买点集合完全相同的比例（相同则差值恒 0，必然不采用）。
输出 repro/selection_sim_results.json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".claude/skills/tune-gates-v3/scripts"))
from scoring import WindowPlan, assess, DEFAULT_POLICY  # noqa: E402

DATA = ROOT / "docs/research/2026-10-02_v3-bb-training-calibration"
OUT = Path(__file__).with_name("selection_sim_results.json")
N_BOOT = 4000
RNG = np.random.default_rng(20261005)
EPS = 1e-12
DELTAS = [0.0, 0.03, 0.05, 0.10, 0.20]


def load(fold: str, part: str):
    return (pd.read_parquet(DATA / f"{fold}_{part}_baseline.parquet"),
            pd.read_parquet(DATA / f"{fold}_{part}_candidates.parquet"))


def split(cands: pd.DataFrame) -> dict[str, pd.DataFrame]:
    order = ["base"] + [c for c in dict.fromkeys(cands.candidate_id) if c != "base"]
    return {cid: cands[cands.candidate_id == cid].drop(columns="candidate_id").reset_index(drop=True)
            for cid in order}


def key_of(rows: pd.DataFrame):
    return tuple(sorted(zip(rows.symbol, pd.to_datetime(rows.date))))


class StockMatrix:
    """候选买点按 股票×日期 摊开；m 为每只股票被抽中次数 (B, n_symbols)。"""

    def __init__(self, plan: WindowPlan, rows: pd.DataFrame, symbols: list[str]):
        self.plan = plan
        nd = len(plan.dates)
        self.cnt = np.zeros((len(symbols), nd))
        self.dir = np.zeros((len(symbols), nd))
        self.mat = np.zeros((len(symbols), nd))
        if len(rows):
            idx = plan._indices_checked(rows)
            date_ids = plan._date_indices[idx]
            sym_pos = pd.Index(symbols).get_indexer(rows.symbol)
            np.add.at(self.cnt, (sym_pos, date_ids), 1)
            np.add.at(self.dir, (sym_pos, date_ids), plan._direction[idx])
            np.add.at(self.mat, (sym_pos, date_ids), plan._matched_direction[idx])
        self.recent_start = max(0, nd - plan.recent_days)

    def stats(self, m: np.ndarray) -> dict:
        p = self.plan
        dc, dd, dm = m @ self.cnt, m @ self.dir, m @ self.mat

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
            Z = np.where(denom > 0, (a * z).sum(axis=1) / np.where(denom > 0, denom, 1), np.nan)
            B = np.where(denom > 0, (a * b).sum(axis=1) / np.where(denom > 0, denom, 1), np.nan)
        return {"Z": Z, "B": B, "N": dc.sum(axis=1), "R": dc[:, self.recent_start:].sum(axis=1)}


def feasible(c: dict, ref: dict, pol=DEFAULT_POLICY) -> np.ndarray:
    """与 scoring._hard_constraints 同一组默认下限（空间/回撤默认不设）。"""
    Z, B = c["Z"], c["B"]
    ok = np.isfinite(Z)
    ok &= c["N"] >= pol["min_buy_days"]
    ok &= c["N"] >= pol["min_reference_fraction"] * ref["N"]
    ok &= c["R"] >= pol["min_recent_buy_days"]
    ok &= c["R"] >= pol["min_recent_reference_fraction"] * ref["R"]
    ok &= np.nan_to_num(Z, nan=-9) > pol["min_direction_score"]
    ok &= np.nan_to_num(Z - B, nan=-9) >= -pol["baseline_tolerance"] - 1e-12
    return ok


def prepare(fold: str, part: str):
    baseline, raw = load(fold, part)
    plan = WindowPlan(baseline, horizon=40, window_days=21, half_life_days=252, recent_days=126)
    cands = split(raw)
    symbols = sorted(baseline.symbol.unique())
    mats = {cid: StockMatrix(plan, rows, symbols) for cid, rows in cands.items()}
    ones = np.ones((1, len(symbols)))
    orig = {cid: {k: v[0] for k, v in sm.stats(ones).items()} for cid, sm in mats.items()}
    # 与正式 assess 对账
    ref_rows = cands["base"]
    for cid, rows in cands.items():
        if not len(rows):
            continue
        res = assess(rows, ref_rows, baseline, plan, {})
        st = res["statistics"]
        assert abs(st["raw_direction_score"] - orig[cid]["Z"]) < 1e-9, (fold, part, cid)
        f = feasible({k: np.array([v]) for k, v in orig[cid].items()},
                     {k: np.array([v]) for k, v in orig["base"].items()})[0]
        assert bool(f) == res["feasible"], (fold, part, cid, res["constraint_names"], res["constraints"])
    return plan, cands, symbols, mats, orig


def train_selection(fold: str) -> dict:
    plan, cands, symbols, mats, orig = prepare(fold, "search")
    # 去重：同一买点集合只留首个（base 优先）
    seen, ids = set(), []
    for cid, rows in cands.items():
        k = key_of(rows)
        if k in seen:
            continue
        seen.add(k)
        ids.append(cid)
    m = RNG.multinomial(len(symbols), np.full(len(symbols), 1 / len(symbols)), size=N_BOOT).astype(float)
    boot = {cid: mats[cid].stats(m) for cid in ids}
    ref = boot["base"]
    others = [c for c in ids if c != "base"]
    dZ = np.vstack([boot[c]["Z"] - ref["Z"] for c in others]).T            # (B, C)
    dZ0 = np.array([orig[c]["Z"] - orig["base"]["Z"] for c in others])        # (C,)
    feas = np.vstack([feasible(boot[c], ref) for c in others]).T               # (B, C)
    ofeas = np.array([feasible({k: np.array([v]) for k, v in orig[c].items()},
                               {k: np.array([v]) for k, v in orig["base"].items()})[0] for c in others])
    sd_pair = np.nanstd(dZ, axis=0)

    def pick(score, ok):
        s = np.where(ok & np.isfinite(score), score, -np.inf)
        j = np.argmax(s, axis=1)
        best = s[np.arange(len(s)), j]
        return j, best

    # 原样本的实际挑选
    s0 = np.where(ofeas, dZ0, -np.inf)
    j0 = int(np.argmax(s0)) if np.isfinite(s0).any() else None
    observed = {"winner": others[j0] if j0 is not None and s0[j0] > EPS else None,
                "winner_improvement": float(s0[j0]) if j0 is not None and np.isfinite(s0[j0]) else None,
                "winner_paired_sd": float(sd_pair[j0]) if j0 is not None else None,
                "feasible_count": int(ofeas.sum())}

    # A1 真实世界 Efron optimism：在重抽样本里挑，再看该候选在原样本的改善
    j, best = pick(dZ, feas)
    sel = np.isfinite(best) & (best > EPS)
    optimism = best[sel] - dZ0[j[sel]]
    eff = {"select_rate": float(sel.mean()),
           "mean_optimism": float(optimism.mean()) if sel.any() else None,
           "median_optimism": float(np.median(optimism)) if sel.any() else None,
           "optimism_over_selected_sd": float(np.mean(optimism / sd_pair[j[sel]])) if sel.any() else None,
           "distinct_winners": int(len(np.unique(j[sel]))),
           "top_winner_share": float(pd.Series(j[sel]).value_counts(normalize=True).iloc[0]) if sel.any() else None}

    # A2 零假设世界：每个候选真实改善都为 0，保留真实的噪声相关结构
    noise = dZ - dZ0[None, :]
    nullZ = {c: ref["Z"] + noise[:, i] for i, c in enumerate(others)}
    nfeas = np.vstack([feasible({**boot[c], "Z": nullZ[c]}, ref) for c in others]).T
    jn, bn = pick(noise, nfeas)
    nsel = np.isfinite(bn) & (bn > EPS)
    null = {"select_rate": float(nsel.mean()),
            "winner_improvement_q50_q90_q95": [float(np.quantile(bn[nsel], q)) for q in (0.5, 0.9, 0.95)] if nsel.any() else None,
            "mean_winner_improvement": float(bn[nsel].mean()) if nsel.any() else None,
            "p_ge_observed": (float((bn[nsel] >= observed["winner_improvement"]).mean())
                              if nsel.any() and observed["winner_improvement"] is not None else None),
            "winner_sd_vs_median_candidate_sd": float(np.median(sd_pair[jn[nsel]]) / np.median(sd_pair)) if nsel.any() else None}

    # B 最大值偏向噪声大的候选：被选中频率 vs 配对噪声；被选中者的 N
    freq = pd.Series(jn[nsel]).value_counts(normalize=True).reindex(range(len(others)), fill_value=0).to_numpy()
    N0 = np.array([orig[c]["N"] for c in others])
    corr = float(pd.Series(freq).corr(pd.Series(sd_pair), method="spearman"))
    per = {c: {"N": int(N0[i]), "paired_sd": float(sd_pair[i]), "dZ_orig": float(dZ0[i]),
               "feasible_orig": bool(ofeas[i]), "null_win_share": float(freq[i])} for i, c in enumerate(others)}
    return {"observed": observed, "efron": eff, "null": null,
            "spearman_winshare_vs_paired_sd": corr,
            "median_paired_sd": float(np.median(sd_pair)), "ref_sd_Z": float(np.nanstd(ref["Z"])),
            "per_candidate": per, "n_unique": len(ids)}


def final_check(fold: str) -> dict:
    """把每个候选当作「被冻结进最后检查」的那一个，算各 δ 下进入暂用的概率。"""
    plan, cands, symbols, mats, orig = prepare(fold, "check")
    base_key = key_of(cands["base"])
    m = RNG.multinomial(len(symbols), np.full(len(symbols), 1 / len(symbols)), size=N_BOOT).astype(float)
    ref = mats["base"].stats(m)
    rows = {}
    for cid in cands:
        if cid == "base":
            continue
        identical = key_of(cands[cid]) == base_key
        st = mats[cid].stats(m)
        d0 = orig[cid]["Z"] - orig["base"]["Z"]
        dz = st["Z"] - ref["Z"]
        noise = dz - d0
        # 重抽里差异股票一只没抽到时，候选与原参数买点完全相同：差值只能是 0（平局 → 不采用），不加 δ
        same = (np.abs(np.nan_to_num(dz, nan=0)) <= EPS) & (st["N"] == ref["N"])
        out = {"identical_to_base": identical, "N": int(orig[cid]["N"]),
               "paired_sd": float(np.nanstd(dz)), "same_draw_share": float(same.mean()),
               "d0": float(d0)}
        for delta in DELTAS:
            diff = np.zeros_like(noise) if identical else np.where(same, 0.0, noise + delta)
            cand = {**st, "Z": ref["Z"] + diff}
            ok = feasible(cand, ref) & (np.nan_to_num(diff, nan=-9) > EPS)
            out[f"p_prov_delta_{delta}"] = float(ok.mean())
            # 只看「改善」那一条（去掉绝对水平约束），显示纯符号检验的判别力
            out[f"p_diffpos_delta_{delta}"] = float((np.nan_to_num(diff, nan=-9) > EPS).mean())
        rows[cid] = out
    df = pd.DataFrame(rows).T
    summary = {"n_candidates": len(df), "identical_share": float(df.identical_to_base.astype(bool).mean()),
               "median_paired_sd_nonidentical": float(df.loc[~df.identical_to_base.astype(bool), "paired_sd"].median()),
               "ref_sd_Z": float(np.nanstd(ref["Z"])), "ref_Z": float(orig["base"]["Z"]),
               "ref_N": int(orig["base"]["N"])}
    for delta in DELTAS:
        summary[f"mean_p_prov_delta_{delta}"] = float(df[f"p_prov_delta_{delta}"].astype(float).mean())
        nonid = df.loc[~df.identical_to_base.astype(bool)]
        summary[f"mean_p_diffpos_nonidentical_delta_{delta}"] = float(nonid[f"p_diffpos_delta_{delta}"].astype(float).mean())
    return {"summary": summary, "per_candidate": rows}


def main():
    out = {}
    for fold in ("fold1", "fold2"):
        out[fold] = {"train": train_selection(fold), "final": final_check(fold)}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float))
    for fold, r in out.items():
        t = r["train"]
        print("=====", fold, "unique", t["n_unique"])
        print("observed", t["observed"])
        print("efron", t["efron"])
        print("null", t["null"])
        print("winshare~paired_sd spearman", round(t["spearman_winshare_vs_paired_sd"], 3),
              "median paired sd", round(t["median_paired_sd"], 4), "ref sd Z", round(t["ref_sd_Z"], 4))
        print("final", json.dumps(r["final"]["summary"], indent=0))


if __name__ == "__main__":
    main()
