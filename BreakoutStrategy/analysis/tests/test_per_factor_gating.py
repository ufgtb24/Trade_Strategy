"""Per-Factor Gating Spec 1 核心测试集合。"""
import numpy as np
import pandas as pd
from datetime import date

from BreakoutStrategy.analysis.breakout_detector import Breakout
from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer, FactorDetail
from BreakoutStrategy.analysis.features import FeatureCalculator
from BreakoutStrategy.factor_registry import FACTOR_REGISTRY, FactorInfo, get_factor
from BreakoutStrategy.UI.styles import SCORE_TOOLTIP_COLORS


def test_all_lookback_factors_are_nullable():
    """所有 buffer>0 的因子必须 nullable=True。
    Per-factor gate 下，features 层对 lookback 不足返回 None，scorer 的 nullable 分支
    是 None → FactorDetail.unavailable=True 的唯一入口。
    """
    for fi in FACTOR_REGISTRY:
        if fi.buffer > 0:
            assert fi.nullable is True, (
                f"Factor '{fi.key}' has buffer={fi.buffer} but nullable=False; "
                f"per-factor gate requires nullable=True"
            )


def test_factor_detail_default_unavailable_false():
    """FactorDetail 默认 unavailable=False，向后兼容。"""
    fd = FactorDetail(name='age', raw_value=180, unit='d',
                      multiplier=1.02, triggered=True, level=1)
    assert fd.unavailable is False


def test_factor_detail_nullable_none_sets_unavailable():
    """scorer._compute_factor 对 nullable 因子 + raw=None 输出 unavailable=True。"""
    scorer = BreakoutScorer()
    fd = scorer._compute_factor('drought', None)
    assert fd.unavailable is True
    assert fd.triggered is False
    assert fd.multiplier == 1.0


def test_factor_detail_normal_path_unavailable_false():
    """scorer._compute_factor 正常计算路径 unavailable 保持 False。"""
    scorer = BreakoutScorer()
    fd = scorer._compute_factor('drought', 100)  # drought>=80 → triggered
    assert fd.unavailable is False
    assert fd.triggered is True


def test_styles_has_factor_unavailable_color():
    """UI styles 必须导出 factor_unavailable 颜色。"""
    assert "factor_unavailable" in SCORE_TOOLTIP_COLORS
    assert SCORE_TOOLTIP_COLORS["factor_unavailable"].startswith("#")


def test_breakout_accepts_none_for_lookback_factors():
    """Breakout dataclass 的 8 个 lookback 因子字段必须接受 None。"""
    bo = Breakout(
        symbol="TEST", date=date(2026, 1, 1), price=10.0, index=100,
        broken_peaks=[],
        breakout_type="yang", intraday_change_pct=0.01, gap_up_pct=0.0,
        volume=None, pbm=None, stability_score=0.5,
        day_str=None, overshoot=None, pk_mom=None, pre_vol=None,
        ma_pos=None, annual_volatility=None,
    )
    assert bo.volume is None
    assert bo.pbm is None
    assert bo.day_str is None
    assert bo.overshoot is None
    assert bo.pk_mom is None
    assert bo.pre_vol is None
    assert bo.ma_pos is None
    assert bo.annual_volatility is None


def _mk_test_df(n_bars: int) -> pd.DataFrame:
    """造合成 OHLCV 数据，长度为 n_bars。"""
    rng = np.random.default_rng(42)
    close = 10 + np.cumsum(rng.normal(0, 0.5, n_bars))
    df = pd.DataFrame({
        'open': close * 0.99, 'high': close * 1.02,
        'low': close * 0.98, 'close': close,
        'volume': rng.integers(1_000_000, 5_000_000, n_bars).astype(float),
    }, index=pd.date_range('2020-01-01', periods=n_bars, freq='B'))
    return df


def test_annual_volatility_insufficient_returns_none():
    """idx<252 时 _calculate_annual_volatility 返回 None，不 raise。"""
    calc = FeatureCalculator()
    df = _mk_test_df(300)
    assert calc._calculate_annual_volatility(df, 100) is None
    assert calc._calculate_annual_volatility(df, 251) is None


def test_annual_volatility_sufficient_returns_float():
    """idx>=252 时 _calculate_annual_volatility 返回 float。"""
    calc = FeatureCalculator()
    df = _mk_test_df(300)
    result = calc._calculate_annual_volatility(df, 252)
    assert isinstance(result, float)
    assert result > 0


def test_day_str_returns_none_when_annual_vol_none():
    calc = FeatureCalculator()
    assert calc._calculate_day_str(0.01, 0.0, None) is None


def test_overshoot_returns_none_when_annual_vol_none():
    calc = FeatureCalculator()
    assert calc._calculate_overshoot(0.05, None) is None


def test_pbm_returns_none_when_annual_vol_none():
    calc = FeatureCalculator()
    df = _mk_test_df(100)
    assert calc._calculate_pbm(df, 50, None) is None


def test_ma_pos_returns_none_when_idx_insufficient():
    """ma_pos_period 默认 20，无 ma_20 列时 idx<19 返回 None。"""
    calc = FeatureCalculator(config={'ma_pos_period': 20})
    df = _mk_test_df(100)
    # df 没有 ma_20 列，走动态计算分支
    result = calc._calculate_ma_pos(df, 10)
    assert result is None


def test_ma_curve_returns_none_when_idx_insufficient():
    """ma_curve_period 默认 50，stride 默认 5，idx<60 时返回 None。"""
    calc = FeatureCalculator()
    df = _mk_test_df(100)
    assert calc._calculate_ma_curve(df, 30) is None


def test_gain_5d_returns_none_when_idx_insufficient():
    """gain_window 默认 5，idx<5 时返回 None。"""
    calc = FeatureCalculator()
    df = _mk_test_df(20)
    assert calc._calculate_gain_5d(df, 3) is None


def test_effective_buffer_zero_factors():
    calc = FeatureCalculator()
    for key in ('age', 'test', 'height', 'peak_vol', 'streak', 'drought'):
        fi = get_factor(key)
        assert calc._effective_buffer(fi) == 0, f"{key} should have buffer=0"


def test_effective_buffer_volume_is_63():
    calc = FeatureCalculator()
    fi = get_factor('volume')
    assert calc._effective_buffer(fi) == 63


def test_effective_buffer_depends_on_sub_params():
    """ma_pos_period=30 → _effective_buffer('ma_pos')=30"""
    calc = FeatureCalculator(config={'ma_pos_period': 30})
    fi = get_factor('ma_pos')
    assert calc._effective_buffer(fi) == 30


def test_effective_buffer_pk_mom_combines_sub_params():
    """pk_mom buffer = pk_lookback + atr_period, 默认 30+14=44"""
    calc = FeatureCalculator()
    fi = get_factor('pk_mom')
    assert calc._effective_buffer(fi) == 44

    calc2 = FeatureCalculator(config={'pk_lookback': 50, 'atr_period': 20})
    assert calc2._effective_buffer(fi) == 70


def test_effective_buffer_annual_vol_dependent_factors():
    """day_str/overshoot/pbm 的 buffer 都是 252（annual_volatility 的 lookback）"""
    calc = FeatureCalculator()
    for key in ('day_str', 'overshoot', 'pbm'):
        fi = get_factor(key)
        assert calc._effective_buffer(fi) == 252, f"{key} should be 252"


def test_effective_buffer_unregistered_raises():
    """伪造未注册的 fi.key → 抛 ValueError"""
    import pytest
    calc = FeatureCalculator()
    fake_fi = FactorInfo('__fake__', 'Fake', '假', (), ())
    with pytest.raises(ValueError, match="No effective_buffer registered"):
        calc._effective_buffer(fake_fi)
