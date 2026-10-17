"""同日对照:命中 = 全体时领先为 0;手造两档验证加权对照与加权中位数;固定 seed 可复现。"""
import numpy as np
import pandas as pd
import pytest

from chart_workflow.config import DEFAULTS
from chart_workflow.control import Control, assign_bands, summarize, weighted_median

CCFG = {**DEFAULTS["control"], "n_boot": 100}


def _random_panel(n_days=30, n_per_day=60, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_per_day):
            rows.append({"symbol": f"S{i:03d}", "date": d, "M": rng.uniform(0.01, 0.1),
                         "dir": int(rng.choice([-1, 0, 1])), "mag": rng.exponential(0.2)})
    return pd.DataFrame(rows)


def test_weighted_median_basics():
    assert weighted_median([1, 2, 3], [1, 1, 2]) == pytest.approx(2.5)   # 累计恰好一半 → 与下一个取平均
    assert weighted_median([1, 2, 3], [3, 1, 1]) == pytest.approx(1.0)
    v = np.random.default_rng(1).normal(size=101)
    assert weighted_median(v, np.ones_like(v)) == pytest.approx(np.median(v))
    v = v[:100]
    assert weighted_median(v, np.ones_like(v)) == pytest.approx(np.median(v))


def test_hits_equal_everything_gives_zero_lead():
    panel = _random_panel()
    ctl = Control(panel, CCFG)
    r = ctl._evaluate(np.arange(len(panel)), CCFG, with_noise=False)
    assert abs(r["dir_lead"]) < 1e-12
    assert abs(r["mag_lead"]) < 1e-12
    assert r["ctrl_mag_median"] == pytest.approx(np.median(panel["mag"]))


def test_two_band_weighted_control():
    # 一天 40 个股票日 → 档数 min(5, 40 // 20) = 2;低波动档 20 个、高波动档 20 个
    d = pd.Timestamp("2024-03-01")
    low = [{"symbol": f"L{i:02d}", "date": d, "M": 0.01 + i * 1e-4,
            "dir": 1 if i < 10 else -1, "mag": i * 0.01} for i in range(20)]
    high = [{"symbol": f"H{i:02d}", "date": d, "M": 0.05 + i * 1e-4,
             "dir": 1, "mag": 1.0 + i * 0.01} for i in range(20)]
    panel = pd.DataFrame(low + high)
    cells = assign_bands(panel, 5, 20)
    assert len(set(cells[:20])) == 1 and len(set(cells[20:])) == 1 and cells[0] != cells[20]

    ctl = Control(panel, CCFG)
    hits = np.array([0, 15, 25])              # 两个落低档(dir +1、−1),一个落高档(dir +1)
    r = ctl._evaluate(hits, CCFG, with_noise=False)
    # 对照方向均值 = (B_low + B_low + B_high) / 3 = (0 + 0 + 1) / 3
    assert r["ctrl_dir_mean"] == pytest.approx(1 / 3)
    assert r["hit_dir_mean"] == pytest.approx(1 / 3)
    assert r["dir_lead"] == pytest.approx(0.0)
    # 对照混合:低档每个值权重 2/20、高档每个值权重 1/20,总 3,半数 1.5 恰落在低档第 15 个值
    # → 与第 16 个取平均 (0.14 + 0.15) / 2
    assert r["ctrl_mag_median"] == pytest.approx(0.145)
    assert r["hit_mag_median"] == pytest.approx(0.15)     # median(0.00, 0.15, 1.05)
    assert r["mag_lead"] == pytest.approx(0.005)


def test_small_day_is_one_band():
    d = pd.Timestamp("2024-03-01")
    panel = pd.DataFrame([{"symbol": f"S{i}", "date": d, "M": 0.01 * (i + 1), "dir": 0,
                           "mag": 0.1} for i in range(19)])
    assert len(set(assign_bands(panel, 5, 20))) == 1


def test_noise_reproducible_with_fixed_seed():
    panel = _random_panel()
    ctl = Control(panel, CCFG)
    rows = np.flatnonzero(panel["symbol"].isin([f"S{i:03d}" for i in range(0, 60, 3)]).values)
    a = ctl._evaluate(rows, CCFG)
    b = ctl._evaluate(rows, CCFG)
    assert a["dir_noise"] == b["dir_noise"] and a["mag_noise"] == b["mag_noise"]
    assert a["dir_noise"] > 0
    c = ctl._evaluate(rows, {**CCFG, "seed": 123})
    assert c["dir_noise"] != a["dir_noise"]
    # 命中数 < 300 用 1.3 的放大系数;改成 1.0 后正好缩小 1.3 倍
    raw = ctl._evaluate(rows, {**CCFG, "inflate_small": 1.0, "inflate_large": 1.0})
    if len(rows) < CCFG["noise_large_n"]:
        assert a["dir_noise"] == pytest.approx(raw["dir_noise"] * 1.3)
    else:
        assert a["dir_noise"] == pytest.approx(raw["dir_noise"] * 1.2)


CTX = {"kind": "rule", "rule_id": "r", "version": "v1", "source": "user-text", "change": "测试"}


def _two_year_panel():
    panel = _random_panel(n_days=40)
    panel["date"] = panel["date"] + pd.Timedelta(days=320)      # 2024-11 起,跨进 2025
    return panel


def test_summarize_rows_years_and_graduation(cw_env):
    from chart_workflow.ledger import read_ledger
    cfg, _ = cw_env
    cfg = {**cfg, "control": CCFG}
    panel = _two_year_panel()
    ctl = Control(panel, CCFG)
    rows = np.arange(0, len(panel), 7)
    s = summarize(ctl, rows, cfg, ledger={**CTX, "list_id": "t-sum"})
    # 默认只给内圈年份:逐年行只有 2025,「全部」也只含 2025 年的命中
    assert [r["scope"] for r in s["rows"]] == ["全部", "2025"]
    n25 = int((panel["date"].values[rows] >= np.datetime64("2025-01-01")).sum())
    assert 0 < n25 < len(rows)
    assert s["rows"][0]["n_hits"] == s["rows"][1]["n_hits"] == n25
    assert s["years"] == ["2025"]
    assert set(s["concentration"]) == {"max_week_share", "max_stock_share"}
    assert "each_year" in s["graduation"]["checks"]
    # 算完当场记账:账本多一行,years 记的是内圈
    led = read_ledger()
    assert len(led) == 1 and led[0]["list_id"] == "t-sum" and led[0]["years"] == ["2025"]
    assert led[0]["entry_id"] == s["ledger_entry_id"] and led[0]["auto"] is True
    assert led[0]["summary_all"]["n_hits"] == n25


def test_summarize_refuses_without_ledger(cw_env):
    from chart_workflow.ledger import read_ledger
    cfg, _ = cw_env
    ctl = Control(_two_year_panel(), CCFG)
    with pytest.raises(TypeError):
        summarize(ctl, np.arange(10), cfg)                       # 不给记账上下文:不算
    with pytest.raises(ValueError, match="必须记账"):
        summarize(ctl, np.arange(10), cfg, ledger=None)
    with pytest.raises(ValueError, match="缺"):
        summarize(ctl, np.arange(10), cfg, ledger={"kind": "rule"})
    assert read_ledger() == []


def test_summarize_other_years_need_reason_and_are_logged(cw_env, capsys):
    from chart_workflow.ledger import read_ledger, render
    cfg, _ = cw_env
    cfg = {**cfg, "control": CCFG}
    panel = _two_year_panel()
    ctl = Control(panel, CCFG)
    rows = np.arange(0, len(panel), 7)
    with pytest.raises(ValueError, match="other_years_reason"):
        summarize(ctl, rows, cfg, ledger={**CTX, "list_id": "t-y0"}, years=["2024", "2025"])
    assert read_ledger() == []
    s = summarize(ctl, rows, cfg, ledger={**CTX, "list_id": "t-y1"}, years=["2024", "2025"],
                  other_years_reason="核对 2024 年的口径")
    assert [r["scope"] for r in s["rows"]] == ["全部", "2024", "2025"]
    assert s["rows"][0]["n_hits"] == len(rows)
    r = read_ledger()[-1]
    assert r["years"] == ["2024", "2025"] and r["other_years_reason"] == "核对 2024 年的口径"
    assert "内圈以外的年份 ['2024']" in capsys.readouterr().err
    assert "(含内圈外年份)" in render(read_ledger())
