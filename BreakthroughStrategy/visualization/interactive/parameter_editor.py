"""参数编辑器窗口

提供图形化的参数编辑界面，支持加载、编辑、保存和应用参数
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, Optional

import yaml

from .parameter_configs import (
    PARAM_CONFIGS,
    SECTION_TITLES,
    get_param_count,
    get_weight_group_names,
)
from .parameter_input_factory import BaseParameterInput, ParameterInputFactory
from .parameter_validator import WeightGroupValidator
from .ui_param_loader import UIParamLoader
from .ui_styles import FONT_SECTION_TITLE, FONT_STATUS, FONT_WEIGHT_SUM
from .yaml_comment_parser import YamlCommentParser


class AccordionSection:
    """单个折叠分组组件"""

    def __init__(self, parent, section_key: str, title: str, param_count: int):
        """
        初始化折叠分组

        Args:
            parent: 父容器
            section_key: 分组键（如'breakthrough_detector'）
            title: 显示标题
            param_count: 参数数量
        """
        self.parent = parent
        self.section_key = section_key
        self.title = title
        self.param_count = param_count
        self.expanded = False
        self.param_inputs = []  # 存储该分组的所有输入组件

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

    def add_parameter(self, param_input: BaseParameterInput):
        """添加参数输入组件"""
        self.param_inputs.append(param_input)
        param_input.frame.pack(fill="x", pady=2)

    def get_all_values(self) -> Dict[str, Any]:
        """获取该分组所有参数值"""
        values = {}
        for param_input in self.param_inputs:
            # 处理嵌套参数（如candle_classification.big_body_threshold）
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

    def __init__(self, parent):
        """
        初始化可滚动容器

        Args:
            parent: 父容器
        """
        self.parent = parent
        self.sections = []

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
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")

    def add_section(
        self, section_key: str, title: str, param_count: int
    ) -> AccordionSection:
        """添加折叠分组"""
        section = AccordionSection(
            self.scrollable_frame, section_key, title, param_count
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
    ):
        """
        初始化参数编辑器窗口

        Args:
            parent: 主窗口
            ui_param_loader: UIParamLoader实例（复用验证逻辑）
            on_apply_callback: Apply时的回调函数（触发图表刷新）
        """
        self.parent = parent
        self.loader = ui_param_loader
        self.on_apply_callback = on_apply_callback
        self.current_params = None  # 当前编辑的参数
        self.param_configs = PARAM_CONFIGS
        self.section_map = {}  # section_key -> AccordionSection 的映射

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
        self.window.title("Parameter Editor")
        self.window.geometry("900x700")

        # 窗口关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # 创建组件
        self._create_widgets()

        # 加载当前参数
        self._load_current_params()

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
        ttk.Button(toolbar, text="Save", command=self.save_to_file, width=10).pack(
            side="left", padx=2
        )
        ttk.Button(
            toolbar, text="Reset to Default", command=self.reset_to_default, width=15
        ).pack(side="left", padx=2)

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

        # 创建滚动容器
        self.accordion = ScrollableAccordion(scroll_frame)
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

    def _load_current_params(self):
        """加载当前ui_params.yaml的参数到编辑器"""
        try:
            # 从UIParamLoader获取所有参数
            self.current_params = self.loader.get_all_params()

            # 填充到各个分组
            for section_key, section in self.section_map.items():
                self._populate_section(section, section_key)

        except Exception as e:
            messagebox.showerror(
                "Load Error", f"Failed to load current parameters: {e}"
            )
            self._set_status(f"Load failed: {str(e)}", "red")

    def _populate_section(self, section: AccordionSection, section_key: str):
        """
        填充分组的参数输入组件

        Args:
            section: AccordionSection实例
            section_key: 分组键
        """
        section_config = self.param_configs[section_key]
        section_data = self.current_params.get(section_key, {})

        for param_name, param_config in section_config.items():
            param_type = param_config.get("type")
            param_value = section_data.get(param_name)

            if param_type == dict and "sub_params" in param_config:
                # 有子参数的字典（如candle_classification或权重组）
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

        param_input = ParameterInputFactory.create(
            section.content_frame,
            param_name,
            param_value,
            param_config,
            on_change_callback=None,  # 可以添加实时验证回调
            tooltip_text=tooltip_text,
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

            sub_input = ParameterInputFactory.create(
                sub_frame,
                full_name,
                sub_value,
                sub_config,
                on_change_callback=lambda: self._update_weight_sum(parent_name)
                if is_weight_group
                else None,
                tooltip_text=tooltip_text,
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
        """从yaml文件加载参数到编辑器"""
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

        try:
            # 加载yaml文件
            with open(file_path, "r", encoding="utf-8") as f:
                self.current_params = yaml.safe_load(f)

            # 更新所有输入组件的值
            for section_key, section in self.section_map.items():
                section_data = self.current_params.get(section_key, {})
                for param_input in section.param_inputs:
                    # 处理嵌套参数
                    if "." in param_input.param_name:
                        parts = param_input.param_name.split(".")
                        parent_key = parts[0]
                        child_key = parts[1]
                        parent_data = section_data.get(parent_key, {})
                        param_value = parent_data.get(child_key)
                    else:
                        param_value = section_data.get(param_input.param_name)

                    if param_value is not None:
                        param_input.set_value(param_value)

            # 更新权重组总和显示
            for weight_group in get_weight_group_names():
                self._update_weight_sum(weight_group)

            self._set_status(f"Loaded: {Path(file_path).name}", "green")

        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load parameters: {e}")
            self._set_status(f"Load failed: {str(e)}", "red")

    def save_to_file(self, file_path: str = None):
        """保存参数到yaml文件"""
        # 先验证所有参数
        errors = self.validate_all()
        if errors:
            messagebox.showerror(
                "Validation Error",
                "Please fix the following errors:\n\n" + "\n".join(errors[:10]),
            )
            return

        if not file_path:
            default_dir = (
                self.loader.get_project_root() / "configs" / "analysis" / "params"
            )
            file_path = filedialog.asksaveasfilename(
                title="Save Parameters",
                initialdir=str(default_dir),
                defaultextension=".yaml",
                filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
            )
            if not file_path:
                return

        try:
            # 收集所有参数值
            params_dict = {}
            for section_key, section in self.section_map.items():
                params_dict[section_key] = section.get_all_values()

            # 保存到文件
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(params_dict, f, default_flow_style=False, allow_unicode=True)

            self._set_status(f"Saved: {Path(file_path).name}", "green")

        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save parameters: {e}")
            self._set_status(f"Save failed: {str(e)}", "red")

    def reset_to_default(self):
        """重置为默认参数（从breakthrough_0.yaml加载）"""
        default_path = (
            self.loader.get_project_root()
            / "configs"
            / "analysis"
            / "params"
            / "breakthrough_0.yaml"
        )

        if not default_path.exists():
            messagebox.showerror(
                "Error", f"Default parameter file not found: {default_path}"
            )
            return

        if messagebox.askyesno(
            "Reset to Default",
            "Reset all parameters to default values?\nThis will discard current changes.",
        ):
            self.load_from_file(str(default_path))

    def apply_params(self):
        """应用参数并触发图表刷新"""
        # 1. 验证所有参数
        errors = self.validate_all()
        if errors:
            messagebox.showerror(
                "Validation Error",
                "Please fix the following errors:\n\n" + "\n".join(errors[:10]),
            )
            return

        try:
            # 2. 保存到 ui_params.yaml
            ui_params_path = (
                self.loader.get_project_root()
                / "configs"
                / "analysis"
                / "params"
                / "ui_params.yaml"
            )
            self.save_to_file(str(ui_params_path))

            # 3. 通知主窗口重新加载参数并刷新图表
            if self.on_apply_callback:
                self.on_apply_callback()

            self._set_status("Parameters applied successfully", "green")

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

    def _on_close(self):
        """窗口关闭事件"""
        # 可以添加"是否保存未保存的修改"的确认对话框（可选）
        self.window.destroy()
