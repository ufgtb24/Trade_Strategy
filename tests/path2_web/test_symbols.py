"""按代码打开:股票列表路由 /symbols 与不带区间的 /ohlc。

- 股票列表 = 网页读行情的目录(训练段副本)里的 <代码>.pkl;不是 .pkl 的文件(副本的指纹清单等)、
  代码名不合格的文件都不算;
- /ohlc 不给 start / end → 这只股票截到训练段末日的全部 K 线;只给一个 → 400;
- 代码不合格 → 400,没有这只股票 → 404(沿用 data.check_symbol / read_bars)。
数据墙(最晚日期不晚于 2025-12-31、2026 年才上市的打不开)见 test_data_wall.py。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web import data as data_mod
from path2_web.app import create_app
from tests.path2_web.conftest import data_cfg


def _write_pkl(ddir, symbol: str, start="2024-01-02", end="2024-03-29") -> None:
    idx = pd.bdate_range(start, end, name="date")
    close = 10 + np.arange(len(idx)) * 0.01
    pd.DataFrame({"open": close, "high": close + 0.2, "low": close - 0.2, "close": close,
                  "volume": np.full(len(idx), 1e6)}, index=idx).to_pickle(ddir / f"{symbol}.pkl")


@pytest.fixture
def snap_dir(tmp_path):
    d = tmp_path / "snap"
    d.mkdir()
    for s in ["MSFT", "AAPL", "BRK-B"]:
        _write_pkl(d, s)
    (d / "FINGERPRINT.json").write_text("{}")          # 副本里的非 pkl 文件(如指纹清单)
    (d / "notes.txt").write_text("x")
    (d / "bad name.pkl").write_bytes(b"")               # 代码名不合格
    (d / ".hidden.pkl").write_bytes(b"")
    (d / "DIR.pkl").mkdir()                              # 不是文件
    return d


def _client(tmp_path, ddir) -> TestClient:
    return TestClient(create_app(config_override=data_cfg(ddir), outputs_root=str(tmp_path / "outputs"),
                                 use_thread_pool=True))


def test_list_symbols_only_pkl_files_with_valid_names(snap_dir):
    assert data_mod.list_symbols(snap_dir) == ["AAPL", "BRK-B", "MSFT"]


def test_symbols_route(tmp_path, snap_dir):
    r = _client(tmp_path, snap_dir).get("/symbols")
    assert r.status_code == 200, r.text
    assert r.json() == ["AAPL", "BRK-B", "MSFT"]


def test_symbols_route_missing_dir_is_503(tmp_path):
    assert _client(tmp_path, tmp_path / "no_such_dir").get("/symbols").status_code == 503


def test_every_listed_symbol_opens_without_window(tmp_path, snap_dir):
    c = _client(tmp_path, snap_dir)
    for s in c.get("/symbols").json():
        r = c.get("/ohlc", params={"symbol": s})
        assert r.status_code == 200, (s, r.text)
        bars = r.json()["bars"]
        assert r.json()["symbol"] == s
        assert bars[0]["date"] == "2024-01-02" and bars[-1]["date"] == "2024-03-29"
        assert set(bars[0]) == {"date", "o", "h", "l", "c", "v", "rv"}


def test_ohlc_without_window_bad_or_missing_symbol(tmp_path, snap_dir):
    c = _client(tmp_path, snap_dir)
    for bad in ["../snap/AAPL", "a b", "..", "X" * 16]:
        assert c.get("/ohlc", params={"symbol": bad}).status_code == 400, bad
    assert c.get("/ohlc", params={"symbol": "NOPE"}).status_code == 404
    assert c.get("/ohlc", params={"symbol": "aapl"}).status_code == 404     # 代码区分大小写


def test_ohlc_one_sided_window_is_400(tmp_path, snap_dir):
    c = _client(tmp_path, snap_dir)
    assert c.get("/ohlc", params={"symbol": "AAPL", "start": "2024-01-02"}).status_code == 400
    assert c.get("/ohlc", params={"symbol": "AAPL", "end": "2024-01-02"}).status_code == 400


def test_ohlc_with_window_unchanged(tmp_path, snap_dir):
    r = _client(tmp_path, snap_dir).get("/ohlc", params={"symbol": "AAPL", "start": "2024-02-01",
                                                          "end": "2024-02-29"})
    dates = [b["date"] for b in r.json()["bars"]]
    assert dates[0] == "2024-02-01" and dates[-1] == "2024-02-29"
