"""副产品核对：各信号全期合并（2022H1–2025H2）的领先与偶然波动，判断是否过最低线（有同日对照 + 幅度中位 CI 不跨 0；方向只跑了 k=5，不够 k=4~6 三档）。"""
import importlib.util, numpy as np, pandas as pd
spec = importlib.util.spec_from_file_location("sig", "02-signals.py"); sig = importlib.util.module_from_spec(spec); spec.loader.exec_module(sig)
R = pd.read_parquet("02-signals-rows.parquet")
R["all"] = "全期"
rows = []
for s in sig.SIGNALS:
    S = R[R[f"s_{s}"]]
    for m, (col, vcol, how) in sig.METRICS.items():
        if m not in ("方向40日", "幅度40日"):
            continue
        g = S[S[f"x_{m}"].notna()]
        x = g[f"x_{m}"].to_numpy(dtype=float); sym = g["sym"].astype(str).to_numpy()
        if how == "mean":
            est, se = x.mean(), sig.twoway_se(x, sym, g["week"].to_numpy())
        else:
            est, se = float(np.median(x)), sig.boot_median_se(x, sym, reps=200)
        per = S.groupby("per")[f"x_{m}"].agg("mean" if how == "mean" else "median")
        rows.append({"信号": s, "指标": m, "全期领先": round(est, 4), "偶然波动": round(se, 4), "倍数": round(est / se, 1),
                     "同号半年数": f"{int((np.sign(per) == np.sign(est)).sum())}/{len(per)}", "买点数": len(x)})
T = pd.DataFrame(rows); pd.set_option("display.width", 200); print(T.to_string(index=False)); T.to_csv("02-pooled.csv", index=False)
