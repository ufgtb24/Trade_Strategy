"""找图:股票池 /pool、大涨段清单 /rally、随机给一段图 /random(path2_web/finder.py)。

- 数据墙(spec 1.8 两种情形各一条):
  - 一段从 2025-11 涨到 2026-02 的涨,只按 2025-12-31 及以前的部分算涨幅;进不进清单也只看这部分;
  - random 抽到 2025-11 附近,窗口截到 2025-12-31,不往另一端补;
  三个路由在任何种子下返回的日期都不晚于 2025-12-31。
- SPAC 单位、认股权证代码、数据错误登记里的股票日都被排除;
- 同一段行情只取一次,每周限量与总量上限都生效;
- 缓存的键含训练段设置与副本指纹:改任一个都重算;键没变时读缓存、不重算。
合成行情的 pkl 都带 2026 年的行(模拟误配到完整行情),副本目录写好指纹清单。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web import finder as finder_mod
from path2_web.app import create_app
from path2_web.config import DEFAULT_CONFIG
from path2_web.snapshot_fingerprint import write_manifest

TRAIN_END = "2025-12-31"
FULL = pd.bdate_range("2021-10-01", "2026-03-31", name="date")
RALLY = DEFAULT_CONFIG["finder"]["rally"]


def _write(ddir, symbol: str, close: np.ndarray, volume=1e6, rng_pct=0.04) -> pd.DataFrame:
    """按 FULL 的日期写一只股票:开盘 = 收盘,最高 / 最低 = 收盘 ×(1 ± rng_pct/2)。"""
    df = pd.DataFrame({"open": close, "high": close * (1 + rng_pct / 2), "low": close * (1 - rng_pct / 2),
                       "close": close, "volume": np.full(len(close), volume)}, index=FULL)
    df.to_pickle(ddir / f"{symbol}.pkl")
    return df


def _ramp(start: str, end: str, lo=5.0, hi=15.0) -> np.ndarray:
    """平在 lo,start..end 线性涨到 hi,之后平在 hi。"""
    c = np.full(len(FULL), lo)
    i, j = FULL.searchsorted(pd.Timestamp(start)), FULL.searchsorted(pd.Timestamp(end))
    c[i:j + 1] = np.linspace(lo, hi, j - i + 1)
    c[j + 1:] = hi
    return c


def _client(tmp_path, ddir, **cfg) -> TestClient:
    names = tmp_path / "names.csv"
    if not names.exists():
        names.write_text("symbol,name\n")                   # 空名称表:只按代码规则认类别
    base = {"view_dataset_dir": str(ddir),
            "finder": {"security_names_file": str(names),
                       "data_errors_file": str(tmp_path / "data_errors.yaml")}}
    return TestClient(create_app(config_override={**base, **cfg}, outputs_root=str(tmp_path / "outputs"),
                                 use_thread_pool=True))


def _expected_rise(df: pd.DataFrame, t: pd.Timestamp, horizon=RALLY["horizon"], k=RALLY["k"]) -> float:
    """逐根照定义算一遍拿得到的涨幅(只给截好的 df):观察期 t+1..t+horizon,第一次收盘 ≤ 止损线就截住。"""
    pos = df.index.get_loc(t)
    obs = df.iloc[pos + 1:pos + 1 + horizon]
    P = obs["open"].iloc[0]
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1) / df["close"]
    M = tr.iloc[pos - 19:pos + 1].median()
    stop = P / (1 + k * M)
    hit = np.flatnonzero(obs["close"].to_numpy() <= stop)
    if len(hit):
        obs = obs.iloc[:hit[0] + 1]
    return obs["high"].max() / P - 1


@pytest.fixture
def snap(tmp_path):
    """RALLY:2025-12-15 起从 5 涨到 2026-02-27 的 20,截止前只走了一小段;
    LATE:2025 年底只涨了一点,2026-01 才大涨;FLAT:一直不动。"""
    d = tmp_path / "snap"
    d.mkdir()
    _write(d, "RALLY", _ramp("2025-12-15", "2026-02-27", hi=20.0))
    late = np.full(len(FULL), 5.0)
    i = FULL.searchsorted(pd.Timestamp("2025-12-22"))
    j = FULL.searchsorted(pd.Timestamp("2026-01-02"))
    late[i:j] = np.linspace(5.0, 5.1, j - i)
    late[j:] = 20.0
    _write(d, "LATE", late)
    _write(d, "FLAT", np.full(len(FULL), 5.0))
    write_manifest(d)
    return d


def test_rally_crossing_year_end_uses_only_pre_cutoff_part(tmp_path, snap):
    """spec 1.8:一段从 2025-11 涨到 2026-02 的涨,只按 2025-12-31 及以前的部分算涨幅;
    进不进清单也只看这部分(LATE 截止前只涨了 2%,2026-01 的大涨不算,不进清单)。"""
    items = _client(tmp_path, snap).get("/rally").json()
    assert items and {it["symbol"] for it in items} == {"RALLY"}
    full = pd.read_pickle(snap / "RALLY.pkl")
    cut = full[full.index <= TRAIN_END]
    crossing = 0
    for it in items:
        for f in ("date", "peak_date", "view_start", "view_end"):
            assert it[f] <= TRAIN_END, it
        t = pd.Timestamp(it["date"])
        assert it["rise"] == pytest.approx(_expected_rise(cut, t), abs=1e-4)
        assert it["view_start"] < it["date"] <= it["peak_date"] <= it["view_end"]
        if cut.index.get_loc(t) + RALLY["horizon"] > len(cut) - 1:      # 观察期跨过了截止日
            crossing += 1
            assert it["view_end"] == TRAIN_END
            # 带上 2026 年的行情会算出大得多的涨幅:说明确实没读到截止后的部分
            assert _expected_rise(full, t) > it["rise"] + 0.5
    assert crossing > 0


def test_random_near_year_end_is_cut_not_padded(tmp_path):
    """spec 1.8:random 抽到 2025-11 附近的窗口,截到 2025-12-31,不往前补够根数。
    NOVL 只在 2025-11 进池(之前和之后收盘都高于价格上限)。"""
    d = tmp_path / "snap"
    d.mkdir()
    c = np.full(len(FULL), 25.0)
    i, j = FULL.searchsorted(pd.Timestamp("2025-11-03")), FULL.searchsorted(pd.Timestamp("2025-12-01"))
    c[i:j] = 5.0
    _write(d, "NOVL", c)
    write_manifest(d)
    client = _client(tmp_path, d)
    assert client.get("/pool").json()["symbols"] == ["NOVL"]
    dates = FULL[FULL <= TRAIN_END]
    half = DEFAULT_CONFIG["finder"]["random_window_bars"] // 2
    for seed in range(30):
        w = client.get("/random", params={"seed": seed}).json()
        assert w["symbol"] == "NOVL" and w["end"] == TRAIN_END
        n_bars = ((dates >= w["start"]) & (dates <= w["end"])).sum()
        assert n_bars < DEFAULT_CONFIG["finder"]["random_window_bars"]          # 截掉的不补
        anchor = dates[dates.searchsorted(pd.Timestamp(w["start"])) + half]     # 中心落在进池的 11 月
        assert pd.Timestamp("2025-11-03") <= anchor < pd.Timestamp("2025-12-01")


def test_all_routes_never_return_dates_after_train_end(tmp_path, snap):
    client = _client(tmp_path, snap)
    for it in client.get("/rally").json():
        assert max(it["date"], it["peak_date"], it["view_start"], it["view_end"]) <= TRAIN_END
    for seed in range(50):
        w = client.get("/random", params={"seed": seed}).json()
        assert w["start"] <= w["end"] <= TRAIN_END
    pool = client.get("/pool").json()
    assert set(pool["symbols"]) == {"RALLY", "LATE", "FLAT"} and pool["stock_days"] > 0


def test_random_without_seed_and_window_length(tmp_path, snap):
    client = _client(tmp_path, snap)
    w = client.get("/random").json()
    dates = FULL[FULL <= TRAIN_END]
    n_bars = ((dates >= w["start"]) & (dates <= w["end"])).sum()
    assert 1 <= n_bars <= DEFAULT_CONFIG["finder"]["random_window_bars"]


def test_units_warrants_and_registered_days_are_excluded(tmp_path):
    """同一段涨写进四只股票:SPAC 单位代码、认股权证代码不进池;ERRS 的涨被数据错误登记盖住,
    这段涨的股票日都不进池、不进清单;RALLY 照常进清单。"""
    d = tmp_path / "snap"
    d.mkdir()
    for s in ("RALLY", "SPCAU", "SPCAW", "ERRS"):
        _write(d, s, _ramp("2024-03-01", "2024-05-31"))
    write_manifest(d)
    (tmp_path / "data_errors.yaml").write_text(
        "entries:\n  - {symbol: ERRS, start: 2024-02-15, end: 2024-06-14, note: 合成的坏数据}\n")
    client = _client(tmp_path, d)
    pool = client.get("/pool").json()
    assert set(pool["symbols"]) == {"RALLY", "ERRS"}
    assert {it["symbol"] for it in client.get("/rally").json()} == {"RALLY"}

    settings = {**DEFAULT_CONFIG["finder"], "security_names_file": str(tmp_path / "names.csv"),
                "data_errors_file": str(tmp_path / "data_errors.yaml")}
    idx = finder_mod.Finder().index(d, segment=("2021-10-08", TRAIN_END), settings=settings,
                                    cache_dir=tmp_path / "c2")
    errs_days = idx.pool_date[idx.pool_sym == idx.symbols.index("ERRS")]
    before = DEFAULT_CONFIG["finder"]["pool"]["data_error_before_bars"]
    after = DEFAULT_CONFIG["finder"]["pool"]["data_error_after_bars"]
    lo = FULL[FULL.searchsorted(pd.Timestamp("2024-02-15")) - after]
    hi = FULL[FULL.searchsorted(pd.Timestamp("2024-06-14")) + before]
    hit = (errs_days >= np.datetime64(lo, "D")) & (errs_days <= np.datetime64(hi, "D"))
    assert not hit.any()
    assert len(errs_days) > 0                                   # 登记范围以外照常进池


def _cands(rows) -> pd.DataFrame:
    """(symbol, date, bar_idx, rel) → 候选表。"""
    df = pd.DataFrame(rows, columns=["symbol", "date", "bar_idx", "rel"])
    df["date"] = pd.to_datetime(df["date"])
    df["rise"] = df["rel"] / 10
    for c in ("peak_date", "view_start", "view_end"):
        df[c] = df["date"]
    return df


def test_same_move_taken_once():
    """同一只股票相隔不超过 suppress_bars 根的只取 rel 大的那段;隔得够远的照取;别的股票不受影响。"""
    gap = RALLY["suppress_bars"]
    rows = [("A", "2024-05-01", 100, 3.0), ("A", "2024-05-15", 100 + gap // 2, 2.5),
            ("A", "2024-06-03", 100 + gap + 1, 2.4), ("A", "2024-06-06", 100 + gap + 5, 2.2),
            ("B", "2024-05-15", 100 + gap // 2, 2.1)]
    sel = finder_mod.select_rally(_cands(rows), RALLY)
    assert sorted(zip(sel["symbol"], sel["bar_idx"])) == [("A", 100), ("A", 100 + gap + 1),
                                                            ("B", 100 + gap // 2)]


def test_weekly_cap_and_total_cap():
    per_week, top = RALLY["per_week_max"], RALLY["top"]
    same_week = [(f"S{i}", "2024-05-08", 100, 2.0 + i / 10) for i in range(per_week + 3)]
    sel = finder_mod.select_rally(_cands(same_week), RALLY)
    assert len(sel) == per_week
    assert sel["rel"].min() == pytest.approx(2.0 + 3 / 10)      # 留下的是 rel 大的那几段
    many = [(f"T{i}", str((pd.Timestamp("2022-01-03") + pd.Timedelta(weeks=i)).date()), 100, 2.0 + i / 1000)
            for i in range(top + 20)]
    sel = finder_mod.select_rally(_cands(many), {**RALLY, "top": 7})
    assert list(sel["symbol"]) == [f"T{i}" for i in range(top + 19, top + 12, -1)]
    assert list(sel["rel"]) == sorted(sel["rel"], reverse=True)


def test_rally_list_rows_are_unique_moves(tmp_path, snap):
    """真实流程里同一段涨也只出一行:清单里同一只股票的各段相隔超过 suppress_bars 根。"""
    items = _client(tmp_path, snap).get("/rally").json()
    dates = FULL[FULL <= TRAIN_END]
    for s in {it["symbol"] for it in items}:
        pos = sorted(dates.searchsorted(pd.Timestamp(it["date"])) for it in items if it["symbol"] == s)
        assert all(b - a > RALLY["suppress_bars"] for a, b in zip(pos, pos[1:]))


def _cache_files(tmp_path):
    return sorted((tmp_path / "outputs" / "finder").glob("finder-*.npz"))


def test_cache_recomputed_when_segment_or_fingerprint_changes(tmp_path, snap):
    client = _client(tmp_path, snap)
    first = client.get("/rally").json()
    [f1] = _cache_files(tmp_path)

    # 改训练段设置:起点挪到那段涨之后 → 键变、重算,RALLY 那段不再进清单
    cfg = client.get("/config").json()
    client.put("/config", json={**cfg, "train_segment": {"start": "2025-12-29", "end": TRAIN_END}})
    second = client.get("/rally").json()
    [f2] = _cache_files(tmp_path)
    assert f2 != f1 and first and second == []

    # 改回训练段、改副本内容(重写指纹清单)→ 键又变、重算
    client.put("/config", json=cfg)
    _write(snap, "FLAT", _ramp("2024-03-01", "2024-05-31"))
    write_manifest(snap)
    third = client.get("/rally").json()
    [f3] = _cache_files(tmp_path)
    assert f3 not in (f1, f2)
    assert {it["symbol"] for it in third} == {"RALLY", "FLAT"}


def test_cache_reused_across_processes_when_key_unchanged(tmp_path, snap, monkeypatch):
    first = _client(tmp_path, snap).get("/rally").json()
    monkeypatch.setattr(finder_mod, "build_index",
                        lambda *a, **k: pytest.fail("键没变不该重算"))
    again = _client(tmp_path, snap)                              # 新进程:内存里没有,读缓存文件
    assert again.get("/rally").json() == first
    assert again.get("/pool").json()["symbols"] == ["FLAT", "LATE", "RALLY"]


def test_missing_manifest_is_503(tmp_path):
    d = tmp_path / "snap"
    d.mkdir()
    _write(d, "FLAT", np.full(len(FULL), 5.0))
    for route in ("/pool", "/rally", "/random"):
        r = _client(tmp_path, d).get(route)
        assert r.status_code == 503 and "FINGERPRINT" in r.text, route


def test_bad_registry_or_segment_is_503(tmp_path, snap):
    (tmp_path / "data_errors.yaml").write_text("entries:\n  - {symbol: X}\n")
    assert _client(tmp_path, snap).get("/rally").status_code == 503
    (tmp_path / "data_errors.yaml").unlink()
    r = _client(tmp_path, snap, train_segment={"start": "2021-10-08", "end": "2026-01-30"}).get("/rally")
    assert r.status_code == 503


def test_random_on_empty_pool_is_404(tmp_path):
    d = tmp_path / "snap"
    d.mkdir()
    _write(d, "PRICY", np.full(len(FULL), 50.0))                   # 价格一直高于上限
    write_manifest(d)
    client = _client(tmp_path, d)
    assert client.get("/pool").json()["symbols"] == []
    assert client.get("/rally").json() == []
    assert client.get("/random").status_code == 404


def test_rally_labels_cut_at_stop_and_at_data_end():
    """拿得到的涨幅:第一次收盘 ≤ 止损线就截住(之后再涨不算);截止前不够 horizon 根时只看有的那几根。"""
    o = np.array([10.0, 10.0, 11.0, 7.0, 20.0, 20.0])
    h = o * 1.01
    c = o.copy()
    M = np.full(6, 0.04)
    lab = finder_mod.rally_labels(o, h, c, M, k=5.0, horizon=4)
    # t=0:P = 10,止损线 10/1.2 ≈ 8.33;t+3 收盘 7 跌破 → 截在 t+3,最高 11.11
    assert lab["valid"][0] and lab["rise"][0] == pytest.approx(11.0 * 1.01 / 10 - 1)
    assert lab["peak_off"][0] == 2
    # t=3:P = 20,只剩 2 根观察日,截在数据末根
    assert lab["valid"][3] and lab["rise"][3] == pytest.approx(0.01) and lab["end_off"][3] == 2
    assert not lab["valid"][5]                                    # 末根没有次日开盘价
