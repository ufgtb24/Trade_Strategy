"""文件命名对话框

用于扫描结果保存时自定义文件名
"""

import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Optional


class FilenameDialog:
    """文件命名对话框

    让用户输入自定义文件名，默认为时间戳格式
    """

    def __init__(self, parent: tk.Widget, title: str = "Save Scan Results"):
        """
        初始化对话框

        Args:
            parent: 父窗口
            title: 对话框标题
        """
        self.result: Optional[str] = None

        # 创建模态窗口
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.grab_set()

        # 变量
        default_name = f"scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.filename_var = tk.StringVar(value=default_name)

        # 创建 UI
        self._create_ui()

        # 调整窗口位置（大小自适应内容）
        self.window.update_idletasks()
        width = self.window.winfo_reqwidth()
        height = self.window.winfo_reqheight()
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        self.window.geometry(f"+{x}+{y}")

        # 绑定事件
        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.window.bind("<Return>", lambda e: self._on_ok())
        self.window.bind("<Escape>", lambda e: self._on_cancel())

        # 选中输入框内容
        self.entry.select_range(0, tk.END)
        self.entry.focus_set()

    def _create_ui(self):
        """创建 UI 组件"""
        main_frame = ttk.Frame(self.window, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 文件名输入区
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(input_frame, text="Filename:").pack(side=tk.LEFT)
        self.entry = ttk.Entry(input_frame, textvariable=self.filename_var, width=35)
        self.entry.pack(side=tk.LEFT, padx=(10, 5), fill=tk.X, expand=True)
        ttk.Label(input_frame, text=".json", foreground="gray").pack(side=tk.LEFT)

        # 按钮区
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(button_frame, text="Cancel", command=self._on_cancel).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(button_frame, text="OK", command=self._on_ok).pack(
            side=tk.RIGHT, padx=5
        )

    def _on_ok(self):
        """确认按钮回调"""
        filename = self.filename_var.get().strip()
        if filename:
            # 确保以 .json 结尾
            if not filename.endswith(".json"):
                filename = f"{filename}.json"
            self.result = filename
        self.window.destroy()

    def _on_cancel(self):
        """取消按钮回调"""
        self.result = None
        self.window.destroy()

    def show(self) -> Optional[str]:
        """显示对话框并等待结果

        Returns:
            用户输入的文件名（含 .json 后缀），取消则返回 None
        """
        self.window.wait_window()
        return self.result
