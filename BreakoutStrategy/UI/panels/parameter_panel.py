"""参数配置面板（信号扫描版）"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ..config import get_ui_config_loader
from ..dialogs import askopenfilename as custom_askopenfilename


class ParameterPanel:
    """参数配置面板"""

    def __init__(
        self,
        parent,
        on_load_callback: Optional[Callable] = None,
        on_scan_callback: Optional[Callable] = None,
        on_edit_config_callback: Optional[Callable] = None,
        on_rescan_callback: Optional[Callable] = None,
        on_settings_callback: Optional[Callable] = None,
        on_mode_changed_callback: Optional[Callable[[bool], None]] = None,
        on_config_file_changed_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        初始化参数面板

        Args:
            parent: 父容器
            on_load_callback: 加载文件回调
            on_scan_callback: New Scan 按钮点击回调
            on_edit_config_callback: Edit Config 按钮点击回调
            on_rescan_callback: Rescan All 按钮点击回调
            on_settings_callback: Settings 按钮点击回调
            on_mode_changed_callback: Use UI Config 切换回调 (is_analysis_mode)
            on_config_file_changed_callback: 配置文件切换回调 (filename)
        """
        self.parent = parent
        self.on_load_callback = on_load_callback
        self.on_scan_callback = on_scan_callback
        self.on_edit_config_callback = on_edit_config_callback
        self.on_rescan_callback = on_rescan_callback
        self.on_settings_callback = on_settings_callback
        self.on_mode_changed_callback = on_mode_changed_callback
        self.on_config_file_changed_callback = on_config_file_changed_callback

        self._create_ui()

    def _create_ui(self):
        """创建UI组件"""
        container = ttk.Frame(self.parent, padding="10")
        container.pack(fill=tk.X)

        # Load Results 按钮
        ttk.Button(
            container, text="Load Results", command=self._on_load_clicked
        ).pack(side=tk.LEFT, padx=5)

        # New Scan 按钮
        self.scan_btn = ttk.Button(
            container, text="New Scan", command=self._on_scan_clicked
        )
        self.scan_btn.pack(side=tk.LEFT, padx=5)

        ttk.Separator(container, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        # Use UI Config 复选框
        self._use_ui_config_var = tk.BooleanVar(value=False)
        self._use_ui_config_cb = ttk.Checkbutton(
            container,
            text="Use UI Config",
            variable=self._use_ui_config_var,
            command=self._on_mode_checkbox_changed,
        )
        self._use_ui_config_cb.pack(side=tk.LEFT, padx=5)

        # 配置文件选择下拉框（初始禁用，勾选 Use UI Config 后启用）
        self._config_file_var = tk.StringVar()
        self._config_file_combobox = ttk.Combobox(
            container,
            textvariable=self._config_file_var,
            state="disabled",
            width=18,
        )
        self._config_file_combobox.pack(side=tk.LEFT, padx=5)
        self._config_file_combobox.bind("<<ComboboxSelected>>", self._on_config_file_selected)

        ttk.Separator(container, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        # Edit Config 按钮
        ttk.Button(
            container, text="Param Edit", command=self._on_edit_config_clicked
        ).pack(side=tk.LEFT, padx=5)

        # Rescan All 按钮
        self.rescan_btn = ttk.Button(
            container, text="Rescan All", command=self._on_rescan_clicked
        )
        self.rescan_btn.pack(side=tk.LEFT, padx=5)

        # Settings 按钮
        ttk.Button(
            container, text="Scan Settings", command=self._on_settings_clicked
        ).pack(side=tk.LEFT, padx=5)

        # 状态标签
        self.status_label = ttk.Label(container, text="Ready", foreground="gray")
        self.status_label.pack(side=tk.RIGHT, padx=10)

    def _on_load_clicked(self):
        """加载扫描结果按钮点击"""
        config_loader = get_ui_config_loader()
        default_dir = config_loader.get_scan_results_dir()

        file_path = custom_askopenfilename(
            parent=self.parent.winfo_toplevel(),
            title="Select Scan Results",
            initialdir=default_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )

        if file_path and self.on_load_callback:
            self.on_load_callback(file_path)

    def _on_scan_clicked(self):
        """New Scan 按钮点击"""
        if self.on_scan_callback:
            self.on_scan_callback()

    def _on_edit_config_clicked(self):
        """Edit Config 按钮点击"""
        if self.on_edit_config_callback:
            self.on_edit_config_callback()

    def _on_rescan_clicked(self):
        """Rescan All 按钮点击"""
        if self.on_rescan_callback:
            self.on_rescan_callback()

    def _on_settings_clicked(self):
        """Settings 按钮点击"""
        if self.on_settings_callback:
            self.on_settings_callback()

    def _on_mode_checkbox_changed(self):
        """Use UI Config 复选框变化"""
        is_analysis_mode = self._use_ui_config_var.get()
        # 同步 Combobox 启用/禁用状态
        self._config_file_combobox.config(
            state="readonly" if is_analysis_mode else "disabled"
        )
        if self.on_mode_changed_callback:
            self.on_mode_changed_callback(is_analysis_mode)

    def _on_config_file_selected(self, event=None):
        """配置文件下拉框选择变化"""
        filename = self._config_file_var.get()
        if filename and self.on_config_file_changed_callback:
            self.on_config_file_changed_callback(filename)

    def set_status(self, text: str, color: str = "gray", font=None):
        """设置状态文本"""
        if font:
            self.status_label.config(text=text, foreground=color, font=font)
        else:
            self.status_label.config(text=text, foreground=color)

    def set_scan_enabled(self, enabled: bool):
        """设置 Scan 按钮启用状态"""
        self.scan_btn.config(state="normal" if enabled else "disabled")

    def set_rescan_enabled(self, enabled: bool):
        """设置 Rescan All 按钮启用状态"""
        self.rescan_btn.config(state="normal" if enabled else "disabled")

    def is_analysis_mode(self) -> bool:
        """检查是否为分析模式"""
        return self._use_ui_config_var.get()

    def set_analysis_mode(self, enabled: bool):
        """设置分析模式"""
        self._use_ui_config_var.set(enabled)

    def refresh_config_files(self, params_dir, active_file: str):
        """
        刷新配置文件下拉列表

        Args:
            params_dir: 配置文件目录 (Path)
            active_file: 当前激活的文件名
        """
        from pathlib import Path
        params_dir = Path(params_dir)
        files = sorted(f.name for f in params_dir.glob("*.yaml"))
        self._config_file_combobox["values"] = files
        if active_file in files:
            self._config_file_var.set(active_file)
        elif files:
            self._config_file_var.set(files[0])

    def get_selected_config_file(self) -> str:
        """获取选中的配置文件名"""
        return self._config_file_var.get()
