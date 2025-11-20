"""可视化辅助工具"""
import pandas as pd
from datetime import datetime
from typing import Optional


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
