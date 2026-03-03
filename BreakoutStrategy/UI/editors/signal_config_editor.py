"""信号配置编辑器"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

import yaml

# B 信号的 peak_measure 和 breakout_modes 选项
MEASURE_OPTIONS_B = ["high", "close", "body_top"]

# D 信号的 tr1_measure 和 tr2_modes 选项
MEASURE_OPTIONS_D = ["low", "close", "body_bottom"]

# D 信号的 bounce_high_measure 选项
BOUNCE_HIGH_MEASURE_OPTIONS = ["close", "high"]

# D 信号严格度定义 (数值越大越严格)
STRICTNESS_D = {"low": 1, "body_bottom": 2, "close": 3}


class SignalConfigEditor:
    """
    信号配置编辑器

    编辑 configs/signals/absolute_signals.yaml 的可视化界面
    使用 Grid 布局确保按钮区域始终可见
    """

    def __init__(
        self,
        parent,
        config_path: Path,
        on_apply_callback: Optional[Callable] = None,
        on_save_as_callback: Optional[Callable] = None,
    ):
        """
        初始化编辑器

        Args:
            parent: 父窗口
            config_path: 配置文件路径
            on_apply_callback: Apply 按钮回调
            on_save_as_callback: Save As 回调 (new_path, config)
        """
        self.config_path = config_path
        self.on_apply_callback = on_apply_callback
        self.on_save_as_callback = on_save_as_callback
        self._original_config = {}  # FILE_VALUE (F) - 磁盘配置
        self._memory_config = {}  # MEMORY_VALUE (M) - 内存配置
        self._vars = {}  # UI_VALUE (U) - 存储所有 Tkinter 变量

        # 按钮引用 (用于状态管理)
        self._apply_btn = None
        self._save_btn = None
        self._reset_btn = None

        # 创建窗口 (尺寸延迟到 UI 创建完成后自适应设置)
        self.window = tk.Toplevel(parent)
        self.window.title("Param Editor")
        self.window.transient(parent)

        # 加载配置
        self._load_config()

        # 创建 UI
        self._create_ui()


    def _load_config(self):
        """从文件加载配置，同步初始化内存配置"""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._original_config = yaml.safe_load(f) or {}
        else:
            self._original_config = {}
        # 初始化时内存配置与文件配置一致
        import copy

        self._memory_config = copy.deepcopy(self._original_config)

    def _create_ui(self):
        """
        创建 UI 组件

        使用 Grid 布局：
        - Row 0: 配置文件路径 (weight=0, 固定高度)
        - Row 1: 滚动内容区 (weight=1, 可扩展)
        - Row 2: 按钮区 (weight=0, 固定高度)
        """
        # 配置 window 的 grid 权重 - 单列布局
        self.window.rowconfigure(0, weight=0)  # 路径标签固定
        self.window.rowconfigure(1, weight=1)  # 滚动容器可扩展
        self.window.rowconfigure(2, weight=0)  # 按钮区固定
        self.window.columnconfigure(0, weight=1)  # 单列布局，可扩展

        # 1. 创建配置文件路径标签
        self._create_path_label()

        # 2. 创建滚动内容区
        self._create_scroll_area()

        # 3. 创建按钮区域
        self._create_buttons()

        # 3. 创建各配置区块（填充到 scrollable_frame）
        # Display 配置已移至主界面底部控制栏（DisplayControlBar）
        self._create_breakout_section()
        self._create_high_volume_section()
        self._create_double_trough_section()
        self._create_big_yang_section()
        self._create_support_analysis_section()

        # 4. 强制更新滚动区域和窗口尺寸（确保所有内容渲染完成后）
        self.window.after_idle(self._finalize_layout)

    def _finalize_layout(self):
        """完成布局：更新滚动区域并自适应窗口尺寸"""
        self.scrollable_frame.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._adjust_window_size()
        # 初始化按钮状态
        self._update_button_states()

    def _adjust_window_size(self):
        """根据内容自适应调整窗口尺寸"""
        self.window.update_idletasks()

        # 获取按钮区域所需宽度
        btn_width = self._btn_frame.winfo_reqwidth()

        # 考虑滚动区域和边距，取较大值
        content_width = self.scrollable_frame.winfo_reqwidth() + 25  # 滚动条+边距

        # 计算所需宽度，至少 600px
        min_width = max(btn_width, content_width, 600)

        # 计算内容所需高度
        content_height = self.scrollable_frame.winfo_reqheight()
        # 加上路径标签和按钮区域的高度，以及边距
        path_height = 30  # 路径标签区域估计高度
        btn_height = self._btn_frame.winfo_reqheight()
        total_height = content_height + path_height + btn_height + 40  # 40 为额外边距

        # 限制最大高度为屏幕高度的 90%
        screen_height = self.window.winfo_screenheight()
        max_height = int(screen_height * 0.9)
        final_height = min(total_height, max_height)

        self.window.geometry(f"{min_width}x{final_height}")
        self.window.minsize(min_width, 500)

    def _create_path_label(self):
        """创建配置文件路径标签 (Grid row=0)"""
        # 计算相对路径
        try:
            rel_path = self.config_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = self.config_path

        path_frame = ttk.Frame(self.window, padding=(10, 5))
        path_frame.grid(row=0, column=0, sticky="ew")

        self._path_label = ttk.Label(
            path_frame, text=f"Config: {rel_path}", foreground="gray"
        )
        self._path_label.pack(anchor="w")

    def _create_scroll_area(self):
        """创建带滚动条的内容区 (Grid row=1)"""
        # 使用容器 Frame 隔离滚动区域
        scroll_container = ttk.Frame(self.window)
        scroll_container.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        scroll_container.grid_rowconfigure(0, weight=1)
        scroll_container.grid_columnconfigure(0, weight=1)

        # Canvas 用于实现滚动 - 放在容器内
        self._canvas = tk.Canvas(scroll_container, highlightthickness=1, relief="sunken")
        self._canvas.grid(row=0, column=0, sticky="nsew")

        # 垂直滚动条 - 也放在容器内
        scrollbar = ttk.Scrollbar(
            scroll_container, orient="vertical", command=self._canvas.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._canvas.configure(yscrollcommand=scrollbar.set)

        # 可滚动的内部 Frame
        self.scrollable_frame = ttk.Frame(self._canvas)
        self._frame_window_id = self._canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw"
        )

        # 事件绑定
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # 鼠标滚轮支持 (Linux)
        self._canvas.bind("<Button-4>", lambda e: self._canvas.yview_scroll(-1, "units"))
        self._canvas.bind("<Button-5>", lambda e: self._canvas.yview_scroll(1, "units"))

    def _on_frame_configure(self, event):
        """当 scrollable_frame 内容变化时，更新 Canvas 的滚动区域"""
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """当 Canvas 大小变化时，同步更新 scrollable_frame 的宽度"""
        self._canvas.itemconfig(self._frame_window_id, width=event.width)

    def _create_buttons(self):
        """创建按钮区域 (Grid row=2)"""
        self._btn_frame = ttk.Frame(self.window, padding=(10, 5))
        self._btn_frame.grid(row=2, column=0, sticky="ew")

        # 使用 grid 布局确保所有按钮可见
        self._btn_frame.columnconfigure(0, weight=0)
        self._btn_frame.columnconfigure(1, weight=0)
        self._btn_frame.columnconfigure(2, weight=0)
        self._btn_frame.columnconfigure(3, weight=0)
        self._btn_frame.columnconfigure(4, weight=1)  # 弹性空间
        self._btn_frame.columnconfigure(5, weight=0)

        # 保存按钮引用以便状态管理
        self._apply_btn = ttk.Button(self._btn_frame, text="Apply", command=self._on_apply)
        self._apply_btn.grid(row=0, column=0, padx=5, sticky="w")

        self._save_btn = ttk.Button(self._btn_frame, text="Save", command=self._on_save)
        self._save_btn.grid(row=0, column=1, padx=5, sticky="w")

        self._save_as_btn = ttk.Button(self._btn_frame, text="Save As", command=self._on_save_as)
        self._save_as_btn.grid(row=0, column=2, padx=5, sticky="w")

        self._reset_btn = ttk.Button(self._btn_frame, text="Reset", command=self._on_reset)
        self._reset_btn.grid(row=0, column=3, padx=5, sticky="w")

        # 弹性空间在 column=4
        ttk.Button(self._btn_frame, text="Cancel", command=self.window.destroy).grid(
            row=0, column=5, padx=5, sticky="e"
        )

    def _create_section_frame(self, title: str, enabled_key: str = None) -> ttk.LabelFrame:
        """创建一个配置区块"""
        frame = ttk.LabelFrame(self.scrollable_frame, text=title, padding=10)
        frame.pack(fill=tk.X, padx=10, pady=5)

        if enabled_key:
            enabled_var = tk.BooleanVar(
                value=self._original_config.get(enabled_key, {}).get("enabled", True)
            )
            self._vars[f"{enabled_key}.enabled"] = enabled_var
            # 添加变量变化追踪
            enabled_var.trace_add("write", self._on_var_changed)
            ttk.Checkbutton(frame, text="Enabled", variable=enabled_var).pack(anchor="w")

        return frame

    def _create_param_row(self, parent, label: str, key: str, default, param_type=float):
        """创建参数输入行"""
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)

        # 使用只读 Entry 替代 Label，支持文本选中复制
        label_entry = ttk.Entry(row, width=20)
        label_entry.insert(0, label)
        label_entry.configure(state="readonly")
        label_entry.pack(side=tk.LEFT)

        var = tk.StringVar(value=str(self._get_nested_value(key, default)))
        self._vars[key] = var

        # 添加变量变化追踪
        var.trace_add("write", self._on_var_changed)

        entry = ttk.Entry(row, textvariable=var, width=15)
        entry.pack(side=tk.LEFT, padx=5)

        return var

    def _create_combo_row(
        self, parent, label: str, key: str, options: List[str], default: str
    ) -> tk.StringVar:
        """
        创建单选下拉框行

        Args:
            parent: 父容器
            label: 标签文本
            key: 配置键名
            options: 可选值列表
            default: 默认值

        Returns:
            StringVar 变量
        """
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)

        # 使用只读 Entry 替代 Label，支持文本选中复制
        label_entry = ttk.Entry(row, width=20)
        label_entry.insert(0, label)
        label_entry.configure(state="readonly")
        label_entry.pack(side=tk.LEFT)

        var = tk.StringVar(value=str(self._get_nested_value(key, default)))
        self._vars[key] = var

        # 添加变量变化追踪
        var.trace_add("write", self._on_var_changed)

        combo = ttk.Combobox(row, textvariable=var, values=options, width=12, state="readonly")
        combo.pack(side=tk.LEFT, padx=5)

        return var

    def _create_multi_select_row(
        self, parent, label: str, key: str, options: List[str], default: List[str]
    ) -> Dict[str, tk.BooleanVar]:
        """
        创建复选框行

        Args:
            parent: 父容器
            label: 标签文本
            key: 配置键名
            options: 可选值列表
            default: 默认选中值列表

        Returns:
            {option: BooleanVar} 字典
        """
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)

        # 使用只读 Entry 替代 Label，支持文本选中复制
        label_entry = ttk.Entry(row, width=20)
        label_entry.insert(0, label)
        label_entry.configure(state="readonly")
        label_entry.pack(side=tk.LEFT)

        # 获取当前值
        current_values = self._get_nested_value(key, default)
        if not isinstance(current_values, list):
            current_values = default

        # 为每个选项创建 BooleanVar
        var_dict = {}
        for option in options:
            var = tk.BooleanVar(value=option in current_values)
            var_dict[option] = var
            # 添加变量变化追踪
            var.trace_add("write", self._on_var_changed)
            cb = ttk.Checkbutton(row, text=option, variable=var)
            cb.pack(side=tk.LEFT, padx=3)

        # 将字典存入 _vars，key 保持原样
        self._vars[key] = var_dict

        return var_dict

    def _get_nested_value(self, key: str, default):
        """获取嵌套配置值"""
        parts = key.split(".")
        value = self._original_config
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part, {})
            else:
                return default
        # 处理 None 值（如 support_trough.window: null）
        if value is None:
            return ""
        return value if value != {} else default

    def _create_breakout_section(self):
        """创建 Breakout 配置区"""
        frame = self._create_section_frame("Breakout (B)", "breakout")
        self._create_param_row(
            frame, "Detection_Lookback", "breakout.detection_lookback_days", 126, int
        )
        self._create_param_row(frame, "Total_Window", "breakout.total_window", 60, int)
        self._create_param_row(frame, "Min_Side_Bars", "breakout.min_side_bars", 15, int)
        self._create_param_row(
            frame, "Min_Rel_Height", "breakout.min_relative_height", 0.2, float
        )
        self._create_param_row(
            frame, "Exceed_Threshold", "breakout.exceed_threshold", 0.01, float
        )
        self._create_param_row(
            frame, "Peak_Supersede_Thr", "breakout.peak_supersede_threshold", 0.03, float
        )
        # 比较标准设置
        self._create_combo_row(
            frame, "Peak_Measure", "breakout.peak_measure", MEASURE_OPTIONS_B, "body_top"
        )
        self._create_multi_select_row(
            frame, "Breakout_Modes", "breakout.breakout_modes", MEASURE_OPTIONS_B, ["close"]
        )

    def _create_high_volume_section(self):
        """创建 High Volume 配置区"""
        frame = self._create_section_frame("High Volume (V)", "high_volume")
        self._create_param_row(frame, "Max_of", "high_volume.lookback_days", 126, int)
        self._create_param_row(
            frame, "RV_Period", "high_volume.volume_ma_period", 20, int
        )
        self._create_param_row(
            frame, "RV_threthold", "high_volume.volume_multiplier", 3.0, float
        )

    def _create_double_trough_section(self):
        """创建 Double Trough 配置区"""
        frame = self._create_section_frame("Double Trough (D)", "double_trough")
        self._create_param_row(frame, "Min_of", "double_trough.min_of", 126, int)
        self._create_param_row(
            frame, "Bounce_ATR", "double_trough.first_bounce_atr", 4.0, float
        )
        self._create_param_row(
            frame, "Depth_ATR", "double_trough.min_tr2_depth_atr", 2.0, float
        )
        self._create_param_row(
            frame, "Recovery_ATR", "double_trough.min_recovery_atr", 0.1, float
        )
        self._create_param_row(
            frame, "ATR_Period", "double_trough.atr_period", 14, int
        )
        self._create_param_row(
            frame, "Max_Gap_Days", "double_trough.max_gap_days", 60, int
        )
        self._create_param_row(
            frame, "Trough_Window", "double_trough.trough.window", 6, int
        )
        self._create_param_row(
            frame, "Trough_Min_Side", "double_trough.trough.min_side_bars", 2, int
        )
        # 支撑测试 trough 检测参数
        self._create_param_row(
            frame, "Sup_Trough_Window", "double_trough.support_trough.window", "", str
        )
        self._create_param_row(
            frame, "Sup_Trough_Min_Side", "double_trough.support_trough.min_side_bars", 1, int
        )
        # 比较标准设置
        self._create_combo_row(
            frame, "TR1_Measure", "double_trough.tr1_measure", MEASURE_OPTIONS_D, "low"
        )
        self._create_combo_row(
            frame, "TR2_Measure", "double_trough.tr2_measure", MEASURE_OPTIONS_D, "low"
        )
        self._create_combo_row(
            frame, "Bounce_High_Measure", "double_trough.bounce_high_measure",
            BOUNCE_HIGH_MEASURE_OPTIONS, "close"
        )

    def _create_big_yang_section(self):
        """创建 Big Yang 配置区"""
        frame = self._create_section_frame("Big Yang (Y)", "big_yang")
        self._create_param_row(
            frame, "Volatility_Lookback", "big_yang.volatility_lookback", 252, int
        )
        self._create_param_row(
            frame, "Sigma_Threshold", "big_yang.sigma_threshold", 2.5, float
        )

    def _create_support_analysis_section(self):
        """创建 Support Analysis 配置区"""
        frame = self._create_section_frame("Support Analysis", "support_analysis")
        self._create_param_row(
            frame, "BO_Tolerance_Pct", "support_analysis.breakout_tolerance_pct", 5.0, float
        )
        self._create_param_row(
            frame, "TR_Tolerance_Pct", "support_analysis.trough_tolerance_pct", 5.0, float
        )
        self._create_param_row(
            frame, "Max_Lookforward", "support_analysis.max_lookforward_days", 90, int
        )

    def _collect_config(self) -> dict:
        """从 UI 收集配置"""
        config = {}

        for key, var in self._vars.items():
            parts = key.split(".")

            # 处理多选变量 (dict of BooleanVars)
            if isinstance(var, dict):
                # 收集选中的选项
                value = [opt for opt, bool_var in var.items() if bool_var.get()]
            else:
                value = var.get()

                # 转换类型
                if key.endswith(".enabled"):
                    value = var.get()  # BooleanVar
                elif "." in key and any(
                    x in key
                    for x in ["window", "days", "period", "bars", "percentile", "lookback", "months", "gap", "min_of"]
                ):
                    # 支持 null 值（如 support_trough.window）
                    if value.strip().lower() in ("", "null", "none"):
                        value = None
                    else:
                        value = int(value)
                elif any(x in key for x in ["threshold", "height", "multiplier", "pct", "depth", "atr"]):
                    value = float(value)

            # 设置嵌套值
            d = config
            for part in parts[:-1]:
                if part not in d:
                    d[part] = {}
                d = d[part]
            d[parts[-1]] = value

        return config

    def _validate_config(self, config: dict) -> Optional[str]:
        """
        验证配置的有效性

        检查无效组合：
        - B 信号: peak_measure=close + breakout_modes 含 high → 无效
        - R 信号: TR1 严格程度 > TR2 中任一选项 → 无效

        Args:
            config: 配置字典

        Returns:
            错误信息，如果有效则返回 None
        """
        # 验证 B 信号配置
        bo_config = config.get("breakout", {})
        if bo_config.get("enabled", True):
            peak_measure = bo_config.get("peak_measure", "body_top")
            breakout_modes = bo_config.get("breakout_modes", ["close"])

            # peak_measure=close 时，breakout_modes 不能包含 high
            if peak_measure == "close" and "high" in breakout_modes:
                return (
                    "Invalid B config: peak_measure='close' cannot be combined with "
                    "breakout_modes containing 'high'.\n"
                    "(close 永远不会超过 high)"
                )

        # 验证 D 信号配置
        dt_config = config.get("double_trough", {})
        if dt_config.get("enabled", False):
            tr1_measure = dt_config.get("tr1_measure", "low")
            tr2_measure = dt_config.get("tr2_measure", "low")

            tr1_strictness = STRICTNESS_D.get(tr1_measure, 1)
            tr2_strictness = STRICTNESS_D.get(tr2_measure, 1)
            if tr1_strictness > tr2_strictness:
                return (
                    f"Invalid D config: tr1_measure='{tr1_measure}' is stricter than "
                    f"tr2_measure='{tr2_measure}'.\n"
                    f"(严格程度: close > body_bottom > low)\n"
                    f"TR1 衡量标准不能比 TR2 更严格。"
                )

        return None

    def _on_apply(self):
        """Apply 按钮回调: M := U"""
        try:
            config = self._collect_config()

            # 验证配置
            error = self._validate_config(config)
            if error:
                messagebox.showerror("Invalid Configuration", error)
                return

            import copy

            self._memory_config = copy.deepcopy(config)
            if self.on_apply_callback:
                self.on_apply_callback(config)
            self._update_button_states()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply: {e}")

    def _on_save(self):
        """Save 按钮回调: F := U, M := U，并自动 Apply"""
        try:
            config = self._collect_config()

            # 验证配置
            error = self._validate_config(config)
            if error:
                messagebox.showerror("Invalid Configuration", error)
                return

            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            import copy

            self._original_config = copy.deepcopy(config)
            self._memory_config = copy.deepcopy(config)
            # 自动调用 Apply 回调
            if self.on_apply_callback:
                self.on_apply_callback(config)
            self._update_button_states()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")

    def _on_save_as(self):
        """Save As 按钮回调: 保存到新文件，自动 Apply 并通知主界面"""
        try:
            config = self._collect_config()

            # 验证配置
            error = self._validate_config(config)
            if error:
                messagebox.showerror("Invalid Configuration", error)
                return

            # 默认保存到 params 目录
            default_dir = self.config_path.parent
            if self.config_path.parent.name != "params":
                params_dir = self.config_path.parent / "params"
                if params_dir.exists():
                    default_dir = params_dir

            save_path = filedialog.asksaveasfilename(
                parent=self.window,
                title="Save Config As",
                initialdir=str(default_dir),
                defaultextension=".yaml",
                filetypes=[("YAML files", "*.yaml")],
            )

            if not save_path:
                return

            save_path = Path(save_path)
            with open(save_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

            import copy

            # 更新编辑器状态为新文件
            self.config_path = save_path
            self._original_config = copy.deepcopy(config)
            self._memory_config = copy.deepcopy(config)

            # 更新路径标签
            try:
                rel_path = save_path.relative_to(Path.cwd())
            except ValueError:
                rel_path = save_path
            self._path_label.config(text=f"Config: {rel_path}")

            # 自动 Apply
            if self.on_apply_callback:
                self.on_apply_callback(config)

            # 通知主界面
            if self.on_save_as_callback:
                self.on_save_as_callback(save_path, config)

            self._update_button_states()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save as: {e}")

    def _on_reset(self):
        """Reset 按钮回调: U := F, M := F"""
        self._load_config()
        # 重新填充所有变量
        for key, var in self._vars.items():
            default = self._get_nested_value(key, "")
            if isinstance(var, dict):
                # 多选变量 (dict of BooleanVars)
                default_list = default if isinstance(default, list) else []
                for opt, bool_var in var.items():
                    bool_var.set(opt in default_list)
            elif isinstance(var, tk.BooleanVar):
                var.set(bool(default))
            else:
                var.set(str(default))
        self._update_button_states()

    # ========== 状态管理方法 ==========

    def _is_dirty_vs_memory(self) -> bool:
        """检查 UI 值是否与内存值不同 (U != M)"""
        try:
            ui_config = self._collect_config()
            return ui_config != self._memory_config
        except (ValueError, TypeError):
            # 输入值无法解析时视为有变化
            return True

    def _is_dirty_vs_file(self) -> bool:
        """检查内存值是否与文件值不同 (M != F)"""
        return self._memory_config != self._original_config

    def _update_button_states(self):
        """根据当前状态更新按钮启用/禁用"""
        dirty_vs_memory = self._is_dirty_vs_memory()
        dirty_vs_file = self._is_dirty_vs_file()

        # Apply: 仅当 UI 与内存不同时启用
        state_apply = "normal" if dirty_vs_memory else "disabled"
        # Save/Reset: 当存在任何未保存修改时启用
        state_save_reset = "normal" if (dirty_vs_memory or dirty_vs_file) else "disabled"

        if self._apply_btn:
            self._apply_btn.configure(state=state_apply)
        if self._save_btn:
            self._save_btn.configure(state=state_save_reset)
        if self._reset_btn:
            self._reset_btn.configure(state=state_save_reset)

    def _on_var_changed(self, *args):
        """变量变化回调，更新按钮状态"""
        self._update_button_states()
