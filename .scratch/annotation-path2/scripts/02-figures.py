"""训练段用多长 —— 出图。只读本目录下的 csv 输出，图写到 ../research/。
用户色盲：不靠色相区分，全部用一个蓝色的深浅 + 灰色 + 文字标注。"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "research"
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "Droid Sans Fallback"]
plt.rcParams["axes.unicode_minus"] = False
BLUE, LIGHT, INK, MUTED, GRID = "#2a78d6", "#b9cbe3", "#0b0b0b", "#52514e", "#e4e3df"
PERS = ["2022H1", "2022H2", "2023H1", "2023H2", "2024H1", "2024H2", "2025H1", "2025H2"]
LAB = ["22上", "22下", "23上", "23下", "24上", "24下", "25上", "25下"]


def style(ax):
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


# 图 1：各半年的市场状态，「现在」（2025 下半年）用深色
R = pd.read_csv(HERE / "02-regime-halfyear.csv", index_col=0).reindex(PERS)
panels = [("市场涨跌", "等权市场半年涨跌", 100, "%"), ("市场波动", "市场波动（年化）", 100, "%"),
          ("池内典型波动M", "池内股票的典型日波动", 100, "%"), ("大盘带动比例", "个股涨跌里大盘带动的比例", 100, "%"),
          ("极端日占比", "单日涨跌超过 20% 的股票日占比", 100, "%"), ("池内每日股票数", "池内每天的股票数", 1, "只")]
fig, axes = plt.subplots(2, 3, figsize=(13, 6.4))
for ax, (col, title, mult, unit) in zip(axes.flat, panels):
    v = R[col].to_numpy() * mult
    colors = [LIGHT] * 7 + [BLUE]
    ax.bar(range(8), v, color=colors, width=0.7, edgecolor="white", linewidth=2)
    ax.set_xticks(range(8), LAB)
    ax.set_title(title, fontsize=11, color=INK, loc="left")
    ax.axhline(0, color=MUTED, lw=0.8)
    for i, x in enumerate(v):
        if i in (0, 7):
            ax.annotate(f"{x:.1f}{unit}" if mult != 1 else f"{x:.0f}", (i, x), ha="center",
                        va="bottom" if x >= 0 else "top", fontsize=8.5, color=INK,
                        xytext=(0, 2 if x >= 0 else -2), textcoords="offset points")
    style(ax)
fig.suptitle("各半年的市场状态（深色 = 2025 下半年，代表「现在」）", fontsize=13, color=INK, x=0.01, ha="left")
fig.tight_layout()
fig.savefig(OUT / "02-regime.png", dpi=130)
plt.close(fig)

# 图 2：用多长的历史估下一个半年最准
def rel(path, mh, excl=()):
    D = pd.read_csv(path)
    D = D[(D["可用历史"] >= mh) & (~D["目标"].isin(excl))]
    meth = ["最近1个半年", "最近2个半年", "最近3个半年", "之前全部·近期加权", "同一市场状态(上限)", "同涨跌方向(上限)", "之前全部"]
    keys = D.groupby(["抽样", "信号", "指标", "目标"])["挑法"].apply(set)
    ok = keys[keys.apply(lambda st: set(meth) <= st)].index
    D = D.set_index(["抽样", "信号", "指标", "目标"]).loc[ok].reset_index()
    out = []
    for m in D["指标"].unique():
        t = D[D["指标"] == m].groupby("挑法")["平方误差"].mean()
        out.append(t / t["之前全部"])
    return pd.concat(out, axis=1).mean(axis=1).reindex(meth)


names = {"最近1个半年": "只用最近半年", "最近2个半年": "只用最近一年", "最近3个半年": "只用最近一年半",
         "之前全部·近期加权": "全部，近期加权（v3 现行）", "同一市场状态(上限)": "只用波动状态相同的半年*",
         "同涨跌方向(上限)": "只用涨跌方向相同的半年*", "之前全部": "全部，等权"}
dense = rel(HERE / "02-window-errors.csv", 3)
sparse = rel(HERE / "02-window-errors-frac0.1.csv", 3)
fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
for ax, ser, title in [(axes[0], dense, "买点多的信号（每半年几百到上万个）"),
                       (axes[1], sparse, "买点稀的版本（每个信号只留一成股票）")]:
    y = np.arange(len(ser))
    cols = [BLUE if k == "之前全部" else LIGHT for k in ser.index]
    ax.barh(y, ser.values, color=cols, height=0.62, edgecolor="white", linewidth=2)
    ax.axvline(1.0, color=INK, lw=1, ls=(0, (3, 3)))
    for yi, v in zip(y, ser.values):
        ax.text(v + 0.03, yi, f"{v:.2f}", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, [names[k] for k in ser.index])
    ax.invert_yaxis()
    ax.set_title(title, fontsize=11, color=INK, loc="left")
    ax.set_xlabel("估错的程度（「全部，等权」= 1，越小越准）", fontsize=9, color=MUTED)
    style(ax)
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.yaxis.grid(False)
fig.suptitle("用之前多长的历史去估「下一个半年」的信号领先，估得准不准", fontsize=13, color=INK, x=0.01, ha="left")
fig.text(0.01, 0.01, "* 用了目标半年自己的市场状态，事先不可能知道，是这种挑法能做到的最好情况。目标半年 = 2023 下半年到 2025 下半年，共 5 个。",
         fontsize=8.5, color=MUTED)
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(OUT / "02-window.png", dpi=130)
plt.close(fig)

# 图 3：深跌股在各半年的领先
E = pd.read_csv(HERE / "02-signals-effects.csv")
fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
for ax, m, title, mult, unit in [(axes[0], "方向40日", "方向领先（首次穿越，40 日）", 1, ""),
                                 (axes[1], "幅度40日", "幅度领先（前瞻收益中位，40 日）", 100, " 个百分点")]:
    g = E[(E["信号"] == "离120日高点跌一半以上") & (E["指标"] == m)].set_index("时段").reindex(PERS)
    v, se = g["领先"].to_numpy() * mult, g["偶然波动"].to_numpy() * mult
    x = np.arange(8)
    ax.errorbar(x, v, yerr=2 * se, fmt="none", ecolor=MUTED, elinewidth=1.2, capsize=3)
    ax.scatter(x[:7], v[:7], s=46, color=LIGHT, edgecolor=BLUE, zorder=3)
    ax.scatter(x[7:], v[7:], s=60, color=BLUE, zorder=3)
    ax.axhline(0, color=INK, lw=0.9)
    ax.set_xticks(x, LAB)
    ax.set_title(title + (f"（单位{unit.strip()}）" if unit else ""), fontsize=11, color=INK, loc="left")
    style(ax)
fig.suptitle("「离 120 日高点跌一半以上」的池内股票日，比同日同档普通买入多出的部分（竖线 = ±2 倍偶然波动）",
             fontsize=12, color=INK, x=0.01, ha="left")
fig.tight_layout()
fig.savefig(OUT / "02-deep-drawdown.png", dpi=130)
plt.close(fig)
print("ok")
