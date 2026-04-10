"""Test UIParamLoader.from_dict classmethod."""
from BreakoutStrategy.UI.config.param_loader import UIParamLoader


def test_from_dict_accepts_scan_params():
    """UIParamLoader.from_dict 应接受 dict 并返回可用的 loader 实例。"""
    raw = {
        "breakout_detector": {
            "total_window": 20,
            "min_side_bars": 6,
            "min_relative_height": 0.1,
            "exceed_threshold": 0.005,
            "peak_supersede_threshold": 0.03,
            "peak_measure": "body_top",
            "breakout_mode": "close",
        },
        "general_feature": {
            "atr_period": 14,
            "ma_period": 20,
            "stability_lookforward": 5,
        },
        "quality_scorer": {
            "factor_base_score": 50,
        },
    }
    loader = UIParamLoader.from_dict(raw)
    feat = loader.get_feature_calculator_params()
    assert feat["atr_period"] == 14
    assert feat["ma_period"] == 20
    assert feat["stability_lookforward"] == 5
