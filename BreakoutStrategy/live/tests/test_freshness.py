"""Test DataFreshnessChecker with mocked datetime."""
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from BreakoutStrategy.live.pipeline.freshness import (
    DataFreshnessChecker,
    FreshnessStatus,
)


def _write_marker(data_dir: Path, iso_date: str) -> None:
    (data_dir / ".last_full_update").write_text(iso_date, encoding="utf-8")


def _mock_now(fake_now: datetime):
    """patch datetime.now() in freshness module."""
    from BreakoutStrategy.live.pipeline import freshness

    class _MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now

    return patch.object(freshness, "datetime", _MockDatetime)


def test_fresh_when_marker_covers_last_closed_trading_day(tmp_path: Path):
    """marker=2026-04-07，当前时间 2026-04-08 08:00 ET（盘前）
    → 上一个已收盘日是 2026-04-07 → 已覆盖 → fresh。"""
    _write_marker(tmp_path, "2026-04-07")

    tz = ZoneInfo("America/New_York")
    fake_now = datetime(2026, 4, 8, 8, 0, tzinfo=tz)
    with _mock_now(fake_now):
        checker = DataFreshnessChecker(tmp_path)
        status = checker.check()

    assert status.is_fresh, f"Expected fresh, missing={status.missing_trading_days}"
    assert status.newest_local_date == "2026-04-07"


def test_stale_when_marker_is_old(tmp_path: Path):
    """marker=2026-04-07，当前时间 2026-04-09 17:00 ET（盘后）
    → 2026-04-08 和 2026-04-09 都已收盘但未覆盖 → stale。"""
    _write_marker(tmp_path, "2026-04-07")

    tz = ZoneInfo("America/New_York")
    fake_now = datetime(2026, 4, 9, 17, 0, tzinfo=tz)
    with _mock_now(fake_now):
        checker = DataFreshnessChecker(tmp_path)
        status = checker.check()

    assert not status.is_fresh
    assert status.newest_local_date == "2026-04-07"
    assert "2026-04-08" in status.missing_trading_days
    assert "2026-04-09" in status.missing_trading_days


def test_fresh_on_saturday_when_marker_covers_friday(tmp_path: Path):
    """marker=2026-04-10（周五），当前时间 2026-04-11 周六 10:00 ET
    → 无新交易日 → fresh。"""
    _write_marker(tmp_path, "2026-04-10")

    tz = ZoneInfo("America/New_York")
    fake_now = datetime(2026, 4, 11, 10, 0, tzinfo=tz)  # Saturday
    with _mock_now(fake_now):
        checker = DataFreshnessChecker(tmp_path)
        status = checker.check()

    assert status.is_fresh


def test_no_marker_returns_stale(tmp_path: Path):
    """无 marker 文件 → newest_local_date=None, is_fresh=False。"""
    tz = ZoneInfo("America/New_York")
    fake_now = datetime(2026, 4, 9, 17, 0, tzinfo=tz)
    with _mock_now(fake_now):
        checker = DataFreshnessChecker(tmp_path)
        status = checker.check()

    assert not status.is_fresh
    assert status.newest_local_date is None


def test_corrupt_marker_returns_stale(tmp_path: Path):
    """marker 文件是空内容 → newest_local_date=None, is_fresh=False。

    注意：完全空文件的 .strip() 返回空字符串，should be treated as None
    so the "no data" code path kicks in.
    """
    (tmp_path / ".last_full_update").write_text("", encoding="utf-8")

    tz = ZoneInfo("America/New_York")
    fake_now = datetime(2026, 4, 9, 17, 0, tzinfo=tz)
    with _mock_now(fake_now):
        checker = DataFreshnessChecker(tmp_path)
        status = checker.check()

    assert not status.is_fresh
    assert status.newest_local_date is None
