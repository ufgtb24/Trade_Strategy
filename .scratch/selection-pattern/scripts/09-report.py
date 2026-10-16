"""09 目标池票 · 汇总：池子大小、池内分辨力、池内幸存者偏差的表与图。

偶然波动 = 假 pattern 的领先在多次重复里的标准差（先减去同一配置的平均值；平均值是「偏爱高波动」白得的
系统偏移，另表单列）。扎堆长相每次重复的买点数随所抽时段与稀疏度变化，按买点数分组后用 02 的平滑曲线
（对数坐标二次拟合）读出指定买点数处的值；分散长相买点数固定，直接取。
「分辨得出」= 真实领先 ≥ 2.8 倍偶然波动（与 02 相同）。

输出：本目录 09-report-tables.txt；research/09-resolution-pool.png、research/09-survivorship-pool.png
运行：uv run python .scratch/selection-pattern/scripts/09-report.py
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent / "research"
SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad")
spec = importlib.util.spec_from_file_location("rep02", HERE / "02-report.py")
rep02 = importlib.util.module_from_spec(spec); sys.modules["rep02"] = rep02; spec.loader.exec_module(rep02)
Curve, points = rep02.Curve, rep02.points
MULT = 2.8
POOL_LABEL = {
    "all_ext": "全市场（剔非普通股）",
    "dv1M_cap100M": "成交额 100万–1亿，不限价",
    "dv2M_cap100M": "成交额 200万–1亿，不限价",
    "dv1M_px20_cap100M": "成交额 100万–1亿，≤20 美元",
    "dv2M_px20_cap100M": "成交额 200万–1亿，≤20 美元",
    "dv5M_px20_cap100M": "成交额 500万–1亿，≤20 美元",
    "dv1M_px10_cap100M": "成交额 100万–1亿，≤10 美元",
    "dv2M_px10_cap100M": "成交额 200万–1亿，≤10 美元",
}
DEFAULT = "dv2M_px20_cap100M"


def load():
    frames = []
    for f in sorted(HERE.glob("09-sim-*-H*_k*.csv.gz")):
        d = pd.read_csv(f)
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    # 偶然波动只算「同一时段里换一批股票」的摆动：按所抽时段的起点把每个配置的重复分成 8 段，各减本段平均。
    # 不同时段之间平均值的差别是「偏爱高波动」在不同年份白得多少不一样（系统偏移随时段变），另表单列。
    keys = ["pool", "H", "k", "cid"]
    d["tbin"] = d.groupby(keys)["D0"].transform(lambda x: pd.qcut(x.rank(method="first"), 8, labels=False))
    n = d.groupby(keys)["D0"].transform("size")
    for col, src in (("dev", "delta"), ("dev_amp", "amp"), ("dev_pooled", "pooled")):
        d[col] = (d[src] - d.groupby(keys + ["tbin"])[src].transform("mean")) * np.sqrt(n / (n - 8))
        d[col + "_total"] = d[src] - d.groupby(keys)[src].transform("mean")
    return d


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def value_at(d, pool, H, kind, Y, col, n_per_year):
    """返回 (偶然波动, 命中股票数, 是否在模拟范围内)。"""
    sub = d[(d.pool == pool) & (d.H == H) & (d.kind == kind) & (d.Y == Y)]
    if sub.empty:
        return np.nan, np.nan, False
    if kind == "dispersed":
        s = sub[sub.rate == n_per_year]
        if s.empty:
            return np.nan, np.nan, False
        return rms(s[col]), float(s.stocks.median()), True
    p = points(sub, col)
    c, st = Curve(p["N"], p["sd"]), Curve(p["N"], p["stocks"])
    n = n_per_year * Y
    return c(n), st(n), c.inside(n)


def main():
    d = load()
    out = []
    P = out.append
    pools = [p for p in POOL_LABEL if p in set(d.pool)]

    # —— 表 A：池子大小
    cnt = pd.read_csv(HERE / "09-pools_counts.csv")
    P("## 表A 池子大小（每天平均只数 / 当年出现过的不同股票；2021 只含 10-08 起，2026 截到 10-05）")
    P("| 池子 | " + " | ".join(str(y) for y in range(2021, 2027)) + " |")
    P("|---|" + "---|" * 6)
    for pn in pools:
        c = cnt[cnt.pool == pn].set_index("year")
        P(f"| {POOL_LABEL[pn]} | " + " | ".join(f"{c.at[y, 'stocks_per_day']:.0f} / {c.at[y, 'distinct']}" for y in range(2021, 2027)) + " |")

    # —— 表 B：H=40 门槛
    for col, name, scale, unit in (("dev", "方向领先", 1, ""), ("dev_amp", "幅度领先", 100, " 个百分点")):
        P(f"\n## 表B {name}的最小可分辨值（{MULT} × 偶然波动；观察期 40 日、线距 5；括号 = 命中的不同股票数；* = 外推）")
        for rate in (300, 1000, 3000):
            P(f"\n### 每年 {rate} 个买点（≈ 名单每天 {rate / 252:.1f} 只）")
            P("| 池子 | 扎堆 1 年 | 2 年 | 4 年 | 分散 1 年 | 2 年 | 4 年 |")
            P("|---|---|---|---|---|---|---|")
            for pn in pools:
                cells = []
                for kind in ("clustered", "dispersed"):
                    for Y in (1, 2, 4):
                        sd, st, ins = value_at(d, pn, 40, kind, Y, col, rate)
                        if not np.isfinite(sd):
                            cells.append("—"); continue
                        v = MULT * sd * scale
                        cells.append(f"{v:.3f}" if scale == 1 else f"{v:.1f}")
                        cells[-1] += f"（{st:.0f}）" + ("" if ins else "*")
                P(f"| {POOL_LABEL[pn]} | " + " | ".join(cells) + " |")

    # —— 表 C：系统偏移
    P("\n## 表C 系统偏移：假 pattern 的平均领先（不是偶然波动，样本再大也不消失）；观察期 40 日")
    P("（括号 = 这个平均值随所抽的 1 年时段不同而摆动多少：8 段时段平均值的标准差）")
    P("| 池子 | 扎堆（bottom_burst 的偏好波动档）方向 | 幅度（百分点） | 分散（同偏好）方向 | 幅度 | 完全随机 方向 | 幅度 |")
    P("|---|---|---|---|---|---|---|")
    for pn in pools:
        s = d[(d.pool == pn) & (d.H == 40)]
        a = s[(s.kind == "clustered") & (s.q == 1)]
        b = s[(s.kind == "dispersed") & (s.rate == 1000)]
        c = s[s.kind == "indep"]
        ta = a[a.Y == 1].groupby("tbin").delta.mean().std()
        tb = b[b.Y == 1].groupby("tbin").delta.mean().std()
        P(f"| {POOL_LABEL[pn]} | {a.delta.mean():+.3f}（±{ta:.3f}） | {a.amp.mean() * 100:+.1f} | {b.delta.mean():+.3f}（±{tb:.3f}） | "
          f"{b.amp.mean() * 100:+.1f} | {c.delta.mean():+.3f} | {c.amp.mean() * 100:+.1f} |")

    # —— 表 D：观察期
    P("\n## 表D 观察期（2 年、每年 1000 个买点；线距随观察期缩放 = 5×√(观察期/40)）")
    P("| 池子 | 观察期 | 触线比例 | 方向门槛 扎堆 / 分散 | 幅度门槛（百分点）扎堆 / 分散 | 同日对照前瞻收益中位 | 幅度门槛 ÷ 对照中位（分散） |")
    P("|---|---|---|---|---|---|---|")
    for pn in pools:
        for (H, k) in sorted(set(zip(d[d.pool == pn].H, d[d.pool == pn].k))):
            s = d[(d.pool == pn) & (d.H == H) & (d.k == k)]
            if s.empty or len(set(d[d.pool == pn].H)) == 1:
                continue
            vals = {}
            for kind in ("clustered", "dispersed"):
                for col in ("dev", "dev_amp"):
                    sd, _, ins = value_at(d, pn, H, kind, 2, col, 1000)
                    vals[(kind, col)] = (MULT * sd, ins)
            touched = s[s.kind == "indep"].touched.mean()
            ctrl = s[(s.kind == "dispersed") & (s.rate == 1000) & (s.Y == 2)].amp_ctrl.median()
            P(f"| {POOL_LABEL[pn]} | {H} | {touched:.2f} | {vals[('clustered', 'dev')][0]:.3f} / {vals[('dispersed', 'dev')][0]:.3f} | "
              f"{vals[('clustered', 'dev_amp')][0] * 100:.1f} / {vals[('dispersed', 'dev_amp')][0] * 100:.1f} | {ctrl * 100:.1f}% | "
              f"{vals[('dispersed', 'dev_amp')][0] / ctrl:.2f} |")

    text = "\n".join(out)
    (HERE / "09-report-tables.txt").write_text(text + "\n")
    print(text)
    plot_resolution(d)
    plot_bias()


def _style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def plot_resolution(d):
    """方向与幅度门槛随每年买点数：全市场 vs 推荐池，扎堆 vs 分散（4 年、观察期 40 日）。"""
    plt = _style()
    from matplotlib.ticker import FuncFormatter
    ink, ink2, grid, surf = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
    lines = [("all_ext", "clustered", "#2a78d6", "--", "全市场 · 扎堆"), ("all_ext", "dispersed", "#2a78d6", ":", "全市场 · 分散"),
             (DEFAULT, "clustered", "#eb6834", "-", "推荐池 · 扎堆"), (DEFAULT, "dispersed", "#eb6834", "-.", "推荐池 · 分散")]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5), facecolor=surf)
    for ax, (col, title, fmt, yt) in zip(axes, (("dev", "方向领先：至少要多大才分辨得出（4 年）", lambda v, _: f"{v:g}",
                                                 [0.02, 0.03, 0.05, 0.1, 0.2, 0.3]),
                                                ("dev_amp", "幅度领先：至少要多大才分辨得出（4 年）", lambda v, _: f"{v * 100:g}%",
                                                 [0.005, 0.01, 0.02, 0.05, 0.1]))):
        ax.set_facecolor(surf)
        for pool, kind, color, ls, label in lines:
            sub = d[(d.pool == pool) & (d.H == 40) & (d.kind == kind) & (d.Y == 4)]
            if kind == "dispersed":
                g = sub.groupby("rate").agg(N=("N", "median"), sd=(col, rms))
                xs, ys = g.N / 4, MULT * g.sd
                ax.plot(xs, ys, color=color, ls=ls, lw=2, marker="o", ms=5)
            else:
                p = points(sub, col)
                c = Curve(p["N"], p["sd"])
                xs = np.geomspace(p["N"].min() / 4, p["N"].max() / 4, 50)
                ys = [MULT * c(x * 4) for x in xs]
                ax.plot(xs, ys, color=color, ls=ls, lw=2)
            ax.annotate(label, (list(xs)[-1], list(ys)[-1]), xytext=(6, 0), textcoords="offset points",
                        color=ink, fontsize=9, va="center")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.set_yticks(yt)
        ax.yaxis.set_major_formatter(FuncFormatter(fmt))
        ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
        ax.set_xlabel("每年买点数", color=ink2)
        ax.set_title(title, color=ink, fontsize=12, loc="left")
        ax.grid(True, which="major", color=grid, lw=0.8)
        ax.tick_params(colors=ink2)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.set_xlim(20, 12000)
    fig.text(0.01, 0.01, f"推荐池 = 成交额每天 200万–1亿美元、价格 ≤20 美元、剔除非普通股；观察期 40 个交易日；"
             f"门槛 = 2.8 倍偶然波动", color=ink2, fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(RESEARCH / "09-resolution-pool.png", dpi=130, facecolor=surf)


def plot_bias():
    plt = _style()
    b = pd.read_pickle(SCR / "09/bias_results.pkl")
    res, dates = b["results"], b["chart_dates"]
    ne = len(dates)
    ink, ink2, muted, grid, surf = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
    series = [("底部：跌掉七成以上", "#2a78d6", "-", "底部：跌掉七成以上"),
              ("底部：跌掉九成以上", "#1baf7a", "-", "底部：跌掉九成以上"),
              ("burst：反弹型", "#eda100", "--", "burst：反弹型（大跌后密集突破）"),
              ("burst：高位型", "#7a7974", ":", "burst：高位型"),
              ("挖数据：跌掉九成以上 + 成交额贴着下限", "#c43c5a", "-.", "挖数据会钻的地方：跌掉九成以上且成交额贴着下限")]
    fig, ax = plt.subplots(figsize=(10.5, 5.8), dpi=150)
    fig.patch.set_facecolor(surf); ax.set_facecolor(surf)
    ax.axhspan(0.02, 0.05, color="#f0efec", zorder=0)
    ax.text(pd.Timestamp("2024-03-01"), 0.046, "想找的真实优势大约在这一带", ha="left", va="center", color=ink2, fontsize=9)
    ax.axhline(0, color="#c3c2b7", lw=1)
    for key, col, ls, label in series:
        r = res[(DEFAULT, key)]
        ax.plot(dates, r["mid"][:ne], color=col, ls=ls, lw=2, label=label)
    full = res[("all_ext", "底部：跌掉七成以上")]["mid"][:ne]
    ax.plot(dates, full, color="#2a78d6", ls="-", lw=1, alpha=0.45, label="（对照）全市场 · 底部跌掉七成以上")
    ax.set_xticks([pd.Timestamp(f"{y}-01-01") for y in range(2022, 2027)])
    ax.set_xticklabels([str(y) for y in range(2022, 2027)])
    ax.set_ylabel("首次穿越的领先被白白抬高多少", color=ink2)
    ax.set_xlabel("买入日期（越早，之后被摘牌、从数据里消失的股票越多）", color=ink2)
    ax.tick_params(colors=muted)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.grid(axis="y", color=grid, lw=0.6)
    ax.set_title("推荐池里，只用活到今天的股票做对照：底部类照样被抬高（推演，非实测；中间假设）",
                 loc="left", color=ink, fontsize=12)
    ax.legend(loc="upper right", frameon=False, fontsize=8.5, labelcolor=ink2)
    fig.text(0.01, 0.01, "推荐池 = 成交额每天 200万–1亿美元、价格 ≤20 美元、剔除非普通股。假设往两头取的范围见研究文件的表。",
             color=muted, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(RESEARCH / "09-survivorship-pool.png", facecolor=surf)


if __name__ == "__main__":
    main()
