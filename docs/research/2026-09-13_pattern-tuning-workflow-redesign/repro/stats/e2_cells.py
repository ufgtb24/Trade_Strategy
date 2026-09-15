"""E2:关键格的有效样本、按股/按时间桶去簇的标准误、设计效应,以及定案改动(A/C/AC/B)在各时间窗上的异质性。
只读长表必要列,逐分片过滤出目标格的行。自检:各格各折 count 必须与 cells.npz 逐位相等,否则 raise。"""
import glob, json, resource
import numpy as np, pandas as pd
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
LT = ROOT / "outputs/tune_gates/bb_v1/main/longtable"
D = ["bo.exceed_threshold", "bo.min_relative_height", "burst.gap_max", "tb.max_rise_k", "tb.max_span", "tb.stop_confirm_bars"]
P = [("burst.count", ">="), ("burst.distinct_pk", ">="), ("burst.first_drought", ">="), ("burst.peak_age_max", ">="), ("burst.max_bar_vol_ratio", ">="), ("tb.max_day_drop", "<")]
LV = {"bo.exceed_threshold": [0.0015, 0.003, 0.0045, 0.0075], "bo.min_relative_height": [0.1, 0.2, 0.3, 0.5], "burst.gap_max": [4, 8, 12, 20],
      "tb.max_rise_k": [0.75, 1.5, 2.25, 3.75], "tb.max_span": [10, 20, 30, 50], "tb.stop_confirm_bars": [1, 2, 3, 4],
      "burst.count": [1, 2, 3, 4], "burst.distinct_pk": [1, 3, 5], "burst.first_drought": [0, 40, 80], "burst.peak_age_max": [0, 60, 120],
      "burst.max_bar_vol_ratio": [0, 3, 6], "tb.max_day_drop": [None, 0.2]}
AX = D + [c for c, _ in P]
REF = {"bo.exceed_threshold": 0.003, "bo.min_relative_height": 0.2, "burst.gap_max": 8, "tb.max_rise_k": 1.5, "tb.max_span": 20, "tb.stop_confirm_bars": 1,
       "burst.count": 1, "burst.distinct_pk": 1, "burst.first_drought": 0, "burst.peak_age_max": 0, "burst.max_bar_vol_ratio": 0, "tb.max_day_drop": None}
PROD = REF | {"burst.distinct_pk": 3, "burst.first_drought": 40, "burst.peak_age_max": 60, "burst.max_bar_vol_ratio": 3, "tb.max_day_drop": 0.2}
CELLS = {"ref": REF, "prod": PROD, "A": PROD | {"burst.peak_age_max": 0}, "C": PROD | {"bo.exceed_threshold": 0.0075},
         "AC": PROD | {"burst.peak_age_max": 0, "bo.exceed_threshold": 0.0075}, "B": PROD | {"tb.stop_confirm_bars": 3},
         "chat": {"bo.exceed_threshold": 0.0045, "bo.min_relative_height": 0.2, "burst.gap_max": 4, "tb.max_rise_k": 2.25, "tb.max_span": 20, "tb.stop_confirm_bars": 3,
                  "burst.count": 4, "burst.distinct_pk": 3, "burst.first_drought": 80, "burst.peak_age_max": 120, "burst.max_bar_vol_ratio": 0, "tb.max_day_drop": 0.2}}
ST = ["fp_up", "fp_down", "fp_both", "fp_none"]
COLS = AX + ["symbol", "fold_Y", "buy_date", "fr"] + ST
SPAN = round(40 * 365 / 252)

def mask(df, cell):
    m = np.ones(len(df), bool)
    for c in D:
        m &= np.isclose(df[c].to_numpy(float), cell[c])
    for c, op in P:
        v = cell[c]
        if v is None:
            continue
        x = df[c].to_numpy(float)
        m &= (x >= v) if op == ">=" else (x < v)
    return m

parts = {k: [] for k in CELLS}
for sp in sorted(glob.glob(str(LT / "part-*.parquet"))):
    df = pd.read_parquet(sp, columns=COLS)
    # prepare() 丢弃任一谓词列(非 None 最松档)为 NaN 的行;逐格 mask 下 NaN 比较恒 False,与之等价
    for k, cell in CELLS.items():
        sub = df.loc[mask(df, cell), ["symbol", "fold_Y", "buy_date", "fr"] + ST].copy()
        sub["symbol"] = sub["symbol"].astype(str); sub["fold_Y"] = sub["fold_Y"].astype(str)
        parts[k].append(sub)
R = {k: pd.concat(v, ignore_index=True) for k, v in parts.items()}

z = np.load(ROOT / "outputs/tune_gates/bb_v1/main/cells.npz")
for k, cell in CELLS.items():
    idx = tuple(LV[a].index(cell[a]) for a in AX)
    exp = z["count"][idx]
    got = [int(R[k].loc[R[k].fold_Y == f, ST].to_numpy().sum()) for f in ("2024", "2025")]
    if list(map(int, exp)) != got:
        raise SystemExit(f"自检失败 {k}: cells.npz count {exp} vs 长表过滤 {got}")
print("自检通过:7 格 × 2 折 count 与 cells.npz 逐位相等")

def ratio_se(u, d, groups):
    """比率估计 R=Σu/Σd 的线性化标准误,groups=None 表示逐行独立;否则按组聚合(簇稳健)。"""
    U, Dn = u.sum(), d.sum(); r = U / Dn
    e = pd.Series(u - r * d)
    if groups is not None:
        e = e.groupby(np.asarray(groups)).sum()
    n = len(e)
    return r, float(np.sqrt((e ** 2).sum() * n / max(n - 1, 1)) / Dn), n

rng = np.random.default_rng(20260913)
out = {}
for k, df in R.items():
    df = df.assign(bucket=(pd.to_datetime(df.buy_date) - pd.Timestamp("2024-01-01")).dt.days // SPAN,
                   den=df.fp_up + df.fp_down + df.fp_both)
    for f in ("2024", "2025"):
        g = df[df.fold_Y == f]
        u, d = g.fp_up.to_numpy(float), g.den.to_numpy(float)
        r, se_row, n_row = ratio_se(u, d, None)
        _, se_unit, n_unit = ratio_se(u, d, (g.symbol + "|" + g.buy_date.astype(str)).to_numpy())
        _, se_sym, n_sym = ratio_se(u, d, g.symbol.to_numpy())
        _, se_bkt, n_bkt = ratio_se(u, d, g.bucket.to_numpy())
        se_bar = np.sqrt(r * (1 - r) / d.sum())
        # 中位收益的按股整簇自助标准误(对照首次穿越率的抽样方差)
        syms = g.symbol.to_numpy(); us = np.unique(syms); gi = {s: np.where(syms == s)[0] for s in us}
        frv = g.fr.to_numpy(float); meds = []
        for _ in range(300):
            pick = rng.choice(us, len(us)); sel = np.concatenate([gi[s] for s in pick]); meds.append(np.nanmedian(frv[sel]))
        out[(k, f)] = dict(cell=k, fold=f, buy_bars=int(g[ST].to_numpy().sum()), den=int(d.sum()), rows=len(g), units=n_unit, symbols=n_sym, buckets=n_bkt,
                           FP=round(r, 4), se_bar=round(se_bar, 4), se_row=round(se_row, 4), se_unit=round(se_unit, 4), se_sym=round(se_sym, 4), se_bucket=round(se_bkt, 4),
                           deff_sym=round((se_sym / se_bar) ** 2, 2), med_fr=round(float(np.nanmedian(frv)), 4), se_med_fr_sym=round(float(np.std(meds, ddof=1)), 4))
T = pd.DataFrame(out.values())
print(T.to_string(index=False))

# 定案改动的配对差:按股聚合线性化残差,重叠买点自动计入协方差
def contrast(kx, ky="prod"):
    rows = []
    for f in ("2024", "2025", None):
        gx = R[kx] if f is None else R[kx][R[kx].fold_Y == f]
        gy = R[ky] if f is None else R[ky][R[ky].fold_Y == f]
        def resid(g, by):
            den = g.fp_up + g.fp_down + g.fp_both; r = g.fp_up.sum() / den.sum()
            return r, ((g.fp_up - r * den) / den.sum()).groupby(by(g)).sum()
        by_sym = lambda g: g.symbol
        rx, ex = resid(gx, by_sym); ry, ey = resid(gy, by_sym)
        dlt = pd.concat([ex, -ey], axis=1).fillna(0).sum(1)
        n = len(dlt); se = float(np.sqrt((dlt ** 2).sum() * n / (n - 1)))
        rows.append(dict(contrast=f"{kx}-{ky}", fold=f or "pooled", diff_pt=round(100 * (rx - ry), 2), se_sym_pt=round(100 * se, 2), z=round((rx - ry) / se, 2)))
    # 逐时间桶差值 + DerSimonian-Laird 异质性
    bx = R[kx].assign(b=(pd.to_datetime(R[kx].buy_date) - pd.Timestamp("2024-01-01")).dt.days // SPAN)
    by = R[ky].assign(b=(pd.to_datetime(R[ky].buy_date) - pd.Timestamp("2024-01-01")).dt.days // SPAN)
    ests = []
    for b in sorted(set(bx.b) & set(by.b)):
        gx, gy = bx[bx.b == b], by[by.b == b]
        def resid(g):
            den = g.fp_up + g.fp_down + g.fp_both; r = g.fp_up.sum() / den.sum()
            return r, ((g.fp_up - r * den) / den.sum()).groupby(g.symbol).sum()
        rx, ex = resid(gx); ry, ey = resid(gy)
        dlt = pd.concat([ex, -ey], axis=1).fillna(0).sum(1); n = len(dlt)
        if n < 5 or gy.fp_up.sum() + gy.fp_down.sum() < 50:
            continue
        ests.append((b, rx - ry, (dlt ** 2).sum() * n / (n - 1)))
    y = np.array([e[1] for e in ests]); v = np.array([e[2] for e in ests]); w = 1 / v
    mu_fe = (w * y).sum() / w.sum(); Q = (w * (y - mu_fe) ** 2).sum(); k = len(y)
    tau2 = max(0.0, (Q - (k - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
    wr = 1 / (v + tau2); mu_re = (wr * y).sum() / wr.sum(); se_re = np.sqrt(1 / wr.sum())
    from scipy import stats
    het = dict(contrast=f"{kx}-{ky}", buckets=k, per_bucket_pt=[round(100 * x, 1) for x in y], per_bucket_se_pt=[round(100 * np.sqrt(x), 1) for x in v],
               Q=round(Q, 2), Q_p=round(float(stats.chi2.sf(Q, k - 1)), 4), tau_pt=round(100 * np.sqrt(tau2), 2),
               mu_re_pt=round(100 * mu_re, 2), se_re_pt=round(100 * se_re, 2), n_pos=int((y > 0).sum()),
               pred_interval_pt=[round(100 * (mu_re - 1.96 * np.sqrt(tau2 + se_re ** 2)), 1), round(100 * (mu_re + 1.96 * np.sqrt(tau2 + se_re ** 2)), 1)])
    return rows, het

allrows, hets = [], []
for kx in ["A", "C", "AC", "B"]:
    r_, h_ = contrast(kx); allrows += r_; hets.append(h_)
print(pd.DataFrame(allrows).to_string(index=False))
for h in hets:
    print(json.dumps(h, ensure_ascii=False))
T.to_csv(HERE / "e2_cells.csv", index=False)
pd.DataFrame(allrows).to_csv(HERE / "e2_contrasts.csv", index=False)
(HERE / "e2_heterogeneity.json").write_text(json.dumps(hets, ensure_ascii=False, indent=1))
print(f"peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB")
