"""Per-Factor Gating Spec 1 核心测试集合。"""
import numpy as np
import pandas as pd
from datetime import date

from BreakoutStrategy.analysis.breakout_detector import Breakout
from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer, FactorDetail
from BreakoutStrategy.analysis.features import FeatureCalculator
from BreakoutStrategy.factor_registry import FACTOR_REGISTRY
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
