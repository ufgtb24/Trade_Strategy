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
