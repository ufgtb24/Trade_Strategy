"""
特征计算模块

从BreakoutInfo（增量检测结果）计算完整的Breakthrough对象（包含丰富特征）
"""

from typing import Dict, List, Optional

import pandas as pd

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

        self.stability_lookforward = config.get("stability_lookforward", 10)
        self.continuity_lookback = config.get("continuity_lookback", 5)

        # 回测标签配置
        # 格式: [{"min_days": 5, "max_days": 20}, {"min_days": 3, "max_days": 10}]
        self.label_configs: List[Dict] = config.get("label_configs", [])

    def enrich_breakthrough(
        self, df: pd.DataFrame, breakout_info: BreakoutInfo, symbol: str, detector=None
    ) -> Breakthrough:
        """
        从BreakoutInfo计算完整特征

        Args:
            df: OHLCV数据
            breakout_info: 增量检测返回的突破信息
            symbol: 股票代码
            detector: BreakthroughDetector实例（可选，用于获取连续突破信息）

        Returns:
            包含所有特征的Breakthrough对象
        """
        idx = breakout_info.current_index
        row = df.iloc[idx]

        # 计算突破类型
        breakthrough_type = self._classify_type(row)

        # 计算涨跌幅
        if row["open"] > 0:
            price_change_pct = (row["close"] - row["open"]) / row["open"]
        else:
            price_change_pct = 0.0

        # 计算跳空
        if idx > 0:
            prev_close = df["close"].iloc[idx - 1]
            gap_up = row["open"] > prev_close
            gap_up_pct = (
                (row["open"] - prev_close) / prev_close
                if prev_close > 0 and gap_up
                else 0.0
            )
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

        # 计算回测标签
        labels = self._calculate_labels(df, idx)

        # 计算连续突破次数（PLAN A: Momentum）
        recent_breakthrough_count = 1
        if detector is not None:
            recent_breakthrough_count = detector.get_recent_breakthrough_count(idx)

        return Breakthrough(
            symbol=symbol,
            date=breakout_info.current_date,
            price=breakout_info.current_price,
            index=idx,
            broken_peaks=breakout_info.broken_peaks,
            superseded_peaks=breakout_info.superseded_peaks,
            breakthrough_type=breakthrough_type,
            price_change_pct=price_change_pct,
            gap_up=gap_up,
            gap_up_pct=gap_up_pct,
            volume_surge_ratio=volume_surge_ratio,
            continuity_days=continuity_days,
            stability_score=stability_score,
            labels=labels,
            recent_breakthrough_count=recent_breakthrough_count,
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
        open_price = row["open"]
        close_price = row["close"]

        if open_price == 0:
            return "shadow"

        change_ratio = abs((close_price - open_price) / open_price)

        if change_ratio < 0.01:  # 收盘价与开盘价差异<1%
            return "shadow"
        elif close_price > open_price:
            return "yang"
        else:
            return "yin"

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
        avg_volume = df["volume"].iloc[window_start:index].mean()

        if avg_volume > 0:
            return df["volume"].iloc[index] / avg_volume
        else:
            return 1.0

    def _calculate_continuity(self, df: pd.DataFrame, index: int) -> int:
        """
        计算连续上涨天数

        从突破日前一天向前查找，统计连续收阳线的天数
        注意：不包括突破日本身，因为突破日可能是阴线突破（靠上影线突破）

        Args:
            df: 行情数据
            index: 突破点索引

        Returns:
            连续上涨天数
        """
        continuity_days = 0

        # 从突破日前一天开始计算，避免阴线突破时直接返回0
        start_index = index - 1
        if start_index < 0:
            return 0

        for i in range(
            start_index, max(-1, start_index - self.continuity_lookback), -1
        ):
            row = df.iloc[i]
            # 视为上涨日的条件：收盘价 > 开盘价，或者收盘价 > 前一日收盘价
            is_bull = False
            if row["close"] > row["open"]:
                is_bull = True
            else:
                if i > 0:
                    prev_close = df["close"].iloc[i - 1]
                    if row["close"] > prev_close:
                        is_bull = True

            if is_bull:
                continuity_days += 1
            else:
                break

        return continuity_days

    def _calculate_stability(
        self, df: pd.DataFrame, index: int, peak_price: float
    ) -> float:
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
        future_data = df.iloc[index + 1 : lookforward_end]

        if len(future_data) == 0:
            # 无未来数据，无法评估稳定性
            return 50.0  # 返回中性分数

        # 统计价格不跌破峰值的天数
        stable_days = (future_data["low"] >= peak_price).sum()
        total_days = len(future_data)

        stability_score = (stable_days / total_days) * 100 if total_days > 0 else 50.0

        return stability_score

    def _calculate_labels(
        self, df: pd.DataFrame, index: int
    ) -> Dict[str, Optional[float]]:
        """
        计算回测标签

        标签定义：(最低点之后到N天内的最高价 - M天内最低价) / M天内最低价
        - M天内最低价：使用 close 价格
        - 最高价范围：从最低点出现日之后到N天内，使用 high 价格
        - M < N，均不包括突破当日

        Args:
            df: OHLCV数据
            index: 突破点索引

        Returns:
            标签字典，格式：{"label_5_20": 0.15, "label_3_10": None}
            数据不足时对应值为 None
        """
        labels = {}

        for config in self.label_configs:
            min_days = config.get("min_days", 5)  # M: 最低价窗口
            max_days = config.get("max_days", 20)  # N: 最高价窗口

            label_key = f"label_{min_days}_{max_days}"

            # 计算数据范围（不包括突破当日）
            min_end = min(len(df), index + min_days + 1)
            max_end = min(len(df), index + max_days + 1)

            future_min_data = df.iloc[index + 1 : min_end]  # M天内数据

            # 检查数据是否充足
            if len(future_min_data) < min_days or (max_end - index - 1) < max_days:
                labels[label_key] = None
                continue

            # 1. 在M天内找最低 close 及其位置
            min_close = future_min_data["close"].min()
            # argmin() 返回相对位置索引，加上起始位置得到在 df 中的绝对位置
            min_close_pos = index + 1 + future_min_data["close"].argmin()

            # 2. 从最低点之后到N天内找最高 high
            future_max_data = df.iloc[min_close_pos + 1 : max_end]

            if len(future_max_data) == 0:
                # 最低点在窗口末尾，没有后续数据计算最高价
                labels[label_key] = None
                continue

            max_high = future_max_data["high"].max()

            # 计算标签
            if min_close > 0:
                label_value = (max_high - min_close) / min_close
            else:
                label_value = None

            labels[label_key] = label_value

        return labels
