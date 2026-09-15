# -*- coding: utf-8 -*-
"""learner 方法实验 E4:「提高突破幅度阈值」的首次穿越增益来自哪批买点(只读长表,不扫描)。

数据:outputs/tune_gates/bb_v1/main/longtable(旧底座 2024-01-01..2026-01-01,HEAD_BUFFER=250)。
这份数据正是执行端当初定案 bo.exceed_threshold 0.003→0.0075 所用的数据,所以本实验是
「对既有定案的归因诊断」,不是验证,不产生新的选择。

做法:其余 5 个 D 维固定在参照格,exceed_threshold 取 θ0=0.003 与 θ1=0.0075 两档;
买点身份 = (symbol, tb.start, tb.end)(首次穿越四态只由 tb 买点窗决定,同身份 label 必相同)。
按 where 设置(宽进 / 定案前生产 / 定案后生产)把两档的买点集合拆成:
  C      两档都在且都过 where
  D_gone θ0 过 where、θ1 下这个买点根本没有 match(弱 bo 删掉后该回踩不再成立)
  D_wh   θ0 过 where、θ1 下 match 仍在但 where 不再通过(burst 组成变了)
  A_new  θ1 过 where、θ0 下根本没有 match(新长出来的买点)
  A_wh   θ1 过 where、θ0 下 match 在但当时 where 不过
自检:定案前生产 where 下 θ0/θ1 两格的计数与 FP 必须逐位复现 tune.cell 查同格的读数
(2024: 1865/0.5725 → 1748/0.5886;2025: 2312/0.5342 → 2111/0.5618;即 notes.md §11 定案表 C 行 ×0.92 / +1.60 / +2.76)。
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

ROOT = Path(__file__).resolve().parents[5]
LT = ROOT / "outputs/tune_gates/bb_v1/main/longtable"
REF = {"bo.min_relative_height": 0.2, "burst.gap_max": 8, "tb.max_rise_k": 1.5,
       "tb.max_span": 20, "tb.stop_confirm_bars": 1}
TH0, TH1 = 0.003, 0.0075
WCOLS = ["burst.count", "burst.distinct_pk", "burst.first_drought", "burst.peak_age_max",
         "burst.max_bar_vol_ratio", "tb.max_day_drop"]
KEY = ["symbol", "tb.start", "tb.end"]
FP = ["fp_up", "fp_down", "fp_both", "fp_none"]


def where_mask(df, setting):
    if setting == "wide":
        return pd.Series(True, index=df.index)
    m = ((df["burst.count"] >= 1) & (df["burst.distinct_pk"] >= 3) & (df["burst.first_drought"] >= 40)
         & (df["burst.max_bar_vol_ratio"] >= 3) & (df["tb.max_day_drop"] < 0.2))
    if setting == "prod_old":
        m &= df["burst.peak_age_max"] >= 60
    return m


def fpr(df):
    den = df.fp_up.sum() + df.fp_down.sum() + df.fp_both.sum()
    return (df.fp_up.sum() / den if den else np.nan), int(df[FP].to_numpy().sum())


def main():
    dset = ds.dataset(sorted(str(p) for p in LT.glob("part-*.parquet")), format="parquet")
    flt = ds.field("bo.exceed_threshold").isin([TH0, TH1])
    for k, v in REF.items():
        flt &= ds.field(k) == v
    cols = ["symbol", "bo.exceed_threshold"] + WCOLS + ["tb.start", "tb.end"] + FP + ["fold_Y"]
    t = dset.to_table(columns=cols, filter=flt).to_pandas()
    t["symbol"] = t["symbol"].astype(str)
    t["fold_Y"] = t["fold_Y"].astype(str)
    print(f"读入行 {len(t)}(θ0 {int((t['bo.exceed_threshold'] == TH0).sum())} / "
          f"θ1 {int((t['bo.exceed_threshold'] == TH1).sum())})")
    a0 = t[t["bo.exceed_threshold"] == TH0].copy()
    a1 = t[t["bo.exceed_threshold"] == TH1].copy()
    for a, nm in [(a0, "θ0"), (a1, "θ1")]:
        dup = a.duplicated(KEY).sum()
        print(f"{nm} 同一回踩段身份的额外行 {dup}(同段被不同 burst 前缀各配一次、各带四态计数;"
              f"本脚本沿用执行端行口径以复现 tune.cell,段口径对照见 e4c_span_multiplicity.py)")

    for a in (a0, a1):
        a["k"] = a["symbol"] + "_" + a["tb.start"].astype(str) + "_" + a["tb.end"].astype(str)
    for setting in ["prod_old", "prod_new", "wide"]:
        print(f"\n======== where 设置 = {setting} ========")
        for year in ["2024", "2025"]:
            x0 = a0[a0.fold_Y == year]; x1 = a1[a1.fold_Y == year]
            # 计数一律只累加「过 where 的行」(同一买点身份可能有多行、各自带四态,不能按身份整组累加)
            r0 = x0[where_mask(x0, setting)]; r1 = x1[where_mask(x1, setting)]
            S0, S1 = set(r0.k), set(r1.k)
            all0, all1 = set(x0.k), set(x1.k)
            groups = {
                "S0(θ0 全部)": (r0, S0), "S1(θ1 全部)": (r1, S1),
                "C(θ0 侧计数)": (r0, S0 & S1),
                "D_gone": (r0, {k for k in S0 - S1 if k not in all1}),
                "D_wh": (r0, {k for k in S0 - S1 if k in all1}),
                "A_new": (r1, {k for k in S1 - S0 if k not in all0}),
                "A_wh": (r1, {k for k in S1 - S0 if k in all0}),
            }
            f0, c0 = fpr(r0); f1, c1 = fpr(r1)
            print(f"[{year}] 四态计数 θ0 {c0} → θ1 {c1}(×{c1 / c0:.3f});FP {f0:.4f} → {f1:.4f}"
                  f"(Δ {100 * (f1 - f0):+.2f} 点)")
            rows = []
            for g, (src, keys) in groups.items():
                sub = src[src.k.isin(keys)]
                f, c = fpr(sub) if len(sub) else (np.nan, 0)
                rows.append(dict(group=g, n_buypoint=len(keys), count=c, FP=f))
            print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:.4f}"))

if __name__ == "__main__":
    main()
