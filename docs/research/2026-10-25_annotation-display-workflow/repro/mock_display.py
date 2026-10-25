"""示意图：标注时（对照 app 关）vs 打开「对照 app」后，用户看到的样子。

数据取原型导出的 WHLRP 一段（bb_v1 的真实事件与 where 实测值）；用户的框与买点是虚构的演示标注。
只为讲清显示方案，不是界面实现。输出 ../mock_display.png。
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

font_manager.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
plt.rcParams["font.family"] = ["Noto Sans CJK JP"]

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
raw = (ROOT / ".scratch/annotation-path2/prototypes/01-annotation/data.js").read_text()
D = json.loads(raw[raw.index("{"):raw.rstrip().rstrip(";").rindex("}") + 1])
ST = [s for s in D["stocks"] if s["symbol"] == "WHLRP"][0]
BARS = ST["bars"][90:]
OFF = 90
UP, DOWN = "#47b262", "#eb5454"          # 主视图 K 线配色
BURST, TB = "#FF1500", "#14b24e"          # bb_v1 node 本色（主视图兜底调色板）
QUAL, DET = "#9ca3af", "#d1d5db"
INK, MUTED = "#111111", "#52525b"

# 演示标注（用户自己画的粗框，索引为原数据索引）
USER = [
    dict(name="放量突破", s=157, e=165, role="burst"),
    dict(name="回落企稳", s=164, e=169, role="tb"),
    dict(name="放量突破", s=205, e=212, role="burst"),
    dict(name="回落企稳", s=213, e=220, role="tb"),
    dict(name="放量突破", s=104, e=110, role="burst"),
    dict(name="底部横盘", s=132, e=156, role=None),
]
BUYS = [dict(i=166, lab="正例"), dict(i=219, lab="正例"), dict(i=113, lab="像但不买")]
# 判定（按 mind.md 第 4.1 节三层规则，从 bb_v1 的真实事件与 where 值得出：
#   框一层看「事件在不在 + 过没过本 node 的 where」，买点一层看进没进 match）
VERDICT = {
    0: ("✓ 认出", None),
    1: ("✓ 认出", None),
    2: ("◐ 不够格：量不够", None),
    3: ("✓ 认出", None),
    4: ("◐ 不够格：量不够", None),
    5: ("× 还没放进 app", "hatch"),
}
BUYV = {166: "✓ app 也会买", 219: "× app 没买", 113: "✓ app 也没买"}
# app 输出（bb_v1）：(node, s, e, 档位)
APP = [("burst", 160, 164, "matched"), ("burst", 208, 211, "detected"), ("burst", 108, 108, "detected"),
       ("tb", 166, 166, "matched"), ("tb", 215, 226, "qualified")]   # tb_215_226 过了 day_drop，是 qualified
MATCH = [(160, 166)]


def candles(ax):
    for k, b in enumerate(BARS):
        c = UP if b["c"] >= b["o"] else DOWN
        ax.plot([k, k], [b["l"], b["h"]], color=c, lw=0.7)
        ax.add_patch(Rectangle((k - 0.35, min(b["o"], b["c"])), 0.7, abs(b["c"] - b["o"]) or 1e-3, color=c))
    ax.set_xlim(-1, len(BARS))
    ax.set_xticks([])
    ax.tick_params(axis="y", labelsize=7, colors=MUTED)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def buy_marks(ax, with_verdict):
    lo = min(b["l"] for b in BARS)
    hi = max(b["h"] for b in BARS)
    for b in BUYS:
        x = b["i"] - OFF
        ax.axvline(x, color=INK, ls=(0, (3, 2)), lw=0.9)
        t = ("买 · " if b["lab"] == "正例" else "不买 · ") + b["lab"]
        if with_verdict:
            t += "\n" + BUYV[b["i"]]
        ax.text(x + 0.8, hi - (hi - lo) * 0.02, t, fontsize=7.5, color=INK, va="top",
                bbox=dict(fc="white", ec=INK, lw=0.6, pad=1.5))


def band_axes(ax, rows):
    ax.set_xlim(-1, len(BARS))
    ax.set_ylim(len(rows), 0)
    ax.set_yticks([r + 0.5 for r in range(len(rows))])
    ax.set_yticklabels(rows, fontsize=8, color=INK)
    ax.set_xticks([])
    for r in range(len(rows) + 1):
        ax.axhline(r, color="#e4e4e7", lw=0.6)
    for sp in ("top", "right", "bottom"):
        ax.spines[sp].set_visible(False)


def user_box(ax, row, u, tag=None, hatch=None):
    x0, x1 = u["s"] - OFF - 0.5, u["e"] - OFF + 0.5
    ax.add_patch(Rectangle((x0, row + 0.12), x1 - x0, 0.76, fill=False, ec=INK, lw=1.2, ls=(0, (4, 2)),
                           hatch="////" if hatch else None))
    lab = u["name"] if tag is None else tag
    ax.text(x0 + 0.3, row + 0.1, lab, fontsize=7, color=INK, va="bottom",
            bbox=dict(fc="white", ec="none", pad=0.6) if tag else None)


fig = plt.figure(figsize=(15, 8.2), dpi=130)
gs = fig.add_gridspec(2, 2, height_ratios=[2.2, 1.35], hspace=0.06, wspace=0.34)

# 左：标注时
ax = fig.add_subplot(gs[0, 0]); candles(ax); buy_marks(ax, False)
ax.set_title("① 标注时：只有 K 线和你自己的标注（「对照 app」关）", loc="left", fontsize=10.5, color=INK)
rows_l = ["放量突破", "回落企稳", "底部横盘"]
bx = fig.add_subplot(gs[1, 0]); band_axes(bx, rows_l)
for u in USER:
    user_box(bx, rows_l.index(u["name"]), u)
bx.set_xlabel("你的框：虚线、不上色、按你起的名字分轨", fontsize=8, color=MUTED)

# 右：对照 app
ax2 = fig.add_subplot(gs[0, 1]); candles(ax2); buy_marks(ax2, True)
ax2.set_title("② 标完按「对照 app」：app 的输出照主视图原样画，你的框上贴判定", loc="left", fontsize=10.5, color=INK)
rows_r = ["match", "burst（你叫它：放量突破）", "tb（你叫它：回落企稳）", "还没放进 app 的"]
bx2 = fig.add_subplot(gs[1, 1]); band_axes(bx2, rows_r)
for s, e in MATCH:
    bx2.add_patch(Rectangle((s - OFF - 0.5, 0.35), e - s + 1, 0.3, color="#52525b"))
    bx2.text(s - OFF - 1.5, 0.5, "①", fontsize=8, ha="right", va="center", color=INK)
for node, s, e, tier in APP:
    row = rows_r.index(next(r for r in rows_r if r.startswith(node)))
    col = {"matched": BURST if node == "burst" else TB, "qualified": QUAL, "detected": DET}[tier]
    bx2.add_patch(Rectangle((s - OFF - 0.45, row + 0.2), e - s + 0.9, 0.6, color=col))
for i, u in enumerate(USER):
    row = rows_r.index(next(r for r in rows_r if u["role"] and r.startswith(u["role"]))) if u["role"] else 3
    tag, h = VERDICT[i]
    user_box(bx2, row, u, tag=tag, hatch=h)
bx2.set_xlabel("实心 = app 的事件（进了 match 用 node 本色，没进灰色）；虚线 = 你的框；判定写在框上，不靠颜色\n"
               "字样只写人话、不写阈值数字；右栏放说明、会话拿不准时的提问和可选的「放过（我标宽了）」", fontsize=8, color=MUTED)

out = HERE.parent / "mock_display.png"
fig.savefig(out, bbox_inches="tight", facecolor="white")
print("wrote", out)
