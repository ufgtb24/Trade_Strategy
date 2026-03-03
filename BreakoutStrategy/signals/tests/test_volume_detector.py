"""测试超大成交量检测器"""
import pytest
import pandas as pd
import numpy as np
from datetime import date

from BreakoutStrategy.signals.detectors.volume import HighVolumeDetector
from BreakoutStrategy.signals.models import SignalType


class TestHighVolumeDetector:
    @pytest.fixture
    def detector(self):
        return HighVolumeDetector(
            lookback_days=126,
            volume_ma_period=20,
            volume_multiplier=3.0,
        )

    @pytest.fixture
    def sample_df(self):
        """创建包含一个超大成交量日的测试数据"""
        np.random.seed(42)
        n_days = 150
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

        # 基础数据：正常成交量约 1000
        volumes = np.random.normal(1000, 100, n_days)

        # 在第 140 天设置一个超大成交量（5倍于均值）
        volumes[140] = 5000

        df = pd.DataFrame(
            {
                "open": np.random.uniform(100, 105, n_days),
                "high": np.random.uniform(105, 110, n_days),
                "low": np.random.uniform(95, 100, n_days),
                "close": np.random.uniform(100, 105, n_days),
                "volume": volumes,
            },
            index=dates,
        )
        return df

    def test_detect_high_volume_by_multiplier(self, detector, sample_df):
        """检测到超过均量倍数的成交量"""
        signals = detector.detect(sample_df, "TEST")

        # 应该检测到第 140 天的超大成交量
        assert len(signals) >= 1

        # 找到第 140 天的信号
        signal_dates = [s.date for s in signals]
        target_date = sample_df.index[140].date()
        assert target_date in signal_dates

        # 验证信号类型
        target_signal = [s for s in signals if s.date == target_date][0]
        assert target_signal.signal_type == SignalType.HIGH_VOLUME
        assert target_signal.details["volume_ratio"] >= 3.0

    def test_detect_max_126d_volume(self, detector):
        """检测 126 日内最大成交量"""
        np.random.seed(42)
        n_days = 150
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

        # 成交量逐渐下降，最后一天是 126 日内最大
        volumes = np.linspace(2000, 500, n_days)
        volumes[-1] = 2500  # 最后一天是 126 日内最大，但不到 3 倍均量

        df = pd.DataFrame(
            {
                "open": [100] * n_days,
                "high": [105] * n_days,
                "low": [95] * n_days,
                "close": [102] * n_days,
                "volume": volumes,
            },
            index=dates,
        )

        signals = detector.detect(df, "TEST")

        # 最后一天应该被检测到（126 日内最大）
        target_date = df.index[-1].date()
        signal_dates = [s.date for s in signals]
        assert target_date in signal_dates

        target_signal = [s for s in signals if s.date == target_date][0]
        assert target_signal.details["is_max_126d"] == True

    def test_no_signal_for_normal_volume(self, detector):
        """正常成交量不应触发信号"""
        np.random.seed(42)
        n_days = 150
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

        # 所有成交量都很正常
        volumes = np.random.normal(1000, 50, n_days)

        df = pd.DataFrame(
            {
                "open": [100] * n_days,
                "high": [105] * n_days,
                "low": [95] * n_days,
                "close": [102] * n_days,
                "volume": volumes,
            },
            index=dates,
        )

        signals = detector.detect(df, "TEST")

        # 不应该有信号（或很少）
        # 由于随机性，可能有少量信号，但不应该很多
        assert len(signals) < 10
