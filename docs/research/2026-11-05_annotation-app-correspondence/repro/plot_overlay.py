"""逐张图叠画:用户框/样本(黑) vs new_step 买入日与支撑线(暖色橙) vs 原型「站在新平台上」(冷色蓝)。
输出 repro/overlay_<SYM>.png 与 repro/overlay_all.png。配色:要分开的两方冷暖相反(橙/蓝),用户的东西用黑色。"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from common import load_state, load_win, d2i, i2d, EXCLUDED_SAMPLES  # noqa: E402
from tb_trace import run_trace  # noqa: E402
import proto_new_platform as proto  # noqa: E402

import path2_apps.new_step as app  # noqa: E402
from path2.eval import _resolve_end_events  # noqa: E402

plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
APP = "#c46a12"      # 暖:app
PROTO = "#1a80ba"    # 冷:原型,RGB(26,128,186)
INK = "#111111"
GRID = "#d0d0d0"

# 每张图的显示窗(终点放宽到能看见 app 那一长串买入日)
VIEW = {
    "CRNC": ("2024-08-01", "2025-04-04"),
    "GEVO": ("2024-06-20", "2024-11-15"),
    "INDO": ("2021-11-20", "2022-04-29"),
    "QBTS": ("2024-09-20", "2025-01-15"),
    "RGTI": ("2024-10-01", "2025-01-10"),
    "SMX": ("2025-09-25", "2025-12-31"),
}

s, fname = load_state()
p = app.load_params()
meta = app.eval_meta(p)
sample_letter = {}
for c in s["charts"]:
    for k, x in enumerate(c["samples"]):
        sample_letter[x["id"]] = "abcdefg"[k]


def draw(sym, ax, lane):
    c = next(cc for cc in s["charts"] if cc["symbol"] == sym)
    win = load_win(sym)
    v0, v1 = d2i(win, VIEW[sym][0]), d2i(win, VIEW[sym][1], "right") - 1
    xs = np.arange(v0, v1 + 1)
    hi_, lo_, cl = (win[k].values.astype(float) for k in ("high", "low", "close"))
    ax.vlines(xs, lo_[v0:v1 + 1], hi_[v0:v1 + 1], color="#9a9a9a", lw=0.8)
    ax.plot(xs, cl[v0:v1 + 1], color="#444444", lw=1.0)
    # 用户框:按框内高低价画虚线框
    for b in c["boxes"]:
        b0, b1 = d2i(win, b["start"]), d2i(win, b["end"])
        y0, y1 = lo_[b0:b1 + 1].min(), hi_[b0:b1 + 1].max()
        ax.add_patch(plt.Rectangle((b0 - 0.4, y0), b1 - b0 + 0.8, y1 - y0, fill=False, ls="--", lw=1.4, ec=INK))
        ax.text(max(b0, v0), y1, f" {fname[b['feature']]}", va="bottom", ha="left", fontsize=8, color=INK,
                bbox=dict(fc="#eeeeee", ec="none", pad=1))
    # app:命中里的支撑线 + 买入日
    res = app.analyze(win, p)
    buy = set()
    sup_drawn = set()
    for h in res.hits:
        if h.end_idx < v0 or h.start_idx > v1:
            continue
        for e in _resolve_end_events(h, meta["end_node"]):
            buy.update(range(e.start_idx, e.end_idx + 1))
        bo_idx = h.node_index["burst"].members[-1].end_idx
        burst = h.node_index["burst"]
        ax.axvspan(burst.start_idx - 0.5, burst.end_idx + 0.5, ymin=0.94, ymax=1.0, color=APP, lw=0)
        if bo_idx in sup_drawn:
            continue
        sup_drawn.add(bo_idx)
        rows, _, _ = run_trace(win, bo_idx, float(cl[bo_idx - 1]), max_rise_k=p.tb.max_rise_k, K=p.tb.stop_confirm_bars,
                               max_span=p.tb.max_span, vol_window=p.tb.vol_window)
        rx = [r[0] for r in rows]
        ry = [r[5] for r in rows]
        ax.step(rx, ry, where="post", color=APP, lw=1.6, ls="-")
    # 原型
    lc = np.log(cl)
    np_days = set()
    for (st, en) in proto.find_steps(lc):
        if en < v0 - 5 or en > v1:
            continue
        L, H, rr, _ = proto.new_platform_days(lc, st, en)
        days = [t for t, (ok, _) in rr.items() if ok]
        np_days.update(days)
        if days:
            ax.axvspan(st - 0.5, en + 0.5, ymin=0.87, ymax=0.93, color=PROTO, lw=0)
    ax.set_xlim(v0 - 1, v1 + 1)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.grid(axis="y", color=GRID, lw=0.5)
    ax.text(0.005, 0.97, sym, transform=ax.transAxes, fontsize=12, color=INK, va="top", fontweight="bold")
    ax.tick_params(labelbottom=False, labelsize=8)
    # 泳道:0 用户样本,1 app 买入日,2 原型站在新平台上
    for x in c["samples"]:
        t = d2i(win, x["date"])
        if not v0 <= t <= v1:
            continue
        excl = (sym, x["date"]) in EXCLUDED_SAMPLES
        lane.plot([t], [2], marker="^", ms=9, mfc="white" if excl else INK, mec=INK, ls="none")
        lane.text(t + 0.8, 2, sample_letter[x["id"]] + ("(排除)" if excl else ""), fontsize=8, va="center", color=INK)
        ax.axvline(t, color=INK, lw=0.6, ls=":")
    bx = sorted(t for t in buy if v0 <= t <= v1)
    lane.plot(bx, [1] * len(bx), marker="v", ms=6, color=APP, ls="none")
    px = sorted(t for t in np_days if v0 <= t <= v1)
    lane.plot(px, [0] * len(px), marker="s", ms=4, color=PROTO, ls="none")
    lane.set_yticks([0, 1, 2], ["原型: 站在新平台上", "app 买入日", "用户样本"], fontsize=8)
    lane.set_ylim(-0.7, 2.7)
    lane.set_xlim(v0 - 1, v1 + 1)
    ticks = np.linspace(v0, v1, 7).astype(int)
    lane.set_xticks(ticks, [i2d(win, t) for t in ticks], fontsize=8)
    lane.grid(axis="x", color=GRID, lw=0.5)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
        lane.spines[sp].set_visible(False)


def legend(fig):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    h = [Line2D([], [], ls="--", color=INK, label="用户框"),
         Line2D([], [], marker="^", color=INK, ls="none", label="用户样本"),
         Patch(color=APP, label="app 阶跃(进了 hit 的 burst,顶部色条)"),
         Line2D([], [], color=APP, lw=1.6, label="app 企稳机器的支撑线"),
         Line2D([], [], marker="v", color=APP, ls="none", label="app 买入日"),
         Patch(color=PROTO, label="原型认出的阶跃(顶部色条)"),
         Line2D([], [], marker="s", color=PROTO, ls="none", label="原型: 站在新平台上")]
    fig.legend(handles=h, loc="lower center", bbox_to_anchor=(0.5, 0.985 if fig.get_figheight() > 10 else 0.93), ncol=4, fontsize=9, frameon=False)


syms = list(VIEW)
fig = plt.figure(figsize=(16, 4.2 * len(syms)))
gs = fig.add_gridspec(len(syms) * 2, 1, height_ratios=[3, 1] * len(syms), hspace=0.35, top=0.975, bottom=0.02)
for k, sym in enumerate(syms):
    ax = fig.add_subplot(gs[2 * k])
    lane = fig.add_subplot(gs[2 * k + 1], sharex=ax)
    draw(sym, ax, lane)
legend(fig)
fig.savefig(HERE / "overlay_all.png", dpi=110, bbox_inches="tight", facecolor="white")
for sym in syms:
    f = plt.figure(figsize=(16, 5.2))
    g = f.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.12, top=0.9)
    a = f.add_subplot(g[0]); ln = f.add_subplot(g[1], sharex=a)
    draw(sym, a, ln)
    legend(f)
    f.savefig(HERE / f"overlay_{sym}.png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(f)
print("ok")
