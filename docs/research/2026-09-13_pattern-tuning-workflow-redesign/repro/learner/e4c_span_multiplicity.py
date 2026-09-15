# -*- coding: utf-8 -*-
"""E4c:长表里「同一回踩段被多个 burst 前缀各配一次」的重复计数有多大、会不会改变读数(只读长表)。

发现:同一组合内,同一 (symbol, tb.start, tb.end) 可以有多行,burst 终点各不相同(all_ends 前缀族各自锚到
不同的 bo,回踩段却是同一段),且多数行各自带非零四态计数——同一批买点日的 label 被计了 2~7 次。
这里比较两种口径:
  行口径   = 执行端现行(tune.cell 同款):过 where 的每行各计一次
  段口径   = 过 where 的行里,每个回踩段身份只计一次(四态取该段任一非零行,同段 label 必相同)
报告:参照格与生产格两档阈值的计数、首次穿越率、ΔFP,以及段口径下 E4 的总变化。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import e4_exceed_decomposition as E  # noqa: E402


def rate(df):
    den = df.fp_up.sum() + df.fp_down.sum() + df.fp_both.sum()
    return df.fp_up.sum() / den, int(df[E.FP].to_numpy().sum()), int(den)


def main():
    dset = ds.dataset(sorted(str(p) for p in E.LT.glob("part-*.parquet")), format="parquet")
    flt = ds.field("bo.exceed_threshold").isin([E.TH0, E.TH1])
    for k, v in E.REF.items():
        flt &= ds.field(k) == v
    cols = ["symbol", "bo.exceed_threshold", "burst.end"] + E.WCOLS + ["tb.start", "tb.end"] + E.FP + ["fold_Y"]
    t = dset.to_table(columns=cols, filter=flt).to_pandas()
    t["symbol"] = t.symbol.astype(str); t["fold_Y"] = t.fold_Y.astype(str)
    t["k"] = t.symbol + "_" + t["tb.start"].astype(str) + "_" + t["tb.end"].astype(str)
    t["nz"] = t[E.FP].sum(1) > 0
    rows = []
    for setting in ["wide", "prod_old", "prod_new"]:
        for year in ["2024", "2025"]:
            for th in [E.TH0, E.TH1]:
                a = t[(t.fold_Y == year) & (t["bo.exceed_threshold"] == th)]
                r = a[E.where_mask(a, setting)]
                f_row, c_row, d_row = rate(r)
                seg = r[r.nz].drop_duplicates("k")
                f_seg, c_seg, d_seg = rate(seg)
                # 同段不同行的四态是否确实相同(label 只由段决定)
                chk = r[r.nz].groupby("k")[E.FP].nunique().max().max()
                rows.append(dict(where=setting, year=year, thr=th, rows=len(r), segments=r.k.nunique(),
                                 count_row=c_row, fp_row=round(f_row, 4), count_seg=c_seg, fp_seg=round(f_seg, 4),
                                 inflate=round(c_row / max(c_seg, 1), 3), same_label_within_seg=int(chk) == 1))
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print("\nΔFP(0.0075 − 0.003),点:")
    for (w, y), g in df.groupby(["where", "year"], sort=False):
        g = g.set_index("thr")
        print(f"  {w:8s} {y}: 行口径 {100*(g.fp_row[E.TH1]-g.fp_row[E.TH0]):+.2f}  段口径 {100*(g.fp_seg[E.TH1]-g.fp_seg[E.TH0]):+.2f}"
              f"  | 计数倍数 行 {g.count_row[E.TH1]/g.count_row[E.TH0]:.3f} 段 {g.count_seg[E.TH1]/g.count_seg[E.TH0]:.3f}")


if __name__ == "__main__":
    main()
