"""E10:按回踩段身份(symbol, 年折, tb.start, tb.end)去重复核关键对比——格内先按闸过滤,再去重,
即「段内任一行过闸就算这段过闸」,一段只计一次。对照:逐 match 计、(买点日+四态)代理去重。
内容:突破幅度在生产闸阵/宽进的效应与差中差;生产点逐道删闸的非劣效下界(δ_NI=2pt);生产格水平 SE(分辨力算法的输入)。"""
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
C = {"bo.exceed_threshold": 0.0075}
CELLS = {"ref": REF, "refC": REF | C, "prod": PROD, "prodC": PROD | C,
         "del_peak": PROD | {"burst.peak_age_max": 0}, "del_vol": PROD | {"burst.max_bar_vol_ratio": 0},
         "del_fd": PROD | {"burst.first_drought": 0}, "del_pk": PROD | {"burst.distinct_pk": 1}, "del_mdd": PROD | {"tb.max_day_drop": None}}
ST = ["fp_up", "fp_down", "fp_both", "fp_none"]
IDX = {k: np.array([LV[a].index(c[a]) for a in AX]) for k, c in CELLS.items()}
parts = {k: [] for k in CELLS}
for sp in sorted(glob.glob(str(LT / "part-*.parquet"))):
    df = pd.read_parquet(sp, columns=AX + ["symbol", "fold_Y", "buy_date", "tb.start", "tb.end"] + ST)
    cc = np.stack([pd.Categorical(df[c], categories=LV[c]).codes for c in D], 1)
    pi = np.stack([pred_level_index(df[c].values, op, LV[c]) for c, op in P], 1)
    keep = (cc >= 0).all(1) & (pi >= 0).all(1)
    for k, ix in IDX.items():
        m = keep & (cc == ix[:6]).all(1) & (pi >= ix[6:]).all(1)
        s = df.loc[m, ["symbol", "fold_Y", "buy_date", "tb.start", "tb.end"] + ST].copy()
        s["symbol"] = s.symbol.astype(str); s["fold_Y"] = s.fold_Y.astype(str)
        parts[k].append(s)
R = {k: pd.concat(v, ignore_index=True) for k, v in parts.items()}
z = np.load(ROOT / "outputs/tune_gates/bb_v1/main/cells.npz")
for k in CELLS:
    assert [int(x) for x in z["count"][tuple(IDX[k])]] == [int(R[k].loc[R[k].fold_Y == f, ST].to_numpy().sum()) for f in ("2024", "2025")], k
print("自检通过:9 格 count 与 cells.npz 逐位相等")

SEG = ["symbol", "fold_Y", "tb.start", "tb.end"]
MODES = {"逐 match 计": lambda g: g,
         "代理去重(买点日+四态)": lambda g: g.drop_duplicates(["symbol", "fold_Y", "buy_date"] + ST),
         "段去重(tb.start,tb.end)": lambda g: g.drop_duplicates(SEG)}
# 段键下四态是否唯一(同 span 同 label)
g = R["ref"]; chk = g.groupby(SEG)[ST].nunique().max().max()
print(f"同段四态取值唯一性:每段内四态最多 {chk} 种取值(1 = 段键决定 label)")
for k in ("ref", "prod", "prodC"):
    print(f"  {k}: 行 {len(R[k])} / 段 {len(R[k].drop_duplicates(SEG))} = {len(R[k])/len(R[k].drop_duplicates(SEG)):.2f}×;代理键 {len(R[k].drop_duplicates(['symbol','fold_Y','buy_date']+ST))}")

def resid(g):
    dec = g.fp_up + g.fp_down + g.fp_both; r = g.fp_up.sum() / dec.sum()
    return r, ((g.fp_up - r * dec) / dec.sum()).groupby(g.symbol).sum()

def lincomb(coef, fold, fn):
    est, es = 0.0, []
    for k, c in coef.items():
        gg = fn(R[k]); gg = gg if fold is None else gg[gg.fold_Y == fold]
        r, e = resid(gg); est += c * r; es.append(c * e)
    tot = pd.concat(es, axis=1).fillna(0).sum(1); n = len(tot)
    return est, float(np.sqrt((tot ** 2).sum() * n / (n - 1)))

CONTR = [("C 在生产闸阵", {"prodC": 1, "prod": -1}), ("C 在宽进参照格", {"refC": 1, "ref": -1}),
         ("差中差 生产−宽进", {"prodC": 1, "prod": -1, "refC": -1, "ref": 1}),
         ("删峰龄闸 60→0", {"del_peak": 1, "prod": -1}), ("删量能闸 3→0", {"del_vol": 1, "prod": -1}),
         ("删旱期闸 40→0", {"del_fd": 1, "prod": -1}), ("删 distinct_pk 3→1", {"del_pk": 1, "prod": -1}),
         ("删单日跌幅闸 0.2→不设", {"del_mdd": 1, "prod": -1})]
for mode, fn in MODES.items():
    print(f"\n== {mode}")
    for name, coef in CONTR:
        out = []
        for f in ("2024", "2025", None):
            e, se = lincomb(coef, f, fn); out.append((e, se))
        e, se = out[2]
        z_int = (out[1][0] - out[0][0]) / np.hypot(out[0][1], out[1][1])
        ni = f"  非劣效下界(单侧95%) {100*(e-1.645*se):+.2f}pt → δ_NI=2pt {'通过' if e-1.645*se >= -0.02 else '不通过'}" if name.startswith("删") else ""
        print(f"  {name:22s} 2024 {100*out[0][0]:+.2f}±{100*out[0][1]:.2f} | 2025 {100*out[1][0]:+.2f}±{100*out[1][1]:.2f} | 合并 {100*e:+.2f}±{100*se:.2f} (z {e/se:+.2f}) | 年交互 z {z_int:+.2f}{ni}")
    gp = fn(R["prod"])
    for f in ("2024", "2025", None):
        gg = gp if f is None else gp[gp.fold_Y == f]
        r, e = resid(gg); n = len(e); se = np.sqrt((e ** 2).sum() * n / (n - 1))
        dec = (gg.fp_up + gg.fp_down + gg.fp_both).sum()
        print(f"  生产格水平 {f or '合并'}: 首次穿越率 {r:.4f} ± {se:.4f}(按股)  定向 bar {int(dec)}  按 bar 二项 SE {np.sqrt(r*(1-r)/dec):.4f}  设计效应 {(se/np.sqrt(r*(1-r)/dec))**2:.1f}")
