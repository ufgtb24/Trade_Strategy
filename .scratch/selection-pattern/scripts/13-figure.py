"""13 外部信息 · 配图：各信息源的历史能回溯到哪，和训练段、验证段对一下。

每一行一个来源；实心长条 = 整段历史都取得到；斜线长条 = 只保留最近一段（随时间往后滚，取不回老数据）。
起点早于图左边界的，在左端标出真实起点。数值来自本票实测与以前的实测（研究文件第一节各表）。
输出：research/13-history-coverage.png
运行：uv run python .scratch/selection-pattern/scripts/13-figure.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

_F = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
font_manager.fontManager.addfont(_F)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=_F).get_name()

OUT = Path(__file__).resolve().parents[1] / "research/13-history-coverage.png"
INK, INK2, GRID, BLUE = "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
LEFT, NOW = pd.Timestamp("2021-10-01"), pd.Timestamp("2026-10-07")
# (名称, 起点, 真实起点说明, 是否整段可得, 价格)
ROWS = [
    ("SEC 公告与文件（8-K、增发、内部人、财务数值）", "2001-01-01", "2001 起", True, "免费"),
    ("FINRA 空头持仓（每月两次）", "2019-12-31", "≥2019 年底", True, "免费"),
    ("FINRA 每日场外卖空量", "2019-01-02", "2019 起", True, "免费"),
    ("Nasdaq 财报日历（含分析师预期）", "2024-02-14", "只试到 2024-02，更早没试", True, "免费"),
    ("StockTwits 讨论", "2013-04-26", "2013 起", True, "免费"),
    ("CBOE 恐慌指数 / Nasdaq 接口的 ETF 日线", "2021-10-01", "1990 起 / 2021-10 起", True, "免费"),
    ("Benzinga 新闻（经 Massive）", "2009-04-27", "2009 起", True, "每月 99 美元"),
    ("Finnhub 新闻（免费档）", "2025-10-07", "只留最近 12 个月", False, "免费"),
    ("EODHD 新闻（免费档）", "2025-10-07", "只留最近 1 年", False, "免费"),
    ("Tiingo 新闻（个人付费档）", "2026-07-07", "只能查最近 3 个月", False, "每月 30 美元"),
]


def main():
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=150)
    fig.patch.set_facecolor("white")
    ax.axvspan(pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-31"), color="#ecebe7", zorder=0)
    ax.axvspan(pd.Timestamp("2026-01-01"), NOW, color="#d9d8d2", zorder=0)
    n = len(ROWS)
    ax.text(pd.Timestamp("2024-12-31"), n - 0.35, "训练段", ha="center", va="bottom", color=INK2, fontsize=10)
    ax.text(pd.Timestamp("2026-05-20"), n - 0.35, "验证段", ha="center", va="bottom", color=INK2, fontsize=10)
    for i, (name, start, note, full, price) in enumerate(ROWS):
        y = n - 1 - i
        s = max(pd.Timestamp(start), LEFT)
        kw = dict(color=BLUE, edgecolor=BLUE) if full else dict(color="white", edgecolor=BLUE, hatch="////")
        ax.barh(y, (NOW - s).days, left=s, height=0.56, linewidth=1.2, zorder=2, **kw)
        label_x = s + pd.Timedelta(days=12)
        txt = f"{note} · {price}"
        if full:
            ax.text(label_x, y, txt, va="center", ha="left", color="white", fontsize=8.5, zorder=3)
        else:
            ax.text(s - pd.Timedelta(days=12), y, txt, va="center", ha="right", color=INK, fontsize=8.5, zorder=3)
    ax.set_yticks(range(n))
    ax.set_yticklabels([r[0] for r in ROWS][::-1], fontsize=9, color=INK)
    ax.set_xlim(LEFT, NOW + pd.Timedelta(days=20))
    ax.set_ylim(-0.6, n + 0.2)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis="x", colors=INK2, labelsize=9)
    ax.grid(axis="x", color=GRID, zorder=1)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="y", length=0)
    ax.set_title("各类外部信息的历史能回溯到哪（实心 = 整段可取；斜线 = 只留最近一段，老数据取不回）",
                 fontsize=11, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(OUT, facecolor="white")
    print(OUT)


if __name__ == "__main__":
    main()
