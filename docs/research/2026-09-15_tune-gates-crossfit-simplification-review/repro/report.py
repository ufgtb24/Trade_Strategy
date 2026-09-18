"""把 results/rows_<tag>.parquet 汇总成 simulator.md 用的 markdown 表。

用法：uv run python report.py --tag main
"""
import argparse
import os

import numpy as np
import pandas as pd

from sim import DELTA, REF_FLAT, scenarios

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = ["keep", "random", "naive", "cur", "cur_gated", "one_se", "cf_draft", "cf_draft_g", "cf_strict", "cf_strict_g",
        "eb_stock", "eb_2way", "oracle"]
NAMES = {"keep": "维持现行参数", "random": "随机挑", "naive": "朴素取最大", "cur": "现行规则",
         "cur_gated": "现行规则+校正后>0才动", "one_se": "一倍标准误", "cf_draft": "草案交叉拟合",
         "cf_draft_g": "草案交叉拟合+估计>0才动", "cf_strict": "双向剔除交叉拟合", "cf_strict_g": "双向剔除+估计>0才动",
         "eb_stock": "平滑先验后验(按股噪声)", "eb_2way": "平滑先验后验(+时段噪声)", "oracle": "oracle"}


def band(r):
    if r.surface == "flat":
        return "全平"
    return "小效应(1-2点)" if r.A <= 2 else "大效应(4-8点)"


def load(tag, T):
    df = pd.read_parquet(os.path.join(HERE, "results", f"rows_{tag}.parquet"))
    meta = pd.DataFrame(scenarios(T=T))
    meta["band"] = meta.apply(band, axis=1)
    df = df.merge(meta, on="sid")
    df["proc"] = df.proc.astype(str); df["obj"] = df.obj.astype(str)
    df["dl"] = df.obj.map(DELTA)
    orc = df[df.proc == "oracle"][["sid", "rep", "obj", "G_S"]].rename(columns={"G_S": "O_S"})
    return df.merge(orc, on=["sid", "rep", "obj"])


def fmt(x, nd=2):
    return "—" if not np.isfinite(x) else f"{x:+.{nd}f}" if nd else f"{x:.0%}"


def tbl_perf(df, obj, noise, procs=MAIN):
    d = df[(df.obj == obj) & (df.noise == noise)]
    bands = ["全平", "小效应(1-2点)", "大效应(4-8点)"]
    L = ["| 流程 | " + " | ".join(f"{b} 平稳增益 / 部署年增益 / 差出δ/2概率 / 不动率" for b in bands) + " |",
         "|---|" + "---|" * len(bands)]
    for p in procs:
        cells = []
        for b in bands:
            g = d[(d.proc == p) & (d.band == b)]
            if g.empty:
                cells.append("—"); continue
            cells.append(f"{g.G_S.mean():+.2f} / {g.G_F.mean():+.2f} / {(g.G_S < -g.dl / 2).mean():.0%} / "
                         f"{(g.cell == REF_FLAT).mean():.0%}")
        L.append(f"| {NAMES.get(p, p)} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def tbl_surface(df, obj, noise, bands=("小效应(1-2点)",), procs=MAIN):
    d = df[(df.obj == obj) & (df.noise == noise) & (df.band.isin(bands) | (df.surface == "flat"))]
    surfs = ["flat", "mono", "plateau", "peak", "theta0opt"]
    L = ["| 流程 | " + " | ".join(surfs) + " |", "|---|" + "---|" * len(surfs)]
    for p in procs:
        row = []
        for s in surfs:
            g = d[(d.proc == p) & (d.surface == s)]
            row.append(f"{g.G_S.mean():+.2f}" if len(g) else "—")
        L.append(f"| {NAMES.get(p, p)} | " + " | ".join(row) + " |")
    return "\n".join(L)


def tbl_honesty(df, obj, procs):
    L = ["| 报数 | " + " | ".join(f"{n} 偏差 / RMSE / 与部署年真值相关" for n in ("N0", "N1", "N2")) + " |",
         "|---|---|---|---|"]
    for p in procs:
        row = []
        for n in ("N0", "N1", "N2"):
            g = df[(df.obj == obj) & (df.noise == n) & (df.proc == p)]
            ok = np.isfinite(g.rep_val)
            g = g[ok]
            if g.empty:
                row.append("—"); continue
            e = g.rep_val - g.G_F
            cr = np.corrcoef(g.rep_val, g.G_F)[0, 1] if g.rep_val.std() > 1e-9 else np.nan
            row.append(f"{e.mean():+.2f} / {np.sqrt((e ** 2).mean()):.2f} / {cr:+.2f}")
        L.append(f"| {NAMES.get(p, p)} | " + " | ".join(row) + " |")
    return "\n".join(L)


def tbl_cv_leak(df, obj):
    kinds = [("draft", "草案(年×股票折,其余全用)"), ("stock", "只按股票折"), ("loyo", "只留一年"), ("strict", "双向剔除")]
    L = ["| 交叉拟合块结构 | 规则 | N0 全平偏差 | N1 全平偏差 | N2 全平偏差 | N1 全场景偏差 | N2 全场景偏差 |",
         "|---|---|---|---|---|---|---|"]
    for k, kn in kinds:
        for r, rn in (("pk", "峰值"), ("pl", "平台"), ("", "两规则取估计更高者")):
            p = f"cf_{k}_{r}" if r else f"cf_{k}"
            vals = []
            for n, flat in (("N0", True), ("N1", True), ("N2", True), ("N1", False), ("N2", False)):
                g = df[(df.obj == obj) & (df.noise == n) & (df.proc == p)]
                if flat:
                    g = g[g.surface == "flat"]
                e = (g.rep_val - g.G_F).dropna()
                vals.append(f"{e.mean():+.2f}±{e.std() / np.sqrt(len(e)):.2f}")
            L.append(f"| {kn} | {rn} | " + " | ".join(vals) + " |")
    return "\n".join(L)


def tbl_val(df, obj, noise):
    procs = ["naive", "cur", "cur_gated", "one_se", "cf_draft", "cf_draft_g", "cf_strict_g", "eb_2way"]
    bands = ["全平", "小效应(1-2点)", "大效应(4-8点)"]
    L = ["| 流程 | " + " | ".join(f"{b} 无验证门→有验证门 平稳增益（不动率）" for b in bands) + " | 验证门后报数偏差 |",
         "|---|" + "---|" * (len(bands) + 1)]
    d = df[(df.obj == obj) & (df.noise == noise)]
    for p in procs:
        row = []
        for b in bands:
            g0 = d[(d.proc == p) & (d.band == b)]; g1 = d[(d.proc == p + "+v") & (d.band == b)]
            row.append(f"{g0.G_S.mean():+.2f}→{g1.G_S.mean():+.2f}（{(g1.cell == REF_FLAT).mean():.0%}）")
        g1 = d[d.proc == p + "+v"]
        row.append(f"{(g1.rep_val - g1.G_F).mean():+.2f}")
        L.append(f"| {NAMES.get(p, p)} | " + " | ".join(row) + " |")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="main")
    ap.add_argument("--T", type=int, default=2)
    a = ap.parse_args()
    df = load(a.tag, a.T)
    for obj in ("Q", "U"):
        print(f"\n## 目标 {obj}\n")
        for n in ("N0", "N1", "N2"):
            print(f"\n### 选点表现 {obj} {n}\n")
            print(tbl_perf(df, obj, n))
        print(f"\n### 分曲面平稳增益 {obj} N1（全平 + 小效应）\n")
        print(tbl_surface(df, obj, "N1"))
        print(f"\n### 分曲面平稳增益 {obj} N1（大效应）\n")
        print(tbl_surface(df, obj, "N1", bands=("大效应(4-8点)",)))
        print(f"\n### 报数诚实度 {obj}（全场景合并，偏差相对部署年真值）\n")
        print(tbl_honesty(df, obj, ["naive", "cur", "cur_corr", "cur_split", "one_se", "cf_draft", "cf_stock",
                                    "cf_loyo", "cf_strict", "eb_stock", "eb_2way"]))
        print(f"\n### 交叉拟合报数偏差拆解 {obj}\n")
        print(tbl_cv_leak(df, obj))
        for n in ("N1", "N2"):
            print(f"\n### 确认窗验证门 {obj} {n}\n")
            print(tbl_val(df, obj, n))


if __name__ == "__main__":
    main()
