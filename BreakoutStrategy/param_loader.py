"""策略参数加载器 (Strategy Parameter Loader, SSoT).

作为 breakout / feature_calculator / scorer 三套参数的单一真理来源
(Single Source of Truth)，从 YAML 文件或 dict 加载后对外提供校验后的
参数字典。

本模块只承担"参数加载 + 解析 + 验证"职责，不涉及：
- UI 编辑器状态（监听器、钩子、活跃文件、dirty 标志）→ 见
  BreakoutStrategy.dev.config.param_editor_state.ParamEditorState

调用方：
- analysis / mining / live.pipeline：通过 ParamLoader 取参数驱动扫描
- dev 编辑器：通过 ParamLoader 读，通过 ParamEditorState 管理 UI 状态
"""

import copy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from BreakoutStrategy.factor_registry import get_active_factors


class ParamLoader:
    """策略参数 SSoT（单例）。"""

    _instance: Optional["ParamLoader"] = None
    _params: Optional[Dict[str, Any]] = None
    _project_root: Optional[Path] = None
    _params_path: Optional[Path] = None

    def __new__(cls, params_path: Optional[str] = None) -> "ParamLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, params_path: Optional[str] = None):
        force_reload = (
            params_path is not None
            and self._params_path is not None
            and Path(params_path) != self._params_path
        )
        if self._params is not None and not force_reload:
            return

        current_file = Path(__file__)
        # .../Trade_Strategy/BreakoutStrategy/param_loader.py
        self._project_root = current_file.parent.parent

        if params_path is None:
            resolved = self._project_root / "configs" / "params" / "all_factor.yaml"
        else:
            resolved = Path(params_path)

        self._params_path = resolved

        if not self._params_path.exists():
            raise FileNotFoundError(
                f"参数文件不存在: {self._params_path}\n"
                "请确保 configs/params/all_factor.yaml 文件存在"
            )

        self._params = self._load_params()

    def _load_params(self) -> Dict[str, Any]:
        try:
            with open(self._params_path, "r", encoding="utf-8") as f:
                params = yaml.safe_load(f)
            if params is None:
                raise ValueError("参数文件为空")
            return params
        except yaml.YAMLError as e:
            raise ValueError(f"YAML格式错误: {e}")

    def reload_params(self) -> None:
        self._params = self._load_params()

    def get_project_root(self) -> Optional[Path]:
        return self._project_root

    def get_all_params(self) -> Dict[str, Any]:
        return copy.deepcopy(self._params) if self._params else {}

    def set_params_in_memory(self, params: Dict[str, Any]) -> None:
        """把 dict 写入内部状态，供 dev 编辑器的 Apply 操作使用。

        此方法不触发任何通知——通知由 dev.ParamEditorState 负责。
        """
        self._params = copy.deepcopy(params)

    def get_detector_params(self) -> Dict[str, Any]:
        detector_params = self._params.get("breakout_detector", {})

        total_window = self._validate_int(
            detector_params.get("total_window", 10), 2, 9999, 10
        )
        min_side_bars = self._validate_int(
            detector_params.get("min_side_bars", 2), 1, 9999, 2
        )
        if min_side_bars * 2 > total_window:
            min_side_bars = total_window // 2

        peak_measure = detector_params.get("peak_measure", "body_top")
        if peak_measure not in ("high", "close", "body_top"):
            peak_measure = "body_top"

        breakout_mode = detector_params.get("breakout_mode", "body_top")
        if breakout_mode not in ("high", "close", "body_top"):
            breakout_mode = "body_top"

        validated: Dict[str, Any] = {
            "total_window": total_window,
            "min_side_bars": min_side_bars,
            "min_relative_height": self._validate_float(
                detector_params.get("min_relative_height", 0.05), 0.0, 1.0, 0.05
            ),
            "exceed_threshold": self._validate_float(
                detector_params.get("exceed_threshold", 0.005), 0.0, 1.0, 0.005
            ),
            "peak_supersede_threshold": self._validate_float(
                detector_params.get("peak_supersede_threshold", 0.03), 0.0, 1.0, 0.03
            ),
            "peak_measure": peak_measure,
            "breakout_mode": breakout_mode,
            "use_cache": bool(detector_params.get("use_cache", False)),
            "cache_dir": str(detector_params.get("cache_dir", "./cache")),
        }

        quality_params = self._params.get("quality_scorer", {})
        for fi in get_active_factors():
            for sp in fi.sub_params:
                if sp.consumer == "detector":
                    raw_val = quality_params.get(fi.yaml_key, {}).get(sp.yaml_name, sp.default)
                    if sp.param_type is float:
                        validated[sp.internal_name] = self._validate_float(
                            raw_val, sp.range[0], sp.range[1], sp.default)
                    else:
                        validated[sp.internal_name] = self._validate_int(
                            raw_val, sp.range[0], sp.range[1], sp.default)
        return validated

    def get_feature_calculator_params(self) -> Dict[str, Any]:
        general_params = self._params.get("general_feature", {})
        quality_params = self._params.get("quality_scorer", {})

        validated: Dict[str, Any] = {
            "stability_lookforward": self._validate_int(
                general_params.get("stability_lookforward", 10), 1, 9999, 10
            ),
            "atr_period": self._validate_int(
                general_params.get("atr_period", 14), 1, 9999, 14
            ),
            "ma_period": self._validate_int(
                general_params.get("ma_period", 200), 5, 500, 200
            ),
        }

        for fi in get_active_factors():
            for sp in fi.sub_params:
                if sp.consumer == "feature_calculator":
                    raw_val = quality_params.get(fi.yaml_key, {}).get(sp.yaml_name, sp.default)
                    if sp.param_type is float:
                        validated[sp.internal_name] = self._validate_float(
                            raw_val, sp.range[0], sp.range[1], sp.default)
                    else:
                        validated[sp.internal_name] = self._validate_int(
                            raw_val, sp.range[0], sp.range[1], sp.default)

        atr_config = quality_params.get("atr_normalization", {})
        validated["use_atr_normalization"] = atr_config.get("enabled", False)
        return validated

    def get_scorer_params(self) -> Dict[str, Any]:
        quality_params = self._params.get("quality_scorer", {})
        validated: Dict[str, Any] = {}

        detector_params = self._params.get("breakout_detector", {})
        peak_supersede_threshold = self._validate_float(
            detector_params.get("peak_supersede_threshold", 0.03), 0.0, 1.0, 0.03
        )
        validated["peak_supersede_threshold"] = peak_supersede_threshold
        if "cluster_density_threshold" in quality_params:
            validated["cluster_density_threshold"] = self._validate_float(
                quality_params.get("cluster_density_threshold"), 0.0, 1.0, 0.03
            )

        validated["factor_base_score"] = self._validate_int(
            quality_params.get("factor_base_score", 50), 1, 9999, 50
        )

        atr_config = quality_params.get("atr_normalization", {})
        validated["use_atr_normalization"] = atr_config.get("enabled", False)
        validated["atr_normalized_height_thresholds"] = atr_config.get("thresholds", [1.5, 2.5])
        validated["atr_normalized_height_values"] = atr_config.get("values", [1.10, 1.20])

        for fi in get_active_factors():
            factor_cfg = quality_params.get(fi.yaml_key, {})
            validated[fi.yaml_key] = {
                "enabled": factor_cfg.get("enabled", True),
                "thresholds": factor_cfg.get("thresholds", list(fi.default_thresholds)),
                "values": factor_cfg.get("values", list(fi.default_values)),
                "mode": factor_cfg.get("mode", fi.mining_mode or "gte"),
            }
        return validated

    def _validate_int(self, value, min_val: int, max_val: int, default: int) -> int:
        try:
            val = int(value)
            return max(min_val, min(max_val, val))
        except (TypeError, ValueError):
            return default

    def _validate_float(self, value, min_val: float, max_val: float, default: float) -> float:
        try:
            val = float(value)
            return max(min_val, min(max_val, val))
        except (TypeError, ValueError):
            return default

    @classmethod
    def from_dict(cls, raw_params: Dict[str, Any]) -> "ParamLoader":
        """从 dict 构造，不走文件 I/O，不污染单例。"""
        instance = object.__new__(cls)
        instance._params_path = None
        instance._params = copy.deepcopy(raw_params)
        instance._project_root = None
        return instance

    @classmethod
    def parse_params(cls, raw_params: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """从原始 dict 解析三组扫描参数，不影响单例状态。"""
        temp = cls.from_dict(raw_params)
        return (
            temp.get_detector_params(),
            temp.get_feature_calculator_params(),
            temp.get_scorer_params(),
        )


def get_param_loader(params_path: Optional[str] = None) -> ParamLoader:
    """获取全局 ParamLoader 单例。"""
    return ParamLoader(params_path)
