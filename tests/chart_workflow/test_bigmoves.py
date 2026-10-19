"""大涨段:同一段行情只取一次、同股不互相露底(同股两条的整段图窗不交叠:决策日不落在另一条的图窗里,靠后那条的
图窗起点也不落在靠前那条决策日之后那段里)、每周限量、分组特征只用 t 及以前(改 t 之后数据结果不变)、
所有段都正常参加排名(最大单日跳变只作显示)。正常行情上同股不交叠的几段照常都列出(不能拦多)。"""
import numpy as np
import pandas as pd

from chart_workflow.bigmoves import build_list, cap_per_week, select_bigmoves, suppress_same_move
from chart_workflow.config import DEFAULTS
from chart_workflow.features import feature_frame
from chart_workflow.labels import label_frame
from chart_workflow.panel import build_panel
from path2.calc.atr import rolling_atr_pct_nanmedian
from tests.chart_workflow.conftest import make_stock


def _same_stock_overlaps(cfg, rows) -> list:
    """同股两条里,整段图窗(起点到终点)交叠的对子(应当为空)。rows:(symbol, t) 列表。"""
    from chart_workflow.listfile import view_window
    bad = []
    for a in rows:
        s, e = view_window(cfg, a[0], a[1])
        for b in rows:
            if b != a and b[0] == a[0]:
                s2, e2 = view_window(cfg, b[0], b[1])
                if s <= e2 and s2 <= e:
                    bad.append((a, b))
    return bad


def test_same_move_taken_once(cw_env):
    cfg, pkl_dir = cw_env
    for sym in ("A", "B"):
        make_stock(seed=1).to_pickle(pkl_dir / f"{sym}.pkl")
    from chart_workflow.loader import trading_dates
    dates = trading_dates(cfg, "A")
    k0 = int(dates.searchsorted(pd.Timestamp("2025-03-03")))
    H = cfg["H"]
    before = cfg["view"]["before_bars"]
    idx = {"A1": k0, "A2": k0 + 10, "A3": k0 + H - 5, "A4": k0 + 130, "A5": k0 + before + H + 1}
    cands = pd.DataFrame({
        "symbol": ["A"] * 5 + ["B"],
        "date": [dates[idx[k]] for k in ("A1", "A2", "A3", "A4", "A5")] + [dates[k0 + 10]],
        "rel": [5.0, 4.0, 3.0, 2.5, 2.4, 4.5],
    })
    kept = suppress_same_move(cands, cfg)
    a = sorted(kept[kept["symbol"] == "A"]["date"].tolist())
    # A2 离 A1 只有 10 根,被压掉;A3 离 A1 超过 20 根,但落在 A1 的图窗里(决策日后 H 根内),也压掉;
    # A4 离 A1 130 根,谁的决策日都不在对方图窗里,但 A4 的图窗起点(往前 before_bars 根)落在 A1 决策日之后的
    # H 根里——点买点之前就画着 A1 的大涨,压掉;A5 的图窗起点在 A1 图窗终点之后,两段不交叠,保留
    assert a == [dates[idx["A1"]], dates[idx["A5"]]]
    assert kept[kept["symbol"] == "B"]["date"].tolist() == [dates[k0 + 10]]   # 别的股票不受影响
    assert not _same_stock_overlaps(cfg, list(zip(kept["symbol"], kept["date"])))


def test_far_apart_moves_of_one_stock_all_listed(cw_env):
    """必须能过:同一只股票相隔很远、图窗不交叠的几段都列出;只有交叠的才压掉。"""
    cfg, pkl_dir = cw_env
    cfg = {**cfg, "view_floor": None}              # 图窗起点不截,按原样的 before_bars 算交叠
    make_stock(seed=3).to_pickle(pkl_dir / "A.pkl")
    from chart_workflow.loader import trading_dates
    dates = trading_dates(cfg, "A")
    gap = cfg["view"]["before_bars"] + cfg["H"] + 1
    k0 = int(dates.searchsorted(pd.Timestamp("2024-01-02"))) + cfg["view"]["before_bars"]
    ks = [k0, k0 + gap, k0 + 2 * gap]
    cands = pd.DataFrame({"symbol": ["A"] * 4, "date": [dates[k] for k in ks] + [dates[ks[1] + 5 + cfg["H"]]],
                          "rel": [3.0, 2.9, 2.8, 2.7]})
    kept = suppress_same_move(cands, cfg)
    assert sorted(kept["date"].tolist()) == [dates[k] for k in ks]
    assert not _same_stock_overlaps(cfg, list(zip(kept["symbol"], kept["date"])))


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
    sel = select_bigmoves(panel, DEFAULTS, top=3)
    assert sel["rel"].tolist() == [7, 6, 5]
    sel = select_bigmoves(panel, DEFAULTS, top=100)
    assert sel["rel"].min() >= 2.0 and len(sel) == 7


def test_extreme_rise_and_jump_rank_normally():
    # 涨幅超 10 倍、单日跳变超 5 倍都不再挪出排名:只按相对涨幅排
    panel = _cands(rel=[9.0, 8.0, 7.0], rise=[300.0, 3.0, 2.0], jump=[1.5, 9.0, 1.2])
    sel = select_bigmoves(panel, DEFAULTS, top=3)
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
    cfg = {**cfg, "view_floor": None}           # 两年都给,同股才会有多条
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
    # 同股不互相露底:任何一条的决策日都不落在同股另一条的图窗里(同股多条确实出现过)
    syms = [it["symbol"] for it in doc["items"]]
    assert len(set(syms)) < len(syms)
    assert not _same_stock_overlaps(cfg, [(it["symbol"], it["t"]) for it in doc["items"]])
    for a in doc["items"]:
        for b in doc["items"]:
            if a is not b and a["symbol"] == b["symbol"]:
                assert not (a["view_start"] <= b["t"] <= a["view_end"])

