"""11 同日对照配对票 · 第六步：照 11-prereg.txt 判每种配对挡没挡住白得的领先，挑推荐的配对。

读 11-noise.csv.gz（判据分母、对照抖动）、11-bias.csv.gz（白得的领先）。
判据（量之前定好）：
  (a) 合并：|全部决策日上的白得领先| ≤ 2 年偶然波动 / 3
  (b) 分年：2022–2025 每年 |白得领先| ≤ 1 年偶然波动（2021 只展示）
  「判不清」：|点估计| 与线的差不到 2 倍抽样误差
推荐：判优用假 pattern 上的失败数最少 → 最坏「白得领先 ÷ 线」最小；约束：对照抖动 ≤ 0.5 × 买点侧偶然波动（每把尺子）。
输出：scripts/11-judge_out.txt、scratchpad/11/judge_cells.csv.gz（逐格判定）
运行：uv run python .scratch/selection-pattern/scripts/11-judge.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("core11", HERE / "11-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core11"] = core; spec.loader.exec_module(core)

YEARS = ["2022", "2023", "2024", "2025"]
JUDGED = ["M_top2", "M_top10", "M_bot10", "M_bot2", "H_top10", "H_bot10",
          "Hhi_Mmid", "Mhi_Hmid", "Hlo_Mmid", "Mlo_Hmid"]
CHECKS = ["DV_bot10", "DV_top10", "PX_bot10", "PX_top10"]
CLS_NAME = {"rand": "无偏好随机", "M_top2": "当天 M 最高 2%", "M_top10": "当天 M 最高 10%",
            "M_bot10": "当天 M 最低 10%", "M_bot2": "当天 M 最低 2%", "H_top10": "平时波动最高一档",
            "H_bot10": "平时波动最低一档", "Hhi_Mmid": "平时高、当天普通", "Mhi_Hmid": "当天高、平时普通",
            "Hlo_Mmid": "平时低、当天普通", "Mlo_Hmid": "当天低、平时普通", "bb_clust": "bottom_burst 长相扎堆型",
            "DV_bot10": "成交额最低一档", "DV_top10": "成交额最高一档", "PX_bot10": "价格最低一档",
            "PX_top10": "价格最高一档"}
SCHEME_NAME = {"M5": "现行：当天 M 五档", "M10": "当天 M 十档", "M20": "当天 M 二十档",
               "M3xH3": "M 三档 × 平时波动三档", "M5xH5": "M 五档 × 平时波动五档",
               "M10xH3": "M 十档 × 平时波动三档", "M10xH5": "M 十档 × 平时波动五档",
               "M20xH3": "M 二十档 × 平时波动三档", "K10": "最近 10 只", "K20": "最近 20 只",
               "K50": "最近 50 只", "K100": "最近 100 只", "K5": "最近 5 只"}


def thresholds():
    nz = pd.read_csv(HERE / "11-noise.csv.gz")
    th = {}
    for m in core.METRICS:
        s1 = float(np.sqrt((nz[(nz.Y == 1) & (nz.scheme == "M5")][f"hsd_{m}"] ** 2).mean()))
        s2 = float(np.sqrt((nz[(nz.Y == 2) & (nz.scheme == "M5")][f"hsd_{m}"] ** 2).mean()))
        th[m] = {"s1_meas": s1, "s2_meas": s2}
        if m == "dir":
            th[m].update(s1=0.023, s2=0.015)
        elif m == "mag":
            th[m].update(s1=0.0068, s2=0.0050)
        else:
            th[m].update(s1=s1, s2=s2)
    jit = {}
    extra = HERE / "11-noise-K5-K10.csv.gz"          # 看过第一轮后加的 K5（K10 重算一遍作核对）
    if extra.exists():
        nx = pd.read_csv(extra)
        nz = pd.concat([nz, nx[nx.scheme == "K5"]], ignore_index=True)
    for s, g in nz[nz.Y == 2].groupby("scheme"):
        jit[s] = {m: float(np.sqrt((g[f"csd_{m}"] ** 2).mean()) / np.sqrt((g[f"hsd_{m}"] ** 2).mean()))
                  for m in core.METRICS}
    return th, jit


def judge_table(bias: pd.DataFrame, th: dict, classes, forms=("full", "disp", "clust")):
    """逐（类, 形式, 配对, 尺子）判 (a)(b)，返回长表。"""
    rows = []
    b = bias[bias.cls.isin(classes) & bias.form.isin(forms)]
    se_full = (bias[bias.form == "full"].query("scheme == 'M5'")
               .set_index(["cls", "scope"])[[f"se_{m}" for m in core.METRICS]])
    for (c, f, s), g in b.groupby(["cls", "form", "scheme"]):
        g = g.set_index("scope")
        for m in core.METRICS:
            t1, t2 = th[m]["s1"], th[m]["s2"]
            if "all" not in g.index:
                continue
            def se_of(scope):
                se = np.nan
                if (c, scope) in se_full.index:
                    se = float(se_full.loc[(c, scope), f"se_{m}"])
                if f in ("disp", "clust") and f"repsd_{m}" in g.columns and scope in g.index:
                    rs = float(g.loc[scope, f"repsd_{m}"]) / np.sqrt(40)
                    se = rs if not np.isfinite(se) else max(se, rs)
                return se
            va = float(g.loc["all", m]); lim_a = t2 / 3
            ya = {y: float(g.loc[y, m]) for y in YEARS if y in g.index}
            worst_y = max(ya, key=lambda y: abs(ya[y])) if ya else None
            vy = ya[worst_y] if worst_y else np.nan
            ex = float(g.loc["ex2022", m]) if "ex2022" in g.index else np.nan
            se_a, se_y = se_of("all"), se_of(worst_y) if worst_y else np.nan
            fail_a = abs(va) > lim_a
            fail_b = any(abs(v) > t1 for v in ya.values())
            n_fail_years = sum(abs(v) > t1 for v in ya.values())
            unclear_a = np.isfinite(se_a) and abs(abs(va) - lim_a) < 2 * se_a
            unclear_b = np.isfinite(se_y) and abs(abs(vy) - t1) < 2 * se_y
            rows.append(dict(cls=c, form=f, scheme=s, metric=m, all=va, lim_a=lim_a, norm_a=abs(va) / lim_a,
                             worst_year=worst_y, worst_val=vy, lim_b=t1, norm_b=abs(vy) / t1, ex2022=ex,
                             norm_ex=abs(ex) / lim_a, fail_a=fail_a, fail_b=fail_b, n_fail_years=n_fail_years,
                             unclear_a=unclear_a, unclear_b=unclear_b, se_all=se_a, se_worst=se_y,
                             **{f"y{y}": ya.get(y, np.nan) for y in YEARS},
                             y2021=float(g.loc["2021", m]) if "2021" in g.index else np.nan))
    return pd.DataFrame(rows)


def summarize(jt: pd.DataFrame, jit: dict):
    out = []
    for s, g in jt.groupby("scheme"):
        clear_a = g.fail_a & ~g.unclear_a
        clear_b = g.fail_b & ~g.unclear_b
        maxj = max(jit[s].values())
        out.append(dict(scheme=s, fails=int(g.fail_a.sum() + g.fail_b.sum()),
                        fails_a=int(g.fail_a.sum()), fails_b=int(g.fail_b.sum()),
                        clear_fails=int(clear_a.sum() + clear_b.sum()),
                        worst=float(np.maximum(g.norm_a, g.norm_b).max()),
                        worst_cell=g.loc[np.maximum(g.norm_a, g.norm_b).idxmax(), ["cls", "form", "metric"]].tolist(),
                        median_norm=float(np.median(np.maximum(g.norm_a, g.norm_b))),
                        max_jitter=maxj, jitter_ok=maxj <= 0.5))
    return pd.DataFrame(out).sort_values(["fails", "worst"])


def main():
    th, jit = thresholds()
    bias = pd.read_csv(HERE / "11-bias.csv.gz", dtype={"scope": str})
    if (HERE / "11-bias-K5.csv.gz").exists():       # 看过第一轮后加的 K5，单独补算
        bias = pd.concat([bias, pd.read_csv(HERE / "11-bias-K5.csv.gz", dtype={"scope": str})], ignore_index=True)
    first_round = bias[bias.scheme != "K5"]
    lines = ["== 判据的分母（偶然波动；方向为方向值，其余为每笔收益的小数）=="]
    for m in core.METRICS:
        t = th[m]
        lines.append(f"  {m:8s} 1 年 {t['s1']:.4f}  2 年 {t['s2']:.4f}  → 合并线 {t['s2'] / 3:.4f}，分年线 {t['s1']:.4f}"
                     f"   （本票实测 1 年 {t['s1_meas']:.4f}，2 年 {t['s2_meas']:.4f}）")
    jt = judge_table(first_round, th, JUDGED + ["bb_clust"])
    jt.to_csv(core.SCR / "judge_cells.csv.gz", index=False)
    sm = summarize(jt, jit)
    lines.append("\n== 各配对：判优用假 pattern（10 类 × 整类/分散 + 扎堆型）× 14 把尺子 × (a)(b) 的失败数 ==")
    lines.append(sm.to_string(index=False))
    # 排除两种噪声大的组合类（只有几百到两三千个股票日），看排名是否变化
    jt2 = jt[~jt.cls.isin(["Mlo_Hmid", "Hlo_Mmid", "Hhi_Mmid", "Mhi_Hmid"])]
    lines.append("\n== 同上，去掉四种「一维高、一维普通」的组合类（样本小、判不清多）==")
    lines.append(summarize(jt2, jit).to_string(index=False))
    for f in ("full", "disp"):
        lines.append(f"\n== 只看 {f} 形式 ==")
        lines.append(summarize(jt[(jt.form == f) | (jt.form == 'clust')], jit).to_string(index=False))
    # 按尺子分的失败数
    lines.append("\n== 每把尺子上的失败数（行 = 配对）==")
    piv = (jt.assign(f=jt.fail_a.astype(int) + jt.fail_b.astype(int))
           .pivot_table(index="scheme", columns="metric", values="f", aggfunc="sum"))[core.METRICS]
    lines.append(piv.to_string())
    lines.append("\n== 每类假 pattern 的失败数（行 = 配对）==")
    piv = (jt.assign(f=jt.fail_a.astype(int) + jt.fail_b.astype(int), k=jt.cls + "/" + jt.form)
           .pivot_table(index="scheme", columns="k", values="f", aggfunc="sum"))
    lines.append(piv.to_string())
    # 检查用（成交额、价格）
    jc = judge_table(bias, th, CHECKS)   # 检查用（含 K5）
    lines.append("\n== 检查用假 pattern（成交额 / 价格）的失败数（行 = 配对）==")
    lines.append(summarize(jc, jit)[["scheme", "fails", "fails_a", "fails_b", "clear_fails", "worst", "worst_cell"]]
                 .to_string(index=False))
    jc.to_csv(core.SCR / "judge_checks.csv.gz", index=False)
    # ---- 看过第一轮结果后补的两组（单独计数，不改上面的判定）----
    b2 = pd.read_csv(HERE / "11-bias2.csv.gz", dtype={"scope": str})
    b2["cls"] = np.where(b2["trim"].astype(bool), b2["cls"] + "|trim", b2["cls"])
    allb = pd.concat([bias, b2], ignore_index=True)
    added = sorted(set(b2.loc[~b2["trim"].astype(bool), "cls"]))
    fair = [c for c in JUDGED if c not in ("M_top10", "M_bot10")] + added + ["bb_clust"]
    jf = judge_table(allb, th, fair)
    jf = jf[~((jf.cls.isin(["M_top10", "M_bot10"])))]
    lines.append("\n== 补充一：不卡档界的判优集（去掉恰好落在档界上的「M 最高 / 最低一档」，加平滑偏好与错开档界的窗口）==")
    lines.append(summarize(jf, jit).to_string(index=False))
    jf.to_csv(core.SCR / "judge_fair.csv.gz", index=False)
    trim_cls = [c + "|trim" for c in fair if c != "bb_clust"] + ["bb_clust|trim"]
    jtr = judge_table(allb, th, trim_cls)
    lines.append("\n== 补充二：同一判优集，只看不在两头的买点（当天 M 与平时波动排位都在 2%–98% 之内）==")
    lines.append(summarize(jtr, jit).to_string(index=False))
    jtr.to_csv(core.SCR / "judge_trim.csv.gz", index=False)
    piv = (jtr.assign(f=jtr.fail_a.astype(int) + jtr.fail_b.astype(int))
           .pivot_table(index="scheme", columns="metric", values="f", aggfunc="sum"))[core.METRICS]
    lines.append("补充二 每把尺子上的失败数：\n" + piv.to_string())
    lines.append("\n== 对照抖动 ÷ 买点侧偶然波动（2 年、无偏好分散；最大值所在尺子）==")
    for s in jit:
        m = max(jit[s], key=jit[s].get)
        lines.append(f"  {s:7s} 最大 {jit[s][m]:.2f}（{m}）  方向 {jit[s]['dir']:.2f}  幅度 {jit[s]['mag']:.2f}")
    txt = "\n".join(lines)
    (HERE / "11-judge_out.txt").write_text(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
