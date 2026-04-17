"""UI工具函数"""
import os
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import pandas as pd
from datetime import datetime
from typing import Optional


# ==================== UI 工具函数 ====================

def get_project_root():
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent


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


# ==================== 可视化工具函数 ====================

def quality_to_color(quality_score: float) -> str:
    """
    根据质量分数映射颜色

    Args:
        quality_score: 质量分数 (0-100)

    Returns:
        颜色代码
    """
    if quality_score >= 60:
        return "#0048FF"  # 红色 - 高质量
    elif quality_score >= 40:
        return '#000000'  # 黑色 - 中等质量
    else:
        return "#909090"  # 灰色 - 低质量


def ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    确保 DataFrame 有 DatetimeIndex (mplfinance 要求)

    Args:
        df: 输入 DataFrame

    Returns:
        带 DatetimeIndex 的 DataFrame
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'date' in df.columns:
            df = df.copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        elif 'Date' in df.columns:
            df = df.copy()
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.set_index('Date')
        else:
            raise ValueError("DataFrame must have 'date' or 'Date' column or DatetimeIndex")

    return df


def format_date(date_obj) -> str:
    """
    格式化日期显示

    Args:
        date_obj: 日期对象 (datetime, pd.Timestamp, str)

    Returns:
        格式化字符串 (YYYY-MM-DD)
    """
    if isinstance(date_obj, str):
        date_obj = pd.to_datetime(date_obj)

    if isinstance(date_obj, (datetime, pd.Timestamp)):
        return date_obj.strftime('%Y-%m-%d')

    return str(date_obj)


def format_price(price: float) -> str:
    """
    格式化价格显示

    Args:
        price: 价格

    Returns:
        格式化字符串 (保留2位小数)
    """
    return f"${price:.2f}"


def filter_date_range(df: pd.DataFrame,
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None) -> pd.DataFrame:
    """
    过滤日期范围

    Args:
        df: DataFrame (必须有 DatetimeIndex)
        start_date: 开始日期 (可选)
        end_date: 结束日期 (可选)

    Returns:
        过滤后的 DataFrame
    """
    df = ensure_datetime_index(df)

    if start_date:
        df = df[df.index >= pd.to_datetime(start_date)]

    if end_date:
        df = df[df.index <= pd.to_datetime(end_date)]

    return df
