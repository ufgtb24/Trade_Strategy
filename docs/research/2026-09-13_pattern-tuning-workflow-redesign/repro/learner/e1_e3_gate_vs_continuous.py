# -*- coding: utf-8 -*-
"""learner 方法实验 E1-E3(只读既有 CSV,不扫描、不跑检测)。

数据 = FC-007/008/009/010 的发现样本
(docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/wide_w202{4,5}.csv:宽进 match,
四道 burst 闸放到最松;anchor_baseline_w202{4,5}.csv:随机日基线,每日带 atr_pct 与 k=5 首次穿越态)。
这份数据对这几条条目已烧掉,本脚本只做「方法对照」,不构成任何条目的验证。

E1 推断引擎:现电池(秩相关 + 子抽样去簇)在首次穿越标签下 vs 全样本簇稳健加权回归
   (股簇 / 时间簇 / 双向 + 时间簇 wild cluster bootstrap)——比较功效与样本用量。
E2 闸式判定 vs 连续判定:阈值切分后保留子集相对「不设闸」的首次穿越率差,
   两种波动率调整(池内 ATR 分层 / 随机日层匹配基线),按股整簇自助 CI;逐年。
E3 首次穿越率随 ATR 分层的斜率:池内 vs 随机日——决定两种调整是否等价。

首次穿越率口径 = up/(up+down+both)(none 不进分母),与 tune-gates 执行端 region_core.fp_count 一致。
"""
import contextlib
import io
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[5]
SRC = ROOT / "docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro"
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".claude/skills/feature-study"))
from run_battery import run_battery  # noqa: E402

FEATS = ["distinct_pk", "first_drought", "vol_spike", "peak_age", "burst_count"]
BUCKET_CAL = round(40 * 365 / 252)      # 58 日历天 = label_horizon 40 交易日
RNG = np.random.default_rng(20260913)


UNIT = os.environ.get("UNIT", "row")   # row = 每条 match 一行(原口径);segment = 每个回踩段只计一次


def load(tag):
    d = pd.read_csv(SRC / f"wide_{tag}.csv", keep_default_na=False, na_values=[""])
    if UNIT == "segment":
        # 同一回踩段(symbol, tb_start, tb_end)可被多个 burst 前缀各配一次,label 相同;
        # 段级闸语义 = 任一前缀过闸 ⟺ 各前缀字段取 max 后过闸(本脚本闸都是 >=)
        key = ["symbol", "tb_start", "tb_end"]
        agg = {c: "max" for c in FEATS}
        agg.update({c: "first" for c in ["tb_date", "fp_up", "fp_down", "fp_both", "fp_none", "atr_pct", "fr"]})
        d = d.groupby(key, as_index=False).agg(agg)
    d["den"] = d.fp_up + d.fp_down + d.fp_both
    d = d[d.den > 0].copy()
    d["p"] = d.fp_up / d.den
    d["entry_date"] = pd.to_datetime(d.tb_date)
    d["year"] = tag
    return d


def load_base(tag):
    b = pd.read_csv(SRC / f"anchor_baseline_{tag}.csv", keep_default_na=False, na_values=[""])
    b = b[b.fp.isin(["up", "down", "both"])].copy()
    b["up"] = (b.fp == "up").astype(float)
    return b


# ───────────────────────── E1 ─────────────────────────

def wls_fit(y, X, w):
    XtWX = X.T @ (X * w[:, None])
    inv = np.linalg.inv(XtWX)
    beta = inv @ (X.T @ (w * y))
    return beta, inv


def cr_var_j(X, w, e, inv, codes, j):
    """CR1 簇稳健方差的第 j 个对角元;e 可为 (n,) 或 (B,n)。"""
    n, k = X.shape
    G = codes.max() + 1
    c = G / (G - 1) * (n - 1) / (n - k)
    proj = X @ inv[j]                      # (n,)  a_i = inv[j]·x_i
    if e.ndim == 1:
        s = np.bincount(codes, weights=proj * w * e, minlength=G)
        return c * (s ** 2).sum()
    B = e.shape[0]
    onehot = np.zeros((n, G)); onehot[np.arange(n), codes] = 1.0
    s = (e * (proj * w)[None, :]) @ onehot  # (B,G)
    return c * (s ** 2).sum(1)


def e1_regression(d, feat, controls, n_boot=1999):
    y = d["p"].to_numpy(float)
    w = d["den"].to_numpy(float)
    cols = [feat] + controls
    R = d[cols].rank(pct=True).to_numpy(float)
    X = np.column_stack([np.ones(len(d)), R])
    beta, inv = wls_fit(y, X, w)
    e = y - X @ beta
    sym = pd.factorize(d["symbol"])[0]
    tim = pd.factorize(((d["entry_date"] - d["entry_date"].min()).dt.days // BUCKET_CAL))[0]
    inter = pd.factorize(pd.Series(sym).astype(str) + "_" + pd.Series(tim).astype(str))[0]
    j = 1
    v_sym = cr_var_j(X, w, e, inv, sym, j)
    v_tim = cr_var_j(X, w, e, inv, tim, j)
    v_int = cr_var_j(X, w, e, inv, inter, j)
    v_two = v_sym + v_tim - v_int
    if v_two <= 0:
        v_two = max(v_sym, v_tim)
    out = dict(beta=beta[j], t_sym=beta[j] / np.sqrt(v_sym), t_time=beta[j] / np.sqrt(v_tim),
               t_two=beta[j] / np.sqrt(v_two), G_sym=sym.max() + 1, G_time=tim.max() + 1)
    # wild cluster bootstrap-t(时间簇,Webb 六点权重,零假设施加 = restricted)
    Xr = np.delete(X, j, axis=1)
    br, _ = wls_fit(y, Xr, w)
    yhat_r = Xr @ br
    er = y - yhat_r
    G = tim.max() + 1
    webb = np.array([-np.sqrt(1.5), -1, -np.sqrt(.5), np.sqrt(.5), 1, np.sqrt(1.5)])
    t_obs = out["t_time"]
    exceed = 0
    done = 0
    while done < n_boot:
        b = min(500, n_boot - done)
        v = webb[RNG.integers(0, 6, size=(b, G))]
        Ys = yhat_r[None, :] + v[:, tim] * er[None, :]
        bet = (inv @ (X.T @ (Ys * w[None, :]).T)).T      # (b,k)
        Es = Ys - bet @ X.T
        vj = cr_var_j(X, w, Es, inv, tim, j)
        ts = bet[:, j] / np.sqrt(vj)
        exceed += int((np.abs(ts) >= abs(t_obs)).sum())
        done += b
    out["p_wcb_time"] = (exceed + 1) / (n_boot + 1)
    return out


def e1(d, label):
    print(f"\n######## E1 [{label}] n={len(d)} symbols={d.symbol.nunique()} "
          f"时间桶(58 日历天)={((d.entry_date - d.entry_date.min()).dt.days // BUCKET_CAL).nunique()}")
    tmp = OUT / f"_tmp_e1_{label}.csv"
    d[["symbol", "entry_date", "p", "atr_pct"] + FEATS].rename(columns={"p": "label"}) \
        .assign(entry_date=lambda x: x.entry_date.dt.strftime("%Y-%m-%d")).to_csv(tmp, index=False)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        v = run_battery(tmp, features=FEATS, controls=["atr_pct"], time_bucket_days=40)
    (OUT / f"e1_battery_fp_label_{label}_{UNIT}.txt").write_text(buf.getvalue())
    tmp.unlink()
    n_first_sym = d.groupby("symbol").head(1).shape[0]
    print(f"现电池(label=逐 match 首次穿越占比,controls=atr_pct):关3a 只用每股首条 n={n_first_sym}"
          f"({n_first_sym / len(d):.0%} 样本);关3b 见 e1_battery_fp_label_{label}.txt")
    rows = []
    for f in FEATS:
        vb = v[f]
        r = e1_regression(d, f, ["atr_pct"])
        rows.append(dict(feat=f, battery_verdict=vb["verdict"][:28], q1=vb["q_fdr"],
                         t_ctrl_battery=vb["t_ctrl"], p3a=vb["declust_p"], p3b=vb["declust_time_p"],
                         beta=r["beta"], t_sym=r["t_sym"], t_time=r["t_time"], t_two=r["t_two"],
                         p_wcb_time=r["p_wcb_time"], G_time=r["G_time"]))
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f"{x:+.3g}"))


# ───────────────────────── E2 / E3 ─────────────────────────

GATES = {"distinct_pk": [2, 3, 4, 5], "first_drought": [20, 40, 65, 80, 114],
         "vol_spike": [1, 3, 6, 8], "peak_age": [30, 60, 90, 120], "burst_count": [2, 3, 4]}


def e2_e3(d, b, tag, n_boot=500):
    cuts = np.quantile(b.atr_pct.dropna(), [1 / 3, 2 / 3])
    lay = lambda s: np.digitize(s, cuts)            # 0/1/2
    b = b.assign(L=lay(b.atr_pct))
    d = d[d.atr_pct.notna()].assign(L=lambda x: lay(x.atr_pct))
    rand_fpr = b.groupby("L").up.mean().reindex([0, 1, 2]).to_numpy()
    pool_fpr = (d.groupby("L").fp_up.sum() / d.groupby("L").den.sum()).reindex([0, 1, 2]).to_numpy()
    pool_share = (d.groupby("L").den.sum() / d.den.sum()).reindex([0, 1, 2]).to_numpy()
    print(f"\n######## E3 [{tag}] ATR 三分层(切点取随机日池):首次穿越率")
    print(f"  随机日 : {np.round(rand_fpr, 4)}   池内宽进 match : {np.round(pool_fpr, 4)}  "
          f"池内买点日占比 : {np.round(pool_share, 3)}")

    syms, sidx = np.unique(d.symbol, return_inverse=True)
    S = len(syms)
    W = RNG.multinomial(S, np.full(S, 1 / S), size=n_boot).astype(float)   # (B,S)

    def agg(mask):
        up = np.zeros((S, 3)); den = np.zeros((S, 3))
        np.add.at(up, (sidx[mask], d.L.to_numpy()[mask]), d.fp_up.to_numpy(float)[mask])
        np.add.at(den, (sidx[mask], d.L.to_numpy()[mask]), d.den.to_numpy(float)[mask])
        return up, den

    upA, denA = agg(np.ones(len(d), bool))

    def stats_of(upK, denK, UA, DA):
        # 输入可带前导 bootstrap 维:(...,3)
        fK = UK = upK; nK = denK
        fprK = UK.sum(-1) / nK.sum(-1)
        fprA = UA.sum(-1) / DA.sum(-1)
        piK = nK / nK.sum(-1, keepdims=True)
        piA = DA / DA.sum(-1, keepdims=True)
        with np.errstate(invalid="ignore", divide="ignore"):
            # 某层保留子集为空时 piK=0,该层贡献按 0 计(否则 0*NaN 污染整条)
            rateK = np.where(nK > 0, UK / np.maximum(nK, 1e-12), 0.0)
            rateA = np.where(DA > 0, UA / np.maximum(DA, 1e-12), 0.0)
            adj_pool = (piK * (rateK - rateA)).sum(-1)
        adj_base = (fprK - piK @ rand_fpr) - (fprA - piA @ rand_fpr)
        return fprK - fprA, adj_pool, adj_base

    UA_b = W @ upA; DA_b = W @ denA
    print(f"\n######## E2 [{tag}] 闸式判定:保留子集 − 不设闸(首次穿越率,点数)。"
          f"不设闸 n={len(d)} FPR={upA.sum() / denA.sum():.4f}")
    rows = []
    for f, ths in GATES.items():
        rs, ps = stats.spearmanr(d[f], d["p"])
        for t in ths:
            m = (d[f] >= t).to_numpy()
            if m.sum() < 30:
                continue
            upK, denK = agg(m)
            raw, ap, ab = stats_of(upK.sum(0), denK.sum(0), upA.sum(0), denA.sum(0))
            _, ap_b, ab_b = stats_of(W @ upK, W @ denK, UA_b, DA_b)
            lo, hi = np.nanpercentile(ap_b, [2.5, 97.5])
            rows.append(dict(feat=f, thr=t, n_keep=int(m.sum()), keep_share=denK.sum() / denA.sum(),
                             d_raw=raw * 100, d_adj_pool=ap * 100, ci_lo=lo * 100, ci_hi=hi * 100,
                             d_adj_base=ab * 100, rho_cont=rs, p_cont=ps))
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f"{x:+.3g}"))


def main():
    d24, d25 = load("w2024"), load("w2025")
    both = pd.concat([d24, d25], ignore_index=True)
    e1(d25, "w2025")
    e1(both, "w2024+w2025")
    for tag, dd in [("w2024", d24), ("w2025", d25)]:
        e2_e3(dd, load_base(tag), tag)
    print("\n时间桶数算术(58 日历天/桶):",
          {k: round(v / BUCKET_CAL, 1) for k, v in
           {"2022-09..2023-12": 486, "2024..2025": 731, "2021-08..2023-12(无首部缓冲)": 864}.items()})


if __name__ == "__main__":
    main()
