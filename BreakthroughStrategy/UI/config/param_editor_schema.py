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
            "range": (0.0, 1.0),
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
    # 质量评分器参数（全 Bonus 乘法模型版）
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
        "cluster_density_threshold": {
            "type": float,
            "range": (0.01, 0.10),
            "default": 0.03,
            "description": "Price proximity threshold for clustering peaks (%)",
        },
        "bonus_base_score": {
            "type": int,
            "range": (10, 100),
            "default": 50,
            "description": "Base score for breakthrough (multiplied by bonuses)",
        },
        # Bonus 配置组
        "age_bonus": {
            "type": dict,
            "is_bonus_group": True,  # 标记为 Bonus 配置组
            "default": {
                "thresholds": [21, 63, 252],
                "values": [1.15, 1.30, 1.50],
            },
            "description": "Age bonus (远期 > 近期): thresholds in days, values are multipliers",
            "sub_params": {
                "thresholds": {
                    "type": list,
                    "element_type": int,
                    "default": [21, 63, 252],
                    "description": "Threshold levels (1mo, 3mo, 1yr)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.15, 1.30, 1.50],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "test_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "thresholds": [2, 3, 4],
                "values": [1.10, 1.25, 1.40],
            },
            "description": "Test count bonus (多次测试 > 单次): thresholds are peak counts",
            "sub_params": {
                "thresholds": {
                    "type": list,
                    "element_type": int,
                    "default": [2, 3, 4],
                    "description": "Threshold levels (2x, 3x, 4x tests)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.10, 1.25, 1.40],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "height_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "thresholds": [0.10, 0.20],
                "values": [1.15, 1.30],
            },
            "description": "Height bonus (高位 > 低位): thresholds are relative height ratios",
            "sub_params": {
                "thresholds": {
                    "type": list,
                    "element_type": float,
                    "default": [0.10, 0.20],
                    "description": "Threshold levels (10%, 20%)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.15, 1.30],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "peak_volume_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "thresholds": [2.0, 4.0],
                "values": [1.15, 1.30],
            },
            "description": "Peak Volume bonus (峰值放量): thresholds are volume surge ratios",
            "sub_params": {
                "thresholds": {
                    "type": list,
                    "element_type": float,
                    "default": [2.0, 4.0],
                    "description": "Threshold levels (2x, 4x volume)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.15, 1.30],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "volume_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "thresholds": [1.5, 2.0],
                "values": [1.15, 1.30],
            },
            "description": "Volume bonus (放量突破): thresholds are volume surge ratios",
            "sub_params": {
                "thresholds": {
                    "type": list,
                    "element_type": float,
                    "default": [1.5, 2.0],
                    "description": "Threshold levels (1.5x, 2.0x volume)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.15, 1.30],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "gap_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "thresholds": [0.01, 0.02],
                "values": [1.10, 1.20],
            },
            "description": "Gap bonus (跳空突破): thresholds are gap percentages",
            "sub_params": {
                "thresholds": {
                    "type": list,
                    "element_type": float,
                    "default": [0.01, 0.02],
                    "description": "Threshold levels (1%, 2% gap)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.10, 1.20],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "continuity_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "thresholds": [3],
                "values": [1.15],
            },
            "description": "Continuity bonus (连续阳线): thresholds are day counts",
            "sub_params": {
                "thresholds": {
                    "type": list,
                    "element_type": int,
                    "default": [3],
                    "description": "Threshold levels (3+ days)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.15],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "momentum_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "thresholds": [2],
                "values": [1.20],
            },
            "description": "Momentum bonus (连续突破): thresholds are breakthrough counts",
            "sub_params": {
                "thresholds": {
                    "type": list,
                    "element_type": int,
                    "default": [2],
                    "description": "Threshold levels (2+ breakthroughs)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.20],
                    "description": "Bonus multipliers for each level",
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
