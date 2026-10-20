"""11 同日对照配对票 · 试过又放弃的做法：近邻 + 局部线性修正（看过第一轮结果后试的，原型，未进推荐）。

均值型尺子用邻域内最小二乘斜率、中位数型尺子用 L1 斜率，把每个对照成员的结果平移到买点自己的波动位置再比。
结论：尾部有的类变好、有的类变坏（越修越偏），无偏好随机买点在两种止损止盈规则的典型一笔上反而出现 0.2–0.7 个百分点的假领先
（结果分布是「止损处一堆、止盈处一堆」，平移破坏了这种形状），弃用。输出见 11-ll-proto_out.txt。
原样保存，路径常量指向会话临时目录。
"""
import importlib.util, sys, time
import numpy as np, pandas as pd
H = "/home/yu/PycharmProjects/Trade_Strategy/.scratch/selection-pattern/scripts/"
def load(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); sys.modules[n] = m; s.loader.exec_module(m); return m
core = load("core11", H + "11-core.py"); bias = load("bias11", H + "11-bias.py")
P, Y, hold, mts, S = core.load_all(["M5", "K20", "K50"])
neigh = np.load(core.SCR / "build.npz")["neigh"]
C = bias.classes(P)
X = np.c_[np.log(P["M"]), np.log(np.maximum(P["Mhm"], 1e-3))]

def slopes(rows, col, kslope=100, l1=False, iters=15, ridge=1e-4):
    """每个买点在它最近 kslope 个邻居上 y ~ a + b·(x − x_i) 的斜率 b（2 维）。"""
    nb = neigh[rows, :kslope]
    xs = X[nb] - X[rows][:, None, :]          # n×k×2
    ys = Y[col][nb]                            # n×k
    A = np.concatenate([np.ones(xs.shape[:2] + (1,)), xs], 2)   # n×k×3
    w = np.ones(ys.shape)
    for it in range(iters if l1 else 1):
        Aw = A * w[..., None]
        G = np.einsum("nki,nkj->nij", Aw, A) + ridge * np.eye(3)[None]
        g = np.einsum("nki,nk->ni", Aw, ys)
        beta = np.linalg.solve(G, g[..., None])[..., 0]
        if l1:
            res = np.abs(ys - np.einsum("nki,ni->nk", A, beta))
            w = 1.0 / np.maximum(res, 1e-4)
    return beta   # [a(在 x_i 处的预测), b1, b2]

def lead_ll(rows, K=20, kslope=100, chunk=20000):
    out = {}
    for m in core.METRICS:
        col = core.base_col(m)
        l1 = m in core.MED_METRICS
        vals, ctrl = [], []
        for s in range(0, len(rows), chunk):
            r = rows[s:s + chunk]
            b = slopes(r, col, kslope, l1=l1)[:, 1:]
            nb = neigh[r, :K]
            adj = Y[col][nb] + np.einsum("nkj,nj->nk", X[r][:, None, :] - X[nb], b)
            if l1:
                vals.append(adj.ravel())
            else:
                ctrl.append(adj.mean(1))
        hit = Y[col][rows]
        if l1:
            v = np.concatenate(vals)
            out[m] = float(np.median(hit) - np.median(v))
        else:
            out[m] = float(hit.mean() - np.concatenate(ctrl).mean())
    return out

rng = np.random.default_rng(0)
res = []
for name in ["rand", "M_top2", "M_top10", "H_top10", "Hhi_Mmid", "Mhi_Hmid", "H_bot10", "M_bot2"]:
    rows = np.flatnonzero(C[name])
    if name == "rand":
        rows = rng.choice(rows, 60000, replace=False); rows.sort()
    t = time.time()
    for K in (20, 50):
        r = lead_ll(rows, K=K)
        res.append({"cls": name, "scheme": f"K{K}LL", **r})
        r0 = core.leads(mts[f"K{K}"], S, rows)
        res.append({"cls": name, "scheme": f"K{K}", **r0})
    res.append({"cls": name, "scheme": "M5", **core.leads(mts["M5"], S, rows)})
    print(name, len(rows), f"{time.time() - t:.0f}s", flush=True)
df = pd.DataFrame(res)
pd.set_option("display.width", 250)
for m in ["dir", "mag", "R1_med", "R3_med", "R3_mean", "R4_med", "R5_med", "R5_mean", "R6_med", "R6_mean"]:
    p = df.pivot_table(index="cls", columns="scheme", values=m)[["M5", "K20", "K20LL", "K50", "K50LL"]]
    print("==", m); print((p * (1 if m == "dir" else 100)).round(3).to_string())
df.to_csv(core.SCR / "proto/ll_proto.csv", index=False)
