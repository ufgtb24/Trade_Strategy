"""
特征计算模块

从BreakoutInfo（增量检测结果）计算完整的Breakthrough对象（包含丰富特征）
"""

import pandas as pd
from typing import Optional
from .breakthrough_detector import BreakoutInfo, Breakthrough


class FeatureCalculator:
    """特征计算器"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化特征计算器

        Args:
            config: 配置参数字典
        """
        if config is None:
            config = {}

        self.stability_lookforward = config.get('stability_lookforward', 10)
        self.continuity_lookback = config.get('continuity_lookback', 5)

    def enrich_breakthrough(self,
                           df: pd.DataFrame,
                           breakout_info: BreakoutInfo,
                           symbol: str) -> Breakthrough:
        """
        从BreakoutInfo计算完整特征

        Args:
            df: OHLCV数据
            breakout_info: 增量检测返回的突破信息
            symbol: 股票代码

        Returns:
            包含所有特征的Breakthrough对象
        """
        idx = breakout_info.current_index
        row = df.iloc[idx]

        # 计算突破类型
        breakthrough_type = self._classify_type(row)

        # 计算涨跌幅
        if row['open'] > 0:
            price_change_pct = (row['close'] - row['open']) / row['open']
        else:
            price_change_pct = 0.0

        # 计算跳空
        if idx > 0:
            prev_close = df['close'].iloc[idx - 1]
            gap_up = row['open'] > prev_close
            gap_up_pct = (row['open'] - prev_close) / prev_close if prev_close > 0 and gap_up else 0.0
        else:
            gap_up = False
            gap_up_pct = 0.0

        # 计算放量倍数
        volume_surge_ratio = self._calculate_volume_ratio(df, idx)

        # 计算连续性
        continuity_days = self._calculate_continuity(df, idx)

        # 计算稳定性
        highest_peak = breakout_info.highest_peak_broken
        stability_score = self._calculate_stability(df, idx, highest_peak.price)

        return Breakthrough(
            symbol=symbol,
            date=breakout_info.current_date,
            price=breakout_info.current_price,
            index=idx,
            broken_peaks=breakout_info.broken_peaks,
            breakthrough_type=breakthrough_type,
            price_change_pct=price_change_pct,
            gap_up=gap_up,
            gap_up_pct=gap_up_pct,
            volume_surge_ratio=volume_surge_ratio,
            continuity_days=continuity_days,
            stability_score=stability_score
        )

    def _classify_type(self, row: pd.Series) -> str:
        """
        分类突破类型

        - 阳线突破：收盘价 > 开盘价
        - 阴线突破：收盘价 < 开盘价
        - 上影线突破：收盘价 ≈ 开盘价（差异<1%）

        Args:
            row: 突破日的行情数据

        Returns:
            突破类型：'yang', 'yin', 'shadow'
        """
        open_price = row['open']
        close_price = row['close']

        if open_price == 0:
            return 'shadow'

        change_ratio = abs((close_price - open_price) / open_price)

        if change_ratio < 0.01:  # 收盘价与开盘价差异<1%
            return 'shadow'
        elif close_price > open_price:
            return 'yang'
        else:
            return 'yin'

    def _calculate_volume_ratio(self, df: pd.DataFrame, index: int) -> float:
        """
        计算放量倍数

        Args:
            df: 行情数据
            index: 突破点索引

        Returns:
            放量倍数
        """
        window_start = max(0, index - 63)
        avg_volume = df['volume'].iloc[window_start:index].mean()

        if avg_volume > 0:
            return df['volume'].iloc[index] / avg_volume
        else:
            return 1.0

    def _calculate_continuity(self, df: pd.DataFrame, index: int) -> int:
        """
        计算连续上涨天数

        从突破日向前查找，统计连续收阳线的天数

        Args:
            df: 行情数据
            index: 突破点索引

        Returns:
            连续上涨天数
        """
        continuity_days = 0

        for i in range(index, max(0, index - self.continuity_lookback), -1):
            row = df.iloc[i]
            if row['close'] > row['open']:
                continuity_days += 1
            else:
                break

        return continuity_days

    def _calculate_stability(self,
                            df: pd.DataFrame,
                            index: int,
                            peak_price: float) -> float:
        """
        计算稳定性分数

        稳定性定义：突破后N天内，价格不跌破最高峰值价格的比例

        Args:
            df: 行情数据
            index: 突破点索引
            peak_price: 最高峰值价格

        Returns:
            稳定性分数（0-100）
        """
        # 向后查看stability_lookforward天
        lookforward_end = min(len(df), index + self.stability_lookforward + 1)
        future_data = df.iloc[index + 1:lookforward_end]

        if len(future_data) == 0:
            # 无未来数据，无法评估稳定性
            return 50.0  # 返回中性分数

        # 统计价格不跌破峰值的天数
        stable_days = (future_data['low'] >= peak_price).sum()
        total_days = len(future_data)

        stability_score = (stable_days / total_days) * 100 if total_days > 0 else 50.0

        return stability_score
