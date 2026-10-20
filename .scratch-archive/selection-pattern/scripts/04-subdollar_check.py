"""04 票补充：2023-12-08 这一天，幸存股里复权收盘价 <1 美元的有多少（对照外部统计：当日全美上市股 557 只低于 1 美元）。
复权价会被之后的反向拆股抬高，所以这里数出来的是「当时真实低于 1 美元的幸存股」的下限。
运行：uv run python .scratch/selection-pattern/scripts/04-subdollar_check.py
"""
import glob, os
import pandas as pd

ROOT = "/home/yu/PycharmProjects/Trade_Strategy"
DAY = pd.Timestamp("2023-12-08")
n_alive = n_lt1 = n_lt2 = 0
for p in sorted(glob.glob(os.path.join(ROOT, "datasets/pkls/*.pkl"))):
    c = pd.read_pickle(p)["close"]
    if DAY in c.index:
        n_alive += 1
        v = float(c.loc[DAY])
        n_lt1 += v < 1
        n_lt2 += v < 2
print(f"{DAY.date()} 有数据的幸存股 {n_alive}；复权收盘 <1 美元 {n_lt1}；<2 美元 {n_lt2}")
