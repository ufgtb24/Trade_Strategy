# -*- coding: utf-8 -*-
"""e2：在 e1 同一份 2 档子设计(4096 格)上检验三件事——

  (i)   运行点局部筛选规则（运行点翻转效应 |z|≥1 且两年同号，按 |z| 取前 4）的幸存者集合稳不稳；
  (ii)  「筛选 + 联合」两次挑选共用同一份数据时，只 bootstrap 联合（幸存者固定）与 整体 bootstrap
        （每个副本重做筛选）给出的 optimism 差多少——量化筛选那一次挑选的真实代价；
  (iii) 功效线从「每折 ≥100 买点日」换成「每格分数 SE 上限」后，朴素分 / optimism / K_eff 怎么变，
        并检验噪声地板预测 = 中位格 SE × E[K_eff 个标准正态的最大值]。

只读长表需要列，逐片过滤，峰值 < 1.5GB。
"""
import itertools
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[5]
LT = ROOT / "outputs/tune_gates/bb_v1/main/longtable"
OUT = Path(__file__).resolve().parent
T0 = time.time()
D_COLS = ["bo.exceed_threshold", "bo.min_relative_height", "burst.gap_max", "tb.max_rise_k", "tb.max_span",
          "tb.stop_confirm_bars"]
D_LOHI = [(0.003, 0.0075), (0.2, 0.3), (8, 4), (1.5, 2.25), (20, 10), (1, 3)]
NAMES = ["exceed", "mrh", "gap", "rise", "span", "scb", "count", "dpk", "fd", "pa", "vs", "mdd"]
COLS = ["symbol"] + D_COLS + ["burst.count", "burst.distinct_pk", "burst.first_drought", "burst.peak_age_max",
                              "burst.max_bar_vol_ratio", "tb.max_day_drop", "buy_date", "fp_up", "fp_down",
                              "fp_both", "fp_none", "fold_6M"]
FOLD6 = ["2024H1", "2024H2", "2025H1", "2025H2"]
POWER, B, MMAX = 100, 200, 4

parts = []
for sp in sorted(LT.glob("part-*.parquet")):
    df = pq.read_table(sp, columns=COLS).to_pandas()
    keep = np.ones(len(df), bool)
    for c, (lo, hi) in zip(D_COLS, D_LOHI):
        v = df[c].to_numpy(dtype=float); keep &= np.isclose(v, lo) | np.isclose(v, hi)
    df = df[keep]
    dcode = np.zeros(len(df), np.int64)
    for j, (c, (lo, hi)) in enumerate(zip(D_COLS, D_LOHI)):
        dcode |= (np.isclose(df[c].to_numpy(dtype=float), hi).astype(np.int64) << j)
    passes = [df["burst.count"].to_numpy() >= 2, df["burst.distinct_pk"].to_numpy() >= 3,
              df["burst.first_drought"].to_numpy() >= 40, df["burst.peak_age_max"].to_numpy() >= 60,
              df["burst.max_bar_vol_ratio"].to_numpy() >= 3, df["tb.max_day_drop"].to_numpy(dtype=float) < 0.2]
    pm = np.zeros(len(df), np.int64)
    for b, p in enumerate(passes):
        pm |= (p.astype(np.int64) << b)
    parts.append(pd.DataFrame({"symbol": df["symbol"].astype(str).to_numpy(), "dcode": dcode, "pmask": pm,
                               "fp_up": df.fp_up.to_numpy(), "fp_down": df.fp_down.to_numpy(),
                               "fp_both": df.fp_both.to_numpy(), "fp_none": df.fp_none.to_numpy(),
                               "day": pd.to_datetime(df.buy_date).to_numpy().astype("datetime64[D]").astype(np.int64),
                               "f6": pd.Categorical(df.fold_6M.astype(str), categories=FOLD6).codes}))
    del df
R = pd.concat(parts, ignore_index=True); del parts
sym_code = pd.Categorical(R.symbol).codes.astype(np.int64); NS = sym_code.max() + 1
blk_code = ((R.day - R.day.min()) // 29).to_numpy(); NBK = blk_code.max() + 1
ST = R[["fp_up", "fp_down", "fp_both", "fp_none"]].to_numpy(np.float64)
base_idx = (R.dcode.to_numpy() * 64 + R.pmask.to_numpy()) * 4 + R.f6.to_numpy()


def cell_tensor(w=None):
    arr = np.zeros((64 * 64 * 4, 4))
    for s in range(4):
        arr[:, s] = np.bincount(base_idx, weights=ST[:, s] if w is None else ST[:, s] * w, minlength=64 * 64 * 4)
    t = arr.reshape((2,) * 12 + (4, 4)).transpose(list(range(5, -1, -1)) + list(range(11, 5, -1)) + [12, 13])
    for ax in range(6, 12):
        a0 = np.take(t, 0, axis=ax); a1 = np.take(t, 1, axis=ax)
        t = np.stack([a0 + a1, a1], axis=ax)
    return t


def fps(t):
    ty = np.stack([t[..., 0, :] + t[..., 1, :], t[..., 2, :] + t[..., 3, :]], axis=-2)
    ta = t.sum(-2)
    with np.errstate(invalid="ignore", divide="ignore"):
        fy = ty[..., 0] / (ty[..., 0] + ty[..., 1] + ty[..., 2])
        fa = ta[..., 0] / (ta[..., 0] + ta[..., 1] + ta[..., 2])
    return fy, fa, ty.sum(-1)


FPY, FPA, NY = fps(cell_tensor())
OK = (NY >= POWER).all(-1)
PROD = (0,) * 6 + (0, 1, 1, 1, 1, 1)
REF = (0,) * 12


def flip(c, *js):
    c = list(c)
    for j in js:
        c[j] = 1 - c[j]
    return tuple(c)


def oat_vec(fy, fa):
    return np.array([[fy[flip(PROD, j)][0] - fy[PROD][0], fy[flip(PROD, j)][1] - fy[PROD][1],
                      fa[flip(PROD, j)] - fa[PROD]] for j in range(12)])


rng = np.random.default_rng(7)
REP = {"股簇": [], "时间块": []}
for m in REP:
    for b in range(B):
        if m == "股簇":
            w = rng.multinomial(NS, np.full(NS, 1 / NS))[sym_code].astype(float)
        else:
            w = rng.multinomial(NBK, np.full(NBK, 1 / NBK))[blk_code].astype(float)
        fy, fa, _ = fps(cell_tensor(w))
        REP[m].append((fy, fa))
print(f"bootstrap 完成 {time.time()-T0:.0f}s")

O0 = oat_vec(FPY, FPA)
SE_OAT = np.max([np.std([oat_vec(*x)[:, 2] for x in REP[m]], axis=0, ddof=1) for m in REP], axis=0)


def screen(o):
    z = o[:, 2] / SE_OAT
    ok = (np.abs(z) >= 1) & (o[:, 0] * o[:, 1] > 0)
    idx = [j for j in np.argsort(-np.abs(z)) if ok[j]][:MMAX]
    return tuple(sorted(idx))


def joint(fy, surv):
    out = {}
    for bits in itertools.product([0, 1], repeat=len(surv)):
        c = flip(PROD, *[j for j, b in zip(surv, bits) if b])
        out[c] = np.nanmin(fy[c] - fy[PROD]) if OK[c] else np.nan
    return out


def best(d):
    ks = [k for k, v in d.items() if np.isfinite(v)]
    return max(ks, key=lambda k: d[k])


L = []
P = L.append
S0 = screen(O0)
P("## (i) 运行点局部筛选：幸存者与稳定性（规则 |z|≥1 且两年同号，按 |z| 取前 4；z 用股簇/时间块 SE 取大）")
P("原数据幸存者：" + "、".join(f"{NAMES[j]}(z={O0[j,2]/SE_OAT[j]:+.1f})" for j in S0))
survs = [screen(oat_vec(*x)) for x in REP["股簇"]]
pj = {NAMES[j]: np.mean([j in s for s in survs]) for j in range(12)}
P("各参数进幸存者的 bootstrap 频率(股簇)：" + "，".join(f"{k} {v:.2f}" for k, v in pj.items()))
P(f"幸存者集合与原数据完全相同的副本比例：{np.mean([s == S0 for s in survs]):.2f}；集合大小分布 "
  f"{dict(zip(*np.unique([len(s) for s in survs], return_counts=True)))}")

P("\n## (ii) 两次挑选的 optimism：幸存者固定 vs 每个副本重做筛选（股簇副本；联合 = 幸存者 2 档全组合，含不改）")
J0 = joint(FPY, S0); c0 = best(J0); naive = J0[c0]
s0 = lambda c: (np.nanmin(FPY[c] - FPY[PROD]) if OK[c] else np.nan)
chg = [NAMES[j] for j in range(12) if c0[j] != PROD[j]]
P(f"原数据联合选中：{chg or '不改'}，朴素分（两年 min Δ）= {naive*100:+.2f}pt")
for m in REP:
    of, ow = [], []
    for fy, fa in REP[m]:
        Jf = joint(fy, S0); cf = best(Jf); of.append(Jf[cf] - s0(cf))
        sb = screen(oat_vec(fy, fa)); Jw = joint(fy, sb); cw = best(Jw)
        if np.isfinite(s0(cw)):
            ow.append(Jw[cw] - s0(cw))
    of, ow = np.array(of) * 100, np.array(ow) * 100
    P(f"- {m}：幸存者固定 optimism {of.mean():+.2f}±{of.std(ddof=1)/np.sqrt(len(of)):.2f}pt → 校正 {naive*100-of.mean():+.2f}；"
      f"整体重做 optimism {ow.mean():+.2f}±{ow.std(ddof=1)/np.sqrt(len(ow)):.2f}pt → 校正 {naive*100-ow.mean():+.2f}（有效副本 {len(ow)}）")

P("\n## (iii) 功效线口径：按买点日计数 vs 按每格分数 SE（相对参照格=D 生产且闸全关，4096 格；副本 0-99 估 SE，100-199 估 optimism）")
sim = np.random.default_rng(1).standard_normal((4000, 4096))
Ks = np.array([1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096])
Es = np.array([np.mean(np.max(sim[:, :k], axis=1)) for k in Ks])
score = lambda fy: np.nanmin(fy - fy[REF], axis=-1)
S_orig = score(FPY)
reps = [score(x[0]) for x in REP["股簇"]]
SE_CELL = np.nanstd(np.array(reps[:100]), axis=0, ddof=1)
for name, adm in [("每折≥100 买点日(现行)", OK), ("SE≤3pt", OK & (SE_CELL <= 0.03)), ("SE≤2pt", OK & (SE_CELL <= 0.02)),
                  ("SE≤1.5pt", OK & (SE_CELL <= 0.015)), ("SE≤1pt", OK & (SE_CELL <= 0.01))]:
    n_adm = int(adm.sum())
    if n_adm < 2:
        P(f"- {name}：可评估 {n_adm} 格，跳过"); continue
    s = np.where(adm, S_orig, np.nan)
    opt, zmx = [], []
    for sb in reps[100:]:
        sbm = np.where(adm, sb, np.nan); cb = np.nanargmax(sbm)
        opt.append(sbm.ravel()[cb] - s.ravel()[cb])
        dev = (sbm - s)[adm] / SE_CELL[adm]
        zmx.append(np.nanmax(dev))
    em = np.mean(zmx); keff = float(np.interp(em, Es, Ks))
    medse = np.median(SE_CELL[adm]) * 100
    pred = medse * float(np.interp(keff, Ks, Es))
    top = np.nanargmax(s)
    P(f"- {name}：可评估 {n_adm} 格；朴素最高 {np.nanmax(s)*100:+.2f}pt（该格 SE {SE_CELL.ravel()[top]*100:.2f}）；"
      f"optimism {np.mean(opt)*100:+.2f}pt → 校正 {np.nanmax(s)*100-np.mean(opt)*100:+.2f}；K_eff≈{keff:.0f}；"
      f"中位 SE {medse:.2f}pt；地板预测(中位SE×E[max]) {pred:.2f}pt")
txt = "\n".join(L)
(OUT / "e2_output.md").write_text(txt, encoding="utf-8")
print(txt)
print(f"总耗时 {time.time()-T0:.0f}s")
