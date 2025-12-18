"""
Configuration Loader for Breakthrough Strategy

Provides centralized configuration loading from YAML files.
"""

import yaml
from pathlib import Path
from typing import Optional, Dict, Any


class ConfigLoader:
    """Configuration loader for breakthrough strategy parameters"""

    def __init__(self, config_path: Optional[str] = None, params_path: Optional[str] = None):
        """
        Initialize configuration loader

        Args:
            config_path: Path to config file. If None, uses default configs/analysis/config.yaml
            params_path: Path to params file. If None, uses the path specified in config_path
        """
        if config_path is None:
            # Find project root (go up from this file)
            current_file = Path(__file__)
            project_root = current_file.parent.parent
            config_path = project_root / 'configs' / 'analysis' / 'config.yaml'
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self.config = self._load_config()

        # Load params config
        if params_path is None:
            # Get params path from config
            params_file = self.config.get('params', {}).get('config_file', 'configs/analysis/params/breakthrough_0.yaml')
            current_file = Path(__file__)
            project_root = current_file.parent.parent
            params_path = project_root / params_file
        else:
            params_path = Path(params_path)

        self.params_path = params_path
        self.params = self._load_params()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        return config

    def _load_params(self) -> Dict[str, Any]:
        """Load params configuration from YAML file"""
        if not self.params_path.exists():
            raise FileNotFoundError(f"Params file not found: {self.params_path}")

        with open(self.params_path, 'r', encoding='utf-8') as f:
            params = yaml.safe_load(f)

        return params

    def get_detector_config(self) -> Dict[str, Any]:
        """
        Get BreakthroughDetector configuration

        Returns:
            Dictionary with: total_window, min_side_bars, min_relative_height,
                           exceed_threshold, peak_supersede_threshold, use_cache, cache_dir
        """
        detector_cfg = self.params.get('breakthrough_detector', {})
        return {
            'total_window': detector_cfg.get('total_window', 10),
            'min_side_bars': detector_cfg.get('min_side_bars', 2),
            'min_relative_height': detector_cfg.get('min_relative_height', 0.05),
            'exceed_threshold': detector_cfg.get('exceed_threshold', 0.005),
            'peak_supersede_threshold': detector_cfg.get('peak_supersede_threshold', 0.03),
            'use_cache': detector_cfg.get('use_cache', False),
            'cache_dir': detector_cfg.get('cache_dir', './cache')
        }

    def get_feature_calculator_config(self) -> Dict[str, Any]:
        """
        Get FeatureCalculator configuration

        Returns:
            Dictionary with: stability_lookforward, continuity_lookback
        """
        feature_cfg = self.params.get('feature_calculator', {})
        return {
            'stability_lookforward': feature_cfg.get('stability_lookforward', 10),
            'continuity_lookback': feature_cfg.get('continuity_lookback', 5)
        }

    def get_quality_scorer_config(self) -> Dict[str, Any]:
        """
        Get QualityScorer configuration (双维度时间模型版)

        Returns:
            Dictionary with all scoring weights and thresholds
        """
        scorer_cfg = self.params.get('quality_scorer', {})

        # Peak weights (仅保留筹码堆积因子：volume + candle)
        peak_weights = scorer_cfg.get('peak_weights', {})
        peak_weight_volume = peak_weights.get('volume', 0.60)
        peak_weight_candle = peak_weights.get('candle', 0.40)

        # Breakthrough weights (新增 historical)
        bt_weights = scorer_cfg.get('breakthrough_weights', {})
        bt_weight_change = bt_weights.get('change', 0.15)
        bt_weight_gap = bt_weights.get('gap', 0.08)
        bt_weight_volume = bt_weights.get('volume', 0.17)
        bt_weight_continuity = bt_weights.get('continuity', 0.12)
        bt_weight_stability = bt_weights.get('stability', 0.13)
        bt_weight_resistance = bt_weights.get('resistance', 0.18)
        bt_weight_historical = bt_weights.get('historical', 0.17)

        # Resistance weights (Phase 1: recency 已整合入 quality)
        res_weights = scorer_cfg.get('resistance_weights', {})
        res_weight_quantity = res_weights.get('quantity', 0.30)
        res_weight_density = res_weights.get('density', 0.30)
        res_weight_quality = res_weights.get('quality', 0.40)

        # Historical weights (relative_height 替换 suppression_span)
        hist_weights = scorer_cfg.get('historical_weights', {})
        hist_weight_oldest_age = hist_weights.get('oldest_age', 0.55)
        hist_weight_relative_height = hist_weights.get('relative_height', 0.45)

        # Time parameters (单位：交易日)
        # 支持两种格式：嵌套在 time_params 或直接在 quality_scorer 下
        time_params = scorer_cfg.get('time_params', {})
        time_decay_half_life = (
            time_params.get('decay_half_life') or
            scorer_cfg.get('time_decay_half_life', 84)
        )
        historical_significance_saturation = (
            time_params.get('significance_saturation') or
            scorer_cfg.get('historical_significance_saturation', 252)
        )
        time_decay_baseline = scorer_cfg.get('time_decay_baseline', 0.3)

        # Phase 2: 条件性历史加成 - 质量阈值
        historical_quality_threshold = scorer_cfg.get('historical_quality_threshold', 70)

        return {
            # Peak weights (仅 volume + candle)
            'peak_weight_volume': peak_weight_volume,
            'peak_weight_candle': peak_weight_candle,

            # Breakthrough weights
            'bt_weight_change': bt_weight_change,
            'bt_weight_gap': bt_weight_gap,
            'bt_weight_volume': bt_weight_volume,
            'bt_weight_continuity': bt_weight_continuity,
            'bt_weight_stability': bt_weight_stability,
            'bt_weight_resistance': bt_weight_resistance,
            'bt_weight_historical': bt_weight_historical,

            # Resistance weights (Phase 1: recency 已整合入 quality)
            'res_weight_quantity': res_weight_quantity,
            'res_weight_density': res_weight_density,
            'res_weight_quality': res_weight_quality,

            # Historical weights (relative_height 替换 suppression_span)
            'hist_weight_oldest_age': hist_weight_oldest_age,
            'hist_weight_relative_height': hist_weight_relative_height,

            # Time parameters
            'time_decay_half_life': time_decay_half_life,
            'time_decay_baseline': time_decay_baseline,
            'historical_significance_saturation': historical_significance_saturation,

            # Phase 2: 条件性历史加成
            'historical_quality_threshold': historical_quality_threshold
        }

    def get_scan_config(self) -> Dict[str, Any]:
        """
        Get scanning configuration

        Returns:
            Dictionary with: data_dir, output_dir, num_workers, max_stocks
        """
        data_cfg = self.config.get('data', {})
        output_cfg = self.config.get('output', {})
        perf_cfg = self.config.get('performance', {})

        return {
            'data_dir': data_cfg.get('data_dir', 'datasets/test_pkls'),
            'max_stocks': data_cfg.get('max_stocks', None),
            'output_dir': output_cfg.get('output_dir', 'outputs/analysis'),
            'num_workers': perf_cfg.get('num_workers', 8),
        }

    def get_all_config(self) -> Dict[str, Any]:
        """Get the complete configuration dictionary"""
        return self.config


# Global config loader instance (lazy initialization)
_global_config_loader: Optional[ConfigLoader] = None


def get_config_loader(config_path: Optional[str] = None) -> ConfigLoader:
    """
    Get global configuration loader instance

    Args:
        config_path: Optional path to config file. If None, uses default.

    Returns:
        ConfigLoader instance
    """
    global _global_config_loader

    if _global_config_loader is None or config_path is not None:
        _global_config_loader = ConfigLoader(config_path)

    return _global_config_loader
