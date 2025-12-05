"""工具函数"""
import os
import tkinter as tk
from tkinter import ttk
from pathlib import Path


def get_project_root():
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent.parent


def ensure_dir(directory):
    """确保目录存在"""
    os.makedirs(directory, exist_ok=True)
    return directory


def show_error_dialog(parent, title, message, font_size=16):
    """
    显示错误对话框（大字体）

    Args:
        parent: 父窗口
        title: 标题
        message: 消息内容
        font_size: 字体大小
    """
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()

    # 设置窗口最小宽度
    dialog.minsize(400, 150)

    # 主框架
    frame = ttk.Frame(dialog, padding="20")
    frame.pack(fill=tk.BOTH, expand=True)

    # 消息标签
    msg_label = ttk.Label(
        frame,
        text=message,
        font=("Arial", font_size),
        wraplength=500,
        foreground="red"
    )
    msg_label.pack(pady=20)

    # 确定按钮
    btn_frame = ttk.Frame(frame)
    btn_frame.pack(pady=10)

    ok_btn = ttk.Button(
        btn_frame,
        text="OK",
        command=dialog.destroy,
        width=10
    )
    ok_btn.pack()

    # 居中显示
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
    dialog.geometry(f"+{x}+{y}")

    # 绑定回车键和ESC键
    dialog.bind('<Return>', lambda e: dialog.destroy())
    dialog.bind('<Escape>', lambda e: dialog.destroy())

    ok_btn.focus_set()
    dialog.wait_window()
