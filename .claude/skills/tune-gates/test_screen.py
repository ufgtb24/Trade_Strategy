# -*- coding: utf-8 -*-
"""筛选核单测(合成数据):uv run pytest .claude/skills/tune-gates/test_screen.py -q"""
import itertools
import re
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import edge_core  # noqa: E402
from inference import bh, cochran_q, level_se, ratio_contrast, time_window_codes, time_window_days  # noqa: E402
from region_core import STATES, prepare, prepare_shards, segment_tensor, stock_sums, tensor  # noqa: E402
import screen  # noqa: E402
from screen import (ScreenSpec, draft_fc_rows, gate_outcome, pool_drift, render_report,  # noqa: E402
                    screen_core, segments_changed)

COMBO = {"d1": [1, 2, 3], "d2": [10, 20]}
PREDS = [("g1", ">=", [0, 1, 2]), ("g2", "<", [None, 0.5])]
YEARS = ["2024", "2025"]
SEG = ["e.start", "e.end"]
TRAIN_START = "2024-01-01"
HORIZON = 20
WORKING = {"d1": 2, "d2": 10, "g1": 1, "g2": 0.5}
WIDE = {"d1": 2, "d2": 10, "g1": 0, "g2": None}
SPEC = ScreenSpec(working=WORKING, wide=WIDE, d_flips={"d1": [1, 3], "d2": [20]}, gate_offs={"g1": 0, "g2": None})


def _table(p_up, *, S=300, n_ev=24, seed=0):
    """合成长表:S 只股 × 6 个检测组合 × n_ev 个买点事件,一行一个买点事件。

    p_up(d1, d2, g1, g2, year, win) → 每行 up 概率(逐行数组);10% 的行为 none,其余非 up 即 down。
    """
    rng = np.random.default_rng(seed)
    combos = list(itertools.product(COMBO["d1"], COMBO["d2"]))
    n = S * len(combos) * n_ev
    sym = np.repeat(np.arange(S), len(combos) * n_ev)
    d1 = np.tile(np.repeat([c[0] for c in combos], n_ev), S)
    d2 = np.tile(np.repeat([c[1] for c in combos], n_ev), S)
    ev = np.tile(np.arange(n_ev), S * len(combos))
    day = rng.integers(0, 731, n)
    date = pd.Timestamp(TRAIN_START) + pd.to_timedelta(day, "D")
    year = np.asarray(date.year)
    win = day // time_window_days(HORIZON)
    g1 = rng.integers(0, 3, n)
    g2 = rng.random(n)
    p = np.clip(p_up(d1, d2, g1, g2, year, win), 0, 1)
    none = rng.random(n) < 0.1
    up = ~none & (rng.random(n) < p)
    return pd.DataFrame({"symbol": [f"S{i:03d}" for i in sym], "d1": d1, "d2": d2, "g1": g1, "g2": g2,
                         "fold": year.astype(str), "buy_date": date, "e.start": ev, "e.end": ev + 3,
                         "fp_up": up.astype(int), "fp_down": (~none & ~up).astype(int), "fp_both": 0,
                         "fp_none": none.astype(int)})


def _preps(df):
    codes, levels = time_window_codes(df["buy_date"], TRAIN_START, time_window_days(HORIZON))
    py = prepare(df, COMBO, PREDS, "fold", YEARS, segment_cols=SEG)
    pw = prepare(df.assign(win=codes), COMBO, PREDS, "win", levels, segment_cols=SEG)
    return py, pw


def _main_p(d1, d2, g1, g2, year, win):
    # d1=3 有主效应;d1=3 与 d2=20 有交互;g2 ≥ 0.5 的买点更差(g2 这道闸有用);g1 无关
    return 0.45 + 0.2 * (d1 == 3) + 0.25 * ((d1 == 3) & (d2 == 20)) - 0.25 * (g2 >= 0.5)


def _hetero_p(d1, d2, g1, g2, year, win):
    # d1=3 两年反号;d2=20 在相邻时间窗之间反号
    return 0.5 + 0.25 * (d1 == 3) * np.where(year == 2024, 1, -1) + 0.3 * (d2 == 20) * np.where(win % 2 == 0, 1, -1)


@pytest.fixture(scope="module")
def main_df():
    return _table(_main_p)


@pytest.fixture(scope="module")
def main_res(main_df):
    py, pw = _preps(main_df)
    return screen_core(py, pw, SPEC, years=YEARS, q=0.10, delta=0.05, B=60, seed=3)


@pytest.fixture(scope="module")
def hetero():
    df = _table(_hetero_p, seed=1)
    py, pw = _preps(df)
    return df, screen_core(py, pw, SPEC, years=YEARS, q=0.10, delta=0.05, B=20, seed=0)


def _row(res, base, axis, level):
    df = res["contrasts"]
    hit = df[(df["base"] == base) & (df["axis"] == axis) & df["level"].map(lambda v: v == level)]
    assert len(hit) == 1
    return hit.iloc[0]


def _sums(df, levels, extra=None):
    """直白版每股和:行过滤 → 按股求和(合成表一行一个买点事件,无需去重)。返回 (U, D, N),股按名排序。"""
    m = np.ones(len(df), bool)
    for c in COMBO:
        m &= df[c].to_numpy() == levels[c]
    for c, op, _ in PREDS:
        if levels[c] is not None:
            m &= (df[c].to_numpy() >= levels[c]) if op == ">=" else (df[c].to_numpy() < levels[c])
    if extra is not None:
        m &= extra
    g = df[m].groupby("symbol")[STATES].sum().reindex(sorted(df["symbol"].unique()), fill_value=0)
    U = g["fp_up"].to_numpy()
    D = U + g["fp_down"].to_numpy() + g["fp_both"].to_numpy()
    return U, D, D + g["fp_none"].to_numpy()


def _brute(df, cells, coef, extra=None):
    S = [_sums(df, c, extra) for c in cells]
    return ratio_contrast(*(np.column_stack([s[i] for s in S]) for i in range(3)), coef)


# ── 对比族与估计 ──

def test_family_size_and_probe_count(main_res):
    df = main_res["contrasts"]
    assert main_res["settings"]["m"] == len(df) == 2 * (3 + 2)
    assert list(df["base"].value_counts().sort_index()) == [5, 5]
    assert set(df.loc[df["kind"] == "gate_off", "axis"]) == {"g1", "g2"}
    assert len(main_res["probes"]) == 9 == main_res["settings"]["n_probes"]   # 5 个单处改动两两组合,去掉同轴的一对


@pytest.mark.parametrize("base,axis,level,x,y", [
    ("working", "d1", 3, {**WORKING, "d1": 3}, WORKING),
    ("working", "g1", 0, {**WORKING, "g1": 0}, WORKING),
    ("wide", "g2", None, WIDE, {**WIDE, "g2": 0.5}),            # 宽进点上也是「关 − 开」
    ("wide", "d2", 20, {**WIDE, "d2": 20}, WIDE),
])
def test_contrast_matches_brute_force(main_df, main_res, base, axis, level, x, y):
    r = _row(main_res, base, axis, level)
    ref = _brute(main_df, [x, y], [1, -1])
    assert r["est"] == pytest.approx(ref["est"], abs=1e-12) and r["se"] == pytest.approx(ref["se"], abs=1e-12)
    assert r["p"] == pytest.approx(2 * stats.norm.sf(abs(ref["z"])), abs=1e-12)
    for yr in YEARS:
        ry = _brute(main_df, [x, y], [1, -1], extra=(main_df["fold"] == yr).to_numpy())
        assert r[f"est_{yr}"] == pytest.approx(ry["est"], abs=1e-12)
        assert r[f"se_{yr}"] == pytest.approx(ry["se"], abs=1e-12)
    nx, ny = _sums(main_df, x)[2].sum(), _sums(main_df, y)[2].sum()
    assert r["keep_ratio"] == pytest.approx(nx / ny)


def test_bh_survival(main_res):
    df = main_res["contrasts"]
    assert np.allclose(df["q_bh"], bh(df["p"].to_numpy()))
    assert (df["survive"] == (df["q_bh"] <= 0.10)).all()
    assert _row(main_res, "working", "d1", 3)["survive"] and _row(main_res, "wide", "d1", 3)["survive"]
    assert not _row(main_res, "working", "d2", 20)["survive"]


def test_level(main_df, main_res):
    ref = level_se(*_sums(main_df, WORKING))
    lv = main_res["level"]
    assert lv["se_level"] == pytest.approx(ref["se"]) and lv["deff"] == pytest.approx(ref["deff"])
    assert lv["n_dir"] == ref["n_dir"] and lv["n_bars"] == _sums(main_df, WORKING)[2].sum()


def test_difference_in_differences(main_df, main_res):
    df = main_res["contrasts"]
    for _, r in df[df["base"] == "working"].iterrows():
        w = _row(main_res, "wide", r["axis"], r["level"])
        assert r["did_est"] == pytest.approx(r["est"] - w["est"], abs=1e-12)
    assert df.loc[df["base"] == "wide", ["did_est", "did_se", "did_z"]].isna().all().all()
    ref = _brute(main_df, [{**WORKING, "d1": 3}, WORKING, {**WIDE, "d1": 3}, WIDE], [1, -1, -1, 1])
    r = _row(main_res, "working", "d1", 3)
    assert (r["did_est"], r["did_se"]) == (pytest.approx(ref["est"]), pytest.approx(ref["se"]))


def test_year_interaction_and_time_flags(hetero):
    df, res = hetero
    r = _row(res, "working", "d1", 3)
    assert r["flag_year"] and abs(r["z_int"]) > 2
    assert r["z_int"] == pytest.approx((r["est_2025"] - r["est_2024"]) / np.hypot(r["se_2024"], r["se_2025"]))
    t = _row(res, "working", "d2", 20)
    assert t["flag_time"] and t["cochran_p"] < 0.05
    # Cochran Q 与逐窗直白版一致
    win = df["buy_date"].sub(pd.Timestamp(TRAIN_START)).dt.days.to_numpy() // time_window_days(HORIZON)
    ests, ses = [], []
    for w in range(win.min(), win.max() + 1):
        c = _brute(df, [{**WORKING, "d2": 20}, WORKING], [1, -1], extra=win == w)
        ests.append(c["est"]); ses.append(c["se"])
    assert t["cochran_p"] == pytest.approx(cochran_q(ests, ses)["p"])


# ── 删闸非劣效 ──

def test_noninferiority_three_outcomes(main_res):
    g1, g2 = _row(main_res, "working", "g1", 0), _row(main_res, "working", "g2", None)
    for r in (g1, g2):
        assert r["ni_lower"] == pytest.approx(r["est"] - 1.645 * r["se"])
        assert r["ni_pass"] == (r["ni_lower"] >= -0.05)
    assert gate_outcome(g1) == "删了不亏"                         # g1 与结果无关
    assert gate_outcome(g2) == "有用"                             # 关掉 g2 放进更差的买点
    d = _row(main_res, "working", "d1", 3)
    assert np.isnan(d["ni_lower"]) and not d["ni_pass"]
    small = _table(lambda d1, d2, g1, g2, year, win: 0.5 - 0.15 * (g1 == 0), S=40, n_ev=4, seed=2)
    res = screen_core(*_preps(small), SPEC, years=YEARS, q=0.10, delta=0.02, B=5, seed=0)
    h = _row(res, "working", "g1", 0)
    assert not h["ni_pass"] and not h["survive"]
    assert gate_outcome(h) == "说不清"


# ── 探针与交互兜底 ──

def test_probe_and_interaction_fallback(main_df, main_res):
    pr = main_res["probes"]
    hit = pr[(pr["axis_a"] == "d1") & (pr["level_a"] == 3) & (pr["axis_b"] == "d2")]
    assert len(hit) == 1
    ref = _brute(main_df, [{**WORKING, "d1": 3, "d2": 20}, {**WORKING, "d1": 3}, {**WORKING, "d2": 20}, WORKING],
                 [1, -1, -1, 1])
    assert hit.iloc[0]["est"] == pytest.approx(ref["est"]) and hit.iloc[0]["se"] == pytest.approx(ref["se"])
    assert abs(hit.iloc[0]["z"]) >= 2
    joint = main_res["joint_axes"]
    assert joint[:2] == ["d1", "g2"]                             # 工作点幸存轴,按族顺序
    assert "d2" in joint                                          # d2 自身不幸存,靠与 d1 的交互带入
    py, pw = _preps(main_df)
    no = screen_core(py, pw, SPEC, years=YEARS, q=0.10, delta=0.05, B=5, seed=0, pair_probes=False)
    assert no["joint_axes"] == ["d1", "g2"] and no["probes"].empty


# ── 稳定性 ──

def test_boot_stats_equals_ratio_contrast(main_df):
    cells = [{**WORKING, "d1": 3}, WORKING, {**WORKING, "g1": 0}]
    S = [_sums(main_df, c) for c in cells]
    U, D, N = (np.column_stack([s[i] for s in S]) for i in range(3))
    C = np.array([[1.0, -1.0, 0.0], [0.0, -1.0, 1.0]])
    keep = np.arange(U.shape[0]) % 3 != 0
    est, se = screen._boot_stats(U, D, N, C, np.vstack([np.ones(U.shape[0]), keep.astype(float)]))
    for j, row in enumerate(C):
        full = ratio_contrast(U, D, N, row)
        sub = ratio_contrast(U[keep], D[keep], N[keep], row)
        assert (est[0, j], se[0, j]) == (pytest.approx(full["est"]), pytest.approx(full["se"]))
        assert (est[1, j], se[1, j]) == (pytest.approx(sub["est"]), pytest.approx(sub["se"]))


def test_stability_reproducible(main_df, main_res):
    py, pw = _preps(main_df)
    again = screen_core(py, pw, SPEC, years=YEARS, q=0.10, delta=0.05, B=60, seed=3)
    assert again["stability"] == main_res["stability"]
    st = main_res["stability"]
    assert st["B"] == 60 and set(st["inclusion_freq"]) == {"d1", "d2", "g1", "g2"}
    assert st["inclusion_freq"]["d1"] >= 0.9 and 0 <= st["set_repro"] <= 1


# ── 校验 ──

@pytest.mark.parametrize("spec,msg", [
    (ScreenSpec(WORKING, WIDE, {"g1": [2]}, {}), "不是检测参数轴"),
    (ScreenSpec(WORKING, WIDE, {"d1": [2]}, {}), "含工作点现值"),
    (ScreenSpec(WORKING, WIDE, {}, {"g1": 1}), "不是在役闸"),
    (ScreenSpec(WORKING, {**WIDE, "d2": 20}, {}, {"g1": 0}), "应同工作点"),
])
def test_spec_validation(main_df, spec, msg):
    py, pw = _preps(main_df.head(3000))
    with pytest.raises(ValueError, match=msg):
        screen_core(py, pw, spec, years=YEARS, q=0.10, delta=0.05, B=1)


def test_years_must_be_folds(main_df):
    py, pw = _preps(main_df.head(3000))
    with pytest.raises(ValueError, match="years"):
        screen_core(py, pw, SPEC, years=["2023"], q=0.10, delta=0.05, B=1)


# ── region_core.prepare_shards 的派生折 ──

def test_prepare_shards_fold_from(tmp_path, main_df):
    wd = time_window_days(HORIZON)
    codes, levels = time_window_codes(main_df["buy_date"], TRAIN_START, wd)
    syms = sorted(main_df["symbol"].unique())
    shards = []
    for i, part in enumerate((syms[: len(syms) // 2], syms[len(syms) // 2:])):
        p = tmp_path / f"part-{i:04d}.parquet"
        main_df[main_df["symbol"].isin(part)].drop(columns=["fold"]).to_parquet(p, index=False)
        shards.append(p)
    fn = lambda s: pd.Series(time_window_codes(s, TRAIN_START, wd)[0], index=s.index)  # noqa: E731
    sh = prepare_shards(shards, COMBO, PREDS, "fold", levels, segment_cols=SEG, fold_from=("buy_date", fn))
    whole = prepare(main_df.assign(win=codes), COMBO, PREDS, "win", levels, segment_cols=SEG)
    assert np.array_equal(tensor(sh), tensor(whole)) and np.array_equal(segment_tensor(sh), segment_tensor(whole))
    cells = [(1, 0, 1, 1), (2, 1, 0, 0)]
    assert all(np.array_equal(a, b) for a, b in zip(stock_sums(sh, cells), stock_sums(whole, cells)))
    with pytest.raises(ValueError, match="fold_from"):
        prepare_shards(shards, COMBO, PREDS, "fold", levels, segment_cols=SEG,
                       fold_from=("buy_date", lambda s: s.iloc[:-1].astype(str)))


# ── 买点事件集合差 ──

def test_segments_changed_matches_brute_force(tmp_path, main_df):
    df = main_df[main_df["symbol"] < "S040"].copy()
    dup = df.sample(frac=0.3, random_state=0).assign(g1=lambda d: (d["g1"] + 1) % 3)   # 同一买点事件的另一行
    df = pd.concat([df, dup], ignore_index=True)
    syms = sorted(df["symbol"].unique())
    shards = []
    for i, part in enumerate((syms[:20], syms[20:])):
        p = tmp_path / f"part-{i:04d}.parquet"
        df[df["symbol"].isin(part)].to_parquet(p, index=False)
        shards.append(p)

    def members(levels):
        m = np.ones(len(df), bool)
        for c in COMBO:
            m &= df[c].to_numpy() == levels[c]
        for c, op, _ in PREDS:
            if levels[c] is not None:
                m &= (df[c].to_numpy() >= levels[c]) if op == ">=" else (df[c].to_numpy() < levels[c])
        return set(map(tuple, df.loc[m, ["symbol", "fold"] + SEG].astype(str).to_numpy()))

    for a, b in [(WORKING, {**WORKING, "d1": 3}), (WORKING, {**WORKING, "g1": 2})]:
        got = segments_changed(shards, SEG, a, b, COMBO, PREDS, "fold", YEARS)
        A, Bs = members(a), members(b)
        for y in YEARS:
            assert got["dropped"][y] == sum(1 for k in A - Bs if k[1] == y)
            assert got["added"][y] == sum(1 for k in Bs - A if k[1] == y)
    assert sum(got["added"].values()) == 0 and sum(got["dropped"].values()) > 0    # 收紧闸只会掉出


# ── 换池漂移 ──

def test_pool_drift(monkeypatch):
    calls = []

    def edge_delta(rows, base, **kw):
        calls.append(kw)
        return {"est": 0.0, "matched_base_rate": float(rows["M"].mean())}

    monkeypatch.setattr(screen, "edge_core", types.SimpleNamespace(edge_delta=edge_delta))
    cols = dict(symbol=["A", "B"], date=pd.to_datetime(["2024-01-02"] * 2), up=[1, 0], down=[0, 1], both=[0, 0])
    a, b = pd.DataFrame({**cols, "M": [0.05, 0.05]}), pd.DataFrame({**cols, "M": [0.02, 0.02]})
    base = pd.DataFrame({**cols, "M": [0.03, 0.03]})
    out = pool_drift(a, b, base, delta=0.05, time_key="day", B=7)
    assert out["available"] and out["drift"] == pytest.approx(0.03) and out["flag"]
    assert calls == [{"time_key": "day", "B": 7}] * 2
    assert not pool_drift(a, b, base, delta=0.08)["flag"]
    assert pool_drift(a.drop(columns="M"), b, base, delta=0.05) == {"available": False}


def test_pool_drift_with_edge_core():
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2024-01-02", periods=5)
    st = rng.integers(0, 3, 300)
    base = pd.DataFrame({"symbol": np.repeat([f"B{i:02d}" for i in range(60)], 5), "date": np.tile(days, 60),
                         "M": rng.random(300), "up": (st == 0).astype(int), "down": (st == 1).astype(int), "both": 0})
    arm = lambda k: base.sample(120, random_state=k).assign(symbol=lambda d: "P" + d["symbol"])  # noqa: E731
    a, b = arm(1), arm(2)
    out = pool_drift(a, b, base, delta=0.02, B=5, min_dir=5)
    ea, eb = (edge_core.edge_delta(x, base, B=5, min_dir=5) for x in (a, b))
    assert out["drift"] == pytest.approx(ea["matched_base_rate"] - eb["matched_base_rate"])
    assert out["flag"] == (abs(out["drift"]) >= 0.01)


# ── 报告 ──

FORBIDDEN = re.compile(r"BH|(?<![A-Za-z_])z(?![A-Za-z_])|底座|seg|回踩|working|wide|bootstrap|Cochran|差中差|非劣效|设计效应")


def test_render_report_business_language(main_res):
    text = render_report(main_res, app="demo", window="w1", delta=0.05)
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text)
    k = int(main_res["contrasts"]["survive"].sum())
    assert f"一共比了 10 个改动,{k} 个分辨得出" in text
    assert "删了不亏:关掉最坏也只差" in text and "有用:关掉明显变差" in text
    assert "`d2`(本身没分辨出来" in text


def test_render_report_flags(main_res):
    res = dict(main_res)
    df = main_res["contrasts"].copy()
    i = df.index[(df["base"] == "working") & (df["axis"] == "d1") & (df["level"] == 3)][0]
    df.loc[i, ["q_bh", "flag_year", "flag_time", "did_z"]] = [0.08, True, True, 3.0]
    df["dropped_2024"], df["added_2024"], df["dropped_2025"], df["added_2025"] = 7, 1, 9, 2
    df["drift"], df["flag_drift"] = 0.03, False
    df.loc[i, "flag_drift"] = True
    res["contrasts"] = df
    text = render_report(res, app="demo", window="w1", delta=0.05)
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text)
    for phrase in ("刚过线", "两年明显不一样", "时好时坏", "效果依赖其他闸开不开", "2024 年掉出 7 段、新增 1 段",
                   "可能换成了另一批波动或行情的股票"):
        assert phrase in text, phrase


def test_draft_fc_rows(main_res):
    text = draft_fc_rows(main_res, app="demo")
    df = main_res["contrasts"]
    w = df[df["base"] == "working"]
    n = int(((w["kind"] == "d_flip") & w["survive"]).sum() + ((w["kind"] == "gate_off") & w["ni_pass"]).sum())
    assert text.count("### FC-???") == n >= 2
    assert "demo / `d1`" in text and "demo / `g1`" in text and "demo / `g2`" not in text
    assert "回踩" not in text and "查询次数:10 个单处改动 + 9 个两两组合" in text


# ── 按权重重做挑选(联合识别的「连筛选一起重做」用) ──

def test_joint_axes_under_unit_weights_match_screen_core(main_df, main_res):
    py, _ = _preps(main_df)
    ones = np.ones((1, py.n_sym))
    assert screen.joint_axes_under_weights(py, SPEC, ones, years=YEARS, q=0.10) == [set(main_res["joint_axes"])]
    df = main_res["contrasts"]
    survived = set(df.loc[(df["base"] == "working") & df["survive"], "axis"])
    assert screen.joint_axes_under_weights(py, SPEC, ones, years=YEARS, q=0.10, pair_probes=False) == [survived]


def test_survivors_under_weights_rows_and_working_mask(main_df, main_res):
    py, _ = _preps(main_df)
    dz = screen.design_cells(SPEC, COMBO, PREDS)
    U, D, N = stock_sums(py, dz["coords"], "per_fold")
    nf = dz["n_family_cells"]
    Up, Dp, Np = (A[:, :nf, :].sum(-1) for A in (U, D, N))
    fam = dz["family"]
    ids, axes = [[f["xi"], f["yi"]] for f in fam], [f["axis"] for f in fam]
    W = np.vstack([np.ones(py.n_sym), np.zeros(py.n_sym)])
    got = screen.survivors_under_weights(Up, Dp, Np, ids, axes, W, q=0.10, working=[f["base"] == "working" for f in fam])
    df = main_res["contrasts"]
    assert got == [set(df.loc[(df["base"] == "working") & df["survive"], "axis"]), set()]
    assert screen.survivors_under_weights(Up, Dp, Np, ids, axes, W[:1], q=0.10) == [set(df.loc[df["survive"], "axis"])]


def test_draft_fc_rows_fills_known_sample_fields(main_res):
    text = draft_fc_rows(main_res, app="demo", window={"start": "2024-01-01", "end": "2026-01-01", "label_horizon": 40},
                         stock_rule="收盘价 0.5~30", report="outputs/demo/report.md")
    assert "待填" not in text
    assert "买点 2024-01-01 至 2026-01-01,标签前瞻期 40 个交易日" in text
    assert "股票规则:收盘价 0.5~30" in text and "- **发现报告**:outputs/demo/report.md" in text
