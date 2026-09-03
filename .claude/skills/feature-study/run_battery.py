"""feature-study 统计电池:特征无关,输入观测 CSV + 列角色,输出全套统计 + 三关判定。

用法(库调用,推荐):
    import sys; sys.path.insert(0, '<repo>/.claude/skills/feature-study')
    from run_battery import run_battery
    run_battery(csv_path, features=[...], binaries=[...], controls=[...])

三关判定(写死,不随任务改):
    关1 原始显著:Spearman BH-FDR q < 0.05(二元特征用 Mann-Whitney p 进同一 FDR 族)
    关2 控制存活:与 controls 同放秩回归,|t| >= 2 且 t 与原始方向同号
        (|t|>=2 但反号 = suppression:原始关联由控制集承载,残余贡献反向——单列"反转"判定,
         不得当"有信号"报;与控制高共线时尤其常见)
    关3 去簇存活(双维,两检各自过):
        3a 股内:每 symbol 留数据原序首条(不按 label 挑)后重算,p<0.05 且同号
            → 防「特征效应其实是少数个股反复观测刷出」(股票轴泛化检查)
        3b 时间:每时间桶(tb_start//time_bucket_days)留首条后重算,同款判据
            → 防「同期跨股共同事件(如某周小盘集体反弹)是同一随机源的
               重复下注」(时间轴泛化检查;桶宽从 scan 的 label_horizon 取整,
               ≥horizon 才保证 forward window 重叠的 match 归同簇)
        time_bucket_days=None 或 CSV 缺 tb_start 列 → 3b 跳过,verdict 标注降级
        死因可区分:3a 死=个股驱动 / 3b 死=事件驱动
        (3b 在 3a 集合之上再做时间压缩 = 先股内后时间的双维压缩集合,兼任最保守读数)
    三关全过 = 有信号;过1而关2 |t|<2 = 代理(被控制集吸收);关1不过 = 无信号。
    controls 为空时关2 跳过,结论必须标注"无已知信号可控,判定降级"。

CSV 约定:必含 symbol、label 列;features/binaries/controls 为其列名子集;
        做时间维去簇另需 tb_start 列(同一 scan 窗内 bar 序号,跨股可比)。
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


def _decluster(d: pd.DataFrame, label: str, pick: str = "best") -> pd.DataFrame:
    """去簇(观测非独立的稳健性检查)。

    pick="best":每 symbol 留 label 最高一条 —— tail_enrichment 消费
        (镜像 UI 排行榜,排行榜展示的就是每只股票的最佳,语义本身)。
    pick="first":每 symbol 留数据原序首条 —— 关 3 消费。稳健性检查的簇代表
        不能由 label 挑选,否则检验被选择污染,还会反向保留事件聚集样本
        (集体反弹周 label 系统性偏高,留最高恰好吃到反弹的那条)。
    """
    if pick == "best":
        return d.sort_values(label, ascending=False).groupby("symbol").head(1)
    return d.groupby("symbol", sort=False).head(1)


def _decluster_time(d: pd.DataFrame, label: str, bucket_days: int,
                    time_col: str = "tb_start") -> pd.DataFrame:
    """同时间桶只留数据原序首条(同期跨股共同事件的去簇)。

    桶键 = time_col // bucket_days。time_col 是同一 scan 切窗内的 bar 序号,
    各股日期轴一致,跨股直接可比。簇代表不按 label 挑选(理由同 pick="first")。
    桶宽机制:两笔 match 的 forward window 重叠 ⟺ label 随机源共享,故桶宽
    下界 = label_horizon 的交易日数,调用方从 scan 取整后传入。
    """
    return (d.assign(_bucket=d[time_col] // bucket_days)
             .groupby("_bucket", sort=False).head(1)
             .drop(columns="_bucket"))


def _retest(dset: pd.DataFrame, m: str, label: str, kind: str) -> tuple[float, float]:
    """在给定集合上重算特征-label 关联(关3a 股内/关3b 时间两处共用)。"""
    if kind == "cont":
        ok = dset[m].notna() & dset[label].notna()
        rs, ps = stats.spearmanr(dset.loc[ok, m], dset.loc[ok, label])
        return float(rs), float(ps)
    g1, g0 = dset.loc[dset[m] == 1, label], dset.loc[dset[m] == 0, label]
    if len(g1) >= 5 and len(g0) >= 5:
        _, ps = stats.mannwhitneyu(g1, g0, alternative="two-sided")
        return float(g1.median() - g0.median()), float(ps)
    return np.nan, 1.0


def tail_enrichment(d: pd.DataFrame, flag: str, label: str,
                    ks: tuple[int, ...] = (20, 50, 100)) -> list[str]:
    """二元特征的 top-k 富集(镜像 UI 排行榜视角):per-symbol 最佳行,Fisher vs 基率。"""
    best = _decluster(d, label, pick="best")
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
                win_thresholds: tuple[float, float] = (0.10, 0.30),
                time_bucket_days: int | None = None) -> dict:
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

    # 关3:双维去簇(股内簇 + 时间簇,两检各自过;代表选择与 label 无关)
    sym_first = _decluster(d, label, pick="first")
    run_time = time_bucket_days is not None and "tb_start" in d.columns
    if time_bucket_days is not None and "tb_start" not in d.columns:
        print("⚠ 已传 time_bucket_days 但 CSV 缺 tb_start 列:关3 时间维跳过,判定降级")
    if time_bucket_days is None:
        print("⚠ 未传 time_bucket_days:关3 时间维跳过(桶宽应从 scan 的 label_horizon 取整),判定降级")
    time_first = _decluster_time(sym_first if run_time else d, label,
                                 time_bucket_days) if run_time else None
    print(f"\n== 关3a 股内去簇(每 symbol 首条,n={len(sym_first)}) ==")
    declust_sym = {m: _retest(sym_first, m, label, raw[m]["kind"])
                   for m in features + binaries}
    for m, (ds, dp) in declust_sym.items():
        print(f"{m:24s} stat={ds:+.3f} p={dp:.2g}")
    if time_first is not None:
        print(f"== 关3b 时间去簇(每时间桶首条,桶宽={time_bucket_days},n={len(time_first)}) ==")
        declust_time = {m: _retest(time_first, m, label, raw[m]["kind"])
                        for m in features + binaries}
        for m, (ds, dp) in declust_time.items():
            print(f"{m:24s} stat={ds:+.3f} p={dp:.2g}")
    else:
        declust_time = {}

    # 三关判定
    print("\n== 三关判定 ==")
    verdicts = {}
    for m in features + binaries:
        v = raw[m]
        gate1 = v["q_fdr"] < 0.05
        sign_ok = (np.sign(t_ctrl[m]) == np.sign(v["stat"])) if controls else True
        gate2 = bool(abs(t_ctrl[m]) >= 2 and sign_ok) if controls else None
        ds_sym, dp_sym = declust_sym[m]
        # bool() 归一:np 标量比较产生 np.True_/np.False_,不归一会漏到
        # 后文 `gate3_time is False` 身份比较与 verdicts 存储(np 布尔不是 bool)
        gate3_sym = bool(dp_sym < 0.05 and np.sign(ds_sym) == np.sign(v["stat"]))
        if m in declust_time:
            ds_time, dp_time = declust_time[m]
            gate3_time = bool(dp_time < 0.05
                              and np.sign(ds_time) == np.sign(v["stat"]))
        else:
            ds_time, dp_time, gate3_time = np.nan, None, None
        gate3 = gate3_sym if gate3_time is None else (gate3_sym and gate3_time)
        time_note = "" if gate3_time is not None else ";时间维未检(缺 tb_start 列或未传 time_bucket_days),关3 降级"
        if not gate1:
            verdict = "无信号"
        elif controls and abs(t_ctrl[m]) >= 2 and not sign_ok:
            verdict = ("反转(suppression):原始方向由控制集承载,"
                       f"控制后残余反向 t={t_ctrl[m]:+.2f}")
        elif gate2 is False:
            verdict = "代理(被控制集吸收)"
        elif not gate3_sym and gate3_time is False:
            verdict = "不稳(双维去簇均不显著,个股+事件混合驱动)"
        elif not gate3_sym:
            verdict = "不稳(股内去簇后不显著或反号,疑似个股驱动——少数股票反复观测刷出)"
        elif gate3_time is False:
            verdict = "不稳(时间去簇后不显著或反号,疑似事件驱动——同期跨股共同行情)"
        else:
            verdict = ("有信号" if controls else "疑似有信号(无控制,降级)")
            verdict += f",方向{'+' if v['stat'] > 0 else '−'}"
            if m in shapes:
                verdict += f",形状:{shapes[m]}"
        verdict += time_note if gate1 else ""   # 无信号时未走到关3,不加降级注记
        verdicts[m] = dict(verdict=verdict, gate1=gate1, gate2=gate2, gate3=bool(gate3),
                           gate3_sym=bool(gate3_sym), gate3_time=gate3_time,
                           q_fdr=v["q_fdr"], t_ctrl=t_ctrl.get(m),
                           declust_p=dp_sym, declust_time_p=dp_time)
        print(f"{m:24s} → {verdict}")
    return verdicts


if __name__ == "__main__":
    # 示例参数(实际使用改这里或直接 import run_battery 调用)
    CSV = "dataset.csv"
    FEATURES = ["m_ratio_a", "m_ratio_b"]
    BINARIES = []
    CONTROLS = ["m1_burst_runup", "m2_depth_rel"]
    run_battery(CSV, FEATURES, binaries=BINARIES, controls=CONTROLS)
