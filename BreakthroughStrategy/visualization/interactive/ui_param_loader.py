"""UI参数加载器"""

import yaml
import shutil
from pathlib import Path
from typing import Dict, Any, Optional


class UIParamLoader:
    """UI参数加载器（单例模式）"""

    _instance = None
    _params = None
    _project_root = None
    _params_path = None

    def __new__(cls, params_path: Optional[str] = None):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, params_path: Optional[str] = None):
        """
        初始化参数加载器

        Args:
            params_path: 参数文件路径（可选）
        """
        # 如果提供了新的路径，强制重新加载
        force_reload = (params_path is not None and
                       self._params_path is not None and
                       Path(params_path) != self._params_path)

        if self._params is not None and not force_reload:
            return  # 已初始化且不需要重新加载，跳过

        # 计算项目根目录
        current_file = Path(__file__)
        # 当前文件: .../Trade_Strategy/BreakthroughStrategy/visualization/interactive/ui_param_loader.py
        # 项目根目录: .../Trade_Strategy
        self._project_root = current_file.parent.parent.parent.parent

        if params_path is None:
            # 默认路径：项目根目录/configs/analysis/params/ui_params.yaml
            params_path = self._project_root / "configs" / "analysis" / "params" / "ui_params.yaml"
        else:
            params_path = Path(params_path)

        self._params_path = params_path

        # 如果 ui_params.yaml 不存在，从模板复制创建
        if not self._params_path.exists():
            self._create_from_template()

        # 加载参数
        self._params = self._load_params()

    def _create_from_template(self):
        """从 breakthrough_0.yaml 复制创建 ui_params.yaml"""
        template_path = self._project_root / "configs" / "analysis" / "params" / "breakthrough_0.yaml"

        if not template_path.exists():
            raise FileNotFoundError(
                f"模板文件不存在: {template_path}\n"
                "请确保 configs/analysis/params/breakthrough_0.yaml 文件存在"
            )

        # 确保目标目录存在
        self._params_path.parent.mkdir(parents=True, exist_ok=True)

        # 复制文件
        shutil.copy2(template_path, self._params_path)
        print(f"已创建UI参数文件: {self._params_path}")

    def _load_params(self) -> Dict[str, Any]:
        """加载参数文件"""
        try:
            with open(self._params_path, "r", encoding="utf-8") as f:
                params = yaml.safe_load(f)

            if params is None:
                raise ValueError("参数文件为空")

            return params

        except yaml.YAMLError as e:
            raise ValueError(f"YAML格式错误: {e}")
        except Exception as e:
            raise RuntimeError(f"加载参数文件失败: {e}")

    def reload_params(self):
        """重新从文件加载参数"""
        self._params = self._load_params()

    def get_project_root(self) -> Path:
        """
        获取项目根目录

        Returns:
            项目根目录的绝对路径
        """
        return self._project_root

    def get_detector_params(self) -> Dict[str, Any]:
        """
        获取 BreakthroughDetector 参数（带验证）

        Returns:
            参数字典，包含: window, exceed_threshold, peak_merge_threshold, use_cache, cache_dir
        """
        detector_params = self._params.get('breakthrough_detector', {})

        # 参数验证和默认值
        validated = {
            'window': self._validate_int(detector_params.get('window', 5), 3, 20, 5),
            'exceed_threshold': self._validate_float(
                detector_params.get('exceed_threshold', 0.005), 0.001, 0.02, 0.005
            ),
            'peak_merge_threshold': self._validate_float(
                detector_params.get('peak_merge_threshold', 0.03), 0.01, 0.1, 0.03
            ),
            'use_cache': bool(detector_params.get('use_cache', False)),
            'cache_dir': str(detector_params.get('cache_dir', './cache'))
        }

        return validated

    def get_all_params(self) -> Dict[str, Any]:
        """
        获取完整参数配置

        Returns:
            完整配置字典
        """
        return self._params.copy()

    def save_params(self, params: Dict[str, Any]):
        """
        保存参数到文件

        Args:
            params: 参数字典（只需要包含要更新的 breakthrough_detector 参数）
        """
        # 更新 breakthrough_detector 部分
        if 'breakthrough_detector' not in self._params:
            self._params['breakthrough_detector'] = {}

        for key, value in params.items():
            self._params['breakthrough_detector'][key] = value

        # 写入文件
        try:
            with open(self._params_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._params, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            raise RuntimeError(f"保存参数文件失败: {e}")

    def get_feature_calculator_params(self) -> Dict[str, Any]:
        """
        获取 FeatureCalculator 参数

        Returns:
            参数字典，包含: stability_lookforward, continuity_lookback
        """
        feature_params = self._params.get('feature_calculator', {})

        validated = {
            'stability_lookforward': self._validate_int(
                feature_params.get('stability_lookforward', 10), 5, 30, 10
            ),
            'continuity_lookback': self._validate_int(
                feature_params.get('continuity_lookback', 5), 1, 10, 5
            ),
        }

        return validated

    def get_quality_scorer_params(self) -> Dict[str, Any]:
        """
        获取 QualityScorer 参数

        Returns:
            参数字典，包含所有权重值
        """
        quality_params = self._params.get('quality_scorer', {})

        # Peak weights
        peak_weights = quality_params.get('peak_weights', {})
        validated = {
            'peak_weight_volume': self._validate_float(
                peak_weights.get('volume', 0.25), 0.0, 1.0, 0.25
            ),
            'peak_weight_candle': self._validate_float(
                peak_weights.get('candle', 0.20), 0.0, 1.0, 0.20
            ),
            'peak_weight_suppression': self._validate_float(
                peak_weights.get('suppression', 0.25), 0.0, 1.0, 0.25
            ),
            'peak_weight_height': self._validate_float(
                peak_weights.get('height', 0.15), 0.0, 1.0, 0.15
            ),
            'peak_weight_merged': self._validate_float(
                peak_weights.get('merged', 0.15), 0.0, 1.0, 0.15
            ),
        }

        # Breakthrough weights
        bt_weights = quality_params.get('breakthrough_weights', {})
        validated.update({
            'bt_weight_change': self._validate_float(
                bt_weights.get('change', 0.20), 0.0, 1.0, 0.20
            ),
            'bt_weight_gap': self._validate_float(
                bt_weights.get('gap', 0.10), 0.0, 1.0, 0.10
            ),
            'bt_weight_volume': self._validate_float(
                bt_weights.get('volume', 0.20), 0.0, 1.0, 0.20
            ),
            'bt_weight_continuity': self._validate_float(
                bt_weights.get('continuity', 0.15), 0.0, 1.0, 0.15
            ),
            'bt_weight_stability': self._validate_float(
                bt_weights.get('stability', 0.15), 0.0, 1.0, 0.15
            ),
            'bt_weight_resistance': self._validate_float(
                bt_weights.get('resistance', 0.20), 0.0, 1.0, 0.20
            ),
        })

        return validated

    def _validate_int(self, value, min_val: int, max_val: int, default: int) -> int:
        """
        验证整数参数

        Args:
            value: 待验证的值
            min_val: 最小值
            max_val: 最大值
            default: 默认值

        Returns:
            验证后的整数值
        """
        try:
            val = int(value)
            return max(min_val, min(max_val, val))
        except (TypeError, ValueError):
            return default

    def _validate_float(self, value, min_val: float, max_val: float, default: float) -> float:
        """
        验证浮点数参数

        Args:
            value: 待验证的值
            min_val: 最小值
            max_val: 最大值
            default: 默认值

        Returns:
            验证后的浮点数值
        """
        try:
            val = float(value)
            return max(min_val, min(max_val, val))
        except (TypeError, ValueError):
            return default


def get_ui_param_loader(params_path: Optional[str] = None) -> UIParamLoader:
    """
    获取全局UI参数加载器实例（单例模式）

    Args:
        params_path: 参数文件路径（可选）

    Returns:
        UIParamLoader实例
    """
    return UIParamLoader(params_path)
