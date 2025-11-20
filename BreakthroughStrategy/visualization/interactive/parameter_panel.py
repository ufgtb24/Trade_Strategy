"""参数配置面板"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from pathlib import Path

from .file_dialog import askopenfilename
from .ui_config_loader import get_ui_config_loader
from .ui_param_loader import get_ui_param_loader


class ParameterPanel:
    """参数配置面板"""

    def __init__(
        self,
        parent,
        on_load_callback: Optional[Callable] = None,
        on_param_changed_callback: Optional[Callable] = None,
    ):
        """
        初始化参数面板

        Args:
            parent: 父容器
            on_load_callback: 加载文件回调
            on_param_changed_callback: 参数变化回调
        """
        self.parent = parent
        self.on_load_callback = on_load_callback
        self.on_param_changed_callback = on_param_changed_callback

        # 参数加载器
        self.param_loader = get_ui_param_loader()

        # 创建UI
        self._create_ui()

    def _create_ui(self):
        """创建UI组件"""
        # 配置按钮和标签的样式，增大字体
        style = ttk.Style()
        style.configure("TButton", font=("TkDefaultFont", 15))
        style.configure("TLabel", font=("TkDefaultFont", 15))

        container = ttk.Frame(self.parent, padding="10")
        container.pack(fill=tk.X)

        # Load Scan Results 按钮
        ttk.Button(
            container, text="Load Scan Results", command=self._on_load_scan_clicked
        ).pack(side=tk.LEFT, padx=5)

        ttk.Separator(container, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        # Load Parameters 按钮
        ttk.Button(
            container, text="Load Parameters", command=self._on_load_params_clicked
        ).pack(side=tk.LEFT, padx=5)

        # Reload Parameters 按钮
        ttk.Button(
            container, text="Reload Parameters", command=self._on_reload_clicked
        ).pack(side=tk.LEFT, padx=5)

        # 状态标签
        self.status_label = ttk.Label(container, text="Ready", foreground="gray")
        self.status_label.pack(side=tk.RIGHT, padx=10)

    def _on_load_scan_clicked(self):
        """加载扫描结果按钮点击"""
        # 获取根窗口
        root = self.parent.winfo_toplevel()

        # 从配置文件加载默认目录
        config_loader = get_ui_config_loader()
        default_dir = config_loader.get_scan_results_dir()

        file_path = askopenfilename(
            parent=root,
            title="Select Scan Results",
            initialdir=default_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            font_size=15,
        )

        if file_path and self.on_load_callback:
            self.on_load_callback(file_path)

    def _on_load_params_clicked(self):
        """加载参数文件按钮点击"""
        # 获取根窗口
        root = self.parent.winfo_toplevel()

        # 默认目录：configs/analysis/params/
        default_dir = self.param_loader.get_project_root() / "configs" / "analysis" / "params"

        file_path = askopenfilename(
            parent=root,
            title="Select Parameter File",
            initialdir=str(default_dir),
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
            font_size=15,
        )

        if file_path:
            try:
                # 重新初始化参数加载器，加载选中的参数文件
                self.param_loader = get_ui_param_loader(file_path)
                # 触发图表刷新（如果有选中的股票）
                if self.on_param_changed_callback:
                    self.on_param_changed_callback()
                self.set_status(f"Parameters loaded: {Path(file_path).name}", "green")
            except Exception as e:
                self.set_status(f"Load failed: {str(e)}", "red")

    def _on_reload_clicked(self):
        """重新加载参数按钮"""
        try:
            self.param_loader.reload_params()
            # 触发图表刷新（如果有选中的股票）
            if self.on_param_changed_callback:
                self.on_param_changed_callback()
            self.set_status("Parameters reloaded", "green")
        except Exception as e:
            self.set_status(f"Reload failed: {str(e)}", "red")

    def set_status(self, text: str, color: str = "gray"):
        """
        设置状态文本

        Args:
            text: 状态文本
            color: 颜色
        """
        self.status_label.config(text=text, foreground=color)

    def get_params(self):
        """获取当前参数"""
        return self.param_loader.get_detector_params()
