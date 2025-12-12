"""
质量评分模块（改进版）

核心改进：
1. 修复密集度加成：识别密集子集而非整体范围
2. 综合所有被突破峰值的质量评分

峰值质量评分因素（总分100）：
- 放量（30%）：volume_surge_ratio越大越好
- 长K线（20%）：candle_change_pct越大越好
- 压制时间（30%）：left_suppression_days + right_suppression_days越长越好
- 相对高度（20%）：relative_height越大越好

突破质量评分因素（总分100）：
- 涨跌幅（20%）：price_change_pct越大越好
- 跳空（10%）：gap_up_pct越大越好
- 放量（20%）：volume_surge_ratio越大越好
- 连续性（15%）：continuity_days越多越好
- 稳定性（15%）：stability_score（突破后不跌破凸点）
- 阻力强度（20%）：综合指标（数量+密集度+质量）
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from .breakthrough_detector import Peak, Breakthrough


# =============================================================================
# 评分分解数据类（用于浮动窗口显示）
# =============================================================================

@dataclass
class FeatureScoreDetail:
    """单个特征的评分详情"""
    name: str           # 显示名称
    raw_value: float    # 原始数值
    unit: str           # 单位 ('x', '%', 'd', 'pks', '')
    score: float        # 分数 (0-100)
    weight: float       # 权重 (0-1)
    # 子因素（用于 Resistance 展开显示）
    sub_features: List['FeatureScoreDetail'] = field(default_factory=list)


@dataclass
class ScoreBreakdown:
    """评分分解"""
    entity_type: str                      # 'peak' or 'breakthrough'
    entity_id: Optional[int]              # Peak ID (if peak)
    total_score: float                    # 总分
    features: List[FeatureScoreDetail]    # 各特征详情
    broken_peak_ids: Optional[List[int]] = None  # 被突破的峰值ID（仅突破）

    def get_formula_string(self) -> str:
        """
        生成计算公式字符串

        Returns:
            如 "60×30% + 75×20% + 75×30% + 82×20% = 72.5"
        """
        terms = []
        for f in self.features:
            # 跳过子因素（它们在 Resistance 里展开）
            if f.sub_features:
                terms.append(f"{f.score:.0f}×{f.weight*100:.0f}%")
            else:
                terms.append(f"{f.score:.0f}×{f.weight*100:.0f}%")

        formula = " + ".join(terms)
        return f"{formula} = {self.total_score:.1f}"


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

        # 峰值评分权重（已移除无效的 merged 权重，重新分配给其他维度）
        self.peak_weights = {
            'volume': config.get('peak_weight_volume', 0.30),
            'candle': config.get('peak_weight_candle', 0.20),
            'suppression': config.get('peak_weight_suppression', 0.30),
            'height': config.get('peak_weight_height', 0.20),
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
        breakdown = self.get_peak_score_breakdown(peak)
        peak.quality_score = breakdown.total_score
        return breakdown.total_score

    def score_breakthrough(self, breakthrough: Breakthrough) -> float:
        """
        评估突破质量

        将分数写入breakthrough.quality_score

        Args:
            breakthrough: 突破点对象

        Returns:
            质量分数（0-100）
        """
        breakdown = self.get_breakthrough_score_breakdown(breakthrough)
        breakthrough.quality_score = breakdown.total_score
        return breakdown.total_score

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
        阻力强度评分

        委托给 _get_resistance_breakdown() 以保持评分逻辑单一来源
        """
        feature = self._get_resistance_breakdown(breakthrough)
        return feature.score

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
        best_cluster_density = None  # 用 None 表示尚未找到密集簇

        # 计算整体分散度（作为备用值）
        overall_range = prices[-1] - prices[0]
        overall_avg = sum(prices) / n
        overall_density = overall_range / overall_avg if overall_avg > 0 else 0.0

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

        # 如果没有找到密集簇，返回整体分散度
        if best_cluster_density is None:
            best_cluster_density = overall_density

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

    # =========================================================================
    # 评分分解方法（用于浮动窗口显示）
    # =========================================================================

    def get_peak_score_breakdown(self, peak: Peak) -> ScoreBreakdown:
        """
        获取峰值评分的详细分解

        Args:
            peak: 峰值对象

        Returns:
            ScoreBreakdown 包含各特征的详细评分
        """
        features = []

        # 1. 放量评分
        volume_score = self._linear_score(
            peak.volume_surge_ratio, 2.0, 5.0, 0, 100
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
            abs(peak.candle_change_pct), 0.05, 0.10, 0, 100
        )
        features.append(FeatureScoreDetail(
            name="Candle Change",
            raw_value=abs(peak.candle_change_pct) * 100,  # 转为百分比
            unit="%",
            score=candle_score,
            weight=self.peak_weights['candle']
        ))

        # 3. 压制时间评分
        suppression_days = peak.left_suppression_days + peak.right_suppression_days
        suppression_score = self._linear_score(
            suppression_days, 30, 60, 0, 100
        )
        features.append(FeatureScoreDetail(
            name="Suppression",
            raw_value=suppression_days,
            unit="d",
            score=suppression_score,
            weight=self.peak_weights['suppression']
        ))

        # 4. 相对高度评分
        height_score = self._linear_score(
            peak.relative_height, 0.05, 0.10, 0, 100
        )
        features.append(FeatureScoreDetail(
            name="Rel. Height",
            raw_value=peak.relative_height * 100,  # 转为百分比
            unit="%",
            score=height_score,
            weight=self.peak_weights['height']
        ))

        # 计算总分
        total_score = sum(f.score * f.weight for f in features)

        return ScoreBreakdown(
            entity_type='peak',
            entity_id=peak.id,
            total_score=total_score,
            features=features
        )

    def get_breakthrough_score_breakdown(
        self, breakthrough: Breakthrough
    ) -> ScoreBreakdown:
        """
        获取突破评分的详细分解

        Args:
            breakthrough: 突破对象

        Returns:
            ScoreBreakdown 包含各特征的详细评分，阻力强度含子因素
        """
        features = []

        # 1. 涨跌幅评分
        change_score = self._linear_score(
            abs(breakthrough.price_change_pct), 0.03, 0.06, 0, 100
        )
        features.append(FeatureScoreDetail(
            name="Price Change",
            raw_value=abs(breakthrough.price_change_pct) * 100,
            unit="%",
            score=change_score,
            weight=self.breakthrough_weights['change']
        ))

        # 2. 跳空评分
        gap_score = self._linear_score(
            breakthrough.gap_up_pct, 0.01, 0.02, 0, 100
        )
        features.append(FeatureScoreDetail(
            name="Gap Up",
            raw_value=breakthrough.gap_up_pct * 100,
            unit="%",
            score=gap_score,
            weight=self.breakthrough_weights['gap']
        ))

        # 3. 放量评分
        volume_score = self._linear_score(
            breakthrough.volume_surge_ratio, 2.0, 5.0, 0, 100
        )
        features.append(FeatureScoreDetail(
            name="Volume Surge",
            raw_value=breakthrough.volume_surge_ratio,
            unit="x",
            score=volume_score,
            weight=self.breakthrough_weights['volume']
        ))

        # 4. 连续性评分
        continuity_score = self._linear_score(
            breakthrough.continuity_days, 3, 5, 0, 100
        )
        features.append(FeatureScoreDetail(
            name="Continuity",
            raw_value=breakthrough.continuity_days,
            unit="d",
            score=continuity_score,
            weight=self.breakthrough_weights['continuity']
        ))

        # 5. 稳定性评分
        stability_score = breakthrough.stability_score
        features.append(FeatureScoreDetail(
            name="Stability",
            raw_value=breakthrough.stability_score,
            unit="%",
            score=stability_score,
            weight=self.breakthrough_weights['stability']
        ))

        # 6. 阻力强度评分（含子因素展开）
        resistance_feature = self._get_resistance_breakdown(breakthrough)
        features.append(resistance_feature)

        # 计算总分
        total_score = sum(f.score * f.weight for f in features)

        # 获取被突破的峰值ID
        broken_peak_ids = [p.id for p in breakthrough.broken_peaks if p.id is not None]

        return ScoreBreakdown(
            entity_type='breakthrough',
            entity_id=None,
            total_score=total_score,
            features=features,
            broken_peak_ids=broken_peak_ids
        )

    def _get_resistance_breakdown(
        self, breakthrough: Breakthrough
    ) -> FeatureScoreDetail:
        """
        获取阻力强度的详细分解（含三个子因素）

        Args:
            breakthrough: 突破对象

        Returns:
            FeatureScoreDetail 含 sub_features
        """
        broken_peaks = breakthrough.broken_peaks
        num_peaks = len(broken_peaks)
        sub_features = []

        if num_peaks == 0:
            return FeatureScoreDetail(
                name="Resistance",
                raw_value=0,
                unit="",
                score=0,
                weight=self.breakthrough_weights['resistance'],
                sub_features=[]
            )

        # 1. 数量评分
        quantity_score = self._score_quantity(num_peaks)
        sub_features.append(FeatureScoreDetail(
            name="Quantity",
            raw_value=num_peaks,
            unit="pks",
            score=quantity_score,
            weight=self.resistance_weights['quantity']
        ))

        # 2. 密集度评分
        if num_peaks >= 2:
            prices = sorted([p.price for p in broken_peaks])
            max_cluster_size, cluster_density = self._find_densest_cluster(prices)
            density_score = self._score_density(broken_peaks)
            density_value = cluster_density * 100  # 转为百分比
        else:
            density_score = 50.0
            density_value = 0.0

        sub_features.append(FeatureScoreDetail(
            name="Density",
            raw_value=density_value,
            unit="%",
            score=density_score,
            weight=self.resistance_weights['density']
        ))

        # 3. 质量评分
        quality_score = self._score_peak_quality_aggregate(broken_peaks)
        qualities = [p.quality_score for p in broken_peaks if p.quality_score]
        avg_quality = sum(qualities) / len(qualities) if qualities else 50.0

        sub_features.append(FeatureScoreDetail(
            name="Quality",
            raw_value=avg_quality,
            unit="",
            score=quality_score,
            weight=self.resistance_weights['quality']
        ))

        # 计算阻力强度总分
        resistance_score = sum(sf.score * sf.weight for sf in sub_features)

        return FeatureScoreDetail(
            name="Resistance",
            raw_value=resistance_score,  # 用总分作为 raw_value 显示
            unit="",
            score=resistance_score,
            weight=self.breakthrough_weights['resistance'],
            sub_features=sub_features
        )
