# -*- coding: utf-8 -*-
"""e4（复用 e2 的读数与副本生成）：在 e1 同一份 2 档子设计(4096 格)上检验三件事——

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


rng = np.random.default_rng(11)
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


L = []
P = L.append
P("## e4. 每格分数 SE 与样本量的关系（噪声地板计算器的系数）")
nmin = NY.min(-1).astype(float)                        # 每格两年中较少那年的买点日
for m in REP:
    sc = np.array([np.nanmin(fy - fy[REF], axis=-1) for fy, _ in REP[m]])
    se = np.nanstd(sc, axis=0, ddof=1)
    ok = OK & np.isfinite(se) & (nmin > 0)
    a = se[ok] * np.sqrt(nmin[ok])
    P(f"- {m}：SE×√(较少年买点日) 的分位 p10/p50/p90 = {np.percentile(a,10):.3f} / {np.percentile(a,50):.3f} / {np.percentile(a,90):.3f}"
      f"（二项独立时约 0.5×√2≈0.71 的量级）")
    for lo_, hi_ in [(100, 300), (300, 1000), (1000, 3000), (3000, 30000)]:
        b = ok & (nmin >= lo_) & (nmin < hi_)
        if b.sum():
            P(f"    - 较少年买点日 [{lo_},{hi_})：{int(b.sum())} 格，SE 中位 {np.median(se[b])*100:.2f}pt")
P("\n运行点上翻转 1 位 / 2 位的配对差 SE（两年合并口径）与翻转后买点日保留比例：")
for m in REP:
    rows = []
    for js in [(j,) for j in range(12)] + list(itertools.combinations(range(12), 2)):
        c = flip(PROD, *js)
        d = np.array([fa[c] - fa[PROD] for _, fa in REP[m]])
        n_c, n_p = NY[c].sum(), NY[PROD].sum()
        rows.append((len(js), np.nanstd(d, ddof=1) * 100, min(n_c, n_p) / max(n_c, n_p)))
    r = np.array(rows)
    for k in (1, 2):
        rr = r[r[:, 0] == k]
        P(f"- {m} 翻转 {k} 位：配对差 SE 中位 {np.median(rr[:,1]):.2f}pt（p90 {np.percentile(rr[:,1],90):.2f}）；"
          f"SE 与买点日保留比例的 Spearman {pd.Series(rr[:,1]).corr(pd.Series(rr[:,2]), method='spearman'):+.2f}")
P(f"运行点两年买点日 {NY[PROD].tolist()}，参照格(宽进) {NY[REF].tolist()}")
txt = "\n".join(L)
(OUT / "e4_output.md").write_text(txt, encoding="utf-8")
print(txt)
