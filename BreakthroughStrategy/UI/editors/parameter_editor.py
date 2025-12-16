"""参数编辑器窗口

提供图形化的参数编辑界面，支持加载、编辑、保存和应用参数
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, Optional

import yaml

from ..config import (
    PARAM_CONFIGS,
    SECTION_TITLES,
    get_param_count,
    get_weight_group_names,
)
from .input_factory import BaseParameterInput, ParameterInputFactory
from ..config import WeightGroupValidator
from ..config import UIParamLoader
from ..config import ParameterStateManager
from ..styles import FONT_SECTION_TITLE, FONT_STATUS, FONT_WEIGHT_SUM
from ..config import YamlCommentParser


class AccordionSection:
    """单个折叠分组组件"""

    def __init__(self, parent, section_key: str, title: str, param_count: int,
                 on_toggle_callback: Optional[Callable] = None):
        """
        初始化折叠分组

        Args:
            parent: 父容器
            section_key: 分组键（如'breakthrough_detector'）
            title: 显示标题
            param_count: 参数数量
            on_toggle_callback: 展开/折叠时的回调（用于调整窗口大小）
        """
        self.parent = parent
        self.section_key = section_key
        self.title = title
        self.param_count = param_count
        self.expanded = False
        self.param_inputs = []  # 存储该分组的所有输入组件
        self.on_toggle_callback = on_toggle_callback

        # 主容器
        self.frame = ttk.Frame(parent, relief="solid", borderwidth=1)
        self.frame.pack(fill="x", padx=10, pady=5)

        # 创建标题栏
        self._create_title_bar()

        # 创建内容区域（初始隐藏）
        self.content_frame = ttk.Frame(self.frame, padding=10)

    def _create_title_bar(self):
        """创建标题栏"""
        self.title_frame = ttk.Frame(self.frame, style="TFrame")
        self.title_frame.pack(fill="x", padx=5, pady=5)

        # 标题标签（显示 ▶ 或 ▼）- 使用统一字体样式
        self.title_label = ttk.Label(
            self.title_frame,
            text=f"▶ {self.title} ({self.param_count} params)",
            font=FONT_SECTION_TITLE,
            cursor="hand2",
        )
        self.title_label.pack(side="left")

        # 绑定点击事件
        self.title_label.bind("<Button-1>", lambda e: self.toggle())
        self.title_frame.bind("<Button-1>", lambda e: self.toggle())

    def toggle(self):
        """展开/折叠"""
        self.expanded = not self.expanded

        if self.expanded:
            # 展开
            self.title_label.config(text=f"▼ {self.title} ({self.param_count} params)")
            self.content_frame.pack(fill="both", expand=True, padx=5, pady=5)
        else:
            # 折叠
            self.title_label.config(text=f"▶ {self.title} ({self.param_count} params)")
            self.content_frame.pack_forget()

        # 触发Canvas更新scrollregion
        self.frame.update_idletasks()

        # 通知窗口调整大小
        if self.on_toggle_callback:
            self.on_toggle_callback()

    def add_parameter(self, param_input: BaseParameterInput):
        """添加参数输入组件"""
        self.param_inputs.append(param_input)
        param_input.frame.pack(fill="x", pady=2)

    def get_all_values(self) -> Dict[str, Any]:
        """获取该分组所有参数值"""
        values = {}
        for param_input in self.param_inputs:
            # 处理嵌套参数（如 peak_weights.volume）
            if "." in param_input.param_name:
                parts = param_input.param_name.split(".")
                parent_key = parts[0]
                child_key = parts[1]
                if parent_key not in values:
                    values[parent_key] = {}
                values[parent_key][child_key] = param_input.get_value()
            else:
                values[param_input.param_name] = param_input.get_value()
        return values

    def validate_all(self) -> list:
        """验证该分组所有参数，返回错误列表"""
        errors = []
        for param_input in self.param_inputs:
            is_valid, error_msg = param_input.validate()
            if not is_valid:
                errors.append(f"{param_input.param_name}: {error_msg}")
                param_input.highlight_error(True)
            else:
                param_input.highlight_error(False)
        return errors


class ScrollableAccordion:
    """可滚动的折叠分组容器"""

    def __init__(self, parent, on_section_toggle_callback: Optional[Callable] = None):
        """
        初始化可滚动容器

        Args:
            parent: 父容器
            on_section_toggle_callback: 分组展开/折叠时的回调
        """
        self.parent = parent
        self.sections = []
        self.on_section_toggle_callback = on_section_toggle_callback

        # 创建Canvas和Scrollbar
        self.canvas = tk.Canvas(parent, highlightthickness=0, bg="white")
        self.scrollbar = ttk.Scrollbar(
            parent, orient="vertical", command=self.canvas.yview
        )

        # 创建可滚动的Frame
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas_frame = self.canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw"
        )

        # 绑定Canvas宽度调整
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # 鼠标滚轮支持
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        # Linux支持
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _on_canvas_configure(self, event):
        """Canvas大小调整时更新frame宽度"""
        self.canvas.itemconfig(self.canvas_frame, width=event.width)

    def _on_mousewheel(self, event):
        """鼠标滚轮事件处理"""
        # 检查 canvas 是否仍然存在
        if not self.canvas.winfo_exists():
            return
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")

    def add_section(
        self, section_key: str, title: str, param_count: int
    ) -> AccordionSection:
        """添加折叠分组"""
        section = AccordionSection(
            self.scrollable_frame, section_key, title, param_count,
            on_toggle_callback=self.on_section_toggle_callback
        )
        self.sections.append(section)
        return section

    def pack(self, **kwargs):
        """布局Canvas和Scrollbar"""
        self.canvas.pack(side="left", fill="both", expand=True, **kwargs)
        self.scrollbar.pack(side="right", fill="y")


class ParameterEditorWindow:
    """参数编辑器主窗口"""

    def __init__(
        self,
        parent,
        ui_param_loader: UIParamLoader,
        on_apply_callback: Optional[Callable] = None,
        json_params: Optional[Dict] = None,
    ):
        """
        初始化参数编辑器窗口

        Args:
            parent: 主窗口
            ui_param_loader: UIParamLoader实例（复用验证逻辑）
            on_apply_callback: Apply时的回调函数（触发图表刷新）
            json_params: JSON 文件中的扫描参数（来自 scan_metadata）
        """
        self.parent = parent
        self.loader = ui_param_loader
        self.on_apply_callback = on_apply_callback
        self.param_configs = PARAM_CONFIGS
        self.section_map = {}  # section_key -> AccordionSection 的映射

        # JSON 参数相关
        self._json_params = json_params  # 原始 JSON 参数
        self._json_column_visible = False  # JSON 列显示状态
        self._json_param_map = self._build_json_param_map()  # 参数名到 JSON 值的映射

        # 初始化状态管理器
        self.state_manager = ParameterStateManager()

        # 初始化注释解析器（从 ui_params.yaml 读取中文注释）
        ui_params_path = (
            self.loader.get_project_root()
            / "configs"
            / "analysis"
            / "params"
            / "ui_params.yaml"
        )
        self.comment_parser = YamlCommentParser(ui_params_path)

        # 创建独立窗口
        self.window = tk.Toplevel(parent)
        self.window.minsize(600, 400)  # 设置最小尺寸

        # 窗口关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # 创建组件
        self._create_widgets()

        # 默认加载 ui_params.yaml
        self._load_file_internal(ui_params_path)

        # 初始化完成后调整窗口大小以适应内容
        self.window.after(100, self._adjust_window_size)

        # 注册文件切换前钩子（监听主界面 Combobox 的文件切换）
        self.loader.add_before_switch_hook(self._on_before_file_switch)
        # 注册状态变化监听器（主界面切换后同步加载）
        self.loader.add_listener(self._on_loader_state_changed)

    def _build_json_param_map(self) -> Dict[str, Any]:
        """
        构建 UI 参数名到 JSON 参数值的映射

        处理两种情况:
        1. 直接映射: breakthrough_detector.total_window -> detector_params.total_window
        2. 权重映射: quality_scorer.peak_weights.volume -> quality_scorer_params.peak_weight_volume

        Returns:
            参数名到 JSON 值的映射字典
        """
        if not self._json_params:
            return {}

        param_map = {}

        # detector_params 映射
        detector = self._json_params.get("detector_params", {})
        param_map["breakthrough_detector.total_window"] = detector.get("total_window")
        param_map["breakthrough_detector.min_side_bars"] = detector.get("min_side_bars")
        param_map["breakthrough_detector.min_relative_height"] = detector.get("min_relative_height")
        param_map["breakthrough_detector.exceed_threshold"] = detector.get("exceed_threshold")
        param_map["breakthrough_detector.peak_supersede_threshold"] = detector.get("peak_supersede_threshold")
        # use_cache 和 cache_dir 不保存到 JSON（运行时配置）

        # feature_calculator_params 映射
        feature = self._json_params.get("feature_calculator_params", {})
        param_map["feature_calculator.stability_lookforward"] = feature.get("stability_lookforward")
        param_map["feature_calculator.continuity_lookback"] = feature.get("continuity_lookback")
        # label_configs 是列表，特殊处理（不在 UI 参数编辑器中显示）

        # quality_scorer_params 映射 (处理权重组的扁平化)
        scorer = self._json_params.get("quality_scorer_params", {})

        # peak_weights (JSON: peak_weight_* -> UI: peak_weights.*)
        param_map["quality_scorer.peak_weights.volume"] = scorer.get("peak_weight_volume")
        param_map["quality_scorer.peak_weights.candle"] = scorer.get("peak_weight_candle")
        param_map["quality_scorer.peak_weights.height"] = scorer.get("peak_weight_height")

        # breakthrough_weights (JSON: bt_weight_* -> UI: breakthrough_weights.*)
        param_map["quality_scorer.breakthrough_weights.change"] = scorer.get("bt_weight_change")
        param_map["quality_scorer.breakthrough_weights.gap"] = scorer.get("bt_weight_gap")
        param_map["quality_scorer.breakthrough_weights.volume"] = scorer.get("bt_weight_volume")
        param_map["quality_scorer.breakthrough_weights.continuity"] = scorer.get("bt_weight_continuity")
        param_map["quality_scorer.breakthrough_weights.stability"] = scorer.get("bt_weight_stability")
        param_map["quality_scorer.breakthrough_weights.resistance"] = scorer.get("bt_weight_resistance")
        param_map["quality_scorer.breakthrough_weights.historical"] = scorer.get("bt_weight_historical")

        # resistance_weights (JSON: res_weight_* -> UI: resistance_weights.*)
        param_map["quality_scorer.resistance_weights.quantity"] = scorer.get("res_weight_quantity")
        param_map["quality_scorer.resistance_weights.density"] = scorer.get("res_weight_density")
        param_map["quality_scorer.resistance_weights.quality"] = scorer.get("res_weight_quality")

        # historical_weights (JSON: hist_weight_* -> UI: historical_weights.*)
        param_map["quality_scorer.historical_weights.oldest_age"] = scorer.get("hist_weight_oldest_age")
        param_map["quality_scorer.historical_weights.suppression_span"] = scorer.get("hist_weight_suppression")

        # 标量参数 (直接映射)
        param_map["quality_scorer.time_decay_baseline"] = scorer.get("time_decay_baseline")
        param_map["quality_scorer.time_decay_half_life"] = scorer.get("time_decay_half_life")
        param_map["quality_scorer.historical_significance_saturation"] = scorer.get("historical_significance_saturation")
        param_map["quality_scorer.historical_quality_threshold"] = scorer.get("historical_quality_threshold")

        return param_map

    def _get_json_value(self, section_key: str, param_name: str) -> Optional[Any]:
        """
        获取指定参数的 JSON 值

        Args:
            section_key: 分组键（如 'breakthrough_detector'）
            param_name: 参数名（如 'total_window' 或 'peak_weights.volume'）

        Returns:
            JSON 参数值，如果不存在则返回 None
        """
        full_key = f"{section_key}.{param_name}"
        return self._json_param_map.get(full_key)

    def _create_widgets(self):
        """创建窗口组件"""
        # 全局样式已在主入口配置，这里不需要重复配置

        # 1. 顶部工具栏
        self._create_toolbar()

        # 2. 中间滚动区域
        self._create_scroll_area()

        # 3. 底部状态栏
        self._create_status_bar()

        # 4. 键盘快捷键
        self.window.bind("<Escape>", lambda e: self._on_close())
        # self.window.bind("<Return>", lambda e: self.apply_params())  # Enter可能会干扰输入

    def _create_toolbar(self):
        """创建顶部工具栏"""
        toolbar = ttk.Frame(self.window, padding=5)
        toolbar.pack(side="top", fill="x")

        # 左侧按钮
        ttk.Button(toolbar, text="Load", command=self.load_from_file, width=10).pack(
            side="left", padx=2
        )

        # Save 按钮（保存引用，用于启用/禁用）
        self.save_button = ttk.Button(
            toolbar, text="Save", command=self.save_to_file, width=10
        )
        self.save_button.pack(side="left", padx=2)

        # Save As 按钮
        ttk.Button(toolbar, text="Save As", command=self.save_as, width=10).pack(
            side="left", padx=2
        )

        # Discard Changes 按钮（保存引用，用于启用/禁用）
        self.discard_button = ttk.Button(
            toolbar, text="Discard", command=self.discard_changes, width=10
        )
        self.discard_button.pack(side="left", padx=2)

        # 分隔符
        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=10, pady=2
        )

        # JSON 对比按钮
        self.json_toggle_btn = ttk.Button(
            toolbar,
            text="Show JSON",
            command=self._toggle_json_column,
            width=12,
        )
        self.json_toggle_btn.pack(side="left", padx=2)

        # 如果没有 JSON 数据，禁用按钮
        if not self._json_params:
            self.json_toggle_btn.config(state="disabled")

        # 分隔符
        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=10, pady=2
        )

        # 右侧按钮
        ttk.Button(toolbar, text="Cancel", command=self._on_close, width=10).pack(
            side="right", padx=2
        )
        ttk.Button(toolbar, text="Apply", command=self.apply_params, width=10).pack(
            side="right", padx=2
        )

    def _create_scroll_area(self):
        """创建中间可滚动区域"""
        scroll_frame = ttk.Frame(self.window)
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # 创建滚动容器（传入回调用于调整窗口大小）
        self.accordion = ScrollableAccordion(
            scroll_frame,
            on_section_toggle_callback=self._adjust_window_size
        )
        self.accordion.pack()

        # 创建5个折叠分组
        for section_key in self.param_configs.keys():
            title = SECTION_TITLES.get(section_key, section_key)
            param_count = get_param_count(section_key)
            section = self.accordion.add_section(section_key, title, param_count)
            self.section_map[section_key] = section

        # 默认展开第一个分组
        if self.accordion.sections:
            self.accordion.sections[0].toggle()

    def _create_status_bar(self):
        """创建底部状态栏"""
        self.status_bar = ttk.Label(
            self.window,
            text="Status: Ready",
            relief="sunken",
            anchor="w",
            padding=5,
            font=FONT_STATUS,
        )
        self.status_bar.pack(side="bottom", fill="x")

    def _toggle_json_column(self):
        """切换 JSON 列的显示/隐藏"""
        self._json_column_visible = not self._json_column_visible

        # 更新按钮文字
        btn_text = "Hide JSON" if self._json_column_visible else "Show JSON"
        self.json_toggle_btn.config(text=btn_text)

        # 遍历所有分组的所有参数输入组件
        for section in self.section_map.values():
            for param_input in section.param_inputs:
                param_input.show_json_column(self._json_column_visible)

        # 调整窗口大小
        self._adjust_window_size()

    def update_json_params(self, json_params: Dict):
        """
        更新 JSON 参数并刷新显示

        当主窗口加载新的 JSON 文件时调用

        Args:
            json_params: 新的 JSON 参数（来自 scan_metadata）
        """
        self._json_params = json_params
        self._json_param_map = self._build_json_param_map()

        # 更新 JSON 按钮状态
        if self._json_params:
            self.json_toggle_btn.config(state="normal")
        else:
            self.json_toggle_btn.config(state="disabled")
            self._json_column_visible = False
            self.json_toggle_btn.config(text="Show JSON")

        # 更新所有参数输入组件的 JSON 值
        for section_key, section in self.section_map.items():
            for param_input in section.param_inputs:
                json_val = self._get_json_value(section_key, param_input.param_name)
                param_input.set_json_value(json_val)

    def _adjust_window_size(self):
        """
        调整窗口大小以适应内容

        在展开/折叠分组时调用，自动调整窗口高度
        """
        # 更新所有组件的布局
        self.window.update_idletasks()

        # 获取内容所需的高度
        content_height = self.accordion.scrollable_frame.winfo_reqheight()

        # 获取工具栏和状态栏的高度
        toolbar_height = 50  # 工具栏大约高度
        status_height = 30   # 状态栏大约高度
        padding = 30         # 额外边距

        # 计算理想高度
        ideal_height = content_height + toolbar_height + status_height + padding

        # 获取屏幕尺寸，限制最大高度
        screen_height = self.window.winfo_screenheight()
        max_height = int(screen_height * 0.85)  # 最大为屏幕高度的85%
        min_height = 400

        # 应用高度限制
        new_height = max(min_height, min(ideal_height, max_height))

        # 保持当前宽度，调整高度
        current_width = self.window.winfo_width()
        if current_width < 600:
            current_width = 900  # 初始默认宽度

        self.window.geometry(f"{current_width}x{new_height}")

    def _load_file_internal(self, file_path: Path):
        """
        内部文件加载方法（由构造函数和 load_from_file 调用）

        Args:
            file_path: 文件路径
        """
        try:
            # 使用状态管理器加载文件
            params = self.state_manager.load_file(file_path)

            # 填充到各个分组
            for section_key, section in self.section_map.items():
                section_data = params.get(section_key, {})
                self._populate_section_data(section, section_key, section_data)

            # 更新权重组总和显示
            for weight_group in get_weight_group_names():
                self._update_weight_sum(weight_group)

            # 【新增】同步到 UIParamLoader（统一状态管理）
            # 这样主界面的下拉菜单会自动更新
            self.loader.set_active_file(file_path, params)

            # 更新窗口状态
            self._update_window_title()
            self._update_button_states()
            self._set_status(f"Loaded: {file_path.name}", "green")

        except Exception as e:
            messagebox.showerror(
                "Load Error", f"Failed to load parameters: {e}"
            )
            self._set_status(f"Load failed: {str(e)}", "red")

    def _populate_section_data(self, section: AccordionSection, section_key: str, section_data: dict):
        """
        填充分组的参数输入组件（使用指定的数据）

        Args:
            section: AccordionSection实例
            section_key: 分组键
            section_data: 分组参数数据
        """
        section_config = self.param_configs[section_key]

        # 清空现有参数输入（如果有）
        for param_input in section.param_inputs[:]:
            param_input.frame.destroy()
        section.param_inputs.clear()

        # 清空 content_frame 中残留的 LabelFrame（字典类型参数的容器）
        for child in section.content_frame.winfo_children():
            child.destroy()

        # 重新添加参数输入
        for param_name, param_config in section_config.items():
            param_type = param_config.get("type")
            param_value = section_data.get(param_name)

            if param_type == dict and "sub_params" in param_config:
                # 有子参数的字典（如权重组）
                self._add_dict_params(
                    section, param_name, param_config, param_value or {}
                )
            else:
                # 普通参数
                self._add_simple_param(section, param_name, param_config, param_value)

    def _add_simple_param(
        self,
        section: AccordionSection,
        param_name: str,
        param_config: dict,
        param_value: Any,
    ):
        """添加简单参数输入组件"""
        # 获取参数的中文注释
        param_path = f"{section.section_key}.{param_name}"
        tooltip_text = self.comment_parser.get_comment(param_path)

        # 获取对应的 JSON 值
        json_value = self._get_json_value(section.section_key, param_name)

        param_input = ParameterInputFactory.create(
            section.content_frame,
            param_name,
            param_value,
            param_config,
            on_change_callback=self._on_param_value_changed,  # 参数值改变回调
            tooltip_text=tooltip_text,
            json_value=json_value,  # JSON 参数值
        )
        section.add_parameter(param_input)

    def _add_dict_params(
        self,
        section: AccordionSection,
        parent_name: str,
        parent_config: dict,
        parent_value: dict,
    ):
        """添加字典类型参数（包含子参数）"""
        # 添加分组标签（如果是权重组，显示实时总和）
        is_weight_group = parent_config.get("is_weight_group", False)

        # 提取约束信息（从description的括号中提取）
        description = parent_config.get("description", "")
        constraint_info = ""
        if "(" in description and ")" in description:
            # 提取括号内的内容作为约束信息
            start_idx = description.find("(")
            end_idx = description.find(")")
            constraint_info = " " + description[start_idx : end_idx + 1]

        # 创建子参数Frame - 只显示组名和约束信息
        sub_frame = ttk.LabelFrame(
            section.content_frame,
            text=f"{parent_name}{constraint_info}",
            padding=10,
        )
        sub_frame.pack(fill="x", pady=5)

        # 添加子参数
        sub_inputs = []
        for sub_name, sub_config in parent_config["sub_params"].items():
            sub_value = parent_value.get(sub_name)
            # 使用 parent_name.sub_name 作为完整参数名
            full_name = f"{parent_name}.{sub_name}"

            # 获取参数的中文注释
            param_path = f"{section.section_key}.{full_name}"
            tooltip_text = self.comment_parser.get_comment(param_path)

            # 获取对应的 JSON 值
            json_value = self._get_json_value(section.section_key, full_name)

            # 组合回调：脏状态标记 + 权重组总和更新（如果是权重组）
            def create_callback(parent=parent_name, is_weight=is_weight_group):
                def callback():
                    self._on_param_value_changed()
                    if is_weight:
                        self._update_weight_sum(parent)
                return callback

            sub_input = ParameterInputFactory.create(
                sub_frame,
                full_name,
                sub_value,
                sub_config,
                on_change_callback=create_callback(),
                tooltip_text=tooltip_text,
                json_value=json_value,  # JSON 参数值
            )
            section.add_parameter(sub_input)
            sub_inputs.append(sub_input)

        # 如果是权重组，添加总和显示
        if is_weight_group:
            sum_frame = ttk.Frame(sub_frame)
            sum_frame.pack(fill="x", pady=5)

            sum_label = ttk.Label(
                sum_frame,
                text="Current Sum:",
                font=FONT_WEIGHT_SUM,
            )
            sum_label.pack(side="left", padx=5)

            sum_value_label = ttk.Label(sum_frame, text="0.00", font=FONT_WEIGHT_SUM)
            sum_value_label.pack(side="left", padx=5)

            # 存储标签引用，用于更新
            setattr(self, f"{parent_name}_sum_label", sum_value_label)

            # 初始计算总和
            self._update_weight_sum(parent_name)

    def _update_weight_sum(self, weight_group_name: str):
        """更新权重组的总和显示"""
        try:
            # 获取该权重组的所有输入组件
            weights = {}
            for section in self.section_map.values():
                for param_input in section.param_inputs:
                    if param_input.param_name.startswith(weight_group_name + "."):
                        sub_name = param_input.param_name.split(".")[1]
                        weights[sub_name] = param_input.get_value()

            # 计算总和
            total = WeightGroupValidator.calculate_sum(weights)

            # 更新显示
            sum_label = getattr(self, f"{weight_group_name}_sum_label", None)
            if sum_label:
                color = "green" if abs(total - 1.0) <= 0.001 else "red"
                symbol = "✓" if color == "green" else "✗"
                sum_label.config(text=f"{total:.4f} {symbol}", foreground=color)

        except Exception as e:
            print(f"Error updating weight sum: {e}")

    def load_from_file(self, file_path: str = None):
        """
        从yaml文件加载参数到编辑器（Load 按钮）

        如果当前有未保存修改，会弹窗提示用户
        """
        # 检查未保存修改
        if self.state_manager.is_dirty:
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before loading?"
            )
            if result is None:  # Cancel
                return
            elif result is True:  # Yes (Save)
                self.save_to_file()

        # 选择文件
        if not file_path:
            default_dir = (
                self.loader.get_project_root() / "configs" / "analysis" / "params"
            )
            file_path = filedialog.askopenfilename(
                title="Load Parameters",
                initialdir=str(default_dir),
                filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
            )
            if not file_path:
                return

        # 加载文件
        self._load_file_internal(Path(file_path))

    def save_to_file(self):
        """
        保存到当前关联文件（Save 按钮）

        保存文件后自动应用参数（更新内存 + 刷新图表）
        """
        if not self.state_manager.current_file_path:
            self.save_as()  # 如果没有关联文件，转为另存为
            return

        # 验证所有参数
        errors = self.validate_all()
        if errors:
            messagebox.showerror(
                "Validation Error",
                "Please fix the following errors:\n\n" + "\n".join(errors[:10]),
            )
            return

        try:
            # 收集所有参数值
            params_dict = self._collect_editor_params()

            # 使用状态管理器保存
            self.state_manager.editor_params = params_dict
            self.state_manager.save_file()

            # 保存后自动应用参数
            # 使用 set_active_file 同步状态（已保存，非仅内存）
            self.loader.set_active_file(
                self.state_manager.current_file_path, params_dict
            )

            # 回调主界面，自动勾选 "Use UI Params" 并刷新图表
            if self.on_apply_callback:
                self.on_apply_callback()

            # 更新窗口状态
            self._update_window_title()
            self._update_button_states()
            self._set_status(
                f"Saved and applied: {self.state_manager.current_file_path.name}",
                "green"
            )

        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save parameters: {e}")
            self._set_status(f"Save failed: {str(e)}", "red")

    def save_as(self):
        """
        另存为新文件并切换关联（Save As 按钮）

        保存文件后自动应用参数（更新内存 + 刷新图表）
        """
        # 验证所有参数
        errors = self.validate_all()
        if errors:
            messagebox.showerror(
                "Validation Error",
                "Please fix the following errors:\n\n" + "\n".join(errors[:10]),
            )
            return

        # 选择保存路径
        default_dir = (
            self.loader.get_project_root() / "configs" / "analysis" / "params"
        )
        file_path = filedialog.asksaveasfilename(
            title="Save Parameters As",
            initialdir=str(default_dir),
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
        )
        if not file_path:
            return

        try:
            # 收集所有参数值
            params_dict = self._collect_editor_params()

            # 使用状态管理器保存并切换关联
            self.state_manager.editor_params = params_dict
            self.state_manager.save_file(Path(file_path))

            # 保存后自动应用参数
            # 使用 set_active_file 同步状态（已保存，非仅内存）
            self.loader.set_active_file(
                self.state_manager.current_file_path, params_dict
            )

            # 回调主界面，自动勾选 "Use UI Params" 并刷新图表
            if self.on_apply_callback:
                self.on_apply_callback()

            # 更新窗口状态
            self._update_window_title()
            self._update_button_states()
            self._set_status(
                f"Saved and applied as: {self.state_manager.current_file_path.name}",
                "green"
            )

        except Exception as e:
            messagebox.showerror("Save As Error", f"Failed to save parameters: {e}")
            self._set_status(f"Save as failed: {str(e)}", "red")

    def discard_changes(self):
        """
        丢弃修改，恢复到最后一次保存的状态（Discard Changes 按钮）
        """
        if not messagebox.askyesno(
            "Discard Changes",
            "Discard all changes and revert to last saved state?"
        ):
            return

        try:
            # 从快照恢复
            reset_params = self.state_manager.reset_to_snapshot()

            # 重新填充所有分组
            for section_key, section in self.section_map.items():
                section_data = reset_params.get(section_key, {})
                self._populate_section_data(section, section_key, section_data)

            # 更新权重组总和显示
            for weight_group in get_weight_group_names():
                self._update_weight_sum(weight_group)

            # 更新窗口状态
            self._update_window_title()
            self._update_button_states()
            self._set_status("Reverted to last saved state", "green")

        except Exception as e:
            messagebox.showerror("Discard Error", f"Failed to discard changes: {e}")
            self._set_status(f"Discard failed: {str(e)}", "red")

    def apply_params(self):
        """
        应用到内存（不保存文件）

        将编辑器参数提交到 UIParamLoader 的内存中，
        自动勾选主界面的 "Use UI Params" 并触发图表刷新
        """
        # 验证所有参数
        errors = self.validate_all()
        if errors:
            messagebox.showerror(
                "Validation Error",
                "Please fix the following errors:\n\n" + "\n".join(errors[:10]),
            )
            return

        try:
            # 收集编辑器参数
            params_dict = self._collect_editor_params()

            # 更新状态管理器
            self.state_manager.editor_params = params_dict

            # 更新 UIParamLoader 的内存参数（不保存文件）
            # 传递 source_file 以同步主界面下拉菜单显示
            source_file = self.state_manager.current_file_path
            self.loader.update_memory_params(params_dict, source_file)

            # 标记已 Apply（用于关闭窗口检查）
            self.state_manager.mark_applied()

            # 回调主界面
            # 主界面会自动勾选 "Use UI Params" 并刷新图表
            if self.on_apply_callback:
                self.on_apply_callback()

            self._set_status("Applied to memory and chart refreshed (file not saved)", "blue")

        except Exception as e:
            messagebox.showerror("Apply Error", f"Failed to apply parameters: {e}")
            self._set_status(f"Apply failed: {str(e)}", "red")

    def validate_all(self) -> list:
        """验证所有参数，返回错误列表"""
        all_errors = []

        # 验证每个分组
        for section in self.section_map.values():
            errors = section.validate_all()
            all_errors.extend(errors)

        # 特殊验证：权重组总和
        for weight_group in get_weight_group_names():
            # 收集该组所有权重参数
            weights = {}
            for section in self.section_map.values():
                for param_input in section.param_inputs:
                    if param_input.param_name.startswith(weight_group + "."):
                        sub_name = param_input.param_name.split(".")[1]
                        weights[sub_name] = param_input.get_value()

            # 验证总和
            is_valid, sum_value, error_msg = WeightGroupValidator.validate_sum(weights)
            if not is_valid:
                all_errors.append(f"{weight_group}: {error_msg}")

        return all_errors

    def _set_status(self, text: str, color: str = "black"):
        """设置状态栏文本"""
        self.status_bar.config(text=f"Status: {text}", foreground=color)

    def _collect_editor_params(self) -> Dict[str, Any]:
        """
        收集编辑器所有参数值

        Returns:
            完整的参数字典
        """
        params_dict = {}
        for section_key, section in self.section_map.items():
            params_dict[section_key] = section.get_all_values()
        return params_dict

    def _on_param_value_changed(self):
        """
        参数值改变时的回调（由输入组件触发）
        """
        self.state_manager.mark_dirty()
        self._update_window_title()
        self._update_button_states()

    def _update_window_title(self):
        """更新窗口标题"""
        if self.state_manager.current_file_path:
            filename = self.state_manager.current_file_path.name
            dirty_mark = " *" if self.state_manager.is_dirty else ""
            self.window.title(f"Parameter Editor - [{filename}]{dirty_mark}")
        else:
            self.window.title("Parameter Editor - [Untitled] *")

    def _update_button_states(self):
        """更新按钮启用状态"""
        is_dirty = self.state_manager.is_dirty

        # Save 和 Discard Changes 仅在有修改时启用
        if is_dirty:
            self.save_button.config(state="normal")
            self.discard_button.config(state="normal")
        else:
            self.save_button.config(state="disabled")
            self.discard_button.config(state="disabled")

    def _on_close(self):
        """
        窗口关闭前检查未保存修改
        """
        # 如果 Apply 过但未 Save，询问是否保存
        if self.state_manager.needs_save_prompt():
            result = messagebox.askyesnocancel(
                "Unsaved Applied Changes",
                "You have applied changes that are not saved to file.\n"
                "Save before closing?"
            )
            if result is None:  # Cancel
                return
            elif result is True:  # Yes (Save)
                self.save_to_file()
        elif self.state_manager.is_dirty:
            # 常规未保存修改检查
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Save before closing?"
            )
            if result is None:  # Cancel
                return
            elif result is True:  # Yes (Save)
                self.save_to_file()

        # 清理钩子和监听器
        self.loader.remove_before_switch_hook(self._on_before_file_switch)
        self.loader.remove_listener(self._on_loader_state_changed)

        self.window.destroy()

    # ==================== 主界面 Combobox 联动 ====================

    def _on_before_file_switch(self, new_file: Path) -> bool:
        """
        文件切换前钩子（由主界面 Combobox 触发）

        检查编辑器是否有未保存的更改，提示用户保存或丢弃

        Args:
            new_file: 即将切换到的新文件路径

        Returns:
            True: 允许切换
            False: 阻止切换（用户取消）
        """
        # 如果编辑器窗口已关闭，直接允许
        if not self.window.winfo_exists():
            return True

        # 如果没有未保存的更改，直接允许
        if not self.state_manager.is_dirty:
            return True

        # 有未保存的更改，提示用户
        current_file = self.state_manager.current_file_path
        current_name = current_file.name if current_file else "Untitled"

        result = messagebox.askyesnocancel(
            "Unsaved Changes",
            f"You have unsaved changes in '{current_name}'.\n\n"
            f"Save before switching to '{new_file.name}'?"
        )

        if result is None:  # Cancel - 阻止切换
            return False
        elif result is True:  # Yes - 保存后允许切换
            self.save_to_file()
            return True
        else:  # No - 丢弃更改，允许切换
            # 重置 dirty 状态（因为用户选择了丢弃）
            self.state_manager._is_dirty = False
            return True

    def _on_loader_state_changed(self):
        """
        响应 UIParamLoader 状态变化（文件切换后）

        当主界面 Combobox 成功切换文件后，同步加载到编辑器
        """
        # 如果编辑器窗口已关闭，跳过
        if not self.window.winfo_exists():
            return

        # 获取当前活跃文件
        active_file = self.loader.get_active_file()
        if not active_file:
            return

        # 如果是同一个文件，跳过
        if (self.state_manager.current_file_path and
            self.state_manager.current_file_path == active_file):
            return

        # 加载新文件到编辑器（不触发钩子，因为已经通过了检查）
        self._load_file_internal(active_file)
