# -*- coding: utf-8 -*-
"""e5：回应 stats B1——「误差功效线 ≤1pt → 64 格、校正后 +2.60」是否只是 2 档 + 无邻域平滑 + 行口径的产物。

在 e2 同一 2 档子设计上，只取「闸全关」的 64 个检测参数组合（D 6 维 × 2 档），分别用
  行口径（现行）与 回踩段口径（同一组合内 (symbol, tb.start, tb.end, 半年折) 只计一次）
算：最高格是哪一格、朴素分、按股 bootstrap optimism、多种子对半分（一半选格、另一半评分），
以及在 6 维 2 档超立方体上做 r=1 邻域取最小后的同样三个读数。
分数 = 两年里较差那年相对参照格（D 全生产值）的首次穿越率增量；功效线每年 ≥100 买点 bar。
"""
import time
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[5]
LT = ROOT / "outputs/tune_gates/bb_v1/main/longtable"
OUT = Path(__file__).resolve().parent
D_COLS = ["bo.exceed_threshold", "bo.min_relative_height", "burst.gap_max", "tb.max_rise_k", "tb.max_span", "tb.stop_confirm_bars"]
D_NAMES = ["exceed 0.003→0.0075", "mrh 0.2→0.3", "gap 8→4", "rise 1.5→2.25", "span 20→10", "scb 1→3"]
D_LOHI = [(0.003, 0.0075), (0.2, 0.3), (8, 4), (1.5, 2.25), (20, 10), (1, 3)]
COLS = ["symbol"] + D_COLS + ["tb.start", "tb.end", "fp_up", "fp_down", "fp_both", "fp_none", "fold_6M"]
FOLD6 = ["2024H1", "2024H2", "2025H1", "2025H2"]
T0 = time.time()
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
    parts.append(pd.DataFrame({"symbol": df.symbol.astype(str).to_numpy(), "dcode": dcode,
                               "ts": df["tb.start"].to_numpy(), "te": df["tb.end"].to_numpy(),
                               "u": df.fp_up.to_numpy(), "d": df.fp_down.to_numpy(), "b": df.fp_both.to_numpy(), "n": df.fp_none.to_numpy(),
                               "f6": pd.Categorical(df.fold_6M.astype(str), categories=FOLD6).codes}))
R = pd.concat(parts, ignore_index=True)
SEG = R.drop_duplicates(["dcode", "symbol", "ts", "te", "f6"])
print(f"行 {len(R)}，去重后段 {len(SEG)}（倍数 {len(R)/len(SEG):.3f}），{time.time()-T0:.0f}s")

NB = [[c ^ (1 << j) for j in range(6)] for c in range(64)]


def run(df, label, B=200, seeds=20):
    sym = pd.Categorical(df.symbol); sc = sym.codes.astype(np.int64); NS = len(sym.categories)
    yr = (df.f6.to_numpy() >= 2).astype(np.int64)
    idx = df.dcode.to_numpy() * 2 + yr
    ST = df[["u", "d", "b", "n"]].to_numpy(float)

    def cells(w=None):
        a = np.stack([np.bincount(idx, weights=ST[:, k] if w is None else ST[:, k] * w, minlength=128) for k in range(4)], 1).reshape(64, 2, 4)
        with np.errstate(invalid="ignore", divide="ignore"):
            fp = a[..., 0] / a[..., :3].sum(-1)
        return fp, a.sum(-1)

    def scores(fp, cnt):
        ok = (cnt >= 100).all(1)
        s = np.where(ok, np.min(fp - fp[0], axis=1), np.nan)
        snb = np.array([np.nan if not ok[c] else np.nanmin([s[c]] + [s[k] for k in NB[c] if ok[k]]) for c in range(64)])
        return s, snb

    fp0, cnt0 = cells(); s0, nb0 = scores(fp0, cnt0)
    rng = np.random.default_rng(3)
    reps = []
    for _ in range(B):
        w = rng.multinomial(NS, np.full(NS, 1 / NS))[sc].astype(float)
        reps.append(scores(*cells(w)))
    out = []
    for kind, base, ri in [("无邻域", s0, 0), ("邻域取最小", nb0, 1)]:
        c = int(np.nanargmax(base))
        opt = []
        for r in reps:
            cb = int(np.nanargmax(r[ri])); opt.append(r[ri][cb] - base[cb])
        sh = []
        for sd in range(seeds):
            half = np.random.default_rng(100 + sd).random(NS) < 0.5
            v = []
            for m in (half, ~half):
                a = scores(*cells(m[sc].astype(float)))[ri]; b = scores(*cells((~m)[sc].astype(float)))[ri]
                ca = int(np.nanargmax(a))
                if np.isfinite(b[ca]):
                    v.append(b[ca])
            if v:
                sh.append(np.mean(v))
        moved = [D_NAMES[j] for j in range(6) if c >> j & 1] or ["不改"]
        o = np.array(opt) * 100; shv = np.array(sh) * 100
        out.append(f"- {label}·{kind}：最高格 = {'+'.join(moved)}；朴素 {base[c]*100:+.2f}pt；optimism {o.mean():+.2f}±{o.std(ddof=1)/np.sqrt(len(o)):.2f} → 校正 {base[c]*100-o.mean():+.2f}；"
                   f"对半分 {shv.mean():+.2f}±{shv.std(ddof=1)/np.sqrt(len(shv)):.2f}（{len(shv)} 种子）；该格两年买点 {cnt0[c].astype(int).tolist()}")
    return out


L = ["## e5. B1 复核：闸全关 × 检测参数 2 档 64 格"]
L += run(R, "行口径")
L += run(SEG, "段口径")
txt = "\n".join(L)
(OUT / "e5_output.md").write_text(txt, encoding="utf-8")
print(txt); print(f"{time.time()-T0:.0f}s")
