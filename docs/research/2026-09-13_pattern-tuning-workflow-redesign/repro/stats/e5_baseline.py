"""E5:边际基线闸的设计检验(只读 2026-09-07 dag-scoring 研究的现存产物:宽进 match 表 + 随机日表,均带买点日 ATR%)。
(a) 宽进 pattern 首次穿越率 vs 随机日基线:不匹配 / ATR 3·5·10 层 / 月 × ATR3 / 40 交易日窗 × ATR3,按股整簇自助 CI;
(b) 同一 tb 跨锚点重复计 bar 的影响(按 (symbol,tb_start,tb_end) 去重对照);
(c) distinct_pk≥3 子集:pattern 内原始 FP 差 vs 「各自层匹配基线后的差」——两端估计量是否同一个;
(d) 逐 match 首次穿越份额的分箱中位数是否退化(电池按 med 判形状的适用性)。
FP 口径统一 = up/(up+down+both)(tune-gates 契约)。"""
import numpy as np, pandas as pd
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
RP = ROOT / "docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro"
rng = np.random.default_rng(20260913)
NB = 500
SPAN = round(40 * 365 / 252)

def load(tag):
    d = pd.read_csv(RP / f"wide_{tag}.csv", keep_default_na=False, na_values=[""])
    b = pd.read_csv(RP / f"anchor_baseline_{tag}.csv", keep_default_na=False, na_values=[""])
    d = d[(d.n_buy_bars > 0) & d.atr_pct.notna()].copy()
    b = b[b.atr_pct.notna()].copy()
    for s in ("up", "down", "both", "none"):
        b[f"fp_{s}"] = (b.fp == s).astype(int)
    d["date"] = pd.to_datetime(d.tb_date); b["date"] = pd.to_datetime(b.date)
    return d, b

def strata(d, b, L, time):
    cuts = np.quantile(b.atr_pct, np.linspace(0, 1, L + 1)[1:-1]) if L > 1 else []
    ld, lb = np.searchsorted(cuts, d.atr_pct), np.searchsorted(cuts, b.atr_pct)
    if time == "month":
        td, tb = d.date.dt.month, b.date.dt.month
    elif time == "win40":
        t0 = min(d.date.min(), b.date.min()); td, tb = (d.date - t0).dt.days // SPAN, (b.date - t0).dt.days // SPAN
    else:
        td = tb = 0
    return pd.Series(ld).astype(str).values + "|" + pd.Series(td).astype(str).values, pd.Series(lb).astype(str).values + "|" + pd.Series(tb).astype(str).values

def mats(df, key):
    """(symbol × 层) 的 up 与 decided 计数矩阵。"""
    df = df.assign(_k=key, dec=df.fp_up + df.fp_down + df.fp_both)
    up = df.pivot_table(index="symbol", columns="_k", values="fp_up", aggfunc="sum", fill_value=0)
    dec = df.pivot_table(index="symbol", columns="_k", values="dec", aggfunc="sum", fill_value=0)
    return up, dec

def delta(pu, pd_, bu, bd, wp=None, wb=None):
    """直接标准化:Δ = FP_pattern − Σ_s w_s·FP_base,s;w_s = pattern 定向 bar 在层 s 的占比;基线空层剔除并报告占比。"""
    cols = pu.columns.intersection(bu.columns)
    PU = pu.values if wp is None else wp @ pu.values
    PD = pd_.values if wp is None else wp @ pd_.values
    BU = bu.values if wb is None else wb @ bu.values
    BD = bd.values if wb is None else wb @ bd.values
    PU, PD = np.atleast_2d(PU).sum(0) if wp is None else PU, np.atleast_2d(PD).sum(0) if wp is None else PD
    BU, BD = np.atleast_2d(BU).sum(0) if wb is None else BU, np.atleast_2d(BD).sum(0) if wb is None else BD
    ip = [pu.columns.get_loc(c) for c in cols]; ib = [bu.columns.get_loc(c) for c in cols]
    ok = BD[ib] >= 20
    fp_pat = PU.sum() / PD.sum()
    w = PD[ip][ok] / PD[ip][ok].sum()
    base = (w * (BU[ib][ok] / BD[ib][ok])).sum()
    cover = PD[ip][ok].sum() / PD.sum()
    return fp_pat - base, fp_pat, base, cover

def boot(pu, pd_, bu, bd):
    est = delta(pu, pd_, bu, bd)
    ns, nb = len(pu), len(bu); vals = []
    for _ in range(NB):
        wp = rng.multinomial(ns, np.full(ns, 1 / ns)).astype(float); wb = rng.multinomial(nb, np.full(nb, 1 / nb)).astype(float)
        vals.append(delta(pu, pd_, bu, bd, wp, wb)[0])
    return est, np.percentile(vals, [2.5, 97.5]), np.std(vals, ddof=1)

for tag in ("w2024", "w2025"):
    d, b = load(tag)
    dd = d.drop_duplicates(["symbol", "tb_start", "tb_end"])
    print(f"\n===== {tag}: pattern 行 {len(d)} / 去重后 {len(dd)}(同一 bar 集合跨锚点重复 {len(d)/len(dd):.2f}×)/ 股 {d.symbol.nunique()} ; 随机日 {len(b)} / 股 {b.symbol.nunique()}")
    for nm, dx in (("逐 match(重复计)", d), ("按 bar 集合去重", dd)):
        for L, time in ((1, None), (3, None), (5, None), (10, None), (3, "month"), (5, "month"), (3, "win40")):
            kd, kb = strata(dx, b, L, time)
            pu, pdm = mats(dx, kd); bu, bdm = mats(b, kb)
            (dl, fpp, base, cover), ci, se = boot(pu, pdm, bu, bdm)
            print(f"  [{nm}] ATR {L:>2} 层 × 时间 {str(time):5s}: FP_pat {fpp:.4f}  基线 {base:.4f}  Δ {dl:+.4f}  CI [{ci[0]:+.4f},{ci[1]:+.4f}] se {se:.4f} 覆盖 {cover:.3f}")
    # 窗级 Δ 离散度(ATR3 层匹配,每 40 交易日窗内单独算)
    t0 = min(dd.date.min(), b.date.min())
    wins = []
    for w_, g in dd.groupby((dd.date - t0).dt.days // SPAN):
        gb = b[((b.date - t0).dt.days // SPAN) == w_]
        if g[["fp_up", "fp_down", "fp_both"]].to_numpy().sum() < 100:
            continue
        kd, kb = strata(g, gb, 3, None); pu, pdm = mats(g, kd); bu, bdm = mats(gb, kb)
        wins.append(delta(pu, pdm, bu, bdm)[0])
    wins = np.array(wins)
    print(f"  窗级 Δ(ATR3,去重):{np.round(wins, 3).tolist()}  均值 {wins.mean():+.4f}  窗间 sd {wins.std(ddof=1):.4f}  → 以窗为簇的 SE ≈ {wins.std(ddof=1)/np.sqrt(len(wins)):.4f}(k={len(wins)})")
    # (c) distinct_pk≥3 子集:两种估计量
    sub = dd[dd.distinct_pk >= 3]
    for L, time in ((3, None), (3, "month")):
        kd_all, kb = strata(dd, b, L, time); kd_sub, _ = strata(sub, b, L, time)
        pu, pdm = mats(dd, kd_all); bu, bdm = mats(b, kb); su, sdm = mats(sub, kd_sub)
        dA, fA, bA, _ = delta(pu, pdm, bu, bdm); dS, fS, bS, _ = delta(su, sdm, bu, bdm)
        # 原始 FP 差的按股配对 SE(子集 ⊂ 全体)
        def res(df):
            dec = df.fp_up + df.fp_down + df.fp_both; r = df.fp_up.sum() / dec.sum()
            return ((df.fp_up - r * dec) / dec.sum()).groupby(df.symbol).sum()
        e = res(sub).sub(res(dd), fill_value=0); n = len(e); se_raw = np.sqrt((e ** 2).sum() * n / (n - 1))
        print(f"  [distinct_pk≥3, ATR{L}×{time}] 原始 FP 子集−全体 {fS - fA:+.4f}(按股 se {se_raw:.4f});基线 子集−全体 {bS - bA:+.4f};"
              f"层匹配Δ 子集−全体 {dS - dA:+.4f};子集 n_bar_dec {int((sub.fp_up+sub.fp_down+sub.fp_both).sum())}")
    # (d) 分箱中位数退化
    share = (dd.fp_up / (dd.fp_up + dd.fp_down + dd.fp_both)).where((dd.fp_up + dd.fp_down + dd.fp_both) > 0)
    q = pd.qcut(dd.vol_spike.rank(method="first"), 5, labels=False)
    tab = pd.DataFrame({"q": q, "s": share}).groupby("q").s.agg(["median", "mean", "count"])
    print(f"  逐 match 首次穿越份额中取值恰为 0 或 1 的占比 {share.isin([0, 1]).mean():.3f};vol_spike 五分位:median {tab['median'].round(3).tolist()} / mean {tab['mean'].round(3).tolist()}")
