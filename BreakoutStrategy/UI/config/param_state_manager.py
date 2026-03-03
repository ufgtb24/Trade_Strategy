"""参数状态管理器

管理编辑器参数的三层状态：File → Editor → Memory
- File State: 磁盘上的 YAML 文件（持久化）
- Editor State: 编辑器临时参数（用户正在调整）
- Memory State: UIParamLoader._params（运行时，由 UIParamLoader 管理）
"""

import copy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ParameterStateManager:
    """参数状态管理器

    追踪参数编辑器的文件关联、快照和脏状态
    """

    def __init__(self):
        """初始化状态管理器"""
        self.current_file_path: Optional[Path] = None  # 当前关联的文件路径
        self.file_snapshot: Optional[Dict[str, Any]] = None  # 文件加载时的快照
        self.editor_params: Dict[str, Any] = {}  # 编辑器当前参数
        self.is_dirty: bool = False  # 编辑器是否有未保存修改
        self.has_applied: bool = False  # 是否 Apply 过但未保存

    def load_file(self, file_path: Path) -> Dict[str, Any]:
        """
        加载文件并记录快照

        Args:
            file_path: YAML 文件路径

        Returns:
            参数字典

        Raises:
            FileNotFoundError: 文件不存在
            yaml.YAMLError: YAML 格式错误
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Parameter file not found: {file_path}")

        params = self._read_yaml(file_path)

        # 更新状态
        self.current_file_path = file_path
        self.file_snapshot = copy.deepcopy(params)
        self.editor_params = copy.deepcopy(params)
        self.is_dirty = False
        self.has_applied = False

        return params

    def save_file(self, file_path: Optional[Path] = None):
        """
        保存到文件（支持另存为）

        Args:
            file_path: 目标文件路径（None = 当前关联文件）

        Raises:
            ValueError: 没有关联文件且未指定路径
        """
        target_path = file_path or self.current_file_path

        if target_path is None:
            raise ValueError("No file path specified and no current file associated")

        # 写入文件
        self._write_yaml(target_path, self.editor_params)

        # 更新状态
        self.current_file_path = target_path
        self.file_snapshot = copy.deepcopy(self.editor_params)
        self.is_dirty = False
        self.has_applied = False  # 保存后清除 Apply 标志

    def reset_to_snapshot(self) -> Dict[str, Any]:
        """
        重置到文件快照（Discard Changes）

        Returns:
            快照参数字典

        Raises:
            ValueError: 没有可用的快照
        """
        if self.file_snapshot is None:
            raise ValueError("No snapshot available to reset to")

        self.editor_params = copy.deepcopy(self.file_snapshot)
        self.is_dirty = False
        self.has_applied = False  # 重置后清除 Apply 标志

        return self.editor_params

    def mark_dirty(self):
        """标记为脏状态（有未保存的修改）"""
        if not self.is_dirty:
            self.is_dirty = True

    def mark_applied(self):
        """标记为已 Apply（应用到内存但未保存到文件）"""
        self.has_applied = True

    def check_dirty(self) -> bool:
        """
        检测是否有修改（深度对比）

        Returns:
            是否有未保存的修改
        """
        if self.file_snapshot is None:
            return bool(self.editor_params)  # 如果没有快照，有参数就算脏

        return self.editor_params != self.file_snapshot

    def needs_save_prompt(self) -> bool:
        """
        是否需要保存提示（Apply 过但未 Save）

        Returns:
            是否需要提示保存
        """
        return self.has_applied and self.is_dirty

    def _read_yaml(self, file_path: Path) -> Dict[str, Any]:
        """
        读取 YAML 文件

        Args:
            file_path: 文件路径

        Returns:
            参数字典

        Raises:
            yaml.YAMLError: YAML 格式错误
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                params = yaml.safe_load(f)

            if params is None:
                raise ValueError("Parameter file is empty")

            return params

        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"YAML format error: {e}")

    def _write_yaml(self, file_path: Path, params: Dict[str, Any]):
        """
        写入 YAML 文件

        Args:
            file_path: 文件路径
            params: 参数字典
        """
        # 确保目标目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(params, f, default_flow_style=False, allow_unicode=True)
