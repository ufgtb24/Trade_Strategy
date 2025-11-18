"""
质量评分模块（改进版）

核心改进：
1. 修复密集度加成：识别密集子集而非整体范围
2. 综合所有被突破峰值的质量评分

峰值质量评分因素（总分100）：
- 放量（25%）：volume_surge_ratio越大越好
- 长K线（20%）：candle_change_pct越大越好
- 压制时间（25%）：left_suppression_days + right_suppression_days越长越好
- 相对高度（15%）：relative_height越大越好
- 保留merged（15%）：向后兼容

突破质量评分因素（总分100）：
- 涨跌幅（20%）：price_change_pct越大越好
- 跳空（10%）：gap_up_pct越大越好
- 放量（20%）：volume_surge_ratio越大越好
- 连续性（15%）：continuity_days越多越好
- 稳定性（15%）：stability_score（突破后不跌破凸点）
- 阻力强度（20%）：综合指标（数量+密集度+质量）
"""

from typing import List, Optional, Tuple
from .breakthrough_detector import Peak, Breakthrough


class QualityScorer:
    """质量评分器（改进版）"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化质量评分器

        Args:
            config: 配置参数字典，包含评分权重和阈值
        """
        if config is None:
            config = {}

        # 峰值评分权重
        self.peak_weights = {
            'volume': config.get('peak_weight_volume', 0.25),
            'candle': config.get('peak_weight_candle', 0.20),
            'suppression': config.get('peak_weight_suppression', 0.25),
            'height': config.get('peak_weight_height', 0.15),
            'merged': config.get('peak_weight_merged', 0.15)  # 保留，向后兼容
        }

        # 突破评分权重
        self.breakthrough_weights = {
            'change': config.get('bt_weight_change', 0.20),
            'gap': config.get('bt_weight_gap', 0.10),
            'volume': config.get('bt_weight_volume', 0.20),
            'continuity': config.get('bt_weight_continuity', 0.15),
            'stability': config.get('bt_weight_stability', 0.15),
            'resistance': config.get('bt_weight_resistance', 0.20)  # 阻力强度
        }

        # 阻力强度评分的子权重
        self.resistance_weights = {
            'quantity': config.get('res_weight_quantity', 0.30),   # 峰值数量
            'density': config.get('res_weight_density', 0.30),     # 峰值密集度
            'quality': config.get('res_weight_quality', 0.40)      # 峰值质量
        }

    def score_peak(self, peak: Peak) -> float:
        """
        评估峰值质量

        将分数写入peak.quality_score

        Args:
            peak: 峰值对象

        Returns:
            质量分数（0-100）
        """
        # 1. 放量评分（2倍=50分，5倍=100分）
        volume_score = self._linear_score(
            peak.volume_surge_ratio,
            low_value=2.0,
            high_value=5.0,
            min_score=0,
            max_score=100
        )

        # 2. 长K线评分（5%=50分，10%=100分）
        candle_score = self._linear_score(
            abs(peak.candle_change_pct),
            low_value=0.05,
            high_value=0.10,
            min_score=0,
            max_score=100
        )

        # 3. 压制时间评分（30天=50分，60天=100分）
        suppression_days = peak.left_suppression_days + peak.right_suppression_days
        suppression_score = self._linear_score(
            suppression_days,
            low_value=30,
            high_value=60,
            min_score=0,
            max_score=100
        )

        # 4. 相对高度评分（5%=50分，10%=100分）
        height_score = self._linear_score(
            peak.relative_height,
            low_value=0.05,
            high_value=0.10,
            min_score=0,
            max_score=100
        )

        # 5. merged评分（保留，向后兼容，默认50分）
        merged_score = 50.0

        # 加权求和
        total_score = (
            volume_score * self.peak_weights['volume'] +
            candle_score * self.peak_weights['candle'] +
            suppression_score * self.peak_weights['suppression'] +
            height_score * self.peak_weights['height'] +
            merged_score * self.peak_weights['merged']
        )

        # 写入peak对象
        peak.quality_score = total_score

        return total_score

    def score_breakthrough(self, breakthrough: Breakthrough) -> float:
        """
        评估突破质量（改进版）

        将分数写入breakthrough.quality_score

        Args:
            breakthrough: 突破点对象

        Returns:
            质量分数（0-100）
        """
        # 1. 涨跌幅评分（3%=50分，6%=100分）
        change_score = self._linear_score(
            abs(breakthrough.price_change_pct),
            low_value=0.03,
            high_value=0.06,
            min_score=0,
            max_score=100
        )

        # 2. 跳空评分（1%=50分，2%=100分）
        gap_score = self._linear_score(
            breakthrough.gap_up_pct,
            low_value=0.01,
            high_value=0.02,
            min_score=0,
            max_score=100
        )

        # 3. 放量评分（2倍=50分，5倍=100分）
        volume_score = self._linear_score(
            breakthrough.volume_surge_ratio,
            low_value=2.0,
            high_value=5.0,
            min_score=0,
            max_score=100
        )

        # 4. 连续性评分（3天=50分，5天=100分）
        continuity_score = self._linear_score(
            breakthrough.continuity_days,
            low_value=3,
            high_value=5,
            min_score=0,
            max_score=100
        )

        # 5. 稳定性评分（已经是0-100分）
        stability_score = breakthrough.stability_score

        # 6. 阻力强度评分（改进版）
        resistance_score = self._score_resistance_strength(breakthrough)

        # 加权求和
        total_score = (
            change_score * self.breakthrough_weights['change'] +
            gap_score * self.breakthrough_weights['gap'] +
            volume_score * self.breakthrough_weights['volume'] +
            continuity_score * self.breakthrough_weights['continuity'] +
            stability_score * self.breakthrough_weights['stability'] +
            resistance_score * self.breakthrough_weights['resistance']
        )

        # 写入breakthrough对象
        breakthrough.quality_score = total_score

        return total_score

    def score_peaks_batch(self, peaks: List[Peak]) -> List[Peak]:
        """
        批量评分峰值

        Args:
            peaks: 峰值列表

        Returns:
            评分后的峰值列表（原列表）
        """
        for peak in peaks:
            self.score_peak(peak)

        return peaks

    def score_breakthroughs_batch(
        self,
        breakthroughs: List[Breakthrough]
    ) -> List[Breakthrough]:
        """
        批量评分突破点

        Args:
            breakthroughs: 突破点列表

        Returns:
            评分后的突破点列表（原列表）
        """
        for breakthrough in breakthroughs:
            self.score_breakthrough(breakthrough)

        return breakthroughs

    def _score_resistance_strength(self, breakthrough: Breakthrough) -> float:
        """
        阻力强度评分（改进版）

        综合考虑：
        1. 峰值数量（quantity）
        2. 峰值密集度（density）← 修复：识别密集子集
        3. 峰值质量（quality）← 新增：综合所有峰值质量
        """
        broken_peaks = breakthrough.broken_peaks
        num_peaks = len(broken_peaks)

        if num_peaks == 0:
            return 0.0

        if num_peaks == 1:
            # 单峰值：主要看峰值质量
            peak = broken_peaks[0]
            quality = peak.quality_score if peak.quality_score else 50.0
            return quality * 0.7 + 30 * 0.3

        # 1. 数量评分
        quantity_score = self._score_quantity(num_peaks)

        # 2. 密集度评分（改进：识别密集子集）
        density_score = self._score_density(broken_peaks)

        # 3. 质量评分（新增：综合峰值质量）
        quality_score = self._score_peak_quality_aggregate(broken_peaks)

        # 加权融合
        total = (
            quantity_score * self.resistance_weights['quantity'] +
            density_score * self.resistance_weights['density'] +
            quality_score * self.resistance_weights['quality']
        )

        return total

    def _score_quantity(self, num_peaks: int) -> float:
        """峰值数量评分"""
        return self._linear_score(num_peaks, 1, 5, 30, 80)

    def _score_density(self, broken_peaks: List[Peak]) -> float:
        """
        密集度评分（改进版）

        修复问题：识别最大密集子集，而非看整体范围

        示例：
        - [3.79, 3.81, 3.82]: 100%密集 → 高分
        - [3.6, 3.79, 3.81, 3.82, 3.9]: 有密集子集[3.79-3.82] → 高分
        - [3.0, 3.5, 4.0]: 完全分散 → 低分
        """
        prices = sorted([p.price for p in broken_peaks])
        n = len(prices)

        if n <= 1:
            return 50.0

        # 找到最大密集子集
        max_cluster_size, cluster_density = self._find_densest_cluster(prices)

        # 基础分：密集子集大小
        if max_cluster_size >= 3:
            size_score = 80
        elif max_cluster_size == 2:
            size_score = 60
        else:
            size_score = 40  # 无密集子集

        # 密集度加成
        if cluster_density < 0.01:  # < 1%
            density_bonus = 20
        elif cluster_density < 0.03:  # < 3%
            density_bonus = 10
        else:
            density_bonus = 0

        # 多样性加成（有密集区 + 分散峰值）
        if max_cluster_size >= 2 and n > max_cluster_size:
            diversity_bonus = 10
        else:
            diversity_bonus = 0

        total = min(100, size_score + density_bonus + diversity_bonus)
        return total

    def _find_densest_cluster(self,
                             prices: List[float],
                             density_threshold: float = 0.03) -> Tuple[int, float]:
        """
        找到最大的密集子集

        Args:
            prices: 排序后的价格列表
            density_threshold: 密集度阈值（默认3%）

        Returns:
            (最大簇大小, 簇内密集度)
        """
        n = len(prices)
        if n <= 1:
            return (n, 0.0)

        max_cluster_size = 1
        best_cluster_density = 999.0

        # 滑动窗口找密集子集
        for i in range(n):
            for j in range(i + 1, n):
                cluster = prices[i:j+1]
                cluster_range = cluster[-1] - cluster[0]
                cluster_avg = sum(cluster) / len(cluster)

                if cluster_avg == 0:
                    continue

                density = cluster_range / cluster_avg

                if density <= density_threshold:
                    # 这是一个密集子集
                    if len(cluster) > max_cluster_size:
                        max_cluster_size = len(cluster)
                        best_cluster_density = density
                    elif len(cluster) == max_cluster_size:
                        # 同样大小，选择更密集的
                        best_cluster_density = min(best_cluster_density, density)

        return (max_cluster_size, best_cluster_density)

    def _score_peak_quality_aggregate(self, broken_peaks: List[Peak]) -> float:
        """
        综合峰值质量评分（新增）

        考虑：
        1. 平均质量（主要）
        2. 最高质量（加成）
        3. 质量一致性（加成）
        """
        qualities = [p.quality_score for p in broken_peaks
                    if p.quality_score is not None]

        if not qualities:
            return 50.0  # 默认中等

        # 1. 平均质量
        avg_quality = sum(qualities) / len(qualities)
        base_score = avg_quality

        # 2. 最高质量加成
        max_quality = max(qualities)
        if max_quality >= 80:
            max_bonus = 10
        elif max_quality >= 70:
            max_bonus = 5
        else:
            max_bonus = 0

        # 3. 一致性加成（所有峰值都是高质量）
        min_quality = min(qualities)
        if min_quality >= 60 and len(qualities) >= 2:
            consistency_bonus = 10
        elif min_quality >= 50 and len(qualities) >= 3:
            consistency_bonus = 5
        else:
            consistency_bonus = 0

        total = min(100, base_score + max_bonus + consistency_bonus)
        return total

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

        将value线性映射到[min_score, max_score]范围

        Args:
            value: 待评分的值
            low_value: 对应min_score的值
            high_value: 对应max_score的值
            min_score: 最低分数（默认0）
            max_score: 最高分数（默认100）

        Returns:
            评分结果（限制在[min_score, max_score]范围内）
        """
        if high_value <= low_value:
            return min_score

        # 线性映射
        ratio = (value - low_value) / (high_value - low_value)
        score = min_score + ratio * (max_score - min_score)

        # 限制在[min_score, max_score]范围内
        score = max(min_score, min(max_score, score))

        return score
