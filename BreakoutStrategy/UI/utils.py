"""UI工具函数"""
import os
import tkinter as tk
from tkinter import ttk
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import pandas as pd
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Tuple


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


# ==================== 股票过滤工具函数 ====================

def _filter_single_stock(args: Tuple) -> Tuple[str, bool, Optional[str]]:
    """
    过滤单只股票（供多进程 worker 调用）

    Args:
        args: (symbol, data_dir, entry_date, price_min, price_max, volume_min)

    Returns:
        (symbol, passed, exclude_reason)
        - passed: True 表示通过过滤
        - exclude_reason: "price" / "volume" / "data" / None
    """
    symbol, data_dir, entry_date, price_min, price_max, volume_min = args
    pkl_path = Path(data_dir) / f"{symbol}.pkl"

    if not pkl_path.exists():
        return (symbol, False, "data")

    try:
        df = pd.read_pickle(pkl_path)
        if df is None or len(df) == 0:
            return (symbol, False, "data")

        # 确保索引是 DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            return (symbol, False, "data")

        # 定位 entry_date（使用 ffill 找最近的交易日）
        entry_ts = pd.Timestamp(entry_date)
        if entry_ts > df.index.max():
            # entry_date 超出数据范围，使用最新日期
            entry_idx = len(df) - 1
        elif entry_ts < df.index.min():
            # entry_date 早于数据起始日期，跳过
            return (symbol, False, "data")
        else:
            # 找到 <= entry_date 的最近交易日
            mask = df.index <= entry_ts
            if not mask.any():
                return (symbol, False, "data")
            entry_idx = mask.sum() - 1

        # 检查价格条件（entry_date 当天的收盘价）
        close_price = df.iloc[entry_idx]["close"]
        if not (price_min <= close_price <= price_max):
            return (symbol, False, "price")

        # 检查成交量条件（entry_date 前 63 个交易日的平均成交量）
        vol_start_idx = max(0, entry_idx - 63)
        vol_data = df.iloc[vol_start_idx:entry_idx + 1]["volume"]
        if len(vol_data) == 0:
            return (symbol, False, "data")

        avg_volume = vol_data.mean()
        if avg_volume < volume_min:
            return (symbol, False, "volume")

        # 通过所有过滤条件
        return (symbol, True, None)

    except Exception:
        return (symbol, False, "data")


def filter_stocks(
    symbols: List[str],
    data_dir: Path,
    entry_date: date,
    filter_config: Dict,
    on_log: Optional[Callable[[str, str], None]] = None,
    max_workers: Optional[int] = None,
) -> List[str]:
    """
    根据入口日属性过滤股票（多进程并行）

    在 entry_date（检测窗口入口日）检查股票的价格和成交量属性，
    只返回满足条件的股票列表。

    Args:
        symbols: 待过滤的股票代码列表
        data_dir: 数据目录（包含 .pkl 文件）
        entry_date: 检测窗口入口日
        filter_config: 过滤配置字典，包含：
            - enabled: bool - 是否启用过滤
            - price_min: float - 价格下限
            - price_max: float - 价格上限
            - volume_min: int - 三个月平均成交量下限
        on_log: 日志回调函数 (message, level)
        max_workers: 最大并行进程数，默认为 cpu_count - 2

    Returns:
        满足条件的股票代码列表
    """
    # 如果未启用过滤，直接返回所有股票
    if not filter_config.get("enabled", True):
        return symbols

    price_min = filter_config.get("price_min", 1.0)
    price_max = filter_config.get("price_max", 10.0)
    volume_min = filter_config.get("volume_min", 100000)

    def log(msg: str, level: str = "info"):
        if on_log:
            on_log(msg, level)

    log(f"Filter: price [{price_min}, {price_max}], avg_volume >= {volume_min:,}")

    # 计算并行进程数
    if max_workers is None:
        max_workers = max(1, (os.cpu_count() or 4) - 2)

    # 构建参数列表
    # 注意：data_dir 需要转为 str 以便跨进程传递
    data_dir_str = str(data_dir)
    args_list = [
        (symbol, data_dir_str, entry_date, price_min, price_max, volume_min)
        for symbol in symbols
    ]

    # 并行执行过滤
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(_filter_single_stock, args_list))

    # 汇总结果
    filtered = []
    excluded_price = 0
    excluded_volume = 0
    excluded_data = 0

    for symbol, passed, reason in results:
        if passed:
            filtered.append(symbol)
        elif reason == "price":
            excluded_price += 1
        elif reason == "volume":
            excluded_volume += 1
        else:  # "data"
            excluded_data += 1

    total_excluded = excluded_price + excluded_volume + excluded_data
    log(
        f"Filtered: {len(filtered)} stocks passed "
        f"({total_excluded} excluded: {excluded_price} price, "
        f"{excluded_volume} volume, {excluded_data} data issues)"
    )

    return filtered


def compute_entry_date(
    data_dir: Path,
    scan_date: date,
    lookback_days: int,
    sample_files: Optional[List[Path]] = None,
) -> date:
    """
    计算检测窗口入口日

    从 scan_date 往前回溯 lookback_days 个交易日。

    Args:
        data_dir: 数据目录
        scan_date: 扫描截止日期
        lookback_days: 回溯天数
        sample_files: 采样文件列表（用于获取交易日历）

    Returns:
        入口日日期
    """
    if sample_files is None:
        sample_files = list(data_dir.glob("*.pkl"))[:10]

    # 从采样文件中获取交易日历
    for pkl_file in sample_files:
        try:
            df = pd.read_pickle(pkl_file)
            if df is not None and len(df) > lookback_days:
                trading_days = df.index

                # 定位 scan_date
                scan_ts = pd.Timestamp(scan_date)
                if scan_ts > trading_days.max():
                    # 数据不包含 scan_date，跳过该文件尝试下一个
                    continue

                mask = trading_days <= scan_ts
                if not mask.any():
                    continue
                scan_idx = mask.sum() - 1

                # 回溯 lookback_days
                entry_idx = max(0, scan_idx - lookback_days)
                return trading_days[entry_idx].date()

        except Exception:
            continue

    # 如果无法从数据计算，简单回溯（假设每月 21 个交易日）
    from datetime import timedelta
    calendar_days = int(lookback_days * 365 / 252)
    return scan_date - timedelta(days=calendar_days)
