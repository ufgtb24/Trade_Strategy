"""参数输入组件工厂

为不同类型的参数创建相应的输入组件
"""

import tkinter as tk
from tkinter import ttk
from typing import Any, Tuple, Callable, Optional

from ..config import InputValidator
from ..styles import FONT_PARAM_LABEL, FONT_PARAM_INPUT, FONT_PARAM_HINT, JSON_DIFF_BG, JSON_MATCH_BG, JSON_NA_FG


class SelectableLabel(ttk.Entry):
    """可选择复制的 Label 组件

    使用只读 Entry 实现，外观接近 Label 但支持文本选择和复制
    """

    def __init__(self, parent, text: str = "", width: int = 25, font=None, **kwargs):
        """
        初始化可选择的 Label

        Args:
            parent: 父容器
            text: 显示文本
            width: 宽度（字符数）
            font: 字体
            **kwargs: 其他参数
        """
        self._var = tk.StringVar(value=text)
        super().__init__(
            parent,
            textvariable=self._var,
            width=width,
            font=font,
            state="readonly",
            style="SelectableLabel.TEntry",
            **kwargs
        )
        # 配置只读样式，使其看起来更像 Label
        self.configure(cursor="arrow")

    def config(self, **kwargs):
        """兼容 Label 的 config 方法"""
        if "text" in kwargs:
            self._var.set(kwargs.pop("text"))
        super().configure(**kwargs)

    def configure(self, **kwargs):
        """兼容 Label 的 configure 方法"""
        if "text" in kwargs:
            self._var.set(kwargs.pop("text"))
        super().configure(**kwargs)


class ToolTip:
    """悬浮提示工具类"""

    def __init__(self, widget, text: str):
        """
        初始化 tooltip

        Args:
            widget: 要绑定 tooltip 的组件
            text: 提示文本
        """
        self.widget = widget
        self.text = text
        self.tipwindow = None

        # 绑定鼠标事件
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        """显示提示"""
        if not self.text or self.tipwindow:
            return

        # 获取组件位置
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        # 创建提示窗口
        self.tipwindow = tk.Toplevel(self.widget)
        self.tipwindow.wm_overrideredirect(True)
        self.tipwindow.wm_geometry(f"+{x}+{y}")

        # 创建标签显示提示文本
        label = tk.Label(
            self.tipwindow,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Arial", 12),
            wraplength=300,
        )
        label.pack()

    def hide_tip(self, event=None):
        """隐藏提示"""
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


class BaseParameterInput:
    """参数输入组件基类"""

    def __init__(
        self,
        parent: ttk.Frame,
        param_name: str,
        param_value: Any,
        param_config: dict,
        on_change_callback: Optional[Callable] = None,
        tooltip_text: Optional[str] = None,
        json_value: Optional[Any] = None,
    ):
        """
        初始化参数输入组件

        Args:
            parent: 父容器
            param_name: 参数名称
            param_value: 参数初始值
            param_config: 参数配置，包含type, range, description等
            on_change_callback: 值变化时的回调函数
            tooltip_text: 鼠标悬浮提示文本（中文注释）
            json_value: JSON 文件中对应的参数值（只读显示）
        """
        self.parent = parent
        self.param_name = param_name
        self.param_value = param_value
        self.param_config = param_config
        self.on_change_callback = on_change_callback
        self.tooltip_text = tooltip_text
        self.json_value = json_value

        # 主容器
        self.frame = ttk.Frame(parent)

        # 组件引用
        self.label = None
        self.input_widget = None
        self.json_label = None  # JSON 值显示标签
        self._json_visible = False  # JSON 列可见性

        # 创建组件
        self._create_widgets()

        # tooltip 在子类中处理（合并范围提示）

    def _get_display_name(self) -> str:
        """
        获取参数的显示名称（移除组名前缀）

        例如: peak_weights.volume -> volume
              resistance_weights.quantity -> quantity

        Returns:
            显示名称
        """
        if '.' in self.param_name:
            return self.param_name.split('.')[-1]
        return self.param_name

    def _create_widgets(self):
        """创建UI组件（子类实现）"""
        raise NotImplementedError

    def get_value(self) -> Any:
        """获取当前值（子类实现）"""
        raise NotImplementedError

    def set_value(self, value: Any):
        """设置值（子类实现）"""
        raise NotImplementedError

    def validate(self) -> Tuple[bool, str]:
        """验证当前值（子类实现）"""
        raise NotImplementedError

    def highlight_error(self, show: bool):
        """显示/隐藏错误高亮（使用输入框样式）"""
        if show:
            if hasattr(self.input_widget, "config"):
                try:
                    self.input_widget.config(style="Error.TEntry")
                except Exception:
                    pass  # 某些组件可能不支持style
        else:
            if hasattr(self.input_widget, "config"):
                try:
                    self.input_widget.config(style="TEntry")
                except Exception:
                    pass

    def show_json_column(self, visible: bool):
        """显示/隐藏 JSON 列"""
        self._json_visible = visible
        if self.json_label is None:
            return

        if visible:
            self.json_label.grid(row=0, column=2, padx=5, pady=2)
            self._update_json_highlight()
        else:
            self.json_label.grid_remove()

    def _update_json_highlight(self):
        """更新 JSON 值差异高亮"""
        if not self._json_visible or self.json_label is None:
            return

        if self.json_value is None:
            # JSON 中不存在该参数
            self.json_label.config(foreground=JSON_NA_FG, background=JSON_MATCH_BG)
            return

        current = self.get_value()
        is_different = not self._values_are_equal(current, self.json_value)

        if is_different:
            self.json_label.config(background=JSON_DIFF_BG, foreground="black")
        else:
            self.json_label.config(background=JSON_MATCH_BG, foreground="black")

    def _values_are_equal(self, ui_value: Any, json_value: Any) -> bool:
        """比较 UI 值和 JSON 值是否相等"""
        if json_value is None:
            return True  # JSON 无值时不标记差异

        # 类型转换比较
        if isinstance(ui_value, float) and isinstance(json_value, (int, float)):
            return abs(ui_value - float(json_value)) < 0.0001
        elif isinstance(ui_value, int) and isinstance(json_value, int):
            return ui_value == json_value
        elif isinstance(ui_value, bool) and isinstance(json_value, bool):
            return ui_value == json_value
        elif isinstance(ui_value, list) and isinstance(json_value, list):
            return ui_value == json_value
        else:
            return str(ui_value) == str(json_value)

    def set_json_value(self, value: Any):
        """更新 JSON 值并刷新显示"""
        self.json_value = value
        if self.json_label:
            display_text = str(value) if value is not None else "N/A"
            self.json_label.config(text=display_text)
            if value is None:
                self.json_label.config(foreground=JSON_NA_FG)
            self._update_json_highlight()


class IntInput(BaseParameterInput):
    """整数输入组件（使用Spinbox）"""

    def _create_widgets(self):
        """创建整数输入组件"""
        min_val, max_val = self.param_config.get("range", (0, 100))

        # Column 0: 标签
        display_name = self._get_display_name()
        self.label = SelectableLabel(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # 范围提示合并到 Tooltip
        range_hint = f"Range: {min_val} - {max_val}"
        combined_tooltip = f"{self.tooltip_text}\n{range_hint}" if self.tooltip_text else range_hint
        ToolTip(self.label, combined_tooltip)

        # Column 1: Spinbox
        self.spinbox_var = tk.IntVar(value=self.param_value or min_val)
        self.input_widget = ttk.Spinbox(
            self.frame,
            from_=min_val,
            to=max_val,
            textvariable=self.spinbox_var,
            width=15,
            command=self._on_value_changed,
            font=FONT_PARAM_INPUT,
        )
        self.input_widget.grid(row=0, column=1, padx=5, pady=2)

        # 绑定键盘输入事件
        self.input_widget.bind("<KeyRelease>", lambda e: self._on_value_changed())

        # Column 2: JSON 值标签（初始隐藏）
        json_display = str(self.json_value) if self.json_value is not None else "N/A"
        self.json_label = tk.Label(
            self.frame,
            text=json_display,
            width=15,
            font=FONT_PARAM_HINT,
            anchor="center",
            foreground=JSON_NA_FG if self.json_value is None else "black",
        )
        # 初始不 grid，由 show_json_column() 控制显示

    def _on_value_changed(self):
        """值变化时的回调"""
        self._update_json_highlight()  # 更新差异高亮
        if self.on_change_callback:
            self.on_change_callback()

    def get_value(self) -> int:
        """获取当前值"""
        try:
            return self.spinbox_var.get()
        except Exception:
            min_val, _ = self.param_config.get("range", (0, 100))
            return min_val

    def set_value(self, value: int):
        """设置值"""
        self.spinbox_var.set(int(value))

    def validate(self) -> Tuple[bool, str]:
        """验证当前值"""
        min_val, max_val = self.param_config.get("range", (0, 100))
        value_str = self.input_widget.get()
        is_valid, _, error_msg = InputValidator.validate_int(value_str, min_val, max_val)

        # 使用输入框样式标识错误
        self.highlight_error(not is_valid)

        return is_valid, error_msg


class FloatInput(BaseParameterInput):
    """浮点数输入组件（使用Entry + 验证）"""

    def _create_widgets(self):
        """创建浮点数输入组件"""
        min_val, max_val = self.param_config.get("range", (0.0, 1.0))

        # Column 0: 标签
        display_name = self._get_display_name()
        self.label = SelectableLabel(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # 范围提示合并到 Tooltip
        range_hint = f"Range: {min_val} - {max_val}"
        combined_tooltip = f"{self.tooltip_text}\n{range_hint}" if self.tooltip_text else range_hint
        ToolTip(self.label, combined_tooltip)

        # Column 1: Entry
        self.entry_var = tk.StringVar(value=str(self.param_value or min_val))
        self.input_widget = ttk.Entry(
            self.frame, textvariable=self.entry_var, width=15, font=FONT_PARAM_INPUT
        )
        self.input_widget.grid(row=0, column=1, padx=5, pady=2)

        # 绑定键盘输入事件
        self.input_widget.bind("<KeyRelease>", self._on_value_changed)

        # Column 2: JSON 值标签（初始隐藏）
        json_display = str(self.json_value) if self.json_value is not None else "N/A"
        self.json_label = tk.Label(
            self.frame,
            text=json_display,
            width=15,
            font=FONT_PARAM_HINT,
            anchor="center",
            foreground=JSON_NA_FG if self.json_value is None else "black",
        )
        # 初始不 grid，由 show_json_column() 控制显示

    def _on_value_changed(self, event=None):
        """值变化时的回调"""
        # 实时验证
        is_valid, _ = self.validate()
        self._update_json_highlight()  # 更新差异高亮
        if self.on_change_callback:
            self.on_change_callback()

    def get_value(self) -> float:
        """获取当前值"""
        try:
            return float(self.entry_var.get())
        except Exception:
            min_val, _ = self.param_config.get("range", (0.0, 1.0))
            return min_val

    def set_value(self, value: float):
        """设置值"""
        self.entry_var.set(str(value))

    def validate(self) -> Tuple[bool, str]:
        """验证当前值"""
        min_val, max_val = self.param_config.get("range", (0.0, 1.0))
        value_str = self.entry_var.get()
        is_valid, _, error_msg = InputValidator.validate_float(
            value_str, min_val, max_val
        )

        # 使用输入框样式标识错误
        self.highlight_error(not is_valid)

        return is_valid, error_msg


class BoolInput(BaseParameterInput):
    """布尔输入组件（使用Checkbutton）"""

    def _create_widgets(self):
        """创建布尔输入组件"""
        # Column 0: 标签
        display_name = self._get_display_name()
        self.label = SelectableLabel(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # Tooltip（如果有）
        if self.tooltip_text:
            ToolTip(self.label, self.tooltip_text)

        # Column 1: Checkbutton
        self.bool_var = tk.BooleanVar(value=bool(self.param_value))
        self.input_widget = ttk.Checkbutton(
            self.frame, variable=self.bool_var, command=self._on_value_changed
        )
        self.input_widget.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # Column 2: JSON 值标签（初始隐藏）
        json_display = str(self.json_value) if self.json_value is not None else "N/A"
        self.json_label = tk.Label(
            self.frame,
            text=json_display,
            width=15,
            font=FONT_PARAM_HINT,
            anchor="center",
            foreground=JSON_NA_FG if self.json_value is None else "black",
        )
        # 初始不 grid，由 show_json_column() 控制显示

    def _on_value_changed(self):
        """值变化时的回调"""
        self._update_json_highlight()  # 更新差异高亮
        if self.on_change_callback:
            self.on_change_callback()

    def get_value(self) -> bool:
        """获取当前值"""
        return self.bool_var.get()

    def set_value(self, value: bool):
        """设置值"""
        self.bool_var.set(bool(value))

    def validate(self) -> Tuple[bool, str]:
        """验证当前值（布尔值总是合法）"""
        return True, ""

    def highlight_error(self, show: bool):
        """布尔输入不需要错误高亮"""
        pass


class ListInput(BaseParameterInput):
    """列表输入组件（使用Entry，逗号分隔）"""

    def _create_widgets(self):
        """创建列表输入组件"""
        element_type = self.param_config.get("element_type", int)

        # Column 0: 标签
        display_name = self._get_display_name()
        self.label = SelectableLabel(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # 格式提示合并到 Tooltip
        type_name = element_type.__name__ if hasattr(element_type, "__name__") else "int"
        format_hint = f"Format: comma-separated {type_name}s"
        combined_tooltip = f"{self.tooltip_text}\n{format_hint}" if self.tooltip_text else format_hint
        ToolTip(self.label, combined_tooltip)

        # Column 1: Entry
        # 将列表转为逗号分隔字符串
        if self.param_value:
            value_str = ", ".join(str(v) for v in self.param_value)
        else:
            value_str = ""
        self.entry_var = tk.StringVar(value=value_str)
        self.input_widget = ttk.Entry(
            self.frame, textvariable=self.entry_var, width=30, font=FONT_PARAM_INPUT
        )
        self.input_widget.grid(row=0, column=1, padx=5, pady=2)

        # 绑定键盘输入事件
        self.input_widget.bind("<KeyRelease>", self._on_value_changed)

        # Column 2: JSON 值标签（初始隐藏）
        json_display = str(self.json_value) if self.json_value is not None else "N/A"
        self.json_label = tk.Label(
            self.frame,
            text=json_display,
            width=15,
            font=FONT_PARAM_HINT,
            anchor="center",
            foreground=JSON_NA_FG if self.json_value is None else "black",
        )
        # 初始不 grid，由 show_json_column() 控制显示

    def _on_value_changed(self, event=None):
        """值变化时的回调"""
        # 实时验证
        is_valid, _ = self.validate()
        self._update_json_highlight()  # 更新差异高亮
        if self.on_change_callback:
            self.on_change_callback()

    def get_value(self) -> list:
        """获取当前值"""
        element_type = self.param_config.get("element_type", int)
        value_str = self.entry_var.get()
        is_valid, value_list, _ = InputValidator.validate_list(value_str, element_type)
        return value_list if is_valid else []

    def set_value(self, value: list):
        """设置值"""
        if value:
            value_str = ", ".join(str(v) for v in value)
        else:
            value_str = ""
        self.entry_var.set(value_str)

    def validate(self) -> Tuple[bool, str]:
        """验证当前值"""
        element_type = self.param_config.get("element_type", int)
        value_str = self.entry_var.get()
        is_valid, _, error_msg = InputValidator.validate_list(value_str, element_type)

        # 使用输入框样式标识错误
        self.highlight_error(not is_valid)

        return is_valid, error_msg


class StrInput(BaseParameterInput):
    """字符串输入组件（使用Entry）"""

    def _create_widgets(self):
        """创建字符串输入组件"""
        # Column 0: 标签
        display_name = self._get_display_name()
        self.label = SelectableLabel(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # Tooltip（如果有）
        if self.tooltip_text:
            ToolTip(self.label, self.tooltip_text)

        # Column 1: Entry
        self.entry_var = tk.StringVar(value=str(self.param_value or ""))
        self.input_widget = ttk.Entry(
            self.frame, textvariable=self.entry_var, width=30, font=FONT_PARAM_INPUT
        )
        self.input_widget.grid(row=0, column=1, padx=5, pady=2)

        # 绑定键盘输入事件
        self.input_widget.bind("<KeyRelease>", self._on_value_changed)

        # Column 2: JSON 值标签（初始隐藏）
        json_display = str(self.json_value) if self.json_value is not None else "N/A"
        self.json_label = tk.Label(
            self.frame,
            text=json_display,
            width=15,
            font=FONT_PARAM_HINT,
            anchor="center",
            foreground=JSON_NA_FG if self.json_value is None else "black",
        )
        # 初始不 grid，由 show_json_column() 控制显示

    def _on_value_changed(self, event=None):
        """值变化时的回调"""
        self._update_json_highlight()  # 更新差异高亮
        if self.on_change_callback:
            self.on_change_callback()

    def get_value(self) -> str:
        """获取当前值"""
        return self.entry_var.get()

    def set_value(self, value: str):
        """设置值"""
        self.entry_var.set(str(value))

    def validate(self) -> Tuple[bool, str]:
        """验证当前值（字符串总是合法）"""
        return True, ""


class ComboInput(BaseParameterInput):
    """下拉选择组件（单选）"""

    def _create_widgets(self):
        """创建下拉选择组件"""
        options = self.param_config.get("options", [])

        # Column 0: 标签
        display_name = self._get_display_name()
        self.label = SelectableLabel(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # Tooltip（如果有）
        if self.tooltip_text:
            ToolTip(self.label, self.tooltip_text)

        # Column 1: Combobox
        self.combo_var = tk.StringVar(value=str(self.param_value or ""))
        self.input_widget = ttk.Combobox(
            self.frame,
            textvariable=self.combo_var,
            values=options,
            width=15,
            font=FONT_PARAM_INPUT,
            state="readonly",
        )
        self.input_widget.grid(row=0, column=1, padx=5, pady=2)

        # 绑定选择事件
        self.input_widget.bind("<<ComboboxSelected>>", self._on_value_changed)

        # Column 2: JSON 值标签（初始隐藏）
        json_display = str(self.json_value) if self.json_value is not None else "N/A"
        self.json_label = tk.Label(
            self.frame,
            text=json_display,
            width=15,
            font=FONT_PARAM_HINT,
            anchor="center",
            foreground=JSON_NA_FG if self.json_value is None else "black",
        )
        # 初始不 grid，由 show_json_column() 控制显示

    def _on_value_changed(self, event=None):
        """值变化时的回调"""
        self._update_json_highlight()
        if self.on_change_callback:
            self.on_change_callback()

    def get_value(self) -> str:
        """获取当前值"""
        return self.combo_var.get()

    def set_value(self, value: str):
        """设置值"""
        self.combo_var.set(str(value))

    def validate(self) -> Tuple[bool, str]:
        """验证当前值"""
        value = self.combo_var.get()
        options = self.param_config.get("options", [])
        if value in options:
            return True, ""
        return False, f"Value must be one of: {options}"


class MultiSelectInput(BaseParameterInput):
    """多选复选框组件"""

    def _create_widgets(self):
        """创建多选复选框组件"""
        options = self.param_config.get("options", [])

        # Column 0: 标签
        display_name = self._get_display_name()
        self.label = SelectableLabel(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # Tooltip（如果有）
        if self.tooltip_text:
            ToolTip(self.label, self.tooltip_text)

        # Column 1: 复选框容器
        self.checkbox_frame = ttk.Frame(self.frame)
        self.checkbox_frame.grid(row=0, column=1, padx=5, pady=2, sticky="w")

        # 创建复选框
        self.checkbuttons = {}
        self.vars = {}
        current_values = self.param_value if isinstance(self.param_value, list) else []

        for option in options:
            var = tk.BooleanVar(value=option in current_values)
            self.vars[option] = var
            cb = ttk.Checkbutton(
                self.checkbox_frame,
                text=option,
                variable=var,
                command=self._on_value_changed,
            )
            cb.pack(side=tk.LEFT, padx=3)
            self.checkbuttons[option] = cb

        # 用于基类的引用
        self.input_widget = self.checkbox_frame

        # Column 2: JSON 值标签（初始隐藏）
        json_display = str(self.json_value) if self.json_value is not None else "N/A"
        self.json_label = tk.Label(
            self.frame,
            text=json_display,
            width=20,
            font=FONT_PARAM_HINT,
            anchor="center",
            foreground=JSON_NA_FG if self.json_value is None else "black",
        )
        # 初始不 grid，由 show_json_column() 控制显示

    def _on_value_changed(self):
        """值变化时的回调"""
        self._update_json_highlight()
        if self.on_change_callback:
            self.on_change_callback()

    def get_value(self) -> list:
        """获取当前选中的值列表"""
        return [opt for opt, var in self.vars.items() if var.get()]

    def set_value(self, value: list):
        """设置选中状态"""
        if not isinstance(value, list):
            value = [value] if value else []
        for opt, var in self.vars.items():
            var.set(opt in value)

    def validate(self) -> Tuple[bool, str]:
        """验证当前值（至少选择一个）"""
        selected = self.get_value()
        if len(selected) == 0:
            return False, "At least one option must be selected"
        return True, ""

    def highlight_error(self, show: bool):
        """多选框不使用常规错误高亮"""
        pass


class ParameterInputFactory:
    """参数输入组件工厂类"""

    @staticmethod
    def create(
        parent: ttk.Frame,
        param_name: str,
        param_value: Any,
        param_config: dict,
        on_change_callback: Optional[Callable] = None,
        tooltip_text: Optional[str] = None,
        json_value: Optional[Any] = None,
    ) -> BaseParameterInput:
        """
        根据参数配置创建相应的输入组件

        Args:
            parent: 父容器
            param_name: 参数名称
            param_value: 参数初始值
            param_config: 参数配置，包含：
                - type: 参数类型（int, float, bool, list, str）
                - range: 范围（可选，对int和float有效）
                - element_type: 元素类型（对list有效）
                - options: 可选值列表（对str单选或list多选有效）
                - multi_select: 是否多选（对有options的参数有效）
                - description: 参数说明
            on_change_callback: 值变化时的回调函数
            tooltip_text: 鼠标悬浮提示文本（中文注释）
            json_value: JSON 文件中对应的参数值（只读显示）

        Returns:
            对应类型的参数输入组件
        """
        param_type = param_config.get("type", str)
        has_options = "options" in param_config
        is_multi_select = param_config.get("multi_select", False)

        # 有 options 时使用特殊组件
        if has_options:
            if is_multi_select or param_type == list:
                # 多选复选框
                return MultiSelectInput(
                    parent, param_name, param_value, param_config, on_change_callback, tooltip_text, json_value
                )
            else:
                # 单选下拉框
                return ComboInput(
                    parent, param_name, param_value, param_config, on_change_callback, tooltip_text, json_value
                )

        if param_type == int:
            return IntInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text, json_value
            )
        elif param_type == float:
            return FloatInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text, json_value
            )
        elif param_type == bool:
            return BoolInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text, json_value
            )
        elif param_type == list:
            return ListInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text, json_value
            )
        elif param_type == str:
            return StrInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text, json_value
            )
        else:
            # 默认使用字符串输入
            return StrInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text, json_value
            )
