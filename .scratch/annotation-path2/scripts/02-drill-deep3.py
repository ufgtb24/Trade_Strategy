"""探查（续二）：2025 下半年深跌股的落后，是不是集中在新上市的股票（文献：2024–2025 超小盘 IPO 与上市后数周到数月的拉高出货）。
新股 = 本地数据第一天距买点不足 2 年（只用买点当天及以前的信息）。只读缓存。"""
import numpy as np, pandas as pd
C = pd.read_parquet("02-cache.parquet", columns=["date", "sym"])
C["date"] = pd.to_datetime(C["date"]); C["sym"] = C["sym"].astype(str)
first = C.groupby("sym")["date"].min().rename("first")
R = pd.read_parquet("02-signals-rows.parquet"); R["sym"] = R["sym"].astype(str)
R = R.merge(first, left_on="sym", right_index=True)
R["new"] = (R["date"] - R["first"]).dt.days < 730
R["new"] &= R["first"] > pd.Timestamp("2021-11-15")      # 数据开头就有的不算新股
for sig in ["离120日高点跌一半以上", "放量大阳", "跳空高开"]:
    S = R[R[f"s_{sig}"]]
    t = S.groupby(["per", "new"])[["x_方向40日", "x_方向10日"]].agg(["mean", "size"]).round(3)
    print("==", sig); print(t.unstack("new").to_string())
