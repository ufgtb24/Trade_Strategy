"""E4:在参照格(宽进)与生产格上,12 条轴各挪一档的配对差——按股去簇 SE、两年折交互 z、13 个时间窗异质性,
以及嵌套(where/过滤型)挪档的「过闸 vs 被拦」差与「两档筛选 SE 公式」对实测 SE 的校验。
自检:所有目标格各折 count 与 cells.npz 逐位相等,否则 raise。"""
import glob, json, sys, resource
import numpy as np, pandas as pd
from pathlib import Path
from scipy import stats
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / ".claude/skills/tune-gates"))
from region_core import pred_level_index  # noqa: E402
LT = ROOT / "outputs/tune_gates/bb_v1/main/longtable"
D = ["bo.exceed_threshold", "bo.min_relative_height", "burst.gap_max", "tb.max_rise_k", "tb.max_span", "tb.stop_confirm_bars"]
P = [("burst.count", ">="), ("burst.distinct_pk", ">="), ("burst.first_drought", ">="), ("burst.peak_age_max", ">="), ("burst.max_bar_vol_ratio", ">="), ("tb.max_day_drop", "<")]
PN = [c for c, _ in P]
LV = {"bo.exceed_threshold": [0.0015, 0.003, 0.0045, 0.0075], "bo.min_relative_height": [0.1, 0.2, 0.3, 0.5], "burst.gap_max": [4, 8, 12, 20],
      "tb.max_rise_k": [0.75, 1.5, 2.25, 3.75], "tb.max_span": [10, 20, 30, 50], "tb.stop_confirm_bars": [1, 2, 3, 4],
      "burst.count": [1, 2, 3, 4], "burst.distinct_pk": [1, 3, 5], "burst.first_drought": [0, 40, 80], "burst.peak_age_max": [0, 60, 120],
      "burst.max_bar_vol_ratio": [0, 3, 6], "tb.max_day_drop": [None, 0.2]}
AX = D + PN
REF = {"bo.exceed_threshold": 0.003, "bo.min_relative_height": 0.2, "burst.gap_max": 8, "tb.max_rise_k": 1.5, "tb.max_span": 20, "tb.stop_confirm_bars": 1,
       "burst.count": 1, "burst.distinct_pk": 1, "burst.first_drought": 0, "burst.peak_age_max": 0, "burst.max_bar_vol_ratio": 0, "tb.max_day_drop": None}
PROD = REF | {"burst.distinct_pk": 3, "burst.first_drought": 40, "burst.peak_age_max": 60, "burst.max_bar_vol_ratio": 3, "tb.max_day_drop": 0.2}
ST = ["fp_up", "fp_down", "fp_both", "fp_none"]
SPAN = round(40 * 365 / 252)
FOLDS = ("2024", "2025")

def li(cell):
    return tuple(LV[a].index(cell[a]) for a in AX)

cells, plan = {}, []
for bn, b in {"ref": REF, "prod": PROD}.items():
    cells[bn] = b
    for a in AX:
        i = LV[a].index(b[a])
        for j in (i - 1, i + 1):
            if 0 <= j < len(LV[a]):
                k = f"{bn}|{a}|{b[a]}->{LV[a][j]}"
                cells[k] = b | {a: LV[a][j]}
                plan.append(dict(base=bn, key=k, axis=a, frm=b[a], to=LV[a][j], nested=a in PN, tighten=j > i))
IDX = {k: np.array(li(c)) for k, c in cells.items()}
agg = {k: [] for k in cells}
for sp in sorted(glob.glob(str(LT / "part-*.parquet"))):
    df = pd.read_parquet(sp, columns=AX + ["symbol", "fold_Y", "buy_date"] + ST)
    cc = np.stack([pd.Categorical(df[c], categories=LV[c]).codes for c in D], 1)
    pi = np.stack([pred_level_index(df[c].values, op, LV[c]) for c, op in P], 1)
    keep = (cc >= 0).all(1) & (pi >= 0).all(1)
    base = pd.DataFrame({"symbol": df["symbol"].astype(str).to_numpy(), "fold": df["fold_Y"].astype(str).to_numpy(),
                         "bucket": ((pd.to_datetime(df["buy_date"]) - pd.Timestamp("2024-01-01")).dt.days // SPAN).to_numpy(),
                         "u": df["fp_up"].to_numpy(np.int64), "d": (df["fp_up"] + df["fp_down"] + df["fp_both"]).to_numpy(np.int64),
                         "n": df[ST].sum(1).to_numpy(np.int64)})
    for k, ix in IDX.items():
        m = keep & (cc == ix[:6]).all(1) & (pi >= ix[6:]).all(1)
        if m.any():
            agg[k].append(base[m].groupby(["symbol", "fold", "bucket"], sort=False).sum().reset_index())
G = {k: pd.concat(v, ignore_index=True).groupby(["symbol", "fold", "bucket"]).sum().reset_index() for k, v in agg.items()}
z = np.load(ROOT / "outputs/tune_gates/bb_v1/main/cells.npz")
for k in cells:
    exp = [int(x) for x in z["count"][tuple(IDX[k])]]
    got = [int(G[k].loc[G[k].fold == f, "n"].sum()) for f in FOLDS]
    if exp != got:
        raise SystemExit(f"自检失败 {k}: {exp} vs {got}")
print(f"自检通过:{len(cells)} 格 × 2 折 count 与 cells.npz 逐位相等")

def resid(g, keys):
    r = g.u.sum() / g.d.sum()
    return r, ((g.u - r * g.d) / g.d.sum()).groupby([g[c] for c in keys]).sum()

def paired(gx, gy, keys=("symbol",)):
    rx, ex = resid(gx, list(keys)); ry, ey = resid(gy, list(keys))
    dl = ex.sub(ey, fill_value=0.0); n = len(dl)
    return rx - ry, float(np.sqrt((dl ** 2).sum() * n / (n - 1))), rx, ry

def se_single(g):
    r, e = resid(g, ["symbol"]); n = len(e)
    return r, float(np.sqrt((e ** 2).sum() * n / (n - 1)))

def minus(big, small):
    """嵌套差集:big ⊇ small(按 symbol/fold/bucket 聚合计数相减)。"""
    m = big.merge(small, on=["symbol", "fold", "bucket"], how="left", suffixes=("", "_s")).fillna(0)
    out = m[["symbol", "fold", "bucket"]].copy()
    for c in ("u", "d", "n"):
        out[c] = m[c] - m[c + "_s"]
    if (out[["u", "d", "n"]] < 0).any().any():
        raise SystemExit("嵌套假设被破坏:差集出现负计数")
    return out[out.n > 0]

rows, summ = [], []
for p in plan:
    X, Y = G[p["key"]], G[p["base"]]
    rec = dict(base=p["base"], axis=p["axis"], move=f"{p['frm']}->{p['to']}")
    zs = {}
    for f in FOLDS:
        gx, gy = X[X.fold == f], Y[Y.fold == f]
        if gx.d.sum() < 30:
            zs[f] = None; continue
        dlt, se, rx, ry = paired(gx, gy)
        r_keep = gx.d.sum() / gy.d.sum()
        # 两档筛选 SE 公式:嵌套挪档时 SE ≈ sqrt(p(1-p)·deff/D_big · (1-r)/r),deff = 大集合按股去簇的 bar 级设计效应
        big, small = (gy, gx) if p["tighten"] else (gx, gy)
        se_formula = None; kr = None; se_kr = None
        if p["nested"]:
            pb, seb = se_single(big); deff = (seb / np.sqrt(pb * (1 - pb) / big.d.sum())) ** 2
            rr = small.d.sum() / big.d.sum()
            se_formula = float(np.sqrt(pb * (1 - pb) * deff / big.d.sum() * (1 - rr) / rr)) if 0 < rr < 1 else None
            rem = minus(big, small)
            if rem.d.sum() >= 30:
                kr, se_kr, _, _ = paired(small, rem)
        zs[f] = dlt / se
        rows.append(rec | dict(fold=f, D_base=int(gy.d.sum()), D_move=int(gx.d.sum()), keep_ratio=round(r_keep, 3), sym_move=int(gx.symbol.nunique()),
                               diff_pt=round(100 * dlt, 2), se_pt=round(100 * se, 2), z=round(dlt / se, 2),
                               se_formula_pt=None if se_formula is None else round(100 * se_formula, 2),
                               kept_minus_removed_pt=None if kr is None else round(100 * kr, 2), se_kr_pt=None if se_kr is None else round(100 * se_kr, 2)))
    if zs.get("2024") is None or zs.get("2025") is None:
        continue
    r24 = rows[-2]; r25 = rows[-1]
    z_int = (r25["diff_pt"] - r24["diff_pt"]) / np.hypot(r24["se_pt"], r25["se_pt"])
    dp, sep, _, _ = paired(X, Y)
    # 13 窗异质性
    ests = []
    for b in sorted(set(X.bucket) & set(Y.bucket)):
        gx, gy = X[X.bucket == b], Y[Y.bucket == b]
        if gy.d.sum() < 50 or gx.d.sum() < 20 or gy.symbol.nunique() < 5:
            continue
        dd, se_b, _, _ = paired(gx, gy)
        if se_b > 0:
            ests.append((dd, se_b ** 2))
    Q = tau = Qp = None
    if len(ests) >= 4:
        y = np.array([e[0] for e in ests]); v = np.array([e[1] for e in ests]); w = 1 / v
        mu = (w * y).sum() / w.sum(); Q = float((w * (y - mu) ** 2).sum()); kk = len(y)
        t2 = max(0.0, (Q - (kk - 1)) / (w.sum() - (w ** 2).sum() / w.sum())); tau = float(np.sqrt(t2)); Qp = float(stats.chi2.sf(Q, kk - 1))
    summ.append(rec | dict(z24=r24["z"], z25=r25["z"], same_sign=bool(np.sign(r24["diff_pt"]) == np.sign(r25["diff_pt"])),
                           both_pos=bool(r24["diff_pt"] > 0 and r25["diff_pt"] > 0), z_int=round(float(z_int), 2),
                           pooled_pt=round(100 * dp, 2), pooled_z=round(dp / sep, 2), n_windows=len(ests),
                           Q_p=None if Qp is None else round(Qp, 3), tau_pt=None if tau is None else round(100 * tau, 2)))
R = pd.DataFrame(rows); S = pd.DataFrame(summ)
pd.set_option("display.width", 250)
print(R.to_string(index=False)); print(); print(S.to_string(index=False))
for bn in ("ref", "prod"):
    s = S[S.base == bn]
    print(f"[{bn}] 挪档数 {len(s)}:两年同号 {int(s.same_sign.sum())}(零假设期望 {len(s)/2:.1f})/ 两年同正 {int(s.both_pos.sum())}(期望 {len(s)/4:.1f})/ "
          f"|z_int|>1.96 {int((s.z_int.abs() > 1.96).sum())}(期望 {0.05*len(s):.1f})/ 13 窗 Q p<0.05 {int((s.Q_p < 0.05).sum())} / |合并 z|>1.96 {int((s.pooled_z.abs() > 1.96).sum())}")
nest = R[R.se_formula_pt.notna()]
print("两档筛选 SE 公式 / 实测配对 SE 之比:", nest.assign(ratio=nest.se_formula_pt / nest.se_pt).ratio.describe().round(2).to_dict())
R.to_csv(HERE / "e4_oat_rows.csv", index=False); S.to_csv(HERE / "e4_oat_summary.csv", index=False)
print(f"peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB")
