"""探查（续）：2025 下半年深跌股的落后是不是停牌 / 零成交造成的假象；以及只看「当天才进这个状态」的买点。只读缓存。"""
import numpy as np, pandas as pd
C = pd.read_parquet("02-cache.parquet", columns=["date", "sym", "dollar", "dd120", "pool", "r1"])
C["date"] = pd.to_datetime(C["date"]); C["sym"] = C["sym"].astype(str)
C["zero"] = C["dollar"] <= 0
C["half"] = C["date"].dt.year.astype(str) + np.where(C["date"].dt.month <= 6, "H1", "H2")
z = C.groupby(["sym", "half"])["zero"].sum().rename("zero_days").reset_index()
R = pd.read_parquet("02-signals-rows.parquet")
S = R[R["s_离120日高点跌一半以上"]].copy(); S["sym"] = S["sym"].astype(str)
S["half"] = S["per"]
S = S.merge(z, on=["sym", "half"], how="left")
S["has_zero"] = S["zero_days"] > 0
print("信号行里所在半年有零成交日的比例：\n", S.groupby("half")["has_zero"].mean().round(3).to_string())
s2 = S[S["half"] == "2025H2"]
print(s2.groupby("has_zero")[["x_方向40日", "x_方向10日", "x_幅度40日"]].agg(["mean", "median", "size"]).round(3).T)
# 首次进入状态（前 20 个交易日都不在该状态）的买点
C = C.sort_values(["sym", "date"])
C["deep"] = C["dd120"] <= -0.5
C["prev_deep"] = C.groupby("sym")["deep"].transform(lambda s: s.shift(1).rolling(20, min_periods=1).max()).fillna(0).astype(bool)
first = C[C["deep"] & ~C["prev_deep"]][["sym", "date"]]
F = S.merge(first, on=["sym", "date"], how="inner")
print("\n只取首次进入深跌状态的买点：")
print(F.groupby("half")[["x_方向40日", "x_方向10日"]].agg(["mean", "size"]).round(3).to_string())
