"""ParamLoader 核心能力测试。

只覆盖"纯策略参数加载"职责：加载、解析、验证、from_dict、parse_params。
不测 UI 状态（监听器、钩子、活跃文件）——那部分已迁到 dev.config.param_editor_state。
"""
from pathlib import Path

import pytest

from BreakoutStrategy.param_loader import ParamLoader, get_param_loader


SAMPLE_PARAMS = {
    "breakout_detector": {
        "total_window": 10,
        "min_side_bars": 2,
        "min_relative_height": 0.05,
        "exceed_threshold": 0.005,
        "peak_supersede_threshold": 0.03,
        "peak_measure": "body_top",
        "breakout_mode": "body_top",
        "use_cache": False,
        "cache_dir": "./cache",
    },
    "general_feature": {
        "stability_lookforward": 10,
        "atr_period": 14,
        "ma_period": 200,
    },
    "quality_scorer": {
        "factor_base_score": 50,
        "atr_normalization": {"enabled": False, "thresholds": [1.5, 2.5], "values": [1.1, 1.2]},
    },
}


def test_from_dict_constructs_instance_without_file_io():
    loader = ParamLoader.from_dict(SAMPLE_PARAMS)
    assert loader.get_all_params() == SAMPLE_PARAMS


def test_get_detector_params_validates_and_returns_defaults():
    loader = ParamLoader.from_dict(SAMPLE_PARAMS)
    params = loader.get_detector_params()
    assert params["total_window"] == 10
    assert params["min_side_bars"] == 2
    assert params["peak_measure"] == "body_top"


def test_get_feature_calculator_params_returns_dict():
    loader = ParamLoader.from_dict(SAMPLE_PARAMS)
    params = loader.get_feature_calculator_params()
    assert params["atr_period"] == 14
    assert params["ma_period"] == 200
    assert params["stability_lookforward"] == 10


def test_get_scorer_params_returns_dict():
    loader = ParamLoader.from_dict(SAMPLE_PARAMS)
    params = loader.get_scorer_params()
    assert params["factor_base_score"] == 50


def test_parse_params_classmethod_returns_three_param_groups():
    detector, feat, scorer = ParamLoader.parse_params(SAMPLE_PARAMS)
    assert detector["total_window"] == 10
    assert feat["atr_period"] == 14
    assert "factor_base_score" in scorer


def test_get_param_loader_returns_singleton():
    a = get_param_loader()
    b = get_param_loader()
    assert a is b


def test_class_has_no_ui_state_methods():
    """ParamLoader 不应含监听器/钩子/活跃文件等 UI 状态机制。"""
    forbidden = [
        "add_listener", "remove_listener", "_notify_listeners",
        "add_before_switch_hook", "remove_before_switch_hook", "_run_before_switch_hooks",
        "set_active_file", "get_active_file", "get_active_file_name", "mark_saved",
        "is_memory_only", "request_file_switch",
        "update_memory_params", "save_params",
    ]
    for name in forbidden:
        assert not hasattr(ParamLoader, name), \
            f"ParamLoader should not have UI state method '{name}' (belongs to dev.ParamEditorState)"
