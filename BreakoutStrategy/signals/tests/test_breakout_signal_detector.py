"""测试突破信号检测器（适配器）"""
import pytest
import pandas as pd
import numpy as np
from datetime import date

from BreakoutStrategy.signals.detectors.breakout import BreakoutSignalDetector
from BreakoutStrategy.signals.models import SignalType


class TestBreakoutSignalDetector:
    @pytest.fixture
    def detector(self):
        return BreakoutSignalDetector()

    @pytest.fixture
    def breakout_df(self):
        """创建包含突破的测试数据"""
        n_days = 100
        dates = pd.date_range("2025-08-01", periods=n_days, freq="B")

        # 先上涨形成高点，然后回调，再突破
        prices = np.concatenate([
            np.linspace(100, 120, 30),   # 上涨到高点
            np.linspace(120, 105, 30),   # 回调
            np.linspace(105, 130, 40),   # 突破新高
        ])

        df = pd.DataFrame(
            {
                "open": prices * 0.99,
                "high": prices * 1.01,
                "low": prices * 0.98,
                "close": prices,
                "volume": np.random.uniform(1000, 2000, n_days),
            },
            index=dates,
        )
        return df

    def test_detect_breakout(self, detector, breakout_df):
        """检测突破信号"""
        signals = detector.detect(breakout_df, "TEST")

        # 应该检测到突破信号
        assert len(signals) >= 1

        # 信号类型应该是 BREAKOUT
        assert all(s.signal_type == SignalType.BREAKOUT for s in signals)

    def test_signal_contains_pk_num(self, detector, breakout_df):
        """信号应包含 pk_num"""
        signals = detector.detect(breakout_df, "TEST")

        if signals:
            for signal in signals:
                assert "pk_num" in signal.details
                assert signal.details["pk_num"] >= 1
