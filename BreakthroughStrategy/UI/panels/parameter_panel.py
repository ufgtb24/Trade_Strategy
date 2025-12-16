"""参数配置面板"""

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, Dict, Optional

from ..config import get_ui_config_loader
from ..config import get_ui_param_loader
from ..config import get_ui_scan_config_loader
from ..dialogs import askopenfilename as custom_askopenfilename


class ParameterPanel:
    """参数配置面板"""

    def __init__(
        self,
        parent,
        on_load_callback: Optional[Callable] = None,
        on_param_changed_callback: Optional[Callable] = None,
        on_display_option_changed_callback: Optional[Callable] = None,
        on_rescan_all_callback: Optional[Callable] = None,
        on_new_scan_callback: Optional[Callable] = None,
        get_json_params_callback: Optional[Callable[[], Optional[Dict]]] = None,
    ):
        """
        初始化参数面板

        Args:
            parent: 父容器
            on_load_callback: 加载文件回调
            on_param_changed_callback: 参数变化回调
            on_display_option_changed_callback: 显示选项变化回调
            on_rescan_all_callback: Rescan All 按钮点击回调
            on_new_scan_callback: New Scan 按钮点击回调
            get_json_params_callback: 获取 JSON 扫描参数的回调（返回 scan_data）
        """
        self.parent = parent
        self.on_load_callback = on_load_callback
        self.on_param_changed_callback = on_param_changed_callback
        self.on_display_option_changed_callback = on_display_option_changed_callback
        self.on_rescan_all_callback = on_rescan_all_callback
        self.on_new_scan_callback = on_new_scan_callback
        self.get_json_params_callback = get_json_params_callback

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

        # 当前参数文件名（不含路径）
        self.current_param_file = "ui_params.yaml"

        # 参数加载器
        self.param_loader = get_ui_param_loader()

        # 扫描配置加载器
        self.scan_config_loader = get_ui_scan_config_loader()

        # 订阅 UIParamLoader 状态变化（统一状态同步）
        self.param_loader.add_listener(self._on_param_loader_state_changed)

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

        # New Scan 按钮
        self.new_scan_btn = ttk.Button(
            container, text="New Scan", command=self._on_new_scan_clicked
        )
        self.new_scan_btn.pack(side=tk.LEFT, padx=5)

        ttk.Separator(container, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        # 参数选择组
        param_group_frame = ttk.Frame(container)
        param_group_frame.pack(side=tk.LEFT, padx=5)

        # 复选框（无标签）
        self.use_ui_params_checkbox = ttk.Checkbutton(
            param_group_frame,
            variable=self.use_ui_params_var,
            command=self._on_use_ui_params_changed,
        )
        self.use_ui_params_checkbox.pack(side=tk.LEFT, padx=(0, 5))

        # 参数文件下拉菜单
        self.param_file_combobox = ttk.Combobox(
            param_group_frame,
            state="disabled",
            width=20,
            values=self._get_available_param_files(),
        )
        self.param_file_combobox.pack(side=tk.LEFT, padx=5)
        self.param_file_combobox.set(self.current_param_file)
        self.param_file_combobox.bind("<<ComboboxSelected>>", self._on_param_file_selected)

        # Edit 按钮
        self.edit_btn = ttk.Button(
            param_group_frame,
            text="Edit",
            command=self._on_edit_params_clicked,
            state="disabled",  # Browse Mode 默认禁用
        )
        self.edit_btn.pack(side=tk.LEFT, padx=5)

        # Rescan All 按钮（仅 Analysis Mode 可用）
        self.rescan_all_btn = ttk.Button(
            param_group_frame,
            text="Rescan All",
            command=self._on_rescan_all_clicked,
            state="disabled",  # Browse Mode 默认禁用
        )
        self.rescan_all_btn.pack(side=tk.LEFT, padx=5)

        # Scan Settings 按钮（始终可用）
        self.scan_settings_btn = ttk.Button(
            param_group_frame,
            text="Scan Settings",
            command=self._on_scan_settings_clicked,
        )
        self.scan_settings_btn.pack(side=tk.LEFT, padx=5)

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

        # 状态标签
        self.status_label = ttk.Label(container, text="Ready", foreground="gray")
        self.status_label.pack(side=tk.RIGHT, padx=10)

    def _on_load_scan_clicked(self):
        """加载扫描结果按钮点击"""
        # 从配置文件加载默认目录
        config_loader = get_ui_config_loader()
        default_dir = config_loader.get_scan_results_dir()

        # 使用自定义文件对话框（支持 Delete 键删除文件）
        file_path = custom_askopenfilename(
            parent=self.parent.winfo_toplevel(),
            title="Select Scan Results",
            initialdir=default_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )

        if file_path and self.on_load_callback:
            self.on_load_callback(file_path)

    def _on_checkbox_changed(self):
        """复选框状态改变回调"""
        if self.on_display_option_changed_callback:
            self.on_display_option_changed_callback()
        elif self.on_param_changed_callback:
            self.on_param_changed_callback()

    def _on_use_ui_params_changed(self):
        """Use UI Params 复选框状态改变回调"""
        # 更新下拉菜单状态
        self._update_combobox_state()

        # 触发参数变化回调
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

    def get_mode(self) -> str:
        """
        获取当前模式

        Returns:
            "browse" - 浏览模式（使用 JSON 缓存）
            "analysis" - 分析模式（使用 UI 参数实时计算）
        """
        return "analysis" if self.use_ui_params_var.get() else "browse"

    def _on_edit_params_clicked(self):
        """Edit 按钮点击 - 打开编辑器，加载当前下拉菜单选中的文件"""
        selected_file = self.param_file_combobox.get()
        file_path = (
            self.param_loader.get_project_root()
            / "configs"
            / "analysis"
            / "params"
            / selected_file
        )
        self._open_parameter_editor(preload_file=str(file_path))

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
            from ..editors import ParameterEditorWindow

            root = self.parent.winfo_toplevel()

            # 获取 JSON 参数（来自 scan_metadata）
            json_params = None
            if self.get_json_params_callback:
                scan_data = self.get_json_params_callback()
                if scan_data:
                    json_params = scan_data.get("scan_metadata", {})

            self.editor_window = ParameterEditorWindow(
                parent=root,
                ui_param_loader=self.param_loader,
                on_apply_callback=self._on_params_applied,
                json_params=json_params,
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
        """
        编辑器 Apply 时的回调

        不需要 reload_params()，因为编辑器已经调用了 update_memory_params()
        自动勾选 "Use UI Params" 并触发图表刷新

        注意：下拉菜单同步由 _on_param_loader_state_changed 监听器自动处理
        """
        try:
            # 自动勾选 "Use UI Params"
            self.use_ui_params_var.set(True)

            # 更新下拉菜单状态
            self._update_combobox_state()

            # 触发图表刷新
            if self.on_param_changed_callback:
                self.on_param_changed_callback()

            self.set_status("Parameters applied and chart refreshed", "green")

        except Exception as e:
            self.set_status(f"Failed to apply parameters: {str(e)}", "red")

    def _on_param_loader_state_changed(self):
        """
        响应 UIParamLoader 状态变化的监听器

        当编辑器 Load/Apply/Save 时，UIParamLoader 会通知此方法，
        自动同步下拉菜单显示
        """
        try:
            # 获取当前活跃文件名
            active_file = self.param_loader.get_active_file_name()
            if active_file:
                # 同步下拉菜单显示
                self.param_file_combobox.set(active_file)
                self.current_param_file = active_file

                # 刷新下拉菜单选项（处理 Save As 创建新文件的情况）
                self._refresh_param_file_list()

        except Exception as e:
            print(f"Error in _on_param_loader_state_changed: {e}")

    def _refresh_param_file_list(self):
        """刷新参数文件下拉菜单的可选项"""
        current_value = self.param_file_combobox.get()
        new_files = self._get_available_param_files()
        self.param_file_combobox.config(values=new_files)
        # 保持当前选中值
        if current_value in new_files:
            self.param_file_combobox.set(current_value)

    def _get_available_param_files(self):
        """
        扫描 configs/analysis/params/ 目录，获取所有 .yaml 文件

        Returns:
            文件名列表（只包含文件名，不含路径）
        """
        params_dir = (
            self.param_loader.get_project_root()
            / "configs"
            / "analysis"
            / "params"
        )

        if not params_dir.exists():
            return ["ui_params.yaml"]

        # 获取所有 .yaml 文件
        yaml_files = [f.name for f in params_dir.glob("*.yaml")]

        if not yaml_files:
            return ["ui_params.yaml"]

        # 排序（ui_params.yaml 优先）
        yaml_files.sort(key=lambda x: (x != "ui_params.yaml", x))

        return yaml_files

    def _load_param_file(self, file_path):
        """
        加载指定参数文件到 UIParamLoader 内存

        Args:
            file_path: 参数文件的完整路径（Path对象或字符串）

        Raises:
            FileNotFoundError: 文件不存在
            yaml.YAMLError: YAML 格式错误
            ValueError: 参数文件为空
        """
        import yaml
        from pathlib import Path

        file_path = Path(file_path)

        # 读取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            params = yaml.safe_load(f)

        if params is None:
            raise ValueError(f"Parameter file is empty: {file_path}")

        # 使用统一的 API 更新状态（会触发监听器通知）
        self.param_loader.set_active_file(file_path, params)

    def _on_param_file_selected(self, event=None):
        """
        下拉菜单选择新文件时的处理

        流程：
        1. 获取选中的文件名
        2. 防止重复加载同一文件
        3. 通过 request_file_switch 请求切换（会触发钩子检查）
        4. 如果切换被阻止，恢复下拉菜单显示
        5. 触发图表刷新（如果复选框已选中）
        """
        import yaml

        selected_file = self.param_file_combobox.get()

        # 防止重复加载同一文件
        if selected_file == self.current_param_file:
            return

        try:
            # 构造完整路径
            file_path = (
                self.param_loader.get_project_root()
                / "configs"
                / "analysis"
                / "params"
                / selected_file
            )

            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                params = yaml.safe_load(f)

            if params is None:
                raise ValueError(f"Parameter file is empty: {file_path}")

            # 使用 request_file_switch 请求切换（会触发钩子检查）
            # 如果编辑器有未保存的更改，会弹出提示框
            if not self.param_loader.request_file_switch(file_path, params):
                # 切换被阻止（用户取消），恢复下拉菜单显示
                self.param_file_combobox.set(self.current_param_file)
                return

            # 切换成功，更新当前文件跟踪
            self.current_param_file = selected_file

            # 触发图表刷新（如果复选框已选中）
            if self.use_ui_params_var.get() and self.on_param_changed_callback:
                self.on_param_changed_callback()

            self.set_status(f"Switched to: {selected_file}", "green")

        except FileNotFoundError:
            self.set_status(f"File not found: {selected_file}", "red")
            self.param_file_combobox.set(self.current_param_file)
        except Exception as e:
            self.set_status(f"Failed to load {selected_file}: {str(e)}", "red")
            self.param_file_combobox.set(self.current_param_file)
            import traceback
            traceback.print_exc()

    def _update_combobox_state(self):
        """
        根据模式更新 UI 组件的启用/禁用状态

        Browse Mode: 参数下拉框、Edit 按钮、Rescan All 按钮禁用
        Analysis Mode: 参数下拉框、Edit 按钮、Rescan All 按钮启用
        """
        if self.use_ui_params_var.get():
            # Analysis Mode
            self.param_file_combobox.config(state="readonly")
            self.edit_btn.config(state="normal")
            self.rescan_all_btn.config(state="normal")
        else:
            # Browse Mode
            self.param_file_combobox.config(state="disabled")
            self.edit_btn.config(state="disabled")
            self.rescan_all_btn.config(state="disabled")

    def _on_rescan_all_clicked(self):
        """Rescan All 按钮点击回调"""
        if self.on_rescan_all_callback:
            self.on_rescan_all_callback()

    def _on_new_scan_clicked(self):
        """New Scan 按钮点击回调"""
        if self.on_new_scan_callback:
            self.on_new_scan_callback()

    def _on_scan_settings_clicked(self):
        """Scan Settings 按钮点击 - 打开扫描配置对话框"""
        self._open_scan_config_dialog()

    def _open_scan_config_dialog(self):
        """打开扫描配置对话框（单例模式）"""
        # 检查是否已经打开
        if (
            hasattr(self, "scan_config_dialog")
            and self.scan_config_dialog.window.winfo_exists()
        ):
            # 窗口已存在，提升到前台
            self.scan_config_dialog.window.lift()
            return

        # 创建新的对话框
        try:
            from ..dialogs import ScanConfigDialog

            root = self.parent.winfo_toplevel()

            self.scan_config_dialog = ScanConfigDialog(
                parent=root,
                scan_config_loader=self.scan_config_loader,
            )

            self.set_status("Scan config dialog opened", "blue")

        except Exception as e:
            self.set_status(f"Failed to open dialog: {str(e)}", "red")
            import traceback

            traceback.print_exc()
