"""E5b:边际基线的时间匹配粒度与 ATR 切点口径(回答 executor §4.2 交 stats 的两问):
时间 = 同一 40 交易日窗 / 同一交易日;ATR 切点 = 全窗统一三分位 / 该时间单元内横截面三分位。按股整簇自助 SE(B=300),按 bar 集合去重。"""
import numpy as np, pandas as pd
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
RP = ROOT / "docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro"
rng = np.random.default_rng(20260913)
SPAN = round(40 * 365 / 252)
NB = 300

def load(tag):
    d = pd.read_csv(RP / f"wide_{tag}.csv", keep_default_na=False, na_values=[""])
    b = pd.read_csv(RP / f"anchor_baseline_{tag}.csv", keep_default_na=False, na_values=[""])
    d = d[(d.n_buy_bars > 0) & d.atr_pct.notna()].drop_duplicates(["symbol", "tb_start", "tb_end"]).copy()
    b = b[b.atr_pct.notna()].copy()
    for s in ("up", "down", "both"):
        b[f"fp_{s}"] = (b.fp == s).astype(int)
    d["date"] = pd.to_datetime(d.tb_date); b["date"] = pd.to_datetime(b.date)
    t0 = b.date.min()
    for x in (d, b):
        x["win"] = (x.date - t0).dt.days // SPAN
        x["day"] = x.date.dt.strftime("%Y-%m-%d")
        x["dec"] = x.fp_up + x.fp_down + x.fp_both
    return d, b

def layers(d, b, tkey, cut):
    if cut == "global":
        q = np.quantile(b.atr_pct, [1 / 3, 2 / 3])
        return np.searchsorted(q, d.atr_pct), np.searchsorted(q, b.atr_pct)
    qq = b.groupby(tkey).atr_pct.quantile([1 / 3, 2 / 3]).unstack()
    qq.columns = ["q1", "q2"]
    dm = d[[tkey]].join(qq, on=tkey); bm = b[[tkey]].join(qq, on=tkey)
    ld = (d.atr_pct > dm.q1).astype(int) + (d.atr_pct > dm.q2).astype(int)
    lb = (b.atr_pct > bm.q1).astype(int) + (b.atr_pct > bm.q2).astype(int)
    ld[dm.q1.isna()] = -1
    return ld.to_numpy(), lb.to_numpy()

def run(d, b, tkey, cut):
    ld, lb = layers(d, b, tkey, cut)
    d = d.assign(k=d[tkey].astype(str) + "|" + pd.Series(ld, index=d.index).astype(str))
    b = b.assign(k=b[tkey].astype(str) + "|" + pd.Series(lb, index=b.index).astype(str))
    # 基线层内首次穿越率(≥20 定向日才用)
    bs = b.groupby("k")[["fp_up", "dec"]].sum()
    ok = bs.index[bs.dec >= 20]
    dd = d[d.k.isin(ok)]
    cover = dd.dec.sum() / d.dec.sum()
    P = dd.pivot_table(index="symbol", columns="k", values=["fp_up", "dec"], aggfunc="sum", fill_value=0)
    B = b[b.k.isin(ok)].pivot_table(index="symbol", columns="k", values=["fp_up", "dec"], aggfunc="sum", fill_value=0)
    cols = P["dec"].columns
    PU, PD = P["fp_up"][cols].to_numpy(float), P["dec"][cols].to_numpy(float)
    BU, BD = B["fp_up"].reindex(columns=cols, fill_value=0).to_numpy(float), B["dec"].reindex(columns=cols, fill_value=0).to_numpy(float)
    def est(wp, wb):
        pu, pdn = wp @ PU, wp @ PD; bu, bdn = wb @ BU, wb @ BD
        m = bdn > 0
        return pu.sum() / pdn.sum() - (pdn[m] / pdn[m].sum() * bu[m] / bdn[m]).sum()
    e0 = est(np.ones(len(PU)), np.ones(len(BU)))
    vals = [est(rng.multinomial(len(PU), np.full(len(PU), 1 / len(PU))).astype(float),
                rng.multinomial(len(BU), np.full(len(BU), 1 / len(BU))).astype(float)) for _ in range(NB)]
    return e0, np.std(vals, ddof=1), cover, len(cols)

for tag in ("w2024", "w2025"):
    d, b = load(tag)
    print(f"== {tag}: pattern 去重行 {len(d)};随机日 {len(b)}")
    for tkey, cut in (("win", "global"), ("win", "per"), ("day", "global"), ("day", "per")):
        e, se, cov, ns = run(d, b, tkey, cut)
        print(f"  时间={'40日窗' if tkey=='win' else '同一交易日'} ATR切点={'全窗统一' if cut=='global' else '单元内横截面'}: Δ {e:+.4f} ± {se:.4f}(按股)  覆盖 {cov:.3f}  层数 {ns}")
