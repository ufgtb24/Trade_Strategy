"""大涨段:同一段行情只取一次、每周限量、分组特征只用 t 及以前(改 t 之后数据结果不变)、
所有段都正常参加排名(最大单日跳变只作显示)。"""
import numpy as np
import pandas as pd

from chart_workflow.bigmoves import build_list, cap_per_week, select_bigmoves, suppress_same_move
from chart_workflow.config import DEFAULTS
from chart_workflow.features import feature_frame
from chart_workflow.labels import label_frame
from chart_workflow.panel import build_panel
from path2.calc.atr import rolling_atr_pct_nanmedian
from tests.chart_workflow.conftest import make_stock


def test_same_move_taken_once():
    d0 = pd.Timestamp("2024-03-01")
    cands = pd.DataFrame({
        "symbol": ["A"] * 4 + ["B"],
        "date": [d0 + pd.Timedelta(days=i) for i in (0, 14, 35, 140, 14)],
        "bar_idx": [100, 110, 125, 200, 110],
        "rel": [5.0, 4.0, 3.0, 2.5, 4.5],
    })
    kept = suppress_same_move(cands, bars=20)
    a = sorted(kept[kept["symbol"] == "A"]["bar_idx"].tolist())
    assert a == [100, 125, 200]            # 110 离 100 只有 10 根,被压掉;125 离 100 有 25 根
    assert kept[kept["symbol"] == "B"]["bar_idx"].tolist() == [110]   # 别的股票不受影响


def test_cap_per_week():
    d = pd.Timestamp("2024-03-04")          # 周一
    df = pd.DataFrame({"symbol": [f"S{i}" for i in range(7)],
                       "date": [d + pd.Timedelta(days=i % 5) for i in range(7)],
                       "bar_idx": 0, "rel": [1, 2, 3, 4, 5, 6, 7.0]})
    other = pd.DataFrame({"symbol": ["Z"], "date": [d + pd.Timedelta(days=7)], "bar_idx": 0,
                          "rel": [0.5]})
    out = cap_per_week(pd.concat([df, other], ignore_index=True), 5)
    assert sorted(out["rel"].tolist()) == [0.5, 3, 4, 5, 6, 7]


def _cands(rel, rise=None, jump=None):
    n = len(rel)
    return pd.DataFrame({
        "symbol": [f"S{i}" for i in range(n)],
        "date": pd.bdate_range("2024-01-01", periods=n),
        "bar_idx": [0] * n,
        "rel": rel,
        "rise": rise or [1.0] * n,
        "max_jump": jump or [1.2] * n,
    })


def test_select_threshold_and_top():
    panel = _cands([0.5, 1.9, 2.0, 2.5, 3, 4, 5, 6, 7, np.nan])
    sel = select_bigmoves(panel, {**DEFAULTS["bigmoves"]}, top=3)
    assert sel["rel"].tolist() == [7, 6, 5]
    sel = select_bigmoves(panel, {**DEFAULTS["bigmoves"]}, top=100)
    assert sel["rel"].min() >= 2.0 and len(sel) == 7


def test_extreme_rise_and_jump_rank_normally():
    # 涨幅超 10 倍、单日跳变超 5 倍都不再挪出排名:只按相对涨幅排
    panel = _cands(rel=[9.0, 8.0, 7.0], rise=[300.0, 3.0, 2.0], jump=[1.5, 9.0, 1.2])
    sel = select_bigmoves(panel, {**DEFAULTS["bigmoves"]}, top=3)
    assert sel["symbol"].tolist() == ["S0", "S1", "S2"]


def test_features_only_use_past():
    df = make_stock(seed=3)
    M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], period=20)
    a = feature_frame(df, M, DEFAULTS["features"])
    t = pd.Timestamp("2025-03-03")
    df2 = df.copy()
    after = df2.index > t
    df2.loc[after, ["open", "high", "low", "close"]] *= 3.0
    df2.loc[after, "volume"] *= 7.0
    M2 = rolling_atr_pct_nanmedian(df2["high"], df2["low"], df2["close"], period=20)
    b = feature_frame(df2, M2, DEFAULTS["features"])
    pd.testing.assert_frame_equal(a.loc[:t], b.loc[:t])
    assert not a.loc[after].equals(b.loc[after])          # 之后确实变了(改动生效)


def test_build_list_groups_and_windows(cw_env):
    cfg, pkl_dir = cw_env
    for i in range(4):
        make_stock(seed=10 + i, sigma=0.04).to_pickle(pkl_dir / f"S{i}.pkl")
    panel = build_panel(cfg, verbose=False)
    doc = build_list(panel, {**cfg, "bigmoves": {**cfg["bigmoves"], "rel_min": 1.0}},
                     "t-big", top=50)
    keys = [g["key"] for g in doc["groups"]]
    assert keys == ["all", "deep_drop", "rising", "flat", "other"]
    all_ids = doc["groups"][0]["item_ids"]
    assert len(all_ids) == len(doc["items"]) > 0
    assert sum(len(g["item_ids"]) for g in doc["groups"][1:]) == len(all_ids)
    for it in doc["items"]:
        assert it["view_end"] <= cfg["train_end"]
        assert it["view_start"] < it["t"] < it["view_end"]
        assert {"decision", "entry", "up_line", "down_line", "peak_date"} <= set(it["marks"])
        assert it["tags"][0] in ("跳空", "不跳空")

