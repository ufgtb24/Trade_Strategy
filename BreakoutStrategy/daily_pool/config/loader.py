"""
YAML 配置加载器

支持从 YAML 文件加载 DailyPoolConfig 配置。
"""
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from .config import (
    DailyPoolConfig,
    PhaseConfig,
    PricePatternConfig,
    VolatilityConfig,
    VolumeConfig,
    SignalConfig,
)


def load_config(yaml_path: Union[str, Path]) -> DailyPoolConfig:
    """
    从 YAML 文件加载配置

    Args:
        yaml_path: YAML 配置文件路径

    Returns:
        DailyPoolConfig 实例

    Raises:
        FileNotFoundError: 配置文件不存在
        yaml.YAMLError: YAML 解析错误
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    return _parse_config(data or {})


def _parse_config(data: Dict[str, Any]) -> DailyPoolConfig:
    """
    解析配置字典为 DailyPoolConfig

    Args:
        data: 从 YAML 加载的字典

    Returns:
        DailyPoolConfig 实例
    """
    return DailyPoolConfig(
        phase=_parse_phase_config(data.get('phase', {})),
        price_pattern=_parse_price_pattern_config(data.get('price_pattern', {})),
        volatility=_parse_volatility_config(data.get('volatility', {})),
        volume=_parse_volume_config(data.get('volume', {})),
        signal=_parse_signal_config(data.get('signal', {})),
        keep_history=data.get('global', {}).get('keep_history', True),
    )


def _parse_phase_config(data: Dict[str, Any]) -> PhaseConfig:
    """解析阶段配置"""
    return PhaseConfig(
        pullback_trigger_atr=data.get('pullback_trigger_atr', 0.3),
        min_convergence_score=data.get('min_convergence_score', 0.5),
        min_support_tests=data.get('min_support_tests', 2),
        min_volume_expansion=data.get('min_volume_expansion', 1.5),
        breakout_confirm_days=data.get('breakout_confirm_days', 1),
        max_drop_from_breakout_atr=data.get('max_drop_from_breakout_atr', 1.5),
        support_break_buffer_atr=data.get('support_break_buffer_atr', 0.5),
        max_pullback_days=data.get('max_pullback_days', 15),
        max_consolidation_days=data.get('max_consolidation_days', 20),
        max_observation_days=data.get('max_observation_days', 30),
    )


def _parse_price_pattern_config(data: Dict[str, Any]) -> PricePatternConfig:
    """解析价格模式配置"""
    support = data.get('support_detection', {})
    consolidation = data.get('consolidation', {})

    return PricePatternConfig(
        min_touches=support.get('min_touches', 2),
        touch_tolerance_atr=support.get('touch_tolerance_atr', 0.1),
        local_min_window=support.get('local_min_window', 2),
        consolidation_window=consolidation.get('window', 10),
        max_width_atr=consolidation.get('max_width_atr', 2.0),
    )


def _parse_volatility_config(data: Dict[str, Any]) -> VolatilityConfig:
    """解析波动率配置"""
    return VolatilityConfig(
        atr_period=data.get('atr_period', 14),
        lookback_days=data.get('lookback_days', 20),
        contraction_threshold=data.get('contraction_threshold', 0.8),
    )


def _parse_volume_config(data: Dict[str, Any]) -> VolumeConfig:
    """解析成交量配置"""
    return VolumeConfig(
        baseline_period=data.get('baseline_period', 20),
        expansion_threshold=data.get('expansion_threshold', 1.5),
    )


def _parse_signal_config(data: Dict[str, Any]) -> SignalConfig:
    """解析信号配置"""
    default_weights = {
        'convergence': 0.30,
        'support': 0.25,
        'volume': 0.25,
        'quality': 0.20,
    }
    default_sizing = {
        'strong': 0.15,
        'normal': 0.10,
        'weak': 0.05,
    }

    return SignalConfig(
        confidence_weights=data.get('confidence_weights', default_weights),
        position_sizing=data.get('position_sizing', default_sizing),
    )


def save_config(config: DailyPoolConfig, yaml_path: Union[str, Path]) -> None:
    """
    将配置保存到 YAML 文件

    Args:
        config: DailyPoolConfig 实例
        yaml_path: 目标 YAML 文件路径
    """
    path = Path(yaml_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = _config_to_dict(config)

    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _config_to_dict(config: DailyPoolConfig) -> Dict[str, Any]:
    """将配置转为字典"""
    return {
        'global': {
            'max_observation_days': config.phase.max_observation_days,
            'keep_history': config.keep_history,
        },
        'phase': {
            'pullback_trigger_atr': config.phase.pullback_trigger_atr,
            'min_convergence_score': config.phase.min_convergence_score,
            'min_support_tests': config.phase.min_support_tests,
            'min_volume_expansion': config.phase.min_volume_expansion,
            'breakout_confirm_days': config.phase.breakout_confirm_days,
            'max_drop_from_breakout_atr': config.phase.max_drop_from_breakout_atr,
            'support_break_buffer_atr': config.phase.support_break_buffer_atr,
            'max_pullback_days': config.phase.max_pullback_days,
            'max_consolidation_days': config.phase.max_consolidation_days,
        },
        'price_pattern': {
            'support_detection': {
                'min_touches': config.price_pattern.min_touches,
                'touch_tolerance_atr': config.price_pattern.touch_tolerance_atr,
                'local_min_window': config.price_pattern.local_min_window,
            },
            'consolidation': {
                'window': config.price_pattern.consolidation_window,
                'max_width_atr': config.price_pattern.max_width_atr,
            },
        },
        'volatility': {
            'atr_period': config.volatility.atr_period,
            'lookback_days': config.volatility.lookback_days,
            'contraction_threshold': config.volatility.contraction_threshold,
        },
        'volume': {
            'baseline_period': config.volume.baseline_period,
            'expansion_threshold': config.volume.expansion_threshold,
        },
        'signal': {
            'confidence_weights': config.signal.confidence_weights,
            'position_sizing': config.signal.position_sizing,
        },
    }
