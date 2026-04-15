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
