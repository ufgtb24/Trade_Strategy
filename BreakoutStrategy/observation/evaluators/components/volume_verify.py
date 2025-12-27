"""
成交量验证评估器

评估当前成交量是否支持突破的有效性：
- 成交量比 >= 1.5 倍基准：满分
- 成交量比 1.0-1.5 倍：部分分数
- 成交量比 < 1.0：低分

回测模式下使用日K成交量相对于MA20进行评估。
实时模式下使用5分钟成交量相对于同时段历史均值评估。
"""
from typing import Any, Dict, Optional, TYPE_CHECKING

import pandas as pd

from ..base import BaseEvaluator
from ..config import VolumeVerifyConfig
from ..result import DimensionScore

if TYPE_CHECKING:
    from ...pool_entry import PoolEntry
    from ...interfaces import ITimeProvider


class VolumeVerifyEvaluator(BaseEvaluator):
    """
    成交量验证评估器

    评估当前成交量是否足够支持突破的有效性。

    评分逻辑：
    - 量比 >= 1.5：100分（强放量）
    - 量比 1.2-1.5：80-100分（温和放量）
    - 量比 1.0-1.2：50-80分（正常量能）
    - 量比 < 1.0：0-50分（缩量）

    回测模式：
    - 使用日K成交量 / MA20 作为量比
    - 如果无基准数据，返回默认中等分数 (70分)

    实时模式：
    - 使用5分钟成交量 / 同时段历史均值
    """

    def __init__(self, config: VolumeVerifyConfig, scoring_weight: float = 0.25):
        """
        初始化成交量验证评估器

        Args:
            config: 成交量验证配置
            scoring_weight: 评分权重 (默认 0.25)
        """
        self.config = config
        self.weight = scoring_weight

    @property
    def dimension_name(self) -> str:
        return 'volume_verify'

    def evaluate(
        self,
        entry: 'PoolEntry',
        current_bar: pd.Series,
        time_provider: 'ITimeProvider',
        context: Optional[Dict[str, Any]] = None
    ) -> DimensionScore:
        """
        评估成交量验证

        Args:
            entry: 观察池条目
            current_bar: 当前价格数据
            time_provider: 时间提供者
            context: 额外上下文，可能包含：
                - volume_ma20: 20日成交量均值
                - minute_volume_avg: 分钟级成交量基准

        Returns:
            成交量验证维度评分
        """
        context = context or {}

        # 获取当前成交量
        current_volume = self._safe_get_price(current_bar, 'volume')

        # 获取基准成交量
        baseline_volume = self._get_baseline_volume(entry, current_bar, context)

        # 如果无法获取有效的成交量数据
        if baseline_volume <= 0:
            return self._create_score(
                score=70,  # 默认中等分数
                weight=self.weight,
                passed=True,
                note='No baseline volume available, using default score',
                current_volume=current_volume,
                baseline_volume=0,
                volume_ratio=0
            )

        # 计算量比
        volume_ratio = current_volume / baseline_volume

        # 计算评分
        score = self._calculate_score(volume_ratio)

        return self._create_score(
            score=score,
            weight=self.weight,
            passed=True,
            current_volume=current_volume,
            baseline_volume=baseline_volume,
            volume_ratio=volume_ratio,
            min_ratio_threshold=self.config.min_volume_ratio,
            baseline_type=self.config.baseline_type
        )

    def _get_baseline_volume(
        self,
        entry: 'PoolEntry',
        current_bar: pd.Series,
        context: Dict[str, Any]
    ) -> float:
        """
        获取基准成交量

        优先级：
        1. context 中的 volume_ma20 或 minute_volume_avg
        2. entry 中缓存的 baseline_volume
        3. current_bar 中的成交量（作为备选）

        Args:
            entry: 观察池条目
            current_bar: 当前K线数据
            context: 上下文数据

        Returns:
            基准成交量
        """
        # 从上下文获取
        if self.config.baseline_type == 'ma20':
            if 'volume_ma20' in context:
                return float(context['volume_ma20'])
        elif self.config.baseline_type == 'prev_day_avg':
            if 'prev_day_volume' in context:
                return float(context['prev_day_volume'])

        # 通用基准
        if 'baseline_volume' in context:
            return float(context['baseline_volume'])

        # 从 entry 获取缓存的基准
        baseline = getattr(entry, 'baseline_volume', 0)
        if baseline and baseline > 0:
            return float(baseline)

        # 如果都没有，返回0表示无基准
        return 0

    def _calculate_score(self, ratio: float) -> float:
        """
        计算成交量评分

        Args:
            ratio: 成交量比 (当前量 / 基准量)

        Returns:
            评分 (0-100)
        """
        min_ratio = self.config.min_volume_ratio  # 1.5

        if ratio < 0.5:
            # 极度缩量
            return 10

        elif ratio < 1.0:
            # 缩量：0.5-1.0 对应 10-50分
            return 10 + (ratio - 0.5) * 80

        elif ratio < 1.2:
            # 正常量能：1.0-1.2 对应 50-70分
            return 50 + (ratio - 1.0) * 100

        elif ratio < min_ratio:
            # 温和放量：1.2-1.5 对应 70-90分
            return 70 + (ratio - 1.2) / (min_ratio - 1.2) * 20

        elif ratio < 2.0:
            # 强放量：1.5-2.0 对应 90-100分
            return 90 + (ratio - min_ratio) / 0.5 * 10

        else:
            # 超强放量：>= 2.0 满分
            return 100
