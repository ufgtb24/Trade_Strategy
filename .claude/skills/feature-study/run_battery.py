"""feature-study 统计电池:特征无关,输入观测表 + 列角色,输出全套统计与判定。

两个入口:
    run_battery(csv_path, features, ...)  连续 / 二元特征与标签的关系(关1 原始关联 → 关2 控制存活 → 分年稳定性)
    gate_judgment(rows, gates, ...)       闸式判定:一道闸(字段 + 运算符 + ≤4 个预注册切点)在条件总体里挣没挣到位置

用法(库调用):
    import sys; sys.path.insert(0, '<repo>/.claude/skills/feature-study')
    from run_battery import run_battery, gate_judgment

两种标签口径(label_type):
    "forward_return":label 列是前瞻收益;回归因变量取它的百分位秩,每行等权。
    "first_passage":读四态计数列 up / down / both / none(一行 = 一个买点事件内合格买点 bar 的计数);
        主指标首次穿越率 = up/(up+down+both),none 不进分母;回归因变量取该行的首次穿越份额,按定向 bar 加权。

推断一律按股去簇(簇稳健加权回归,CR1);时间维用时间窗固定效应控制(窗宽 = label_horizon 个交易日换算成的
日历天),分年估计只作稳定性过滤。统计核(BH / Simes / 簇稳健回归 / 按股线性化比率误差 / 层匹配差 / 分辨力)
在 tune-gates 的 inference.py、budget.py,本模块按文件路径加载,不另写一份。

run_battery 的判定:
    关1 原始关联:特征(连续取百分位秩、二元取 0/1)对因变量的簇稳健回归 z,与同批其余假设一起 BH,q < 0.05。
    关2 控制存活:同一回归加控制列(百分位秩)与时间窗固定效应,|z| ≥ 1.96 且与关1 同号。
        |z| ≥ 1.96 但反号 = suppression,单列「反转」(原始关联由控制集承载,残余贡献反向);|z| < 1.96 =「代理」。
    稳定性:每年都有足够把握看到合并效应(单侧功效 ≥ 0.8)时,某年显著反向或显著缩水 →「不稳」;功效不够一律不判不稳。
    controls 为空且没有时间窗 → 关2 跳过,判定降级。
    方向一律取回归系数的符号——离散标签(首次穿越四态、0/1)下两组中位数差恒为 0,不能拿来定方向。

为什么不再做子抽样去簇(每股留首条 / 每时间桶留首条):子抽样丢掉大半样本,时间桶只有十几个时检验功效不到一成,
两个方向的 p 值都不可解释;全样本按股簇稳健推断既用满样本、又不把同一只股票的反复观测当独立证据。

CSV 约定:必含 symbol;forward_return 另需 label 列,first_passage 另需四态列;时间窗固定效应需要日期列
(time_col,默认 entry_date)并传 label_horizon。读 CSV 一律 keep_default_na=False(存在名为 NA 的 ticker)。
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

SKILL_DIR = Path(__file__).resolve().parent
TUNE_GATES_DIR = SKILL_DIR.parent / "tune-gates"


def load_tune_gates(name: str):
    """按文件路径加载 tune-gates 的模块 `<name>.py`,以原名登记进 sys.modules 后返回。

    按路径加载、不把 tune-gates 目录并进 sys.path:两个 skill 目录下都有 apps/<app>/,同时进 sys.path
    会被合并成一个命名空间包、互相遮蔽(同 extract.load_adapter 的理由)。以原名登记,是因为 tune-gates
    模块之间用 `import 模块名` 互相引用,登记后它们拿到的是同一个模块对象。同名模块已从别处加载 → 报错。
    """
    path = (TUNE_GATES_DIR / f"{name}.py").resolve()
    mod = sys.modules.get(name)
    if mod is not None:
        if Path(getattr(mod, "__file__", "") or "").resolve() != path:
            raise ImportError(f"模块名 {name!r} 已被 {getattr(mod, '__file__', None)} 占用,不能再按路径加载 {path}")
        return mod
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


inference = load_tune_gates("inference")
budget = load_tune_gates("budget")

LABEL_TYPES = ("forward_return", "first_passage")
STATES = ("up", "down", "both", "none")
Z_CRIT = float(stats.norm.ppf(0.975))   # 双侧 5%
Z_ONE = float(stats.norm.ppf(0.95))     # 单侧 5%:非劣效下界
Q_FDR = 0.05                            # 学习端判定的 BH 阈值
POWER_OK = 0.8                          # 分年稳定性检查要求的单侧功效
MAX_CUTS = 4                            # 每道闸最多预注册的切点数
P0 = 0.5                                # 功效预检的首次穿越率取值(最保守)


# ── 基础件 ──

def _p_two(z: float) -> float:
    return float(2 * stats.norm.sf(abs(z))) if np.isfinite(z) else float("nan")


def _pct_rank(values) -> pd.Series:
    return pd.to_numeric(pd.Series(values), errors="coerce").rank(pct=True)


def _independent_cols(X: np.ndarray, w: np.ndarray) -> list[int]:
    """按列序贪心保留线性无关的列(加权 Gram 矩阵上判秩):常数列、被前面列线性表出的列被丢掉。"""
    G = X.T @ (X * w[:, None])
    keep: list[int] = []
    for k in range(X.shape[1]):
        cand = keep + [k]
        sub = G[np.ix_(cand, cand)]
        tol = 1e-9 * max(1.0, float(np.abs(sub).max()))
        if np.linalg.matrix_rank(sub, tol=tol) == len(cand):
            keep.append(k)
    return keep


def _coef(y, X, w, clusters, j: int = 1) -> dict:
    """簇稳健加权回归(inference.cluster_wls,CR1)里第 j 列的系数。

    先丢掉线性相关的列(如样本里恒为 0 的时间窗哑变量);第 j 列被丢掉、或样本不够估计时返回 nan。
    返回 {"beta", "se", "z", "p", "n", "G"}。
    """
    y = np.asarray(y, float); X = np.asarray(X, float); w = np.asarray(w, float)
    G_n = int(pd.unique(np.asarray(clusters)).size)
    out = {"beta": float("nan"), "se": float("nan"), "z": float("nan"), "p": float("nan"), "n": len(y), "G": G_n}
    if len(y) == 0 or G_n < 2:
        return out
    keep = _independent_cols(X, w)
    if j not in keep or len(y) <= len(keep):
        return out
    try:
        fit = inference.cluster_wls(y, X[:, keep], w, clusters)
    except np.linalg.LinAlgError:
        return out
    i = keep.index(j)
    b, se = float(fit["beta"][i]), float(fit["se"][i])
    z = b / se if se > 0 else float("nan")
    return {"beta": b, "se": se, "z": z, "p": _p_two(z), "n": int(fit["n"]), "G": int(fit["G"])}


def _window_dummies(dates, train_start, label_horizon: int) -> tuple[np.ndarray, int]:
    """时间窗固定效应的哑变量(去掉第一个出现的窗)与有数据的时间窗个数。

    窗宽 = inference.time_window_days(label_horizon),窗号 = (date − train_start).days // 窗宽。
    """
    codes, _ = inference.time_window_codes(dates, train_start, inference.time_window_days(label_horizon))
    present = sorted(set(codes), key=int)
    dummies = (codes[:, None] == np.array(present[1:], dtype=object)[None, :]).astype(float)
    return dummies, len(present)


def _time_undetermined(n_windows: int, n_years: int) -> bool:
    """时间维在结构上检查不了:有数据的时间窗 < 2(时间窗固定效应吸收不了任何东西),
    或只覆盖 1 个年份(分年稳定性检查做不了)。窗数多少本身不是理由——窗宽由标签前瞻期决定,窗数由数据跨度决定。"""
    return n_windows < 2 or n_years < 2


def _unstable(est: float, by_year: dict, rest: dict) -> tuple[bool | None, str]:
    """分年稳定性:合并估计 est 的方向在单年里是否显著反向或显著缩水。

    参数:by_year / rest = {年: (估计, SE)},rest 是「除该年以外的其余年份」的估计。
    判据:
        功效:每年 power_normal(|est|, se_年) ≥ 0.8(单年里有足够把握看到合并效应);任一年不够 → 不判(None)。
        显著反向:s·est_年 / se_年 ≤ −1.96(s = est 的符号)。
        显著缩水:s·(est_年 − est_其余) / hypot(se_年, se_其余) ≤ −1.96,且该年自身不显著同号。
    返回 (True / False / None, 说明)。
    """
    s = float(np.sign(est))
    if len(by_year) < 2 or s == 0 or not np.isfinite(est):
        return None, "只有一年数据,分年稳定性未判"
    for y, (_, se_y) in by_year.items():
        if not (np.isfinite(se_y) and se_y > 0) or inference.power_normal(abs(est), se_y) < POWER_OK:
            return None, "分年功效不足,不判不稳"
    for y, (e_y, se_y) in by_year.items():
        z_y = s * e_y / se_y
        if z_y <= -Z_CRIT:
            return True, f"{y} 年显著反向"
        e_r, se_r = rest[y]
        if np.isfinite(e_r) and np.isfinite(se_r) and se_r > 0:
            z_int = s * (e_y - e_r) / math.hypot(se_y, se_r)
            if z_int <= -Z_CRIT and z_y < Z_CRIT:
                return True, f"{y} 年显著缩水"
    return False, ""


def _fmt(v) -> str:
    return "不设" if v is None else f"{v:g}"


# ── 分箱与形状 ──

def quantile_table(d: pd.DataFrame, m: str, label: str, k: int = 5) -> pd.DataFrame:
    dd = d[[m, label]].dropna().copy()
    dd["q"] = pd.qcut(dd[m], k, labels=False, duplicates="drop")
    return dd.groupby("q").agg(
        n=(label, "size"), lo=(m, "min"), hi=(m, "max"),
        mean_lab=(label, "mean"), med_lab=(label, "median"),
        win10=(label, lambda s: (s > 0.10).mean()),
        win30=(label, lambda s: (s > 0.30).mean()),
    )


def _group_rate(g: pd.DataFrame) -> dict:
    """一组行的首次穿越合并率 ΣU/ΣD 与按股去簇的 95% CI。"""
    s = g.groupby("symbol", observed=True)[list(STATES)].sum()
    U = s["up"].to_numpy(float)
    D = U + s["down"].to_numpy(float) + s["both"].to_numpy(float)
    N = D + s["none"].to_numpy(float)
    if D.sum() <= 0:
        return dict(n=len(g), n_dir=0, rate=np.nan, ci_lo=np.nan, ci_hi=np.nan)
    lv = inference.level_se(U, D, N)
    return dict(n=len(g), n_dir=int(D.sum()), rate=lv["r"],
                ci_lo=lv["r"] - Z_CRIT * lv["se"], ci_hi=lv["r"] + Z_CRIT * lv["se"])


def rate_table(d: pd.DataFrame, m: str, k: int = 5) -> pd.DataFrame:
    """首次穿越口径的分箱表:按特征分位切 k 箱,每箱合并率 ΣU/ΣD(不是逐行份额的均值)与按股去簇的 95% CI。"""
    dd = d[["symbol", m, *STATES]].copy()
    dd[m] = pd.to_numeric(dd[m], errors="coerce")
    dd = dd.dropna(subset=[m])
    dd["q"] = pd.qcut(dd[m], k, labels=False, duplicates="drop")
    rows = [dict(q=q, lo=g[m].min(), hi=g[m].max(), **_group_rate(g)) for q, g in dd.groupby("q")]
    return pd.DataFrame(rows).set_index("q")


def _shape_of(vals: np.ndarray) -> str:
    """单值序列的形状:单调性 + 饱和/回落。"""
    rho = stats.spearmanr(np.arange(len(vals)), vals)[0]
    mono = "单调升" if rho > 0.9 else ("单调降" if rho < -0.9 else "非单调")
    peak = int(np.argmax(vals))
    sat = ""
    if mono == "非单调" and 0 < peak < len(vals) - 1:
        sat = f",峰在第{peak + 1}箱后回落"
    elif mono == "单调升" and peak == len(vals) - 1 and len(vals) >= 4 \
            and vals[-1] - vals[-2] < 0.25 * max(vals[-2] - vals[0], 1e-12):
        sat = ",尾箱增益趋缓"
    return mono + sat


def _shape_note(qt: pd.DataFrame) -> str:
    """前瞻收益分箱的形状注记:单调性 + 饱和/回落。

    **主判 med_lab**——本仓评估纪律以 median(forward_return) 为核心指标,
    形状又是交给执行端定硬闸时最要紧的信息(尾箱回落 vs 单调升导出完全不同的闸形)。
    mean_lab 判出不同形状时追加提示:两者打架本身是信息(分布右偏、尾部在拉均值)。
    2026-09-08 那轮该注记按均值判,报告直接抄到自己引用的中位数序列上,
    被复审用它自己贴的数字推翻——故此处主判改为中位数。
    """
    med = qt["med_lab"].to_numpy()
    if len(med) < 3:
        return "箱数不足"
    note = _shape_of(med)
    alt = _shape_of(qt["mean_lab"].to_numpy())
    if alt.split(",")[0] != note.split(",")[0]:
        note += f"(mean_lab 读作{alt.split(',')[0]}——分布有偏,以 med 为准)"
    return note


def _decluster(d: pd.DataFrame, label: str) -> pd.DataFrame:
    """每 symbol 留 label 最高一条——tail_enrichment 消费(镜像 UI 排行榜:排行榜展示的就是每只股票的最佳)。"""
    return d.sort_values(label, ascending=False).groupby("symbol").head(1)


def tail_enrichment(d: pd.DataFrame, flag: str, label: str,
                    ks: tuple[int, ...] = (20, 50, 100)) -> list[str]:
    """二元特征的 top-k 富集(镜像 UI 排行榜视角):per-symbol 最佳行,Fisher vs 基率。只用于前瞻收益口径。"""
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


# ── run_battery ──

def _read(csv_path) -> pd.DataFrame:
    if isinstance(csv_path, pd.DataFrame):
        return csv_path.reset_index(drop=True).copy()
    return pd.read_csv(csv_path, keep_default_na=False, na_values=[""])


def _response(d: pd.DataFrame, label: str, label_type: str) -> tuple[np.ndarray, np.ndarray]:
    """回归因变量与权重:前瞻收益 = (百分位秩, 1);首次穿越 = (份额 up/定向, 定向 bar 数)。"""
    if label_type == "forward_return":
        return _pct_rank(d[label]).to_numpy(float), np.ones(len(d))
    up = d["up"].to_numpy(float)
    dirs = up + d["down"].to_numpy(float) + d["both"].to_numpy(float)
    share = np.divide(up, dirs, out=np.full(len(d), np.nan), where=dirs > 0)
    return share, dirs


def run_battery(csv_path, features: list[str], label: str = "label", *,
                label_type: str = "forward_return",
                binaries: list[str] | None = None,
                controls: list[str] | None = None,
                win_thresholds: tuple[float, float] = (0.10, 0.30),
                label_horizon: int | None = None,
                train_start=None,
                time_col: str = "entry_date",
                extra_pvals: dict | None = None) -> dict:
    """跑全套电池,打印报告文本,返回 {feature: verdict_dict}(供报告引用)。

    参数:
        csv_path: 观测 CSV 路径,或已读好的 DataFrame。
        features / binaries: 连续特征列 / 0-1 二元特征列。
        label: 前瞻收益列名(label_type="forward_return" 时用)。
        label_type: "forward_return" | "first_passage"(见模块文档)。
        controls: 控制列(通常 ["c0_atr_pct"] + adapter.KNOWN_SIGNALS),回归里取百分位秩。
        label_horizon: 标签前瞻期(交易日);给出且有 time_col 列时加时间窗固定效应。
        train_start: 窗号零点;None = 数据里最早的日期。
        extra_pvals: {假设名: p} 同一批里其余假设(如同批闸式判定的闸级 Simes p),并进 BH 族。
    返回 {列名: {"verdict", "direction", "gate1", "gate2", "stable", "q_fdr", "p_raw", "z_raw", "beta_raw",
               "z_ctrl", "shape", "time_flags", "n_windows", "n_years", "by_year", "family_size"}}。
    """
    if label_type not in LABEL_TYPES:
        raise ValueError(f"label_type 只能是 {LABEL_TYPES}: {label_type!r}")
    binaries = list(binaries or [])
    controls = list(controls or [])
    extra = dict(extra_pvals or {})
    fr = label_type == "forward_return"
    d = _read(csv_path)
    need = ["symbol"] + ([label] if fr else list(STATES)) + list(features) + binaries + controls
    missing = [c for c in dict.fromkeys(need) if c not in d.columns]
    if missing:
        raise ValueError(f"观测表缺列 {missing}")
    y, w = _response(d, label, label_type)
    sym = d["symbol"].astype(str).to_numpy()
    base_ok = np.isfinite(y) & (w > 0)

    has_time = label_horizon is not None and time_col in d.columns
    years = None
    FE, n_windows = np.zeros((len(d), 0)), None
    if time_col in d.columns:
        dates = pd.to_datetime(d[time_col], errors="coerce")
        if dates.isna().any():
            raise ValueError(f"{time_col} 列有 {int(dates.isna().sum())} 行不是日期")
        years = dates.dt.year.astype(str).to_numpy()
        if has_time:
            FE, n_windows = _window_dummies(dates, dates.min() if train_start is None else train_start,
                                            label_horizon)
    elif "year" in d.columns:
        years = d["year"].astype(str).to_numpy()
    n_years = None if years is None else len(set(years))

    print(f"n={len(d)}  symbols={d['symbol'].nunique()}  label_type={label_type}")
    if fr:
        print(f"label: mean={d[label].mean():.3f} med={d[label].median():.3f} "
              f"p10={d[label].quantile(.1):.3f} p90={d[label].quantile(.9):.3f}")
    else:
        tot = _group_rate(d)
        print(f"首次穿越合并率={tot['rate']:.4f} [{tot['ci_lo']:.4f}, {tot['ci_hi']:.4f}]  定向 bar={tot['n_dir']}")
    if not controls:
        print("⚠ 无 controls:没有已知信号可控,判定降级(报告必须声明)")
    if not has_time:
        print(f"⚠ 未加时间窗固定效应(缺 {time_col} 列或未传 label_horizon):时间维未控,判定降级")
    elif _time_undetermined(n_windows, n_years):
        print(f"⚠ 有数据的时间窗 {n_windows} 个、年份 {n_years} 个:时间窗固定效应或分年稳定性检查做不了,"
              "判定标「时间维未定」")

    # 关1:原始关联(按股簇稳健回归)
    kinds = {m: "cont" for m in features}
    kinds.update({m: "bin" for m in binaries})
    xs, raw = {}, {}
    print("\n== 关1 原始关联(按股去簇回归 + BH) ==")
    for m, kind in kinds.items():
        v = pd.to_numeric(d[m], errors="coerce")
        if kind == "bin":
            vals = set(v.dropna().unique())
            if not vals <= {0, 1}:
                raise ValueError(f"二元特征 {m} 只能取 0/1,实际取值 {sorted(vals)[:5]}")
            x = v.to_numpy(float)
        else:
            x = _pct_rank(v).to_numpy(float)
        xs[m] = x
        ok = base_ok & np.isfinite(x)
        fit = _coef(y[ok], np.column_stack([np.ones(ok.sum()), x[ok]]), w[ok], sym[ok])
        desc = {}
        if kind == "cont" and fr:
            okl = v.notna() & d[label].notna()
            desc["spearman"] = float(stats.spearmanr(v[okl], d.loc[okl, label])[0])
        elif kind == "cont":
            desc["spearman"] = float(stats.spearmanr(v[ok], y[ok])[0])
        elif fr:
            desc["med_diff"] = float(d.loc[v == 1, label].median() - d.loc[v == 0, label].median())
        else:
            desc["rate1"] = _group_rate(d[v == 1])["rate"]
            desc["rate0"] = _group_rate(d[v == 0])["rate"]
        raw[m] = dict(kind=kind, **fit, **desc)
    names = list(raw)
    qs = inference.bh([raw[m]["p"] for m in names] + list(extra.values())) if names or extra else []
    family_size = len(names) + len(extra)
    for m, q in zip(names, qs):
        v = raw[m]
        v["q_fdr"] = float(q)
        extra_txt = "  ".join(f"{k}={v[k]:+.3f}" for k in ("spearman", "med_diff", "rate1", "rate0")
                              if k in v and np.isfinite(v[k]))
        print(f"{m:24s} [{'二元' if v['kind'] == 'bin' else '连续'}] beta={v['beta']:+.4f} z={v['z']:+.2f} "
              f"p={v['p']:.2g} q={q:.3f} n={v['n']} 股={v['G']}  {extra_txt}")

    # 分箱形状(连续)/ 分组表(二元)
    shapes = {}
    for m in features:
        if fr:
            qt = quantile_table(d, m, label)
            shapes[m] = _shape_note(qt)
        else:
            qt = rate_table(d, m)
            shapes[m] = _shape_of(qt["rate"].to_numpy()) if len(qt) >= 3 else "箱数不足"
        print(f"\n== 分箱: {m}({shapes[m]}) ==")
        print(qt.to_string(float_format=lambda v: f"{v:.3f}"))
    for m in binaries:
        print(f"\n== 分组: {m} ==")
        for name, g in [(f"{m}=1", d[d[m] == 1]), (f"{m}=0", d[d[m] == 0])]:
            if fr:
                print(f"  {name:14s} n={len(g):4d} mean={g[label].mean():.3f} "
                      f"med={g[label].median():.3f} "
                      f"P(>{win_thresholds[0]:.0%})={(g[label] > win_thresholds[0]).mean():.1%} "
                      f"P(>{win_thresholds[1]:.0%})={(g[label] > win_thresholds[1]).mean():.1%}")
            else:
                r = _group_rate(g)
                print(f"  {name:14s} n={r['n']:4d} 定向 bar={r['n_dir']} 合并率={r['rate']:.4f} "
                      f"[{r['ci_lo']:.4f}, {r['ci_hi']:.4f}]")
        if fr:
            for line in tail_enrichment(d, m, label):
                print("  " + line)

    # 特征间 + 与控制的相关结构
    resp_name = label if fr else "首次穿越份额"
    mat = d[list(features) + binaries + controls].apply(pd.to_numeric, errors="coerce")
    mat[resp_name] = d[label] if fr else y
    print("\n== Spearman 矩阵(混杂结构) ==")
    print(mat.corr(method="spearman").round(3).to_string())

    # 关2:控制已知信号 + 时间窗固定效应后的独立贡献
    gate2_run = bool(controls) or has_time
    ctrl = np.column_stack([_pct_rank(d[c]).to_numpy(float) for c in controls]) if controls \
        else np.zeros((len(d), 0))
    ctrl_ok = np.isfinite(ctrl).all(axis=1)
    ctrl_fit = {}
    if gate2_run:
        print("\n== 关2 控制后回归(特征 + controls + 时间窗固定效应,按股去簇) ==")
        for m in names:
            ok = base_ok & np.isfinite(xs[m]) & ctrl_ok
            X = np.column_stack([np.ones(len(d)), xs[m], ctrl, FE])[ok]
            ctrl_fit[m] = _coef(y[ok], X, w[ok], sym[ok])
            print(f"{m:24s} z_ctrl={ctrl_fit[m]['z']:+.2f} n={ctrl_fit[m]['n']}")

    # 分年稳定性(原始口径)
    by_year, stability = {}, {}
    for m in names:
        by_year[m], rest = {}, {}
        if years is not None:
            ok = base_ok & np.isfinite(xs[m])
            for yv in sorted(set(years[ok])):
                for tgt, sel in ((by_year[m], ok & (years == yv)), (rest, ok & (years != yv))):
                    f = _coef(y[sel], np.column_stack([np.ones(sel.sum()), xs[m][sel]]), w[sel], sym[sel])
                    tgt[yv] = (f["beta"], f["se"])
        stability[m] = _unstable(raw[m]["beta"], by_year[m], rest)

    print("\n== 判定 ==")
    verdicts = {}
    for m in names:
        v = raw[m]
        gate1 = bool(v["q_fdr"] < Q_FDR)
        s = float(np.sign(v["beta"])) if np.isfinite(v["beta"]) else 0.0
        zc = ctrl_fit[m]["z"] if gate2_run else float("nan")
        gate2 = bool(np.isfinite(zc) and abs(zc) >= Z_CRIT and np.sign(zc) == s) if gate2_run else None
        stable_flag, stable_note = stability[m]
        time_flags = []
        if has_time and _time_undetermined(n_windows, n_years):
            time_flags.append("时间维未定")
        if not gate1:
            verdict = "无信号"
        elif gate2_run and np.isfinite(zc) and abs(zc) >= Z_CRIT and np.sign(zc) != s:
            verdict = f"反转(suppression):原始方向由控制集承载,控制后残余反向 z={zc:+.2f}"
        elif gate2 is False:
            verdict = "代理(被控制集吸收)"
        elif stable_flag:
            verdict = f"不稳({stable_note},分年功效足够)"
        else:
            verdict = "有信号" if controls else "疑似有信号(无控制,降级)"
            verdict += f",方向{'+' if s > 0 else '−'}"
            if m in shapes:
                verdict += f",形状:{shapes[m]}"
        if gate1:
            if not has_time:
                verdict += ";时间维未控(缺日期列或未传 label_horizon),判定降级"
            elif time_flags:
                verdict += f";时间维未定(有数据的时间窗 {n_windows} 个、年份 {n_years} 个)"
            if stable_flag is None:
                verdict += f";{stable_note}"
        direction = ("+" if s > 0 else "−") if gate1 and s != 0 else None
        verdicts[m] = dict(verdict=verdict, direction=direction, gate1=gate1, gate2=gate2,
                           stable=None if stable_flag is None else not stable_flag,
                           q_fdr=v["q_fdr"], p_raw=v["p"], z_raw=v["z"], beta_raw=v["beta"],
                           z_ctrl=zc if gate2_run else None, shape=shapes.get(m),
                           n_windows=n_windows, n_years=n_years,
                           time_flags=time_flags, by_year={yv: {"est": e, "se": se} for yv, (e, se) in by_year[m].items()},
                           family_size=family_size)
        print(f"{m:24s} → {verdict}")
    return verdicts


# ── 闸式判定 ──

def _cmp(x: np.ndarray, op: str, v) -> np.ndarray:
    """行过闸掩码:v 为 None = 不设闸(全过);字段缺失(NaN)在任何阈值下都不过。"""
    if v is None:
        return np.ones(len(x), dtype=bool)
    with np.errstate(invalid="ignore"):
        if op == ">=":
            return x >= v
        if op == ">":
            return x > v
        if op == "<":
            return x < v
        if op == "<=":
            return x <= v
    raise ValueError(f"不支持的运算符 {op!r}")


def _gate_spec(g) -> tuple:
    """(列名, op, 切点[, 工作点取值]) → (列名, op, 按松→紧排好的切点, 工作点取值或 None)。"""
    if len(g) not in (3, 4):
        raise ValueError(f"闸声明应为 (列名, 运算符, 切点列表[, 工作点取值]): {g!r}")
    col, op, cuts = g[0], g[1], list(g[2])
    working = g[3] if len(g) == 4 else None
    if op not in (">=", ">", "<", "<="):
        raise ValueError(f"闸 {col} 的运算符不支持: {op!r}")
    if not 1 <= len(cuts) <= MAX_CUTS:
        raise ValueError(f"闸 {col} 的切点要 1~{MAX_CUTS} 个,实际 {len(cuts)} 个")
    if any(c is None for c in cuts):
        raise ValueError(f"闸 {col} 的切点不能是「不设」——不设闸就是池本身")
    tighter_up = op in (">=", ">")
    return col, op, sorted(set(cuts), key=lambda c: c if tighter_up else -c), working


class _Events:
    """买点事件表上的按股汇总与对比(条件总体里每个买点事件一行)。"""

    def __init__(self, ev: pd.DataFrame):
        self.up = ev["up"].to_numpy(float)
        self.dirs = self.up + ev["down"].to_numpy(float) + ev["both"].to_numpy(float)
        self.tot = self.dirs + ev["none"].to_numpy(float)
        self.sym, uniq = pd.factorize(ev["symbol"].astype(str))
        self.n_sym = len(uniq)

    def sums(self, mask: np.ndarray) -> tuple:
        f = lambda v: np.bincount(self.sym[mask], weights=v[mask], minlength=self.n_sym)  # noqa: E731
        return f(self.up), f(self.dirs), f(self.tot)

    def contrast(self, a: np.ndarray, b: np.ndarray) -> dict:
        """合并率差 r(a) − r(b) 的按股线性化估计(inference.ratio_contrast)。"""
        ua, da, na = self.sums(a)
        ub, db, nb = self.sums(b)
        rc = inference.ratio_contrast(np.column_stack([ua, ub]), np.column_stack([da, db]),
                                      np.column_stack([na, nb]), [1.0, -1.0])
        est, se = float(rc["est"]), float(rc["se"])
        z = est / se if se > 0 else float("nan")
        return {"est": est, "se": se, "z": z, "p": _p_two(z),
                "ci_lo": est - Z_CRIT * se, "ci_hi": est + Z_CRIT * se}


def _curve_shape(curve: list, kept_masks: list, events: _Events) -> str:
    """闸曲线形状(按合并率):切点按松→紧排,看每档保留集合相对池的合并率差是否显著及其走势。

    记 v_j = 第 j 档相对池的差、t_j = 显著方向(|z| ≥ 1.96 取符号,否则 0)。
        全 0 → 平
        显著方向先负后正 → U 形;先正后负 → 甜点[正区间两端]
        只有一个方向 s,且显著区间没延伸到最紧档 → s>0 甜点[区间两端]、s<0 U 形
        延伸到最紧档(区间起点 a):最紧档相对 a 档不再显著走强 → 台阶@a;
            否则找首个 j>a:j 档相对 a 档显著走强、最紧档相对 j 档不再显著走强 → 饱和@j;找不到 → 单调
    """
    idx = [i for i, e in enumerate(curve) if not e["degenerate"]]
    if not idx:
        return "平"
    sig = [int(np.sign(curve[i]["raw"]["est"])) if abs(curve[i]["raw"]["z"]) >= Z_CRIT else 0 for i in idx]
    nz = [(k, s) for k, s in enumerate(sig) if s != 0]
    if not nz:
        return "平"
    cut = lambda k: _fmt(curve[idx[k]]["cut"])  # noqa: E731
    signs = [s for _, s in nz]
    if len(set(signs)) > 1:
        if signs[0] < 0:
            return "U 形"
        run = [k for k, s in nz if s > 0]
        first_neg = next(k for k, s in nz if s < 0)
        run = [k for k in run if k < first_neg]
        return f"甜点[{cut(run[0])}, {cut(run[-1])}]"
    s = signs[0]
    a, b = nz[0][0], nz[-1][0]
    if b < len(idx) - 1 and all(sig[k] == 0 for k in range(b + 1, len(idx))):
        return f"甜点[{cut(a)}, {cut(b)}]" if s > 0 else "U 形"
    last = len(idx) - 1
    stronger = lambda i, j: s * events.contrast(kept_masks[idx[i]], kept_masks[idx[j]])["z"] >= Z_CRIT  # noqa: E731
    if a == last or not stronger(last, a):
        return f"台阶@{cut(a)}"
    for j in range(a + 1, last):
        if stronger(j, a) and not stronger(last, j):
            return f"饱和@{cut(j)}"
    return "单调"


def _degenerate_words(e: dict) -> str:
    """退化切点的原因:全筛掉 / 全保留 / 定向 bar 全在一侧。"""
    if e["n_events_kept"] == 0:
        return "全筛掉"
    if e["n_events_kept"] == e["n_events_pool"]:
        return "全保留"
    return "定向 bar 全在一侧"


def gate_judgment(rows: pd.DataFrame, gates, *, population_mask, seg_cols, controls, delta: float,
                  train_start, label_horizon: int, B: int = 300, seed: int = 0,
                  extra_pvals: dict | None = None, time_verified: bool | dict = False,
                  family: dict | None = None) -> dict:
    """闸式判定:每道闸在条件总体里挣没挣到位置(首次穿越口径,观测单位 = 买点事件)。

    参数:
        rows: 长表行,列含 symbol、date(或 buy_date)、M、up/down/both/none、seg_cols、各闸字段列、controls 各列。
            同一买点事件可有多行(不同前缀,闸字段取值可能不同);四态、日期、M 只由买点事件决定,多行不一致即报错。
        gates: [(列名, 运算符, [切点, ...≤4]) 或 (列名, 运算符, [切点...], 工作点取值), ...]。切点须在读标签前冻结。
            工作点取值 = 这道闸在判定所服务的配置里的现值(None 或省略 = 不在配置里的候选闸):
            它决定其余闸的池(判第 g 道闸时,其余闸都按各自工作点取值过滤),也是非劣效「关 − 开」里「开」的位置。
        population_mask: 与 rows 等长的布尔数组 = 条件总体(检测参数与不在 gates 里的闸已按配置过滤,gates 里的闸全放开)。
        seg_cols: 买点事件键列(与 symbol 一起认出同一段买点)。
        controls: 控制列(回归里取百分位秩);时间窗固定效应总是加。
        delta: 最小关心改进(比例,0.02 = 2 点)。
        train_start / label_horizon: 时间窗零点与窗宽来源(窗宽 = inference.time_window_days(label_horizon))。
        B / seed: 层匹配差按股 bootstrap 的副本数与种子。
        extra_pvals: {假设名: p} 同一批里的其余假设(如同批连续特征),与闸级 p 一起做 BH。
        time_verified: 本批数据是否与闸的发现样本时间不相交(bool 对全部闸,或 {列名: bool} 逐闸);
            False → 标「时间维未验证」,不归「确实有用」。
        family: {列名: [进族切点, ...]} 读标签前冻结的族(每道闸都要给,可为空列表;切点须在这道闸的切点里)。
            给了 → 进族严格按它,现场算的功效只作诊断(stats 的 mde_measured / power_ok_measured);
            None → 没有预注册的探索性调用,按池的实测设计效应现场决定进族(stats 标「现场实测(未预注册)」)。

    算法(每道闸 g):
        1. 池 = 条件总体里过其余闸工作点取值的行;买点事件在切点 t 下过闸 ⟺ 它在池里至少有一行满足 g 的切点(任一行过闸)。
        2. 每个切点:保留占比 r = 保留定向 bar / 池定向 bar;原始差 = 保留合并率 − 池合并率(按股线性化 SE);
           层匹配差(inference.layer_matched_diff,池内 M 三分位 × 时间窗);分年原始差;
           控制后回归(因变量 = 买点事件首次穿越份额,按定向 bar 加权;自变量 = 过闸指示 + 控制列 + 时间窗固定效应;按股 CR1)。
        3. 进族:给了 family 就按冻结族(冻结族里的切点在这批数据上退化——全保留或全筛掉——照常记退化、不参与合成,
           reason 里说明);没给就现场功效预检:SE ≈ √(p0(1−p0)·deff/D_池·(1−r)/r),p0 = 0.5,deff = 池的实测设计效应,
           MDE = 2.8·SE,MDE > δ 的切点不进族。无论哪种,实测 MDE 与是否够功效都记进 curve 与 stats 作诊断。
           一个切点都进不了族的闸判「分辨不出」。
        4. 闸内 Simes 合成闸级 p;闸间(连同 extra_pvals)BH,q < 0.05 为显著。
        5. 判定:显著时看领头切点(族内 p 最小)控制后 z:反号显著 → 反转;不显著 → 代理;同号显著 → 分年稳定性检查
           (_unstable,功效不足不判)不过 → 不稳,过 → 有信号±。不显著时:族内切点原始差 CI 上界都 < δ → 无信号,否则分辨不出。
        6. 非劣效(有工作点取值时):工作点「关 − 开」= 池合并率 − 工作点保留合并率,单侧 95% 下界 ≥ −δ 为通过。
        7. 归栏:有信号+ 且时间维已验证 → 确实有用;非劣效通过且不是有信号+ → 没用删了不亏;其余 → 判不了(附原因)。
        8. curve / shape / effective_interval(CI 在判定方向上不含 0 的切点范围)/ suggested_levels([不设, 区间两端与中点],≤4)/ ni / stats。
    返回 {列名: {"verdict", "direction", "bucket", "reason", "time_flags", "curve", "shape", "effective_interval",
               "suggested_levels", "ni", "stats"}};估计量一律是比例。
    """
    d = rows.reset_index(drop=True)
    specs = [_gate_spec(g) for g in gates]
    names = [s[0] for s in specs]
    if len(set(names)) != len(names):
        raise ValueError(f"同一列不能声明成两道闸: {names}")
    if family is not None:
        stray, lacking = sorted(set(family) - set(names)), [c for c in names if c not in family]
        if stray or lacking:
            raise ValueError(f"冻结族的列与闸对不上:多出 {stray},缺 {lacking}")
        for col, _, cuts, _ in specs:
            off = [c for c in family[col] if c not in cuts]
            if off:
                raise ValueError(f"冻结族里「{col}」的切点 {off} 不在这道闸的切点 {cuts} 里")
    date_col = "date" if "date" in d.columns else "buy_date"
    seg_cols, controls = list(seg_cols), list(controls)
    need = ["symbol", date_col, "M", *STATES, *seg_cols, *controls, *names]
    missing = [c for c in dict.fromkeys(need) if c not in d.columns]
    if missing:
        raise ValueError(f"rows 缺列 {missing}")
    pop = np.asarray(population_mask, dtype=bool)
    if pop.shape != (len(d),):
        raise ValueError(f"population_mask 长度 {pop.shape} 与 rows 行数 {len(d)} 不符")
    if not pop.any():
        raise ValueError("population_mask 一行都没选中")
    key_cols = ["symbol"] + [c for c in seg_cols if c != "symbol"]
    if d[key_cols].isna().any().any():
        raise ValueError(f"买点事件键 {key_cols} 有缺失值,认不出哪些行是同一段买点")
    row_ev = d.groupby(key_cols, sort=False, observed=True).ngroup().to_numpy()
    const_cols = [*STATES, date_col, "M"]
    nun = d.groupby(row_ev)[const_cols].nunique(dropna=False).max()
    bad = [c for c in const_cols if nun[c] > 1]
    if bad:
        raise ValueError(f"同一个买点事件的多行在 {bad} 上取值不同——这些量只应由买点事件决定,数据口径坏了")

    # 买点事件表:每个事件取条件总体里的第一行(控制列若随前缀变化,取数据原序第一行)
    pop_idx = np.flatnonzero(pop)
    first = pd.Series(pop_idx).groupby(row_ev[pop_idx], sort=True).first()
    remap = np.full(int(row_ev.max()) + 1, -1, dtype=np.int64)
    remap[first.index.to_numpy()] = np.arange(len(first))
    rev = remap[row_ev]
    ev = d.iloc[first.to_numpy()].reset_index(drop=True)
    E = len(ev)
    events = _Events(ev)
    dates = pd.to_datetime(ev[date_col])
    years = dates.dt.year.astype(str).to_numpy()
    share = np.divide(events.up, events.dirs, out=np.full(E, np.nan), where=events.dirs > 0)
    win_days = inference.time_window_days(label_horizon)
    win_codes, _ = inference.time_window_codes(dates, train_start, win_days)
    win_num = win_codes.astype(np.int64)
    lm_all = pd.DataFrame({"symbol": ev["symbol"].astype(str).to_numpy(), "date": dates.to_numpy(),
                           "M": pd.to_numeric(ev["M"], errors="coerce").to_numpy(float),
                           "up": events.up, "down": ev["down"].to_numpy(float), "both": ev["both"].to_numpy(float)})

    def any_by_event(mask_rows: np.ndarray) -> np.ndarray:
        out = np.zeros(E, dtype=bool)
        out[rev[mask_rows & pop]] = True
        return out

    fields = {c: pd.to_numeric(d[c], errors="coerce").to_numpy(float) for c in names}
    gate_out = {}
    for col, op, cuts, working in specs:
        other = pop.copy()
        for col2, op2, _, w2 in specs:
            if col2 != col and w2 is not None:
                other &= _cmp(fields[col2], op2, w2)
        pool_rows = other
        in_pool = any_by_event(pool_rows)
        n_pool, dir_pool = int(in_pool.sum()), float(events.dirs[in_pool].sum())
        lv = inference.level_se(*events.sums(in_pool)) if dir_pool > 0 else {"deff": float("nan")}
        deff = float(lv["deff"])
        pool_years = sorted(set(years[in_pool]))
        pool_by_year = {yv: {"n_events": int((in_pool & (years == yv)).sum()),
                             "n_dir": float(events.dirs[in_pool & (years == yv)].sum())} for yv in pool_years}
        n_windows = len(set(win_num[in_pool]))

        # 控制后回归的公共设计:池里有定向 bar 的买点事件
        reg = in_pool & (events.dirs > 0)
        ctrl = np.column_stack([_pct_rank(ev[c].to_numpy()[reg]).to_numpy(float) for c in controls]) \
            if controls else np.zeros((int(reg.sum()), 0))
        ctrl_ok = np.isfinite(ctrl).all(axis=1)
        reg_idx = np.flatnonzero(reg)[ctrl_ok]
        ctrl = ctrl[ctrl_ok]
        present = sorted(set(win_num[reg_idx]))
        FE = (win_num[reg_idx][:, None] == np.array(present[1:])[None, :]).astype(float)
        y_reg, w_reg, g_reg = share[reg_idx], events.dirs[reg_idx], events.sym[reg_idx]

        def controlled(kept: np.ndarray, weighted=True, clustered=True) -> dict:
            X = np.column_stack([np.ones(len(reg_idx)), kept[reg_idx].astype(float), ctrl, FE])
            return _coef(y_reg, X, w_reg if weighted else np.ones(len(reg_idx)),
                         g_reg if clustered else np.arange(len(reg_idx)))

        xg = fields[col]
        curve, kept_masks = [], []
        for t in cuts:
            kept = any_by_event(pool_rows & _cmp(xg, op, t)) & in_pool
            kept_masks.append(kept)
            n_k, dir_k = int(kept.sum()), float(events.dirs[kept].sum())
            r = dir_k / dir_pool if dir_pool > 0 else float("nan")
            e = {"cut": t, "keep_ratio": r, "n_events_pool": n_pool, "n_events_kept": n_k,
                 "n_dir_pool": dir_pool, "n_dir_kept": dir_k}
            if n_k == 0 or n_k == n_pool or not (0 < r < 1):
                e.update(degenerate=True, powered=False, mde=float("nan"), raw=None, layer_matched=None,
                         controlled=None, by_year={})
                curve.append(e)
                continue
            se_pre = math.sqrt(P0 * (1 - P0) * deff / dir_pool * (1 - r) / r) if np.isfinite(deff) else float("nan")
            mde = float(budget.x_single(se_pre))
            lm = inference.layer_matched_diff(lm_all[in_pool].reset_index(drop=True), kept[in_pool],
                                              train_start=train_start, win_days=win_days, B=B, seed=seed)
            lm_z = lm["est"] / lm["se"] if lm["se"] > 0 else float("nan")
            e.update(degenerate=False, powered=bool(np.isfinite(mde) and mde <= delta), mde=mde,
                     raw=events.contrast(kept, in_pool),
                     layer_matched={"est": lm["est"], "se": lm["se"], "z": lm_z,
                                    "ci_lo": lm["est"] - Z_CRIT * lm["se"], "ci_hi": lm["est"] + Z_CRIT * lm["se"],
                                    "coverage": lm["coverage"], "n_layers": lm["n_layers"]},
                     controlled=controlled(kept),
                     by_year={yv: {**events.contrast(kept & (years == yv), in_pool & (years == yv)),
                                   "n_events_kept": int((kept & (years == yv)).sum()),
                                   "n_dir_kept": float(events.dirs[kept & (years == yv)].sum())}
                              for yv in pool_years})
            curve.append(e)

        for e in curve:
            e["in_family"] = bool(e["cut"] in family[col]) if family is not None else e["powered"]
        live = [i for i, e in enumerate(curve) if not e["degenerate"]]
        fam = [i for i in live if curve[i]["in_family"]]
        degen = [f"{_fmt(e['cut'])}({_degenerate_words(e)})" for e in curve if e["degenerate"] and e["in_family"]]
        lead = min(fam or live, key=lambda i: curve[i]["raw"]["p"]) if live else None
        simes_p = inference.simes([curve[i]["raw"]["p"] for i in fam]) if fam else float("nan")

        extra_stats, stability = {}, (None, "")
        if lead is not None:
            kept = kept_masks[lead]
            est_lead = curve[lead]["raw"]["est"]
            rest = {yv: events.contrast(kept & (years != yv), in_pool & (years != yv)) for yv in pool_years}
            stability = _unstable(est_lead, {yv: (b["est"], b["se"]) for yv, b in curve[lead]["by_year"].items()},
                                  {yv: (b["est"], b["se"]) for yv, b in rest.items()})
            eq_k = float(np.nanmean(share[kept])) if (kept & (events.dirs > 0)).any() else float("nan")
            eq_p = float(np.nanmean(share[in_pool])) if (in_pool & (events.dirs > 0)).any() else float("nan")
            eq = eq_k - eq_p
            extra_stats = {
                "three_cols": {"加权不去簇": controlled(kept, clustered=False),
                               "加权去簇": curve[lead]["controlled"],
                               "不加权去簇": controlled(kept, weighted=False)},
                "segment_equal_weight": {"est": eq, "diff_from_main": eq - est_lead,
                                         "flag": bool(abs(eq - est_lead) > curve[lead]["raw"]["se"])},
            }

        ni = None
        if working is not None:
            kept_w = any_by_event(pool_rows & _cmp(xg, op, working)) & in_pool
            if int(kept_w.sum()) == n_pool:
                ni = {"working": working, "est": 0.0, "se": 0.0, "lower": 0.0, "upper": 0.0, "delta": delta,
                      "pass": True, "better_off": False, "note": "工作点上这道闸一个买点事件都没筛掉"}
            else:
                c = events.contrast(in_pool, kept_w)
                lower, upper = c["est"] - Z_ONE * c["se"], c["est"] + Z_ONE * c["se"]
                ni = {"working": working, "est": c["est"], "se": c["se"], "lower": lower, "upper": upper,
                      "delta": delta, "pass": bool(np.isfinite(lower) and lower >= -delta),
                      "better_off": bool(np.isfinite(upper) and upper < 0), "note": ""}

        gate_out[col] = dict(op=op, cuts=cuts, working=working, curve=curve, fam=fam, lead=lead, simes_p=simes_p,
                             degen_note=f"预注册进族的切点 {'、'.join(degen)} 在这批数据上退化,没参与合成" if degen else "",
                             stability=stability, extra_stats=extra_stats, ni=ni, deff=deff, n_windows=n_windows,
                             pool_by_year=pool_by_year,
                             shape=_curve_shape(curve, kept_masks, events))

    fam_names = [c for c in names if gate_out[c]["fam"]]
    pvals = [gate_out[c]["simes_p"] for c in fam_names] + list((extra_pvals or {}).values())
    qs = dict(zip(fam_names, inference.bh(pvals))) if pvals else {}
    family_size = len(pvals)

    out = {}
    for col in names:
        g = gate_out[col]
        curve, lead = g["curve"], g["lead"]
        q = float(qs.get(col, float("nan")))
        direction = None
        if not g["fam"]:
            verdict = "分辨不出"
        elif q < Q_FDR:
            L = curve[lead]
            s = float(np.sign(L["raw"]["est"]))
            zc = L["controlled"]["z"]
            direction = "+" if s > 0 else "−"
            if np.isfinite(zc) and abs(zc) >= Z_CRIT and np.sign(zc) != s:
                verdict = "反转"
            elif not (np.isfinite(zc) and abs(zc) >= Z_CRIT):
                verdict = "代理"
            elif g["stability"][0]:
                verdict = "不稳"
            else:
                verdict = f"有信号{direction}"
        else:
            upper = max(curve[i]["raw"]["ci_hi"] for i in g["fam"])
            verdict = "无信号" if upper < delta else "分辨不出"

        time_flags = []
        if _time_undetermined(g["n_windows"], len(g["pool_by_year"])):
            time_flags.append("时间维未定")
        verified = bool(time_verified.get(col, False)) if isinstance(time_verified, dict) else bool(time_verified)
        if not verified:
            time_flags.append("时间维未验证")

        ni = g["ni"]
        if verdict == "有信号+" and verified:
            bucket, reason = "确实有用", ""
        elif ni is not None and ni["pass"] and verdict != "有信号+":
            bucket, reason = "没用删了不亏", ("删了反而更好" if ni["better_off"] else "")
        else:
            bucket = "判不了"
            reason = {
                "分辨不出": "样本不够",
                "有信号+": "还不能排除是某段行情特有的(时间维未验证)",
                "不稳": f"效果集中在少数股票或时段({g['stability'][1]})",
                "代理": "效果来自波动率构成或所处时段(控制波动率与时间窗后消失)",
                "反转": "控制波动率、已知信号与时间窗后方向反过来",
                "有信号−": "这道闸做负功" + ("" if ni is None else ",但关掉它的损失上限证明不了小于最小关心改进"),
                "无信号": "没有可检出的效果" + ("" if ni is None else ",但关掉它的损失上限超过最小关心改进"),
            }[verdict]
        if g["degen_note"]:
            reason = ";".join(x for x in (reason, g["degen_note"]) if x)

        sgn = -1 if direction == "−" else 1
        hits = [curve[i]["cut"] for i in range(len(curve)) if not curve[i]["degenerate"]
                and (curve[i]["raw"]["ci_lo"] > 0 if sgn > 0 else curve[i]["raw"]["ci_hi"] < 0)]
        interval = [min(hits), max(hits)] if hits else None
        levels = None
        if interval:
            mid = (interval[0] + interval[1]) / 2
            if all(float(c).is_integer() for c in g["cuts"]):
                mid = int(round(mid))
            levels = list(dict.fromkeys([None, interval[0], mid, interval[1]]))[:MAX_CUTS]

        L = curve[lead] if lead is not None else None
        stats_ = {
            "simes_p": g["simes_p"], "bh_q": q, "family_size": family_size,
            "controls": controls + ["时间窗固定效应"],
            "lead_cut": L["cut"] if L else None,
            "raw": L["raw"] if L else None,
            "layer_matched": L["layer_matched"] if L else None,
            "controlled": L["controlled"] if L else None,
            "three_cols": g["extra_stats"].get("three_cols"),
            "segment_equal_weight": g["extra_stats"].get("segment_equal_weight"),
            "family_source": "现场实测(未预注册)" if family is None else "预注册冻结",
            "family_cuts": [e["cut"] for e in curve if e["in_family"]],
            "power_ok": bool(g["fam"]),
            "mde_measured": {e["cut"]: e["mde"] for e in curve},
            "power_ok_measured": any(e["powered"] for e in curve),
            "deff": g["deff"],
            "stability": g["stability"][1],
            "n_windows": g["n_windows"],
            "n_years": len(g["pool_by_year"]),
            "pool_by_year": g["pool_by_year"],
        }
        out[col] = dict(verdict=verdict, direction=direction, bucket=bucket, reason=reason, time_flags=time_flags,
                        curve=curve, shape=g["shape"], effective_interval=interval, suggested_levels=levels,
                        ni=ni, stats=stats_)
    return out
