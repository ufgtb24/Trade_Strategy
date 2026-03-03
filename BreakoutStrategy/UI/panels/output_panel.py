"""输出面板组件 - 显示日志和扫描信息"""

import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Optional


class OutputPanel:
    """
    输出面板组件

    在主窗口底部显示日志信息，支持显示/隐藏切换。
    """

    def __init__(self, parent, initial_visible: bool = True, height: int = 150):
        """
        初始化输出面板

        Args:
            parent: 父容器
            initial_visible: 初始是否可见
            height: 面板高度（像素）
        """
        self.parent = parent
        self._visible = initial_visible
        self._height = height

        # 创建主容器
        self.container = ttk.Frame(parent)
        self.container.pack(fill=tk.X, side=tk.BOTTOM)

        # 创建工具栏
        self._create_toolbar()

        # 创建文本区域容器（用于控制显示/隐藏）
        self.text_container = ttk.Frame(self.container)
        if initial_visible:
            self.text_container.pack(fill=tk.BOTH, expand=False)

        # 创建文本区域
        self._create_text_area()

        # 更新按钮文本
        self._update_toggle_button()

    def _create_toolbar(self):
        """创建工具栏"""
        toolbar = ttk.Frame(self.container)
        toolbar.pack(fill=tk.X, pady=(2, 0))

        # 显示/隐藏按钮
        self.toggle_btn = ttk.Button(
            toolbar,
            text="▼ Output",
            width=12,
            command=self.toggle_visibility,
        )
        self.toggle_btn.pack(side=tk.LEFT, padx=2)

        # Clear 按钮
        ttk.Button(
            toolbar,
            text="Clear",
            width=6,
            command=self.clear,
        ).pack(side=tk.LEFT, padx=2)

    def _create_text_area(self):
        """创建文本区域"""
        # 文本框 + 滚动条
        text_frame = ttk.Frame(self.text_container)
        text_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text = tk.Text(
            text_frame,
            height=8,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            state=tk.DISABLED,
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
        )
        self.text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.text.yview)

        # 配置颜色标签
        self.text.tag_config("info", foreground="#d4d4d4")
        self.text.tag_config("warning", foreground="#dcdcaa")
        self.text.tag_config("error", foreground="#f14c4c")
        self.text.tag_config("success", foreground="#4ec9b0")
        self.text.tag_config("timestamp", foreground="#808080")

    def _update_toggle_button(self):
        """更新显示/隐藏按钮文本"""
        if self._visible:
            self.toggle_btn.config(text="▼ Output")
        else:
            self.toggle_btn.config(text="▶ Output")

    def log(self, message: str, level: str = "info"):
        """
        添加日志消息

        Args:
            message: 消息内容
            level: 日志级别 (info/warning/error/success)
        """
        timestamp = datetime.now().strftime("[%H:%M:%S] ")

        self.text.config(state=tk.NORMAL)
        self.text.insert(tk.END, timestamp, "timestamp")
        self.text.insert(tk.END, message + "\n", level)
        self.text.see(tk.END)  # 自动滚动到底部
        self.text.config(state=tk.DISABLED)

    def clear(self):
        """清空输出内容"""
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.config(state=tk.DISABLED)

    def toggle_visibility(self):
        """切换显示/隐藏状态"""
        self._visible = not self._visible
        if self._visible:
            self.text_container.pack(fill=tk.BOTH, expand=False)
        else:
            self.text_container.pack_forget()
        self._update_toggle_button()

    def set_visible(self, visible: bool):
        """
        设置显示状态

        Args:
            visible: 是否可见
        """
        if visible != self._visible:
            self.toggle_visibility()

    def is_visible(self) -> bool:
        """获取当前显示状态"""
        return self._visible
