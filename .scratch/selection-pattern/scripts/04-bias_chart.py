"""04 幸存者偏差票：把推演画成一张图——买入日期越早、跌得越深，方向领先被抬得越多。

模型（全部假设见研究文件「数值推演」节）：
  f(t)  买入日在市、到 2026-10-05 前因业绩被摘牌的比例，由逐年摘牌率累乘：
        2022 2.6%、2023 4.5%（文献图读数），2024–2026 各 3%/年（假设）。
  c_q   这些股票在买入日落在第 q 个波动档的比例（假设：最高档 0.6，区间 0.5–0.7；次高档 0.25，其余三档分剩下的）。
  h_q   第 q 档同日对照里缺掉的比例 = f·c_q / (f·c_q + 0.2·(1−f))。
  b_s   幸存股在第 q 档里处于该状态的比例（本地实测，本脚本现算，只用买入当天及以前的数据）。
  b_d   以后被摘牌的股票在该档时处于该状态的比例 = 比例 × b_s（比例为假设，各档相同，见 STATES 注释）。
  h_X   = h_q·b_d / (h_q·b_d + (1−h_q)·b_s)
  偏差  = Σ_q w_q · (h_X − h_q) × G，w_q = 该状态的买点落在第 q 档的比例（本地实测），
        G = 以后被摘牌的股票比幸存股方向得分低多少（模拟：0.25，区间 0.15–0.40）。
运行：uv run python .scratch/selection-pattern/scripts/04-bias_chart.py
输出：research/04-survivorship-bias.png 与 scripts/04-bias_chart_out.txt
"""
import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/home/yu/PycharmProjects/Trade_Strategy"
PNG = os.path.join(HERE, "..", "research", "04-survivorship-bias.png")
TXT = os.path.join(HERE, "04-bias_chart_out.txt")
END = pd.Timestamp("2026-10-05")
RATES = {2022: 0.026, 2023: 0.045, 2024: 0.03, 2025: 0.03, 2026: 0.03}

# 状态：(名称, 判定函数, 「以后被摘牌的股票处于该状态的比例 / 幸存股处于该状态的比例」低 / 中 / 高)
# 大跌后三档的比例由最高波动档的假设换算：b_d 取 九成 0.30/0.45/0.60、七成 0.60/0.75/0.90、一半 0.80/0.90/0.95，
# 除以最高档实测 b_s（0.130 / 0.401 / 0.657）；其余各档沿用同一比例（即该状态在各档同样「预示」摘牌）。
STATES = [
    ("大跌后（离一年高点跌掉九成以上）", lambda p: p.dd <= 0.1, (0.30 / 0.130, 0.45 / 0.130, 0.60 / 0.130)),
    ("大跌后（跌掉七成以上）", lambda p: p.dd <= 0.3, (0.60 / 0.401, 0.75 / 0.401, 0.90 / 0.401)),
    ("大跌后（跌掉一半以上）", lambda p: p.dd <= 0.5, (0.80 / 0.657, 0.90 / 0.657, 0.95 / 0.657)),
    ("创一年新高的突破", lambda p: p.dd >= 0.999, (0.1, 0.3, 0.6)),
]
# 以后被摘牌的股票在买入日落在各波动档（低→高）的比例：低 / 中 / 高三套
C_SETS = ((0.05, 0.05, 0.10, 0.30, 0.50), (0.03, 0.03, 0.09, 0.25, 0.60), (0.02, 0.02, 0.06, 0.20, 0.70))
G = (0.15, 0.25, 0.40)


def load_panel():
    rows = []
    for path in sorted(glob.glob(os.path.join(ROOT, "datasets/pkls/*.pkl"))):
        df = pd.read_pickle(path)[["high", "low", "close"]].astype(float)
        df = df[df.close > 0]
        c = df.close
        prev = c.shift(1)
        tr = pd.concat([df.high - df.low, (df.high - prev).abs(), (df.low - prev).abs()], axis=1).max(axis=1)
        f = pd.DataFrame({"M": (tr / c).rolling(20).median(), "dd": c / c.rolling(252, min_periods=1).max()})
        rows.append(f[f.index >= "2022-01-03"].iloc[::5].dropna())
    panel = pd.concat(rows).reset_index()
    panel["q"] = panel.groupby("date")["M"].transform(
        lambda s: np.searchsorted(np.unique(np.quantile(s, [.2, .4, .6, .8])), s, side="left"))
    return panel


def f_of(t):
    surv, cur = 1.0, t
    while cur < END:
        nxt = min(pd.Timestamp(f"{cur.year + 1}-01-01"), END)
        surv *= (1 - RATES[cur.year]) ** ((nxt - cur).days / 365.25)
        cur = nxt
    return 1 - surv


def bias(t, w, b_s, ratio, c_set, g):
    f = f_of(t)
    total = 0.0
    for q in range(5):
        if w[q] == 0:
            continue
        hq = f * c_set[q] / (f * c_set[q] + 0.2 * (1 - f))
        bd = min(ratio * b_s[q], 0.95)
        hx = hq * bd / (hq * bd + (1 - hq) * b_s[q])
        total += w[q] * (hx - hq) * g
    return total


def main():
    panel = load_panel()
    dates = pd.date_range("2022-01-01", "2026-08-01", freq="MS")
    res, meta = {}, ["各状态实测：w = 买点落在各档（低→高）的比例；b_s = 各档里处于该状态的比例"]
    for name, rule, ratios in STATES:
        mask = rule(panel)
        w = panel.loc[mask, "q"].value_counts(normalize=True).reindex(range(5), fill_value=0).to_numpy()
        b_s = panel.assign(m=mask).groupby("q")["m"].mean().reindex(range(5)).to_numpy()
        meta.append(f"{name}: w={np.round(w, 3).tolist()} b_s={np.round(b_s, 3).tolist()}")
        res[name] = tuple(np.array([bias(t, w, b_s, ratios[i], C_SETS[i], G[i]) for t in dates])
                          for i in range(3))

    lines = meta + ["", "买入月份 | f(到数据末日前因业绩摘牌的比例) | " + " | ".join(f"{n[0]}: 低/中/高" for n in STATES)]
    for i, t in enumerate(dates):
        if t.month not in (1, 7):
            continue
        cells = [f"{res[n[0]][0][i]:+.3f}/{res[n[0]][1][i]:+.3f}/{res[n[0]][2][i]:+.3f}" for n in STATES]
        lines.append(f"{t.date()} | {f_of(t):.3f} | " + " | ".join(cells))
    out = "\n".join(lines)
    print(out)
    with open(TXT, "w") as fh:
        fh.write(out + "\n")

    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False
    surface, ink, ink2, muted, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
    styles = ["-", "--", "-.", ":"]
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=150)
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)
    ax.axhspan(0.02, 0.05, color="#f0efec", zorder=0)
    ax.text(dates[-1], 0.035, "想找的真实优势\n大约在这一带", ha="right", va="center", color=ink2, fontsize=9)
    ax.axhline(0, color="#c3c2b7", lw=1, zorder=1)
    for (name, _, _), col, ls in zip(STATES, colors, styles):
        lo, mid, hi = res[name]
        ax.plot(dates, mid, color=col, lw=2, ls=ls, zorder=3, label=name)
        ax.text(dates[0] - pd.Timedelta(days=12), mid[0], name, ha="right", va="center", color=ink, fontsize=9)
    ax.set_xlim(dates[0] - pd.Timedelta(days=560), dates[-1] + pd.Timedelta(days=20))
    ax.set_xticks([pd.Timestamp(f"{y}-01-01") for y in range(2022, 2027)])
    ax.set_xticklabels([str(y) for y in range(2022, 2027)])
    ax.set_ylabel("首次穿越的领先被抬高多少（先涨比例减先跌比例）", color=ink2, fontsize=10)
    ax.set_xlabel("买入日期（越早，到数据末日之间退市的股票越多）", color=ink2, fontsize=10)
    ax.tick_params(colors=muted, labelsize=9)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.grid(axis="y", color=grid, lw=0.6)
    ax.set_title("只用活到今天的股票做对照：底部类被抬高，突破类反而略被压低（推演，非实测）",
                 loc="left", color=ink, fontsize=12)
    ax.legend(loc="upper right", frameon=False, fontsize=9, labelcolor=ink2)
    fig.text(0.01, 0.01, "四条线都取中间假设（假设取低 / 取高时的范围见研究文件附表）；已按买点在各波动档的分布加权。",
             color=muted, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(PNG, facecolor=surface)
    print("saved", os.path.abspath(PNG))


if __name__ == "__main__":
    main()
