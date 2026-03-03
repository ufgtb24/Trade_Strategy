"""测试信号数据模型"""
import pytest
from datetime import date

from BreakoutStrategy.signals.models import SignalType, AbsoluteSignal, SignalStats


class TestSignalType:
    def test_signal_type_values(self):
        assert SignalType.BREAKOUT.value == "B"
        assert SignalType.HIGH_VOLUME.value == "V"
        assert SignalType.BIG_YANG.value == "Y"
        assert SignalType.DOUBLE_TROUGH.value == "D"


class TestAbsoluteSignal:
    def test_create_signal(self):
        signal = AbsoluteSignal(
            symbol="AAPL",
            date=date(2026, 1, 10),
            signal_type=SignalType.BREAKOUT,
            price=150.0,
        )
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BREAKOUT
        assert signal.strength == 1.0  # 默认值

    def test_signal_with_details(self):
        signal = AbsoluteSignal(
            symbol="AAPL",
            date=date(2026, 1, 10),
            signal_type=SignalType.HIGH_VOLUME,
            price=150.0,
            details={"volume_ratio": 4.5, "is_max_126d": True},
        )
        assert signal.details["volume_ratio"] == 4.5


class TestSignalStats:
    def test_create_stats(self):
        signals = [
            AbsoluteSignal("AAPL", date(2026, 1, 5), SignalType.BREAKOUT, 145.0),
            AbsoluteSignal("AAPL", date(2026, 1, 10), SignalType.HIGH_VOLUME, 150.0),
        ]
        stats = SignalStats(
            symbol="AAPL",
            signal_count=2,
            signals=signals,
            latest_signal_date=date(2026, 1, 10),
            latest_price=152.0,
        )
        assert stats.signal_count == 2
        assert len(stats.signals) == 2
