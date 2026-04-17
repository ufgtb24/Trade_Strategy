"""参数配置字典

定义所有参数的类型、范围、默认值和说明
驱动参数编辑器UI的生成
"""

from BreakoutStrategy.factor_registry import get_active_factors


def _build_factor_schemas() -> dict:
    """从 FACTOR_REGISTRY 动态生成因子 schema（UI 参数编辑器用）"""
    schemas = {}
    for fi in get_active_factors():
        element_type = int if fi.is_discrete else float
        schema = {
            "type": dict,
            "is_factor_group": True,
            "default": {
                "enabled": True,
                "thresholds": list(fi.default_thresholds),
                "values": list(fi.default_values),
            },
            "description": f"{fi.name} factor ({fi.cn_name})",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": f"Enable {fi.name} factor",
                },
                "thresholds": {
                    "type": list,
                    "element_type": element_type,
                    "default": list(fi.default_thresholds),
                    "description": "Threshold levels",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": list(fi.default_values),
                    "description": "Factor multipliers for each level",
                },
            },
        }
        # 添加因子特有的 sub_params（lookback, gain_window 等）
        for sp in fi.sub_params:
            schema["sub_params"][sp.yaml_name] = {
                "type": sp.param_type,
                "range": sp.range,
                "default": sp.default,
                "description": sp.description,
            }
        schemas[fi.yaml_key] = schema
    return schemas


# 参数配置字典
# 结构: {分组名: {参数名: {type, range, default, description}}}
PARAM_CONFIGS = {
    # 突破检测器参数
    "breakout_detector": {
        "total_window": {
            "type": int,
            "range": (2, 9999),
            "default": 10,
            "description": "Total window size (left + right bars)",
        },
        "min_side_bars": {
            "type": int,
            "range": (1, 9999),
            "default": 2,
            "description": "Minimum bars on each side of peak",
        },
        "min_relative_height": {
            "type": float,
            "range": (0.0, 1.0),
            "default": 0.05,
            "description": "Minimum relative height from window low (measure vs low)",
        },
        "peak_measure": {
            "type": str,
            "options": ["body_top", "high", "close"],
            "default": "body_top",
            "description": "Peak price definition: body_top=max(open,close), high, close",
        },
        "breakout_mode": {
            "type": str,
            "options": ["body_top", "high", "close"],
            "default": "body_top",
            "description": "Breakout confirmation mode: body_top, high, or close",
        },
        "exceed_threshold": {
            "type": float,
            "range": (0.0, 1.0),
            "default": 0.005,
            "description": "Threshold for breakout confirmation (ratio)",
        },
        "peak_supersede_threshold": {
            "type": float,
            "range": (0.0, 1.0),
            "default": 0.03,
            "description": "Resistance zone threshold: peak superseding & cluster grouping (ratio)",
        },
        "use_cache": {
            "type": bool,
            "default": False,
            "description": "Enable result caching",
        },
        "cache_dir": {
            "type": str,
            "default": "./cache",
            "description": "Cache directory path",
        },
    },
    # 通用特征参数
    "general_feature": {
        "atr_period": {
            "type": int,
            "range": (1, 9999),
            "default": 14,
            "description": "ATR calculation period",
        },
        "ma_period": {
            "type": int,
            "range": (5, 500),
            "default": 200,
            "description": "Moving Average period for trend filter (均线周期)",
        },
        "stability_lookforward": {
            "type": int,
            "range": (1, 9999),
            "default": 10,
            "description": "Forward-looking period for stability after breakout",
        },
    },
    # 质量评分器参数（Factor 乘法模型）
    "quality_scorer": {
        "factor_base_score": {
            "type": int,
            "range": (1, 9999),
            "default": 50,
            "description": "Base score for breakout quality",
        },
        # 因子 schema 从 FACTOR_REGISTRY 动态生成
        **_build_factor_schemas(),
    },
}


# 分组显示名称映射（用于UI显示）
SECTION_TITLES = {
    "breakout_detector": "Breakout Detector",
    "general_feature": "General Feature",
    "quality_scorer": "Quality Scorer",
}


def get_param_count(section_key: str) -> int:
    """
    获取指定分组的参数数量（递归计算，包括子参数）

    Args:
        section_key: 分组键，如 'breakout_detector'

    Returns:
        参数总数
    """
    if section_key not in PARAM_CONFIGS:
        return 0

    section = PARAM_CONFIGS[section_key]
    count = 0

    for param_name, param_config in section.items():
        param_type = param_config.get("type")
        if param_type == dict and "sub_params" in param_config:
            # 有子参数的字典（如权重组）
            count += len(param_config["sub_params"])
        else:
            # 普通参数
            count += 1

    return count


def get_weight_groups() -> list:
    """
    获取所有权重组的完整参数名（格式：section_key.param_name）

    权重组的特征：
    - type == dict
    - is_weight_group == True

    Returns:
        权重组名称列表，如 ['quality_scorer.peak_weights', 'quality_scorer.breakout_weights']
    """
    weight_groups = []

    for section_key, section in PARAM_CONFIGS.items():
        for param_name, param_config in section.items():
            if param_config.get("type") == dict and param_config.get(
                "is_weight_group", False
            ):
                weight_groups.append(f"{section_key}.{param_name}")

    return weight_groups


def get_weight_group_names() -> list:
    """
    获取所有权重组的参数名（不含section前缀）

    Returns:
        权重组名称列表，如 ['peak_weights', 'breakout_weights', 'resistance_weights']
    """
    weight_group_names = []

    for section_key, section in PARAM_CONFIGS.items():
        for param_name, param_config in section.items():
            if param_config.get("type") == dict and param_config.get(
                "is_weight_group", False
            ):
                weight_group_names.append(param_name)

    return weight_group_names


def get_default_params() -> dict:
    """
    获取所有参数的默认值（用于Reset to Default功能）

    Returns:
        默认参数字典
    """
    defaults = {}

    for section_key, section in PARAM_CONFIGS.items():
        defaults[section_key] = {}

        for param_name, param_config in section.items():
            param_type = param_config.get("type")
            if param_type == dict and "sub_params" in param_config:
                # 字典类型，提取子参数的默认值
                defaults[section_key][param_name] = {}
                for sub_name, sub_config in param_config["sub_params"].items():
                    defaults[section_key][param_name][sub_name] = sub_config.get(
                        "default"
                    )
            else:
                # 普通参数
                defaults[section_key][param_name] = param_config.get("default")

    return defaults
