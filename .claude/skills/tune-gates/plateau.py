# -*- coding: utf-8 -*-
"""平台检测器 + 复核图:逐闸阈值调参的判定与可视化(tune-gates skill 核心脚本)。

输入 CSV 宽表(每行 = 某闸的一个档位):
    gate,x,fr,fp,match[,se_fr,se_fp][,fr_y1,fp_y1,match_y1,fr_y2,fp_y2,match_y2]
    gate   闸名;x 档位值(可不均匀);fr/FP 主指标;match 样本数
    se_*   峰值容差用(provided 模式);缺省走 relative 模式
    *_y1/*_y2  分年列(可选;提供后判「分年平台交集」)

判据(全部数值化,不依赖看图):
    平台   = 「>= 峰值 - 容差」的最大连通档位区间;容差 = 峰值处 se(provided)
             或 |峰值|*rel_tol(relative)
    交集   = fr 平台 ∩ FP 平台;分年列存在时再 ∩ 各年 fr 平台 = 稳健交集
    推荐   = 稳健交集(无则总交集)中心最近的实际档位
    警告   = 交集空 / 交集过窄(<=2 档) / 峰值贴边 / 分年无交集 / match 破线

输出: OUT_DIR 下 verdicts.json(机器读) + verdicts.md(人读) + <gate>.png(复核图)。
图只给人复核;判定一律以数值输出为准。
"""
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def load(csv_path):
    """读宽表 → {gate: {列名: list[float]}}(按 x 升序)。"""
    gates = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            g = gates.setdefault(row["gate"], {})
            for k, v in row.items():
                if k == "gate" or v is None or v == "":
                    continue
                g.setdefault(k, []).append(float(v))
    for g in gates.values():
        order = sorted(range(len(g["x"])), key=lambda i: g["x"][i])
        for k in list(g):
            g[k] = [g[k][i] for i in order]
    return gates


def plateau(xs, ys, tol):
    """「>= max(ys)-tol」的最大连通区间 → (lo, hi) x 值闭区间;空返回 None。"""
    m = max(ys)
    ok = [y >= m - tol for y in ys]
    best = (0, -1)   # 最长 run 的 [i, j)
    i = 0
    while i < len(ok):
        if ok[i]:
            j = i
            while j < len(ok) and ok[j]:
                j += 1
            if j - i > best[1] - best[0]:
                best = (i, j)
            i = j
        else:
            i += 1
    if best[1] <= best[0]:
        return None
    return (xs[best[0]], xs[best[1] - 1]), best[0], best[1] - 1


def intersect(a, b):
    """两个 (lo, hi) 闭区间求交;无交返回 None。"""
    if a is None or b is None:
        return None
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return (lo, hi) if lo <= hi else None


def judge_gate(g, rel_tol, min_match):
    """单闸判定 → dict(平台/交集/推荐/警告)。"""
    xs, fr, fp, mt = g["x"], g["fr"], g["fp"], g["match"]
    se_fr = g.get("se_fr")
    tol_fr = (se_fr[fr.index(max(fr))] if se_fr else abs(max(fr)) * rel_tol)
    se_fp = g.get("se_fp")
    tol_fp = (se_fp[fp.index(max(fp))] if se_fp else abs(max(fp)) * rel_tol)
    p_fr = plateau(xs, fr, tol_fr)
    p_fp = plateau(xs, fp, tol_fp)
    inter = intersect(p_fr and p_fr[0], p_fp and p_fp[0])

    # 分年:各年 fr 平台与总 fr 平台取交(仅幅度指标,FP 分年只画图不进判据)
    year_plats, robust = [], inter
    for y in ("y1", "y2"):
        if f"fr_{y}" in g:
            p = plateau(xs, g[f"fr_{y}"], abs(max(g[f"fr_{y}"])) * rel_tol)
            year_plats.append((y, p[0] if p else None))
            robust = intersect(robust, p[0] if p else None) if robust else robust
    base = robust if robust else inter
    rec = None
    if base:
        c = (base[0] + base[1]) / 2
        rec = xs[min(range(len(xs)), key=lambda i: abs(xs[i] - c))]

    # 警告收集
    n = len(xs)
    warn = []
    if inter is None:
        warn.append("fr 与 FP 平台无交集(先分年仲裁,再考虑方案级取舍)")
    else:
        width = sum(inter[0] <= x <= inter[1] for x in xs)
        if width <= 2:
            warn.append(f"交集仅 {width} 档,疑似尖峰")
        for name, ys_ in (("fr", fr), ("fp", fp)):
            pk_i = ys_.index(max(ys_))
            in_idx = [i for i in range(n) if inter[0] <= xs[i] <= inter[1]]
            # 峰值在交集内存在等值实例(含平台内本就到顶) → 不算贴边;
            # 峰值在交集外且紧贴边界 ≤1 档 → 交集可能是从尖峰斜坡上切出来的
            has_peak_in = any(ys_[i] >= ys_[pk_i] - 1e-12 for i in in_idx)
            if in_idx and not has_peak_in:
                if min(abs(pk_i - i) for i in in_idx) <= 1:
                    warn.append(f"{name} 峰值贴着交集边缘,警惕尖峰一侧")
    if year_plats and robust is None:
        warn.append("分年平台无共同交集(两年不同号,以分年一致性优先仲裁)")
    mt_in = [mt[i] for i in range(n)
             if base and base[0] <= xs[i] <= base[1]] if base else []
    if mt_in and min(mt_in) < min_match:
        warn.append(f"区间内 match 最低 {int(min(mt_in))} < 功效线 {min_match}")

    return {
        "fr_plateau": p_fr[0] if p_fr else None,
        "fp_plateau": p_fp[0] if p_fp else None,
        "intersection": inter,
        "robust_intersection": robust,
        "year_plateaus": {y: p for y, p in year_plats},
        "recommend_x": rec,
        "match_at_rec": int(mt[xs.index(rec)]) if rec is not None else None,
        "warnings": warn,
    }


def plot_gate(name, g, v, out_png, min_match):
    """单闸复核图:上=双 y 轴指标线(总粗/分年细),下=match 条带。"""
    xs, fr, fp, mt = g["x"], g["fr"], g["fp"], g["match"]
    fig, (ax1, ax3) = plt.subplots(
        2, 1, figsize=(9, 5.5), height_ratios=[3, 1], sharex=True)
    ax2 = ax1.twinx()
    ax1.plot(xs, fr, "o-", color="#1f77b4", lw=2, label="fr_median")
    ax2.plot(xs, fp, "s--", color="#ff7f0e", lw=2, label="FP")
    for y, color in (("y1", "#1f77b4"), ("y2", "#2ca02c")):
        if f"fr_{y}" in g:
            ax1.plot(xs, g[f"fr_{y}"], "-", color=color, lw=1, alpha=0.45,
                     label=f"fr_{y}")
    for ax, ys_, m in ((ax1, fr, "^"), (ax2, fp, "^")):
        i = ys_.index(max(ys_))
        ax.scatter([xs[i]], [ys_[i]], marker=m, color="red", s=90, zorder=5,
                   label="peak")
    inter = v["robust_intersection"] or v["intersection"]
    if inter:
        ax1.axvspan(inter[0], inter[1], color="#fbbf24", alpha=0.18,
                    label="plateau")
    if v["recommend_x"] is not None:
        i = xs.index(v["recommend_x"])
        ax1.scatter([xs[i]], [fr[i]], marker="*", color="#d97706", s=160,
                    zorder=6, label="recommend")
    ax1.set_ylabel("fr_median")
    ax2.set_ylabel("FP")
    ax1.set_title(f"{name}  (warnings: {len(v['warnings'])})")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=8, loc="best")
    ax3.bar(xs, mt, width=min((xs[1] - xs[0]) * 0.6, 1) if len(xs) > 1 else 1,
            color="#9ca3af")
    ax3.axhline(min_match, color="red", ls=":", lw=1)
    ax3.set_ylabel("match")
    ax3.set_xlabel("threshold")
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def run(csv: str, out_dir: str, *, rel_tol: float = 0.05, min_match: int = 100) -> dict:
    """逐闸平台判定:出 verdicts.json / verdicts.md / 每闸一张 png。

    rel_tol 与 min_match 至今未走过实战校准(见 SKILL.md「首轮使用注意」),不要当已验证默认。
    """
    CSV = csv
    OUT_DIR = out_dir
    REL_TOL = rel_tol
    MIN_MATCH = min_match
    out = Path(OUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    verdicts = {}
    for name, g in load(CSV).items():
        verdicts[name] = judge_gate(g, REL_TOL, MIN_MATCH)
        plot_gate(name, g, verdicts[name], out / f"{name}.png", MIN_MATCH)
    (out / "verdicts.json").write_text(
        json.dumps(verdicts, ensure_ascii=False, indent=1))
    lines = ["| gate | fr平台 | FP平台 | 交集 | 稳健交集 | 推荐 | match@rec | 警告 |",
             "|---|---|---|---|---|---|---|---|"]
    for name, v in verdicts.items():
        fmt = lambda r: (f"[{r[0]:.4g},{r[1]:.4g}]" if r else "—")
        lines.append(
            f"| {name} | {fmt(v['fr_plateau'])} | {fmt(v['fp_plateau'])} | "
            f"{fmt(v['intersection'])} | {fmt(v['robust_intersection'])} | "
            f"{v['recommend_x'] if v['recommend_x'] is not None else '—'} | "
            f"{v['match_at_rec'] if v['match_at_rec'] is not None else '—'} | "
            f"{'; '.join(v['warnings']) or '—'} |")
    (out / "verdicts.md").write_text("\n".join(lines))
    print(f"判定 {len(verdicts)} 闸 → {out}/verdicts.md (+json +png)")
    return verdicts
