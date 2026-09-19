"""v6 汇总：选候选与开窗前门用不用同一把尺子（R0 / R1 / R2 / R3 / 现行 validate），Q 口径，按曲面分开报。

四个 R 臂写入门统一为全式：两段合并（每段方差 + τ̂²）单侧 95% 下界 > 0 且往后段点估计 ≥ −δ。
裁决口径在看数之前写死在 verdict() 里：
  1. 支配：X 支配 Y = 三档噪声 × 10 个主曲面列上，配对差 X−Y 都 ≥ −2·MC SE，且工作点即最优时开窗率 X−Y ≤ +2·MC SE，
     并且至少有一处严格占优（某列配对差 > +2·MC SE，或工作点即最优时开窗率显著更低）。
  2. 无支配：N1 下 10 个主曲面列里 R2−R1 配对差点估计的最小值 ≥ −0.2 → 取 R2，否则 R1。
  3. R3 只有同时支配 R1 与 R2 才取。
「松侧平台」是新曲面形状的敏感性版本，不进裁决，单独列。

用法：uv run python report6.py --tag v6
"""
import argparse

import numpy as np
import pandas as pd

from report2 import load
from sim import AT, REF_FLAT

SURF = {"flat": "全平", "mono": "单调", "plateau": "宽平台", "peak": "窄尖峰", "relax": "放松更好",
        "relaxp": "松侧平台", "theta0opt": "工作点即最优"}
MAIN = ["全平", "单调·小", "单调·大", "宽平台·小", "宽平台·大", "窄尖峰·小", "窄尖峰·大", "放松更好·小", "放松更好·大",
        "工作点即最优"]
SENS = ["松侧平台·小", "松侧平台·大"]
ARMS = [("R0", "R0 d̄ 取最大、无前门"), ("R1", "R1 d̄ 取最大 + 选中格 ρ·d̄>δ"), ("R2", "R2 ρ·d̄ 取最大 + 该值>δ"),
        ("R3", "R3 ρ·d̄>δ 的格里 d̄ 取最大"), ("naive+v", "现行 validate")]
PAIRS = [("R2", "R1"), ("R3", "R1"), ("R3", "R2"), ("R2", "naive+v"), ("R1", "naive+v"), ("R0", "naive+v")]
NOISES = ("N0", "N1", "N2")
RATIO = AT["cell_mass"] / AT["cell_mass"][REF_FLAT]


def col_of(r):
    if r.surface in ("flat", "theta0opt"):
        return SURF[r.surface]
    return SURF[r.surface] + ("·小" if r.A <= 2 else "·大")


def wide(df, value):
    """(noise, col, sid, rep) × proc 的宽表，取 Q 口径。"""
    return df.pivot_table(index=["noise", "col", "A", "sid", "rep"], columns="proc", values=value, aggfunc="first", observed=True)


def mse(x):
    x = np.asarray(x, float)
    return x.mean(), x.std(ddof=1) / np.sqrt(len(x))


def tbl_gain(G, noise, cols):
    L = ["| 曲面 | " + " | ".join(n for _, n in ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for c in cols:
        g = G.loc[(noise, c)]
        L.append(f"| {c} | " + " | ".join("{:+.2f}±{:.2f}".format(*mse(g[p])) for p, _ in ARMS) + " |")
    return "\n".join(L)


def tbl_rates(G, CELL, OPEN, noise, cols, dl=2.0):
    L = ["| 曲面 | " + " | ".join(f"{p}：差出δ / 写入 / 开窗" for p, _ in ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for c in cols:
        g, ce, op = G.loc[(noise, c)], CELL.loc[(noise, c)], OPEN.loc[(noise, c)]
        cells = []
        for p, _ in ARMS:
            o = 1.0 if p == "naive+v" else op[p].mean()
            cells.append(f"{(g[p] < -dl).mean():.1%} / {(ce[p] != REF_FLAT).mean():.0%} / {o:.0%}")
        L.append(f"| {c} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def tbl_ratio(CELL, OPEN, noise, cols):
    """选中格买点数 ÷ 工作点（中位）：送去确认的候选（开窗的 rep）/ 最终写入的格（写入的 rep）。"""
    L = ["| 曲面 | oracle | " + " | ".join(f"{p}：候选(开窗时) / 写入时" for p, _ in ARMS) + " |", "|---|---|" + "---|" * len(ARMS)]
    for c in cols:
        ce, op = CELL.loc[(noise, c)], OPEN.loc[(noise, c)]
        cells = []
        for p, _ in ARMS:
            cand = ce["naive"] if p == "naive+v" else ce[p + "_c"]
            o = np.ones(len(ce), bool) if p == "naive+v" else (op[p] == 1).to_numpy()
            w = (ce[p] != REF_FLAT).to_numpy()
            a = np.median(RATIO[cand[o].astype(int)]) if o.any() else np.nan
            b = np.median(RATIO[ce[p][w].astype(int)]) if w.any() else np.nan
            cells.append(f"{a:.2f} / {b:.2f}")
        L.append(f"| {c} | {np.median(RATIO[ce['oracle'].astype(int)]):.2f} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def tbl_pairs(G, cols, pairs, fmt="{:+.2f}±{:.2f}"):
    L = ["| 对比 | 噪声 | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    for a, b in pairs:
        for n in NOISES:
            L.append(f"| {a} − {b} | {n} | " + " | ".join(fmt.format(*mse(G.loc[(n, c)][a] - G.loc[(n, c)][b])) for c in cols) + " |")
    return "\n".join(L)


def tbl_decomp(G, CELL, OPEN, noise, cols):
    """R2 − R1 的来源拆解：R1 空转而有别的格过线（R3 能救回的那部分轮次）/ 两臂都开窗但候选不同。贡献 = 该部分配对差之和 ÷ 总轮次。"""
    L = ["| 曲面 | R1 空转而有别的格过线：占比 / 对 R2−R1 的贡献 | 两臂都开窗但候选不同：占比 / 贡献 |", "|---|---|---|"]
    for c in cols:
        g, ce, op = G.loc[(noise, c)], CELL.loc[(noise, c)], OPEN.loc[(noise, c)]
        d = (g.R2 - g.R1).to_numpy()
        resc = ((op.R1 == 0) & (op.R2 == 1)).to_numpy()
        both = ((op.R1 == 1) & (ce.R2_c != ce.R1_c)).to_numpy()
        L.append(f"| {c} | {resc.mean():.1%} / {d[resc].sum() / len(d):+.2f} | {both.mean():.1%} / {d[both].sum() / len(d):+.2f} |")
    return "\n".join(L)


def dominates(G, OPEN, x, y, noises=None):
    """按文件头口径 1 判 x 是否支配 y；返回 (是否支配, 不满足的条目, 严格占优的条目)。"""
    bad, strict = [], []
    for n in noises or NOISES:
        for c in MAIN:
            m, s = mse(G.loc[(n, c)][x] - G.loc[(n, c)][y])
            if m < -2 * s:
                bad.append(f"{n} {c} 增益 {m:+.2f}±{s:.2f}")
            if m > 2 * s:
                strict.append(f"{n} {c} 增益 {m:+.2f}±{s:.2f}")
        o = OPEN.loc[(n, "工作点即最优")]
        m, s = mse(o[x] - o[y])
        if m > 2 * s:
            bad.append(f"{n} 工作点即最优开窗率 {m:+.1%}±{s:.1%}")
        if m < -2 * s:
            strict.append(f"{n} 工作点即最优开窗率 {m:+.1%}±{s:.1%}")
    return (not bad) and bool(strict), bad, strict


def verdict(G, OPEN):
    L = []
    dom = {}
    for x, y in [("R1", "R2"), ("R2", "R1"), ("R3", "R1"), ("R1", "R3"), ("R3", "R2"), ("R2", "R3"), ("R1", "R0"), ("R0", "R1")]:
        ok, bad, strict = dominates(G, OPEN, x, y)
        dom[x, y] = ok
        L.append(f"- {x} 支配 {y}？**{'是' if ok else '否'}**。不满足：{'；'.join(bad) if bad else '无'}。严格占优：{'；'.join(strict) if strict else '无'}。")
    d = {c: mse(G.loc[("N1", c)]["R2"] - G.loc[("N1", c)]["R1"]) for c in MAIN}
    cw = min(d, key=lambda c: d[c][0])
    L.append(f"- 口径 2：N1 下 R2−R1 最差落差在「{cw}」= {d[cw][0]:+.2f}±{d[cw][1]:.2f}（阈值 −0.20）。")
    perA = G.loc["N1"].reset_index()
    perA = perA[perA.col.isin(MAIN)].assign(d=lambda t: t.R2 - t.R1).groupby(["col", "A"], observed=True).d.agg(["mean", "sem"])
    k = perA["mean"].idxmin()
    L.append(f"- 敏感性（不进裁决）：按单个幅度拆开，N1 最差在 {k[0]} A={k[1]}：{perA.loc[k, 'mean']:+.2f}±{perA.loc[k, 'sem']:.2f}；"
             + "；".join(f"{c} {mse(G.loc[('N1', c)]['R2'] - G.loc[('N1', c)]['R1'])[0]:+.2f}" for c in SENS) + "。")
    if dom["R3", "R1"] and dom["R3", "R2"]:
        pick = "R3（口径 3：同时支配 R1 与 R2）"
    elif dom["R1", "R2"]:
        pick = "R1（口径 1：R1 支配 R2）"
    elif dom["R2", "R1"]:
        pick = "R2（口径 1：R2 支配 R1）"
    else:
        pick = "R2（口径 2：最差落差不超过 0.2 点）" if d[cw][0] >= -0.2 else "R1（口径 2：R2 最差落差超过 0.2 点）"
    L.append(f"- **机械裁决：取 {pick}**")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v6")
    a = ap.parse_args()
    df = load(a.tag, 2)
    df = df[df.obj == "Q"].copy()
    global NOISES
    NOISES = tuple(n for n in NOISES if n in set(df.noise))          # 允许只跑了部分噪声档的 parquet（如 --only N1 的加跑）
    cmap = {(r.surface, r.A): col_of(r) for r in df[["surface", "A"]].drop_duplicates().itertuples()}
    df["col"] = [cmap[k] for k in zip(df.surface, df.A)]
    G, CELL, OPEN = (wide(df, v).sort_index() for v in ("G_F", "cell", "extra"))
    OPEN["naive+v"] = 1.0
    n = G.groupby(level=["noise", "col"]).size()
    print("每列 rep 数：" + ", ".join(f"{c}={n.loc[('N1', c)]}" for c in MAIN + SENS))
    for ns in NOISES:
        print(f"\n## Q {ns}：部署年增益 ± MC SE\n"); print(tbl_gain(G, ns, MAIN + SENS))
        print(f"\n## Q {ns}：P(部署年差出 δ) / 写入率 / 开窗率\n"); print(tbl_rates(G, CELL, OPEN, ns, MAIN + SENS))
        print(f"\n## Q {ns}：选中格买点数 ÷ 工作点（中位）\n"); print(tbl_ratio(CELL, OPEN, ns, MAIN + SENS))
    print("\n## 同一 rep 配对差：部署年增益 ± MC SE\n"); print(tbl_pairs(G, MAIN + SENS, PAIRS))
    print("\n## 同一 rep 配对差：开窗率\n"); print(tbl_pairs(OPEN, MAIN + SENS, [("R2", "R1")], fmt="{:+.1%}±{:.1%}"))
    print("\n## 排序本身（ρ·d̄ 排序 − d̄ 取最大）在三个层次上的配对差\n")
    print("R2_c − R0_c = 候选格不过任何门；V2_mand − A_mand = 只接写入门（无前门，合并 SE 不含 τ̂²）；R2 − R1 = 前门 + 写入门全式\n")
    print(tbl_pairs(G, MAIN + SENS, [("R2_c", "R0_c"), ("V2_mand", "A_mand"), ("R2", "R1")]))
    for ns in NOISES:
        print(f"\n## Q {ns}：R2 − R1 的来源拆解\n"); print(tbl_decomp(G, CELL, OPEN, ns, MAIN + SENS))
    print("\n## 按预先口径的机械裁决\n"); print(verdict(G, OPEN))


if __name__ == "__main__":
    main()
