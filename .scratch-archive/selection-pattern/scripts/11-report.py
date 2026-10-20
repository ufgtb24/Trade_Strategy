"""11 同日对照配对票 · 第七步：研究文件用的数表与图。

读 11-judge.py 存下的逐格判定（scratchpad/11/judge_*.csv.gz）、11-bias*.csv.gz、11-noise*.csv.gz、11-struct*.csv.gz。
输出：scripts/11-report-tables.txt；research/11-leak-heatmap.png、11-sweep.png、11-cost.png、11-struct.png
运行：uv run python .scratch/selection-pattern/scripts/11-report.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "research"
spec = importlib.util.spec_from_file_location("judge11", HERE / "11-judge.py")
judge = importlib.util.module_from_spec(spec); sys.modules["judge11"] = judge; spec.loader.exec_module(judge)
core = judge.core

CUR, REC = "M5", "K10"
plt.rcParams.update({"font.sans-serif": ["Noto Sans CJK JP", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "SimHei", "DejaVu Sans"],
                     "axes.unicode_minus": False, "font.size": 10})
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#52514e"
METRIC_SHORT = {"dir": "方向", "mag": "幅度", "R1_med": "持5日·典型", "R1_mean": "持5日·平均",
                "R2_med": "持20日·典型", "R2_mean": "持20日·平均", "R3_med": "持40日·典型", "R3_mean": "持40日·平均",
                "R4_med": "波动线k2·典型", "R4_mean": "波动线k2·平均", "R5_med": "波动线k5·典型",
                "R5_mean": "波动线k5·平均", "R6_med": "−8/+20%·典型", "R6_mean": "−8/+20%·平均"}
ADDED_NAME = {"tiltM+1.0": "偏爱当天高波动（平滑）", "tiltM-1.0": "偏爱当天低波动（平滑）",
              "tiltH+1.0": "偏爱平时高波动（平滑）", "tiltH-1.0": "偏爱平时低波动（平滑）",
              "tiltM+0.5": "略偏当天高波动", "tiltM-0.5": "略偏当天低波动",
              "tiltH+0.5": "略偏平时高波动", "tiltH-0.5": "略偏平时低波动",
              "M_87_97": "当天 M 排 87–97%", "M_03_13": "当天 M 排 3–13%",
              "H_87_97": "平时波动排 87–97%", "H_03_13": "平时波动排 3–13%"}
NAME = {**judge.CLS_NAME, **ADDED_NAME}


def fmt_pp(m, v):
    return f"{v:+.3f}" if m == "dir" else f"{v * 100:+.2f}"


def load():
    th, jit = judge.thresholds()
    jc = pd.read_csv(core.SCR / "judge_cells.csv.gz")
    jf = pd.read_csv(core.SCR / "judge_fair.csv.gz")
    jt = pd.read_csv(core.SCR / "judge_trim.csv.gz")
    nz = pd.read_csv(HERE / "11-noise.csv.gz")
    nx = HERE / "11-noise-K5-K10.csv.gz"
    if nx.exists():
        n2 = pd.read_csv(nx)
        nz = pd.concat([nz, n2[n2.scheme == "K5"]], ignore_index=True)
    return th, jit, jc, jf, jt, nz


def scheme_table(jc, jf, jt, nz, jit):
    rows = []
    n2 = nz[nz.Y == 2]
    h0 = np.sqrt((n2[n2.scheme == "M5"]["hsd_dir"] ** 2).mean())
    for s, g in n2.groupby("scheme"):
        h = np.sqrt((g["hsd_dir"] ** 2).mean()); c = np.sqrt((g["csd_dir"] ** 2).mean())
        hR = np.sqrt((g["hsd_R3_med"] ** 2).mean()); cR = np.sqrt((g["csd_R3_med"] ** 2).mean())
        hR0 = np.sqrt((n2[n2.scheme == "M5"]["hsd_R3_med"] ** 2).mean())

        def cnt(j):
            x = j[j.scheme == s]
            if not len(x):
                return "—", "—"
            f = int(x.fail_a.sum() + x.fail_b.sum())
            cf = int((x.fail_a & ~x.unclear_a).sum() + (x.fail_b & ~x.unclear_b).sum())
            return f"{f}/{2 * len(x)}", str(cf)

        a, b, cc = cnt(jc), cnt(jf), cnt(jt)
        rows.append(dict(scheme=s, name=judge.SCHEME_NAME.get(s, s), pre=a[0], pre_clear=a[1], fair=b[0],
                         fair_clear=b[1], trim=cc[0], trim_clear=cc[1],
                         jit_max=max(jit[s].values()), jit_dir=jit[s]["dir"],
                         noise_dir=np.sqrt(h ** 2 + c ** 2) / h0 - 1, noise_R3=np.sqrt(hR ** 2 + cR ** 2) / hR0 - 1,
                         lt10=g.lt10.mean(), lt20=g.lt20.mean()))
    order = ["M5", "M10", "M20", "M3xH3", "M5xH5", "M10xH3", "M10xH5", "M20xH3", "K100", "K50", "K20", "K10", "K5"]
    return pd.DataFrame(rows).set_index("scheme").loc[[o for o in order if o in {r["scheme"] for r in rows}]]


def heatmap(jf, th, path):
    cls = ["M_top2", "M_bot2", "H_top10", "H_bot10",
           "tiltM+1.0", "tiltM-1.0", "tiltH+1.0", "tiltH-1.0", "M_87_97", "M_03_13", "H_87_97", "H_03_13",
           "bb_clust", "Hhi_Mmid", "Mhi_Hmid", "Hlo_Mmid", "Mlo_Hmid"]
    seps = [4, 12, 13]      # 两头 | 平滑偏好与错开档界的窗口 | 扎堆型 | 样本小的组合类
    x = jf[jf.form.isin(["full", "clust"])]
    fig, axes = plt.subplots(1, 2, figsize=(17, 9.5), sharey=True)
    for ax, s, title in ((axes[0], CUR, judge.SCHEME_NAME[CUR]),
                         (axes[1], REC, f"推荐：同一天波动最近的 10 只（{REC}）")):
        g = x[x.scheme == s].set_index(["cls", "metric"])
        M = np.full((len(cls), len(core.METRICS)), np.nan)
        U = np.zeros_like(M, bool)
        for i, c in enumerate(cls):
            for j, m in enumerate(core.METRICS):
                if (c, m) in g.index:
                    r = g.loc[(c, m)]
                    M[i, j] = max(r.norm_a, r.norm_b)
                    U[i, j] = bool((r.fail_a and r.unclear_a) or (r.fail_b and r.unclear_b)) and \
                        not ((r.fail_a and not r.unclear_a) or (r.fail_b and not r.unclear_b))
        L = np.log10(np.clip(M, 0.1, 100))
        ax.imshow(L, cmap="Blues", vmin=-0.3, vmax=2.0, aspect="auto")
        for i in range(len(cls)):
            for j in range(len(core.METRICS)):
                v = M[i, j]
                if not np.isfinite(v):
                    continue
                txt = "≤1" if v <= 1 else (f"{v:.0f}" if v >= 10 else f"{v:.1f}")
                if U[i, j]:
                    txt += "?"
                ax.text(j, i, txt, ha="center", va="center", fontsize=8,
                        color="white" if L[i, j] > 1.2 else "#0b0b0b",
                        fontweight="bold" if v > 1 else "normal")
        ax.set_xticks(range(len(core.METRICS)))
        ax.set_xticklabels([METRIC_SHORT[m] for m in core.METRICS], rotation=60, ha="right")
        ax.set_title(title, fontsize=12)
        ax.set_yticks(range(len(cls)))
        ax.set_yticklabels([NAME.get(c, c) + ("（样本小）" if c in ("Hhi_Mmid", "Mhi_Hmid", "Hlo_Mmid", "Mlo_Hmid") else "")
                            for c in cls])
        for y in seps:
            ax.axhline(y - 0.5, color="#0b0b0b", lw=1.5)
    fig.suptitle("只偏爱某种波动、毫无本事的假 pattern 白得多少领先——以「线」为单位（≤1 = 挡住了；数字越大漏得越多）\n"
                 "每格取「合并 ÷ 合并线」和「最坏一年 ÷ 分年线」中较大的那个；「?」= 超线但离线不到 2 倍抽样误差，判不清",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def sweep(bias, th, path):
    mets = ["dir", "mag", "R3_med", "R1_med"]
    fig, axes = plt.subplots(2, 4, figsize=(17, 7.5))
    for r, pre in enumerate(["Mdec", "Hdec"]):
        for c, m in enumerate(mets):
            ax = axes[r, c]
            sc = 1 if m == "dir" else 100
            lim = th[m]["s2"] / 3 * sc
            ax.axhspan(-lim, lim, color="#cde2fb", zorder=0)
            ax.axhline(0, color=GRAY, lw=0.8)
            for s, col, mk, ls in ((CUR, ORANGE, "s", "--"), (REC, BLUE, "o", "-")):
                f = bias[(bias.form == "full") & (bias.scope == "all") & (bias.scheme == s)]
                y = [f[f.cls == f"{pre}{k}"][m].mean() * sc for k in range(1, 11)]
                ax.plot(range(1, 11), y, color=col, marker=mk, ls=ls, lw=2, ms=6,
                        label=("现行 " if s == CUR else "推荐 ") + s)
            ax.set_xticks(range(1, 11))
            ax.set_xlabel(("当天 M" if pre == "Mdec" else "平时波动") + "在池内的十档（1 = 最低）")
            unit = "方向值" if m == "dir" else "百分点"
            ax.set_title(f"{METRIC_SHORT[m]}（{unit}）")
            if c == 0 and r == 0:
                ax.legend(frameon=False, loc="upper left")
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
    fig.suptitle("只买某一档波动的股票（整档全算，2021-11..2025-11 合并）白得的领先；浅蓝带 = 合并线（2 年偶然波动的 1/3）\n"
                 "上排锯齿：现行五档每档里还有「偏低的一半」和「偏高的一半」，只买其中一半就白得或白丢", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def cost_plot(st, path):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, col, title in ((axes[0], "fair_clear", "全部不卡档界的假 pattern"),
                           (axes[1], "trim_clear", "只看不在两头 2% 的买点")):
        for s, r in st.iterrows():
            if r[col] == "—":
                continue
            x = r.noise_dir * 100; y = int(r[col])
            hi = s in (CUR, REC)
            ax.scatter(x, y, s=70 if hi else 40, color=BLUE if s == REC else (ORANGE if s == CUR else GRAY),
                       zorder=3, edgecolor="white", lw=1.5)
            off = {"M10xH5": (-55, -14), "M5xH5": (8, -3), "M20xH3": (8, 9), "M10xH3": (-55, 8),
                   "K100": (6, 6), "M3xH3": (-50, 4), "M10": (6, -2)}.get(s, (5, 4))
            ax.annotate(s, (x, y), textcoords="offset points", xytext=off, fontsize=9,
                        fontweight="bold" if hi else "normal")
        ax.set_xlim(-4, 19)
        ax.set_xlabel("偶然波动因对照变抖而放大（%，方向，2 年分散 1000 个/年）")
        ax.set_ylabel("明确没挡住的格数（超线且离线 ≥ 2 倍误差）")
        ax.set_title(title)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    fig.suptitle("代价与收益：越往左下越好（对照抖得少、漏得少）", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def struct_tables(path_png):
    f = HERE / "11-struct-K10.csv.gz"
    df = pd.read_csv(f if f.exists() else HERE / "11-struct.csv.gz", dtype={"scope": str})
    s = REC if f.exists() else "K20"
    df = df[df.scheme == s].copy()
    for v in ["A1", "A2", "A3"]:
        for t in ("med", "mean"):
            df[f"b_{v}_{t}"] = df[f"{v}_{t}"] - df[f"A0_{t}"]
    cols = [f"b_{v}_{t}" for v in ["A1", "A2", "A3"] for t in ("med", "mean")]
    g = df.groupby(["cls", "scope"])[cols + ["A0_med", "A0_mean"]]
    mean = g.mean() * 100; se = g.std(ddof=1) / np.sqrt(df.rep.nunique()) * 100
    # 图：随当天 M 十档
    dec = [f"rand_Mdec{k}" for k in range(1, 11)]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    for ax, t, vs, ttl in ((axes[0], "med", ["A1", "A3"], "典型一笔：同比例 vs 移植"),
                           (axes[1], "med", ["A2"], "典型一笔：固定倍数（注意纵轴大得多）"),
                           (axes[2], "mean", ["A1", "A2", "A3"], "平均一笔：三种替代")):
        ax.axhline(0, color=GRAY, lw=0.8)
        for v, col, mk, ls in (("A1", ORANGE, "s", "--"), ("A2", GRAY, "^", ":"), ("A3", BLUE, "o", "-")):
            if v not in vs:
                continue
            y = [mean.loc[(d, "all"), f"b_{v}_{t}"] for d in dec]
            ax.plot(range(1, 11), y, color=col, marker=mk, ls=ls, lw=2, ms=6,
                    label={"A1": "同比例", "A2": "固定倍数", "A3": "移植"}[v])
        ax.set_xticks(range(1, 11)); ax.set_xlabel("买点当天 M 在池内的十档")
        ax.set_ylabel("替代带来的偏差（百分点）"); ax.set_title(ttl); ax.legend(frameon=False)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    fig.suptitle(f"结构位规则（20 日最低价止损、60 日最高价止盈）：对照换成替代说法后多出来的领先（配对 {s}，无偏好随机买点）\n"
                 "每档约 380 个买点 × 20 次，相邻档之间的锯齿多半是抽样起伏；同比例与移植两条线几乎重合", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path_png, dpi=130)
    plt.close(fig)
    return s, mean, se


def main():
    th, jit, jc, jf, jt, nz = load()
    bias = pd.concat([pd.read_csv(HERE / "11-bias.csv.gz", dtype={"scope": str}),
                      pd.read_csv(HERE / "11-bias-K5.csv.gz", dtype={"scope": str})], ignore_index=True)
    b2 = pd.read_csv(HERE / "11-bias2.csv.gz", dtype={"scope": str})
    out = []
    out.append("## T1 判据的线（方向为方向值，其余为百分点）")
    out.append("| 尺子 | 1 年偶然波动 | 2 年偶然波动 | 合并线（2 年 ÷ 3） | 分年线（1 年） |")
    out.append("|---|---|---|---|---|")
    for m in core.METRICS:
        sc = 1 if m == "dir" else 100
        out.append(f"| {METRIC_SHORT[m]} | {th[m]['s1'] * sc:.3f} | {th[m]['s2'] * sc:.3f} | {th[m]['s2'] / 3 * sc:.3f} | {th[m]['s1'] * sc:.3f} |")
    st = scheme_table(jc, jf, jt, nz, jit)
    out.append("\n## T2 各配对：没挡住的格数（失败 / 总格数；括号外第二列是「明确没挡住」）与代价")
    out.append("| 配对 | 事先那组 | 明确 | 不卡档界那组 | 明确 | 剔两头后 | 明确 | 对照抖动÷买点侧（最大 / 方向） | 偶然波动放大（方向 / 持40日典型） | 买点对照 <10 / <20 只 |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for s, r in st.iterrows():
        out.append(f"| {s} {r['name']} | {r.pre} | {r.pre_clear} | {r.fair} | {r.fair_clear} | {r.trim} | {r.trim_clear} | "
                   f"{r.jit_max:.2f} / {r.jit_dir:.2f} | {r.noise_dir * 100:+.1f}% / {r.noise_R3 * 100:+.1f}% | "
                   f"{r.lt10 * 100:.0f}% / {r.lt20 * 100:.0f}% |")
    # T3 现行 vs 推荐，逐类逐尺子
    allf = pd.concat([jf[jf.scheme.isin([CUR, REC])],
                      jc[jc.cls.isin(["M_top10", "M_bot10"]) & jc.scheme.isin([CUR, REC])]], ignore_index=True)
    cls_order = ["M_top2", "M_top10", "M_bot10", "M_bot2", "H_top10", "H_bot10", "Hhi_Mmid", "Mhi_Hmid", "Hlo_Mmid",
                 "Mlo_Hmid", "tiltM+1.0", "tiltM-1.0", "tiltH+1.0", "tiltH-1.0", "M_87_97", "M_03_13", "H_87_97",
                 "H_03_13", "bb_clust"]
    for grp, mets in (("体检尺子", ["dir", "mag"]),
                      ("主尺子·典型一笔", [f"R{i}_med" for i in range(1, 7)]),
                      ("主尺子·平均一笔", [f"R{i}_mean" for i in range(1, 7)])):
        out.append(f"\n## T3 {grp}：整类全算（扎堆型为 40 次平均）的白得领先，现行 {CUR} → 推荐 {REC}；"
                   "格内为「合并（最坏一年）」，方向为方向值、其余为百分点；* = 超线")
        out.append("| 假 pattern | " + " | ".join(METRIC_SHORT[m] for m in mets) + " |")
        out.append("|---|" + "---|" * len(mets))
        out.append("| 合并线 / 分年线 | " + " | ".join(
            f"{fmt_pp(m, th[m]['s2'] / 3).lstrip('+')} / {fmt_pp(m, th[m]['s1']).lstrip('+')}" for m in mets) + " |")
        for c in cls_order:
            cells = []
            for m in mets:
                parts = []
                for s in (CUR, REC):
                    x = allf[(allf.cls == c) & (allf.scheme == s) & (allf.metric == m) & allf.form.isin(["full", "clust"])]
                    if not len(x):
                        parts.append("—"); continue
                    r = x.iloc[0]
                    star = "*" if (r.fail_a or r.fail_b) else ""
                    parts.append(f"{fmt_pp(m, r['all'])}（{fmt_pp(m, r.worst_val)}）{star}")
                cells.append(" → ".join(parts))
            out.append(f"| {NAME.get(c, c)} | " + " | ".join(cells) + " |")
    # T4 分年与去掉 2022：几类关键假 pattern
    out.append(f"\n## T4 分年与去掉 2022 年（整类全算；扎堆型 40 次平均）：现行 {CUR} / 推荐 {REC}")
    allb = pd.concat([bias, b2[~b2.trim.astype(bool)]], ignore_index=True)
    for c in ["bb_clust", "H_top10", "M_top2", "tiltH+1.0", "tiltM+1.0", "Hhi_Mmid"]:
        for m in ["dir", "mag", "R3_med", "R5_med", "R3_mean"]:
            row = []
            for s in (CUR, REC):
                x = allb[(allb.cls == c) & (allb.scheme == s) & allb.form.isin(["full", "clust"])].set_index("scope")
                row.append(" ".join(f"{sc}:{fmt_pp(m, x.loc[sc, m])}" for sc in
                                    ["2021", "2022", "2023", "2024", "2025", "all", "ex2022"] if sc in x.index))
            out.append(f"- {NAME.get(c, c)} · {METRIC_SHORT[m]}：现行 {row[0]}｜推荐 {row[1]}")
    # T5 检查用
    out.append(f"\n## T5 检查用假 pattern（成交额、价格；整类全算）：合并（最坏一年），现行 {CUR} → 推荐 {REC}")
    chk = pd.read_csv(core.SCR / "judge_checks.csv.gz")
    for c in judge.CHECKS:
        cells = []
        for m in ["dir", "mag", "R3_med", "R3_mean", "R5_mean"]:
            p = []
            for s in (CUR, REC):
                x = chk[(chk.cls == c) & (chk.scheme == s) & (chk.metric == m) & (chk.form == "full")].iloc[0]
                p.append(f"{fmt_pp(m, x['all'])}（{fmt_pp(m, x.worst_val)}）")
            cells.append(f"{METRIC_SHORT[m]} " + " → ".join(p))
        x = allb[(allb.cls == c) & (allb.scheme == REC) & (allb.form == "full")].set_index("scope")
        yrs = " ".join(f"{y}:{x.loc[y, 'dir']:+.3f}" for y in ["2021", "2022", "2023", "2024", "2025"])
        out.append(f"- {NAME[c]}：" + "；".join(cells) + f"；推荐配对下方向逐年 {yrs}")
    # T6 结构位替代
    s, mean, se = struct_tables(RES / "11-struct.png")
    out.append(f"\n## T6 结构位规则的替代偏差（配对 {s}，分散长相每年 1000 个、20 次平均；百分点；± 为 20 次之间的误差，"
               "低估了数据本身的误差）")
    out.append("| 买点 | 范围 | 对照用自己结构位时的领先（典型 / 平均） | 同比例（典型 / 平均） | 固定倍数（典型 / 平均） | 移植（典型 / 平均） |")
    out.append("|---|---|---|---|---|---|")
    for c in ["rand", "M_top10", "M_bot10", "H_top10", "H_bot10"]:
        for scp in ["all", "2022", "2023", "2024", "2025", "ex2022"]:
            if (c, scp) not in mean.index:
                continue
            r = mean.loc[(c, scp)]; e = se.loc[(c, scp)]
            out.append(f"| {NAME.get(c, c)} | {scp} | {r.A0_med:+.2f} / {r.A0_mean:+.2f} | "
                       + " | ".join(f"{r[f'b_{v}_med']:+.2f}±{e[f'b_{v}_med']:.2f} / {r[f'b_{v}_mean']:+.2f}±{e[f'b_{v}_mean']:.2f}"
                                    for v in ["A1", "A2", "A3"]) + " |")
    out.append("按买点当天 M 十档（无偏好随机，全期）：")
    for k in range(1, 11):
        r = mean.loc[(f"rand_Mdec{k}", "all")]
        out.append(f"- 第 {k} 档：同比例 {r.b_A1_med:+.2f} / {r.b_A1_mean:+.2f}；固定倍数 {r.b_A2_med:+.2f} / {r.b_A2_mean:+.2f}；"
                   f"移植 {r.b_A3_med:+.2f} / {r.b_A3_mean:+.2f}")
    # T7 折算到每月
    out.append(f"\n## T7 典型一笔的白得领先折算到每月（领先 × 21 ÷ 买点平均持有天数；推荐 {REC}，整类全算合并）")
    hold = bias[(bias.form == "full") & (bias.scope == "all") & (bias.scheme == REC)].set_index("cls")
    for c in ["M_top2", "H_top10", "Hhi_Mmid", "Mhi_Hmid", "PX_bot10", "DV_top10"]:
        if c not in hold.index:
            continue
        r = hold.loc[c]
        cells = [f"{k} {r[f'{k}_med'] * 100 * 21 / r[f'hold_{k}']:+.2f}（持 {r[f'hold_{k}']:.0f} 日）" for k in core.RULES]
        out.append(f"- {NAME[c]}：" + "；".join(cells))
    (HERE / "11-report-tables.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    heatmap(jf, th, RES / "11-leak-heatmap.png")
    sweep(bias, th, RES / "11-sweep.png")
    cost_plot(st, RES / "11-cost.png")


if __name__ == "__main__":
    main()
