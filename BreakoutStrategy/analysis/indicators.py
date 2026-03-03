"""
技术指标模块

基于 pandas_ta 库提供常用技术指标的计算功能。
"""

import pandas as pd
import numpy as np

try:
    import pandas_ta as ta
except ImportError as e:
    raise ImportError(
        "pandas_ta 是计算技术指标的必需依赖。"
        "请使用以下命令安装: uv add pandas-ta>=0.3.14b"
    ) from e


class TechnicalIndicators:
    """技术指标计算器"""

    @staticmethod
    def calculate_ma(series: pd.Series, period: int = 20) -> pd.Series:
        """
        计算移动平均线（Moving Average）

        Args:
            series: 价格序列（通常是收盘价）
            period: 周期（默认20）

        Returns:
            移动平均线序列
        """
        return series.rolling(window=period).mean()

    @staticmethod
    def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """
        计算 RSI 指标（Relative Strength Index）

        Args:
            close: 收盘价序列
            period: RSI 周期（默认14）

        Returns:
            RSI 值序列（0-100）
        """
        return ta.rsi(close, length=period)

    @staticmethod
    def calculate_atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """
        计算 ATR（Average True Range）

        使用 Wilder's smoothing (RMA) 方法，与 TradingView 一致。

        Args:
            high: 最高价序列
            low: 最低价序列
            close: 收盘价序列
            period: ATR 周期（默认14）

        Returns:
            ATR 值序列
        """
        return ta.atr(high, low, close, length=period)

    @staticmethod
    def calculate_relative_volume(volume: pd.Series, period: int = 63) -> pd.Series:
        """
        计算相对成交量

        相对成交量 = 当前成交量 / 过去N天平均成交量

        Args:
            volume: 成交量序列
            period: 计算平均成交量的周期（默认63，约3个月）

        Returns:
            相对成交量序列
        """
        avg_volume = volume.rolling(window=period).mean()

        # 防止除零
        relative_volume = volume / avg_volume.replace(0, np.nan)

        return relative_volume

    @staticmethod
    def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        批量添加常用技术指标到DataFrame

        添加的指标：
        - ma_20: 20日移动平均线
        - ma_50: 50日移动平均线
        - rsi_14: 14日RSI
        - rv_63: 63日相对成交量

        Args:
            df: 包含close和volume列的DataFrame

        Returns:
            添加了指标列的DataFrame副本
        """
        df = df.copy()

        # 移动平均线
        df['ma_20'] = TechnicalIndicators.calculate_ma(df['close'], 20)
        df['ma_50'] = TechnicalIndicators.calculate_ma(df['close'], 50)

        # RSI
        df['rsi_14'] = TechnicalIndicators.calculate_rsi(df['close'], 14)

        # 相对成交量
        df['rv_63'] = TechnicalIndicators.calculate_relative_volume(df['volume'], 63)

        return df
