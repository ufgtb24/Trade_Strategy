"""列配置对话框"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, List


class ColumnConfigDialog:
    """列配置对话框（多选Listbox）"""

    def __init__(
        self,
        parent: tk.Widget,
        available_columns: List[str],
        visible_columns: List[str],
        on_apply_callback: Callable[[List[str]], None],
    ):
        """
        初始化对话框

        Args:
            parent: 父窗口
            available_columns: 所有可用列
            visible_columns: 当前可见列
            on_apply_callback: Apply按钮回调
        """
        self.available_columns = available_columns
        self.visible_columns = visible_columns
        self.on_apply_callback = on_apply_callback

        # 创建模态窗口
        self.window = tk.Toplevel(parent)
        self.window.title("Configure Columns")
        self.window.geometry("400x500")
        self.window.transient(parent)
        self.window.grab_set()

        self._create_ui()

        # 居中显示
        self.window.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.window.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.window.winfo_height()) // 2
        self.window.geometry(f"+{x}+{y}")

    def _create_ui(self):
        """创建UI组件"""
        # 说明标签
        ttk.Label(
            self.window,
            text="Select columns to display in the stock list:",
            font=("", 10, "bold"),
        ).pack(pady=10)

        # 列表区域（带滚动条）
        list_frame = ttk.Frame(self.window)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(
            list_frame,
            selectmode=tk.MULTIPLE,
            yscrollcommand=scrollbar.set,
            font=("", 10),
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        # 填充数据并预选中
        for idx, col in enumerate(self.available_columns):
            # 格式化显示名称
            display_name = col.replace("_", " ").title()
            self.listbox.insert(tk.END, display_name)

            if col in self.visible_columns:
                self.listbox.selection_set(idx)

        # 快捷按钮区域
        shortcut_frame = ttk.Frame(self.window)
        shortcut_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(
            shortcut_frame, text="Select All", command=self._select_all
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(shortcut_frame, text="Clear All", command=self._clear_all).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Button(
            shortcut_frame, text="Reset to Default", command=self._reset_default
        ).pack(side=tk.LEFT, padx=5)

        # 底部按钮
        button_frame = ttk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(button_frame, text="Apply", command=self._apply).pack(
            side=tk.RIGHT, padx=5
        )

        ttk.Button(button_frame, text="Cancel", command=self.window.destroy).pack(
            side=tk.RIGHT, padx=5
        )

    def _select_all(self):
        """全选"""
        self.listbox.selection_set(0, tk.END)

    def _clear_all(self):
        """清空"""
        self.listbox.selection_clear(0, tk.END)

    def _reset_default(self):
        """重置为默认（3个核心列）"""
        self.listbox.selection_clear(0, tk.END)
        default_columns = ["bts", "active_peaks", "max_quality"]
        for idx, col in enumerate(self.available_columns):
            if col in default_columns:
                self.listbox.selection_set(idx)

    def _apply(self):
        """应用选择"""
        # 获取选中的列
        selected_indices = self.listbox.curselection()
        selected_columns = [self.available_columns[i] for i in selected_indices]

        # 调用回调
        if self.on_apply_callback:
            self.on_apply_callback(selected_columns)

        # 关闭窗口
        self.window.destroy()
