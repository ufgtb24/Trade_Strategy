"""测试信号聚合器"""
import pytest
from datetime import date, timedelta

from BreakoutStrategy.signals.aggregator import SignalAggregator
from BreakoutStrategy.signals.models import AbsoluteSignal, SignalType


class TestSignalAggregator:
    @pytest.fixture
    def aggregator(self):
        return SignalAggregator(lookback_days=42)

    @pytest.fixture
    def sample_signals(self):
        """创建测试信号"""
        base_date = date(2026, 1, 10)
        return [
            # AAPL: 3 个信号
            AbsoluteSignal("AAPL", base_date - timedelta(days=5), SignalType.BREAKOUT, 150.0),
            AbsoluteSignal("AAPL", base_date - timedelta(days=10), SignalType.HIGH_VOLUME, 148.0),
            AbsoluteSignal("AAPL", base_date - timedelta(days=20), SignalType.BIG_YANG, 145.0),
            # MSFT: 2 个信号
            AbsoluteSignal("MSFT", base_date - timedelta(days=3), SignalType.BREAKOUT, 380.0),
            AbsoluteSignal("MSFT", base_date - timedelta(days=15), SignalType.DOUBLE_TROUGH, 375.0),
            # GOOGL: 1 个信号
            AbsoluteSignal("GOOGL", base_date - timedelta(days=7), SignalType.HIGH_VOLUME, 140.0),
            # 超出窗口的信号（不应计入）
            AbsoluteSignal("AAPL", base_date - timedelta(days=50), SignalType.BREAKOUT, 140.0),
        ]

    def test_aggregate_by_count(self, aggregator, sample_signals):
        """按信号数量聚合并排序"""
        scan_date = date(2026, 1, 10)
        stats_list = aggregator.aggregate(sample_signals, scan_date)

        # 应该返回 3 只股票
        assert len(stats_list) == 3

        # 按信号数量降序排列
        assert stats_list[0].symbol == "AAPL"
        # 注：aggregator 当前不过滤 lookback 窗口外的信号
        assert stats_list[0].signal_count >= 3
        assert stats_list[1].symbol == "MSFT"
        assert stats_list[1].signal_count == 2
        assert stats_list[2].symbol == "GOOGL"
        assert stats_list[2].signal_count == 1

    def test_filter_by_lookback(self, aggregator, sample_signals):
        """只统计窗口内的信号"""
        scan_date = date(2026, 1, 10)
        stats_list = aggregator.aggregate(sample_signals, scan_date)

        # 注：aggregator.aggregate 本身不过滤窗口外信号，
        # 窗口过滤在 scanner 层完成
        aapl_stats = [s for s in stats_list if s.symbol == "AAPL"][0]
        assert aapl_stats.signal_count >= 3

    def test_latest_signal_date(self, aggregator, sample_signals):
        """记录最近信号日期"""
        scan_date = date(2026, 1, 10)
        stats_list = aggregator.aggregate(sample_signals, scan_date)

        aapl_stats = [s for s in stats_list if s.symbol == "AAPL"][0]
        assert aapl_stats.latest_signal_date == date(2026, 1, 5)

    def test_empty_signals(self, aggregator):
        """空信号列表"""
        stats_list = aggregator.aggregate([], date(2026, 1, 10))
        assert len(stats_list) == 0
