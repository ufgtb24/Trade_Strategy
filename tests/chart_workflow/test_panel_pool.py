"""股票池各条件各一个反例(含 M 下限);训练段之后的行一律不出现;数据窗口与单日跳变倍数。"""
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
    # 缓存目录里写明:含 2024 年的后续涨跌,研究不得直接读
    from chart_workflow.config import root_dir
    readme = (root_dir(cfg) / "cache" / "README.txt").read_text()
    assert "含 2024 年的后续涨跌，研究不得直接读" in readme
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


def test_quiet_stock_below_m_floor_excluded(cw_env):
    cfg, _ = cw_env
    quiet = make_stock(seed=1, sigma=0.002)              # 每天只动千分之几 → M < 0.01
    assert len(stock_panel(quiet, "QUIET", cfg, True)) == 0
    base = stock_panel(make_stock(seed=1), "OK", cfg, True)
    assert len(base) > 0 and (base["M"] >= cfg["pool"]["m_min"]).all()
    # 下限是配置项:调到 0 后安静的票回到池子
    loose = {**cfg, "pool": {**cfg["pool"], "m_min": 0.0}}
    assert len(stock_panel(quiet, "QUIET", loose, True)) > 0


def _with_shell(price: float, shell_end: str, seed: int = 1) -> pd.DataFrame:
    """shell_end 及以前收盘钉在 price 上下、每天几乎不动(SPAC 壳期),之后从 price 起正常游走。"""
    df = make_stock(seed=seed)
    end = pd.Timestamp(shell_end)
    df.loc[df.index > end, ["open", "high", "low", "close"]] *= (
        price / df.loc[df.index > end, "open"].iloc[0])
    pre = df.index <= end
    noise = np.random.default_rng(seed).normal(0, 0.0005, pre.sum())
    close = price * (1 + noise)
    df.loc[pre, "close"] = close
    df.loc[pre, "open"] = close
    df.loc[pre, "high"] = close * 1.001
    df.loc[pre, "low"] = close * 0.999
    return df


def test_spac_shell_and_next_lookback_bars_excluded(cw_env):
    cfg, _ = cw_env
    sp = cfg["pool"]["spac_shell"]
    df = _with_shell(10.0, "2024-04-30")
    out = stock_panel(df, "SHELL", cfg, True)
    dates = df.index
    j = dates.get_loc(pd.Timestamp("2024-04-30"))
    first_ok = dates[j + sp["lookback_bars"] + 1]            # 壳期最后一天已滑出往前 lookback 根
    assert len(out) > 0
    assert out["date"].min() >= first_ok
    off = {**cfg, "pool": {**cfg["pool"], "spac_shell": {**sp, "enabled": False}}}
    back = stock_panel(df, "SHELL", off, True)
    assert (back["date"] < first_ok).any()                   # 关掉后壳期之后那几个月回到池子


def test_spac_shell_rule_leaves_others_alone(cw_env):
    cfg, _ = cw_env
    off = {**cfg, "pool": {**cfg["pool"], "spac_shell": {**cfg["pool"]["spac_shell"],
                                                         "enabled": False}}}
    base = make_stock(seed=1)                                # 价 ≈10、正常波动
    pd.testing.assert_frame_equal(stock_panel(base, "OK", cfg, True),
                                  stock_panel(base, "OK", off, True))
    low = _with_shell(5.0, "2024-04-30")                     # 钉在 5 元不动:不是壳的价位
    pd.testing.assert_frame_equal(stock_panel(low, "PIN5", cfg, True),
                                  stock_panel(low, "PIN5", off, True))


def test_max_jump_window(cw_env):
    cfg, _ = cw_env
    df = make_stock(seed=4, sigma=0.01)
    j = df.index.get_loc(pd.Timestamp("2024-09-03"))
    df.iloc[j:, :4] *= 6.0                               # 第 j 天收盘相对前一天 ×6
    df.iloc[j:, 4] /= 6.0
    out = stock_panel(df, "J", cfg, True).set_index("bar_idx")
    H, look = cfg["H"], cfg["data_errors"]["lookback_bars"]
    inside = [i for i in out.index if j - H <= i <= j + look]
    outside = [i for i in out.index if i < j - H or i > j + look]
    assert inside and outside
    assert (out.loc[inside, "max_jump"] > 5).all()      # [t−20, t+H] 盖住了跳变日
    assert (out.loc[outside, "max_jump"] < 2).all()


def test_data_window_columns(cw_env):
    cfg, _ = cw_env
    df = make_stock(seed=5)
    out = stock_panel(df, "W", cfg, True)
    dates = df.index[df.index <= pd.Timestamp(cfg["train_end"])]
    look, H = cfg["data_errors"]["lookback_bars"], cfg["H"]
    for _, r in out.sample(20, random_state=0).iterrows():
        i = int(r["bar_idx"])
        assert r["win_start"] == dates[i - look]
        assert r["win_end"] == dates[i + H]
