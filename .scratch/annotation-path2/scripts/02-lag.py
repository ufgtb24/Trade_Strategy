"""训练段用多长 —— 补充：两个半年隔得越远，信号领先的「偏离常态」越不像吗？以及各信号不同半年之间本来就会差多少。
只读 02-signals-effects.csv。偏离 = 该半年领先 − 除这两个半年以外其余半年的平均，再除以该半年的偶然波动。
基准：同样口径在「完全没有时段差异」的假设下会有多少相关 —— 用把各半年领先换成「全期平均 + 按偶然波动抽的随机数」模拟 2000 次。"""
import numpy as np, pandas as pd
E = pd.read_csv("02-signals-effects.csv")
PERS = ["2022H1", "2022H2", "2023H1", "2023H2", "2024H1", "2024H2", "2025H1", "2025H2"]
rng = np.random.default_rng(1)

def lag_corr(V, SE, excl_last=False):
    out = {}
    for lag in range(1, 7):
        a, b = [], []
        for v, se in zip(V, SE):
            for i in range(len(PERS) - lag):
                j = i + lag
                if excl_last and j == len(PERS) - 1:
                    continue
                if np.isfinite(v[i]) and np.isfinite(v[j]):
                    rest = np.delete(v, [i, j]); mu = np.nanmean(rest)
                    a.append((v[i] - mu) / se[i]); b.append((v[j] - mu) / se[j])
        out[lag] = np.corrcoef(a, b)[0, 1] if len(a) > 5 else np.nan
    return out

V, SE, keys = [], [], []
for (s, m), g in E.groupby(["信号", "指标"]):
    g = g.set_index("时段").reindex(PERS)
    V.append(g["领先"].to_numpy()); SE.append(g["偶然波动"].to_numpy()); keys.append((s, m))
obs = lag_corr(V, SE)
obs2 = lag_corr(V, SE, excl_last=True)
null = []
for _ in range(300):
    Vn = []
    for v, se in zip(V, SE):
        mu = np.nansum(v / se**2) / np.nansum(1 / se**2)
        vn = mu + rng.standard_normal(len(v)) * se
        vn[~np.isfinite(v)] = np.nan
        Vn.append(vn)
    null.append(lag_corr(Vn, SE))
null = pd.DataFrame(null)
print(pd.DataFrame({"实测(含2025H2)": obs, "实测(不含2025H2)": obs2, "无时段差异时均值": null.mean(), "无时段差异时95%上沿": null.quantile(0.95)}).round(3).to_string())

# 不同半年之间「本来就会差多少」：实测分散 vs 偶然波动能解释的分散
rows = []
for (s, m), v, se in zip(keys, V, SE):
    ok = np.isfinite(v)
    vv, ss = v[ok], se[ok]
    obs_sd = np.std(vv, ddof=1)
    tau = np.sqrt(max(0.0, np.var(vv, ddof=1) - np.mean(ss**2)))
    vv7, ss7 = vv[:-1], ss[:-1]
    tau7 = np.sqrt(max(0.0, np.var(vv7, ddof=1) - np.mean(ss7**2)))
    rows.append({"信号": s, "指标": m, "各半年平均领先": vv.mean(), "实测分散": obs_sd, "典型偶然波动": np.sqrt(np.mean(ss**2)),
                 "真实时段差异": tau, "真实时段差异(不含2025H2)": tau7,
                 "2025H2偏离(倍偶然波动)": (vv[-1] - vv[:-1].mean()) / np.sqrt(ss[-1]**2 + np.var(vv[:-1], ddof=1) / len(vv[:-1])) if len(vv) == 8 else np.nan})
T = pd.DataFrame(rows)
T.to_csv("02-lag-tau.csv", index=False)
pd.set_option("display.width", 220)
for m in ["方向40日", "幅度40日", "方向10日", "收益10日"]:
    print("\n==", m); print(T[T["指标"] == m].drop(columns="指标").round(3).to_string(index=False))
