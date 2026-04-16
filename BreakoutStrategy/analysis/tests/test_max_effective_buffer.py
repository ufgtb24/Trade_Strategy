"""FeatureCalculator.max_effective_buffer 单元测试"""

from BreakoutStrategy.analysis.features import FeatureCalculator


def test_max_effective_buffer_default_config_is_252():
    """默认配置下最大因子 lookback = 252（dd_recov / annual_vol 依赖因子）。"""
    assert FeatureCalculator.max_effective_buffer() == 252


def test_max_effective_buffer_scales_with_ma_pos_period():
    """ma_pos_period 调大到超过 252 时，max_effective_buffer 应跟随。"""
    assert FeatureCalculator.max_effective_buffer({"ma_pos_period": 400}) >= 400


def test_max_effective_buffer_scales_with_dd_recov_lookback():
    """dd_recov_lookback 调大时，max_effective_buffer 应跟随。"""
    assert FeatureCalculator.max_effective_buffer({"dd_recov_lookback": 500}) >= 500


def test_max_effective_buffer_scales_with_ma_curve():
    """ma_curve_period + 2 × ma_curve_stride 超过 252 时也应反映。"""
    # 300 + 2 × 50 = 400
    result = FeatureCalculator.max_effective_buffer({
        "ma_curve_period": 300,
        "ma_curve_stride": 50,
    })
    assert result >= 400
