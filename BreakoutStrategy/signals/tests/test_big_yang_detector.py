"""测试大阳线检测器"""
import pytest
import pandas as pd
import numpy as np
from datetime import date

from BreakoutStrategy.signals.detectors.big_yang import BigYangDetector
from BreakoutStrategy.signals.models import SignalType


class TestBigYangDetector:
    @pytest.fixture
    def detector(self):
        return BigYangDetector(
            volatility_lookback=252,
            sigma_threshold=2.5,
        )

    @pytest.fixture
    def sample_df(self):
        """创建包含一个大阳线的测试数据"""
        np.random.seed(42)
        n_days = 300
        dates = pd.date_range("2025-01-01", periods=n_days, freq="B")

        # 基础价格序列，日收益率约 1%（年化波动率约 16%）
        returns = np.random.normal(0.0005, 0.01, n_days)
        prices = 100 * np.cumprod(1 + returns)

        opens = prices * (1 - np.random.uniform(0, 0.005, n_days))
        closes = prices
        highs = np.maximum(opens, closes) * (1 + np.random.uniform(0, 0.01, n_days))
        lows = np.minimum(opens, closes) * (1 - np.random.uniform(0, 0.01, n_days))

        # 在第 280 天创建一个大阳线（涨幅约 5%，远超 2.5 sigma）
        opens[280] = prices[280] * 0.98
        closes[280] = prices[280] * 1.03  # 日内涨幅约 5%

        df = pd.DataFrame(
            {
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": np.random.uniform(1000, 2000, n_days),
            },
            index=dates,
        )
        return df

    def test_detect_big_yang(self, detector, sample_df):
        """检测大阳线"""
        signals = detector.detect(sample_df, "TEST")

        # 应该检测到第 280 天的大阳线
        target_date = sample_df.index[280].date()
        signal_dates = [s.date for s in signals]
        assert target_date in signal_dates

        target_signal = [s for s in signals if s.date == target_date][0]
        assert target_signal.signal_type == SignalType.BIG_YANG
        assert target_signal.details["sigma"] >= 2.5

    def test_no_signal_for_normal_days(self, detector):
        """正常交易日不应触发信号"""
        np.random.seed(42)
        n_days = 300
        dates = pd.date_range("2025-01-01", periods=n_days, freq="B")

        # 所有日内涨跌幅都很小
        opens = np.full(n_days, 100.0)
        closes = opens * (1 + np.random.uniform(-0.005, 0.005, n_days))

        df = pd.DataFrame(
            {
                "open": opens,
                "high": closes * 1.005,
                "low": opens * 0.995,
                "close": closes,
                "volume": np.random.uniform(1000, 2000, n_days),
            },
            index=dates,
        )

        signals = detector.detect(df, "TEST")

        # 不应该有信号
        assert len(signals) == 0

    def test_requires_positive_change(self, detector):
        """只检测阳线，不检测阴线"""
        np.random.seed(42)
        n_days = 300
        dates = pd.date_range("2025-01-01", periods=n_days, freq="B")

        opens = np.full(n_days, 100.0)
        closes = opens.copy()

        # 创建一个大阴线（跌幅 5%）
        opens[280] = 105
        closes[280] = 100

        df = pd.DataFrame(
            {
                "open": opens,
                "high": opens * 1.01,
                "low": closes * 0.99,
                "close": closes,
                "volume": np.random.uniform(1000, 2000, n_days),
            },
            index=dates,
        )

        signals = detector.detect(df, "TEST")

        # 大阴线不应该被检测
        target_date = df.index[280].date()
        signal_dates = [s.date for s in signals]
        assert target_date not in signal_dates
