# -*- coding: utf-8 -*-
"""edge_core 优势检查估计量与分辨力单测(显式路径跑):uv run pytest .claude/skills/tune-gates/test_edge_core.py -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import budget  # noqa: E402
from edge_core import (_layer_keys, _prepare, edge_by_year, edge_delta, edge_source_note,  # noqa: E402
                       edge_verdict, resolution)


# ── 合成数据与直白版 ──

def _synth(seed, start="2024-03-01", n_base_sym=150, n_pat_sym=20, n_days=12, n_pat=400):
    """合成两侧行。

    基线:每股每个交易日约 9 成出现一行,四态 one-hot,约 3% 的 M 缺失。
    pattern:从 pattern 股的基线股日里抽,一半沿用同股同日的基线 M(与切点、基线值打平手),一半重抽 M;
    计数为买点事件级 0~2;另加若干落在基线最后一天之后约 30 个交易日的行(任何时间单元都没有基线,层 −1)。日期用字符串。
    """
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, periods=n_days + 33)
    syms = np.array([f"S{i:03d}" for i in range(n_base_sym)])
    si, di = (a.ravel() for a in np.meshgrid(np.arange(n_base_sym), np.arange(n_days), indexing="ij"))
    keep = rng.random(len(si)) < 0.9
    si, di = si[keep], di[keep]
    n = len(si)
    M = rng.lognormal(-3, 0.5, n)
    M[rng.random(n) < 0.03] = np.nan
    state = rng.choice(4, size=n, p=[0.3, 0.3, 0.1, 0.3])
    base = pd.DataFrame({"symbol": syms[si], "date": days[di], "M": M,
                         "up": (state == 0).astype(int), "down": (state == 1).astype(int),
                         "both": (state == 2).astype(int)})

    pool = np.flatnonzero(si < n_pat_sym)
    pick = rng.choice(pool, n_pat)
    pM = M[pick].copy()
    fresh = rng.random(n_pat) < 0.5
    pM[fresh] = rng.lognormal(-3, 0.5, fresh.sum())
    n_off = 12
    pattern = pd.DataFrame({
        "symbol": np.concatenate([syms[si[pick]], rng.choice(syms[:n_pat_sym], n_off)]),
        "date": np.concatenate([days[di[pick]], days[n_days + 30 + rng.integers(0, 3, n_off)]]).astype("datetime64[D]").astype(str),
        "M": np.concatenate([pM, rng.lognormal(-3, 0.5, n_off)]),
        "up": rng.integers(0, 3, n_pat + n_off), "down": rng.integers(0, 3, n_pat + n_off),
        "both": rng.integers(0, 2, n_pat + n_off)})
    return pattern, base


def _direct(pattern, base, *, time_key, cut, min_dir, win_days=None):
    """按优势检查第 1~6 步逐步写的 pandas 直白版点估计(对照用)。"""
    p = pattern[pattern["M"].notna()].copy()
    b = base[base["M"].notna()].copy()
    for x in (p, b):
        x["date"] = pd.to_datetime(x["date"])
        x["dec"] = x["up"] + x["down"] + x["both"]
    if time_key == "day":
        p["unit"], b["unit"] = p["date"], b["date"]
    else:
        t0 = b["date"].min()
        p["unit"] = (p["date"] - t0).dt.days // win_days
        b["unit"] = (b["date"] - t0).dt.days // win_days
    if cut == "per":
        qq = b.groupby("unit")["M"].quantile([1 / 3, 2 / 3]).unstack()
        qq.columns = ["q1", "q2"]
    else:
        g1, g2 = b["M"].quantile([1 / 3, 2 / 3])
        qq = pd.DataFrame({"q1": g1, "q2": g2}, index=pd.Index(b["unit"].unique(), name="unit"))
    for x in (p, b):
        j = x[["unit"]].join(qq, on="unit")
        x["layer"] = (x["M"] > j["q1"]).astype(int) + (x["M"] > j["q2"]).astype(int)
        x.loc[j["q1"].isna(), "layer"] = -1
    keys = ["unit", "layer"]
    b_all = b.groupby(keys)[["up", "dec"]].sum()
    ok = b_all.index[b_all["dec"] >= min_dir]
    p_in = p[pd.MultiIndex.from_frame(p[keys]).isin(ok)]
    b_in = b[pd.MultiIndex.from_frame(b[keys]).isin(ok)]
    pk = p_in.groupby(keys)[["up", "dec"]].sum()
    bk = b_in.groupby(keys)[["up", "dec"]].sum()
    j = pk.join(bk, rsuffix="_b").fillna(0)
    jm = j[j["dec_b"] > 0]
    pattern_rate = pk["up"].sum() / pk["dec"].sum()
    base_rate = (jm["dec"] / jm["dec"].sum() * jm["up_b"] / jm["dec_b"]).sum()
    return {"est": pattern_rate - base_rate, "pattern_rate": pattern_rate, "matched_base_rate": base_rate,
            "coverage": p_in["dec"].sum() / p["dec"].sum(), "n_layers": len(ok),
            "n_pattern_dir": int(p_in["dec"].sum()), "n_base_dir": int(b_in["dec"].sum()),
            "n_pattern_symbols": p_in["symbol"].nunique(), "n_base_symbols": b_in["symbol"].nunique(),
            "_n_all_layers": len(b_all), "_n_minus1": int((p["layer"] == -1).sum())}


# ── ① 点估计与直白版逐位相等 ──

@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("time_key,cut,min_dir,win_days", [
    ("day", "per", 30, None), ("day", "global", 30, None), ("win", "per", 120, 7), ("win", "global", 120, 7)])
def test_point_estimate_matches_direct(seed, time_key, cut, min_dir, win_days):
    pattern, base = _synth(seed)
    got = edge_delta(pattern, base, time_key=time_key, cut=cut, min_dir=min_dir, win_days=win_days, B=5)
    want = _direct(pattern, base, time_key=time_key, cut=cut, min_dir=min_dir, win_days=win_days)
    # 夹具自检:既有不可用层,也有层 −1 的 pattern 行
    assert 0 < want["n_layers"] < want["_n_all_layers"] and want["_n_minus1"] > 0
    for k in ("est", "pattern_rate", "matched_base_rate", "coverage"):
        assert abs(got[k] - want[k]) < 1e-12, k
    for k in ("n_layers", "n_pattern_dir", "n_base_dir", "n_pattern_symbols", "n_base_symbols"):
        assert got[k] == want[k], k


# ── ② SE 随种子确定 ──

def test_se_reproducible_by_seed():
    pattern, base = _synth(3)
    a = edge_delta(pattern, base, min_dir=30, B=60, seed=7)
    b = edge_delta(pattern, base, min_dir=30, B=60, seed=7)
    c = edge_delta(pattern, base, min_dir=30, B=60, seed=8)
    assert np.isfinite(a["se"]) and a["se"] > 0
    assert a["se"] == b["se"]
    assert c["se"] != a["se"] and c["est"] == a["est"]
    assert a["ci_lo"] == pytest.approx(a["est"] - 1.96 * a["se"], abs=1e-15)
    assert a["ci_hi"] == pytest.approx(a["est"] + 1.96 * a["se"], abs=1e-15)


# ── ③ 可用层阈值、覆盖率、层 −1、参数校验 ──

def _flat_day(day, n_dir, prefix, n_none=3):
    """同一交易日的基线行:M 全相同 → 切点 = 该值,全部落在第 0 层;定向行 up / down 交替,另加 none 行。"""
    n = n_dir + n_none
    return pd.DataFrame({"symbol": [f"{prefix}{i}" for i in range(n)], "date": day, "M": 0.05,
                         "up": [int(i < n_dir and i % 2 == 0) for i in range(n)],
                         "down": [int(i < n_dir and i % 2 == 1) for i in range(n)], "both": 0})


def _pattern(day_counts):
    """pattern 行:每项 (日期, up, down, both),股票逐行不同,M 与基线相同。"""
    return pd.DataFrame([{"symbol": f"P{i}", "date": d, "M": 0.05, "up": u, "down": dn, "both": bt}
                         for i, (d, u, dn, bt) in enumerate(day_counts)])


@pytest.mark.parametrize("cut", ["per", "global"])
def test_usable_layer_threshold(cut):
    """基线定向计数恰为 min_dir − 1 → 不可用;恰为 min_dir → 可用。"""
    k = 7
    day = "2024-05-02"
    pattern = _pattern([(day, 2, 1, 0), (day, 1, 2, 1)])
    below = edge_delta(pattern, _flat_day(day, k - 1, "B"), cut=cut, min_dir=k, B=20)
    at = edge_delta(pattern, _flat_day(day, k, "B"), cut=cut, min_dir=k, B=20)
    assert below["n_layers"] == 0 and below["coverage"] == 0.0 and np.isnan(below["est"])
    assert at["n_layers"] == 1 and at["coverage"] == 1.0
    # pattern 率 = 3/7;基线 7 个定向日里 up 4 个
    assert at["pattern_rate"] == pytest.approx(3 / 7)
    assert at["matched_base_rate"] == pytest.approx(4 / 7)
    assert at["est"] == pytest.approx(-1 / 7)


def test_coverage():
    """覆盖率 = 可用层内 pattern 定向计数 / 全部 pattern 定向计数;不可用层的 pattern 行不进估计。"""
    day_a, day_b = "2024-05-02", "2024-05-03"
    base = pd.concat([_flat_day(day_a, 10, "A"), _flat_day(day_b, 3, "B")], ignore_index=True)
    pattern = _pattern([(day_a, 2, 1, 0), (day_b, 1, 0, 0), (day_a, 0, 0, 0)])
    res = edge_delta(pattern, base, min_dir=5, B=20)
    assert res["n_layers"] == 1
    assert res["coverage"] == pytest.approx(0.75)
    assert res["pattern_rate"] == pytest.approx(2 / 3)
    assert res["n_pattern_dir"] == 3 and res["n_pattern_symbols"] == 2


@pytest.mark.parametrize("time_key,win_days", [("day", None), ("win", 7)])
@pytest.mark.parametrize("cut", ["per", "global"])
def test_pattern_row_without_base_unit_is_minus1(time_key, cut, win_days):
    """pattern 行所在时间单元没有基线行 → 层 −1:不进覆盖率分子,不影响估计。"""
    day_a, far = "2024-05-02", "2024-06-20"
    base = _flat_day(day_a, 10, "A")
    inside = _pattern([(day_a, 2, 1, 0)])
    both = _pattern([(day_a, 2, 1, 0), (far, 4, 1, 0)])
    kw = dict(time_key=time_key, cut=cut, win_days=win_days)
    p_key, b_key, _ = _layer_keys(_prepare(both, "p"), _prepare(base, "b"), **kw)
    assert p_key.tolist()[1] == -1 and p_key.tolist()[0] >= 0 and (b_key >= 0).all()
    with_far = edge_delta(both, base, min_dir=5, B=20, **kw)
    only_in = edge_delta(inside, base, min_dir=5, B=20, **kw)
    assert with_far["coverage"] == pytest.approx(3 / 8)
    assert with_far["est"] == only_in["est"]


def test_argument_checks():
    pattern, base = _synth(0)
    with pytest.raises(ValueError, match="win_days"):
        edge_delta(pattern, base, time_key="win")
    with pytest.raises(ValueError):
        edge_delta(pattern, base, time_key="week")
    with pytest.raises(ValueError):
        edge_delta(pattern, base, cut="both")
    with pytest.raises(ValueError, match="缺列"):
        edge_delta(pattern.drop(columns="M"), base)


def test_empty_sides_give_nan():
    pattern, base = _synth(0)
    assert np.isnan(edge_delta(pattern, base.iloc[:0], B=10)["est"])
    res = edge_delta(pattern.iloc[:0], base, B=10)
    assert np.isnan(res["est"]) and np.isnan(res["se"]) and np.isnan(res["coverage"])


def test_drops_missing_M_rows():
    """M 缺失行在两侧都丢掉,不管它们的计数是多少。"""
    pattern, base = _synth(4)
    noisy_p = pd.concat([pattern, pattern.assign(M=np.nan, up=9)], ignore_index=True)
    noisy_b = pd.concat([base, base.assign(M=np.nan, up=1, down=0, both=0)], ignore_index=True)
    a = edge_delta(pattern, base, min_dir=30, B=10)
    b = edge_delta(noisy_p, noisy_b, min_dir=30, B=10)
    assert a["est"] == b["est"] and a["coverage"] == b["coverage"]


def test_edge_by_year():
    pattern, base = _synth(5, start="2024-12-20")
    kw = dict(min_dir=30, B=10, seed=1)
    res = edge_by_year(pattern, base, **kw)
    assert list(res) == ["2024", "2025", "pooled"]
    p_year = pd.to_datetime(pattern["date"]).dt.year
    b_year = pd.to_datetime(base["date"]).dt.year
    for y in (2024, 2025):
        assert res[str(y)] == edge_delta(pattern[p_year == y], base[b_year == y], **kw)
    assert res["pooled"] == edge_delta(pattern, base, **kw)


# ── ④ 判读、来源提示、分辨力 ──

@pytest.mark.parametrize("ci,verdict", [
    ((0.001, 0.05), "有边际"), ((-0.01, 0.015), "没有"), ((-0.01, 0.03), "未证实"),
    ((float("nan"), float("nan")), "未证实")])
def test_edge_verdict(ci, verdict):
    assert edge_verdict({"ci_lo": ci[0], "ci_hi": ci[1]}, 0.02) == verdict


def test_edge_source_note():
    assert edge_source_note({"2024": "未证实", "2025": "有边际"},
                            {"2024": "有边际", "2025": "有边际"}) == "优势来自在役闸"
    assert edge_source_note({"2024": "没有"}, {"2024": "有边际"}) == "优势来自在役闸"
    assert edge_source_note({"2024": "有边际", "2025": "有边际"}, {"2024": "有边际", "2025": "未证实"}) is None
    assert edge_source_note({"2024": "没有"}, {"2024": "未证实"}) is None
    assert edge_source_note({"2024": "未证实"}, {"2025": "有边际"}) is None


RES_KEYS = {"se_level", "deff", "s_dec", "n_dir", "n_bars", "n_bars_per_fold", "se_flip", "x_screen", "x_single", "n_pl",
            "floor_upper", "joint_feasible_2", "m", "r_bar", "r_bar_source"}


@pytest.mark.parametrize("delta", [0.02, 0.2])
def test_resolution_matches_hand_calc(delta):
    U, D, N = np.array([30., 12., 3.]), np.array([60., 20., 14.]), np.array([90., 41., 20.])
    m, q, r_bar, p = 10, 0.10, 0.9, 0.5
    res = resolution(U, D, N, delta=delta, m=m, q=q, r_bar=r_bar, r_bar_source="实测", n_folds=1, p=p)
    r = U.sum() / D.sum()
    E = (U - r * D) / D.sum()
    se = np.sqrt(3 / 2 * (E ** 2).sum())
    deff = (se / np.sqrt(r * (1 - r) / D.sum())) ** 2
    s_dec = D.sum() / N.sum()
    sf = se * np.sqrt((1 - r_bar) / r_bar)
    want = {"se_level": se, "deff": deff, "s_dec": s_dec, "se_flip": sf,
            "x_screen": (stats.norm.ppf(1 - q / (2 * m)) + 0.84) * sf, "x_single": 2.8 * sf,
            "n_pl": 1.96 * p * (1 - p) * deff / (1.2 * s_dec * delta ** 2),
            "floor_upper": 1.4 * np.sqrt(p * (1 - p) * deff / (1.2 * N.sum() * s_dec))}
    assert set(res) == RES_KEYS
    for k, v in want.items():
        assert res[k] == pytest.approx(v, rel=1e-12), k
    assert (res["n_dir"], res["n_bars"], res["n_bars_per_fold"]) == (94, 151, 151)
    assert res["joint_feasible_2"] is bool(2.8 * 1.7 * sf <= delta)
    assert (res["m"], res["r_bar"], res["r_bar_source"]) == (m, r_bar, "实测")


def test_resolution_joint_feasible_both_ways():
    U, D, N = np.array([30., 12., 3.]), np.array([60., 20., 14.]), np.array([90., 41., 20.])
    kw = dict(m=10, q=0.10, r_bar=0.9, r_bar_source="实测", n_folds=2)
    assert resolution(U, D, N, delta=0.02, **kw)["joint_feasible_2"] is False
    assert resolution(U, D, N, delta=0.2, **kw)["joint_feasible_2"] is True


def test_resolution_bb_v1_calibration():
    """bb_v1 标定例(只作计算器数值核对,与 budget 对应量一致):两只股构造出 SE_level = 3.01 点,
    检测参数 r̄ 取先验 0.85、筛选族大小 36、q 0.10。"""
    res = resolution([5301, 4699], [10000, 10000], [16000, 16000], delta=0.02, m=36, q=0.10,
                     r_bar=budget.R_BAR_DETECT_PRIOR, r_bar_source="标定先验", n_folds=2)
    assert res["se_level"] == pytest.approx(0.0301, rel=1e-12)
    sf = budget.se_flip(0.0301, 0.85)
    assert res["se_flip"] == pytest.approx(sf, rel=1e-12)
    assert res["x_screen"] == pytest.approx(budget.x_screen(sf, 36, 0.10), rel=1e-12)
    assert res["x_single"] == pytest.approx(budget.x_single(sf), rel=1e-12)
    assert round(res["se_flip"] * 100, 2) == 1.26
    assert round(res["x_screen"] * 100, 1) == 4.8
    assert round(res["x_single"] * 100, 1) == 3.5


def test_resolution_floor_is_per_fold():
    """n_folds=2 时地板 = 用一半 bar 数算的值(= 合并口径的 √2 倍);功效线与折数无关。"""
    U, D, N = np.array([30., 12., 3.]), np.array([60., 20., 14.]), np.array([90., 41., 20.])
    kw = dict(delta=0.02, m=10, q=0.10, r_bar=0.9, r_bar_source="实测")
    one = resolution(U, D, N, n_folds=1, **kw)
    two = resolution(U, D, N, n_folds=2, **kw)
    assert two["n_bars_per_fold"] == N.sum() / 2 and two["n_bars"] == 151
    assert two["floor_upper"] == pytest.approx(
        1.4 * np.sqrt(0.25 * two["deff"] / (1.2 * (N.sum() / 2) * two["s_dec"])), rel=1e-12)
    assert two["floor_upper"] == pytest.approx(
        budget.floor_upper(N.sum() / 2, deff=two["deff"], s_dec=two["s_dec"]), rel=1e-12)
    assert two["floor_upper"] == pytest.approx(one["floor_upper"] * np.sqrt(2), rel=1e-12)
    assert two["n_pl"] == one["n_pl"]


def test_resolution_argument_checks():
    kw = dict(delta=0.02, m=4, q=0.10, r_bar=0.85)
    with pytest.raises(ValueError):
        resolution([1, 2], [2, 3], [4, 5], r_bar_source="默认", n_folds=2, **kw)
    with pytest.raises(ValueError):
        resolution([1, 2], [2, 3], [4, 5], r_bar_source="实测", n_folds=0, **kw)
    with pytest.raises(TypeError):
        resolution([1, 2], [2, 3], [4, 5], r_bar_source="实测", **kw)
