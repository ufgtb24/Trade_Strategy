"""测试联合信号强度计算、序列标签与异常走势检测"""
import pytest
from datetime import date, timedelta

import numpy as np
import pandas as pd

from BreakoutStrategy.signals.composite import (
    AMPLITUDE_THRESHOLD,
    FRESHNESS_ALPHA,
    FRESHNESS_HALF_LIFE,
    MIN_RISE_PCT,
    _get_freshness,
    calc_effective_weighted_sum,
    calculate_amplitude,
    calculate_signal_freshness,
    calculate_signal_strength,
    generate_sequence_label,
    is_turbulent,
    _calc_price_decay_momentum,
    _calc_price_decay_support,
)
from BreakoutStrategy.signals.aggregator import SignalAggregator
from BreakoutStrategy.signals.models import AbsoluteSignal, SignalType


class TestCalculateSignalStrength:
    def test_breakout_strength(self):
        """B(pk_num=3) → strength=3.0"""
        signal = AbsoluteSignal(
            "AAPL", date(2026, 1, 10), SignalType.BREAKOUT, 150.0,
            details={"pk_num": 3},
        )
        assert calculate_signal_strength(signal) == 3.0

    def test_breakout_strength_default(self):
        """B 无 pk_num → strength=1.0"""
        signal = AbsoluteSignal(
            "AAPL", date(2026, 1, 10), SignalType.BREAKOUT, 150.0,
        )
        assert calculate_signal_strength(signal) == 1.0

    def test_trough_strength(self):
        """D(tr_num=2) → strength=2.0"""
        signal = AbsoluteSignal(
            "AAPL", date(2026, 1, 10), SignalType.DOUBLE_TROUGH, 150.0,
            details={"tr_num": 2},
        )
        assert calculate_signal_strength(signal) == 2.0

    def test_trough_strength_default(self):
        """D 无 tr_num → strength=1.0"""
        signal = AbsoluteSignal(
            "AAPL", date(2026, 1, 10), SignalType.DOUBLE_TROUGH, 150.0,
        )
        assert calculate_signal_strength(signal) == 1.0

    def test_volume_strength(self):
        """V → strength=1.0"""
        signal = AbsoluteSignal(
            "AAPL", date(2026, 1, 10), SignalType.HIGH_VOLUME, 150.0,
        )
        assert calculate_signal_strength(signal) == 1.0

    def test_yang_strength(self):
        """Y → strength=1.0"""
        signal = AbsoluteSignal(
            "AAPL", date(2026, 1, 10), SignalType.BIG_YANG, 150.0,
        )
        assert calculate_signal_strength(signal) == 1.0


class TestGenerateSequenceLabel:
    def test_sequence_label_basic(self):
        """多信号生成正确标签"""
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal("AAPL", base - timedelta(days=30), SignalType.DOUBLE_TROUGH, 140.0, details={"tr_num": 2}),
            AbsoluteSignal("AAPL", base - timedelta(days=20), SignalType.BREAKOUT, 148.0, details={"pk_num": 3}),
            AbsoluteSignal("AAPL", base - timedelta(days=10), SignalType.HIGH_VOLUME, 150.0),
            AbsoluteSignal("AAPL", base - timedelta(days=5), SignalType.BIG_YANG, 152.0),
        ]
        label = generate_sequence_label(signals)
        assert label == "D(2) → B(3) → V → Y"

    def test_sequence_label_single(self):
        """单信号无箭头"""
        signals = [
            AbsoluteSignal("AAPL", date(2026, 1, 10), SignalType.BREAKOUT, 150.0, details={"pk_num": 2}),
        ]
        label = generate_sequence_label(signals)
        assert label == "B(2)"

    def test_sequence_label_no_extra_info(self):
        """pk_num=1 和 tr_num=1 时不显示括号"""
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal("AAPL", base - timedelta(days=10), SignalType.DOUBLE_TROUGH, 140.0, details={"tr_num": 1}),
            AbsoluteSignal("AAPL", base - timedelta(days=5), SignalType.BREAKOUT, 150.0, details={"pk_num": 1}),
        ]
        label = generate_sequence_label(signals)
        assert label == "D → B"

    def test_sequence_label_sorted_by_date(self):
        """确认按日期升序排列（即使输入乱序）"""
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal("AAPL", base - timedelta(days=5), SignalType.BIG_YANG, 152.0),
            AbsoluteSignal("AAPL", base - timedelta(days=20), SignalType.BREAKOUT, 148.0),
        ]
        label = generate_sequence_label(signals)
        assert label == "B → Y"


class TestAggregatorWeightedSort:
    def test_aggregator_weighted_sort(self):
        """weighted_sum 排序正确（集成测试）"""
        base = date(2026, 1, 10)
        signals = [
            # AAPL: 2 个信号，weighted_sum = 3+1 = 4.0
            AbsoluteSignal("AAPL", base - timedelta(days=5), SignalType.BREAKOUT, 150.0, details={"pk_num": 3}),
            AbsoluteSignal("AAPL", base - timedelta(days=10), SignalType.HIGH_VOLUME, 148.0),
            # MSFT: 3 个信号，weighted_sum = 1+1+1 = 3.0
            AbsoluteSignal("MSFT", base - timedelta(days=3), SignalType.BREAKOUT, 380.0, details={"pk_num": 1}),
            AbsoluteSignal("MSFT", base - timedelta(days=10), SignalType.HIGH_VOLUME, 375.0),
            AbsoluteSignal("MSFT", base - timedelta(days=15), SignalType.BIG_YANG, 370.0),
        ]

        aggregator = SignalAggregator()
        results = aggregator.aggregate(signals, base)

        # AAPL weighted_sum=4.0 > MSFT weighted_sum=3.0
        assert results[0].symbol == "AAPL"
        assert results[0].weighted_sum == 4.0
        assert results[1].symbol == "MSFT"
        assert results[1].weighted_sum == 3.0

    def test_aggregator_tiebreak_by_count(self):
        """weighted_sum 相同时按 signal_count 降序"""
        base = date(2026, 1, 10)
        signals = [
            # AAPL: 2 个信号，weighted_sum = 1+1 = 2.0
            AbsoluteSignal("AAPL", base - timedelta(days=5), SignalType.BREAKOUT, 150.0),
            AbsoluteSignal("AAPL", base - timedelta(days=10), SignalType.HIGH_VOLUME, 148.0),
            # MSFT: 1 个信号，weighted_sum = 2.0
            AbsoluteSignal("MSFT", base - timedelta(days=3), SignalType.DOUBLE_TROUGH, 380.0, details={"tr_num": 2}),
        ]

        aggregator = SignalAggregator()
        results = aggregator.aggregate(signals, base)

        # 两者 weighted_sum 相同 = 2.0，AAPL signal_count=2 > MSFT signal_count=1
        assert results[0].symbol == "AAPL"
        assert results[1].symbol == "MSFT"

    def test_aggregator_sequence_label(self):
        """聚合后 sequence_label 正确"""
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal("AAPL", base - timedelta(days=20), SignalType.DOUBLE_TROUGH, 140.0, details={"tr_num": 2}),
            AbsoluteSignal("AAPL", base - timedelta(days=5), SignalType.BREAKOUT, 150.0, details={"pk_num": 3}),
        ]

        aggregator = SignalAggregator()
        results = aggregator.aggregate(signals, base)

        assert results[0].sequence_label == "D(2) → B(3)"
        assert results[0].weighted_sum == 5.0


# ========== 异常走势检测测试 ==========

class TestCalculateAmplitude:
    def _make_df(self, highs, lows):
        """构造测试用 DataFrame"""
        n = len(highs)
        return pd.DataFrame({
            "High": highs,
            "Low": lows,
            "Close": [(h + l) / 2 for h, l in zip(highs, lows)],
        })

    def test_normal_stock(self):
        """正常波动股票，max_runup 较小"""
        # 价格在 100-120 之间波动
        df = self._make_df(
            highs=[110, 115, 112, 118, 120],
            lows=[100, 105, 102, 108, 110],
        )
        amp = calculate_amplitude(df, lookback_days=5)
        # cum_min=[100,100,100,100,100], max runup = (120-100)/100 = 0.2
        assert amp == pytest.approx(0.2)

    def test_pump_and_dump(self):
        """暴涨-暴跌完成型，max_runup 很大"""
        # 从 100 涨到 200 再跌回 110
        df = self._make_df(
            highs=[105, 150, 200, 160, 115],
            lows=[100, 120, 170, 110, 105],
        )
        amp = calculate_amplitude(df, lookback_days=5)
        # cum_min=[100,100,100,100,100], max runup = (200-100)/100 = 1.0
        assert amp == pytest.approx(1.0)

    def test_pump_still_high(self):
        """暴涨未跌型，持续上涨"""
        df = self._make_df(
            highs=[105, 130, 170, 190, 185],
            lows=[100, 115, 150, 170, 175],
        )
        amp = calculate_amplitude(df, lookback_days=5)
        # cum_min=[100,100,100,100,100], max runup = (190-100)/100 = 0.9
        assert amp == pytest.approx(0.9)

    def test_lookback_window_clips(self):
        """lookback_days 裁剪有效"""
        # 前 3 行有极端值，但 lookback=2 只看最后 2 行
        df = self._make_df(
            highs=[500, 105, 110],
            lows=[100, 100, 105],
        )
        amp = calculate_amplitude(df, lookback_days=2)
        # 只看最后 2 行: cum_min=[100,100], max runup = (110-100)/100 = 0.1
        assert amp == pytest.approx(0.1)

    def test_zero_low(self):
        """min_low <= 0 时返回 0"""
        df = self._make_df(highs=[10, 20], lows=[0, 5])
        amp = calculate_amplitude(df, lookback_days=2)
        assert amp == 0.0

    def test_zero_low_at_end(self):
        """零值在窗口末尾 — 仅该 bar 被忽略，前面的 runup 仍有效"""
        df = self._make_df(highs=[20, 10], lows=[5, 0])
        amp = calculate_amplitude(df, lookback_days=2)
        # cum_min=[5, 0], safe=[5, nan], runups=[(20-5)/5, nan] = [3.0, nan]
        assert amp == pytest.approx(3.0)

    def test_drop_then_partial_recovery(self):
        """先跌后涨 — max_runup 小于旧 amplitude

        价格从高位跌到低位再部分回升。
        旧 amplitude = (100-50)/50 = 1.0
        新 max_runup:
            cum_min = [90, 60, 50, 50, 50]
            runups = [(100-90)/90, (80-60)/60, (55-50)/50, (65-50)/50, (75-50)/50]
                   = [0.111, 0.333, 0.1, 0.3, 0.5]
            max_runup = 0.5
        """
        df = self._make_df(
            highs=[100, 80, 55, 65, 75],
            lows=[90, 60, 50, 55, 65],
        )
        amp = calculate_amplitude(df, lookback_days=5)
        assert amp == pytest.approx(0.5)


class TestIsTurbulent:
    def test_below_threshold(self):
        assert is_turbulent(0.5) is False

    def test_at_threshold(self):
        assert is_turbulent(AMPLITUDE_THRESHOLD) is True

    def test_above_threshold(self):
        assert is_turbulent(1.2) is True


class TestCalcEffectiveWeightedSum:
    def _make_signals(self):
        """构造混合信号列表"""
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal("X", base - timedelta(days=20), SignalType.BREAKOUT, 150.0, strength=3.0),
            AbsoluteSignal("X", base - timedelta(days=15), SignalType.HIGH_VOLUME, 160.0, strength=1.0),
            AbsoluteSignal("X", base - timedelta(days=10), SignalType.BIG_YANG, 170.0, strength=1.0),
            AbsoluteSignal("X", base - timedelta(days=5), SignalType.DOUBLE_TROUGH, 110.0, strength=2.0),
        ]
        return signals

    def test_not_turbulent(self):
        """非 turbulent 时所有信号计入"""
        signals = self._make_signals()
        assert calc_effective_weighted_sum(signals, turbulent=False) == 7.0

    def test_turbulent_only_d(self):
        """turbulent 时仅 D 信号计入"""
        signals = self._make_signals()
        assert calc_effective_weighted_sum(signals, turbulent=True) == 2.0

    def test_turbulent_no_d_signals(self):
        """turbulent 且无 D 信号时 weighted_sum = 0"""
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal("X", base, SignalType.BREAKOUT, 150.0, strength=3.0),
            AbsoluteSignal("X", base, SignalType.HIGH_VOLUME, 160.0, strength=1.0),
        ]
        assert calc_effective_weighted_sum(signals, turbulent=True) == 0.0


class TestAggregatorTurbulent:
    def test_turbulent_demotes_stock(self):
        """turbulent 股票的 B/V/Y 信号不计入 weighted_sum，排名下降"""
        base = date(2026, 1, 10)
        signals = [
            # PUMP: 4 个信号 (B+V+Y+D)，但 amplitude=1.0 → turbulent
            AbsoluteSignal("PUMP", base - timedelta(days=20), SignalType.BREAKOUT, 200.0, details={"pk_num": 3}),
            AbsoluteSignal("PUMP", base - timedelta(days=15), SignalType.HIGH_VOLUME, 180.0),
            AbsoluteSignal("PUMP", base - timedelta(days=10), SignalType.BIG_YANG, 190.0),
            AbsoluteSignal("PUMP", base - timedelta(days=3), SignalType.DOUBLE_TROUGH, 110.0, details={"tr_num": 1}),
            # NORMAL: 2 个信号，amplitude=0.2 → 正常
            AbsoluteSignal("NORMAL", base - timedelta(days=10), SignalType.BREAKOUT, 120.0, details={"pk_num": 2}),
            AbsoluteSignal("NORMAL", base - timedelta(days=5), SignalType.HIGH_VOLUME, 122.0),
        ]

        amplitude_by_symbol = {"PUMP": 1.0, "NORMAL": 0.2}
        aggregator = SignalAggregator()
        results = aggregator.aggregate(signals, base, amplitude_by_symbol)

        # NORMAL 排第一: weighted_sum = 2+1 = 3.0
        assert results[0].symbol == "NORMAL"
        assert results[0].weighted_sum == 3.0
        assert results[0].turbulent is False

        # PUMP 排第二: 仅 D 信号计入, weighted_sum = 1.0
        assert results[1].symbol == "PUMP"
        assert results[1].weighted_sum == 1.0
        assert results[1].turbulent is True
        assert results[1].signal_count == 4  # 所有信号仍保留
        assert results[1].amplitude == 1.0

    def test_no_amplitude_data_no_turbulent(self):
        """无 amplitude 数据时不标记 turbulent"""
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal("AAPL", base, SignalType.BREAKOUT, 150.0, details={"pk_num": 2}),
        ]

        aggregator = SignalAggregator()
        results = aggregator.aggregate(signals, base)  # 不传 amplitude

        assert results[0].turbulent is False
        assert results[0].weighted_sum == 2.0

    def test_turbulent_d_signal_immune(self):
        """turbulent 股票的 D 信号完全保留强度"""
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal("X", base - timedelta(days=10), SignalType.BREAKOUT, 200.0, details={"pk_num": 5}),
            AbsoluteSignal("X", base - timedelta(days=3), SignalType.DOUBLE_TROUGH, 110.0, details={"tr_num": 3}),
        ]

        amplitude_by_symbol = {"X": 0.9}
        aggregator = SignalAggregator()
        results = aggregator.aggregate(signals, base, amplitude_by_symbol)

        # 仅 D(tr_num=3) 计入
        assert results[0].weighted_sum == 3.0
        assert results[0].turbulent is True


# ========== 信号鲜度测试 ==========

class TestSignalFreshness:
    """测试信号鲜度（PRTR 价格衰减 + 时间衰减）"""

    def _make_price_df(self, dates, highs, lows, closes):
        """构造带日期索引的价格 DataFrame"""
        idx = pd.DatetimeIndex(dates)
        return pd.DataFrame(
            {"High": highs, "Low": lows, "Close": closes},
            index=idx,
        )

    # --- 动量信号（B/V/Y）价格衰减测试 ---

    def test_momentum_full_roundtrip(self):
        """B 信号完全回撤 → price_decay ≈ 0

        信号价 $10，涨到 $15（rise=$5），当前跌回 $10（giveback=$5）
        prtr = 5/5 = 1.0, decay = 1 - 1.0^1.5 = 0.0
        """
        signal = AbsoluteSignal(
            "X", date(2026, 1, 2), SignalType.BREAKOUT, 10.0,
        )
        dates = [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 6)]
        df = self._make_price_df(
            dates=dates,
            highs=[10.5, 15.0, 10.2],
            lows=[9.8, 12.0, 9.5],
            closes=[10.0, 14.0, 10.0],
        )
        decay = _calc_price_decay_momentum(signal, df, current_price=10.0)
        assert decay == pytest.approx(0.0, abs=0.01)

    def test_momentum_no_retracement(self):
        """B 信号无回撤 → price_decay ≈ 1.0

        信号价 $10，涨到 $15，当前 $15（giveback=0）
        prtr = 0/5 = 0.0, decay = 1 - 0^1.5 = 1.0
        """
        signal = AbsoluteSignal(
            "X", date(2026, 1, 2), SignalType.BREAKOUT, 10.0,
        )
        dates = [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 6)]
        df = self._make_price_df(
            dates=dates,
            highs=[10.5, 15.0, 15.2],
            lows=[9.8, 12.0, 14.5],
            closes=[10.0, 14.0, 15.0],
        )
        decay = _calc_price_decay_momentum(signal, df, current_price=15.0)
        assert decay == pytest.approx(1.0, abs=0.01)

    def test_momentum_partial_retracement(self):
        """B 信号 50% 回撤 → price_decay ≈ 0.65

        信号价 $10，涨到 $20（rise=$10），当前 $15（giveback=$5）
        prtr = 5/10 = 0.5, decay = 1 - 0.5^1.5 ≈ 1 - 0.354 = 0.646
        """
        signal = AbsoluteSignal(
            "X", date(2026, 1, 2), SignalType.BREAKOUT, 10.0,
        )
        dates = [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 6)]
        df = self._make_price_df(
            dates=dates,
            highs=[10.5, 20.0, 15.5],
            lows=[9.8, 15.0, 14.0],
            closes=[10.0, 19.0, 15.0],
        )
        decay = _calc_price_decay_momentum(signal, df, current_price=15.0)
        expected = 1.0 - 0.5 ** 1.5  # ≈ 0.646
        assert decay == pytest.approx(expected, abs=0.01)

    def test_momentum_small_rise_fallback(self):
        """信号后涨幅过小（< 5%），使用简单跌幅回退

        signal.price=$2.0, peak=$2.08 (rise=$0.08, 4% < 5%), current=$1.9
        drop_ratio = (2.0 - 1.9) / 2.0 = 0.05
        decay = max(0.0, 1.0 - 0.05) = 0.95
        """
        signal = AbsoluteSignal(
            "X", date(2026, 1, 2), SignalType.BREAKOUT, 2.0,
        )
        dates = [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 6)]
        df = self._make_price_df(
            dates=dates,
            highs=[2.05, 2.08, 1.92],
            lows=[1.95, 2.0, 1.88],
            closes=[2.0, 2.05, 1.9],
        )
        decay = _calc_price_decay_momentum(signal, df, current_price=1.9)
        # rise = 2.08 - 2.0 = 0.08 < 2.0 * 0.05 = 0.10 → 回退
        # current_price < signal.price → drop_ratio = 0.05
        assert decay == pytest.approx(0.95, abs=0.01)

    def test_momentum_small_rise_above_signal(self):
        """涨幅过小且当前价 >= 信号价 → decay = 1.0"""
        signal = AbsoluteSignal(
            "X", date(2026, 1, 2), SignalType.BREAKOUT, 2.0,
        )
        dates = [date(2026, 1, 2), date(2026, 1, 3)]
        df = self._make_price_df(
            dates=dates,
            highs=[2.05, 2.08],
            lows=[1.95, 2.0],
            closes=[2.0, 2.05],
        )
        decay = _calc_price_decay_momentum(signal, df, current_price=2.05)
        assert decay == pytest.approx(1.0)

    # --- 支撑信号（D）价格衰减测试 ---

    def test_support_in_zone(self):
        """D 信号在支撑区间内 → price_decay = 1.0

        signal.price=$2.0, current=$2.1, ratio=1.05 在 [0.9, 1.2] 内
        """
        signal = AbsoluteSignal(
            "X", date(2026, 1, 2), SignalType.DOUBLE_TROUGH, 2.0,
        )
        decay = _calc_price_decay_support(signal, current_price=2.1)
        assert decay == pytest.approx(1.0)

    def test_support_failed(self):
        """D 信号支撑失效 → price_decay 较低

        signal.price=$2.0, current=$1.6, ratio=0.8
        ratio < 0.9 → max(0.1, 1.0 - (0.9 - 0.8) / 0.2) = max(0.1, 0.5) = 0.5
        """
        signal = AbsoluteSignal(
            "X", date(2026, 1, 2), SignalType.DOUBLE_TROUGH, 2.0,
        )
        decay = _calc_price_decay_support(signal, current_price=1.6)
        assert decay == pytest.approx(0.5, abs=0.01)

    def test_support_badly_failed(self):
        """D 信号支撑严重失效 → price_decay 接近下限 0.1

        signal.price=$2.0, current=$1.2, ratio=0.6
        max(0.1, 1.0 - (0.9 - 0.6) / 0.2) = max(0.1, -0.5) = 0.1
        """
        signal = AbsoluteSignal(
            "X", date(2026, 1, 2), SignalType.DOUBLE_TROUGH, 2.0,
        )
        decay = _calc_price_decay_support(signal, current_price=1.2)
        assert decay == pytest.approx(0.1, abs=0.01)

    def test_support_moved_away(self):
        """D 信号远离支撑 → price_decay ≈ 0.3（下限）

        signal.price=$2.0, current=$4.0, ratio=2.0
        ratio > 1.2 → max(0.3, 1.0 - (2.0 - 1.2) / 0.5) = max(0.3, -0.6) = 0.3
        """
        signal = AbsoluteSignal(
            "X", date(2026, 1, 2), SignalType.DOUBLE_TROUGH, 2.0,
        )
        decay = _calc_price_decay_support(signal, current_price=4.0)
        assert decay == pytest.approx(0.3, abs=0.01)

    def test_support_zero_price(self):
        """D 信号 price=0 → price_decay = 0.0"""
        signal = AbsoluteSignal(
            "X", date(2026, 1, 2), SignalType.DOUBLE_TROUGH, 0.0,
        )
        decay = _calc_price_decay_support(signal, current_price=1.0)
        assert decay == pytest.approx(0.0)

    # --- 时间衰减测试 ---

    def test_time_decay_half_life(self):
        """信号发出 30 个交易日后 → time_decay = 0.5

        构造 31 根 bar（index 0..30），信号在 index 0，扫描在 index 30
        days_elapsed = 30, time_decay = 0.5^(30/30) = 0.5
        """
        base = date(2026, 1, 2)
        # 生成 31 个交易日
        dates = pd.bdate_range(base, periods=31)
        n = len(dates)
        df = pd.DataFrame(
            {
                "High": [12.0] * n,
                "Low": [10.0] * n,
                "Close": [11.0] * n,
            },
            index=dates,
        )

        signal = AbsoluteSignal(
            "X", dates[0].date(), SignalType.BREAKOUT, 10.0,
        )
        # price 不变 → no rise → small rise fallback, current >= signal → price_decay=1.0
        # 但 High=12 vs signal.price=10 → rise=2.0, 2.0 > 10*0.05=0.5 → 走 PRTR
        # peak=12, giveback=12-11=1, prtr=1/2=0.5, decay=1-0.5^1.5≈0.646
        # 我们只关心 time_decay，所以验证 freshness = price_decay * time_decay
        result = calculate_signal_freshness(
            signal, df, current_price=11.0, scan_date=dates[-1].date(),
        )
        assert isinstance(result, dict)
        price_decay = 1.0 - 0.5 ** 1.5  # ≈ 0.646
        time_decay = 0.5  # 30 days / 30 half_life
        expected = price_decay * time_decay
        assert result["value"] == pytest.approx(expected, abs=0.02)
        assert result["price_decay"] == pytest.approx(price_decay, abs=0.01)
        assert result["time_decay"] == pytest.approx(time_decay, abs=0.01)

    def test_time_decay_zero_days(self):
        """信号当天 → time_decay = 1.0（无时间衰减）"""
        base = date(2026, 1, 2)
        dates = pd.bdate_range(base, periods=1)
        df = pd.DataFrame(
            {"High": [12.0], "Low": [10.0], "Close": [11.0]},
            index=dates,
        )
        signal = AbsoluteSignal(
            "X", dates[0].date(), SignalType.BREAKOUT, 10.0,
        )
        result = calculate_signal_freshness(
            signal, df, current_price=11.0, scan_date=dates[0].date(),
        )
        assert isinstance(result, dict)
        # days_elapsed=0, time_decay=1.0
        # rise=12-10=2 > 10*0.05=0.5, giveback=12-11=1, prtr=0.5
        # price_decay=1-0.5^1.5≈0.646
        expected_price_decay = 1.0 - 0.5 ** 1.5
        assert result["value"] == pytest.approx(expected_price_decay, abs=0.01)
        assert result["time_decay"] == pytest.approx(1.0)

    # --- 向后兼容测试 ---

    def test_freshness_default_backward_compat(self):
        """无 freshness 的信号 → calc_effective_weighted_sum 结果不变

        details 中没有 freshness 键时默认为 1.0
        """
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal("X", base, SignalType.BREAKOUT, 150.0, strength=3.0),
            AbsoluteSignal("X", base, SignalType.HIGH_VOLUME, 160.0, strength=1.0),
        ]
        # 没有 freshness → 默认 1.0
        result = calc_effective_weighted_sum(signals, turbulent=False)
        assert result == pytest.approx(4.0)

    # --- 集成测试：聚合器使用 freshness ---

    def test_aggregator_with_freshness(self):
        """聚合器通过 details["freshness"] 使用鲜度因子

        信号已预设 freshness，验证 calc_effective_weighted_sum 乘入鲜度。
        """
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal(
                "X", base - timedelta(days=5), SignalType.BREAKOUT, 150.0,
                strength=3.0, details={"pk_num": 3, "freshness": 0.5},
            ),
            AbsoluteSignal(
                "X", base - timedelta(days=10), SignalType.HIGH_VOLUME, 160.0,
                strength=1.0, details={"freshness": 0.8},
            ),
        ]
        # weighted_sum = 3.0 * 0.5 + 1.0 * 0.8 = 1.5 + 0.8 = 2.3
        result = calc_effective_weighted_sum(signals, turbulent=False)
        assert result == pytest.approx(2.3, abs=0.01)

    def test_aggregator_turbulent_with_freshness(self):
        """turbulent 模式下 D 信号的鲜度也被应用"""
        base = date(2026, 1, 10)
        signals = [
            AbsoluteSignal(
                "X", base - timedelta(days=5), SignalType.BREAKOUT, 200.0,
                strength=3.0, details={"pk_num": 3, "freshness": 1.0},
            ),
            AbsoluteSignal(
                "X", base - timedelta(days=3), SignalType.DOUBLE_TROUGH, 110.0,
                strength=2.0, details={"tr_num": 2, "freshness": 0.6},
            ),
        ]
        # turbulent=True → 仅 D 信号: 2.0 * 0.6 = 1.2
        result = calc_effective_weighted_sum(signals, turbulent=True)
        assert result == pytest.approx(1.2, abs=0.01)

    def test_aggregator_integration_freshness_applied(self):
        """端到端：聚合器 aggregate() 中 freshness 参与 weighted_sum 计算

        aggregator.aggregate() 内部调用 calculate_signal_strength() 设置 strength，
        然后 calc_effective_weighted_sum() 读取 details["freshness"]。
        """
        base = date(2026, 1, 10)
        signals = [
            # pk_num=2 → strength=2.0, freshness=0.5 → effective=1.0
            AbsoluteSignal(
                "AAPL", base - timedelta(days=5), SignalType.BREAKOUT, 150.0,
                details={"pk_num": 2, "freshness": 0.5},
            ),
            # V → strength=1.0, freshness=0.8 → effective=0.8
            AbsoluteSignal(
                "AAPL", base - timedelta(days=10), SignalType.HIGH_VOLUME, 148.0,
                details={"freshness": 0.8},
            ),
        ]

        aggregator = SignalAggregator()
        results = aggregator.aggregate(signals, base)

        # weighted_sum = 2.0*0.5 + 1.0*0.8 = 1.8
        assert results[0].weighted_sum == pytest.approx(1.8, abs=0.01)
