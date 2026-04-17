"""dev UI 编辑器参数状态管理器。

把参数 SSoT（BreakoutStrategy.param_loader.ParamLoader）包装一层，
附加只在 dev 编辑器场景下需要的状态：
- 活跃文件路径
- 内存态 dirty 标志（有未保存修改）
- 监听器机制（状态变化通知订阅者）
- 文件切换前钩子（允许其它组件阻止切换）

这些机制不属于策略参数本身，因此不放在顶层 ParamLoader。live 和
pipeline 不需要这些——它们只读取参数，没有编辑 / 切换文件的概念。
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from BreakoutStrategy.param_loader import ParamLoader, get_param_loader


class ParamEditorState:
    """dev 编辑器 UI 状态单例。包装 ParamLoader 并管理编辑器侧的状态。"""

    _instance: Optional["ParamEditorState"] = None

    def __new__(cls) -> "ParamEditorState":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._initialized = False
            cls._instance = inst
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.loader: ParamLoader = get_param_loader()
        self._active_file: Optional[Path] = self.loader._params_path
        self._is_memory_only: bool = False
        self._listeners: List[Callable[[], None]] = []
        self._before_switch_hooks: List[Callable[[Path], bool]] = []

    # ==================== 活跃文件 ====================

    def set_active_file(self, file_path: Path, params: Dict[str, Any]) -> None:
        self._active_file = file_path
        self.loader.set_params_in_memory(params)
        self.loader._params_path = file_path  # 保持向后兼容
        self._is_memory_only = False
        self._notify_listeners()

    def get_active_file(self) -> Optional[Path]:
        return self._active_file

    def get_active_file_name(self) -> Optional[str]:
        return self._active_file.name if self._active_file else None

    # ==================== 内存态 ====================

    def update_memory_params(
        self, params: Dict[str, Any], source_file: Optional[Path] = None
    ) -> None:
        """编辑器 Apply 操作：内存更新但不写文件。"""
        self.loader.set_params_in_memory(params)
        if source_file:
            self._active_file = source_file
        self._is_memory_only = True
        self._notify_listeners()

    def mark_saved(self) -> None:
        self._is_memory_only = False
        self._notify_listeners()

    def is_memory_only(self) -> bool:
        return self._is_memory_only

    def save_params(self, params: Dict[str, Any]) -> None:
        """保存 breakout_detector 部分到当前活跃文件（向后兼容旧用法）。"""
        current = self.loader.get_all_params()
        if "breakout_detector" not in current:
            current["breakout_detector"] = {}
        for key, value in params.items():
            current["breakout_detector"][key] = value
        self.loader.set_params_in_memory(current)

        target = self._active_file or self.loader._params_path
        if target is None:
            raise RuntimeError("无活跃文件路径，无法保存")
        with open(target, "w", encoding="utf-8") as f:
            yaml.dump(current, f, allow_unicode=True, default_flow_style=False)

    # ==================== 监听器 ====================

    def add_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        for listener in self._listeners:
            try:
                listener()
            except Exception as e:
                print(f"Error in ParamEditorState listener: {e}")

    # ==================== 文件切换前钩子 ====================

    def add_before_switch_hook(self, hook: Callable[[Path], bool]) -> None:
        if hook not in self._before_switch_hooks:
            self._before_switch_hooks.append(hook)

    def remove_before_switch_hook(self, hook: Callable[[Path], bool]) -> None:
        if hook in self._before_switch_hooks:
            self._before_switch_hooks.remove(hook)

    def _run_before_switch_hooks(self, new_file: Path) -> bool:
        for hook in self._before_switch_hooks:
            try:
                if not hook(new_file):
                    return False
            except Exception as e:
                print(f"Error in before_switch_hook: {e}")
        return True

    def request_file_switch(self, new_file: Path, params: Dict[str, Any]) -> bool:
        if self._active_file and self._active_file == new_file:
            return True
        if not self._run_before_switch_hooks(new_file):
            return False
        self.set_active_file(new_file, params)
        return True


def get_param_editor_state() -> ParamEditorState:
    return ParamEditorState()
