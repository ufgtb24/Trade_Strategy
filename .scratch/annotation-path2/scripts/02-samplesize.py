"""训练段用多长 —— 样本多带来多少好处：各种训练段的可用买点日、股票数，以及分辨门槛的相对倍数。只读缓存。
门槛倍数（相对「全部」）：
  等权合并：门槛 ∝ 1/√(有效样本)，有效样本按「池内股票日 × 不同股票数」两种口径各给一个（股票数口径更接近扎堆的 pattern）。
  v3 近期加权（一年前减半）：有效年数 = (∫w)² / ∫w²，w = 2^(−年龄)；门槛 ∝ 1/√(有效年数)。"""
import numpy as np, pandas as pd
C = pd.read_parquet("02-cache.parquet", columns=["date", "sym", "pool", "d40"])
C = C[C["pool"] & (C["d40"] != -9)]
C["date"] = pd.to_datetime(C["date"])
end = C["date"].max()
def ess_years(T):
    a = (1 - 2 ** (-T)) / np.log(2); b = (1 - 2 ** (-2 * T)) / (2 * np.log(2)); return a * a / b
rows = []
for name, start in [("全部（2022-01 起）", "2022-01-01"), ("去掉 2022（2023-01 起）", "2023-01-01"),
                    ("只用 2024–2025（2024-01 起）", "2024-01-01"), ("只用 2025", "2025-01-01"), ("只用 2025 下半年", "2025-07-01")]:
    S = C[C["date"] >= start]
    yrs = (end - pd.Timestamp(start)).days / 365.25
    rows.append({"训练段": name, "决策日跨度(年)": round(yrs, 2), "池内有标签股票日": len(S), "不同股票数": S["sym"].nunique(),
                 "交易日": S["date"].nunique(), "v3有效年数": round(ess_years(yrs), 2)})
T = pd.DataFrame(rows)
base = T.iloc[0]
T["门槛倍数·按股票日"] = np.sqrt(base["池内有标签股票日"] / T["池内有标签股票日"]).round(2)
T["门槛倍数·按年数"] = np.sqrt(base["决策日跨度(年)"] / T["决策日跨度(年)"]).round(2)
T["门槛倍数·v3加权"] = np.sqrt(base["v3有效年数"] / T["v3有效年数"]).round(2)
print("有标签的最后决策日：", end.date())
pd.set_option("display.width", 250); print(T.to_string(index=False))
T.to_csv("02-samplesize.csv", index=False)
