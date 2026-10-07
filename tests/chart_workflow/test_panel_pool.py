"""股票池四个条件各一个反例;训练段之后的行一律不出现。"""
import numpy as np
import pandas as pd

from chart_workflow.panel import build_panel, stock_panel
from tests.chart_workflow.conftest import make_stock


def _write(pkl_dir, sym, df):
    df.to_pickle(pkl_dir / f"{sym}.pkl")


def test_base_stock_is_in_pool_and_never_after_train_end(cw_env):
    cfg, pkl_dir = cw_env
    _write(pkl_dir, "GOOD", make_stock(seed=1))         # 价 ≈10、成交额 ≈1000 万
    panel = build_panel(cfg, verbose=False)
    assert len(panel) > 300
    assert set(panel["symbol"]) == {"GOOD"}
    end = pd.Timestamp(cfg["train_end"])
    assert panel["date"].min() >= pd.Timestamp(cfg["train_start"])
    for col in ("date", "entry_date", "peak_date"):
        assert panel[col].max() <= end
    # 最后一个决策日之后恰好还有 H 个交易日在训练段内
    dates = make_stock(seed=1).index
    dates = dates[dates <= end]
    last = panel["date"].max()
    assert len(dates[dates > last]) == cfg["H"]


def test_not_common_is_excluded(cw_env):
    cfg, pkl_dir = cw_env
    _write(pkl_dir, "ABCDW", make_stock(seed=1))        # 5 位、W 结尾 → 权证
    assert len(build_panel(cfg, verbose=False)) == 0


def test_price_cap(cw_env):
    cfg, _ = cw_env
    df = make_stock(seed=1)
    df[["open", "high", "low", "close"]] *= 20.5 / df["close"].min()   # 全程收盘 > 20
    df["volume"] = 500_000.0                             # 成交额仍在 200 万..1 亿之间
    assert len(stock_panel(df, "PRICY", cfg, True)) == 0
    ok = stock_panel(make_stock(seed=1), "OK", cfg, True)
    assert (ok["close"] <= 20).all()


def test_dollar_volume_band(cw_env):
    cfg, _ = cw_env
    low = make_stock(seed=1, vol=50_000.0)              # 成交额 ≈50 万 < 200 万
    high = make_stock(seed=1, vol=50_000_000.0)         # 成交额 ≈5 亿 > 1 亿
    assert len(stock_panel(low, "LOW", cfg, True)) == 0
    assert len(stock_panel(high, "HIGH", cfg, True)) == 0


def test_flat_prices_have_no_m_and_bad_next_open_excluded(cw_env):
    cfg, _ = cw_env
    flat = make_stock(seed=1)
    flat[["open", "high", "low", "close"]] = 10.0        # TR 恒为 0 → M=0,不是正数
    assert len(stock_panel(flat, "FLAT", cfg, True)) == 0

    df = make_stock(seed=1)
    t = pd.Timestamp("2024-06-03")
    nxt = df.index[df.index.get_loc(t) + 1]
    base = stock_panel(df, "X", cfg, True)
    assert t in set(base["date"])
    df.loc[nxt, "open"] = 0.0                            # 次日开盘不是正数
    bad = stock_panel(df, "X", cfg, True)
    assert t not in set(bad["date"])


def test_post_train_data_changes_nothing(cw_env):
    cfg, _ = cw_env
    df = make_stock(seed=2)
    a = stock_panel(df, "X", cfg, True)
    df2 = df.copy()
    after = df2.index > pd.Timestamp(cfg["train_end"])
    df2.loc[after, ["open", "high", "low", "close"]] *= 3
    df2.loc[after, "volume"] *= 10
    b = stock_panel(df2, "X", cfg, True)
    pd.testing.assert_frame_equal(a, b)
