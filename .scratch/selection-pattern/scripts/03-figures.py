"""03 研究文件的两张图。

图 1：文献的「每月平均收益差」换算成方向成绩领先（读 03-drift_to_fp_out.txt），对照分辨力门槛带。
图 2：几个关键价量信号在各时段的平均月收益（读 03-factor_recent_output.csv，JKP 口径）。

用法：uv run python -I 03-figures.py <scripts 目录> <输出目录>
"""
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from matplotlib import font_manager

for _f in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",):
    font_manager.fontManager.addfont(_f)
plt.rcParams["font.family"] = font_manager.FontProperties(fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc").get_name()
plt.rcParams["axes.unicode_minus"] = False

INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]


def fig_drift(scripts: Path, out: Path):
    rows = []
    for line in (scripts / "03-drift_to_fp_out.txt").read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split()
        rows.append((parts[0], float(parts[1].rstrip("%")), float(parts[2])))
    fig, ax = plt.subplots(figsize=(7.2, 4.2), facecolor=SURF)
    ax.set_facecolor(SURF)
    ax.axhspan(0.07, 0.22, color="#f0efec", zorder=0)
    ax.text(0.35, 0.215, "「分辨力」票草稿里的门槛区间（0.07~0.22，未确认）",
            fontsize=8.5, color=INK2, va="top")
    styles = ["-", "--", ":"]
    markers = ["o", "s", "^"]
    for i, vol in enumerate(["2%", "3%", "5%"]):
        xs = [m for v, m, _ in rows if v == vol]
        ys = [d for v, _, d in rows if v == vol]
        ax.plot(xs, ys, styles[i], marker=markers[i], color=SERIES[i], lw=2, ms=7)
        ax.annotate(f"日波动 {vol}", (xs[-1], ys[-1]), xytext=(6, 0), textcoords="offset points",
                    fontsize=9, color=INK, va="center")
    ax.set_xlim(0.3, 2.6)
    ax.set_ylim(0, 0.24)
    ax.set_xlabel("文献里的每月平均收益差（%）", color=INK2)
    ax.set_ylabel("方向成绩领先（先触上行线 − 先触下行线）", color=INK2)
    ax.set_title("每月 1% 的收益差，只值 0.04~0.10 的方向领先", color=INK, fontsize=11, loc="left")
    ax.grid(axis="y", color=GRID, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED)
    fig.text(0.01, 0.01, "粗略换算：正态日收益、无跳空，线距 5 倍 ATR%，观察 40 个交易日；自算，待验证。",
             fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out / "03-fig-drift-to-direction.png", dpi=160, facecolor=SURF)


SIGNALS = [
    ("ret_1_0", "短期反转（买上月输家）"),
    ("ret_12_1", "动量 12-1"),
    ("resff3_12_1", "残差动量 12-1"),
    ("prc_highprc_252d", "接近 52 周高点"),
    ("rmax1_21d", "避开上月单日暴涨（MAX）"),
    ("rmax5_rvol_21d", "避开暴涨日÷波动（MAX5/σ）"),
    ("rskew_21d", "避开正偏度（21 日）"),
    ("turnover_126d", "低换手"),
    ("seas_1_1an", "季节性（去年同月）"),
    ("ret_60_12", "长期反转"),
]
PERIODS = [("2000前", "2000 前"), ("2000-2010", "2000-10"), ("2011-2020", "2011-20"),
           ("2021-末", "2021-25"), ("2021-末去2022", "21-25 去掉 2022")]


def fig_heat(scripts: Path, out: Path):
    data = {}
    with open(scripts / "03-factor_recent_output.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["来源"] == "JKP":
                data[(row["代码"], row["加权"])] = row
    cmap = LinearSegmentedColormap.from_list("div", ["#d03b3b", "#f0efec", "#2a78d6"])
    norm = TwoSlopeNorm(vmin=-1.6, vcenter=0, vmax=1.6)
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.6), facecolor=SURF)
    for ax, (w, wname) in zip(axes, [("vw_cap", "按市值加权（大盘股为主）"), ("ew", "等权（小盘股分量大）")]):
        grid, labels = [], []
        for code, _ in SIGNALS:
            r = data.get((code, w))
            vals, labs = [], []
            for key, _ in PERIODS:
                m = r.get(f"{key}_均值%") if r else None
                t = r.get(f"{key}_t") if r else None
                if m in (None, ""):
                    vals.append(0.0)
                    labs.append("—")
                else:
                    vals.append(float(m))
                    labs.append(f"{float(m):+.2f}\n({float(t):+.1f})")
            grid.append(vals)
            labels.append(labs)
        ax.imshow(grid, cmap=cmap, norm=norm, aspect="auto")
        for i, labs in enumerate(labels):
            for j, s in enumerate(labs):
                ax.text(j, i, s, ha="center", va="center", fontsize=7.5, color=INK)
        ax.set_xticks(range(len(PERIODS)), [p for _, p in PERIODS], fontsize=8.5, color=INK2)
        ax.set_yticks(range(len(SIGNALS)), [n for _, n in SIGNALS] if ax is axes[0] else [""] * len(SIGNALS),
                      fontsize=9, color=INK)
        ax.set_title(wname, fontsize=10.5, color=INK, loc="left")
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xticks([x - 0.5 for x in range(1, len(PERIODS))], minor=True)
        ax.set_yticks([y - 0.5 for y in range(1, len(SIGNALS))], minor=True)
        ax.grid(which="minor", color=SURF, lw=2)
    fig.suptitle("价量信号的多空月收益 %（括号内 t 值）：蓝 = 仍按原方向赚钱，红 = 反过来亏钱",
                 x=0.01, ha="left", fontsize=11.5, color=INK)
    fig.text(0.01, 0.01, "数据：Jensen-Kelly-Pedersen 公开因子（美国，截至 2025-12），原始多空收益、未扣成本；"
             "正负号已统一为「按原论文方向做多为正」。", fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(out / "03-fig-factor-decay.png", dpi=160, facecolor=SURF)


if __name__ == "__main__":
    scripts_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_drift(scripts_dir, out_dir)
    fig_heat(scripts_dir, out_dir)
