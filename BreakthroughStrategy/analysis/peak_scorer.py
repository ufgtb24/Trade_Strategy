"""
峰值质量评分模块（加权模型）

峰值评分公式：
    总分 = volume_score × volume_weight + candle_score × candle_weight

评分因素：
- 放量（60%）：volume_surge_ratio - 使用对数映射（边际效益递减）
- 长K线（40%）：candle_change_pct - 使用线性映射

设计理念：
1. 峰值质量反映筹码堆积程度
2. 高放量、大K线的峰值具有更强的阻力意义
3. 与 BreakthroughScorer 的 Bonus 乘法模型分离
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .breakthrough_detector import Peak
    from .breakthrough_scorer import ScoreBreakdown


# =============================================================================
# 评分分解数据类
# =============================================================================

@dataclass
class FeatureScoreDetail:
    """单个特征的评分详情（加权模型用）"""
    name: str           # 显示名称
    raw_value: float    # 原始数值
    unit: str           # 单位 ('x', '%', 'd', 'pks', '')
    score: float        # 分数 (0-100)
    weight: float       # 权重 (0-1)
    # 子因素（用于展开显示）
    sub_features: List['FeatureScoreDetail'] = field(default_factory=list)


class PeakScorer:
    """峰值质量评分器（加权模型）"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化峰值评分器

        Args:
            config: 配置参数字典，包含评分权重
        """
        if config is None:
            config = {}

        # 峰值评分权重（筹码堆积因子：volume + candle）
        self.peak_weights = {
            'volume': config.get('peak_weight_volume', 0.60),
            'candle': config.get('peak_weight_candle', 0.40),
        }

    def score_peak(self, peak: 'Peak') -> float:
        """
        评估峰值质量

        将分数写入 peak.quality_score

        Args:
            peak: 峰值对象

        Returns:
            质量分数（0-100）
        """
        breakdown = self.get_peak_score_breakdown(peak)
        peak.quality_score = breakdown.total_score
        return breakdown.total_score

    def score_peaks_batch(self, peaks: List['Peak']) -> List['Peak']:
        """
        批量评分峰值

        Args:
            peaks: 峰值列表

        Returns:
            评分后的峰值列表（原列表，in-place 修改）
        """
        for peak in peaks:
            self.score_peak(peak)

        return peaks

    def get_peak_score_breakdown(self, peak: 'Peak') -> 'ScoreBreakdown':
        """
        获取峰值评分的详细分解

        Args:
            peak: 峰值对象

        Returns:
            ScoreBreakdown 包含各特征的详细评分
        """
        # 避免循环导入
        from .breakthrough_scorer import ScoreBreakdown

        features = []

        # 1. 放量评分（对数函数，边际效益递减）
        volume_score = self._log_score(
            peak.volume_surge_ratio, 1.0, 10.0, 0, 100
        )
        features.append(FeatureScoreDetail(
            name="Volume Surge",
            raw_value=peak.volume_surge_ratio,
            unit="x",
            score=volume_score,
            weight=self.peak_weights['volume']
        ))

        # 2. K线涨跌幅评分
        candle_score = self._linear_score(
            abs(peak.candle_change_pct), 0.03, 0.20, 0, 100
        )
        features.append(FeatureScoreDetail(
            name="Candle Change",
            raw_value=abs(peak.candle_change_pct) * 100,  # 转为百分比
            unit="%",
            score=candle_score,
            weight=self.peak_weights['candle']
        ))

        # 计算总分
        total_score = sum(f.score * f.weight for f in features)

        return ScoreBreakdown(
            entity_type='peak',
            entity_id=peak.id,
            total_score=total_score,
            features=features
        )

    # =========================================================================
    # 评分辅助方法
    # =========================================================================

    @staticmethod
    def _linear_score(
        value: float,
        low_value: float,
        high_value: float,
        min_score: float = 0,
        max_score: float = 100
    ) -> float:
        """
        线性映射评分

        将 value 线性映射到 [min_score, max_score] 范围

        Args:
            value: 待评分的值
            low_value: 对应 min_score 的值
            high_value: 对应 max_score 的值
            min_score: 最低分数（默认 0）
            max_score: 最高分数（默认 100）

        Returns:
            评分结果（限制在 [min_score, max_score] 范围内）
        """
        if high_value <= low_value:
            return min_score

        # 线性映射
        ratio = (value - low_value) / (high_value - low_value)
        score = min_score + ratio * (max_score - min_score)

        # 限制在 [min_score, max_score] 范围内
        score = max(min_score, min(max_score, score))

        return score

    @staticmethod
    def _log_score(
        value: float,
        base_value: float = 1.0,
        saturation_value: float = 10.0,
        min_score: float = 0,
        max_score: float = 100
    ) -> float:
        """
        对数映射评分（边际效益递减）

        使用对数函数实现边际效益递减：
        - 1x → 2x 的增益 等于 2x → 4x 的增益
        - 符合成交量的对数正态分布特性
        - 抗极端值（超大放量评分趋于饱和）

        Args:
            value: 待评分的值（如放量倍数）
            base_value: 基准值，低于此值得 0 分（默认 1.0，正常量）
            saturation_value: 饱和值，达到此值得满分（默认 10.0）
            min_score: 最低分数（默认 0）
            max_score: 最高分数（默认 100）

        Returns:
            评分结果（限制在 [min_score, max_score] 范围内）

        Example:
            _log_score(2.0, 1.0, 10.0) ≈ 30  # 2 倍量
            _log_score(4.0, 1.0, 10.0) ≈ 60  # 4 倍量（翻倍才等值增益）
            _log_score(8.0, 1.0, 10.0) ≈ 90  # 8 倍量
        """
        if value <= base_value:
            return min_score

        if saturation_value <= base_value:
            return min_score

        # 对数映射: log(value/base) / log(saturation/base)
        log_value = math.log(value / base_value)
        log_saturation = math.log(saturation_value / base_value)
        ratio = log_value / log_saturation

        # 映射到分数范围
        score = min_score + ratio * (max_score - min_score)

        # 限制在 [min_score, max_score] 范围内
        score = max(min_score, min(max_score, score))

        return score
