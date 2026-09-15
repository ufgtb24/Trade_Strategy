# -*- coding: utf-8 -*-
"""E4d:段口径下 E4 各组的计数(stats 审查第 10 条:小组报计数不报比例)。
每组报:回踩段数、up 计数、定向计数(up+down+both)。口径与 e4_exceed_decomposition.py 相同,
只把「过 where 的行」按回踩段身份去重(同段四态相同,取任一非零行)。"""
import sys
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import e4_exceed_decomposition as E  # noqa: E402

dset = ds.dataset(sorted(str(p) for p in E.LT.glob("part-*.parquet")), format="parquet")
flt = ds.field("bo.exceed_threshold").isin([E.TH0, E.TH1])
for k, v in E.REF.items():
    flt &= ds.field(k) == v
cols = ["symbol", "bo.exceed_threshold"] + E.WCOLS + ["tb.start", "tb.end"] + E.FP + ["fold_Y"]
t = dset.to_table(columns=cols, filter=flt).to_pandas()
t["symbol"] = t.symbol.astype(str); t["fold_Y"] = t.fold_Y.astype(str)
t["k"] = t.symbol + "_" + t["tb.start"].astype(str) + "_" + t["tb.end"].astype(str)
rows = []
for setting in ["prod_old", "prod_new", "wide"]:
    for year in ["2024", "2025"]:
        x = t[t.fold_Y == year]
        x0 = x[x["bo.exceed_threshold"] == E.TH0]; x1 = x[x["bo.exceed_threshold"] == E.TH1]
        r0 = x0[E.where_mask(x0, setting)]; r1 = x1[E.where_mask(x1, setting)]
        seg0 = r0[r0[E.FP].sum(1) > 0].drop_duplicates("k"); seg1 = r1[r1[E.FP].sum(1) > 0].drop_duplicates("k")
        S0, S1, all0, all1 = set(r0.k), set(r1.k), set(x0.k), set(x1.k)
        groups = {"C": (seg0, S0 & S1), "D_gone": (seg0, {k for k in S0 - S1 if k not in all1}),
                  "D_wh": (seg0, {k for k in S0 - S1 if k in all1}),
                  "A_new": (seg1, {k for k in S1 - S0 if k not in all0}),
                  "A_wh": (seg1, {k for k in S1 - S0 if k in all0})}
        for g, (src, keys) in groups.items():
            sub = src[src.k.isin(keys)]
            rows.append(dict(where=setting, year=year, group=g, segments=len(keys),
                             up=int(sub.fp_up.sum()), directed=int((sub.fp_up + sub.fp_down + sub.fp_both).sum())))
print(pd.DataFrame(rows).to_string(index=False))
