"""
时间窗口评估器

评估当前时间是否处于最佳买入窗口：
- 最佳窗口：10:00-11:30 AM ET
- 可接受窗口：10:00-15:00 (非最佳时段)
- 避开时段：开盘30分钟、尾盘、盘后/盘前

回测模式下默认返回满分，因为回测使用日K数据无法精确判断盘中时间。
"""
from datetime import time
from typing import Any, Dict, Optional, TYPE_CHECKING

import pandas as pd

from ..base import BaseEvaluator
from ..config import TimeWindowConfig
from ..result import DimensionScore

if TYPE_CHECKING:
    from ...pool_entry import PoolEntry
    from ...interfaces import ITimeProvider


class TimeWindowEvaluator(BaseEvaluator):
    """
    时间窗口评估器

    根据当前时间评估买入时机的合适程度。

    评分逻辑：
    - 最佳窗口 (10:00-11:30)：100分
    - 可接受时段 (其他常规时间)：70分
    - 边际时段 (尾盘)：40分
    - 避开时段 (开盘30分钟/盘后/盘前)：0分

    回测模式：
    - 无法精确判断盘中时间，默认返回100分
    """

    def __init__(self, config: TimeWindowConfig, scoring_weight: float = 0.20):
        """
        初始化时间窗口评估器

        Args:
            config: 时间窗口配置
            scoring_weight: 评分权重 (默认 0.20)
        """
        self.config = config
        self.weight = scoring_weight

    @property
    def dimension_name(self) -> str:
        return 'time_window'

    def evaluate(
        self,
        entry: 'PoolEntry',
        current_bar: pd.Series,
        time_provider: 'ITimeProvider',
        context: Optional[Dict[str, Any]] = None
    ) -> DimensionScore:
        """
        评估时间窗口

        Args:
            entry: 观察池条目
            current_bar: 当前价格数据
            time_provider: 时间提供者
            context: 额外上下文

        Returns:
            时间窗口维度评分
        """
        # 回测模式：跳过时间窗口检查，默认最优
        if time_provider.is_backtest_mode():
            return self._create_score(
                score=100,
                weight=self.weight,
                passed=True,
                period='backtest',
                note='Backtest mode - optimal window assumed'
            )

        # 获取当前时间
        current_time = time_provider.get_current_datetime().time()

        # 判断时段类型
        period = self._classify_time_period(current_time)

        # 计算评分
        score = self._calculate_score(period)

        # 判断是否通过 (avoid 时段不通过)
        passed = (period != 'avoid')

        return self._create_score(
            score=score,
            weight=self.weight,
            passed=passed,
            current_time=str(current_time),
            period=period,
            optimal_windows=[
                (str(w[0]), str(w[1])) for w in self.config.optimal_windows
            ]
        )

    def _classify_time_period(self, t: time) -> str:
        """
        分类时间段

        Args:
            t: 当前时间 (ET时区)

        Returns:
            时段类型: 'optimal' | 'acceptable' | 'marginal' | 'avoid' | 'premarket' | 'afterhours'
        """
        hour = t.hour
        minute = t.minute

        # 盘前 4:00-9:30
        if hour < 9 or (hour == 9 and minute < 30):
            if hour >= 4:
                return 'premarket' if self.config.allow_extended_hours else 'avoid'
            return 'avoid'

        # 开盘避让期 9:30 - 10:00 (或配置的避让时间)
        open_time = time(9, 30)
        avoid_until = time(
            9 + (30 + self.config.open_avoid_minutes) // 60,
            (30 + self.config.open_avoid_minutes) % 60
        )
        if open_time <= t < avoid_until:
            return 'avoid'

        # 检查最优窗口
        for start, end in self.config.optimal_windows:
            if start <= t <= end:
                return 'optimal'

        # 盘后 16:00-20:00
        if hour >= 16 and hour < 20:
            return 'afterhours' if self.config.allow_extended_hours else 'avoid'

        # 收盘后
        if hour >= 20:
            return 'avoid'

        # 尾盘 15:00-16:00
        if hour == 15:
            return 'marginal'

        # 其他常规交易时间
        if hour >= 10 and hour < 15:
            return 'acceptable'

        return 'avoid'

    def _calculate_score(self, period: str) -> float:
        """
        计算时间窗口评分

        Args:
            period: 时段类型

        Returns:
            评分 (0-100)
        """
        # 从配置获取评分映射
        score_map = self.config.window_scores

        # 获取评分因子 (0-1)
        if period in score_map:
            factor = score_map[period]
        elif period in ('premarket', 'afterhours'):
            # 盘后/盘前如果允许，使用 marginal 评分
            factor = score_map.get('marginal', 0.4) if self.config.allow_extended_hours else 0.0
        else:
            factor = 0.0

        return factor * 100
