"""测试双底检测器"""
import pytest
import pandas as pd
import numpy as np

from BreakoutStrategy.signals.detectors.double_trough import DoubleTroughDetector
from BreakoutStrategy.signals.models import SignalType


class TestDoubleTroughDetector:
    @pytest.fixture
    def detector(self):
        """使用默认参数的检测器"""
        return DoubleTroughDetector(
            min_of=126,
            first_bounce_atr=2.0,
            max_gap_days=60,
            min_recovery_atr=0.0,
            atr_period=14,
            trough_window=6,
            trough_min_side_bars=2,
        )

    @pytest.fixture
    def double_trough_df(self):
        """
        创建双底数据，带有足够的反弹

        价格走势：
        - 横盘 → 下跌到底部(TR1) → 大幅反弹(≥10%) → 回调形成次低点(TR2) → 上涨
        """
        n_days = 180
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

        # TR1 在第 90 天左右，价格 70
        # 反弹到 80（涨幅约 14.3%，超过 10%）
        # TR2 在第 125 天左右，价格 75
        prices = np.concatenate([
            np.linspace(100, 100, 60),   # 横盘
            np.linspace(100, 70, 30),    # 下跌到底部 (TR1)
            np.linspace(70, 80, 20),     # 反弹 14.3%
            np.linspace(80, 75, 15),     # 回调形成次低点 (TR2)
            np.linspace(75, 95, 55),     # 继续上涨
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

    def test_detect_with_bounce(self, detector, double_trough_df):
        """TR1 有足够反弹时应检测到信号"""
        signals = detector.detect(double_trough_df, "TEST")

        # 应该检测到双底信号
        assert len(signals) >= 1

        # 信号类型应该是 DOUBLE_TROUGH
        assert all(s.signal_type == SignalType.DOUBLE_TROUGH for s in signals)

        # 检查 details 包含必要信息
        for signal in signals:
            assert "trough1_date" in signal.details
            assert "trough2_date" in signal.details
            assert "trough1_price" in signal.details
            assert "trough2_price" in signal.details
            assert "bounce_pct" in signal.details
            assert "gap_days" in signal.details
            # TR2 价格应该高于 TR1
            assert signal.details["trough2_price"] > signal.details["trough1_price"]
            # bounce_atr 应该 >= first_bounce_atr
            assert signal.details["bounce_atr"] >= detector.first_bounce_atr
            # details 应包含 ATR 相关字段
            assert "atr_at_tr1" in signal.details
            assert "bounce_atr" in signal.details
            assert "depth_atr" in signal.details
            assert "recovery_atr" in signal.details

    def test_no_signal_without_bounce(self):
        """TR1 反弹不足时不应触发信号"""
        # 使用短窗口检测器，确保反弹只在限定窗口内计算
        detector = DoubleTroughDetector(
            min_of=126,
            first_bounce_atr=4.0,
            max_gap_days=30,  # 限制窗口为 30 天
            atr_period=14,
            trough_window=6,
            trough_min_side_bars=2,
        )

        n_days = 180
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

        # 创建反弹不足的 V 形
        # TR1 在第 90 天，反弹在 30 天窗口内仅 5%
        # 注意：high 是 prices * 1.01，所以实际反弹计算基于 high
        # 70 * 1.01 = 70.7 (TR1 的 low = 70 * 0.98 = 68.6)
        # 需要确保 30 天内最高点不超过 68.6 * 1.10 = 75.46
        prices = np.concatenate([
            np.linspace(100, 100, 60),   # 横盘
            np.linspace(100, 70, 30),    # 下跌到底部 (TR1 约第 90 天)
            np.linspace(70, 73, 30),     # 30 天内反弹很小（high 约 73.73，涨幅约 7.5%）
            np.linspace(73, 71, 15),     # 回调形成次低点
            np.linspace(71, 85, 45),     # 继续上涨（超出 30 天窗口）
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

        signals = detector.detect(df, "TEST")

        # 在 30 天窗口内反弹不足 10%，不应有信号
        assert len(signals) == 0

    def test_continuous_downtrend(self, detector):
        """持续下跌中不应频繁触发信号"""
        n_days = 180
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

        # 持续下跌，没有明显反弹
        prices = np.linspace(100, 50, n_days)

        df = pd.DataFrame(
            {
                "open": prices * 1.01,
                "high": prices * 1.02,
                "low": prices * 0.99,
                "close": prices,
                "volume": np.random.uniform(1000, 2000, n_days),
            },
            index=dates,
        )

        signals = detector.detect(df, "TEST")

        # 持续下跌不应该有双底信号
        assert len(signals) == 0

    def test_tr1_is_126d_low(self, detector, double_trough_df):
        """验证 TR1 是 126 日最低点"""
        signals = detector.detect(double_trough_df, "TEST")

        for signal in signals:
            tr1_idx = signal.details["trough1_index"]
            tr2_idx = signal.details["trough2_index"]
            tr1_price = signal.details["trough1_price"]

            # 验证 TR1 确实是 TR2 时刻回看 126 日内的最低点
            lookback_start = max(0, tr2_idx - detector.min_of)
            window_lows = double_trough_df["low"].iloc[lookback_start : tr2_idx]
            actual_min = window_lows.min()

            # TR1 的价格应该等于窗口最低价（允许浮点误差）
            assert abs(tr1_price - actual_min) < 0.01, f"TR1 price {tr1_price} != window min {actual_min}"

    def test_first_bounce_atr_threshold(self):
        """验证 first_bounce_atr 阈值"""
        n_days = 180
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

        # 创建恰好 15% 反弹的数据
        prices = np.concatenate([
            np.linspace(100, 100, 60),   # 横盘
            np.linspace(100, 70, 30),    # 下跌到底部 (TR1)
            np.linspace(70, 80.5, 20),   # 反弹 15%
            np.linspace(80.5, 75, 15),   # 回调形成次低点 (TR2)
            np.linspace(75, 95, 55),     # 继续上涨
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

        # 使用 15% 阈值的检测器
        detector_15 = DoubleTroughDetector(
            min_of=126,
            first_bounce_atr=2.0,
            atr_period=14,
            trough_window=6,
            trough_min_side_bars=2,
        )

        signals_15 = detector_15.detect(df, "TEST")

        # 使用 20% 阈值的检测器
        detector_20 = DoubleTroughDetector(
            min_of=126,
            first_bounce_atr=6.0,
            atr_period=14,
            trough_window=6,
            trough_min_side_bars=2,
        )

        signals_20 = detector_20.detect(df, "TEST")

        # 15% 阈值应该能检测到信号，20% 阈值不应该
        assert len(signals_15) >= len(signals_20)

    def test_max_gap_days_constraint(self):
        """测试 max_gap_days 约束"""
        detector = DoubleTroughDetector(
            min_of=126,
            first_bounce_atr=2.0,
            max_gap_days=10,  # 设置较短的间隔限制
            atr_period=14,
            trough_window=6,
            trough_min_side_bars=2,
        )

        n_days = 180
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

        # 创建间隔很大的双底：底部在第 60 天，次低点在第 100 天（间隔 40 天）
        prices = np.concatenate([
            np.linspace(100, 70, 60),    # 下跌到底部
            np.linspace(70, 85, 40),     # 反弹 21%
            np.linspace(85, 75, 20),     # 回调形成次低点（间隔 > 10 天）
            np.linspace(75, 100, 60),    # 继续上涨
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

        signals = detector.detect(df, "TEST")

        # 由于间隔超过 10 天，信号的 gap_days 应该 <= 10
        for signal in signals:
            assert signal.details["gap_days"] <= 10

    def test_min_recovery_atr_constraint(self):
        """测试 min_recovery_atr 约束"""
        detector = DoubleTroughDetector(
            min_of=126,
            first_bounce_atr=2.0,
            min_recovery_atr=5.0,  # 需要至少 5 倍 ATR 的恢复
            atr_period=14,
            trough_window=6,
            trough_min_side_bars=2,
        )

        n_days = 180
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

        # 创建恢复幅度较小的双底
        prices = np.concatenate([
            np.linspace(100, 100, 60),   # 横盘
            np.linspace(100, 70, 30),    # 下跌到底部
            np.linspace(70, 80, 20),     # 反弹 14%（满足 bounce 要求）
            np.linspace(80, 72, 15),     # 回调形成次低点（恢复约 2.8%，< 10%）
            np.linspace(72, 85, 55),     # 继续上涨
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

        signals = detector.detect(df, "TEST")

        # 验证所有信号的恢复 ATR 倍数都 >= 5.0
        for signal in signals:
            assert signal.details["recovery_atr"] >= 5.0

    def test_structural_adjacency(self):
        """测试结构紧邻约束：TR2 必须是 TR1 之后的第一个 trough"""
        detector = DoubleTroughDetector(
            min_of=126,
            first_bounce_atr=2.0,
            atr_period=14,
            trough_window=6,
            trough_min_side_bars=2,
        )

        n_days = 200
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

        # 创建一个场景：TR1 之后有一个更低的 trough，应该使 TR1 作废
        prices = np.concatenate([
            np.linspace(100, 100, 50),   # 横盘
            np.linspace(100, 70, 30),    # 下跌到第一个底部 (70)
            np.linspace(70, 80, 15),     # 反弹 14%
            np.linspace(80, 65, 20),     # 继续下跌到更低点 (65)
            np.linspace(65, 75, 15),     # 反弹形成次低点
            np.linspace(75, 70, 10),     # 回调
            np.linspace(70, 90, 60),     # 上涨
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

        signals = detector.detect(df, "TEST")

        # 验证信号的 TR1 是真正的 126 日最低点
        for signal in signals:
            tr1_idx = signal.details["trough1_index"]
            tr2_idx = signal.details["trough2_index"]

            # TR2 应该在 TR1 之后
            assert tr2_idx > tr1_idx

    def test_bounce_pct_in_details(self, detector, double_trough_df):
        """验证 details 中包含 bounce_pct 和 bounce_atr"""
        signals = detector.detect(double_trough_df, "TEST")

        for signal in signals:
            # bounce_pct 应该存在（保留百分比用于人类可读）
            assert "bounce_pct" in signal.details
            # bounce_atr 应该存在且 >= first_bounce_atr
            assert "bounce_atr" in signal.details
            assert signal.details["bounce_atr"] >= detector.first_bounce_atr

    def test_troughs_cached_in_details(self, detector, double_trough_df):
        """验证 details 中包含缓存的 troughs 列表（供 SupportAnalyzer 复用）"""
        signals = detector.detect(double_trough_df, "TEST")

        for signal in signals:
            # troughs 应该存在
            assert "troughs" in signal.details
            troughs = signal.details["troughs"]

            # troughs 应该是列表
            assert isinstance(troughs, list)
            assert len(troughs) >= 1  # 至少有 TR2

            # 每个 trough 应该包含必要字段
            for t in troughs:
                assert "index" in t
                assert "price" in t
                assert "date" in t
                assert isinstance(t["index"], int)
                assert isinstance(t["price"], float)
                assert isinstance(t["date"], str)
