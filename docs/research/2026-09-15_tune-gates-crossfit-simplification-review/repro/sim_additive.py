"""red-team S3 / S5 / S6 / S7 的合成对照：12 维单翻转相加结构。

格 = 被翻转维的子集（共 4096 格），格估计 = 各维翻转差之和，所以格与格天然相关、有效独立方向只有 12 个。
标定：单翻转按股 SE 两年合并 1.25 点（单年 1.77、半年 2.5、往前那段 15 个月 1.58）；配对差年交互 τ ∈ {0, 0.9, 1.8}；
δ = 2 点；前向确认窗 SE 3.3 点·√(翻转维数)，门槛 = 估计 > 0 且 估计 − 1.645·SE ≥ −δ。
部署年的年交互独立新抽。所有「增益」相对工作点（空子集）。

用法：uv run python sim_additive.py [--reps 4000]
"""
import argparse
import itertools
import os
from multiprocessing import Pool

import numpy as np
from scipy.stats import norm

D = 12
SE_Y = 1.77
SE_H = SE_Y * np.sqrt(2)
SE_P = SE_Y * np.sqrt(12 / 15)
SE_FWD = 3.3
DELTA = 2.0
SUB = np.array(list(itertools.product([0, 1], repeat=D)), float)   # 第 0 行 = 空子集 = 工作点
SIZE = SUB.sum(1)


def mu_of(scen, rng):
    if scen == "null":
        return np.zeros(D)
    if scen == "one+3":
        m = np.zeros(D); m[0] = 3.0
        return m
    if scen == "two+3":
        m = np.zeros(D); m[:2] = 3.0
        return m
    if scen == "nearopt":
        return -np.abs(rng.normal(0, 1.0, D))
    raise ValueError(scen)


def fwd_gate(rng, sel, truth_fwd, se1=SE_FWD):
    """前向确认窗：对选中配置出一个估计，按非劣效 + 同号判定是否写入。"""
    k = sel.sum()
    if k == 0:
        return False
    se = se1 * np.sqrt(k)
    est = (truth_fwd * sel).sum() + rng.normal(0, se)
    return est > 0 and est - 1.645 * se >= -DELTA


# ---------------------------------------------------------------- S3 剪枝放在循环外
def s3(args):
    tau, scen, reps, seed = args
    rng = np.random.default_rng(seed)
    acc = {m: [] for m in ("A_全数据剪枝", "B_折内剪枝", "C_不剪枝")}
    for _ in range(reps):
        mu = mu_of(scen, rng)
        g = rng.normal(0, tau, (3, D))
        x = mu + g[:2] + rng.normal(0, SE_Y, (2, D))
        pooled = x.mean(0)
        z = pooled / (SE_Y / np.sqrt(2))
        tF = mu + g[2]
        for mode in acc:
            keep_full = np.ones(D, bool) if mode.startswith("C") else np.abs(z) >= 2
            cv = []
            for t in range(2):
                tr = 1 - t
                kp = (np.abs(x[tr] / SE_Y) >= 2) if mode.startswith("B") else keep_full
                cv.append((x[t] * (kp & (x[tr] > 0))).sum())
            cv = float(np.mean(cv))
            final = keep_full & (pooled > 0)
            GF = float((tF * final).sum())
            sw = bool(final.any() and cv > 0)
            acc[mode].append((cv, GF, sw, GF if sw else 0.0, keep_full.sum()))
    out = []
    for mode, v in acc.items():
        a = np.array(v)
        out.append(dict(S="S3", tau=tau, scen=scen, mode=mode, cv_bias=(a[:, 0] - a[:, 1]).mean(),
                        cv_mean=a[:, 0].mean(), P_switch=a[:, 2].mean(), G_gate=a[:, 3].mean(),
                        G_nogate=a[:, 1].mean(), dims_kept=a[:, 4].mean()))
    return out


# ---------------------------------------------------------------- S6 半年块 vs 整年块
def worst_rule(Xb):
    """Xb: (块数, D) → 在 4096 个子集里取「各块和的最小值」最大的子集。"""
    s = SUB @ Xb.T
    return SUB[int(np.argmax(s.min(1)))].astype(bool)


def s6(args):
    tau, r, scen, reps, seed = args
    rng = np.random.default_rng(seed)
    p = 40 / 126
    acc = {}
    for _ in range(reps):
        mu = mu_of(scen, rng)
        th = tau / np.sqrt(r + (1 - r) / 2) if tau > 0 else 0.0
        gy = rng.normal(0, 1, (3, D)); gh = rng.normal(0, 1, (6, D))
        gam = th * (np.sqrt(r) * gy[[0, 0, 1, 1, 2, 2]] + np.sqrt(1 - r) * gh)
        keep = mu + gam[:4] + rng.normal(0, SE_H / np.sqrt(1 - p), (4, D))
        purge = mu + gam[:4] + rng.normal(0, SE_H / np.sqrt(p), (4, D))
        xh = (1 - p) * keep + p * purge
        xy = np.stack([xh[:2].mean(0), xh[2:].mean(0)])
        tF = mu + gam[4:].mean(0)
        tS = mu
        for split in ("i_整年2折", "ii_半年4折_purge"):
            for rule in ("pooled", "worst"):
                if split.startswith("i_"):
                    blocks_tr = [[xy[1]], [xy[0]]]; w_tr = [[1.0], [1.0]]; ho = [xy[0], xy[1]]
                    full_blocks, full_w = [xy[0], xy[1]], [1.0, 1.0]
                else:
                    blocks_tr, w_tr, ho = [], [], []
                    for hh in range(4):
                        bl, ww = [], []
                        for b in range(4):
                            if b == hh:
                                continue
                            adj = abs(b - hh) == 1
                            bl.append(keep[b] if adj else xh[b]); ww.append(1 - p if adj else 1.0)
                        blocks_tr.append(bl); w_tr.append(ww); ho.append(xh[hh])
                    full_blocks, full_w = list(xh), [1.0] * 4

                def pick(bl, ww):
                    bl = np.array(bl); ww = np.array(ww)
                    if rule == "pooled" or len(bl) == 1:
                        return (ww[:, None] * bl).sum(0) / ww.sum() > 0
                    return worst_rule(bl)

                g = [float((ho[i] * pick(blocks_tr[i], w_tr[i])).sum()) for i in range(len(ho))]
                cv = float(np.mean(g))
                final = pick(full_blocks, full_w)
                GF = float((tF * final).sum()); GS = float((tS * final).sum())
                sw = bool(final.any() and cv > 0)
                acc.setdefault((split, rule), []).append((cv, GF, GS, GF if sw else 0.0, GS if sw else 0.0, sw))
    out = []
    for (split, rule), v in acc.items():
        a = np.array(v)
        e = a[:, 0] - a[:, 1]
        out.append(dict(S="S6", tau=tau, r=r, scen=scen, split=split, rule=rule, cv_bias=e.mean(), cv_sd=e.std(),
                        G_F=a[:, 1].mean(), G_S=a[:, 2].mean(), G_F_gate=a[:, 3].mean(), G_S_gate=a[:, 4].mean(),
                        P_switch=a[:, 5].mean()))
    return out


# ---------------------------------------------------------------- S5 往前那段并入（幸存者偏差）
def s5(args):
    tau, scen, reps, seed = args
    rng = np.random.default_rng(seed)
    pi, H = 0.3, -4.0
    relax = np.arange(D) < 6
    acc = {}
    for _ in range(reps):
        mu = mu_of(scen, rng) if scen != "one+3" else np.r_[np.zeros(6), 3.0, np.zeros(5)]

        def seg(m):
            return mu + relax * H * (pi - m) / (1 - m)

        g = rng.normal(0, tau, (5, D))                 # P, Y1, Y2, FWD, F
        xP = seg(pi) + g[0] + rng.normal(0, SE_P, D)
        gh = g[[1, 1, 2, 2]] / np.sqrt(0.5 + 0.25) * np.sqrt(0.5) + rng.normal(0, tau / np.sqrt(0.75) * np.sqrt(0.5), (4, D))
        xh = seg(pi / 3) + gh + rng.normal(0, SE_H, (4, D))
        xY = np.stack([xh[:2].mean(0), xh[2:].mean(0)])
        t_fwd = seg(pi / 10) + g[3]
        tF = seg(0.0) + g[4]

        def run(blocks, ses, confirm_P):
            blocks = np.array(blocks); w = 1 / np.array(ses) ** 2
            cv = []
            for i in range(len(blocks)):
                o = [j for j in range(len(blocks)) if j != i]
                sel = (w[o, None] * blocks[o]).sum(0) / w[o].sum() > 0
                cv.append((blocks[i] * sel).sum())
            final = (w[:, None] * blocks).sum(0) / w.sum() > 0
            ok = final.any() and np.mean(cv) > 0
            if ok and confirm_P:
                k = final.sum(); se = SE_P * np.sqrt(k); est = (xP * final).sum()
                ok = est > 0 and est - 1.645 * se >= -DELTA
            ok = ok and fwd_gate(rng, final, t_fwd)
            relax_share = (final & relax).sum() / max(final.sum(), 1)
            return float((tF * final).sum()) if ok else 0.0, bool(ok), relax_share, float((tF * final).sum())

        acc.setdefault("a_三块整块留出(往前段参与挑选)", []).append(run([xP, xY[0], xY[1]], [SE_P, SE_Y, SE_Y], False))
        acc.setdefault("b_两年+往前段当确认", []).append(run([xY[0], xY[1]], [SE_Y, SE_Y], True))
        acc.setdefault("b0_两年、不用往前段", []).append(run([xY[0], xY[1]], [SE_Y, SE_Y], False))
        acc.setdefault("c_四个半年块+往前段当确认", []).append(run(list(xh), [SE_H] * 4, True))
    out = []
    for k, v in acc.items():
        a = np.array(v)
        out.append(dict(S="S5", tau=tau, scen=scen, mode=k, G_F_written=a[:, 0].mean(), P_write=a[:, 1].mean(),
                        relax_share_selected=a[:, 2].mean(), G_F_selected_nogate=a[:, 3].mean()))
    return out


# ---------------------------------------------------------------- S7 经验贝叶斯前提检验（相加相关网格）
def spike_slab_post(db, v):
    """尖峰加平板先验 d ~ (1−w)·δ0 + w·N(0, s²)，(w, s) 按边际似然（格间当独立）在网格上取；返回后验均值。"""
    l0 = norm.logpdf(db, 0, np.sqrt(v))
    best = None
    for s in (0.5, 1.0, 2.0, 3.0, 4.0, 6.0):
        l1 = norm.logpdf(db, 0, np.sqrt(v + s * s))
        for w in (0.001, 0.005, 0.02, 0.05, 0.2, 0.5, 1.0):
            ll = float((np.logaddexp(np.log1p(-w) + l0, np.log(w) + l1) if w < 1 else l1).sum())
            if best is None or ll > best[0]:
                best = (ll, s, w, l1)
    _, s, w, l1 = best
    p = np.ones_like(db) if w >= 1 else 1 / (1 + np.exp(np.log1p(-w) + l0 - np.log(w) - l1))
    return p * s * s / (s * s + v) * db


def s7(args):
    tau, scen, reps, seed = args
    rng = np.random.default_rng(seed)
    acc = {}
    s2 = SIZE[1:] * SE_Y ** 2
    bits = 2 ** np.arange(D)[::-1]
    for _ in range(reps):
        mu = mu_of(scen, rng)
        g = rng.normal(0, tau, (4, D))                     # Y1, Y2, 前向窗, 部署年
        x = mu + g[:2] + rng.normal(0, SE_Y, (2, D))
        d = SUB[1:] @ x.T                                  # (4095, 2)
        tF = SUB @ (mu + g[3]); tS = SUB @ mu; tW = mu + g[2]
        d1, d2 = d[:, 0], d[:, 1]
        db = (d1 + d2) / 2
        sM = max(0.0, float(np.cov(d1, d2)[0, 1]))
        sE = max(0.0, (float(np.var(d1 - d2, ddof=1)) - float(np.mean(2 * s2))) / 2)
        v = sE / 2 + s2 / 2
        rho = sM / (sM + v) if sM > 0 else np.zeros_like(v)
        sel = x.mean(0) > 0
        c_arg = int(sel @ bits)
        cv = float(np.mean([(x[t] * (x[1 - t] > 0)).sum() for t in range(2)]))
        cands = {}
        for center in ("格均值", "0"):
            c0 = db.mean() if center == "格均值" else 0.0
            dt = c0 + rho * (db - c0)
            k = int(np.argmax(dt))
            cands[f"ρ收缩(中心={center})"] = (k + 1, float(dt[k]))
        ss = spike_slab_post(db, v)
        k = int(np.argmax(ss)); cands["尖峰加平板"] = (k + 1, float(ss[k]))

        def rec(name, cell, rep):
            sw = cell != 0
            acc.setdefault(name, []).append((tF[cell], tS[cell], sw, sw and tS[cell] < 0,
                                             rep - tF[cell] if (sw and np.isfinite(rep)) else np.nan))

        c_gate = c_arg if (sel.any() and cv > 0) else 0
        rec("argmax 不设门", c_arg, np.nan)
        rec("argmax+整年留出>0才换", c_gate, cv)
        for nmk, (cell, val) in cands.items():
            rec(f"{nmk} >δ才换", cell if val > DELTA else 0, val)
        rsk, rsv = cands["ρ收缩(中心=0)"]
        ssk, ssv = cands["尖峰加平板"]
        rec("ρ收缩(中心=0)排序+整年留出>0才换", rsk if cv > 0 else 0, rsv)
        rec("尖峰加平板排序+整年留出>0才换", ssk if cv > 0 else 0, ssv)
        for nmk, cell in (("argmax+整年留出>0才换", c_gate), ("ρ收缩(中心=0) >δ才换", rsk if rsv > DELTA else 0),
                          ("尖峰加平板 >δ才换", ssk if ssv > DELTA else 0),
                          ("尖峰加平板排序+整年留出>0才换", ssk if cv > 0 else 0)):
            ok = cell != 0 and fwd_gate(rng, SUB[cell].astype(bool), tW, se1=2.7)
            rec(nmk + " +前向窗(SE2.7)", cell if ok else 0, np.nan)
    out = []
    for k, v in acc.items():
        a = np.array(v, float)
        out.append(dict(S="S7", tau=tau, scen=scen, rule=k, G_F=a[:, 0].mean(), G_S=a[:, 1].mean(),
                        P_switch=a[:, 2].mean(), P_switch_to_worse=a[:, 3].mean(),
                        report_bias_when_switch=np.nanmean(a[:, 4]) if np.isfinite(a[:, 4]).any() else np.nan))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=4000)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--only", default="", help="如 S7：只跑该项，结果写 additive_<项>.csv")
    a = ap.parse_args()
    import pandas as pd
    jobs = []
    seed = 0
    for tau in (0.0, 0.9, 1.8):
        for scen in ("null", "one+3"):
            jobs.append((s3, (tau, scen, a.reps, seed := seed + 1)))
        for scen in ("null", "one+3", "two+3", "nearopt"):
            jobs.append((s7, (tau, scen, a.reps, seed := seed + 1)))
        for scen in ("null", "one+3", "nearopt"):
            for r in (0.0, 0.5, 1.0):
                jobs.append((s6, (tau, r, scen, a.reps // 4, seed := seed + 1)))
    for tau in (0.0, 0.9):
        for scen in ("null", "one+3"):
            jobs.append((s5, (tau, scen, a.reps, seed := seed + 1)))
    if a.only:
        jobs = [j for j in jobs if j[0].__name__ == a.only.lower()]
    with Pool(a.workers) as pool:
        res = pool.starmap(_call, jobs)
    rows = [r for rr in res for r in rr]
    df = pd.DataFrame(rows)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out, exist_ok=True)
    df.to_csv(os.path.join(out, f"additive{'_' + a.only if a.only else ''}.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500); pd.set_option("display.max_columns", 30)
    for s in ((a.only,) if a.only else ("S3", "S5", "S6", "S7")):
        print(f"\n## {s}\n")
        print(df[df.S == s].dropna(axis=1, how="all").round(3).to_markdown(index=False))


def _call(fn, args):
    return fn(args)


if __name__ == "__main__":
    main()
