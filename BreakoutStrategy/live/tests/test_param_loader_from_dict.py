"""Test ParamLoader.from_dict classmethod."""
from BreakoutStrategy.param_loader import ParamLoader


def test_from_dict_accepts_scan_params():
    """ParamLoader.from_dict 应接受 dict 并返回可用的 loader 实例。"""
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
    loader = ParamLoader.from_dict(raw)
    feat = loader.get_feature_calculator_params()
    assert feat["atr_period"] == 14
    assert feat["ma_period"] == 20
    assert feat["stability_lookforward"] == 5


def test_from_dict_does_not_corrupt_singleton():
    """from_dict 创建的实例必须独立于单例，不能污染已存在的单例状态。"""
    import yaml
    import tempfile
    from pathlib import Path

    # 1. 先创建单例（从文件）
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tf:
        yaml.dump({
            'breakout_detector': {
                'total_window': 10,
                'min_side_bars': 3,
                'min_relative_height': 0.05,
                'exceed_threshold': 0.003,
                'peak_supersede_threshold': 0.02,
                'peak_measure': 'high',
                'breakout_mode': 'high',
            },
            'general_feature': {
                'atr_period': 7,
                'ma_period': 50,
                'stability_lookforward': 3,
            },
            'quality_scorer': {'factor_base_score': 30},
        }, tf)
        singleton_path = tf.name

    try:
        singleton = ParamLoader(singleton_path)
        singleton_feat_before = singleton.get_feature_calculator_params()
        assert singleton_feat_before['atr_period'] == 7

        # 2. 用 from_dict 创建独立实例（用不同参数）
        dict_loader = ParamLoader.from_dict({
            'breakout_detector': {
                'total_window': 20,
                'min_side_bars': 6,
                'min_relative_height': 0.1,
                'exceed_threshold': 0.005,
                'peak_supersede_threshold': 0.03,
                'peak_measure': 'body_top',
                'breakout_mode': 'close',
            },
            'general_feature': {
                'atr_period': 99,  # 明显不同的值
                'ma_period': 200,
                'stability_lookforward': 10,
            },
            'quality_scorer': {'factor_base_score': 50},
        })

        # 3. 验证两个实例独立
        assert dict_loader.get_feature_calculator_params()['atr_period'] == 99
        assert dict_loader is not singleton, "from_dict 返回了单例，未创建独立实例"

        # 4. 验证单例状态未被破坏
        singleton_feat_after = singleton.get_feature_calculator_params()
        assert singleton_feat_after['atr_period'] == 7, \
            f"单例被 from_dict 污染: atr_period 从 7 变成 {singleton_feat_after['atr_period']}"
    finally:
        Path(singleton_path).unlink()
