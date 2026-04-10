"""UI参数加载器"""

import copy
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List

from BreakoutStrategy.factor_registry import get_active_factors


class UIParamLoader:
    """UI参数加载器（单例模式）

    作为参数状态的唯一真理来源（Single Source of Truth），
    管理当前活跃的参数文件和内存参数状态。
    """

    _instance = None
    _params = None
    _project_root = None
    _params_path = None  # 保留向后兼容

    # 新增：统一状态管理
    _active_file: Optional[Path] = None  # 当前活跃的参数文件
    _is_memory_only: bool = False  # 是否仅内存模式（未保存到文件）
    _listeners: List[Callable] = []  # 状态变化监听器（文件切换后通知）
    _before_switch_hooks: List[Callable[[Path], bool]] = []  # 文件切换前钩子

    def __new__(cls, params_path: Optional[str] = None):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._listeners = []  # 初始化监听器列表
            cls._instance._before_switch_hooks = []  # 初始化钩子列表
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
        # 当前文件: .../Trade_Strategy/BreakoutStrategy/UI/interactive/ui_param_loader.py
        # 项目根目录: .../Trade_Strategy
        self._project_root = current_file.parent.parent.parent.parent

        if params_path is None:
            # 默认路径：项目根目录/configs/params/all_factor.yaml
            params_path = self._project_root / "configs" / "params" / "all_factor.yaml"
        else:
            params_path = Path(params_path)

        self._params_path = params_path

        # 如果参数文件不存在，抛出错误
        if not self._params_path.exists():
            raise FileNotFoundError(
                f"参数文件不存在: {self._params_path}\n"
                "请确保 configs/params/all_factor.yaml 文件存在"
            )

        # 加载参数
        self._params = self._load_params()

        # 初始化活跃文件状态
        self._active_file = self._params_path
        self._is_memory_only = False

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
        获取 BreakoutDetector 参数（带验证）

        Returns:
            参数字典，包含: total_window, min_side_bars, min_relative_height,
                         exceed_threshold, peak_supersede_threshold,
                         peak_measure, breakout_mode, use_cache, cache_dir
        """
        detector_params = self._params.get('breakout_detector', {})

        # 参数验证和默认值（使用理论边界）
        total_window = self._validate_int(
            detector_params.get('total_window', 10), 2, 9999, 10
        )
        min_side_bars = self._validate_int(
            detector_params.get('min_side_bars', 2), 1, 9999, 2
        )

        # 约束验证：min_side_bars * 2 <= total_window
        if min_side_bars * 2 > total_window:
            min_side_bars = total_window // 2

        # peak_measure 验证
        peak_measure = detector_params.get('peak_measure', 'body_top')
        if peak_measure not in ['high', 'close', 'body_top']:
            peak_measure = 'body_top'

        # breakout_mode 验证
        breakout_mode = detector_params.get('breakout_mode', 'body_top')
        if breakout_mode not in ('high', 'close', 'body_top'):
            breakout_mode = 'body_top'

        validated = {
            'total_window': total_window,
            'min_side_bars': min_side_bars,
            'min_relative_height': self._validate_float(
                detector_params.get('min_relative_height', 0.05), 0.0, 1.0, 0.05
            ),
            'exceed_threshold': self._validate_float(
                detector_params.get('exceed_threshold', 0.005), 0.0, 1.0, 0.005
            ),
            'peak_supersede_threshold': self._validate_float(
                detector_params.get('peak_supersede_threshold', 0.03), 0.0, 1.0, 0.03
            ),
            'peak_measure': peak_measure,
            'breakout_mode': breakout_mode,
            'use_cache': bool(detector_params.get('use_cache', False)),
            'cache_dir': str(detector_params.get('cache_dir', './cache')),
        }

        # 从 FACTOR_REGISTRY sub_params 动态读取 detector 参数
        quality_params = self._params.get('quality_scorer', {})
        for fi in get_active_factors():
            for sp in fi.sub_params:
                if sp.consumer == 'detector':
                    raw_val = quality_params.get(fi.yaml_key, {}).get(sp.yaml_name, sp.default)
                    if sp.param_type is float:
                        validated[sp.internal_name] = self._validate_float(
                            raw_val, sp.range[0], sp.range[1], sp.default)
                    else:
                        validated[sp.internal_name] = self._validate_int(
                            raw_val, sp.range[0], sp.range[1], sp.default)

        return validated

    def get_all_params(self) -> Dict[str, Any]:
        """
        获取完整参数配置

        Returns:
            完整配置字典
        """
        return self._params.copy()

    def update_memory_params(self, params: Dict[str, Any], source_file: Optional[Path] = None):
        """
        更新内存参数（不保存文件）

        用于参数编辑器的 Apply 操作，仅更新内存中的参数，不影响磁盘文件

        Args:
            params: 完整的参数字典（包含所有 section）
            source_file: 参数来源文件（可选，用于同步 UI 显示）
        """
        # 深度拷贝，避免引用问题
        self._params = copy.deepcopy(params)

        # 更新活跃文件
        if source_file:
            self._active_file = source_file

        # 标记为仅内存模式（未保存）
        self._is_memory_only = True

        # 通知监听器
        self._notify_listeners()

    def save_params(self, params: Dict[str, Any]):
        """
        保存参数到文件（旧版本，保留向后兼容）

        Args:
            params: 参数字典（只需要包含要更新的 breakout_detector 参数）
        """
        # 更新 breakout_detector 部分
        if 'breakout_detector' not in self._params:
            self._params['breakout_detector'] = {}

        for key, value in params.items():
            self._params['breakout_detector'][key] = value

        # 写入文件
        try:
            with open(self._params_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._params, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            raise RuntimeError(f"保存参数文件失败: {e}")

    def get_feature_calculator_params(self) -> Dict[str, Any]:
        """获取 FeatureCalculator 参数（从 FACTOR_REGISTRY sub_params 动态驱动）"""
        general_params = self._params.get('general_feature', {})
        quality_params = self._params.get('quality_scorer', {})

        validated = {
            'stability_lookforward': self._validate_int(
                general_params.get('stability_lookforward', 10), 1, 9999, 10
            ),
            'atr_period': self._validate_int(
                general_params.get('atr_period', 14), 1, 9999, 14
            ),
            'ma_period': self._validate_int(
                general_params.get('ma_period', 200), 5, 500, 200
            ),
        }

        # 从 FACTOR_REGISTRY sub_params 动态读取 feature_calculator 参数
        for fi in get_active_factors():
            for sp in fi.sub_params:
                if sp.consumer == 'feature_calculator':
                    raw_val = quality_params.get(fi.yaml_key, {}).get(sp.yaml_name, sp.default)
                    if sp.param_type is float:
                        validated[sp.internal_name] = self._validate_float(
                            raw_val, sp.range[0], sp.range[1], sp.default)
                    else:
                        validated[sp.internal_name] = self._validate_int(
                            raw_val, sp.range[0], sp.range[1], sp.default)

        # ATR 配置传递（向后兼容）
        atr_config = quality_params.get('atr_normalization', {})
        validated['use_atr_normalization'] = atr_config.get('enabled', False)

        return validated

    def get_scorer_params(self) -> Dict[str, Any]:
        """获取评分器参数（从 FACTOR_REGISTRY 动态驱动）"""
        quality_params = self._params.get('quality_scorer', {})
        validated = {}

        # 簇分组阈值（默认引用 peak_supersede_threshold）
        # 先获取 detector 的 peak_supersede_threshold 作为默认值
        detector_params = self._params.get('breakout_detector', {})
        peak_supersede_threshold = self._validate_float(
            detector_params.get('peak_supersede_threshold', 0.03), 0.0, 1.0, 0.03
        )
        # 传递给 scorer，以便其内部可以回退到这个值
        validated['peak_supersede_threshold'] = peak_supersede_threshold
        # 如果 cluster_density_threshold 未显式配置，使用 peak_supersede_threshold
        if 'cluster_density_threshold' in quality_params:
            validated['cluster_density_threshold'] = self._validate_float(
                quality_params.get('cluster_density_threshold'), 0.0, 1.0, 0.03
            )
        # 否则不设置，让 BreakoutScorer 自动回退到 peak_supersede_threshold

        # 非因子参数（手动）
        validated['factor_base_score'] = self._validate_int(
            quality_params.get('factor_base_score', 50), 1, 9999, 50
        )

        # ATR 标准化（手动，不是注册因子）
        atr_config = quality_params.get('atr_normalization', {})
        validated['use_atr_normalization'] = atr_config.get('enabled', False)
        validated['atr_normalized_height_thresholds'] = atr_config.get('thresholds', [1.5, 2.5])
        validated['atr_normalized_height_values'] = atr_config.get('values', [1.10, 1.20])

        # 所有注册因子（动态，defaults 来自 FACTOR_REGISTRY）
        for fi in get_active_factors():
            factor_cfg = quality_params.get(fi.yaml_key, {})
            validated[fi.yaml_key] = {
                'enabled': factor_cfg.get('enabled', True),
                'thresholds': factor_cfg.get('thresholds', list(fi.default_thresholds)),
                'values': factor_cfg.get('values', list(fi.default_values)),
                'mode': factor_cfg.get('mode', fi.mining_mode or 'gte'),
            }

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

    # ==================== 状态管理 API ====================

    def set_active_file(self, file_path: Path, params: Dict[str, Any]):
        """
        设置当前活跃文件并更新参数

        用于从文件加载参数后同步状态

        Args:
            file_path: 文件路径
            params: 参数字典
        """
        self._active_file = file_path
        self._params = copy.deepcopy(params)
        self._params_path = file_path  # 同步更新（向后兼容）
        self._is_memory_only = False
        self._notify_listeners()

    def mark_saved(self):
        """标记当前参数已保存到文件"""
        self._is_memory_only = False
        self._notify_listeners()

    def get_active_file(self) -> Optional[Path]:
        """获取当前活跃的参数文件路径"""
        return self._active_file

    def get_active_file_name(self) -> Optional[str]:
        """获取当前活跃的参数文件名（不含路径）"""
        return self._active_file.name if self._active_file else None

    def is_memory_only(self) -> bool:
        """
        检查当前参数是否仅在内存中（未保存到文件）

        Returns:
            True 表示有未保存的修改
        """
        return self._is_memory_only

    # ==================== 监听器机制 ====================

    def add_listener(self, callback: Callable[[], None]):
        """
        添加状态变化监听器

        当参数状态发生变化时（加载、应用、保存），会调用所有注册的监听器

        Args:
            callback: 回调函数（无参数）
        """
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]):
        """
        移除状态变化监听器

        Args:
            callback: 要移除的回调函数
        """
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self):
        """通知所有监听器状态已变化"""
        for listener in self._listeners:
            try:
                listener()
            except Exception as e:
                print(f"Error in UIParamLoader listener: {e}")

    # ==================== 文件切换前钩子 ====================

    def add_before_switch_hook(self, hook: Callable[[Path], bool]):
        """
        添加文件切换前钩子

        钩子函数在文件切换前被调用，可以用于：
        - 检查未保存的更改并提示用户
        - 阻止文件切换（返回 False）

        Args:
            hook: 钩子函数，接收新文件路径，返回 bool
                  - True: 允许切换
                  - False: 阻止切换
        """
        if hook not in self._before_switch_hooks:
            self._before_switch_hooks.append(hook)

    def remove_before_switch_hook(self, hook: Callable[[Path], bool]):
        """
        移除文件切换前钩子

        Args:
            hook: 要移除的钩子函数
        """
        if hook in self._before_switch_hooks:
            self._before_switch_hooks.remove(hook)

    def _run_before_switch_hooks(self, new_file: Path) -> bool:
        """
        运行所有文件切换前钩子

        Args:
            new_file: 即将切换到的新文件路径

        Returns:
            True: 所有钩子都允许切换
            False: 有钩子阻止了切换
        """
        for hook in self._before_switch_hooks:
            try:
                if not hook(new_file):
                    return False  # 钩子阻止了切换
            except Exception as e:
                print(f"Error in before_switch_hook: {e}")
        return True

    def request_file_switch(self, new_file: Path, params: Dict[str, Any]) -> bool:
        """
        请求切换到新文件（会触发钩子检查）

        这是主界面 Combobox 切换文件时应该调用的方法。
        它会先运行所有钩子，如果钩子都允许，才执行实际切换。

        Args:
            new_file: 新文件路径
            params: 新文件的参数内容

        Returns:
            True: 切换成功
            False: 切换被钩子阻止
        """
        # 如果是同一个文件，直接返回
        if self._active_file and self._active_file == new_file:
            return True

        # 运行钩子检查
        if not self._run_before_switch_hooks(new_file):
            return False

        # 执行实际切换
        self.set_active_file(new_file, params)
        return True

    @classmethod
    def from_dict(cls, raw_params: dict) -> "UIParamLoader":
        """从 dict 构造 UIParamLoader，避免临时文件 I/O。

        用于实盘 UI 从 filter.yaml 的 scan_params 字段直接加载参数。

        Args:
            raw_params: 包含 breakout_detector / general_feature / quality_scorer
                        三个顶层 key 的 dict

        Returns:
            UIParamLoader 实例，内部 _params 状态等价于从相应 YAML 文件加载
        """
        instance = cls.__new__(cls)
        instance._params_path = None  # 无关联文件
        instance._params = raw_params
        instance._project_root = None
        instance._active_file = None
        instance._is_memory_only = False
        instance._listeners = []
        instance._before_switch_hooks = []
        return instance

    @classmethod
    def parse_params(cls, raw_params: dict) -> tuple[dict, dict, dict]:
        """从原始参数字典解析出三组扫描参数，不影响单例状态。

        用于模板模式下从模板嵌入的 scan_params 获取扫描参数。

        Args:
            raw_params: 完整参数字典（与 all_factor.yaml 结构一致）

        Returns:
            (detector_params, feature_calculator_params, scorer_params)
        """
        temp = object.__new__(cls)
        temp._params = raw_params
        temp._project_root = None
        temp._params_path = None
        temp._active_file = None
        temp._is_memory_only = False
        temp._listeners = []
        temp._before_switch_hooks = []
        return (
            temp.get_detector_params(),
            temp.get_feature_calculator_params(),
            temp.get_scorer_params(),
        )


def get_ui_param_loader(params_path: Optional[str] = None) -> UIParamLoader:
    """
    获取全局UI参数加载器实例（单例模式）

    Args:
        params_path: 参数文件路径（可选）

    Returns:
        UIParamLoader实例
    """
    return UIParamLoader(params_path)
