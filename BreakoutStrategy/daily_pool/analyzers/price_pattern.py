"""
价格模式分析器

负责分析价格走势中的关键模式:
- 回调深度
- 支撑位检测
- 企稳区间计算
"""
from datetime import date
from typing import List, Optional, Tuple, TYPE_CHECKING

import numpy as np
import pandas as pd

from ..config import PricePatternConfig
from .results import SupportZone, ConsolidationRange, PricePatternResult

if TYPE_CHECKING:
    from ..models import DailyPoolEntry


class PricePatternAnalyzer:
    """
    价格模式分析器

    职责:
    - 检测回调深度
    - 识别支撑位
    - 计算企稳区间

    算法说明:
    - 支撑位检测: 局部最低点聚类 -> 过滤触及次数 -> 计算强度
    - 企稳区间: 近N日收盘价的 mean ± 1.5*std
    """

    def __init__(self, config: PricePatternConfig):
        """
        初始化分析器

        Args:
            config: 价格模式配置
        """
        self.config = config

    def analyze(self, df: pd.DataFrame, entry: 'DailyPoolEntry',
                as_of_date: date) -> PricePatternResult:
        """
        分析价格模式

        Args:
            df: 包含 OHLCV 的 DataFrame，索引为日期，已截止到 as_of_date
            entry: 池条目（包含 initial_atr, post_breakout_high 等）
            as_of_date: 分析日期

        Returns:
            PricePatternResult
        """
        if len(df) == 0:
            return self._empty_result()

        # 回调深度
        pullback_depth = self._calculate_pullback_depth(df, entry)

        # 支撑位检测
        support_zones = self._detect_support_zones(df, entry.initial_atr)

        # 企稳区间
        consolidation_range = self._calculate_consolidation_range(
            df, entry.initial_atr
        )

        # 价格位置
        current_price = df['close'].iloc[-1]
        price_position = self._determine_price_position(
            current_price, consolidation_range
        )

        return PricePatternResult(
            pullback_depth_atr=pullback_depth,
            support_zones=support_zones,
            consolidation_range=consolidation_range,
            price_position=price_position,
            strongest_support=support_zones[0] if support_zones else None
        )

    def _calculate_pullback_depth(self, df: pd.DataFrame,
                                  entry: 'DailyPoolEntry') -> float:
        """
        计算从突破后高点的回调深度（ATR单位）

        Args:
            df: 价格数据
            entry: 池条目

        Returns:
            回调深度（ATR单位）
        """
        current_price = df['close'].iloc[-1]
        high_price = entry.post_breakout_high

        if high_price <= 0:
            # 使用 DataFrame 中的最高价
            high_price = df['high'].max()

        drop = high_price - current_price
        if entry.initial_atr > 0:
            return drop / entry.initial_atr
        return 0.0

    def _detect_support_zones(self, df: pd.DataFrame,
                              atr: float) -> List[SupportZone]:
        """
        检测支撑区域

        算法:
        1. 找局部最低点 (low[i] < low[i-w:i+w])
        2. 按价格聚类（容差 = touch_tolerance_atr * ATR）
        3. 过滤: 测试次数 >= min_touches
        4. 计算强度

        Args:
            df: 价格数据
            atr: ATR值

        Returns:
            支撑区域列表（按强度降序排列）
        """
        if len(df) < 2 * self.config.local_min_window + 1:
            return []

        lows = df['low'].values
        dates = df.index.tolist()
        tolerance = self.config.touch_tolerance_atr * atr
        window = self.config.local_min_window

        # Step 1: 找局部最低点
        local_mins: List[Tuple[date, float]] = []
        for i in range(window, len(lows) - window):
            window_slice = lows[max(0, i - window): i + window + 1]
            if lows[i] == min(window_slice):
                local_mins.append((dates[i], lows[i]))

        if not local_mins:
            return []

        # Step 2: 按价格聚类
        clusters = self._cluster_by_price(local_mins, tolerance)

        # Step 3 & 4: 过滤并构建 SupportZone
        zones = []
        for cluster in clusters:
            if len(cluster) >= self.config.min_touches:
                prices = [p for _, p in cluster]
                dates_in_cluster = [d for d, _ in cluster]

                strength = self._calculate_support_strength(cluster)

                # 转换日期类型
                first_date = dates_in_cluster[0]
                last_date = dates_in_cluster[-1]
                if isinstance(first_date, pd.Timestamp):
                    first_date = first_date.date()
                if isinstance(last_date, pd.Timestamp):
                    last_date = last_date.date()

                zones.append(SupportZone(
                    price_low=min(prices),
                    price_high=max(prices),
                    test_count=len(cluster),
                    strength=strength,
                    first_test_date=min(dates_in_cluster).date() if hasattr(min(dates_in_cluster), 'date') else min(dates_in_cluster),
                    last_test_date=max(dates_in_cluster).date() if hasattr(max(dates_in_cluster), 'date') else max(dates_in_cluster),
                ))

        return sorted(zones, key=lambda z: z.strength, reverse=True)

    def _cluster_by_price(self, points: List[Tuple], tolerance: float) -> List[List]:
        """
        按价格聚类

        Args:
            points: (date, price) 元组列表
            tolerance: 聚类容差

        Returns:
            聚类列表
        """
        if not points:
            return []

        sorted_points = sorted(points, key=lambda x: x[1])
        clusters: List[List] = [[sorted_points[0]]]

        for point in sorted_points[1:]:
            if point[1] - clusters[-1][-1][1] <= tolerance:
                clusters[-1].append(point)
            else:
                clusters.append([point])

        return clusters

    def _calculate_support_strength(self, cluster: List[Tuple]) -> float:
        """
        计算支撑强度

        公式: strength = 0.4 * (测试次数/5) + 0.3 * (时间跨度/15天) + 0.3 * 反弹质量

        Args:
            cluster: 同一支撑位的触及点列表

        Returns:
            强度值 (0-1)
        """
        # 测试次数分数
        count_score = min(len(cluster) / 5, 1.0) * 0.4

        # 时间跨度分数
        dates = [d for d, _ in cluster]
        if len(dates) > 1:
            first = min(dates)
            last = max(dates)
            if hasattr(first, 'date'):
                first = first.date()
            if hasattr(last, 'date'):
                last = last.date()
            span_days = (last - first).days
            span_score = min(span_days / 15, 1.0) * 0.3
        else:
            span_score = 0.0

        # 反弹质量分数（简化：假设反弹质量良好）
        bounce_score = 0.3

        return count_score + span_score + bounce_score

    def _calculate_consolidation_range(self, df: pd.DataFrame,
                                       atr: float) -> Optional[ConsolidationRange]:
        """
        计算企稳区间

        区间 = mean ± 1.5 * std
        有效性: 宽度 <= max_width_atr

        Args:
            df: 价格数据
            atr: ATR值

        Returns:
            ConsolidationRange 或 None
        """
        if len(df) < self.config.consolidation_window:
            return None

        closes = df.tail(self.config.consolidation_window)['close'].values

        mean_price = float(np.mean(closes))
        std_price = float(np.std(closes))

        upper = mean_price + 1.5 * std_price
        lower = mean_price - 1.5 * std_price

        width_atr = (upper - lower) / atr if atr > 0 else float('inf')
        is_valid = width_atr <= self.config.max_width_atr

        return ConsolidationRange(
            upper_bound=upper,
            lower_bound=lower,
            center=mean_price,
            width_atr=width_atr,
            is_valid=is_valid
        )

    def _determine_price_position(self, current_price: float,
                                  consolidation: Optional[ConsolidationRange]) -> str:
        """
        判断当前价格相对于企稳区间的位置

        Args:
            current_price: 当前价格
            consolidation: 企稳区间

        Returns:
            位置字符串
        """
        if consolidation is None:
            return "unknown"

        if current_price > consolidation.upper_bound:
            return "above_range"
        elif current_price < consolidation.lower_bound:
            return "below_range"
        else:
            return "in_range"

    def _empty_result(self) -> PricePatternResult:
        """返回空结果"""
        return PricePatternResult(
            pullback_depth_atr=0.0,
            support_zones=[],
            consolidation_range=None,
            price_position="unknown",
            strongest_support=None
        )
