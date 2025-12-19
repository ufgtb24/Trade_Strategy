"""Rescan 模式选择对话框

用于 Rescan All 功能选择覆盖或新建文件
"""

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional, Tuple


class RescanModeDialog:
    """Rescan 模式选择对话框

    让用户选择覆盖当前文件或新建文件
    """

    # 模式常量
    MODE_OVERWRITE = "overwrite"
    MODE_NEW_FILE = "new_file"

    def __init__(self, parent: tk.Widget, current_file: str):
        """
        初始化对话框

        Args:
            parent: 父窗口
            current_file: 当前已加载的 JSON 文件路径
        """
        self.parent = parent
        self.current_file = current_file
        self.result: Optional[Tuple[str, Optional[str]]] = None

        # 创建模态窗口
        self.window = tk.Toplevel(parent)
        self.window.title("Rescan All")
        self.window.transient(parent)
        self.window.grab_set()

        # 变量
        self.mode_var = tk.StringVar(value=self.MODE_OVERWRITE)
        default_name = f"scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.filename_var = tk.StringVar(value=default_name)

        # 创建 UI
        self._create_ui()

        # 调整窗口大小和位置 - 自适应内容大小
        self.window.update_idletasks()
        # 获取内容所需的实际尺寸
        req_width = self.window.winfo_reqwidth()
        req_height = self.window.winfo_reqheight()
        # 设置最小尺寸，并添加边距
        width = max(450, req_width + 20)
        height = max(250, req_height + 20)
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.minsize(width, height)

        # 绑定事件
        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.window.bind("<Escape>", lambda e: self._on_cancel())

        # 初始状态
        self._on_mode_changed()

    def _create_ui(self):
        """创建 UI 组件"""
        main_frame = ttk.Frame(self.window, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 当前文件显示
        file_frame = ttk.LabelFrame(main_frame, text="Current File", padding=10)
        file_frame.pack(fill=tk.X, pady=(0, 10))

        # 只显示文件名，完整路径太长
        current_filename = Path(self.current_file).name
        ttk.Label(file_frame, text=current_filename, foreground="gray").pack(
            anchor=tk.W
        )

        # 模式选择区
        mode_frame = ttk.LabelFrame(main_frame, text="Save Mode", padding=10)
        mode_frame.pack(fill=tk.X, pady=(0, 10))

        # 覆盖模式
        ttk.Radiobutton(
            mode_frame,
            text="Overwrite current file",
            variable=self.mode_var,
            value=self.MODE_OVERWRITE,
            command=self._on_mode_changed,
        ).pack(anchor=tk.W)

        # 新建文件模式
        ttk.Radiobutton(
            mode_frame,
            text="Create new file",
            variable=self.mode_var,
            value=self.MODE_NEW_FILE,
            command=self._on_mode_changed,
        ).pack(anchor=tk.W, pady=(5, 0))

        # 文件名输入区（新建模式时显示）
        self.filename_frame = ttk.Frame(mode_frame)
        self.filename_frame.pack(fill=tk.X, pady=(5, 0), padx=(20, 0))

        ttk.Label(self.filename_frame, text="Filename:").pack(side=tk.LEFT)
        self.entry = ttk.Entry(
            self.filename_frame, textvariable=self.filename_var, width=30
        )
        self.entry.pack(side=tk.LEFT, padx=(10, 5))
        ttk.Label(self.filename_frame, text=".json", foreground="gray").pack(
            side=tk.LEFT
        )

        # 按钮区
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(button_frame, text="Cancel", command=self._on_cancel).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(button_frame, text="Start", command=self._on_start).pack(
            side=tk.RIGHT, padx=5
        )

    def _on_mode_changed(self):
        """模式切换时更新 UI"""
        mode = self.mode_var.get()
        if mode == self.MODE_NEW_FILE:
            # 显示文件名输入区
            for child in self.filename_frame.winfo_children():
                child.configure(state="normal")
            self.entry.focus_set()
        else:
            # 隐藏文件名输入区
            for child in self.filename_frame.winfo_children():
                if isinstance(child, ttk.Entry):
                    child.configure(state="disabled")

    def _on_start(self):
        """开始按钮回调"""
        mode = self.mode_var.get()

        if mode == self.MODE_OVERWRITE:
            # 覆盖模式：二次确认
            current_filename = Path(self.current_file).name
            confirmed = messagebox.askyesno(
                "Confirm Overwrite",
                f"This will overwrite:\n{current_filename}\n\n"
                "This action cannot be undone.\nContinue?",
                icon="warning",
                parent=self.window,
            )
            if not confirmed:
                return
            self.result = (self.MODE_OVERWRITE, self.current_file)
        else:
            # 新建文件模式
            filename = self.filename_var.get().strip()
            if not filename:
                messagebox.showwarning(
                    "Warning", "Please enter a filename.", parent=self.window
                )
                return
            # 确保以 .json 结尾
            if not filename.endswith(".json"):
                filename = f"{filename}.json"
            self.result = (self.MODE_NEW_FILE, filename)

        self.window.destroy()

    def _on_cancel(self):
        """取消按钮回调"""
        self.result = None
        self.window.destroy()

    def show(self) -> Optional[Tuple[str, str]]:
        """显示对话框并等待结果

        Returns:
            (mode, filename/filepath) 元组：
            - MODE_OVERWRITE: (mode, 当前文件完整路径)
            - MODE_NEW_FILE: (mode, 用户输入的文件名含.json后缀)
            - 取消返回 None
        """
        self.window.wait_window()
        return self.result
