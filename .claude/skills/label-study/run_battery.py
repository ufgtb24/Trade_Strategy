"""label-study 统计电池:特征无关,输入观测 CSV + 列角色,输出全套统计 + 三关判定。

用法(库调用,推荐):
    import sys; sys.path.insert(0, '<repo>/.claude/skills/label-study')
    from run_battery import run_battery
    run_battery(csv_path, features=[...], binaries=[...], controls=[...])

三关判定(写死,不随任务改):
    关1 原始显著:Spearman BH-FDR q < 0.05(二元特征用 Mann-Whitney p 进同一 FDR 族)
    关2 控制存活:与 controls 同放秩回归,|t| >= 2 且 t 与原始方向同号
        (|t|>=2 但反号 = suppression:原始关联由控制集承载,残余贡献反向——单列"反转"判定,
         不得当"有信号"报;与控制高共线时尤其常见)
    关3 去簇存活:每 symbol 只留 label 最高一条后重算,p < 0.05 且同号
    三关全过 = 有信号;过1而关2 |t|<2 = 代理(被控制集吸收);关1不过 = 无信号。
    controls 为空时关2 跳过,结论必须标注"无已知信号可控,判定降级"。

CSV 约定:必含 symbol、label 列;features/binaries/controls 为其列名子集。
读 CSV 一律 keep_default_na=False(存在名为 NA 的 ticker)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


# ── 基础件 ──

def _bh_fdr(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg q 值(口径族多重比较校正)。"""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank_from_last, idx in enumerate(order[::-1]):
        i = n - rank_from_last          # 1-based 名次(从大到小)
        prev = min(prev, p[idx] * n / i)
        q[idx] = prev
    return q.tolist()


def rank_ols(d: pd.DataFrame, cols: list[str], label: str) -> dict[str, tuple[float, float]]:
    """label 秩 ~ 各列秩 的 OLS;返回 {col: (beta, t)}。"""
    dd = d[cols + [label]].apply(pd.to_numeric, errors="coerce").dropna()
    r = dd.rank(pct=True)
    X = np.column_stack([np.ones(len(r))] + [r[c] for c in cols])
    y = r[label].to_numpy()
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * resid.var(ddof=len(cols) + 1))
    names = ["const"] + cols
    return {n: (float(b), float(b / s)) for n, b, s in zip(names, beta, se)}


def quantile_table(d: pd.DataFrame, m: str, label: str, k: int = 5) -> pd.DataFrame:
    dd = d[[m, label]].dropna().copy()
    dd["q"] = pd.qcut(dd[m], k, labels=False, duplicates="drop")
    return dd.groupby("q").agg(
        n=(label, "size"), lo=(m, "min"), hi=(m, "max"),
        mean_lab=(label, "mean"), med_lab=(label, "median"),
        win10=(label, lambda s: (s > 0.10).mean()),
        win30=(label, lambda s: (s > 0.30).mean()),
    )


def _shape_note(qt: pd.DataFrame) -> str:
    """分箱形状注记:单调性 + 饱和/回落。"""
    means = qt["mean_lab"].to_numpy()
    if len(means) < 3:
        return "箱数不足"
    rho = stats.spearmanr(np.arange(len(means)), means)[0]
    mono = "单调升" if rho > 0.9 else ("单调降" if rho < -0.9 else "非单调")
    peak = int(np.argmax(means))
    sat = ""
    if mono == "非单调" and 0 < peak < len(means) - 1:
        sat = f",峰在第{peak + 1}箱后回落"
    elif mono == "单调升" and peak == len(means) - 1 and len(means) >= 4 \
            and means[-1] - means[-2] < 0.25 * max(means[-2] - means[0], 1e-12):
        sat = ",尾箱增益趋缓"
    return mono + sat


def _decluster(d: pd.DataFrame, label: str) -> pd.DataFrame:
    """每 symbol 只留 label 最高一条(观测非独立的去簇稳健性)。"""
    return d.sort_values(label, ascending=False).groupby("symbol").head(1)


def tail_enrichment(d: pd.DataFrame, flag: str, label: str,
                    ks: tuple[int, ...] = (20, 50, 100)) -> list[str]:
    """二元特征的 top-k 富集(镜像 UI 排行榜视角):per-symbol 最佳行,Fisher vs 基率。"""
    best = _decluster(d, label)
    base = best[flag].mean()
    lines = [f"基率 P({flag}=1) = {base:.1%}(per-symbol 最佳行,n={len(best)})"]
    for k in ks:
        if k >= len(best):
            continue
        topk = best.sort_values(label, ascending=False).head(k)
        a = int(topk[flag].sum())
        rest_pos = int(best[flag].sum()) - a
        tbl = [[a, k - a], [rest_pos, len(best) - k - rest_pos]]
        _, p = stats.fisher_exact(tbl)
        lines.append(f"top{k}: {flag}=1 有 {a} 个(基率期望 {k * base:.1f}),Fisher p={p:.3f}")
    return lines


# ── 主入口 ──

def run_battery(csv_path, features: list[str], label: str = "label",
                binaries: list[str] | None = None,
                controls: list[str] | None = None,
                win_thresholds: tuple[float, float] = (0.10, 0.30)) -> dict:
    """跑全套电池,打印报告文本,返回 {feature: verdict_dict}(供报告引用)。"""
    binaries = binaries or []
    controls = controls or []
    d = pd.read_csv(csv_path, keep_default_na=False, na_values=[""])
    assert "symbol" in d.columns and label in d.columns, "CSV 必含 symbol 与 label 列"

    print(f"n={len(d)}  symbols={d['symbol'].nunique()}")
    print(f"label: mean={d[label].mean():.3f} med={d[label].median():.3f} "
          f"p10={d[label].quantile(.1):.3f} p90={d[label].quantile(.9):.3f}")
    if not controls:
        print("⚠ 无 controls:关2 跳过,全部判定自动降级(报告必须声明)")

    # 关1:原始显著性(连续 Spearman;二元 Mann-Whitney)→ 同族 BH-FDR
    raw = {}
    lab_w = d[label].clip(lower=d[label].quantile(0.01), upper=d[label].quantile(0.99))
    print("\n== 关1 原始关联(Spearman / MW + BH-FDR) ==")
    for m in features:
        ok = d[m].notna() & d[label].notna()
        rs, ps = stats.spearmanr(d.loc[ok, m], d.loc[ok, label])
        xw = d.loc[ok, m].clip(lower=d.loc[ok, m].quantile(0.01), upper=d.loc[ok, m].quantile(0.99))
        rp, _ = stats.pearsonr(xw, lab_w[ok])
        raw[m] = dict(kind="cont", stat=rs, p=ps, pearson_w=rp, n=int(ok.sum()))
    for m in binaries:
        g1, g0 = d.loc[d[m] == 1, label], d.loc[d[m] == 0, label]
        _, p = stats.mannwhitneyu(g1, g0, alternative="two-sided")
        raw[m] = dict(kind="bin", stat=float(g1.median() - g0.median()), p=p,
                      n1=len(g1), n0=len(g0))
    qs = _bh_fdr([v["p"] for v in raw.values()])
    for (m, v), q in zip(raw.items(), qs):
        v["q_fdr"] = q
        if v["kind"] == "cont":
            print(f"{m:24s} spearman={v['stat']:+.3f} p={v['p']:.2g} q_fdr={q:.3f} "
                  f"pearson_w={v['pearson_w']:+.3f} n={v['n']}")
        else:
            print(f"{m:24s} [二元] med_diff={v['stat']:+.3f} MW_p={v['p']:.2g} "
                  f"q_fdr={q:.3f} n1/n0={v['n1']}/{v['n0']}")

    # 分箱形状(连续)/分组表(二元)
    shapes = {}
    for m in features:
        qt = quantile_table(d, m, label)
        shapes[m] = _shape_note(qt)
        print(f"\n== 分箱: {m}({shapes[m]}) ==")
        print(qt.to_string(float_format=lambda v: f"{v:.3f}"))
    for m in binaries:
        print(f"\n== 分组: {m} ==")
        for name, g in [(f"{m}=1", d[d[m] == 1]), (f"{m}=0", d[d[m] == 0])]:
            print(f"  {name:14s} n={len(g):4d} mean={g[label].mean():.3f} "
                  f"med={g[label].median():.3f} "
                  f"P(>{win_thresholds[0]:.0%})={(g[label] > win_thresholds[0]).mean():.1%} "
                  f"P(>{win_thresholds[1]:.0%})={(g[label] > win_thresholds[1]).mean():.1%}")
        for line in tail_enrichment(d, m, label):
            print("  " + line)

    # 特征间 + 与控制的相关结构
    all_cols = features + binaries + controls + [label]
    print("\n== Spearman 矩阵(混杂结构) ==")
    print(d[all_cols].apply(pd.to_numeric, errors="coerce")
          .corr(method="spearman").round(3).to_string())

    # 关2:控制已知信号后的独立贡献
    t_ctrl = {}
    if controls:
        print("\n== 关2 秩回归(特征 + controls) ==")
        for m in features + binaries:
            res = rank_ols(d, [m] + controls, label)
            t_ctrl[m] = res[m][1]
            terms = "  ".join(f"{k}: t={v[1]:+.2f}" for k, v in res.items() if k != "const")
            print(f"{m:24s} {terms}")

    # 关3:去簇
    best = _decluster(d, label)
    print(f"\n== 关3 去簇(per-symbol 最佳,n={len(best)}) ==")
    declust = {}
    for m in features:
        ok = best[m].notna()
        rs, ps = stats.spearmanr(best.loc[ok, m], best.loc[ok, label])
        declust[m] = (rs, ps)
        print(f"{m:24s} spearman={rs:+.3f} p={ps:.2g}")
    for m in binaries:
        g1, g0 = best.loc[best[m] == 1, label], best.loc[best[m] == 0, label]
        if len(g1) >= 5 and len(g0) >= 5:
            _, ps = stats.mannwhitneyu(g1, g0, alternative="two-sided")
            declust[m] = (float(g1.median() - g0.median()), ps)
        else:
            declust[m] = (np.nan, 1.0)
        print(f"{m:24s} med_diff={declust[m][0]:+.3f} p={declust[m][1]:.2g}")

    # 三关判定
    print("\n== 三关判定 ==")
    verdicts = {}
    for m in features + binaries:
        v = raw[m]
        gate1 = v["q_fdr"] < 0.05
        sign_ok = (np.sign(t_ctrl[m]) == np.sign(v["stat"])) if controls else True
        gate2 = (abs(t_ctrl[m]) >= 2 and sign_ok) if controls else None
        ds, dp = declust[m]
        gate3 = dp < 0.05 and np.sign(ds) == np.sign(v["stat"])
        if not gate1:
            verdict = "无信号"
        elif controls and abs(t_ctrl[m]) >= 2 and not sign_ok:
            verdict = ("反转(suppression):原始方向由控制集承载,"
                       f"控制后残余反向 t={t_ctrl[m]:+.2f}")
        elif gate2 is False:
            verdict = "代理(被控制集吸收)"
        elif not gate3:
            verdict = "不稳(去簇后不显著,疑似股票簇驱动)"
        else:
            verdict = ("有信号" if controls else "疑似有信号(无控制,降级)")
            verdict += f",方向{'+' if v['stat'] > 0 else '−'}"
            if m in shapes:
                verdict += f",形状:{shapes[m]}"
        verdicts[m] = dict(verdict=verdict, gate1=gate1, gate2=gate2, gate3=bool(gate3),
                           q_fdr=v["q_fdr"], t_ctrl=t_ctrl.get(m), declust_p=dp)
        print(f"{m:24s} → {verdict}")
    return verdicts


if __name__ == "__main__":
    # 示例参数(实际使用改这里或直接 import run_battery 调用)
    CSV = "dataset.csv"
    FEATURES = ["m_ratio_a", "m_ratio_b"]
    BINARIES = []
    CONTROLS = ["m1_burst_runup", "m2_depth_rel"]
    run_battery(CSV, FEATURES, binaries=BINARIES, controls=CONTROLS)
