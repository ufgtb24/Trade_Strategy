"""
买入条件评估器接口

定义评估器的抽象基类，所有维度评估器需实现此接口。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING

import pandas as pd

from .result import DimensionScore

if TYPE_CHECKING:
    from ..pool_entry import PoolEntry
    from ..interfaces import ITimeProvider


class IBuyConditionEvaluator(ABC):
    """
    买入条件评估器接口

    每个具体评估器负责评估一个维度（时间窗口/价格确认/成交量/风险过滤），
    返回该维度的评分结果。

    设计原则：
    - 单一职责：每个评估器只关注一个维度
    - 可配置：通过配置类控制评估参数
    - 可测试：每个评估器可独立单元测试
    """

    @property
    @abstractmethod
    def dimension_name(self) -> str:
        """
        评估维度名称

        Returns:
            维度标识符，如 'time_window', 'price_confirm', 'volume_verify', 'risk_filter'
        """
        pass

    @abstractmethod
    def evaluate(
        self,
        entry: 'PoolEntry',
        current_bar: pd.Series,
        time_provider: 'ITimeProvider',
        context: Optional[Dict[str, Any]] = None
    ) -> DimensionScore:
        """
        评估单个维度

        Args:
            entry: 观察池条目，包含突破信息和状态
            current_bar: 当前价格数据 (包含 open, high, low, close, volume)
            time_provider: 时间提供者，用于获取当前时间和日期
            context: 额外上下文信息，如：
                - minute_bars: 分钟级K线数据 (实时模式)
                - volume_ma20: 20日成交量均值
                - prev_close: 前日收盘价

        Returns:
            DimensionScore 评分结果，包含：
            - dimension: 维度名称
            - score: 评分 (0-100)
            - weight: 权重
            - details: 详细信息
            - passed: 是否通过门槛条件
        """
        pass

    def get_default_weight(self) -> float:
        """
        获取默认权重

        可被子类覆盖以提供自定义默认权重。

        Returns:
            默认权重值 (0-1)
        """
        return 0.25


class BaseEvaluator(IBuyConditionEvaluator):
    """
    评估器基类

    提供通用的辅助方法，减少子类重复代码。
    """

    def _safe_get_price(self, bar: pd.Series, key: str, default: float = 0.0) -> float:
        """安全获取价格字段"""
        try:
            value = bar.get(key, default)
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    def _calculate_margin(self, current_price: float, reference_price: float) -> float:
        """
        计算价格偏离比例

        Args:
            current_price: 当前价格
            reference_price: 参考价格

        Returns:
            偏离比例，正数表示高于参考价，负数表示低于
        """
        if reference_price <= 0:
            return 0.0
        return (current_price - reference_price) / reference_price

    def _create_score(
        self,
        score: float,
        weight: float,
        passed: bool = True,
        **details
    ) -> DimensionScore:
        """
        创建评分结果

        Args:
            score: 评分 (0-100)
            weight: 权重
            passed: 是否通过门槛
            **details: 额外详情

        Returns:
            DimensionScore 实例
        """
        return DimensionScore(
            dimension=self.dimension_name,
            score=max(0, min(100, score)),  # 限制在 0-100
            weight=weight,
            details=details,
            passed=passed
        )

    def _create_fail_score(self, reason: str, weight: float = 0.0, **details) -> DimensionScore:
        """
        创建失败评分 (评分为0，passed=False)

        Args:
            reason: 失败原因
            weight: 权重
            **details: 额外详情

        Returns:
            DimensionScore 实例
        """
        return DimensionScore(
            dimension=self.dimension_name,
            score=0,
            weight=weight,
            details={'reason': reason, **details},
            passed=False
        )
