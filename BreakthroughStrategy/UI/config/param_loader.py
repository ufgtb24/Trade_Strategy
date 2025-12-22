"""UI参数加载器"""

import copy
import shutil
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List


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
        # 当前文件: .../Trade_Strategy/BreakthroughStrategy/UI/interactive/ui_param_loader.py
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

        # 初始化活跃文件状态
        self._active_file = self._params_path
        self._is_memory_only = False

    def _create_from_template(self):
        """从 breakthrough_0.yaml 复制创建 ui_params.yaml"""
        template_path = self._project_root / "configs" / "UI" / "ui_params_bk.yaml"

        if not template_path.exists():
            raise FileNotFoundError(
                f"模板文件不存在: {template_path}\n"
                "请确保 configs/UI/ui_params_bk.yaml 文件存在"
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
            参数字典，包含: total_window, min_side_bars, min_relative_height,
                         exceed_threshold, peak_supersede_threshold, use_cache, cache_dir
        """
        detector_params = self._params.get('breakthrough_detector', {})

        # 参数验证和默认值
        total_window = self._validate_int(
            detector_params.get('total_window', 10), 6, 30, 10
        )
        min_side_bars = self._validate_int(
            detector_params.get('min_side_bars', 2), 1, 10, 2
        )

        # 约束验证：min_side_bars * 2 <= total_window
        if min_side_bars * 2 > total_window:
            min_side_bars = total_window // 2

        validated = {
            'total_window': total_window,
            'min_side_bars': min_side_bars,
            'min_relative_height': self._validate_float(
                detector_params.get('min_relative_height', 0.05), 0.0, 0.3, 0.05
            ),
            'exceed_threshold': self._validate_float(
                detector_params.get('exceed_threshold', 0.005), 0.001, 0.02, 0.005
            ),
            'peak_supersede_threshold': self._validate_float(
                detector_params.get('peak_supersede_threshold', 0.03), 0.01, 0.1, 0.03
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
            注意: label_configs 已移至 UIScanConfigLoader
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

    def get_scorer_params(self) -> Dict[str, Any]:
        """
        获取评分器参数

        Returns:
            参数字典，用于 BreakthroughScorer 的初始化
        """
        quality_params = self._params.get('quality_scorer', {})
        validated = {}

        # 簇分组阈值（默认引用 peak_supersede_threshold）
        # 先获取 detector 的 peak_supersede_threshold 作为默认值
        detector_params = self._params.get('breakthrough_detector', {})
        peak_supersede_threshold = self._validate_float(
            detector_params.get('peak_supersede_threshold', 0.03), 0.01, 0.10, 0.03
        )
        # 传递给 scorer，以便其内部可以回退到这个值
        validated['peak_supersede_threshold'] = peak_supersede_threshold
        # 如果 cluster_density_threshold 未显式配置，使用 peak_supersede_threshold
        if 'cluster_density_threshold' in quality_params:
            validated['cluster_density_threshold'] = self._validate_float(
                quality_params.get('cluster_density_threshold'), 0.01, 0.10, 0.03
            )
        # 否则不设置，让 BreakthroughScorer 自动回退到 peak_supersede_threshold

        # =====================================================================
        # Bonus 乘法模型配置
        # =====================================================================

        # 基准分
        validated['bonus_base_score'] = self._validate_int(
            quality_params.get('bonus_base_score', 50), 10, 100, 50
        )

        # Age bonus
        age_bonus = quality_params.get('age_bonus', {})
        validated['age_bonus_thresholds'] = age_bonus.get('thresholds', [21, 63, 252])
        validated['age_bonus_values'] = age_bonus.get('values', [1.15, 1.30, 1.50])

        # Test bonus
        test_bonus = quality_params.get('test_bonus', {})
        validated['test_bonus_thresholds'] = test_bonus.get('thresholds', [2, 3, 4])
        validated['test_bonus_values'] = test_bonus.get('values', [1.10, 1.25, 1.40])

        # Height bonus
        height_bonus = quality_params.get('height_bonus', {})
        validated['height_bonus_thresholds'] = height_bonus.get('thresholds', [0.10, 0.20])
        validated['height_bonus_values'] = height_bonus.get('values', [1.15, 1.30])

        # Peak Volume bonus（峰值放量）
        peak_volume_bonus = quality_params.get('peak_volume_bonus', {})
        validated['peak_volume_bonus_thresholds'] = peak_volume_bonus.get('thresholds', [2.0, 4.0])
        validated['peak_volume_bonus_values'] = peak_volume_bonus.get('values', [1.15, 1.30])

        # Volume bonus
        volume_bonus = quality_params.get('volume_bonus', {})
        validated['volume_bonus_thresholds'] = volume_bonus.get('thresholds', [1.5, 2.0])
        validated['volume_bonus_values'] = volume_bonus.get('values', [1.15, 1.30])

        # Gap bonus
        gap_bonus = quality_params.get('gap_bonus', {})
        validated['gap_bonus_thresholds'] = gap_bonus.get('thresholds', [0.01, 0.02])
        validated['gap_bonus_values'] = gap_bonus.get('values', [1.10, 1.20])

        # Continuity bonus
        continuity_bonus = quality_params.get('continuity_bonus', {})
        validated['continuity_bonus_thresholds'] = continuity_bonus.get('thresholds', [3])
        validated['continuity_bonus_values'] = continuity_bonus.get('values', [1.15])

        # Momentum bonus
        momentum_bonus = quality_params.get('momentum_bonus', {})
        validated['momentum_bonus_thresholds'] = momentum_bonus.get('thresholds', [2])
        validated['momentum_bonus_values'] = momentum_bonus.get('values', [1.20])

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


def get_ui_param_loader(params_path: Optional[str] = None) -> UIParamLoader:
    """
    获取全局UI参数加载器实例（单例模式）

    Args:
        params_path: 参数文件路径（可选）

    Returns:
        UIParamLoader实例
    """
    return UIParamLoader(params_path)
