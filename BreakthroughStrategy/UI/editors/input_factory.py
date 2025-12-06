"""参数输入组件工厂

为不同类型的参数创建相应的输入组件
"""

import tkinter as tk
from tkinter import ttk
from typing import Any, Tuple, Callable, Optional

from ..config import InputValidator
from ..styles import FONT_PARAM_LABEL, FONT_PARAM_INPUT, FONT_PARAM_HINT


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
        """
        self.parent = parent
        self.param_name = param_name
        self.param_value = param_value
        self.param_config = param_config
        self.on_change_callback = on_change_callback
        self.tooltip_text = tooltip_text

        # 主容器
        self.frame = ttk.Frame(parent)

        # 组件引用
        self.label = None
        self.input_widget = None
        self.range_label = None
        self.error_indicator = None

        # 创建组件
        self._create_widgets()

        # 绑定 tooltip
        if self.tooltip_text and self.label:
            ToolTip(self.label, self.tooltip_text)

    def _get_display_name(self) -> str:
        """
        获取参数的显示名称（移除组名前缀）

        例如: peak_weights.volume -> volume
              candle_classification.big_body_threshold -> big_body_threshold

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
        """显示/隐藏错误高亮"""
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


class IntInput(BaseParameterInput):
    """整数输入组件（使用Spinbox）"""

    def _create_widgets(self):
        """创建整数输入组件"""
        min_val, max_val = self.param_config.get("range", (0, 100))
        description = self.param_config.get("description", "")

        # 标签 - 14号字体，使用显示名称
        display_name = self._get_display_name()
        self.label = ttk.Label(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # Spinbox - 14号字体
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

        # 范围提示 - 14号字体
        self.range_label = ttk.Label(
            self.frame,
            text=f"({min_val} - {max_val})",
            foreground="gray",
            font=FONT_PARAM_HINT,
        )
        self.range_label.grid(row=0, column=2, padx=5, pady=2)

        # 错误指示器 - 14号字体
        self.error_indicator = ttk.Label(
            self.frame, text="", foreground="red", font=FONT_PARAM_LABEL
        )
        self.error_indicator.grid(row=0, column=3, padx=5, pady=2)

    def _on_value_changed(self):
        """值变化时的回调"""
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

        if not is_valid:
            self.error_indicator.config(text="✗")
        else:
            self.error_indicator.config(text="")

        return is_valid, error_msg


class FloatInput(BaseParameterInput):
    """浮点数输入组件（使用Entry + 验证）"""

    def _create_widgets(self):
        """创建浮点数输入组件"""
        min_val, max_val = self.param_config.get("range", (0.0, 1.0))
        description = self.param_config.get("description", "")

        # 标签 - 14号字体，使用显示名称
        display_name = self._get_display_name()
        self.label = ttk.Label(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # Entry - 14号字体
        self.entry_var = tk.StringVar(value=str(self.param_value or min_val))
        self.input_widget = ttk.Entry(
            self.frame, textvariable=self.entry_var, width=15, font=FONT_PARAM_INPUT
        )
        self.input_widget.grid(row=0, column=1, padx=5, pady=2)

        # 绑定键盘输入事件
        self.input_widget.bind("<KeyRelease>", self._on_value_changed)

        # 范围提示 - 14号字体
        self.range_label = ttk.Label(
            self.frame,
            text=f"({min_val} - {max_val})",
            foreground="gray",
            font=FONT_PARAM_HINT,
        )
        self.range_label.grid(row=0, column=2, padx=5, pady=2)

        # 错误指示器 - 14号字体
        self.error_indicator = ttk.Label(
            self.frame, text="", foreground="red", font=FONT_PARAM_LABEL
        )
        self.error_indicator.grid(row=0, column=3, padx=5, pady=2)

    def _on_value_changed(self, event=None):
        """值变化时的回调"""
        # 实时验证
        is_valid, _ = self.validate()
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

        if not is_valid:
            self.error_indicator.config(text="✗")
        else:
            self.error_indicator.config(text="")

        return is_valid, error_msg


class BoolInput(BaseParameterInput):
    """布尔输入组件（使用Checkbutton）"""

    def _create_widgets(self):
        """创建布尔输入组件"""
        description = self.param_config.get("description", "")

        # 标签 - 14号字体，使用显示名称
        display_name = self._get_display_name()
        self.label = ttk.Label(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # Checkbutton
        self.bool_var = tk.BooleanVar(value=bool(self.param_value))
        self.input_widget = ttk.Checkbutton(
            self.frame, variable=self.bool_var, command=self._on_value_changed
        )
        self.input_widget.grid(row=0, column=1, sticky="w", padx=5, pady=2)

    def _on_value_changed(self):
        """值变化时的回调"""
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
        description = self.param_config.get("description", "")

        # 标签 - 14号字体，使用显示名称
        display_name = self._get_display_name()
        self.label = ttk.Label(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # Entry - 14号字体
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

        # 提示 - 14号字体
        type_name = element_type.__name__ if hasattr(element_type, "__name__") else "int"
        self.range_label = ttk.Label(
            self.frame,
            text=f"(comma-separated {type_name}s)",
            foreground="gray",
            font=FONT_PARAM_HINT,
        )
        self.range_label.grid(row=0, column=2, padx=5, pady=2)

        # 错误指示器 - 14号字体
        self.error_indicator = ttk.Label(
            self.frame, text="", foreground="red", font=FONT_PARAM_LABEL
        )
        self.error_indicator.grid(row=0, column=3, padx=5, pady=2)

    def _on_value_changed(self, event=None):
        """值变化时的回调"""
        # 实时验证
        is_valid, _ = self.validate()
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

        if not is_valid:
            self.error_indicator.config(text="✗")
        else:
            self.error_indicator.config(text="")

        return is_valid, error_msg


class StrInput(BaseParameterInput):
    """字符串输入组件（使用Entry）"""

    def _create_widgets(self):
        """创建字符串输入组件"""
        description = self.param_config.get("description", "")

        # 标签 - 14号字体，使用显示名称
        display_name = self._get_display_name()
        self.label = ttk.Label(
            self.frame, text=f"{display_name}:", width=25, font=FONT_PARAM_LABEL
        )
        self.label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        # Entry - 14号字体
        self.entry_var = tk.StringVar(value=str(self.param_value or ""))
        self.input_widget = ttk.Entry(
            self.frame, textvariable=self.entry_var, width=30, font=FONT_PARAM_INPUT
        )
        self.input_widget.grid(row=0, column=1, padx=5, pady=2)

        # 绑定键盘输入事件
        self.input_widget.bind("<KeyRelease>", self._on_value_changed)

    def _on_value_changed(self, event=None):
        """值变化时的回调"""
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
                - description: 参数说明
            on_change_callback: 值变化时的回调函数
            tooltip_text: 鼠标悬浮提示文本（中文注释）

        Returns:
            对应类型的参数输入组件
        """
        param_type = param_config.get("type", str)

        if param_type == int:
            return IntInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text
            )
        elif param_type == float:
            return FloatInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text
            )
        elif param_type == bool:
            return BoolInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text
            )
        elif param_type == list:
            return ListInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text
            )
        elif param_type == str:
            return StrInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text
            )
        else:
            # 默认使用字符串输入
            return StrInput(
                parent, param_name, param_value, param_config, on_change_callback, tooltip_text
            )
