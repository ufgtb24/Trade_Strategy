"""E1:长表行数 vs 独立买点单位数。label 随机源 = (symbol, buy_date),同一买点在多个检测组合/where 档里重复出现。
只读 symbol/buy_date/fold_Y/fp_* 四态列,逐分片处理(分片按股划分,股票不跨片——脚本内核验)。"""
import glob, resource
import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
LT = ROOT / "outputs/tune_gates/bb_v1/main/longtable"
rows = 0; units = []; seen_sym = set(); dup_sym = 0
for sp in sorted(glob.glob(str(LT / "part-*.parquet"))):
    df = pd.read_parquet(sp, columns=["symbol", "buy_date", "fold_Y", "fp_up", "fp_down", "fp_both", "fp_none"])
    rows += len(df)
    syms = set(df["symbol"].astype(str).unique()); dup_sym += len(syms & seen_sym); seen_sym |= syms
    u = df.drop_duplicates(["symbol", "buy_date"]).copy()
    u["symbol"] = u["symbol"].astype(str); u["fold_Y"] = u["fold_Y"].astype(str)
    units.append(u)
U = pd.concat(units, ignore_index=True)
print(f"rows={rows}  distinct (symbol,buy_date) units={len(U)}  rows/unit={rows/len(U):.0f}  symbols={U.symbol.nunique()}  symbols跨片重复={dup_sym}")
for f, g in U.groupby("fold_Y"):
    den = g.fp_up + g.fp_down + g.fp_both
    print(f"fold {f}: units={len(g)} symbols={g.symbol.nunique()} none占比={g.fp_none.mean():.3f} FP(全体独立买点)={g.fp_up.sum()/den.sum():.4f} 每股买点均值={len(g)/g.symbol.nunique():.2f}")
# 时间:40 交易日 ≈ 58 日历天的桶
U["bd"] = pd.to_datetime(U["buy_date"])
span = round(40 * 365 / 252)
U["bucket"] = (U["bd"] - pd.Timestamp("2024-01-01")).dt.days // span
print("58 日历天桶数:", U["bucket"].nunique(), " 每桶独立买点:", U.groupby("bucket").size().describe()[["min","50%","max"]].to_dict())
U[["symbol", "buy_date", "fold_Y", "fp_up", "fp_down", "fp_both", "fp_none", "bucket"]].to_parquet(Path(__file__).with_name("e1_units.parquet"))
print(f"peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB")
