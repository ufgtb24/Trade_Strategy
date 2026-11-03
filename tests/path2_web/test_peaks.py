"""参照层 peaks:路由 /peaks 与 path2_web/peaks.py 的 peak_lines。

- 每个峰一条线 {date, price, end}:date 是峰那根 K 线,price 是峰登记时的价,end 是第一次被突破的那根,
  没被突破的画到最后一根;
- 数据墙:只用截到 2025-12-31 的行情算。合成股票在 2026 年涨得更高:截止前几天的峰要 2026 年的 K 线才确认、
  2026 年的高点、截止前的峰在 2026 年才被突破,这三样都不能从路由里漏出来;
- 代码不合格 → 400,没有这只股票、2026 年才上市 → 404(同 /ohlc 不给区间)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app
from path2_web.peaks import peak_lines
from tests.path2_web.conftest import TRAIN_END, data_cfg


def _ramp(a: float, b: float, n: int) -> list[float]:
    return list(np.linspace(a, b, n + 1)[1:])


def _rising_after_cutoff() -> pd.DataFrame:
    """2025-01-02～2026-03-31 的合成股票(工作日,index 名 date,与真实 pkl 同形),收盘价分段:
    平 10 → 峰 1(13)→ 回 10 → 越过峰 1 涨到峰 2(15)→ 回 10 → 2025-12-23 的峰 3(12.5)→
    2026 年涨到 20 并停在那里。最高价 = 收盘 + 0.05。"""
    idx = pd.bdate_range("2025-01-02", "2026-03-31", name="date")
    c = [10.0] * 40 + _ramp(10, 13, 10) + _ramp(13, 10, 10) + [10.0] * 30
    c += _ramp(10, 15, 12) + _ramp(15, 10, 12)
    c += [10.0] * (idx.get_loc(pd.Timestamp("2025-12-24")) - len(c) - 8)
    c += _ramp(10, 12.5, 8) + _ramp(12.5, 10, 6) + _ramp(10, 20, 10)
    c = np.array(c + [20.0] * (len(idx) - len(c)))
    return pd.DataFrame({"open": c, "high": c + 0.05, "low": c - 0.05, "close": c,
                         "volume": np.full(len(c), 1e6)}, index=idx)


# 截到 2025-12-31 时该有的峰:峰 1 在峰 2 那段涨里被突破,峰 2 到截止还没被突破,画到最后一根
EXPECTED = [{"date": "2025-03-12", "price": 13.05, "end": "2025-05-19"},
            {"date": "2025-05-23", "price": 15.05, "end": TRAIN_END}]


@pytest.fixture
def snap_dir(tmp_path):
    d = tmp_path / "snap"
    d.mkdir()
    _rising_after_cutoff().to_pickle(d / "RISE.pkl")
    late = _rising_after_cutoff().loc["2026-01-02":]               # 2026 年才上市
    late.to_pickle(d / "LATE.pkl")
    return d


def _client(tmp_path, ddir) -> TestClient:
    return TestClient(create_app(config_override=data_cfg(ddir), outputs_root=str(tmp_path / "outputs"),
                                 use_thread_pool=True))


def test_peak_lines_start_at_peak_bar_and_end_at_first_break():
    df = _rising_after_cutoff().loc[:TRAIN_END]
    lines = peak_lines(df)
    assert lines == EXPECTED
    first = lines[0]
    # 峰价 = 峰那根的最高价;线停在第一根最高价越过它(加 BODetector 默认的 0.3% 溢价)的 K 线
    assert first["price"] == pytest.approx(df.loc[first["date"], "high"])
    after = df.loc[first["date"]:].iloc[1:]
    assert after.index[after["high"] > first["price"] * 1.003][0] == pd.Timestamp(first["end"])


def test_peak_lines_empty():
    assert peak_lines(_rising_after_cutoff().iloc[:0]) == []


def test_route_uses_only_data_until_train_end(tmp_path, snap_dir):
    r = _client(tmp_path, snap_dir).get("/peaks", params={"symbol": "RISE"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got == EXPECTED
    assert all(p["date"] <= TRAIN_END and p["end"] <= TRAIN_END for p in got)
    # 对照:同一只股票拿完整行情算,三样截止之后才有的东西都在,路由里一样都没有
    full = peak_lines(_rising_after_cutoff())
    assert {"date": "2025-12-23", "price": 12.55} in [{k: p[k] for k in ("date", "price")} for p in full]
    assert max(p["price"] for p in full) == pytest.approx(20.05)
    assert [p["end"] for p in full if p["date"] == "2025-05-23"][0] > TRAIN_END
    assert "2025-12-23" not in [p["date"] for p in got]
    assert max(p["price"] for p in got) < 20


def test_route_bad_symbol_is_400_missing_is_404(tmp_path, snap_dir):
    c = _client(tmp_path, snap_dir)
    assert c.get("/peaks", params={"symbol": "../RISE"}).status_code == 400
    assert c.get("/peaks", params={"symbol": "NOPE"}).status_code == 404
    assert c.get("/peaks", params={"symbol": "LATE"}).status_code == 404       # 2026 年才上市
