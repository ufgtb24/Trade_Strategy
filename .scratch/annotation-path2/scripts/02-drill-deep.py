"""探查：2025 下半年「离 120 日高点跌一半以上」为什么明显落后同日对照。只读 02-signals-rows.parquet 与 02-cache.parquet。"""
import numpy as np, pandas as pd
R = pd.read_parquet("02-signals-rows.parquet")
S = R[R["s_离120日高点跌一半以上"]].copy()
S["month"] = S["date"].dt.to_period("Q").astype(str)
for m in ["x_方向40日", "x_方向10日"]:
    g = S[S[m].notna()].groupby("month")[m]
    print(m); print(pd.DataFrame({"lead": g.mean().round(3), "n": g.size(), "stocks": S[S[m].notna()].groupby("month")["sym"].nunique()}).T.to_string())
# 按 2025H2 内月份
S2 = S[S["date"] >= "2025-07-01"].copy(); S2["mon"] = S2["date"].dt.month
print(S2.groupby("mon")[["x_方向40日", "x_方向10日"]].agg(["mean", "size"]).round(3))
# 集中度：2025H2 落后来自少数股票吗
g = S2[S2["x_方向10日"].notna()].groupby("sym", observed=True)["x_方向10日"].agg(["mean", "size"]).sort_values("size", ascending=False)
print("2025H2 股票数", len(g), "前 20 只占买点比例", g["size"].head(20).sum() / g["size"].sum())
print("按股票等权的平均领先", g["mean"].mean().round(3))
# 与之前一年是同一批股票吗：之前（2024H2-2025H1）也在这一信号里的股票 vs 新进的
prev = set(S[(S["date"] >= "2024-07-01") & (S["date"] < "2025-07-01")]["sym"].astype(str))
S2["old"] = S2["sym"].astype(str).isin(prev)
print(S2.groupby("old")[["x_方向40日", "x_方向10日"]].agg(["mean", "size"]).round(3))
