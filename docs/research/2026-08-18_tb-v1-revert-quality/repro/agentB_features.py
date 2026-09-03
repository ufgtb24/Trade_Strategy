# -*- coding: utf-8 -*-
"""agentB:回踩下降段(bo+1 .. confirm-1)形态特征 × 前向收益(fr) 分析。

独立视角(不读 agentA/analysis_report 产物),只用 samples.pkl。

口径约定:
  - B  = burst 段行号 [burst_start, bo_idx](上涨串,含最后突破根 bo)
  - R  = revert 下降段 [bo_idx+1, confirm-1](confirm 为企稳确认,不进段)
  - TR_med = B 段 true range 中位数(波动基线,仅用 confirm 前数据)
  - burst_gain = close[bo]/close[burst_start-1] - 1
标签: fr 越小越坏。坏 = bottom20 / 好 = top20(按 fr 排序)。
输出: agentB_features.csv(每样本一行全特征)+ 控制台特征排名。
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "samples.pkl"
OUT_CSV = HERE / "agentB_features.csv"
N_TAIL = 20


# ---------- 基础量 ----------

def true_ranges(win: pd.DataFrame, lo: int, hi: int) -> np.ndarray:
    """[lo,hi] 行号闭区间的 true range 数组(需 lo>=1,有前收盘)。"""
    h = win["high"].to_numpy()[lo - 1:hi + 1]
    l = win["low"].to_numpy()[lo - 1:hi + 1]
    pc = win["close"].to_numpy()[lo - 2:hi]
    return np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])


def max_streak(closes: np.ndarray) -> tuple[int, float]:
    """最长连续下跌(close<前收)天数与该段累计跌幅(比例,<0)。"""
    best_len, best_drop, i = 0, 0.0, 0
    n = len(closes)
    while i < n:
        if closes[i] < closes[i - 1]:
            j = i
            while j < n and closes[j] < closes[j - 1]:
                j += 1
            drop = closes[j - 1] / closes[i - 1] - 1
            if (j - i) > best_len or ((j - i) == best_len and drop < best_drop):
                best_len, best_drop = j - i, drop
            i = j
        else:
            i += 1
    return best_len, best_drop


def featurize(r: dict) -> dict:
    win = r["win"]
    o = win["open"].to_numpy()
    h = win["high"].to_numpy()
    l = win["low"].to_numpy()
    c = win["close"].to_numpy()
    v = win["volume"].to_numpy().astype(float)
    bs, bo, cf = r["burst_start"], r["bo_idx"], r["confirm"]
    R = range(bo + 1, cf)                      # 下降段(不含 confirm)
    f: dict[str, float] = {}
    # 基线
    tr_med = float(np.median(true_ranges(win, bs, bo)))
    burst_gain = c[bo] / c[bs - 1] - 1
    peak = float(h[bs:bo + 1].max())
    f["base_tr_med"] = tr_med
    f["base_burst_gain"] = burst_gain
    # ---- 单日跌幅类(假设1/5) ----
    day_drop = np.array([(c[i - 1] - c[i]) / c[i - 1] for i in R])
    f["dd_max_raw"] = day_drop.max()
    f["dd_max_tr"] = day_drop.max() * c[bo] / tr_med          # 比例→TR 个数
    f["dd_max_bg"] = day_drop.max() / burst_gain               # 单日吐回涨幅比例
    f["dd_sum_bg"] = day_drop.sum() / burst_gain               # 整段累计吐回比例
    # 阴线实体(仅阴线日)
    bodies = np.array([(o[i] - c[i]) for i in R if c[i] < o[i]])
    f["body_max_tr"] = (bodies.max() / tr_med) if len(bodies) else 0.0
    f["body_max_bg"] = (bodies.max() / c[bo] / burst_gain) if len(bodies) else 0.0
    # ---- 上影线类(假设2) ----
    wick = np.array([h[i] - max(o[i], c[i]) for i in R])
    rng = np.array([h[i] - l[i] for i in R])
    f["wick_max_tr"] = wick.max() / tr_med
    f["wick_max_bg"] = wick.max() / c[bo] / burst_gain
    f["wick_close_frac"] = (wick / np.maximum(rng, 1e-12)).max()
    # ---- 连续阴线类(假设3) ----
    closes_R = c[bo:cf]                                        # 含 bo 收盘作起点
    stk_len, stk_drop = max_streak(closes_R)
    f["streak_max"] = stk_len
    f["streak_drop_bg"] = stk_drop / burst_gain
    f["red_frac"] = float(np.mean([c[i] < c[i - 1] for i in R]))
    f["n_red"] = float(np.sum([c[i] < c[i - 1] for i in R]))
    # ---- 回撤跌破类(假设4) ----
    tr_ = r["trough"]
    f["ddown_peak"] = c[tr_] / peak - 1                        # 相对 burst 峰 high
    f["ddown_bo"] = c[tr_] / c[bo] - 1
    f["ddown_bg"] = (c[bo] - c[tr_]) / c[bo] / burst_gain      # 吐回涨幅比例
    f["low_vs_start"] = float(l[bo + 1:cf].min()) / c[bs - 1] - 1
    f["n_below_start"] = float(np.sum([c[i] < c[bs - 1] for i in R]))
    f["below_start"] = float(f["n_below_start"] > 0)
    # ---- 量能/结构变体 ----
    f["vol_ratio"] = float(np.mean(v[bo + 1:cf])) / float(np.mean(v[bs:bo + 1]))
    v_red = [v[i] for i in R if c[i] < c[i - 1]]
    f["vol_red_ratio"] = (float(np.mean(v_red)) / float(np.mean(v[bs:bo + 1]))
                          if v_red else 0.0)
    f["revert_len"] = float(cf - bo - 1)
    f["slope_dd"] = f["ddown_bo"] / f["revert_len"]
    f["high_decay"] = h[cf - 1] / h[bo] - 1
    gaps = np.array([(c[i - 1] - o[i]) / c[i - 1] for i in R])
    f["gap_max_tr"] = gaps.max() * c[bo] / tr_med
    pos = np.array([(c[i] - l[i]) / max(h[i] - l[i], 1e-12) for i in R])
    f["close_pos_min"] = pos.min()
    f["confirm_recover"] = c[cf] / c[tr_] - 1
    f["trough_lag"] = float(tr_ - bo)
    # ---- burst 控制变量 ----
    f["burst_len"] = float(bo - bs + 1)
    f["burst_slope"] = burst_gain / f["burst_len"]
    f["bo_close_pos"] = (c[bo] - float(l[bs:bo + 1].min())) / (peak - float(l[bs:bo + 1].min()))
    return f


def auc_bad_gt_good(x_bad: np.ndarray, x_good: np.ndarray) -> float:
    """AUC = P(feat_bad > feat_good),并列记 0.5。"""
    n = 0.0
    for a in x_bad:
        n += np.sum(a > x_good) + 0.5 * np.sum(a == x_good)
    return n / (len(x_bad) * len(x_good))


def main() -> None:
    rows = pickle.loads(SAMPLES.read_bytes())
    feats = []
    for r in rows:
        d = featurize(r)
        d["symbol"] = r["symbol"]
        d["match_id"] = r["match_id"]
        d["fr"] = r["fr"]
        d["fp"] = r["fp"]
        feats.append(d)
    df = pd.DataFrame(feats)
    df.to_csv(OUT_CSV, index=False)

    order = df["fr"].rank(method="first")
    bad = df[order <= N_TAIL]            # fr 最小 20
    good = df[order > len(df) - N_TAIL]  # fr 最大 20
    feat_cols = [c for c in df.columns if c not in ("symbol", "match_id", "fr", "fp")]

    out = []
    rng = np.random.default_rng(42)
    for col in feat_cols:
        xb = bad[col].to_numpy(float)
        xg = good[col].to_numpy(float)
        a = auc_bad_gt_good(xb, xg)
        rho = stats.spearmanr(df[col], df["fr"]).statistic
        # bootstrap AUC CI(层内重采样 1000 次)
        bs_aucs = []
        for _ in range(1000):
            ib = xb[rng.integers(0, len(xb), len(xb))]
            ig = xg[rng.integers(0, len(xg), len(xg))]
            bs_aucs.append(auc_bad_gt_good(ib, ig))
        lo95, hi95 = np.percentile(bs_aucs, [2.5, 97.5])
        out.append(dict(feat=col, auc=round(a, 3), lo95=round(lo95, 3), hi95=round(hi95, 3),
                        spearman=round(rho, 3),
                        bad_med=np.median(xb), good_med=np.median(xg)))
    rep = pd.DataFrame(out).sort_values("auc", ascending=False, ignore_index=True)
    pd.set_option("display.width", 200)
    print(rep.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"\nn_bad={len(bad)} n_good={len(good)}  fr range bad "
          f"[{bad['fr'].min():.3f},{bad['fr'].max():.3f}] good "
          f"[{good['fr'].min():.3f},{good['fr'].max():.3f}]")


if __name__ == "__main__":
    main()
