"""参数配置字典

定义所有参数的类型、范围、默认值和说明
驱动参数编辑器UI的生成
"""

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
        "breakout_modes": {
            "type": list,
            "options": ["body_top", "high", "close"],
            "default": ["body_top"],
            "multi_select": True,
            "description": "Breakout confirmation modes (any selected triggers)",
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
        "streak_window": {
            "type": int,
            "range": (1, 9999),
            "default": 20,
            "description": "Window for counting recent breakouts (streak bonus)",
        },
    },
    # 特征计算器参数
    "feature_calculator": {
        "stability_lookforward": {
            "type": int,
            "range": (1, 9999),
            "default": 10,
            "description": "Forward-looking period for stability after breakout",
        },
        "continuity_lookback": {
            "type": int,
            "range": (1, 9999),
            "default": 5,
            "description": "Lookback period for continuity analysis",
        },
        "atr_period": {
            "type": int,
            "range": (1, 9999),
            "default": 14,
            "description": "ATR calculation period",
        },
        "gain_window": {
            "type": int,
            "range": (1, 30),
            "default": 5,
            "description": "Window for gain calculation (days, used for gain_5d)",
        },
        "pk_lookback": {
            "type": int,
            "range": (1, 9999),
            "default": 30,
            "description": "Time window for pk_momentum (recent peak detection)",
        },
        "ma_period": {
            "type": int,
            "range": (5, 500),
            "default": 200,
            "description": "Moving Average period for trend filter (均线周期)",
        },
    },
    # 质量评分器参数（Bonus 乘法模型）
    "quality_scorer": {
        "bonus_base_score": {
            "type": int,
            "range": (1, 9999),
            "default": 50,
            "description": "Base score for breakout (multiplied by bonuses)",
        },
        # Bonus 配置组
        "age_bonus": {
            "type": dict,
            "is_bonus_group": True,  # 标记为 Bonus 配置组
            "default": {
                "enabled": True,
                "thresholds": [21, 63, 252],
                "values": [1.15, 1.30, 1.50],
            },
            "description": "Age bonus (远期 > 近期): thresholds in days, values are multipliers",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable age bonus",
                },
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
                "enabled": True,
                "thresholds": [2, 3, 4],
                "values": [1.10, 1.25, 1.40],
            },
            "description": "Test count bonus (多次测试 > 单次): thresholds are peak counts",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable test count bonus",
                },
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
                "enabled": True,
                "thresholds": [0.10, 0.20],
                "values": [1.15, 1.30],
            },
            "description": "Height bonus (高位 > 低位): thresholds are relative height ratios",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable height bonus",
                },
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
                "enabled": True,
                "thresholds": [2.0, 4.0],
                "values": [1.15, 1.30],
            },
            "description": "Peak Volume bonus (峰值放量): thresholds are volume surge ratios",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable peak volume bonus",
                },
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
                "enabled": True,
                "thresholds": [1.5, 2.0],
                "values": [1.15, 1.30],
            },
            "description": "Volume bonus (放量突破): thresholds are volume surge ratios",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable volume bonus",
                },
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
        "pbm_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "enabled": True,
                "thresholds": [0.70, 1.45],
                "values": [1.15, 1.30],
            },
            "description": "PBM bonus (突破前涨势): thresholds in σ_N units (N-day expected volatility)",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable PBM bonus",
                },
                "thresholds": {
                    "type": list,
                    "element_type": float,
                    "default": [0.70, 1.45],
                    "description": "Threshold levels in σN (0.70σN=涨势, 1.45σN=强劲涨势)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.15, 1.30],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "streak_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "enabled": True,
                "thresholds": [2, 4],
                "values": [1.20, 1.40],
            },
            "description": "Streak bonus (连续突破): thresholds are breakout counts",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable streak bonus",
                },
                "thresholds": {
                    "type": list,
                    "element_type": int,
                    "default": [2, 4],
                    "description": "Threshold levels (2+ breakouts, 4+ strong trend)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.20, 1.40],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "drought_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "enabled": True,
                "thresholds": [60, 120],
                "values": [1.15, 1.30],
            },
            "description": "Drought bonus (久旱逢甘霖): thresholds in trading days since last breakout",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable drought bonus",
                },
                "thresholds": {
                    "type": list,
                    "element_type": int,
                    "default": [60, 120],
                    "description": "Threshold levels (60d ~3mo, 120d ~6mo)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.15, 1.30],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "overshoot_penalty": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "enabled": True,
                "thresholds": [3.0, 4.0],
                "values": [0.80, 0.60],
            },
            "description": "Overshoot penalty (超涨惩罚): ratio = gain_5d / five_day_vol, unit: σ",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable overshoot penalty",
                },
                "thresholds": {
                    "type": list,
                    "element_type": float,
                    "default": [3.0, 4.0],
                    "description": "Threshold levels (3σ, 4σ)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [0.80, 0.60],
                    "description": "Penalty multipliers for each level (< 1.0)",
                },
            },
        },
        "breakout_day_strength_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "enabled": True,
                "thresholds": [1.5, 2.5],
                "values": [1.10, 1.20],
            },
            "description": "Breakout Day Strength bonus (突破日强度): max(IDR-Vol, Gap-Vol) in σ",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable breakout day strength bonus",
                },
                "thresholds": {
                    "type": list,
                    "element_type": float,
                    "default": [1.5, 2.5],
                    "description": "Threshold levels (1.5σ, 2.5σ)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.10, 1.20],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
        "pk_momentum_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "enabled": True,
                "thresholds": [1.5, 2.0],
                "values": [1.15, 1.25],
            },
            "description": "PK Momentum bonus (近期peak凹陷): pk_momentum = 1 + log(1 + D_atr)",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable PK momentum bonus",
                },
                "thresholds": {
                    "type": list,
                    "element_type": float,
                    "default": [1.5, 2.0],
                    "description": "Threshold levels (1.5=中等凹陷, 2.0=深凹陷)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.15, 1.25],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
    },
}


# 分组显示名称映射（用于UI显示）
SECTION_TITLES = {
    "breakout_detector": "Breakout Detector",
    "feature_calculator": "Feature Calculator",
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
