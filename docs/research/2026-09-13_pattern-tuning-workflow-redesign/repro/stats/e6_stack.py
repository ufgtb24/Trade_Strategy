"""E6:(1) 整套闸阵 / 定案组合相对宽进参照格的配对差(按股去簇、两年折交互);
(2) 长表同一 bar 集合跨 match 重复计数对 FP 点估计与定案差值的影响(按 (symbol,fold,buy_date,四态) 去重对照)。
自检:count 与 cells.npz 逐位相等。"""
import glob, sys
import numpy as np, pandas as pd
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / ".claude/skills/tune-gates"))
from region_core import pred_level_index  # noqa: E402
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
         "AC": PROD | {"burst.peak_age_max": 0, "bo.exceed_threshold": 0.0075},
         "ABC": PROD | {"burst.peak_age_max": 0, "bo.exceed_threshold": 0.0075, "tb.stop_confirm_bars": 3}}
ST = ["fp_up", "fp_down", "fp_both", "fp_none"]
IDX = {k: np.array([LV[a].index(c[a]) for a in AX]) for k, c in CELLS.items()}
parts = {k: [] for k in CELLS}
for sp in sorted(glob.glob(str(LT / "part-*.parquet"))):
    df = pd.read_parquet(sp, columns=AX + ["symbol", "fold_Y", "buy_date"] + ST)
    cc = np.stack([pd.Categorical(df[c], categories=LV[c]).codes for c in D], 1)
    pi = np.stack([pred_level_index(df[c].values, op, LV[c]) for c, op in P], 1)
    keep = (cc >= 0).all(1) & (pi >= 0).all(1)
    for k, ix in IDX.items():
        m = keep & (cc == ix[:6]).all(1) & (pi >= ix[6:]).all(1)
        s = df.loc[m, ["symbol", "fold_Y", "buy_date"] + ST].copy()
        s["symbol"] = s.symbol.astype(str); s["fold_Y"] = s.fold_Y.astype(str)
        parts[k].append(s)
R = {k: pd.concat(v, ignore_index=True) for k, v in parts.items()}
z = np.load(ROOT / "outputs/tune_gates/bb_v1/main/cells.npz")
for k in CELLS:
    exp = [int(x) for x in z["count"][tuple(IDX[k])]]
    got = [int(R[k].loc[R[k].fold_Y == f, ST].to_numpy().sum()) for f in ("2024", "2025")]
    assert exp == got, (k, exp, got)
print("自检通过")

def resid(g):
    dec = g.fp_up + g.fp_down + g.fp_both; r = g.fp_up.sum() / dec.sum()
    return r, ((g.fp_up - r * dec) / dec.sum()).groupby(g.symbol).sum()

def paired(gx, gy):
    rx, ex = resid(gx); ry, ey = resid(gy); dl = ex.sub(ey, fill_value=0); n = len(dl)
    return rx - ry, float(np.sqrt((dl ** 2).sum() * n / (n - 1)))

def dedup(g):
    return g.drop_duplicates(["symbol", "fold_Y", "buy_date"] + ST)

for mode, fn in (("逐 match 计(长表现口径)", lambda g: g), ("同一买点日同四态去重", dedup)):
    print(f"\n== {mode}")
    for k in CELLS:
        g = fn(R[k])
        fps = [resid(g[g.fold_Y == f])[0] for f in ("2024", "2025")]
        print(f"  {k:4s} 行 {len(g):6d}  FP 2024 {fps[0]:.4f}  2025 {fps[1]:.4f}")
    for kx, ky in (("prod", "ref"), ("AC", "ref"), ("ABC", "ref"), ("A", "prod"), ("C", "prod"), ("AC", "prod")):
        out = []
        for f in ("2024", "2025"):
            gx, gy = fn(R[kx]), fn(R[ky])
            dlt, se = paired(gx[gx.fold_Y == f], gy[gy.fold_Y == f]); out.append((dlt, se))
        dp, sp_ = paired(fn(R[kx]), fn(R[ky]))
        z_int = (out[1][0] - out[0][0]) / np.hypot(out[0][1], out[1][1])
        print(f"  {kx}-{ky}: 2024 {100*out[0][0]:+.2f}±{100*out[0][1]:.2f}pt (z {out[0][0]/out[0][1]:+.2f}) / 2025 {100*out[1][0]:+.2f}±{100*out[1][1]:.2f}pt (z {out[1][0]/out[1][1]:+.2f}) / 合并 z {dp/sp_:+.2f} / 年交互 z {z_int:+.2f}")
