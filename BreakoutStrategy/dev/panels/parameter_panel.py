"""参数配置面板"""

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, Dict, Optional

from BreakoutStrategy.param_loader import get_param_loader

from ..config import get_ui_config_loader
from ..config import get_ui_scan_config_loader
from ..config.param_editor_state import get_param_editor_state
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
        on_use_template_changed_callback: Optional[Callable] = None,
        on_template_file_changed_callback: Optional[Callable] = None,
        get_file_validator_callback: Optional[Callable] = None,
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
            on_use_template_changed_callback: Use Template 复选框状态变化回调
            on_template_file_changed_callback: 模板文件选择变化回调
            get_file_validator_callback: 获取文件验证器的回调（模板模式下返回兼容性验证器）
        """
        self.parent = parent
        self.on_load_callback = on_load_callback
        self.on_param_changed_callback = on_param_changed_callback
        self.on_display_option_changed_callback = on_display_option_changed_callback
        self.on_rescan_all_callback = on_rescan_all_callback
        self.on_new_scan_callback = on_new_scan_callback
        self.get_json_params_callback = get_json_params_callback
        self.on_use_template_changed_callback = on_use_template_changed_callback
        self.on_template_file_changed_callback = on_template_file_changed_callback
        self.get_file_validator_callback = get_file_validator_callback
        self.use_template_var = tk.BooleanVar(value=False)
        self.current_template_file = ""

        # 加载默认显示选项
        config_loader = get_ui_config_loader()
        defaults = config_loader.get_display_options_defaults()

        # 显示选项变量
        self.show_bo_score_var = tk.BooleanVar(
            value=defaults.get("show_bo_score", False)
        )
        self.show_superseded_peaks_var = tk.BooleanVar(
            value=defaults.get("show_superseded_peaks", True)
        )
        self.show_bo_label_var = tk.BooleanVar(
            value=defaults.get("show_bo_label", True)
        )
        # bo_label_n 的初始值来自默认 20；scan 加载后由 set_bo_label_n_default 更新
        self.bo_label_n_var = tk.IntVar(value=20)

        # UI 参数选项（默认不选中 = Browse Mode，加载 scan 后直接浏览已算结果）
        self.use_ui_params_var = tk.BooleanVar(value=False)

        # 当前参数文件名（不含路径）
        self.current_param_file = "all_factor.yaml"

        # 参数加载器（纯读：只读策略参数）
        self.param_loader = get_param_loader()

        # 编辑器 UI 状态（活跃文件、dirty、监听器、切换钩子）
        self.editor_state = get_param_editor_state()

        # 扫描配置加载器
        self.scan_config_loader = get_ui_scan_config_loader()

        # 订阅 ParamEditorState 状态变化（统一状态同步）
        self.editor_state.add_listener(self._on_param_loader_state_changed)

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
            text="BO Score",
            variable=self.show_bo_score_var,
            command=self._on_checkbox_changed,
        ).pack(side=tk.LEFT, padx=5)

        # BO Label 复选框 + N Spinbox（同一组）
        self.show_bo_label_checkbox = ttk.Checkbutton(
            container,
            text="BO Label",
            variable=self.show_bo_label_var,
            command=self._on_bo_label_toggle,
        )
        self.show_bo_label_checkbox.pack(side=tk.LEFT, padx=(5, 2))

        ttk.Label(container, text="N:").pack(side=tk.LEFT)
        # 不传 command=，箭头点击 / 滚轮滚动仅改变 Spinbox 显示值，不触发重绘；
        # 用户在任意调整后按 Enter 才确认提交。这样滚轮滚动顺畅可控。
        self.bo_label_n_spin = ttk.Spinbox(
            container,
            from_=1,
            to=200,
            increment=1,
            textvariable=self.bo_label_n_var,
            width=4,
            # 初始 state 跟随 BO Label checkbox，避免与默认勾选状态不一致
            state="normal" if self.show_bo_label_var.get() else "disabled",
        )
        self.bo_label_n_spin.pack(side=tk.LEFT, padx=(2, 5))

        # Enter（主键盘或小键盘）是唯一的提交入口——输入 / 箭头 / 滚轮调整后，
        # 用户按 Enter 才真正刷新 chart。不监听 FocusOut，避免回车刷新重建 chart
        # 造成焦点切走从而双重触发。
        self.bo_label_n_spin.bind("<Return>", self._on_bo_label_n_enter)
        self.bo_label_n_spin.bind("<KP_Enter>", self._on_bo_label_n_enter)

        ttk.Checkbutton(
            container,
            text="SU_PK",
            variable=self.show_superseded_peaks_var,
            command=self._on_checkbox_changed,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Separator(container, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        # 模板选择组
        template_group_frame = ttk.Frame(container)
        template_group_frame.pack(side=tk.LEFT, padx=5)

        self.use_template_checkbox = ttk.Checkbutton(
            template_group_frame,
            variable=self.use_template_var,
            command=self._on_use_template_changed,
        )
        self.use_template_checkbox.pack(side=tk.LEFT, padx=(0, 5))

        self.template_file_combobox = ttk.Combobox(
            template_group_frame,
            state="disabled",
            width=20,
            values=self._get_available_template_files(),
        )
        self.template_file_combobox.pack(side=tk.LEFT, padx=5)
        template_files = self._get_available_template_files()
        if template_files:
            self.template_file_combobox.set(template_files[0])
            self.current_template_file = template_files[0]
        self.template_file_combobox.bind("<<ComboboxSelected>>", self._on_template_file_selected)

        # 状态标签
        self.status_label = ttk.Label(container, text="Ready", foreground="gray")
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # 根据 use_ui_params_var 初始值同步组件状态
        self._update_combobox_state()

    def _on_load_scan_clicked(self):
        """加载扫描结果按钮点击"""
        # 从配置文件加载默认目录
        config_loader = get_ui_config_loader()
        default_dir = config_loader.get_scan_results_dir()

        # 模板模式激活时，获取兼容性验证器进行预过滤
        validator = None
        if self.get_file_validator_callback:
            validator = self.get_file_validator_callback()

        # 使用自定义文件对话框（支持 Delete 键删除文件）
        file_path = custom_askopenfilename(
            parent=self.parent.winfo_toplevel(),
            title="Select Scan Results",
            initialdir=default_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            file_validator=validator,
        )

        if file_path and self.on_load_callback:
            self.on_load_callback(file_path)

    def _on_checkbox_changed(self):
        """复选框状态改变回调"""
        if self.on_display_option_changed_callback:
            self.on_display_option_changed_callback()
        elif self.on_param_changed_callback:
            self.on_param_changed_callback()

    def _on_bo_label_toggle(self):
        """BO Label checkbox toggle：同步 Spinbox 启停，并触发重绘。"""
        if self.show_bo_label_var.get():
            self.bo_label_n_spin.config(state="normal")
        else:
            self.bo_label_n_spin.config(state="disabled")
        self._on_checkbox_changed()

    def _on_bo_label_n_enter(self, _event):
        """Spinbox Enter：触发 chart 重绘，然后把焦点还给 Spinbox。

        重绘会销毁并重建 matplotlib canvas，新 canvas 默认抢键盘焦点；不还回来的话
        下一次 Enter 会送到 canvas，Spinbox 的 <Return> 绑定不再触发。用 after_idle
        排到事件队列末尾，确保在 canvas 自动抢焦之后执行。
        """
        self._on_checkbox_changed()
        self.bo_label_n_spin.after_idle(self.bo_label_n_spin.focus_set)

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
        try:
            n = self.bo_label_n_var.get()
        except tk.TclError:
            # Spinbox 文本非整数（用户输入非法字符时），回退默认
            n = 20
        return {
            "show_bo_score": self.show_bo_score_var.get(),
            "show_superseded_peaks": self.show_superseded_peaks_var.get(),
            "show_bo_label": self.show_bo_label_var.get(),
            "bo_label_n": n,
        }

    def set_bo_label_n_default(self, max_days: int):
        """把 Spinbox 当前值重置为指定默认值。

        通常在加载新 scan 时由 main.py 调用，让 Spinbox 默认反映扫描时的
        label_configs[0].max_days，与股票列表 Label 列的聚合基准一致。

        Args:
            max_days: 扫描的窗口天数；clamp 到 [1, 200]
        """
        n = max(1, min(200, int(max_days)))
        self.bo_label_n_var.set(n)

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
        响应 ParamEditorState 状态变化的监听器

        当编辑器 Load/Apply/Save 时，ParamEditorState 会通知此方法，
        自动同步下拉菜单显示
        """
        try:
            # 获取当前活跃文件名
            active_file = self.editor_state.get_active_file_name()
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
        扫描 configs/params/ 目录，获取所有 .yaml 文件

        Returns:
            文件名列表（只包含文件名，不含路径）
        """
        params_dir = (
            self.param_loader.get_project_root()
            / "configs"
            / "params"
        )

        if not params_dir.exists():
            return ["all_factor.yaml"]

        # 获取所有 .yaml 文件
        yaml_files = [f.name for f in params_dir.glob("*.yaml")]

        if not yaml_files:
            return ["all_factor.yaml"]

        # 排序（all_factor.yaml 优先）
        yaml_files.sort(key=lambda x: (x != "all_factor.yaml", x))

        return yaml_files

    def _load_param_file(self, file_path):
        """
        加载指定参数文件到 ParamEditorState 内存

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
        self.editor_state.set_active_file(file_path, params)

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
            if not self.editor_state.request_file_switch(file_path, params):
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
        """根据模式更新 UI 组件的启用/禁用状态

        三种模式优先级：Template Mode > Analysis Mode > Browse Mode
        """
        template_active = self.use_template_var.get()

        if template_active:
            # Template Mode：强制 Browse，禁用 Analysis 相关控件
            self.use_ui_params_var.set(False)
            self.use_ui_params_checkbox.config(state="disabled")
            self.param_file_combobox.config(state="disabled")
            self.edit_btn.config(state="disabled")
            self.rescan_all_btn.config(state="disabled")
        elif self.use_ui_params_var.get():
            # Analysis Mode
            self.use_ui_params_checkbox.config(state="normal")
            self.param_file_combobox.config(state="readonly")
            self.edit_btn.config(state="normal")
            self.rescan_all_btn.config(state="normal")
        else:
            # Browse Mode
            self.use_ui_params_checkbox.config(state="normal")
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

    def _get_available_template_files(self) -> list[str]:
        """扫描 configs/templates/ 目录获取所有 .yaml 文件"""
        templates_dir = self.param_loader.get_project_root() / "configs" / "templates"
        if not templates_dir.exists():
            return []
        yaml_files = sorted(f.name for f in templates_dir.glob("*.yaml"))
        return yaml_files

    def _on_use_template_changed(self):
        """Use Template 复选框状态变化"""
        self._update_template_combobox_state()
        self._update_combobox_state()  # 同步 Analysis 控件状态
        if self.on_use_template_changed_callback:
            self.on_use_template_changed_callback(self.use_template_var.get())

    def _on_template_file_selected(self, event=None):
        """模板文件下拉框选择变化"""
        selected = self.template_file_combobox.get()
        if selected == self.current_template_file:
            return
        self.current_template_file = selected
        if self.on_template_file_changed_callback:
            self.on_template_file_changed_callback(selected)

    def _update_template_combobox_state(self):
        """根据复选框状态启用/禁用模板下拉框"""
        if self.use_template_var.get():
            self.template_file_combobox.config(state="readonly")
        else:
            self.template_file_combobox.config(state="disabled")

    def get_use_template(self) -> bool:
        """获取 Use Template 复选框状态"""
        return self.use_template_var.get()

    def get_template_file_path(self) -> str | None:
        """获取当前选中的模板文件完整路径"""
        filename = self.template_file_combobox.get()
        if not filename:
            return None
        return str(self.param_loader.get_project_root() / "configs" / "templates" / filename)
