"""图表显示范围控制栏"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class DisplayControlBar(ttk.Frame):
    """
    图表底部显示范围控制栏

    提供 before_months、after_months 和 lookback_days 的 Spinbox 控件，
    用于动态调整 K 线图表的显示范围和信号检测窗口。
    """

    def __init__(
        self,
        parent,
        on_change_callback: Callable[[int, int], None],
        on_lookback_callback: Optional[Callable[[int], None]] = None,
        initial_before: int = 6,
        initial_after: int = 1,
        initial_lookback: int = 42,
    ):
        """
        初始化控制栏

        Args:
            parent: 父容器
            on_change_callback: 显示范围变化回调，签名为 (before_months, after_months)
            on_lookback_callback: lookback_days 变化回调，签名为 (lookback_days)
            initial_before: 初始 before_months 值
            initial_after: 初始 after_months 值
            initial_lookback: 初始 lookback_days 值
        """
        super().__init__(parent)
        self._callback = on_change_callback
        self._lookback_callback = on_lookback_callback

        # 创建变量
        self._before_var = tk.IntVar(value=initial_before)
        self._after_var = tk.IntVar(value=initial_after)
        self._lookback_var = tk.IntVar(value=initial_lookback)

        # 防止重复触发
        self._updating = False

        self._create_widgets()

    def _create_widgets(self):
        """创建控件"""
        # 左侧留白，使控件居中偏右
        ttk.Label(self, text="").pack(side=tk.LEFT, expand=True)

        # Before 控件组
        before_frame = ttk.Frame(self)
        before_frame.pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(before_frame, text="Before:").pack(side=tk.LEFT, padx=(0, 5))
        self._before_spinbox = ttk.Spinbox(
            before_frame,
            from_=0,
            to=12,
            width=3,
            textvariable=self._before_var,
            command=self._on_value_changed,
        )
        self._before_spinbox.pack(side=tk.LEFT)
        ttk.Label(before_frame, text="months").pack(side=tk.LEFT, padx=(5, 0))

        # After 控件组
        after_frame = ttk.Frame(self)
        after_frame.pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(after_frame, text="After:").pack(side=tk.LEFT, padx=(0, 5))
        self._after_spinbox = ttk.Spinbox(
            after_frame,
            from_=0,
            to=3,
            width=3,
            textvariable=self._after_var,
            command=self._on_value_changed,
        )
        self._after_spinbox.pack(side=tk.LEFT)
        ttk.Label(after_frame, text="months").pack(side=tk.LEFT, padx=(5, 0))

        # Lookback 控件组
        lookback_frame = ttk.Frame(self)
        lookback_frame.pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(lookback_frame, text="Lookback:").pack(side=tk.LEFT, padx=(0, 5))
        self._lookback_spinbox = ttk.Spinbox(
            lookback_frame,
            from_=7,
            to=252,
            width=4,
            textvariable=self._lookback_var,
            command=self._on_lookback_changed,
        )
        self._lookback_spinbox.pack(side=tk.LEFT)
        ttk.Label(lookback_frame, text="days").pack(side=tk.LEFT, padx=(5, 0))

        # 绑定回车键和焦点离开事件
        self._before_spinbox.bind("<Return>", lambda e: self._on_value_changed())
        self._before_spinbox.bind("<FocusOut>", lambda e: self._on_value_changed())
        self._after_spinbox.bind("<Return>", lambda e: self._on_value_changed())
        self._after_spinbox.bind("<FocusOut>", lambda e: self._on_value_changed())
        self._lookback_spinbox.bind("<Return>", lambda e: self._on_lookback_changed())
        self._lookback_spinbox.bind("<FocusOut>", lambda e: self._on_lookback_changed())

    def _on_value_changed(self):
        """显示范围值变化处理"""
        if self._updating:
            return

        self._updating = True
        try:
            before = self._before_var.get()
            after = self._after_var.get()

            # 范围校验
            before = max(0, min(12, before))
            after = max(0, min(3, after))

            # 更新变量（如果被校验修改）
            self._before_var.set(before)
            self._after_var.set(after)

            # 触发回调
            if self._callback:
                self._callback(before, after)
        except tk.TclError:
            # 输入无效值时忽略
            pass
        finally:
            self._updating = False

    def _on_lookback_changed(self):
        """lookback_days 值变化处理"""
        if self._updating:
            return

        self._updating = True
        try:
            lookback = self._lookback_var.get()

            # 范围校验 (7~252)
            lookback = max(7, min(252, lookback))

            # 更新变量（如果被校验修改）
            self._lookback_var.set(lookback)

            # 触发回调
            if self._lookback_callback:
                self._lookback_callback(lookback)
        except tk.TclError:
            # 输入无效值时忽略
            pass
        finally:
            self._updating = False

    def get_values(self) -> tuple[int, int]:
        """
        获取当前值

        Returns:
            (before_months, after_months) 元组
        """
        return (self._before_var.get(), self._after_var.get())

    def set_values(self, before: int, after: int):
        """
        设置显示范围值（不触发回调）

        Args:
            before: before_months 值
            after: after_months 值
        """
        self._updating = True
        try:
            self._before_var.set(before)
            self._after_var.set(after)
        finally:
            self._updating = False

    def get_lookback_days(self) -> int:
        """
        获取当前 lookback_days 值

        Returns:
            lookback_days 值
        """
        return self._lookback_var.get()

    def set_lookback_days(self, lookback: int):
        """
        设置 lookback_days 值（不触发回调）

        Args:
            lookback: lookback_days 值
        """
        self._updating = True
        try:
            self._lookback_var.set(lookback)
        finally:
            self._updating = False
