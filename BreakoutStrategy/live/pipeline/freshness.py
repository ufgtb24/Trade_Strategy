"""数据新鲜度检查。

使用 pandas_market_calendars 的 NYSE 日历自动处理周末/节假日/半日交易，
判断本地 PKL 数据是否覆盖了所有已收盘的交易日。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import logging

import pandas_market_calendars as mcal

logger = logging.getLogger(__name__)

# 与 daily_runner.DOWNLOAD_MARKER_FILENAME 保持一致。
# 不 import 以避免模块耦合（daily_runner 是 freshness 的下游消费者）。
_DOWNLOAD_MARKER_FILENAME = ".last_full_update"


@dataclass
class FreshnessStatus:
    is_fresh: bool
    newest_local_date: str | None              # "YYYY-MM-DD" or None
    missing_trading_days: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.is_fresh:
            return f"Fresh (up to {self.newest_local_date})"
        n = len(self.missing_trading_days)
        return f"Stale: {n} trading day(s) missing"


class DataFreshnessChecker:
    """检查本地 PKL 数据是否覆盖到最近一个已收盘的 NYSE 交易日。"""

    def __init__(
        self,
        data_dir: Path,
        market_timezone: str = "America/New_York",
    ):
        self.data_dir = Path(data_dir)
        self.tz = ZoneInfo(market_timezone)
        self.calendar = mcal.get_calendar("NYSE")

    def check(self) -> FreshnessStatus:
        newest = self._newest_local_data_date()
        missing = self._missing_trading_days(newest)
        return FreshnessStatus(
            is_fresh=(len(missing) == 0),
            newest_local_date=newest,
            missing_trading_days=missing,
        )

    def _newest_local_data_date(self) -> str | None:
        """返回本地数据最新日期（ISO YYYY-MM-DD），无 marker 返回 None。

        依赖 DailyPipeline._step1_download_data 成功完成时写入的
        data_dir/.last_full_update marker 文件。marker 不存在或读取
        失败时返回 None，触发 UI 的"数据陈旧"流程。
        """
        marker = self.data_dir / _DOWNLOAD_MARKER_FILENAME
        if not marker.exists():
            return None
        try:
            content = marker.read_text(encoding="utf-8").strip()
            return content or None
        except OSError as e:
            logger.warning("Failed to read marker %s: %s", marker, e)
            return None

    def _missing_trading_days(self, newest_local: str | None) -> list[str]:
        """返回 (newest_local, now] 区间内已收盘但未覆盖的交易日。"""
        now_et = datetime.now(self.tz)
        today = now_et.date()

        if newest_local is None:
            start = today - timedelta(days=365)
        else:
            start = datetime.strptime(newest_local, "%Y-%m-%d").date() + timedelta(days=1)

        if start > today:
            return []

        schedule = self.calendar.schedule(
            start_date=start.isoformat(),
            end_date=today.isoformat(),
        )

        missing: list[str] = []
        for ts, row in schedule.iterrows():
            trading_date = ts.date()
            market_close = row["market_close"].tz_convert(self.tz).to_pydatetime()
            if now_et >= market_close:
                missing.append(trading_date.isoformat())
        return missing
