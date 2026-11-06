"""折叠行示意图（合成数据，不读任何行情）。

造一次 new_step 式的阶跃：旧平台 15 根、阶跃 2 根（两个前缀 e=20、e=21），新平台上每天一个 plateau 实例，
画「现在一实例一行」和「折叠后一族一行」两种样子，选中同一个 hit（前缀 e=21、当天 t=31）。

输出：同目录 mock_fold.png。只为讨论界面，不代表任何真实股票。
配色按用户色盲规则：in_hit 用中蓝 (26,128,186)；qualified 深灰、detected 浅灰，且档位同时用格子高度区分；
选中描边用深色实线；「当前日」竖线用和选中框同一种深色、两侧加白边，压在任何色块上都和底下拉开深浅。
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon

plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]

BLUE = (26 / 255, 128 / 255, 186 / 255)
QUAL = "#9ca3af"
DET = "#d1d5db"
AMBER = "#F2C25C"
EDGE = "#1e293b"
CURSOR = "#1e293b"
STEM = "#6b7280"
MONO = "DejaVu Sans Mono"

L, S = 15, 20
OLD = (S - L, S - 1)
PREFIXES = [20, 21]
T_MAX = 40
HIT_DAYS = [25, 26, 27, 31, 32, 36, 38]          # 只有前缀 e=21 的这些天成 hit
TODAY_QUAL = {23, 28, 29, 33, 35, 39}            # today 自己的诊断 where（收阳）过了的天
SEL_T, SEL_E = 31, 21

# ── 合成实例 ──
plateau = []  # (e, start, end, tier)
newplat = []
for e in PREFIXES:
    for t in range(e + 2, T_MAX + 1):
        hit = e == SEL_E and t in HIT_DAYS
        plateau.append((e, OLD[0], t, "in_hit" if hit else "detected"))
        newplat.append((e, e + 1, t - 1, "in_hit" if hit else "qualified"))
steps = [(e, S, e, "in_hit" if e == SEL_E else "detected") for e in PREFIXES]
today = []
for t in range(min(PREFIXES) + 2, T_MAX + 1):
    tier = "in_hit" if t in HIT_DAYS else ("qualified" if t in TODAY_QUAL else "detected")
    today.append((None, t, t, tier))
hits = [(SEL_E, OLD[0], t) for t in HIT_DAYS]

COLOR = {"in_hit": BLUE, "qualified": QUAL, "detected": DET}
HFRAC = {"in_hit": 1.0, "qualified": 0.62, "detected": 0.34}

ROW = 1.0
BAR_H = 0.72


def band_title(ax, y, name):
    ax.text(-1.2, y, name, ha="right", va="center", fontsize=9, family=MONO)


def sep(ax, y, x1=46):
    ax.plot([-0.5, x1], [y, y], color="#cbd5e1", lw=1.0)


# ─────────── 左：现状（一实例一行）───────────
def draw_current(ax):
    y = 0.0
    rows = []

    def bar(x0, x1, yy, color, sel=False, group=False):
        ax.add_patch(Rectangle((x0 - 0.4, yy - BAR_H / 2), x1 - x0 + 0.8, BAR_H, color=color, lw=0))
        if sel or group:
            ax.add_patch(Rectangle((x0 - 0.4, yy - BAR_H / 2 - 0.12), x1 - x0 + 0.8, BAR_H + 0.24,
                                   fill=False, ec=EDGE, lw=2.4 if sel else 1.4))

    # bracket
    start_y = y
    for (e, s0, t) in hits:
        bar(s0, t, y, AMBER, group=(t == SEL_T))
        ax.add_patch(Polygon([[t - 0.4, y + 0.3], [t + 0.4, y + 0.3], [t, y - 0.3]], color="black"))
        y += ROW
    band_title(ax, (start_y + y - ROW) / 2, "bracket")
    sep(ax, y - 0.4)
    y += 0.4
    # plateau
    start_y = y
    for (e, s0, t, tier) in sorted(plateau, key=lambda r: (r[2], r[0])):
        bar(s0, t, y, COLOR[tier], group=(e == SEL_E and t == SEL_T))
        y += ROW
    band_title(ax, (start_y + y - ROW) / 2, "plateau")
    sep(ax, y - 0.4)
    y += 0.4
    # old_plat
    bar(OLD[0], OLD[1], y, BLUE, group=True)
    band_title(ax, y, "old_plat")
    y += ROW
    sep(ax, y - 0.4)
    y += 0.4
    start_y = y
    for (e, s0, t, tier) in steps:
        bar(s0, t, y, COLOR[tier], group=(e == SEL_E))
        y += ROW
    band_title(ax, (start_y + y - ROW) / 2, "step")
    sep(ax, y - 0.4)
    y += 0.4
    start_y = y
    for (e, s0, t, tier) in sorted(newplat, key=lambda r: (r[1], r[2])):
        bar(s0, t, y, COLOR[tier], group=(e == SEL_E and t == SEL_T - 1))
        y += ROW
    band_title(ax, (start_y + y - ROW) / 2, "new_plat")
    sep(ax, y - 0.4)
    y += 0.4
    for (_, s0, t, tier) in today:
        ax.add_patch(Polygon([[t - 0.4, y - 0.3], [t + 0.4, y - 0.3], [t, y + 0.35]], color=COLOR[tier],
                             ec=EDGE if t == SEL_T else None, lw=2.0 if t == SEL_T else 0))
    band_title(ax, y, "today")
    y += ROW
    ax.set_ylim(y, -1.2)
    ax.set_xlim(-0.5, 46)
    ax.set_title("现状：一个实例一行（同一次 hit 选中，边框散在 80 多行里）", fontsize=11, loc="left")


# ─────────── 右：折叠后（一族一行）───────────
def draw_folded(ax):
    y = 0.0
    RH = 1.25          # 折叠行比普通 lane 高一点
    CELL_W = 0.78
    def fold_row(start, cells, yy, sel_end=None, focus=False):
        """cells: {end: (tier, count)}。多成员族：每个成员一格立在终点，族跨度只由底部细线表达；
        单成员族：照旧一根整条（族起点 → 它的终点）。"""
        last = max(cells)
        single = len(cells) == 1 and list(cells.values())[0][1] == 1
        base = yy + RH * 0.42
        if not single:
            ax.plot([start - 0.4, last + 0.4], [base, base], color=STEM, lw=1.0, solid_capstyle="butt", zorder=0.8)
        for x, (tier, cnt) in cells.items():
            h = RH * 0.8 * HFRAC[tier]
            x0 = (start - CELL_W / 2) if single else (x - CELL_W / 2)
            w = (x - start + CELL_W) if single else CELL_W
            ax.add_patch(Rectangle((x0, base - h), w, h, color=COLOR[tier], lw=0))
        if sel_end is not None:
            top = base - RH * 0.8 - 0.12
            ax.add_patch(Rectangle((start - 0.45, top), sel_end - start + 0.9, base - top + 0.12,
                                   fill=False, ec=EDGE, lw=1.4))
            tier, _ = cells[sel_end]
            h = RH * 0.8 * HFRAC[tier]
            x0 = (start - CELL_W / 2) if single else (sel_end - CELL_W / 2)
            w = (sel_end - start + CELL_W) if single else CELL_W
            ax.add_patch(Rectangle((x0 - 0.08, base - h - 0.08), w + 0.16, h + 0.16,
                                   fill=False, ec=EDGE, lw=2.6))

    rows_y = {}
    # bracket（一族：hit 同起点）：和 band 同一种画法——每个 hit 一格立在终点，族跨度只由底线表达；▼ = 买入日
    base = y + RH * 0.42
    last = max(HIT_DAYS)
    first = min(HIT_DAYS)
    BH = RH * 0.8
    ax.plot([OLD[0] - 0.4, last + 0.4], [base, base], color=STEM, lw=1.0, zorder=0.8)
    for t in HIT_DAYS:
        ax.add_patch(Rectangle((t - CELL_W / 2, base - BH), CELL_W, BH, color=AMBER, lw=0))
    for t in HIT_DAYS:
        ax.add_patch(Polygon([[t - 0.32, base - BH + 0.05], [t + 0.32, base - BH + 0.05], [t, base - BH * 0.45]],
                             color="black", zorder=3))
    # 选中 hit：跨度空心细框 + 它那一格粗框
    ax.add_patch(Rectangle((OLD[0] - 0.45, base - BH - 0.12), SEL_T - OLD[0] + 0.9, BH + 0.24,
                           fill=False, ec=EDGE, lw=1.4))
    ax.add_patch(Rectangle((SEL_T - CELL_W / 2 - 0.08, base - BH - 0.08), CELL_W + 0.16, BH + 0.16,
                           fill=False, ec=EDGE, lw=2.6))
    # 当家行：底线加深加粗（刚才点的是这一行，←/→ 在这一行里走）
    ax.plot([OLD[0] - 0.4, last + 0.4], [base + 0.1, base + 0.1], color=EDGE, lw=2.6, zorder=3)
    band_title(ax, base - RH * 0.25, "bracket")
    rows_y["bracket"] = (y, y + RH)
    y += RH
    sep(ax, y)
    y += 0.25
    # plateau：一族（所有前缀同起点）
    cells = {}
    for (e, s0, t, tier) in plateau:
        old = cells.get(t)
        rank = {"detected": 0, "qualified": 1, "in_hit": 2}
        if old is None:
            cells[t] = (tier, 1)
        else:
            best = tier if rank[tier] > rank[old[0]] else old[0]
            cells[t] = (best, old[1] + 1)
    fold_row(OLD[0], dict(sorted(cells.items())), y, sel_end=SEL_T)
    band_title(ax, y + RH * 0.2, "plateau")
    y += RH
    sep(ax, y)
    y += 0.25
    # old_plat：单个对象
    base = y + RH * 0.42
    ax.add_patch(Rectangle((OLD[0] - 0.4, base - RH * 0.8), OLD[1] - OLD[0] + 0.8, RH * 0.8, color=BLUE, lw=0))
    ax.add_patch(Rectangle((OLD[0] - 0.45, base - RH * 0.8 - 0.1), OLD[1] - OLD[0] + 0.9, RH * 0.8 + 0.2,
                           fill=False, ec=EDGE, lw=1.4))
    band_title(ax, y + RH * 0.2, "old_plat")
    y += RH
    sep(ax, y)
    y += 0.25
    # step：一族（同起点 s）
    fold_row(S, {e: (tier, 1) for (e, s0, _, tier) in steps}, y, sel_end=SEL_E)
    band_title(ax, y + RH * 0.2, "step")
    y += RH
    sep(ax, y)
    y += 0.25
    # new_plat：每个前缀一族（起点不同），两行
    for e in PREFIXES:
        fam = {t: (tier, 1) for (ee, s0, t, tier) in newplat if ee == e}
        fold_row(e + 1, dict(sorted(fam.items())), y, sel_end=(SEL_T - 1) if e == SEL_E else None)
        y += RH
    band_title(ax, y - RH * 1.1, "new_plat")
    sep(ax, y)
    y += 0.25
    # today：点事件，本来就一行
    base = y + RH * 0.42
    for (_, s0, t, tier) in today:
        h = 0.62 * HFRAC[tier] + 0.18
        ax.add_patch(Polygon([[t - 0.4, base - h], [t + 0.4, base - h], [t, base]], color=COLOR[tier],
                             ec=EDGE if t == SEL_T else None, lw=2.4 if t == SEL_T else 0))
    band_title(ax, y + RH * 0.2, "today")
    y += RH
    # 当前日竖线
    import matplotlib.patheffects as pe
    ax.plot([SEL_T, SEL_T], [-0.3, y], color=CURSOR, lw=1.0, zorder=4,
            path_effects=[pe.Stroke(linewidth=3.2, foreground="white"), pe.Normal()])
    ax.text(SEL_T, -0.45, "t", color="black", ha="center", va="bottom", fontsize=9, family=MONO)
    ax.set_ylim(y + 0.3, -1.4)
    ax.set_xlim(-0.5, 46)
    ax.set_title("折叠后：一族一行，选中 = 跨度描边 + 那一格粗框 + 当前日竖线", fontsize=11, loc="left")

    return y


fig, axes = plt.subplots(1, 2, figsize=(17, 11), gridspec_kw={"width_ratios": [1, 1]})
for ax in axes:
    ax.set_yticks([])
    ax.set_xticks(range(0, 46, 5))
    ax.tick_params(axis="x", labelsize=8)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
draw_current(axes[0])
draw_folded(axes[1])
axes[1].set_position([0.55, 0.42, 0.43, 0.52])

# 右下：图例与读法
lg = fig.add_axes([0.55, 0.05, 0.43, 0.3])
lg.axis("off")
items = [
    (BLUE, 1.0, "in_hit：满高、node 本色"),
    (QUAL, 0.62, "qualified：中高、深灰"),
    (DET, 0.34, "detected：矮、浅灰"),
]
for i, (c, h, txt) in enumerate(items):
    lg.add_patch(Rectangle((0.02, 0.88 - i * 0.12), 0.025, 0.08 * h, color=c, transform=lg.transAxes))
    lg.text(0.06, 0.9 - i * 0.12, txt, fontsize=10, transform=lg.transAxes, va="center")
notes = [
    "多成员的族：每个成员一格，立在各自终点上；只有一个成员时照旧画整条（如 old_plat）",
    "底部灰色细线 = 族从起点到最后一个成员终点，不表示档位",
    "23~40 每格其实有 2 个成员（两个阶跃前缀同一天），格子取较深的档位，悬停列全部、步进逐个走",
    "选中成员：从族起点到它终点的细实线框（它的完整跨度）+ 它那一格粗框",
    "深色细竖线（两侧白边）= 当前日；bracket 行底下的粗黑线 = 当家行，←/→ 在这一行里走",
]
for i, n in enumerate(notes):
    lg.text(0.02, 0.5 - i * 0.1, n, fontsize=10, transform=lg.transAxes, va="center")

out = Path(__file__).with_name("mock_fold.png")
fig.savefig(out, dpi=110, bbox_inches="tight")
print(out)
