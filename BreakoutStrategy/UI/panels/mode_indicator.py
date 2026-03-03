"""模式指示器 - 显示 Browse/Analysis 模式和配置不匹配警告"""

import tkinter as tk
from tkinter import ttk
from typing import Optional


class ModeIndicator:
    """
    模式指示器组件

    显示当前模式 (Browse/Analysis) 和配置不匹配警告。
    """

    MODE_BROWSE = "browse"
    MODE_ANALYSIS = "analysis"

    def __init__(self, parent):
        """
        初始化模式指示器

        Args:
            parent: 父容器
        """
        self.parent = parent
        self._mode = self.MODE_BROWSE
        self._config_mismatch = False
        self._json_filename: Optional[str] = None
        self._active_config: Optional[str] = None

        self._create_ui()

    def _create_ui(self):
        """创建 UI 组件"""
        self.container = ttk.Frame(self.parent)
        self.container.pack(fill=tk.X, padx=10, pady=(5, 0))

        # 模式标签
        self.mode_label = ttk.Label(
            self.container,
            text="Browse Mode",
            font=("Arial", 12, "bold"),
        )
        self.mode_label.pack(side=tk.LEFT)

        # 警告标签（初始隐藏）
        self.warning_label = ttk.Label(
            self.container,
            text="",
            foreground="#FF6600",
            font=("Arial", 11),
        )
        self.warning_label.pack(side=tk.LEFT, padx=(10, 0))

        # 文件名标签
        self.file_label = ttk.Label(
            self.container,
            text="",
            foreground="#666666",
            font=("Arial", 11),
        )
        self.file_label.pack(side=tk.RIGHT)

        self._update_display()

    def set_mode(self, mode: str, config_mismatch: bool = False):
        """
        设置当前模式

        Args:
            mode: 模式 (MODE_BROWSE 或 MODE_ANALYSIS)
            config_mismatch: 是否存在配置不匹配
        """
        self._mode = mode
        self._config_mismatch = config_mismatch
        self._update_display()

    def set_json_filename(self, filename: Optional[str]):
        """
        设置当前加载的 JSON 文件名

        Args:
            filename: 文件名（不含路径）
        """
        self._json_filename = filename
        self._update_display()

    def _update_display(self):
        """更新显示"""
        # 更新模式文本
        if self._mode == self.MODE_BROWSE:
            mode_text = "Browse Mode"
            if self._config_mismatch:
                mode_text += " (config mismatch)"
                self.warning_label.config(text="Config differs from scan")
            else:
                self.warning_label.config(text="")
        else:
            mode_text = "Analysis Mode"
            if self._active_config:
                self.warning_label.config(text=f"Config: {self._active_config}")
            else:
                self.warning_label.config(text="Using UI config for real-time analysis")

        self.mode_label.config(text=mode_text)

        # 更新文件名
        if self._json_filename:
            self.file_label.config(text=f"| {self._json_filename}")
        else:
            self.file_label.config(text="")

    def set_active_config(self, config_name: str):
        """
        设置当前活跃配置文件名

        Args:
            config_name: 配置文件名
        """
        self._active_config = config_name
        self._update_display()

    def get_mode(self) -> str:
        """获取当前模式"""
        return self._mode
