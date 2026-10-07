"""大涨段:同一段行情只取一次、每周限量、分组特征只用 t 及以前(改 t 之后数据结果不变)、
疑似数据出错的段进「待核对」组且不参加排序。"""
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


def _cands(rel, rise=None, jump=None, symbols=None, bar_idx=None):
    n = len(rel)
    return pd.DataFrame({
        "symbol": symbols or [f"S{i}" for i in range(n)],
        "date": pd.bdate_range("2024-01-01", periods=n),
        "bar_idx": bar_idx or [0] * n,
        "rel": rel,
        "rise": rise or [1.0] * n,
        "max_jump": jump or [1.2] * n,
    })


def test_select_threshold_and_top():
    panel = _cands([0.5, 1.9, 2.0, 2.5, 3, 4, 5, 6, 7, np.nan])
    sel, review = select_bigmoves(panel, {**DEFAULTS["bigmoves"]}, top=3)
    assert sel["rel"].tolist() == [7, 6, 5]
    assert len(review) == 0
    sel, _ = select_bigmoves(panel, {**DEFAULTS["bigmoves"]}, top=100)
    assert sel["rel"].min() >= 2.0 and len(sel) == 7


def test_anomalies_go_to_review_and_skip_ranking():
    # rel 最大的两段:一段涨幅超 10 倍(rise 9.5),一段窗口里有单日 ÷6(max_jump 记为 6)
    panel = _cands(rel=[9.0, 8.0, 7.0, 6.0, 5.0, 4.0],
                   rise=[9.5, 3.0, 2.0, 2.0, 9.0, 1.5],      # rise 恰好 9 不算(要 > 9)
                   jump=[1.5, 6.0, 1.2, 5.0, 1.1, 1.3])      # 恰好 5 倍不算(要 > 5)
    sel, review = select_bigmoves(panel, {**DEFAULTS["bigmoves"]}, top=3)
    assert review["symbol"].tolist() == ["S0", "S1"]         # 按涨幅原值降序
    assert sel["symbol"].tolist() == ["S2", "S3", "S4"]      # 前 3 名的名额不被待核对占用


def test_same_move_counted_once_across_review_and_main():
    # 同一只股票:rel 最大那天疑似出错 → 进待核对,并压掉 10 根以内的正常候选
    panel = _cands(rel=[9.0, 8.0, 3.0], rise=[12.0, 5.0, 2.0], symbols=["A", "A", "A"],
                   bar_idx=[100, 110, 150])
    sel, review = select_bigmoves(panel, {**DEFAULTS["bigmoves"]}, top=10)
    assert review["bar_idx"].tolist() == [100]
    assert sel["bar_idx"].tolist() == [150]


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
    assert keys == ["all", "deep_drop", "rising", "flat", "other", "review"]
    all_ids = doc["groups"][0]["item_ids"]
    review_ids = doc["groups"][-1]["item_ids"]
    assert len(all_ids) + len(review_ids) == len(doc["items"]) and len(all_ids) > 0
    assert sum(len(g["item_ids"]) for g in doc["groups"][1:-1]) == len(all_ids)
    for it in doc["items"]:
        assert it["view_end"] <= cfg["train_end"]
        assert it["view_start"] < it["t"] < it["view_end"]
        assert {"decision", "entry", "up_line", "down_line", "peak_date"} <= set(it["marks"])
        assert it["tags"][0] in ("跳空", "不跳空")


def test_build_list_review_group(cw_env):
    """一只股票在训练段中途价格被错乘 6 倍(单日跳变)→ 它的大涨段进「待核对」,不进其他分组。"""
    cfg, pkl_dir = cw_env
    bad = make_stock(seed=50, sigma=0.03)
    jump_day = pd.Timestamp("2024-09-03")
    bad.loc[bad.index >= jump_day, ["open", "high", "low", "close"]] *= 6.0
    bad.loc[bad.index >= jump_day, "volume"] /= 6.0          # 成交额仍在池子范围内
    bad.to_pickle(pkl_dir / "BAD.pkl")
    for i in range(3):
        make_stock(seed=60 + i, sigma=0.04).to_pickle(pkl_dir / f"G{i}.pkl")
    panel = build_panel(cfg, verbose=False)
    doc = build_list(panel, cfg, "t-review", top=50)
    groups = {g["key"]: g["item_ids"] for g in doc["groups"]}
    review = groups["review"]
    assert review and all(i.startswith("BAD@") for i in review)
    others = {i for k, ids in groups.items() if k != "review" for i in ids}
    assert not (set(review) & others)
    by_id = {it["item_id"]: it for it in doc["items"]}
    for i in review:
        assert any(t.startswith("疑似：") for t in by_id[i]["tags"])
        assert by_id[i]["metrics"]["max_jump"] > 5 or by_id[i]["metrics"]["rise"] > 9
    assert doc["params"]["pool"]["m_min"] == cfg["pool"]["m_min"]
