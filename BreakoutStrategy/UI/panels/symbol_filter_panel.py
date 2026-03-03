"""符号筛选面板 - 控制K线图上显示哪些符号"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict


class SymbolFilterPanel(ttk.Frame):
    """
    符号筛选面板

    提供 6 个 checkbox 控制 K 线图上的符号显示：
    - B: 突破信号标签
    - V: 超大成交量信号标签
    - Y: 大阳线信号标签
    - D: 双底信号标签（含 TR1 标记）
    - Peak: 峰值标记（空心倒三角 + ID）
    - Trough: 支撑 trough 标记（空心正三角 + ID）
    """

    # 符号类型定义
    SYMBOL_TYPES = [
        ("show_bo", "B"),
        ("show_hv", "V"),
        ("show_by", "Y"),
        ("show_dt", "D"),
        ("show_peak", "Peak"),
        ("show_trough", "Trough"),
    ]

    def __init__(
        self,
        parent,
        on_change_callback: Callable[[Dict[str, bool]], None],
        initial_state: Dict[str, bool] = None,
    ):
        """
        初始化符号筛选面板

        Args:
            parent: 父容器
            on_change_callback: 状态变化回调，签名为 (filter_state: Dict[str, bool])
            initial_state: 初始状态字典，如 {"show_bo": True, "show_hv": False, ...}
        """
        super().__init__(parent)
        self._callback = on_change_callback
        self._updating = False

        # 初始化状态（默认全部开启）
        if initial_state is None:
            initial_state = {}
        self._vars: Dict[str, tk.BooleanVar] = {}
        for key, _ in self.SYMBOL_TYPES:
            self._vars[key] = tk.BooleanVar(value=initial_state.get(key, True))

        self._create_widgets()

    def _create_widgets(self):
        """创建控件"""
        # 标签
        ttk.Label(self, text="Symbols:").pack(side=tk.LEFT, padx=(0, 10))

        # 创建 checkbox
        for key, label in self.SYMBOL_TYPES:
            cb = ttk.Checkbutton(
                self,
                text=label,
                variable=self._vars[key],
                command=self._on_value_changed,
            )
            cb.pack(side=tk.LEFT, padx=(0, 8))

    def _on_value_changed(self):
        """值变化处理"""
        if self._updating:
            return

        self._updating = True
        try:
            if self._callback:
                self._callback(self.get_state())
        finally:
            self._updating = False

    def get_state(self) -> Dict[str, bool]:
        """
        获取当前筛选状态

        Returns:
            筛选状态字典，如 {"show_bo": True, "show_hv": False, ...}
        """
        return {key: var.get() for key, var in self._vars.items()}

    def set_state(self, state: Dict[str, bool]):
        """
        设置筛选状态（不触发回调）

        Args:
            state: 筛选状态字典
        """
        self._updating = True
        try:
            for key, value in state.items():
                if key in self._vars:
                    self._vars[key].set(value)
        finally:
            self._updating = False
