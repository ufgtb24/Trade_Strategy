"""02 分辨力研究 · 汇总：把 02-sim 的逐次结果整理成研究文件用的表和图。

偶然波动 = 假 pattern 的领先在多次重复里的标准差（先减去同一配置的平均值：换股时保留了波动水平，
平均值里有「偏好高波动」白得的偏移，那是系统偏差、不是偶然波动，另表单列）。
真实长相的假 pattern 每次重复的买点数随所抽时段变化，所以按买点数分组算波动，再在对数坐标上
用二次曲线把「买点数 → 偶然波动」连成平滑曲线；表里超出模拟覆盖范围的格子标 *（外推）。
「分辨得出」= 真实领先 ≥ 2.8 倍偶然波动：这时有八成把握观察到的领先超过 2 倍偶然波动（单次、事先写好的检查）。

输出：scripts/02-report-tables.txt、research/02-resolution-*.png
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent / "research"
MULT = 2.8
FAMILIES = {
    "bottom_burst 长相": lambda d: (d.kind == "real") & (d.app == "bottom_burst") & (d.mapping == "vol"),
    "bb_v1 长相": lambda d: (d.kind == "real") & (d.app == "bb_v1") & (d.mapping == "vol"),
    "连续 5 天一段": lambda d: d.kind == "runs",
    "完全独立": lambda d: d.kind == "indep",
}


def load():
    frames = []
    for f in sorted(HERE.glob("02-sim-H*_k*.csv.gz")):
        if "quick" in f.name:
            continue
        H, k = re.match(r"02-sim-H(\d+)_k([\d.]+)\.csv\.gz", f.name).groups()
        d = pd.read_csv(f)
        d["H"], d["k"] = int(H), float(k)
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    if "tag" not in d:
        d["tag"] = np.nan
    for c in ("app", "mapping"):
        d[c] = d[c].fillna("")
    d["dev"] = d["delta"] - d.groupby(["H", "k", "cid"])["delta"].transform("mean")
    d["dev_amp"] = d["amp"] - d.groupby(["H", "k", "cid"])["amp"].transform("mean")
    d["dev_pooled"] = d["pooled"] - d.groupby(["H", "k", "cid"])["pooled"].transform("mean")
    return d


def points(sub: pd.DataFrame, col: str, nbins: int = 10):
    """按买点数分组的 (中位买点数, 偶然波动, 中位股票数)。固定买点数的配置一组一个点。"""
    if sub["N"].nunique() <= 8:
        g = sub.groupby("cid")
        return pd.DataFrame({"N": g["N"].median(), "sd": g[col].apply(lambda x: np.sqrt(np.mean(x ** 2))),
                             "stocks": g["stocks"].median(), "n": g.size()}).sort_values("N").reset_index(drop=True)
    q = pd.qcut(np.log(sub["N"]), nbins, labels=False, duplicates="drop").rename("nbin")
    g = sub.groupby(q)
    return pd.DataFrame({"N": g["N"].median(), "sd": g[col].apply(lambda x: np.sqrt(np.mean(x ** 2))),
                         "stocks": g["stocks"].median(), "n": g.size()}).sort_values("N").reset_index(drop=True)


class Curve:
    """对数坐标二次拟合；范围外按边界斜率线性外推。"""

    def __init__(self, x, y):
        self.lx, self.ly = np.log(np.asarray(x, float)), np.log(np.asarray(y, float))
        self.lo, self.hi = self.lx.min(), self.lx.max()
        deg = 2 if len(self.lx) >= 5 else 1
        self.p = np.polyfit(self.lx, self.ly, deg)
        dp = np.polyder(self.p)
        self.slo, self.shi = np.polyval(dp, self.lo), np.polyval(dp, self.hi)

    def __call__(self, x):
        lx = np.log(x)
        if lx < self.lo:
            return float(np.exp(np.polyval(self.p, self.lo) + self.slo * (lx - self.lo)))
        if lx > self.hi:
            return float(np.exp(np.polyval(self.p, self.hi) + self.shi * (lx - self.hi)))
        return float(np.exp(np.polyval(self.p, lx)))

    def inside(self, x):
        return self.lo - 0.05 <= np.log(x) <= self.hi + 0.05

    def inverse(self, target):
        """最小 N 使曲线值 ≤ target（单调递减假设）；在 [1, 1e7] 上二分。"""
        a, b = 1.0, 1e7
        if self(b) > target:
            return np.inf
        for _ in range(200):
            m = np.sqrt(a * b)
            a, b = (m, b) if self(m) > target else (a, m)
        return b


def curves(d, H, k, fam, Y, col):
    m = (d.H == H) & (d.k == k) & FAMILIES[fam](d) & (d.Y == Y) & d.tag.isna()
    sub = d[m]
    if sub.empty:
        return None, None, None
    p = points(sub, col)
    return Curve(p["N"], p["sd"]), Curve(p["N"], p["stocks"]), p


def fmt(v, inside, nd=3):
    return f"{v:.{nd}f}" + ("" if inside else "*")


def main():
    d = load()
    out = []
    P = out.append
    rates = [30, 100, 300, 1000, 3000]
    years = [1, 2, 4]

    # ---------- 表 1：偶然波动（H=40, k=5）----------
    for col, name, nd in (("dev", "方向领先（v3 口径 Δ，单位：(先上−先下)/买点数）", 3),
                          ("dev_amp", "幅度领先（前瞻收益中位数之差，单位：收益率，0.01 = 1 个百分点）", 4)):
        P(f"\n## 表1 偶然波动（1 倍标准差）：{name}；H=40 k=5")
        for fam in FAMILIES:
            P(f"\n### {fam}")
            P("| 每年买点数 | " + " | ".join(f"{y} 年" for y in years) + " |")
            P("|---|" + "---|" * len(years))
            cs = {y: curves(d, 40, 5.0, fam, y, col) for y in years}
            for r in rates:
                cells = []
                for y in years:
                    c, s, _ = cs[y]
                    if c is None:
                        cells.append("—"); continue
                    n = r * y
                    cells.append(f"{fmt(c(n), c.inside(n), nd)}（{s(n):.0f} 只）")
                P(f"| {r} | " + " | ".join(cells) + " |")

    # ---------- 表 2：最小可分辨领先 + 反查需要多少买点 ----------
    for col, name, nd in (("dev", "方向领先", 3), ("dev_amp", "幅度领先（收益率）", 3)):
        P(f"\n## 表2a 最小可分辨的{name} = {MULT} × 偶然波动；H=40 k=5（左：bottom_burst 长相 / 中：bb_v1 长相 / 右：完全独立）")
        P("| 每年买点数 | " + " | ".join(f"{y} 年" for y in years) + " |")
        P("|---|" + "---|" * len(years))
        cs = {(f, y): curves(d, 40, 5.0, f, y, col)[0] for f in ("bottom_burst 长相", "bb_v1 长相", "完全独立") for y in years}
        for r in rates:
            cells = []
            for y in years:
                vals = [fmt(MULT * cs[(f, y)](r * y), cs[(f, y)].inside(r * y), nd)
                        for f in ("bottom_burst 长相", "bb_v1 长相", "完全独立")]
                cells.append(" / ".join(vals))
            P(f"| {r} | " + " | ".join(cells) + " |")
    targets = {"dev": [0.03, 0.05, 0.08, 0.12], "dev_amp": [0.01, 0.02, 0.03, 0.05]}
    for col, name in (("dev", "方向领先"), ("dev_amp", "幅度领先（收益率）")):
        P(f"\n## 表2b 要分辨出某个{name}需要的买点（真实领先 ≥ {MULT} 倍偶然波动）；H=40 k=5；"
          f"「超出」= 需要的买点数超过这种长相模拟到的最大值的 1.5 倍，曲线外推不可信")
        for fam in ("bottom_burst 长相", "bb_v1 长相", "完全独立"):
            P(f"\n### {fam}")
            P("| 领先 | " + " | ".join(f"{y} 年：共需买点（每年）/ 股票" for y in years) + " |")
            P("|---|" + "---|" * len(years))
            cs = {y: curves(d, 40, 5.0, fam, y, col) for y in years}
            for t in targets[col]:
                cells = []
                for y in years:
                    c, s, p = cs[y]
                    n = c.inverse(t / MULT)
                    nmax = p["N"].max() * 1.5
                    if not np.isfinite(n) or n > nmax:
                        cells.append(f"超出（最多模拟到 {p['N'].max():,.0f}）"); continue
                    flag = "" if c.inside(n) else "*"
                    cells.append(f"{n:,.0f}（{n / y:,.0f}/年）/ {s(n):,.0f} 只{flag}")
                P(f"| {t:g} | " + " | ".join(cells) + " |")

    # ---------- 表 3：不独立的折扣 ----------
    P("\n## 表3 不独立的折扣：同样买点数下，方差是完全独立时的几倍（设计效应）；H=40 k=5；括号内为有效独立样本 / 命中股票数")
    for col, name in (("dev", "方向"), ("dev_amp", "幅度")):
        P(f"\n### {name}")
        P("| 长相 | 年数 | " + " | ".join(f"每年 {r}" for r in (100, 300, 1000, 3000)) + " |")
        P("|---|---|" + "---|" * 4)
        for fam in ("bottom_burst 长相", "bb_v1 长相", "连续 5 天一段"):
            for y in years:
                c, s, _ = curves(d, 40, 5.0, fam, y, col)
                ci, _, _ = curves(d, 40, 5.0, "完全独立", y, col)
                cells = []
                for r in (100, 300, 1000, 3000):
                    n = r * y
                    deff = (c(n) / ci(n)) ** 2
                    cells.append(f"{deff:.1f}（{n / deff / s(n):.2f}）" + ("" if c.inside(n) else "*"))
                P(f"| {fam} | {y} | " + " | ".join(cells) + " |")

    # ---------- 表 4：观察期长度 ----------
    P("\n## 表4 观察期长度的影响（2 年；每年 300 / 1000 个买点；括号内为 bb_v1 长相）")
    P("| 观察期 H | 线距 k | 触线比例 | 方向波动 每年300 | 方向波动 每年1000 | 幅度波动 每年300 | 幅度波动 每年1000 | 对照中位前瞻收益 | 幅度波动/对照中位 (每年1000) |")
    P("|---|---|---|---|---|---|---|---|---|")
    for (H, k) in sorted(set(zip(d.H, d.k))):
        row = []
        for col in ("dev", "dev_amp"):
            for r in (300, 1000):
                c1, _, _ = curves(d, H, k, "bottom_burst 长相", 2, col)
                c2, _, _ = curves(d, H, k, "bb_v1 长相", 2, col)
                nd = 3 if col == "dev" else 4
                row.append(f"{fmt(c1(r * 2), c1.inside(r * 2), nd)}（{fmt(c2(r * 2), c2.inside(r * 2), nd)}）")
        m = (d.H == H) & (d.k == k) & d.tag.isna() & FAMILIES["bottom_burst 长相"](d) & (d.Y == 2)
        touched = d.loc[(d.H == H) & (d.k == k) & (d.kind == "indep"), "touched"].mean()
        ctrl = d.loc[m, "amp_ctrl"].median()
        ca, _, _ = curves(d, H, k, "bottom_burst 长相", 2, "dev_amp")
        P(f"| {H} | {k:g} | {touched:.2f} | " + " | ".join(row) + f" | {ctrl:.3f} | {ca(2000) / ctrl:.2f} |")

    # ---------- 表 5：核对 ----------
    P("\n## 表5 核对：v3 自带「整只股票重抽」的偶然波动 vs 真实重复的偶然波动")
    t = d[d.tag == "v3train"]
    if len(t):
        g = t.groupby("cid").agg(kind=("kind", "first"), app=("app", "first"), q=("q", "first"),
                                 N=("N", "median"), stocks=("stocks", "median"),
                                 sd_true=("dev", lambda x: np.sqrt(np.mean(x ** 2))), boot=("boot_sd", "mean"),
                                 sd_pooled=("dev_pooled", lambda x: np.sqrt(np.mean(x ** 2))),
                                 sd_amp=("dev_amp", lambda x: np.sqrt(np.mean(x ** 2))))
        P("训练段 2024-07-01..2025-10-31（bottom_burst v3 全池冒烟所用），H=40 k=5")
        P(g.to_string())
    rb = d[d.tag.isna() & (d.k == 5.0) & (d.kind == "real") & (d.mapping == "vol")]
    gb = rb.groupby(["H", "cid"]).agg(fam=("app", "first"), Y=("Y", "first"), q=("q", "first"), N=("N", "median"),
                                      true=("dev", lambda x: np.sqrt(np.mean(x ** 2))), boot=("boot_sd", "mean"))
    gb["ratio"] = gb["boot"] / gb["true"]
    P("\n各配置：v3 重抽估计 / 真实偶然波动（<1 表示 v3 自带估计偏小）")
    P(gb.reset_index().groupby(["H", "fam"])["ratio"].describe()[["count", "min", "50%", "max"]].to_string())
    P(gb[gb.index.get_level_values(0) == 40].to_string())

    # ---------- 表 6：系统偏差（偏好波动水平白得的领先）----------
    P("\n## 表6 系统偏差：没有选股能力、只是偏好某种波动水平，白得的领先（平均值）")
    tl = d[d.kind == "tilt"].groupby(["H", "k", "dec"]).agg(dir=("delta", "mean"), amp=("amp", "mean"), sims=("delta", "size"))
    P(tl.to_string())
    rv = d[(d.kind == "real") & d.tag.isna()].groupby(["H", "k", "app", "mapping"]).agg(
        dir=("delta", "mean"), amp=("amp", "mean"), vdec=("vdec_mean", "mean"))
    P("\n换股假 pattern（同波动档换 = vol；不管波动档 = random）的平均领先：")
    P(rv.to_string())

    # ---------- 表 7：v3 窗口口径 vs 合并口径 ----------
    P("\n## 表7 方向领先：v3 口径（窗口平均 + 近期加权）偶然波动 / 合并口径偶然波动；H=40 k=5")
    m = (d.H == 40) & (d.k == 5.0) & d.tag.isna() & d.kind.isin(["indep", "runs", "real"])
    g = d[m].groupby("cid").agg(kind=("kind", "first"), app=("app", "first"), Y=("Y", "first"), N=("N", "median"),
                                v3=("dev", lambda x: np.sqrt(np.mean(x ** 2))),
                                pooled=("dev_pooled", lambda x: np.sqrt(np.mean(x ** 2))))
    g["ratio"] = g["v3"] / g["pooled"]
    P(g.groupby(["kind", "app", "Y"])["ratio"].agg(["min", "median", "max"]).to_string())

    text = "\n".join(out)
    (HERE / "02-report-tables.txt").write_text(text + "\n")
    print(text)
    plot(d)


def plot(d):
    """最小可分辨领先（2.8 × 偶然波动）随每年买点数的变化；只画模拟覆盖到的范围，不画外推。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False
    ink, ink2, grid, surf = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
    styles = {"bottom_burst 长相": ("#2a78d6", "-", "o", 9), "bb_v1 长相": ("#eb6834", "--", "s", -9),
              "完全独立": ("#7a7974", ":", "^", 0)}
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5), facecolor=surf)
    panels = (("dev", "方向领先：至少要多大才分辨得出", lambda v, _: f"{v:g}", [0.03, 0.05, 0.1, 0.2, 0.4, 0.7]),
              ("dev_amp", "幅度领先：至少要多大才分辨得出", lambda v, _: f"{v * 100:g}%", [0.005, 0.01, 0.02, 0.05, 0.1, 0.2]))
    for ax, (col, title, tick, yt) in zip(axes, panels):
        ax.set_facecolor(surf)
        for fam, (color, ls, mk, dy) in styles.items():
            c, _, p = curves(d, 40, 5.0, fam, 2, col)
            lo, hi = p["N"].min() / 2, p["N"].max() / 2
            xs = np.geomspace(max(30, lo), hi, 60)
            ys = [MULT * c(x * 2) for x in xs]
            ax.plot(xs, ys, color=color, ls=ls, lw=2)
            ax.plot(p["N"] / 2, MULT * p["sd"], mk, color=color, ms=8, mec=surf, mew=2)
            ax.annotate(fam, (xs[-1], ys[-1]), xytext=(8, dy), textcoords="offset points",
                        color=ink, fontsize=10, va="center")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.set_yticks(yt)
        ax.yaxis.set_major_formatter(FuncFormatter(tick))
        ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
        ax.set_xlabel("每年买点数（同一只股票同一天只算一个）", color=ink2)
        ax.set_title(title, color=ink, fontsize=12, loc="left")
        ax.grid(True, which="major", color=grid, lw=0.8)
        ax.tick_params(colors=ink2)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(grid)
        ax.set_xlim(25, 30000)
    fig.text(0.01, 0.01, "数据：2 年、观察期 40 个交易日、线距系数 5；点 = 模拟分组，线 = 平滑；"
             "门槛 = 2.8 倍偶然波动（有八成把握让观察值越过 2 倍偶然波动）",
             color=ink2, fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(RESEARCH / "02-resolution-noise.png", dpi=130, facecolor=surf)


if __name__ == "__main__":
    main()
