"""Per-Factor Gating Spec 1 核心测试集合。"""
from BreakoutStrategy.factor_registry import FACTOR_REGISTRY


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


from BreakoutStrategy.analysis.breakout_scorer import FactorDetail, BreakoutScorer


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
    from BreakoutStrategy.UI.styles import SCORE_TOOLTIP_COLORS
    assert "factor_unavailable" in SCORE_TOOLTIP_COLORS
    assert SCORE_TOOLTIP_COLORS["factor_unavailable"].startswith("#")


from datetime import date
from BreakoutStrategy.analysis.breakout_detector import Breakout


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
