"""测试低谷检测器"""
import pytest
import pandas as pd
import numpy as np

from BreakoutStrategy.signals.detectors.trough import TroughDetector, Trough


class TestTroughDetector:
    @pytest.fixture
    def detector(self):
        return TroughDetector(window=10, min_side_bars=3)

    @pytest.fixture
    def v_shape_df(self):
        """创建 V 形走势数据"""
        # 价格从 100 下跌到 80，然后回升到 95
        n_days = 60
        dates = pd.date_range("2025-10-01", periods=n_days, freq="B")

        # V 形价格走势
        prices = np.concatenate([
            np.linspace(100, 80, 20),   # 下跌
            np.linspace(80, 75, 10),    # 底部震荡
            np.linspace(75, 95, 30),    # 回升
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

    def test_detect_troughs(self, detector, v_shape_df):
        """检测到 V 形底部的低谷"""
        troughs = detector.detect_troughs(v_shape_df)

        # 应该检测到至少一个低谷（在底部区域）
        assert len(troughs) >= 1

        # 最低的低谷应该在底部区域（索引约 20-30）
        lowest_trough = min(troughs, key=lambda t: t.price)
        assert 15 <= lowest_trough.index <= 35

    def test_trough_is_local_minimum(self, detector):
        """低谷是局部最低点"""
        # 创建一个清晰的局部低点
        n_days = 30
        dates = pd.date_range("2025-10-01", periods=n_days, freq="B")

        prices = np.array([100] * 10 + [90] * 1 + [100] * 19)  # 第 10 天是低点

        df = pd.DataFrame(
            {
                "open": prices,
                "high": prices * 1.01,
                "low": prices * 0.99,
                "close": prices,
                "volume": [1000] * n_days,
            },
            index=dates,
        )

        troughs = detector.detect_troughs(df)

        # 应该检测到第 10 天的低谷
        trough_indices = [t.index for t in troughs]
        assert 10 in trough_indices

    def test_different_parameters(self):
        """不同参数的检测器"""
        # 严格参数
        strict_detector = TroughDetector(window=10, min_side_bars=3)
        # 宽松参数
        loose_detector = TroughDetector(window=6, min_side_bars=2)

        n_days = 50
        dates = pd.date_range("2025-10-01", periods=n_days, freq="B")
        prices = np.sin(np.linspace(0, 4 * np.pi, n_days)) * 10 + 100

        df = pd.DataFrame(
            {
                "open": prices,
                "high": prices * 1.01,
                "low": prices * 0.99,
                "close": prices,
                "volume": [1000] * n_days,
            },
            index=dates,
        )

        strict_troughs = strict_detector.detect_troughs(df)
        loose_troughs = loose_detector.detect_troughs(df)

        # 宽松参数应该检测到更多或相同数量的低谷
        assert len(loose_troughs) >= len(strict_troughs)
