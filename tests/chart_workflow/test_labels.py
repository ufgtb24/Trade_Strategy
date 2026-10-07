"""标签口径的金标数字:次日开盘起点、按收盘判先碰哪条线、先碰下线后的高点不计入 rise、
不越过训练段末日。统一用 k=1、M=0.1(两条线 = P×1.1 与 P/1.1)。"""
import math

import numpy as np
import pandas as pd
import pytest

from chart_workflow.labels import compute_labels, label_frame


def _df(rows, start="2025-01-01"):
    """rows: [(open, high, low, close), ...] → 日线(工作日)。"""
    dates = pd.bdate_range(start, periods=len(rows), name="date")
    o, h, l, c = map(np.array, zip(*rows))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0}, index=dates)


def _lab(rows, H, M=0.1, k=1.0):
    df = _df(rows)
    return compute_labels(df["open"], df["high"], df["low"], df["close"],
                          np.full(len(df), M), k, H)


def test_entry_is_next_open_and_up_first():
    # t=0 收盘 9.5,但买入价取 t+1 开盘 10;第 2 天收盘 11.2 ≥ U=11 先碰上线
    rows = [(9.4, 9.6, 9.3, 9.5),
            (10.0, 10.5, 9.8, 10.2),
            (10.2, 11.5, 10.1, 11.2),
            (11.0, 12.0, 8.0, 8.5),     # 收盘 8.5 ≤ D,但上线已先碰
            (8.5, 8.6, 8.4, 8.5)]
    lab = _lab(rows, H=3)
    assert lab["P"][0] == pytest.approx(10.0)
    assert lab["U"][0] == pytest.approx(11.0)
    assert lab["D"][0] == pytest.approx(10.0 / 1.1)
    assert lab["dir"][0] == 1
    assert lab["mag"][0] == pytest.approx(0.2)            # max(10.5, 11.5, 12) / 10 − 1
    assert lab["dd"][0] == pytest.approx(-0.2)            # min(9.8, 10.1, 8.0) / 10 − 1
    # 先碰下线在第 3 天,W = 第 1..3 天,最高 12 在第 3 天
    assert lab["rise"][0] == pytest.approx(0.2)
    assert lab["peak_off"][0] == 3
    assert lab["rel"][0] == pytest.approx(math.log(1.2) / math.log(1.1))


def test_close_decides_not_intraday_touch():
    # 第 1 天最高 11.5 越过 U=11 但收盘 10.5 没到;第 2 天收盘 9.0 ≤ D → −1
    rows = [(10.0, 10.0, 10.0, 10.0),
            (10.0, 11.5, 9.9, 10.5),
            (10.5, 10.6, 8.9, 9.0),
            (9.0, 9.1, 8.9, 9.0)]
    lab = _lab(rows, H=3)
    assert lab["dir"][0] == -1


def test_neither_line_is_zero():
    rows = [(10.0, 10.0, 10.0, 10.0)] + [(10.0, 10.8, 9.3, 10.1)] * 3
    lab = _lab(rows, H=3)
    assert lab["dir"][0] == 0
    assert lab["stop_off"][0] == -1


def test_high_after_stop_not_in_rise():
    # 第 1 天收盘 9.0 ≤ D 先碰下线;第 2 天冲到 13 → 计入 mag,不计入 rise
    rows = [(10.0, 10.0, 10.0, 10.0),
            (10.0, 10.3, 8.8, 9.0),
            (9.0, 13.0, 9.0, 12.5),
            (12.5, 12.6, 12.0, 12.2)]
    lab = _lab(rows, H=3)
    assert lab["dir"][0] == -1
    assert lab["stop_off"][0] == 1
    assert lab["mag"][0] == pytest.approx(0.3)
    assert lab["rise"][0] == pytest.approx(0.03)          # 只看第 1 天的最高 10.3
    assert lab["peak_off"][0] == 1
    assert lab["rel"][0] == pytest.approx(math.log(1.03) / math.log(1.1))


def test_invalid_when_window_incomplete_or_bad_m():
    rows = [(10.0, 10.0, 10.0, 10.0)] * 5
    lab = _lab(rows, H=3)
    assert lab["valid"].tolist() == [True, True, False, False, False]   # t+3 必须存在
    lab = _lab(rows, H=3, M=float("nan"))
    assert not lab["valid"].any()
    lab = _lab(rows, H=3, M=0.0)
    assert not lab["valid"].any()


def test_label_frame_never_crosses_train_end():
    rows = [(10.0, 10.2, 9.9, 10.0)] * 30
    df = _df(rows, start="2025-12-01")              # 2025-12-01 .. 2026-01-09
    M = np.full(len(df), 0.1)
    H = 3
    lab = label_frame(df, M, 1.0, H, train_end="2025-12-31")
    assert lab.index.max() <= pd.Timestamp("2025-12-31")
    valid = lab[lab["valid"]]
    # 最后一个有效决策日 + H 个交易日恰好是训练段末日
    last_t = valid.index.max()
    pos = list(lab.index).index(last_t)
    assert lab.index[pos + H] == pd.Timestamp("2025-12-31")
    assert valid["entry_date"].max() <= pd.Timestamp("2025-12-31")
    assert valid["peak_date"].max() <= pd.Timestamp("2025-12-31")

    # 训练段之后的价格怎么改,标签都不变
    df2 = df.copy()
    df2.loc[df2.index > "2025-12-31", ["open", "high", "low", "close"]] *= 5
    lab2 = label_frame(df2, M, 1.0, H, train_end="2025-12-31")
    pd.testing.assert_frame_equal(lab, lab2)
