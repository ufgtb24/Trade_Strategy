"""参数配置字典

定义所有参数的类型、范围、默认值和说明
驱动参数编辑器UI的生成
"""

# 参数配置字典
# 结构: {分组名: {参数名: {type, range, default, description}}}
PARAM_CONFIGS = {
    # 突破检测器参数
    "breakthrough_detector": {
        "total_window": {
            "type": int,
            "range": (6, 30),
            "default": 10,
            "description": "Total window size (left + right bars)",
        },
        "min_side_bars": {
            "type": int,
            "range": (1, 10),
            "default": 2,
            "description": "Minimum bars on each side of peak",
        },
        "min_relative_height": {
            "type": float,
            "range": (0.0, 0.3),
            "default": 0.05,
            "description": "Minimum relative height from window low",
        },
        "exceed_threshold": {
            "type": float,
            "range": (0.001, 0.02),
            "default": 0.005,
            "description": "Threshold for breakthrough confirmation (ratio)",
        },
        "peak_supersede_threshold": {
            "type": float,
            "range": (0.01, 0.1),
            "default": 0.03,
            "description": "Threshold for superseding old peaks when new peaks exceed them (ratio)",
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
    # 特征计算器参数
    "feature_calculator": {
        "stability_lookforward": {
            "type": int,
            "range": (5, 30),
            "default": 10,
            "description": "Forward-looking period for stability after breakthrough",
        },
        "continuity_lookback": {
            "type": int,
            "range": (1, 10),
            "default": 5,
            "description": "Lookback period for continuity analysis",
        },
    },
    # 质量评分器参数（双维度时间模型版）
    "quality_scorer": {
        "peak_weights": {
            "type": dict,
            "is_weight_group": True,  # 标记为权重组，总和必须为1.0
            "default": {
                "volume": 0.60,
                "candle": 0.40,
            },
            "description": "Peak quality scoring weights (筹码堆积因子, sum must = 1.0)",
            "sub_params": {
                "volume": {
                    "type": float,
                    "range": (0.0, 1.0),
                    "default": 0.60,
                    "description": "Volume surge weight (reflects trading density)",
                },
                "candle": {
                    "type": float,
                    "range": (0.0, 1.0),
                    "default": 0.40,
                    "description": "Candle pattern weight (reflects price intensity)",
                },
            },
        },
        "breakthrough_weights": {
            "type": dict,
            "is_weight_group": True,
            "default": {
                "change": 0.05,
                "gap": 0.0,
                "volume": 0.15,
                "continuity": 0.10,
                "stability": 0.0,
                "resistance": 0.50,  # 合并原 resistance + historical
                "momentum": 0.20,
            },
            "description": "Breakthrough quality scoring weights (sum must = 1.0)",
            "sub_params": {
                "change": {
                    "type": float,
                    "range": (0.0, 1.0),
                    "default": 0.05,
                    "description": "Price change weight",
                },
                "gap": {
                    "type": float,
                    "range": (0.0, 1.0),
                    "default": 0.0,
                    "description": "Gap weight",
                },
                "volume": {
                    "type": float,
                    "range": (0.0, 1.0),
                    "default": 0.15,
                    "description": "Volume weight",
                },
                "continuity": {
                    "type": float,
                    "range": (0.0, 1.0),
                    "default": 0.10,
                    "description": "Continuity weight",
                },
                "stability": {
                    "type": float,
                    "range": (0.0, 1.0),
                    "default": 0.0,
                    "description": "Stability weight",
                },
                "resistance": {
                    "type": float,
                    "range": (0.0, 1.0),
                    "default": 0.50,
                    "description": "Resistance importance weight (merged resistance + historical)",
                },
                "momentum": {
                    "type": float,
                    "range": (0.0, 1.0),
                    "default": 0.20,
                    "description": "Momentum weight (consecutive breakthroughs bonus)",
                },
            },
        },
        "resistance_importance": {
            "type": dict,
            "is_weight_group": False,  # 不是权重组，是参数组
            "default": {
                "cluster_density_threshold": 0.03,
                "age_base_days": 21,
                "age_saturation_days": 504,
            },
            "description": "Resistance importance calculation parameters (new architecture)",
            "sub_params": {
                "cluster_density_threshold": {
                    "type": float,
                    "range": (0.01, 0.10),
                    "default": 0.03,
                    "description": "Price proximity threshold for clustering peaks (%)",
                },
                "age_base_days": {
                    "type": int,
                    "range": (7, 63),
                    "default": 21,
                    "description": "Base age for scoring (trading days, 21≈1mo)",
                },
                "age_saturation_days": {
                    "type": int,
                    "range": (252, 756),
                    "default": 504,
                    "description": "Saturation age for max score (trading days, 504≈2yr)",
                },
            },
        },
    },
}


# 分组显示名称映射（用于UI显示）
SECTION_TITLES = {
    "breakthrough_detector": "Breakthrough Detector",
    "feature_calculator": "Feature Calculator",
    "quality_scorer": "Quality Scorer",
}


def get_param_count(section_key: str) -> int:
    """
    获取指定分组的参数数量（递归计算，包括子参数）

    Args:
        section_key: 分组键，如 'breakthrough_detector'

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
        权重组名称列表，如 ['quality_scorer.peak_weights', 'quality_scorer.breakthrough_weights']
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
        权重组名称列表，如 ['peak_weights', 'breakthrough_weights', 'resistance_weights']
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
