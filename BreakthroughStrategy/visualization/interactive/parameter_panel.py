"""参数配置面板"""

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

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
        on_display_option_changed_callback: Optional[Callable] = None,
    ):
        """
        初始化参数面板

        Args:
            parent: 父容器
            on_load_callback: 加载文件回调
            on_param_changed_callback: 参数变化回调
            on_display_option_changed_callback: 显示选项变化回调
        """
        self.parent = parent
        self.on_load_callback = on_load_callback
        self.on_param_changed_callback = on_param_changed_callback
        self.on_display_option_changed_callback = on_display_option_changed_callback

        # 加载默认显示选项
        config_loader = get_ui_config_loader()
        defaults = config_loader.get_display_options_defaults()

        # 显示选项变量
        self.show_peak_score_var = tk.BooleanVar(
            value=defaults.get("show_peak_score", True)
        )
        self.show_bt_score_var = tk.BooleanVar(
            value=defaults.get("show_bt_score", True)
        )

        # UI 参数选项（默认不选中 = 使用 JSON cache）
        self.use_ui_params_var = tk.BooleanVar(value=False)

        # StockListPanel 引用（稍后设置）
        self.stock_list_panel = None

        # 列显示总开关状态
        column_config = config_loader.get_stock_list_column_config()
        self.toggle_columns_var = tk.BooleanVar(
            value=column_config.get("columns_enabled", True)
        )

        # 参数加载器
        self.param_loader = get_ui_param_loader()

        # 创建UI
        self._create_ui()

    def _create_ui(self):
        """创建UI组件"""
        # 注意：字体样式由 ui_styles.py 的 configure_global_styles() 统一管理
        # 不在此处设置局部样式，以避免覆盖全局配置

        container = ttk.Frame(self.parent, padding="10")
        container.pack(fill=tk.X)

        # Load Scan Results 按钮
        ttk.Button(
            container, text="Load Scan Results", command=self._on_load_scan_clicked
        ).pack(side=tk.LEFT, padx=5)

        ttk.Separator(container, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        # Edit Parameters 按钮
        ttk.Button(
            container, text="Edit Parameters", command=self._on_edit_params_clicked
        ).pack(side=tk.LEFT, padx=5)

        # Load Parameters 按钮
        ttk.Button(
            container, text="Load Parameters", command=self._on_load_params_clicked
        ).pack(side=tk.LEFT, padx=5)

        # Reload Parameters 按钮
        ttk.Button(
            container, text="Reload Parameters", command=self._on_reload_clicked
        ).pack(side=tk.LEFT, padx=5)

        ttk.Separator(container, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        # Use UI Params 复选框
        ttk.Checkbutton(
            container,
            text="Use UI Params",
            variable=self.use_ui_params_var,
            command=self._on_use_ui_params_changed,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Separator(container, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        # 显示选项复选框
        ttk.Checkbutton(
            container,
            text="Peak Score",
            variable=self.show_peak_score_var,
            command=self._on_checkbox_changed,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Checkbutton(
            container,
            text="BT Score",
            variable=self.show_bt_score_var,
            command=self._on_checkbox_changed,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Separator(container, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        # 列配置按钮
        ttk.Button(
            container,
            text="Configure Columns",
            command=self._on_configure_columns_clicked,
        ).pack(side=tk.LEFT, padx=5)

        # 列显示总开关（Checkbutton样式）
        ttk.Checkbutton(
            container,
            text="👁 Show Columns",
            variable=self.toggle_columns_var,
            command=self._on_toggle_columns_clicked,
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
        """加载参数文件按钮点击 - 打开编辑器预加载文件"""
        # 获取根窗口
        root = self.parent.winfo_toplevel()

        # 默认目录：configs/analysis/params/
        default_dir = (
            self.param_loader.get_project_root() / "configs" / "analysis" / "params"
        )

        file_path = askopenfilename(
            parent=root,
            title="Select Parameter File",
            initialdir=str(default_dir),
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
            font_size=15,
        )

        if file_path:
            # 打开编辑器并预加载文件
            self._open_parameter_editor(preload_file=file_path)

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

    def _on_checkbox_changed(self):
        """复选框状态改变回调"""
        if self.on_display_option_changed_callback:
            self.on_display_option_changed_callback()
        elif self.on_param_changed_callback:
            self.on_param_changed_callback()

    def _on_use_ui_params_changed(self):
        """Use UI Params 复选框状态改变回调"""
        if self.on_param_changed_callback:
            self.on_param_changed_callback()

    def set_status(self, text: str, color: str = "gray", font=None):
        """
        设置状态文本

        Args:
            text: 状态文本
            color: 颜色
            font: 字体配置 (tuple or str)
        """
        if font:
            self.status_label.config(text=text, foreground=color, font=font)
        else:
            self.status_label.config(text=text, foreground=color)

    def get_params(self):
        """获取当前参数"""
        return self.param_loader.get_detector_params()

    def get_display_options(self):
        """获取显示选项"""
        return {
            "show_peak_score": self.show_peak_score_var.get(),
            "show_bt_score": self.show_bt_score_var.get(),
        }

    def get_use_ui_params(self) -> bool:
        """获取 Use UI Params 复选框状态"""
        return self.use_ui_params_var.get()

    def _on_edit_params_clicked(self):
        """Edit Parameters 按钮点击 - 打开编辑器，加载当前ui_params.yaml"""
        ui_params_path = (
            self.param_loader.get_project_root()
            / "configs"
            / "analysis"
            / "params"
            / "ui_params.yaml"
        )
        self._open_parameter_editor(preload_file=str(ui_params_path))

    def _open_parameter_editor(self, preload_file: str = None):
        """
        打开参数编辑器窗口（单例模式）

        Args:
            preload_file: 预加载的参数文件路径
        """
        # 检查是否已经打开
        if hasattr(self, "editor_window") and self.editor_window.window.winfo_exists():
            # 窗口已存在，提升到前台
            self.editor_window.window.lift()
            if preload_file:
                self.editor_window.load_from_file(preload_file)
            return

        # 创建新的编辑器窗口
        try:
            from .parameter_editor import ParameterEditorWindow

            root = self.parent.winfo_toplevel()

            self.editor_window = ParameterEditorWindow(
                parent=root,
                ui_param_loader=self.param_loader,
                on_apply_callback=self._on_params_applied,
            )

            # 预加载文件
            if preload_file:
                self.editor_window.load_from_file(preload_file)

            self.set_status("Parameter editor opened", "blue")

        except Exception as e:
            self.set_status(f"Failed to open editor: {str(e)}", "red")
            import traceback

            traceback.print_exc()

    def _on_params_applied(self):
        """编辑器Apply时的回调 - 重新加载参数并触发图表刷新"""
        try:
            # 重新加载 ui_params.yaml
            self.param_loader.reload_params()

            # 触发图表刷新
            if self.on_param_changed_callback:
                self.on_param_changed_callback()

            self.set_status("Parameters applied and reloaded", "green")

        except Exception as e:
            self.set_status(f"Failed to apply parameters: {str(e)}", "red")

    def set_stock_list_panel(self, stock_list_panel):
        """
        设置 StockListPanel 引用

        Args:
            stock_list_panel: StockListPanel 实例
        """
        self.stock_list_panel = stock_list_panel

    def _on_configure_columns_clicked(self):
        """打开列配置对话框"""
        from .column_config_dialog import ColumnConfigDialog

        if not self.stock_list_panel or not self.stock_list_panel.stock_data:
            return  # 没有数据时不打开

        # 动态发现所有字段
        first_item = self.stock_list_panel.stock_data[0]
        available_columns = [
            k for k in first_item.keys() if k not in ["symbol", "raw_data"]
        ]

        # 当前可见列
        config_loader = get_ui_config_loader()
        config = config_loader.get_stock_list_column_config()
        visible_columns = config.get("visible_columns", [])

        # 打开对话框
        ColumnConfigDialog(
            parent=self.parent.winfo_toplevel(),
            available_columns=available_columns,
            visible_columns=visible_columns,
            on_apply_callback=self._on_columns_applied,
        )

    def _on_columns_applied(self, new_visible_columns: list):
        """应用列配置回调"""
        if self.stock_list_panel:
            self.stock_list_panel.set_visible_columns(new_visible_columns)

    def _on_toggle_columns_clicked(self):
        """一键开关回调"""
        if self.stock_list_panel:
            new_state = self.stock_list_panel.toggle_columns_enabled()
            self.toggle_columns_var.set(new_state)
