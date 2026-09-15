"""E7:定案三改动 A(峰龄闸 60→0)/ B(确认根数 1→3)/ C(突破幅度 0.003→0.0075)在生产格上的 2³ 析因:
主效应、两两交互、三阶交互,按股去簇 SE(各格按股线性化残差的线性组合,重叠买点自动计入协方差);逐 match 计与按买点日去重两口径。"""
import glob, sys, itertools
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
PROD = {"bo.exceed_threshold": 0.003, "bo.min_relative_height": 0.2, "burst.gap_max": 8, "tb.max_rise_k": 1.5, "tb.max_span": 20, "tb.stop_confirm_bars": 1,
        "burst.count": 1, "burst.distinct_pk": 3, "burst.first_drought": 40, "burst.peak_age_max": 60, "burst.max_bar_vol_ratio": 3, "tb.max_day_drop": 0.2}
FAC = {"A": ("burst.peak_age_max", 0), "B": ("tb.stop_confirm_bars", 3), "C": ("bo.exceed_threshold", 0.0075)}
CELLS = {}
for bits in itertools.product((0, 1), repeat=3):
    c = dict(PROD)
    for on, (nm, (ax, v)) in zip(bits, FAC.items()):
        if on:
            c[ax] = v
    CELLS[bits] = c
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
        s = df.loc[m, ["symbol", "fold_Y", "buy_date"] + ST].copy(); s["symbol"] = s.symbol.astype(str); s["fold_Y"] = s.fold_Y.astype(str)
        parts[k].append(s)
R = {k: pd.concat(v, ignore_index=True) for k, v in parts.items()}
z = np.load(ROOT / "outputs/tune_gates/bb_v1/main/cells.npz")
for k in CELLS:
    assert [int(x) for x in z["count"][tuple(IDX[k])]] == [int(R[k].loc[R[k].fold_Y == f, ST].to_numpy().sum()) for f in ("2024", "2025")], k
print("自检通过:8 格 count 与 cells.npz 逐位相等")

def resid(g):
    dec = g.fp_up + g.fp_down + g.fp_both; r = g.fp_up.sum() / dec.sum()
    return r, ((g.fp_up - r * dec) / dec.sum()).groupby(g.symbol).sum()

def lincomb(coef, fold, dedup):
    est, es = 0.0, []
    for k, c in coef.items():
        g = R[k] if fold is None else R[k][R[k].fold_Y == fold]
        if dedup:
            g = g.drop_duplicates(["symbol", "fold_Y", "buy_date"] + ST)
        r, e = resid(g); est += c * r; es.append(c * e)
    tot = pd.concat(es, axis=1).fillna(0).sum(1); n = len(tot)
    return est, float(np.sqrt((tot ** 2).sum() * n / (n - 1)))

def contrast(term):
    """2³ 析因的效应系数:term 为因子名集合;效应 = 平均差(主效应)/ 交互(按 ±1 编码 /4)。"""
    coef = {}
    for bits in CELLS:
        sgn = 1
        for i, nm in enumerate(FAC):
            if nm in term:
                sgn *= (1 if bits[i] else -1)
        coef[bits] = sgn / 4
    return coef

for dedup in (False, True):
    print(f"\n== {'按买点日去重' if dedup else '逐 match 计'}(效应单位 pt;主效应 = 开 vs 关 在其余两因子四种组合上的平均差;交互 = 效应差的一半)")
    for term in (("A",), ("B",), ("C",), ("A", "B"), ("A", "C"), ("B", "C"), ("A", "B", "C")):
        out = []
        for f in ("2024", "2025", None):
            e, se = lincomb(contrast(set(term)), f, dedup)
            out.append(f"{f or '合并'} {100*e:+.2f}±{100*se:.2f} (z {e/se:+.2f})")
        print(f"  {'×'.join(term):6s} " + " | ".join(out))
