"""
技术指标模块

提供常用技术指标的计算功能，优先使用pandas-ta库（如果可用），
否则使用自实现的简单版本。
"""

import pandas as pd
import numpy as np
from typing import Optional


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
        计算RSI指标（Relative Strength Index）

        优先使用pandas-ta库，如果未安装则使用自实现版本

        Args:
            close: 收盘价序列
            period: RSI周期（默认14）

        Returns:
            RSI值序列（0-100）
        """
        try:
            # 尝试使用pandas-ta
            import pandas_ta as ta
            return ta.rsi(close, length=period)
        except ImportError:
            # Fallback：自实现RSI
            delta = close.diff()

            # 分离涨跌
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            # 计算平均涨跌幅
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()

            # 计算RS和RSI
            rs = avg_gain / avg_loss
            rsi = 100 - 100 / (1 + rs)

            return rsi

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
