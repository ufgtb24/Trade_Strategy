"""
Simple Pool 工具函数

提供 ATR 计算、成交量比率等核心指标计算。
"""
import pandas as pd
import numpy as np


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    计算 ATR (Average True Range)

    True Range = max(high-low, |high-prev_close|, |low-prev_close|)
    ATR = SMA(TR, period)

    Args:
        df: OHLCV DataFrame，需包含 high, low, close 列
        period: ATR 计算周期

    Returns:
        最新 ATR 值
    """
    if len(df) < period + 1:
        # 数据不足，返回简单的 high-low 均值
        return float((df['high'] - df['low']).mean())

    high = df['high']
    low = df['low']
    close = df['close']

    # True Range 三个组成部分
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    # 取最大值
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # SMA
    atr = tr.rolling(window=period).mean()

    return float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else float(tr.iloc[-1])


def calculate_atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算 ATR 序列

    Args:
        df: OHLCV DataFrame
        period: ATR 计算周期

    Returns:
        ATR 序列
    """
    high = df['high']
    low = df['low']
    close = df['close']

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return atr


def calculate_volume_ratio(df: pd.DataFrame, period: int = 20) -> float:
    """
    计算成交量相对于均量的比率

    Args:
        df: OHLCV DataFrame，需包含 volume 列
        period: 均量计算周期

    Returns:
        当前成交量 / MA(volume, period)
    """
    if len(df) < 2:
        return 1.0

    volume = df['volume']
    current_vol = float(volume.iloc[-1])

    if len(volume) >= period:
        baseline = float(volume.tail(period).mean())
    else:
        baseline = float(volume.mean())

    if baseline <= 0:
        return 1.0

    return current_vol / baseline


def calculate_price_ma(df: pd.DataFrame, period: int = 5) -> float:
    """
    计算收盘价均线

    Args:
        df: OHLCV DataFrame
        period: 均线周期

    Returns:
        MA 值
    """
    if len(df) < period:
        return float(df['close'].mean())
    return float(df['close'].tail(period).mean())


def get_recent_support(df: pd.DataFrame, lookback: int = 10) -> float:
    """
    获取近期支撑位 (近N天最低价)

    Args:
        df: OHLCV DataFrame
        lookback: 回看天数

    Returns:
        支撑价位
    """
    if len(df) == 0:
        return 0.0

    lookback = min(lookback, len(df))
    return float(df.tail(lookback)['low'].min())


def is_bullish_candle(df: pd.DataFrame) -> bool:
    """
    判断最新 K 线是否为阳线

    Args:
        df: OHLCV DataFrame

    Returns:
        True if close > open
    """
    if len(df) == 0:
        return False

    latest = df.iloc[-1]
    return float(latest['close']) > float(latest['open'])


def get_price_change(df: pd.DataFrame) -> float:
    """
    获取最新价格变化 (相对于前一日收盘)

    Args:
        df: OHLCV DataFrame

    Returns:
        价格变化 (正为上涨)
    """
    if len(df) < 2:
        return 0.0

    current_close = float(df.iloc[-1]['close'])
    prev_close = float(df.iloc[-2]['close'])

    return current_close - prev_close
