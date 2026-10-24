"""05 号票：把带 / 不带比较的结果画成「领先 ± 2 倍偶然波动」的点线图。

读 05-with-without_out.json（同目录），写 05-bands.png。只画已经算好的汇总数，不读行情。
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

HERE = Path(__file__).parent
SRC = HERE / "05-with-without_out.json"
OUT = HERE / "05-bands.png"

for name in ("Noto Sans CJK SC", "Noto Sans CJK JP", "WenQuanYi Micro Hei", "Source Han Sans SC"):
    if any(f.name == name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = name
        break

ROWS = [
    ("or_with_v10_vs_without", "added", "「或」并进量比≥10：多出来的"),
    ("or_with_v20_vs_without", "added", "「或」并进量比≥20：多出来的"),
    ("k2of3_vs_k_fixed", "added", "三条至少 2 条，去掉量比、k 不变：多出来的"),
    ("k2of3_vs_k_minus_1", "lost", "三条至少 2 条，去掉量比、k 减一：差出来的"),
    ("and_all3_vs_without", "lost", "三条都要（k=n），去掉量比：被它挡掉的"),
]
INK, MUTED, MARK, SURFACE = "#0b0b0b", "#52514e", "#2a78d6", "#fcfcfb"


def main() -> None:
    data = json.loads(SRC.read_text())
    ranges = list(data["ranges"])
    fig, axes = plt.subplots(1, len(ranges), figsize=(13, 4.6), sharey=True, facecolor=SURFACE)
    for ax, rg in zip(axes, ranges):
        ax.set_facecolor(SURFACE)
        blk = data["ranges"][rg]
        ax.axvspan(-0.03, 0.03, color="#e4e3df", zorder=0)
        ax.axvline(0, color=MUTED, lw=1, zorder=1)
        for i, (key, side, label) in enumerate(ROWS):
            b = blk[key][side]
            y = len(ROWS) - 1 - i
            lo, hi = b["band_2sd"]
            ax.plot([lo, hi], [y, y], color=MARK, lw=2, solid_capstyle="round", zorder=2)
            ax.plot(b["delta"], y, "o", ms=8, color=MARK, mec=SURFACE, mew=2, zorder=3)
            ax.annotate(f"{b['count']} 个买点日 / {b['stocks']} 只股票",
                        (hi, y), xytext=(6, 0), textcoords="offset points",
                        va="center", fontsize=8, color=MUTED)
        ax.set_yticks(range(len(ROWS)))
        ax.set_yticklabels([r[2] for r in reversed(ROWS)], fontsize=9, color=INK)
        ax.set_xlim(-0.25, 0.2)
        ax.set_title(f"训练段 {rg}", fontsize=10, color=INK)
        ax.set_xlabel("比同日普通买入多出的方向成绩（点 = 实测，线 = ±2 倍偶然波动）", fontsize=8.5, color=MUTED)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=8)
    fig.text(0.01, 0.01, "灰底 = ±0.03（过去实测参数改动的效果量级，待验证）；线跨过 0 = 还不能排除是 0",
             fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(OUT, dpi=150, facecolor=SURFACE)


if __name__ == "__main__":
    main()
