# -*- coding: utf-8 -*-
"""E4b:给 E4 的拆解加按股整簇自助 CI(B=2000)。数据与口径同 e4_exceed_decomposition.py。

报三个量(逐年、逐 where 设置):
  dFP      = FP(S1) − FP(S0)                     提高突破幅度阈值的总变化
  drop_eff = FP(S0 去掉 D_gone∪D_wh) − FP(S0)     只删掉「掉出去的买点」带来的变化
  add_eff  = FP(S1) − FP(S1 去掉 A_new∪A_wh)      只加入「新进来的买点」带来的变化
按股自助只覆盖股内相关,不覆盖同期跨股相关——CI 偏窄,只作量级参考。
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import e4_exceed_decomposition as E  # noqa: E402
import pyarrow.dataset as ds  # noqa: E402

B = 2000
UNIT = os.environ.get("UNIT", "row")   # row = 执行端行口径;segment = 每个回踩段只计一次
rng = np.random.default_rng(20260913)


def main():
    dset = ds.dataset(sorted(str(p) for p in E.LT.glob("part-*.parquet")), format="parquet")
    flt = ds.field("bo.exceed_threshold").isin([E.TH0, E.TH1])
    for k, v in E.REF.items():
        flt &= ds.field(k) == v
    cols = ["symbol", "bo.exceed_threshold"] + E.WCOLS + ["tb.start", "tb.end"] + E.FP + ["fold_Y"]
    t = dset.to_table(columns=cols, filter=flt).to_pandas()
    t["symbol"] = t["symbol"].astype(str); t["fold_Y"] = t["fold_Y"].astype(str)
    t["k"] = t["symbol"] + "_" + t["tb.start"].astype(str) + "_" + t["tb.end"].astype(str)
    t["up"] = t.fp_up; t["den"] = t.fp_up + t.fp_down + t.fp_both
    for setting in ["prod_old", "prod_new", "wide"]:
        for year in ["2024", "2025"]:
            x = t[t.fold_Y == year]
            x0 = x[x["bo.exceed_threshold"] == E.TH0]; x1 = x[x["bo.exceed_threshold"] == E.TH1]
            r0 = x0[E.where_mask(x0, setting)]; r1 = x1[E.where_mask(x1, setting)]
            S0, S1 = set(r0.k), set(r1.k)
            dropped = S0 - S1; added = S1 - S0
            syms = sorted(set(x.symbol)); si = {s: i for i, s in enumerate(syms)}; n = len(syms)

            def vec(df, keys=None, exclude=False):
                if UNIT == "segment":
                    df = df[df[E.FP].sum(1) > 0].drop_duplicates("k")
                if keys is not None:
                    m = df.k.isin(keys)
                    df = df[~m] if exclude else df[m]
                g = df.groupby("symbol")[["up", "den"]].sum()
                u = np.zeros(n); dn = np.zeros(n)
                idx = [si[s] for s in g.index]
                u[idx] = g.up.to_numpy(); dn[idx] = g.den.to_numpy()
                return u, dn

            parts = dict(S0=vec(r0), S1=vec(r1), S0_nodrop=vec(r0, dropped, True),
                         S1_noadd=vec(r1, added, True), D=vec(r0, dropped), A=vec(r1, added))
            W = rng.multinomial(n, np.full(n, 1 / n), size=B).astype(float)
            rate = lambda p, w=None: ((p[0].sum() if w is None else w @ p[0]) /
                                      np.maximum((p[1].sum() if w is None else w @ p[1]), 1e-12))
            out = {}
            for name, (a, b) in {"dFP": ("S1", "S0"), "drop_eff": ("S0_nodrop", "S0"),
                                 "add_eff": ("S1", "S1_noadd")}.items():
                pt = rate(parts[a]) - rate(parts[b])
                bs = rate(parts[a], W) - rate(parts[b], W)
                out[name] = (100 * pt, *np.percentile(100 * bs, [2.5, 97.5]))
            nD = int(parts["D"][1].sum()); nA = int(parts["A"][1].sum())
            print(f"{setting:8s} {year}: " + "  ".join(f"{k} {v[0]:+.2f} [{v[1]:+.2f},{v[2]:+.2f}]"
                                                     for k, v in out.items())
                  + f"  | 掉出买点 {len(dropped)}(计数 {nD}) 新进 {len(added)}(计数 {nA})")


if __name__ == "__main__":
    main()
