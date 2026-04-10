"""Test DataFreshnessChecker with mocked datetime."""
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from BreakoutStrategy.live.pipeline.freshness import (
    DataFreshnessChecker,
    FreshnessStatus,
)


def _make_fake_pkl(path: Path, last_date: str):
    """生成一个只有若干行的 PKL 文件，index 最大值为 last_date。"""
    dates = pd.date_range(end=last_date, periods=5, freq="B")
    df = pd.DataFrame({
        "open": [1.0] * len(dates),
        "high": [1.1] * len(dates),
        "low": [0.9] * len(dates),
        "close": [1.0] * len(dates),
        "volume": [100] * len(dates),
    }, index=dates)
    df.to_pickle(path)


@pytest.fixture
def fake_data_dir(tmp_path: Path):
    """建一个临时 data_dir，内含 3 个 fake PKL。"""
    (tmp_path / "AAA.pkl").touch()
    _make_fake_pkl(tmp_path / "AAA.pkl", "2026-04-07")
    _make_fake_pkl(tmp_path / "BBB.pkl", "2026-04-07")
    _make_fake_pkl(tmp_path / "CCC.pkl", "2026-04-07")
    return tmp_path


def _mock_now(fake_now: datetime):
    """patch datetime.now() in freshness module."""
    from BreakoutStrategy.live.pipeline import freshness

    class _MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now

    return patch.object(freshness, "datetime", _MockDatetime)


def test_fresh_when_newest_covers_last_closed_trading_day(fake_data_dir):
    """本地数据到 2026-04-07 (周二)，当前时间 2026-04-08 08:00 ET (盘前)
    → 上一个已收盘日是 2026-04-07 → 已覆盖 → fresh。"""
    tz = ZoneInfo("America/New_York")
    fake_now = datetime(2026, 4, 8, 8, 0, tzinfo=tz)
    with _mock_now(fake_now):
        checker = DataFreshnessChecker(fake_data_dir)
        status = checker.check()
    assert status.is_fresh, f"Expected fresh, missing={status.missing_trading_days}"
    assert status.newest_local_date == "2026-04-07"


def test_stale_when_trading_day_closed_not_covered(fake_data_dir):
    """本地数据到 2026-04-07，当前时间 2026-04-09 17:00 ET (盘后)
    → 2026-04-08 和 2026-04-09 都已收盘但未覆盖 → stale。"""
    tz = ZoneInfo("America/New_York")
    fake_now = datetime(2026, 4, 9, 17, 0, tzinfo=tz)
    with _mock_now(fake_now):
        checker = DataFreshnessChecker(fake_data_dir)
        status = checker.check()
    assert not status.is_fresh
    assert "2026-04-08" in status.missing_trading_days
    assert "2026-04-09" in status.missing_trading_days


def test_fresh_on_saturday_when_friday_covered(fake_data_dir):
    """本地数据到 2026-04-10 (周五)，当前时间 2026-04-11 周六 → 无新交易日 → fresh。"""
    # 先重建数据到周五
    for sym in ("AAA", "BBB", "CCC"):
        _make_fake_pkl(fake_data_dir / f"{sym}.pkl", "2026-04-10")

    tz = ZoneInfo("America/New_York")
    fake_now = datetime(2026, 4, 11, 10, 0, tzinfo=tz)  # Saturday
    with _mock_now(fake_now):
        checker = DataFreshnessChecker(fake_data_dir)
        status = checker.check()
    assert status.is_fresh


def test_no_local_data_reports_stale(tmp_path: Path):
    """data_dir 没有任何 PKL → newest_local_date=None, is_fresh=False。"""
    tz = ZoneInfo("America/New_York")
    fake_now = datetime(2026, 4, 9, 17, 0, tzinfo=tz)
    with _mock_now(fake_now):
        checker = DataFreshnessChecker(tmp_path)
        status = checker.check()
    assert not status.is_fresh
    assert status.newest_local_date is None
