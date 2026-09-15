# -*- coding: utf-8 -*-
"""tune-gates · 优势检查估计量与分辨力。

优势检查回答「pattern 的买点比同一天、同一波动层的普通交易日好多少」:
    Δ = pattern 首次穿越率 − 按 pattern 的层构成加权的基线首次穿越率
层 = 时间单元(默认同一交易日)× 当期横截面 M(ATR%)三分位。高波动股、行情好的日子本身首次穿越率
就不同,按层匹配后 Δ 读到的是 pattern 本身,而不是它在「哪段行情、多高波动」上的构成。

判读(`edge_verdict`,δ = 最小关心改进):
- 95% CI 下界 > 0 → 有边际;
- 否则 CI 上界 < δ → 没有(相对同层基线没有值得关心的优势,停);
- 其余 → 未证实。
宽进点(闸全放开)不是有边际、工作点是有边际 → 优势来自在役闸(`edge_source_note`):
pattern 的检测结构本身没带来边际,边际是闸筛出来的。

分辨力(`resolution`)回答「工作点这点样本能分辨多小的改进」:从工作点格的每股计数和算按股线性化 SE、
设计效应、定向占比,换算成一次改动的差值 SE,以及筛选 / 单个预写改动能分辨的最小改进。

纯 numpy / pandas;统计核与预算复用同目录的 inference、budget。
口径约定:
- 首次穿越率 = up / (up+down+both),none 排除;定向计数 = up+down+both。
- 估计量、SE、δ 一律用比例(0.02 = 2 点),报告层再乘 100。
- 误差按股去簇:股票是 bootstrap 的独立单位,pattern 股与基线股各自独立抽。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
import budget  # noqa: E402
import inference  # noqa: E402

ROW_COLS = ("symbol", "date", "M", "up", "down", "both")
TIME_KEYS = ("day", "win")
CUTS = ("per", "global")
R_BAR_SOURCES = ("标定先验", "实测")
CI_Z = 1.96


# ── 优势检查 ──

def _prepare(rows: pd.DataFrame, name: str) -> dict:
    """丢 M 缺失行,取出计算用的列:symbol、date(归一到日)、M、up、dirs(= up+down+both)。"""
    missing = [c for c in ROW_COLS if c not in rows.columns]
    if missing:
        raise ValueError(f"{name} 缺列 {missing}")
    M = rows["M"].to_numpy(dtype=float)
    ok = ~np.isnan(M)
    up = rows["up"].to_numpy(dtype=float)[ok]
    dirs = up + rows["down"].to_numpy(dtype=float)[ok] + rows["both"].to_numpy(dtype=float)[ok]
    return {"symbol": rows["symbol"].to_numpy()[ok],
            "date": pd.to_datetime(rows["date"]).dt.normalize().to_numpy()[ok],
            "M": M[ok], "up": up, "dirs": dirs}


def _time_units(p_dates, b_dates, time_key: str, win_days: int | None):
    """时间单元的整数编码:day = 日期本身;win = (date − 基线最早日).days // win_days。"""
    if time_key == "day":
        return p_dates.astype(np.int64), b_dates.astype(np.int64)
    origin = b_dates.min()
    one_day = np.timedelta64(1, "D")
    return (p_dates - origin) // one_day // win_days, (b_dates - origin) // one_day // win_days


def _layer_keys(p: dict, b: dict, *, time_key: str, cut: str, win_days: int | None):
    """层键 = 时间单元序号 × 3 + 层,层 = (M > q1) + (M > q2)。

    p、b 为 `_prepare` 的输出,基线非空。切点取基线行 M 的 1/3、2/3 分位(pandas quantile 默认线性插值,
    基线行等权、含 none 行):per = 每个时间单元内分别取,global = 全部基线行取一次。
    pattern 行所在时间单元没有基线行 → 层键 −1。
    返回 (pattern 层键, 基线层键, 时间单元数)。
    """
    p_unit, b_unit = _time_units(p["date"], b["date"], time_key, win_days)
    if cut == "per":
        qq = pd.Series(b["M"]).groupby(b_unit).quantile([1 / 3, 2 / 3]).unstack()
        units = qq.index.to_numpy()
        q1, q2 = qq.iloc[:, 0].to_numpy(), qq.iloc[:, 1].to_numpy()
    else:
        units = np.unique(b_unit)
        g1, g2 = pd.Series(b["M"]).quantile([1 / 3, 2 / 3]).to_numpy()
        q1, q2 = np.full(len(units), g1), np.full(len(units), g2)
    b_code = np.searchsorted(units, b_unit)
    b_key = b_code * 3 + (b["M"] > q1[b_code]) + (b["M"] > q2[b_code])
    p_code = np.minimum(np.searchsorted(units, p_unit), len(units) - 1)
    found = units[p_code] == p_unit
    p_key = np.where(found, p_code * 3 + (p["M"] > q1[p_code]) + (p["M"] > q2[p_code]), -1)
    return p_key, b_key, len(units)


def _stock_layer_sums(side: dict, col: np.ndarray, L: int):
    """「股 × 可用层」的 up 和与定向和稠密矩阵 (S, L);行 = 在可用层里有行的股票。"""
    inside = col >= 0
    sym, uniq = pd.factorize(side["symbol"][inside])
    S = len(uniq)
    flat = sym * L + col[inside]
    U = np.bincount(flat, weights=side["up"][inside], minlength=S * L).reshape(S, L)
    D = np.bincount(flat, weights=side["dirs"][inside], minlength=S * L).reshape(S, L)
    return U, D


def _delta(pu, pdn, bu, bdn):
    """每行一个副本:pu/pdn/bu/bdn 形状 (b, L) 为各层加权和 → (Δ, pattern 率, 同层基线率),各 (b,)。

    Δ = Σ_k pu_k / Σ_k pd_k − Σ_{k∈m} (pd_k / Σ_{k∈m} pd_k)·(bu_k / bd_k),m = {k : bd_k > 0}。
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        p_rate = pu.sum(axis=1) / pdn.sum(axis=1)
        has_base = bdn > 0
        w = np.where(has_base, pdn, 0.0)
        b_rate = (w * np.where(has_base, bu / bdn, 0.0)).sum(axis=1) / w.sum(axis=1)
    return p_rate - b_rate, p_rate, b_rate


def edge_delta(pattern_rows, base_rows, *, time_key: str = "day", cut: str = "per",
               B: int = 300, seed: int = 0, min_dir: int = 20, win_days: int | None = None) -> dict:
    """pattern 相对同层基线的首次穿越率超额 Δ,及按股 bootstrap 的 SE 与 95% CI。

    参数:
        pattern_rows: DataFrame[symbol, date, M, up, down, both] = 被检的买点(宽进点或工作点)。
                      计数逐行口径取 0/1;买点事件口径取事件内计数,可直接喂入。
        base_rows: 同列的基线逐日行(每只股每个合格交易日一行,四态 one-hot)。
        time_key: 时间单元。"day" = 同一交易日;"win" = (date − 基线最早日).days // win_days,作敏感性选项。
        cut: M 三分位切点。"per" = 每个时间单元内基线行的分位;"global" = 全部基线行的分位。
        B, seed: bootstrap 副本数与种子。
        min_dir: 层可用所需的基线定向计数下限。
        win_days: time_key="win" 时必填,调用方用 inference.time_window_days(label_horizon) 推出。
    算法:
        1. 两侧丢 M 缺失行;定向计数 = up+down+both。
        2. 时间单元见 time_key;"win" 的零点取丢行后的基线最早日。
        3. 切点见 cut(pandas quantile 默认线性插值;基线行等权,含 none 行);层 = (M > q1) + (M > q2)。
           pattern 行所在时间单元没有基线行 → 层 −1,不进任何层。
        4. 层键 k = (时间单元, 层);可用层 = 基线在该层的定向计数 ≥ min_dir。
           覆盖率 = 可用层内 pattern 定向计数 / 全部 pattern 定向计数。
        5. 只留可用层,建「股 × 层」矩阵:pattern 侧 up 和 PU、定向和 PD,基线侧 BU、BD;两侧股票各自编号。
        6. est(wp, wb):pu_k = Σ_s wp_s·PU_{s,k}(pd_k、bu_k、bd_k 同理);m = {k : bd_k > 0};
           Δ = Σ_k pu_k / Σ_k pd_k − Σ_{k∈m} (pd_k / Σ_{k∈m} pd_k)·(bu_k / bd_k)
           前一项 = pattern 首次穿越率,后一项 = 按 pattern 层构成加权的基线首次穿越率。
        7. 点估计取 wp = wb = 1。SE:B 个副本,pattern 股与基线股各自独立抽 multinomial(n, 1/n) 权重
           (n = 该侧矩阵的股票数),取副本 Δ 的样本标准差(ddof=1);CI = Δ ± 1.96·SE。
           可用层与切点固定取原样本。副本里 Δ 无定义(某侧定向和为 0,样本极少时才会发生)→ SE 为 nan,
           判读落到「未证实」。
    内存:矩阵稠密,每侧约 16 字节 × 股票数 × 可用层数(全宇宙逐日基线 5000 股 × 1500 层约 120MB)。
    返回 {"est", "se", "ci_lo", "ci_hi", "coverage", "n_layers", "pattern_rate", "matched_base_rate",
          "n_pattern_dir", "n_base_dir", "n_pattern_symbols", "n_base_symbols"}:
        n_layers = 可用层数;n_*_dir、n_*_symbols = 进入可用层的定向计数与股票数(后者即 bootstrap 的簇数)。
        没有可用层或某侧为空时 est、se 为 nan。
    """
    if time_key not in TIME_KEYS:
        raise ValueError(f"time_key 须为 {TIME_KEYS} 之一,实际 {time_key!r}")
    if cut not in CUTS:
        raise ValueError(f"cut 须为 {CUTS} 之一,实际 {cut!r}")
    if time_key == "win" and win_days is None:
        raise ValueError("time_key='win' 时必须传 win_days(用 inference.time_window_days(label_horizon) 推出)")
    p, b = _prepare(pattern_rows, "pattern_rows"), _prepare(base_rows, "base_rows")

    if len(b["M"]):
        p_key, b_key, n_units = _layer_keys(p, b, time_key=time_key, cut=cut, win_days=win_days)
    else:
        p_key, b_key, n_units = np.full(len(p["M"]), -1), np.empty(0, dtype=np.int64), 0
    usable = np.bincount(b_key, weights=b["dirs"], minlength=3 * n_units) >= min_dir
    L = int(usable.sum())
    col = np.full(3 * n_units + 1, -1)          # 末位留给层键 −1
    col[:-1][usable] = np.arange(L)
    p_col, b_col = col[p_key], col[b_key]

    p_dir_all = p["dirs"].sum()
    coverage = float(p["dirs"][p_col >= 0].sum() / p_dir_all) if p_dir_all > 0 else float("nan")
    PU, PD = _stock_layer_sums(p, p_col, L)
    BU, BD = _stock_layer_sums(b, b_col, L)
    Sp, Sb = PU.shape[0], BU.shape[0]

    col_sum = lambda X: X.sum(axis=0)[None, :]  # noqa: E731
    est, p_rate, b_rate = (float(v[0]) for v in _delta(col_sum(PU), col_sum(PD), col_sum(BU), col_sum(BD)))
    se = float("nan")
    if Sp and Sb and L and B >= 2:
        rng = np.random.default_rng(seed)
        WP = inference._stock_weights(rng, Sp, B)
        WB = inference._stock_weights(rng, Sb, B)
        with np.errstate(invalid="ignore"):
            se = float(np.std(_delta(WP @ PU, WP @ PD, WB @ BU, WB @ BD)[0], ddof=1))
    return {"est": est, "se": se, "ci_lo": est - CI_Z * se, "ci_hi": est + CI_Z * se,
            "coverage": coverage, "n_layers": L, "pattern_rate": p_rate, "matched_base_rate": b_rate,
            "n_pattern_dir": int(PD.sum()), "n_base_dir": int(BD.sum()),
            "n_pattern_symbols": Sp, "n_base_symbols": Sb}


def edge_by_year(pattern_rows, base_rows, **kw) -> dict:
    """逐年分别做优势检查,另报全部年份合并。

    年份按 date 切,取 pattern 行出现的年份;两侧都只留该年的行后调 edge_delta(**kw)。
    time_key="win" 时各年的窗号零点是该年基线最早日。
    返回 {"<年>": edge_delta 输出, ..., "pooled": 全部行的 edge_delta 输出}。
    """
    p_year = pd.to_datetime(pattern_rows["date"]).dt.year.to_numpy()
    b_year = pd.to_datetime(base_rows["date"]).dt.year.to_numpy()
    out = {}
    for y in sorted(set(p_year.tolist())):
        out[str(y)] = edge_delta(pattern_rows[p_year == y], base_rows[b_year == y], **kw)
    out["pooled"] = edge_delta(pattern_rows, base_rows, **kw)
    return out


def edge_verdict(res: dict, delta: float) -> str:
    """三分支判读:ci_lo > 0 → "有边际";否则 ci_hi < δ → "没有";否则 "未证实"(含 SE 为 nan)。"""
    if res["ci_lo"] > 0:
        return "有边际"
    if res["ci_hi"] < delta:
        return "没有"
    return "未证实"


def edge_source_note(wide: dict, working: dict) -> str | None:
    """边际来源提示。

    参数:wide、working 各为 {年: verdict}(宽进点 / 工作点)。逐个两边都有的键比较(调用方若带上合并键
    pooled 也一并比);存在某键「宽进点不是有边际、工作点是有边际」→ "优势来自在役闸",否则 None。
    """
    for k, v in wide.items():
        if k in working and v != "有边际" and working[k] == "有边际":
            return "优势来自在役闸"
    return None


# ── 分辨力 ──

def resolution(U, D, N, *, delta: float, m: int, q: float, r_bar: float, r_bar_source: str,
               n_folds: int, p: float = 0.5) -> dict:
    """工作点格的分辨力:这点样本能分辨多小的改进,以及两个参数联合调够不够。

    参数:
        U, D, N: 工作点格(按买点事件去重后)n_folds 折合并的每股计数和,形状 (S,);
                 U = up,D = 定向(up+down+both),N = 全部(含 none)。
        delta: 最小关心改进 δ(比例)。
        m: 筛选实际要比的对比族大小,由调用方按设计算出。
        q: 筛选的 BH 阈值。
        r_bar: 改动后的买点保留比例 r̄。r_bar_source ∈ {"标定先验", "实测"}:筛选之前只能传
               budget.R_BAR_DETECT_PRIOR 与 "标定先验"(由此算出的量是估计),筛选之后传实测保留比例与 "实测"。
        n_folds: U/D/N 合并了几折(如分年的两年 → 2)。功效线与噪声地板都是「每折」口径,
                 地板按每折 bar 数 ΣN / n_folds 算;直接用合并 bar 数会把地板低估 √n_folds 倍。
        p: 功效线与噪声地板用的基准首次穿越率。
    公式:
        SE_level、设计效应 deff 取 inference.level_se(U, D, N):按股线性化 SE,deff = (SE_level / √(r(1−r)/ΣD))²
        定向占比 s_dec = ΣD / ΣN
        SE_flip = SE_level·√((1−r̄)/r̄)
        x_screen = (z_BH(m, q) + 0.84)·SE_flip(筛选能分辨的最小改进);x_single = 2.8·SE_flip(单个预写改动)
        n_pl = 1.96·p(1−p)·deff / (1.2·s_dec·δ²)(功效线:每折所需全部 bar 数)
        n_bars_per_fold = ΣN / n_folds
        floor_upper = 1.4·√(p(1−p)·deff / (1.2·n_bars_per_fold·s_dec))(本格每折样本量下的噪声地板上界)
        joint_feasible_2 = 2.8·1.7·SE_flip ≤ δ(两个参数同改是否分辨得出 δ)
        deff、s_dec 一律取本格实测,不回退任何标定常数。
    判读:x_single > δ → 单个改动在这点样本上分辨不出 δ 大的改进;joint_feasible_2 为 False → 不宜两个参数联合调。
    返回 {"se_level", "deff", "s_dec", "n_dir", "n_bars", "n_bars_per_fold", "se_flip", "x_screen", "x_single",
          "n_pl", "floor_upper", "joint_feasible_2", "m", "r_bar", "r_bar_source"};n_dir、n_bars 为合并计数。
    """
    if r_bar_source not in R_BAR_SOURCES:
        raise ValueError(f"r_bar_source 须为 {R_BAR_SOURCES} 之一,实际 {r_bar_source!r}")
    if n_folds < 1:
        raise ValueError(f"n_folds 须 ≥ 1,实际 {n_folds}")
    lv = inference.level_se(U, D, N)
    n_bars = float(np.asarray(N, dtype=float).sum())
    s_dec = lv["n_dir"] / n_bars if n_bars > 0 else float("nan")
    per_fold = n_bars / n_folds
    sf = budget.se_flip(lv["se"], r_bar)
    return {"se_level": lv["se"], "deff": lv["deff"], "s_dec": s_dec,
            "n_dir": int(lv["n_dir"]), "n_bars": int(n_bars), "n_bars_per_fold": per_fold,
            "se_flip": sf, "x_screen": budget.x_screen(sf, m, q), "x_single": budget.x_single(sf),
            "n_pl": budget.n_pl(delta, deff=lv["deff"], s_dec=s_dec, p=p),
            "floor_upper": budget.floor_upper(per_fold, deff=lv["deff"], s_dec=s_dec, p=p),
            "joint_feasible_2": budget.joint_feasible(sf, delta, 2),
            "m": m, "r_bar": r_bar, "r_bar_source": r_bar_source}
