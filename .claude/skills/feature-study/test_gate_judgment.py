# -*- coding: utf-8 -*-
"""闸式判定 gate_judgment 单元测试(合成数据):
uv run pytest .claude/skills/feature-study/test_gate_judgment.py -q -p no:cacheprovider
覆盖:台阶 / U 形 / 尾部三种闸(秩相关读不出、闸式判定读得出)、闸内 Simes 与闸间 BH 的族结构(现场实测族与冻结族)、非劣效三种结局、
同一买点事件多行只计一次、「不稳」只在功效足够时判、按股簇稳健回归与手算一致。
"""
import contextlib
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import run_battery as RB  # noqa: E402

TRAIN_START = "2024-01-01"
HORIZON = 40


def _synth(effect, n_sym: int, per: int = 10, seed: int = 0, sd_sym: float = 0.3) -> pd.DataFrame:
    """合成买点事件表,一个买点事件一行。

    每股 per 个买点事件;股票层随机效应(logit 尺度 sd_sym)制造股内相关;x ~ U(0, 100) 是闸字段;
    首次穿越概率 = 0.5 加股票效应后再加 effect(x, 年);每个事件 1 + Poisson(4) 根买点 bar,85% 定向,
    非上行的定向 bar 里 10% 记 both。日期在 2024、2025 两年均匀分布;M、c0_atr_pct 与标签无关。
    """
    rng = np.random.default_rng(seed)
    n = n_sym * per
    sym = np.repeat([f"S{i:03d}" for i in range(n_sym)], per)
    re = np.repeat(rng.normal(0, sd_sym, n_sym), per)
    x = rng.uniform(0, 100, n)
    date = pd.Timestamp(TRAIN_START) + pd.to_timedelta(rng.integers(0, 730, n), "D")
    p = np.clip(1 / (1 + np.exp(-re)) + effect(x, date.year.to_numpy()), 0.02, 0.98)
    bars = 1 + rng.poisson(4, n)
    dirn = rng.binomial(bars, 0.85)
    up = rng.binomial(dirn, p)
    both = rng.binomial(dirn - up, 0.1)
    return pd.DataFrame({"symbol": sym, "date": date, "M": rng.uniform(0.01, 0.05, n),
                         "c0_atr_pct": rng.uniform(0.01, 0.06, n), "seg": np.arange(n),
                         "up": up, "down": dirn - up - both, "both": both, "none": bars - dirn, "x": x})


def _judge(df, gates, *, delta, controls=("c0_atr_pct",), pop=None, **kw):
    kw.setdefault("time_verified", True)
    return RB.gate_judgment(df, gates, population_mask=np.ones(len(df), bool) if pop is None else pop,
                            seg_cols=["seg"], controls=list(controls), delta=delta, train_start=TRAIN_START,
                            label_horizon=HORIZON, B=100, seed=0, **kw)


def _battery(df) -> dict:
    with contextlib.redirect_stdout(io.StringIO()):
        return RB.run_battery(df, ["x"], label_type="first_passage", controls=["c0_atr_pct"],
                              label_horizon=HORIZON, time_col="date")["x"]


# ── ② 三种闸:秩相关读不出、闸式判定读得出 ──

def test_step_gate():
    """台阶:x ≥ 80 的买点事件首次穿越率高 12 点。叠加一条温和的反向线性趋势,斜率取成让「x 的秩」与效应的协方差恰为 0
    (台阶项协方差 0.12 × 0.8 × 0.2 / 2 = 0.0096 = 斜率 / 12)——秩相关只读线性成分,读不出集中在阈值处的跳变。"""
    df = _synth(lambda x, yr: np.where(x >= 80, 0.12, 0.0) - 12 * 0.12 * 0.08 * (x / 100 - 0.5), 300, seed=2)
    r = _judge(df, [("x", ">=", [40, 60, 80, 90])], delta=0.05)["x"]
    assert r["verdict"] == "有信号+" and r["direction"] == "+"
    assert r["shape"] == "台阶@80"
    assert _battery(df)["verdict"] == "无信号"


def test_u_shaped_gate():
    """U 形:两端首次穿越率高、中间低,对称 → 秩相关恰为 0;闸在松档砍掉高的低端、紧档只留高的高端,曲线先降后升。"""
    df = _synth(lambda x, yr: 0.16 * ((x - 50) / 50) ** 2 - 0.16 / 3, 150, seed=0)
    r = _judge(df, [("x", ">=", [25, 50, 75, 90])], delta=0.05)["x"]
    assert r["verdict"].startswith("有信号")
    assert r["shape"] == "U 形"
    assert _battery(df)["verdict"] == "无信号"


def test_tail_gate():
    """尾部:只有 x ≥ 95 的 5% 买点事件首次穿越率高 30 点,同样叠加使秩协方差为 0 的反向趋势
    (尾部项协方差 0.30 × 0.05 × 0.475)。有效区间落在最紧的两档。"""
    df = _synth(lambda x, yr: np.where(x >= 95, 0.30, 0.0) - 12 * 0.30 * 0.05 * 0.475 * (x / 100 - 0.5), 600, seed=0)
    r = _judge(df, [("x", ">=", [50, 70, 90, 95])], delta=0.1)["x"]
    assert r["verdict"] == "有信号+"
    assert r["effective_interval"] == [90, 95]
    assert r["suggested_levels"] == [None, 90, 92, 95]
    assert _battery(df)["verdict"] == "无信号"


# ── ③ 族结构 ──

def test_simes_within_gate_bh_across_gates_underpowered_excluded():
    """闸内 Simes 合成闸级 p,闸间(连同同批其余假设)做 BH;功效预检出局的闸不进族、判「分辨不出」。"""
    df = _synth(lambda x, yr: np.where(x >= 50, 0.06, 0.0), 300, seed=4)
    rng = np.random.default_rng(0)
    df["b"] = rng.uniform(0, 1, len(df))          # 无效的闸
    df["c"] = rng.uniform(0, 1, len(df))          # 切点只留 0.5% 的买点事件:功效不够
    gates = [("x", ">=", [30, 50]), ("b", ">=", [0.3, 0.6]), ("c", ">=", [0.995])]
    res = _judge(df, gates, delta=0.03, extra_pvals={"feature:z": 0.2})

    for col in ("x", "b"):
        p = np.array([e["raw"]["p"] for e in res[col]["curve"] if e["powered"]])
        assert res[col]["stats"]["power_ok"]
        assert res[col]["stats"]["simes_p"] == pytest.approx(float(np.min(len(p) * np.sort(p) / np.arange(1, len(p) + 1))))
    c = res["c"]
    assert not c["stats"]["power_ok"] and np.isnan(c["stats"]["bh_q"])
    assert c["verdict"] == "分辨不出" and c["bucket"] == "判不了" and c["reason"] == "样本不够"
    assert c["stats"]["mde_measured"][0.995] > 0.03
    assert {r["stats"]["family_source"] for r in res.values()} == {"现场实测(未预注册)"}

    q = RB.inference.bh([res["x"]["stats"]["simes_p"], res["b"]["stats"]["simes_p"], 0.2])
    assert res["x"]["stats"]["bh_q"] == q[0] and res["b"]["stats"]["bh_q"] == q[1]
    assert {r["stats"]["family_size"] for r in res.values()} == {3}
    assert res["x"]["verdict"] == "有信号+" and res["b"]["verdict"] == "无信号"

    alone = _judge(df, gates, delta=0.03)
    assert alone["x"]["stats"]["family_size"] == 2


def test_frozen_family_overrides_measured_power():
    """同一份数据,冻结族与现场实测族不同:进族、Simes、BH、family_size 一律按冻结族;实测功效只作诊断;
    冻结族里退化的切点照常记退化、不参与合成,reason 里说明。"""
    df = _synth(lambda x, yr: np.where(x >= 50, 0.06, 0.0), 300, seed=4)
    rng = np.random.default_rng(0)
    df["b"] = rng.uniform(0, 1, len(df))
    df["c"] = rng.uniform(0, 1, len(df))
    gates = [("x", ">=", [30, 50, 101]), ("b", ">=", [0.3, 0.6]), ("c", ">=", [0.995])]
    measured = _judge(df, gates, delta=0.03)
    assert {c: r["stats"]["family_cuts"] for c, r in measured.items()} == {"x": [30, 50], "b": [0.3, 0.6], "c": []}
    assert measured["x"]["stats"]["family_size"] == 2

    family = {"x": [50, 101], "b": [0.3], "c": [0.995]}
    res = _judge(df, gates, delta=0.03, family=family)
    assert {c: r["stats"]["family_cuts"] for c, r in res.items()} == family
    assert {r["stats"]["family_source"] for r in res.values()} == {"预注册冻结"}
    assert {r["stats"]["family_size"] for r in res.values()} == {3}
    raw_p = {c: {e["cut"]: e["raw"]["p"] for e in r["curve"] if not e["degenerate"]} for c, r in res.items()}
    assert res["x"]["stats"]["simes_p"] == pytest.approx(raw_p["x"][50])
    assert res["b"]["stats"]["simes_p"] == pytest.approx(raw_p["b"][0.3])
    assert res["b"]["stats"]["simes_p"] != pytest.approx(measured["b"]["stats"]["simes_p"])
    q = RB.inference.bh([res[c]["stats"]["simes_p"] for c in ("x", "b", "c")])
    assert [res[c]["stats"]["bh_q"] for c in ("x", "b", "c")] == pytest.approx(q)

    c = res["c"]                                     # 实测功效不够,但冻结进族:照样进族判定
    assert c["stats"]["power_ok"] and not c["stats"]["power_ok_measured"] and np.isfinite(c["stats"]["bh_q"])
    assert c["stats"]["mde_measured"][0.995] > 0.03

    top = next(e for e in res["x"]["curve"] if e["cut"] == 101)
    assert top["degenerate"] and top["in_family"]
    assert "预注册进族的切点 101(全筛掉) 在这批数据上退化" in res["x"]["reason"]


def test_frozen_family_must_match_gates():
    df = _synth(lambda x, yr: 0.0, 20, seed=0)
    with pytest.raises(ValueError, match="对不上"):
        _judge(df, [("x", ">=", [30, 50])], delta=0.03, family={"y": [30]})
    with pytest.raises(ValueError, match="不在这道闸的切点"):
        _judge(df, [("x", ">=", [30, 50])], delta=0.03, family={"x": [40]})


# ── ④ 非劣效三种结局 ──

@pytest.mark.parametrize("n_sym, effect, bucket, reason", [
    (300, 0.06, "确实有用", ""),
    (1500, 0.0, "没用删了不亏", ""),
    (40, 0.0, "判不了", "样本不够"),
])
def test_noninferiority_three_outcomes(n_sym, effect, bucket, reason):
    """工作点「关 − 开」单侧 95% 下界 ≥ −δ 才算删了不亏:有效的闸 → 确实有用;无效且样本足 → 删了不亏;
    无效但样本少、下界够不着 → 判不了。"""
    df = _synth(lambda x, yr: np.where(x >= 50, effect, 0.0), n_sym, seed=3)
    r = _judge(df, [("x", ">=", [30, 50, 70], 50)], delta=0.02)["x"]
    ni = r["ni"]
    assert ni["lower"] == pytest.approx(ni["est"] - RB.Z_ONE * ni["se"])
    assert ni["pass"] == (ni["lower"] >= -0.02)
    assert (r["bucket"], r["reason"]) == (bucket, reason)


# ── ⑤ 同一买点事件多行 ──

def test_prefix_rows_count_once_any_row_passes():
    """同一买点事件被不同前缀锚到多行(闸字段取值不同、四态相同):事件只计一次,任一行过闸即算过闸。
    把事件展开成 1~3 行、其中一行取原值其余取更小值,结果应与「每个事件一行、字段取原值」完全一致。"""
    base = _synth(lambda x, yr: np.where(x >= 50, 0.08, 0.0), 200, seed=1)
    rng = np.random.default_rng(5)
    reps = rng.integers(1, 4, len(base))
    wide = base.loc[base.index.repeat(reps)].reset_index(drop=True)
    first = ~wide["seg"].duplicated()
    wide.loc[~first, "x"] = wide.loc[~first, "x"] * rng.uniform(0, 1, int((~first).sum()))
    wide = wide.sample(frac=1.0, random_state=0).sort_values("seg", kind="stable").reset_index(drop=True)

    gates = [("x", ">=", [30, 50, 70])]
    one, many = _judge(base, gates, delta=0.05)["x"], _judge(wide, gates, delta=0.05)["x"]
    assert len(wide) > len(base)
    for a, b in zip(one["curve"], many["curve"]):
        assert (a["n_events_pool"], a["n_events_kept"]) == (b["n_events_pool"], b["n_events_kept"]) == (len(base), a["n_events_kept"])
        assert a["raw"] == pytest.approx(b["raw"])
        assert a["controlled"] == pytest.approx(b["controlled"])
    assert (one["verdict"], one["shape"]) == (many["verdict"], many["shape"])

    rowwise = _judge(wide.assign(seg=np.arange(len(wide))), gates, delta=0.05)["x"]
    assert rowwise["curve"][0]["n_events_pool"] == len(wide)        # 逐行口径会把前缀行当成独立买点事件

    bad = wide.copy()
    dup = bad.index[bad["seg"].duplicated()][0]
    bad.loc[dup, "up"] += 1
    with pytest.raises(ValueError, match="取值不同"):
        _judge(bad, gates, delta=0.05)


def test_pool_uses_other_gates_working_values():
    """判一道闸时,其余闸按各自工作点取值过滤出池;条件总体之外的行不进任何池。"""
    df = _synth(lambda x, yr: 0.0 * x, 60, seed=0)
    rng = np.random.default_rng(1)
    df["b"] = rng.uniform(0, 1, len(df))
    pop = df["M"].to_numpy() < 0.04
    res = _judge(df, [("x", ">=", [50], 50), ("b", ">=", [0.5], 0.5)], delta=0.5, pop=pop)
    assert res["x"]["curve"][0]["n_events_pool"] == int((pop & (df["b"] >= 0.5)).sum())
    assert res["b"]["curve"][0]["n_events_pool"] == int((pop & (df["x"] >= 50)).sum())
    assert res["x"]["curve"][0]["n_events_kept"] == int((pop & (df["b"] >= 0.5) & (df["x"] >= 50)).sum())


# ── ⑥ 不稳只在功效足够时判 ──

def test_unstable_only_when_powered():
    """2024 年闸有效(+12 点)、2025 年反向(−3 点):样本大、每年都有把握看到合并效应 → 判「不稳」;
    同样的设计样本小、分年功效不够 → 不判不稳,照常给出有信号。"""
    effect = lambda x, yr: np.where(x >= 50, np.where(yr == 2024, 0.12, -0.03), 0.0)  # noqa: E731
    big = _judge(_synth(effect, 600, seed=0), [("x", ">=", [50])], delta=0.15)["x"]
    assert big["verdict"] == "不稳" and big["bucket"] == "判不了"
    assert "2025 年显著反向" in big["reason"]
    small = _judge(_synth(effect, 60, seed=0), [("x", ">=", [50])], delta=0.15)["x"]
    assert small["verdict"] == "有信号+"
    assert small["stats"]["stability"] == "分年功效不足,不判不稳"


def test_time_undetermined_flag_derived_from_pool():
    """「时间维未定」由池里的数据推出:池跨两年、多个时间窗 → 不标;只覆盖一个年份 → 标,并报出实际窗数与年份数。"""
    df = _synth(lambda x, yr: np.where(x >= 50, 0.06, 0.0), 100, seed=0)
    both = _judge(df, [("x", ">=", [50])], delta=0.2)["x"]
    assert "时间维未定" not in both["time_flags"]
    assert both["stats"]["n_years"] == 2 and both["stats"]["n_windows"] > 2
    one = df[df["date"].dt.year == 2024].reset_index(drop=True)
    r = _judge(one, [("x", ">=", [50])], delta=0.2)["x"]
    assert "时间维未定" in r["time_flags"] and r["stats"]["n_years"] == 1 and r["stats"]["n_windows"] > 2


# ── ⑦ 簇稳健回归与手算一致 ──

def test_cluster_robust_regression_matches_hand_calculation():
    """6 只股 × 5 个买点事件、同一时间窗、无控制列:判定层报的三列回归系数与 SE 与手算的 WLS + CR1 一致。"""
    rng = np.random.default_rng(3)
    n = 30
    up = rng.integers(0, 5, n)
    down = rng.integers(1, 5, n)
    df = pd.DataFrame({"symbol": np.repeat([f"S{i}" for i in range(6)], 5),
                       "date": pd.Timestamp("2024-02-01") + pd.to_timedelta(rng.integers(0, 20, n), "D"),
                       "M": 0.02, "c0_atr_pct": 0.03, "seg": np.arange(n),
                       "up": up, "down": down, "both": rng.integers(0, 2, n), "none": 1, "x": rng.uniform(0, 1, n)})
    r = _judge(df, [("x", ">=", [0.5])], delta=1.0, controls=())["x"]
    kept = (df["x"] >= 0.5).to_numpy(float)
    D = (df["up"] + df["down"] + df["both"]).to_numpy(float)
    y = df["up"].to_numpy(float) / D
    X = np.column_stack([np.ones(n), kept])

    def hand(w, groups):
        bread = np.linalg.inv(X.T @ (X * w[:, None]))
        beta = bread @ X.T @ (w * y)
        e = y - X @ beta
        meat = np.zeros((2, 2))
        for g in np.unique(groups):
            s = (X[groups == g] * (w * e)[groups == g][:, None]).sum(axis=0)
            meat += np.outer(s, s)
        G = len(np.unique(groups))
        V = G / (G - 1) * (n - 1) / (n - 2) * bread @ meat @ bread
        return beta[1], np.sqrt(V[1, 1])

    cols = r["stats"]["three_cols"]
    sym = df["symbol"].to_numpy()
    for name, (w, groups) in {"加权去簇": (D, sym), "加权不去簇": (D, np.arange(n)),
                              "不加权去簇": (np.ones(n), sym)}.items():
        b, se = hand(w, groups)
        assert cols[name]["beta"] == pytest.approx(b, rel=1e-10)
        assert cols[name]["se"] == pytest.approx(se, rel=1e-10)
    k = kept.astype(bool)
    raw = df["up"][k].sum() / D[k].sum() - df["up"].sum() / D.sum()
    assert r["stats"]["raw"]["est"] == pytest.approx(raw, rel=1e-12)
