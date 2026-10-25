"""画 cost.md 的耗时对比图:两种窗口各一格,横条 = 200 只股票的中位数,细线延到最慢那只,虚线 = 约 100 毫秒。"""
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
d = json.loads((HERE / "out_bench.json").read_text())
rows = d["rows"]
from matplotlib import font_manager  # noqa: E402
font_manager.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
plt.rcParams["font.family"] = ["Noto Sans CJK JP"]
INK, MUTED, BAR, SURF = "#0b0b0b", "#52514e", "#2a78d6", "#fcfcfb"

items = [
    ("读一只股票的 K 线", lambda r, w: r["load_ms"]),
    ("现在：切股时现跑 app 的 node 诊断", lambda r, w: r[w]["bb_v1"]["diagnose_ms"]),
    ("一个 app 完整算一遍（bb_v1）", lambda r, w: r[w]["bb_v1"]["analyze_ms"] + r[w]["bb_v1"]["serialize_ms"]),
    ("所有现成 detector 一起算", lambda r, w: r[w]["all_atoms"]["engine_ms"] + r[w]["all_atoms"]["serialize_ms"]),
]
fig, axes = plt.subplots(1, 2, figsize=(11, 3.4), sharey=True, facecolor=SURF)
for ax, (w, title) in zip(axes, (("view1y", "一年看图范围（约 315 根）"), ("train4y", "整个训练段（约 1060 根）"))):
    ax.set_facecolor(SURF)
    for i, (name, f) in enumerate(items):
        xs = [f(r, w) for r in rows]
        med, mx = statistics.median(xs), max(xs)
        y = len(items) - 1 - i
        ax.barh(y, med, height=0.5, color=BAR)
        ax.plot([med, mx], [y, y], color=MUTED, lw=1)
        ax.text(mx + 2, y, f"{med:.0f} 毫秒（最慢 {mx:.0f}）", va="center", fontsize=9, color=INK)
    ax.axvline(100, color=MUTED, ls="--", lw=1)
    ax.text(101, len(items) - 0.55, "约 100 毫秒：开始能感到卡", fontsize=8.5, color=MUTED, va="bottom")
    ax.set_xlim(0, 130)
    ax.set_title(title, fontsize=10.5, color=INK, loc="left")
    ax.set_xlabel("毫秒", fontsize=9, color=MUTED)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=9)
axes[0].set_yticks(range(len(items)))
axes[0].set_yticklabels([n for n, _ in items][::-1], fontsize=9.5, color=INK)
fig.suptitle(f"单只股票的后端计算耗时（{len(rows)} 只随机股票，横条 = 中位数，细线到最慢那只）",
             fontsize=11, color=INK, x=0.01, ha="left")
fig.tight_layout()
fig.savefig(HERE.parent / "cost_latency.png", dpi=150, facecolor=SURF)
print("ok")
