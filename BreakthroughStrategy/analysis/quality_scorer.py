"""
质量评分模块（双维度时间模型版）

核心设计：
1. 峰值质量仅包含筹码堆积因子（volume + candle），相对高度移至历史意义（心理阻力）
2. recency 整合入 quality - 阻力强度 = 数量 + 密集度 + (质量 × 时间调制)
3. 双维度时间模型：阻力衰减（指数）+ 历史意义增长（对数）
4. 所有被突破峰值都参与 Historical 计算（简化逻辑，避免过拟合）

峰值质量评分因素（总分100）- 反映筹码堆积强度：
- 放量（60%）：volume_surge_ratio越大越好，反映单点成交密集
- 长K线（40%）：candle_change_pct越大越好，反映单点价格波动剧烈

突破质量评分因素（总分100）：
- 涨跌幅：price_change_pct越大越好
- 跳空：gap_up_pct越大越好
- 放量：volume_surge_ratio越大越好
- 连续性：continuity_days越多越好
- 稳定性：stability_score（突破后不跌破凸点）
- 阻力强度：数量 + 密集度 + 有效质量(质量×时间因子)
- 历史意义：最远峰值年龄 + 最大相对高度
- 连续突破（Momentum）：近期突破次数加成
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional
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

        # 峰值评分权重（仅保留筹码堆积因子：volume + candle）
        # 相对高度已移至 Historical 维度（心理阻力）
        self.peak_weights = {
            'volume': config.get('peak_weight_volume', 0.60),
            'candle': config.get('peak_weight_candle', 0.40),
        }

        # 突破评分权重（新增 historical 和 momentum）
        self.breakthrough_weights = {
            'change': config.get('bt_weight_change', 0.15),
            'gap': config.get('bt_weight_gap', 0.08),
            'volume': config.get('bt_weight_volume', 0.17),
            'continuity': config.get('bt_weight_continuity', 0.12),
            'stability': config.get('bt_weight_stability', 0.13),
            'resistance': config.get('bt_weight_resistance', 0.18),
            'historical': config.get('bt_weight_historical', 0.17),  # 历史意义
            'momentum': config.get('bt_weight_momentum', 0.0)  # 连续突破加成（默认0，需配置启用）
        }

        # 阻力强度评分的子权重（recency 已整合入 quality）
        # Phase 1 重构：recency 不再独立，而是调制 quality
        self.resistance_weights = {
            'quantity': config.get('res_weight_quantity', 0.30),
            'density': config.get('res_weight_density', 0.30),
            'quality': config.get('res_weight_quality', 0.40),  # 含时间衰减
        }

        # 时间衰减基线：即使峰值很老，仍保留一定比例的基础阻力
        self.time_decay_baseline = config.get('time_decay_baseline', 0.3)

        # 历史意义评分的子权重
        # relative_height 反映心理阻力（如 W 型突破）
        self.historical_weights = {
            'oldest_age': config.get('hist_weight_oldest_age', 0.55),
            'relative_height': config.get('hist_weight_relative_height', 0.45)
        }

        # 时间函数参数（单位：交易日）
        self.time_decay_half_life = config.get('time_decay_half_life', 84)  # 4个月
        self.historical_significance_saturation = config.get(
            'historical_significance_saturation', 252  # 1年
        )

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
            self.score_breakthrough(breakthrough) ## str(breakthrough.date) == "2024-05-15"

        return breakthroughs

    def _score_resistance_strength(self, breakthrough: Breakthrough) -> float:
        """
        阻力强度评分

        委托给 _get_resistance_breakdown() 以保持评分逻辑单一来源
        """
        feature = self._get_resistance_breakdown(breakthrough)
        return feature.score

    def _score_quantity(self, num_peaks: int) -> float:
        """
        峰值数量评分

        1个峰值 → 0分（最少阻力）
        5+个峰值 → 100分（强阻力区）
        """
        return self._linear_score(num_peaks, 1, 5, 0, 100)

    def _score_density(
        self,
        broken_peaks: List[Peak],
        max_cluster_size: int = None
    ) -> float:
        """
        密集度评分（简化版）

        评分逻辑：
        - 无密集簇：0分
        - 2个峰值：50分（基础阻力区）
        - 3个峰值：75分
        - 4+个峰值：100分（强阻力区）

        注：密集簇由 _find_densest_cluster 用 3% 阈值识别，
        通过阈值的簇已经"足够密集"，只需按簇大小评分。

        Args:
            broken_peaks: 被突破的峰值列表
            max_cluster_size: 可选的预计算结果（最大簇大小）
        """
        n = len(broken_peaks)

        if n <= 1:
            return 0.0

        # 获取密集簇大小
        if max_cluster_size is None:
            prices = sorted([p.price for p in broken_peaks])
            max_cluster_size = self._find_densest_cluster(prices)

        if max_cluster_size <= 1:
            return 0.0

        # 仅根据簇大小评分：2个→50, 4+个→100
        return self._linear_score(max_cluster_size, 2, 4, 50, 100)

    def _find_densest_cluster(self,
                             prices: List[float],
                             density_threshold: float = 0.03) -> int:
        """
        找到最大的密集簇

        Args:
            prices: 排序后的价格列表
            density_threshold: 密集度阈值（默认3%）

        Returns:
            最大簇包含的峰值数量
        """
        n = len(prices)
        if n <= 1:
            return n

        max_cluster_size = 1

        # 滑动窗口找密集子集
        for i in range(n):
            for j in range(i + 1, n):
                cluster = prices[i:j+1]
                cluster_range = cluster[-1] - cluster[0]
                cluster_avg = sum(cluster) / len(cluster)

                if cluster_avg == 0:
                    continue

                density = cluster_range / cluster_avg

                if density <= density_threshold and len(cluster) > max_cluster_size:
                    max_cluster_size = len(cluster)

        return max_cluster_size

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

    # =========================================================================
    # 时间函数方法（双维度时间模型）
    # =========================================================================

    def _calculate_time_decay_factor(self, peak_age_bars: int) -> float:
        """
        计算时间衰减因子（指数衰减）

        阻力强度随时间衰减：近期峰值阻力强，远期峰值阻力弱
        公式：decay = 0.5^(bars / half_life)

        Args:
            peak_age_bars: 峰值距今K线数（交易日，非日历日）

        Returns:
            衰减因子 (0.1, 1.0]，越新的峰值越接近 1.0
        """
        if peak_age_bars <= 0:
            return 1.0

        decay = math.pow(0.5, peak_age_bars / self.time_decay_half_life)
        return max(0.1, decay)  # 保留 10% 底线阻力

    def _score_effective_quality(
        self,
        broken_peaks: List[Peak],
        breakthrough_index: int
    ) -> tuple:
        """
        计算有效质量评分（Phase 1 核心方法）

        设计理念：
        - 阻力 = 峰值质量 × 时间调制因子
        - 时间调制因子 = baseline + (1 - baseline) × decay
        - baseline 保证即使很老的峰值也保留部分阻力（默认30%）

        物理类比：
        - peak_quality 是"墙的原始厚度"
        - time_factor 是"风化程度"（0.3~1.0）
        - effective_quality 是"当前有效厚度"

        Args:
            broken_peaks: 被突破的峰值列表
            breakthrough_index: 突破点的索引

        Returns:
            (effective_quality_score, avg_raw_quality, avg_time_factor)
            - effective_quality_score: 有效质量分数 (0-100)
            - avg_raw_quality: 原始质量均值（用于 UI 显示）
            - avg_time_factor: 时间因子均值（用于 UI 显示）
        """
        if not broken_peaks:
            return 0.0, 0.0, 0.0

        baseline = self.time_decay_baseline  # 默认 0.3

        effective_qualities = []
        raw_qualities = []
        time_factors = []

        for peak in broken_peaks:
            # 原始质量
            raw_quality = peak.quality_score if peak.quality_score else 50.0
            raw_qualities.append(raw_quality)

            # 时间衰减
            age_bars = breakthrough_index - peak.index
            decay = self._calculate_time_decay_factor(age_bars)

            # 时间调制因子：baseline + (1-baseline) × decay
            # 含义：即使 decay→0，仍保留 baseline 比例的阻力
            time_factor = baseline + (1 - baseline) * decay
            time_factors.append(time_factor)

            # 有效质量 = 原始质量 × 时间调制因子
            effective_quality = raw_quality * time_factor
            effective_qualities.append(effective_quality)

        # 计算平均值
        avg_effective = sum(effective_qualities) / len(effective_qualities)
        avg_raw = sum(raw_qualities) / len(raw_qualities)
        avg_time_factor = sum(time_factors) / len(time_factors)

        # 有效质量分数已经在 0-100 范围内（因为 quality 是 0-100，factor 是 0.3-1.0）
        return avg_effective, avg_raw, avg_time_factor

    def _score_recency(
        self,
        broken_peaks: List[Peak],
        breakthrough_index: int
    ) -> float:
        """
        评估峰值的时间近度（已废弃，保留用于向后兼容）

        注意：Phase 1 重构后，此方法不再被 _get_resistance_breakdown 调用
        recency 已整合入 _score_effective_quality

        Args:
            broken_peaks: 被突破的峰值列表
            breakthrough_index: 突破点的索引

        Returns:
            时间近度分数 (0-100)
        """
        if not broken_peaks:
            return 0.0

        # 计算每个峰值的衰减因子
        decay_factors = []
        for peak in broken_peaks:
            age_bars = breakthrough_index - peak.index  # K线索引差 = 交易日数
            decay = self._calculate_time_decay_factor(age_bars)
            decay_factors.append(decay)

        # 简单平均
        avg_decay = sum(decay_factors) / len(decay_factors)

        # 映射到 0-100 分数
        return avg_decay * 100

    def _score_suppression_span(self, broken_peaks: List[Peak]) -> float:
        """
        压制跨度评分（用于历史意义维度）

        考虑所有被突破峰值的总压制时间跨度

        Args:
            broken_peaks: 被突破的峰值列表

        Returns:
            压制跨度分数 (0-100)
        """
        if not broken_peaks:
            return 0.0

        # 计算平均压制天数
        total_suppression = sum(
            p.left_suppression_days + p.right_suppression_days
            for p in broken_peaks
        )
        avg_suppression = total_suppression / len(broken_peaks)

        # 线性映射：30天->0分，90天->100分
        return self._linear_score(avg_suppression, 30, 90, 0, 100)

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
            base_value: 基准值，低于此值得0分（默认1.0，正常量）
            saturation_value: 饱和值，达到此值得满分（默认10.0）
            min_score: 最低分数（默认0）
            max_score: 最高分数（默认100）

        Returns:
            评分结果（限制在[min_score, max_score]范围内）

        Example:
            _log_score(2.0, 1.0, 10.0) ≈ 30  # 2倍量
            _log_score(4.0, 1.0, 10.0) ≈ 60  # 4倍量（翻倍才等值增益）
            _log_score(8.0, 1.0, 10.0) ≈ 90  # 8倍量
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

        # 注：相对高度已移至 Historical 维度（心理阻力），不再作为峰值质量因子

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
        # 断点条件： breakthrough.symbol == "600519" and str(breakthrough.date.date) == "2024-05-15"
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

        # 3. 放量评分（对数函数，边际效益递减）
        volume_score = self._log_score(
            breakthrough.volume_surge_ratio, 1.0, 8.0, 0, 100
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

        # 7. 历史意义评分（新增，含子因素展开）
        historical_feature = self._get_historical_breakdown(breakthrough)
        features.append(historical_feature)

        # 8. 连续突破加成（Momentum）
        momentum_feature = self._get_momentum_breakdown(breakthrough)
        features.append(momentum_feature)

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
        获取阻力强度的详细分解（Phase 1 重构版）

        设计理念（基于阻力衰减研究）：
        - Recency 不再作为独立维度，而是调制 Quality
        - 公式：effective_quality = peak_quality × (baseline + (1-baseline) × decay)
        - 这样符合物理直觉："阻力墙的厚度"随时间"风化"

        子因素：
        1. Quantity: 峰值数量（结构因素，不衰减）
        2. Density: 峰值密集度（结构因素，不衰减）
        3. Eff.Quality: 有效质量 = 峰值质量 × 时间调制因子

        Args:
            breakthrough: 突破对象

        Returns:
            FeatureScoreDetail 含 sub_features
        """
        # breakthrough.symbol == "VRAX" and str(breakthrough.date) == "2024-08-14"
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

        # 1. 数量评分（结构因素，不受时间影响）
        quantity_score = self._score_quantity(num_peaks)
        sub_features.append(FeatureScoreDetail(
            name="Quantity",
            raw_value=num_peaks,
            unit="pks",
            score=quantity_score,
            weight=self.resistance_weights['quantity']
        ))

        # 2. 密集度评分（结构因素，不受时间影响）
        if num_peaks >= 2:
            prices = sorted([p.price for p in broken_peaks])
            max_cluster_size = self._find_densest_cluster(prices)
            density_score = self._score_density(broken_peaks, max_cluster_size)
        else:
            # 单一峰值：密集度概念不适用，得 0 分
            max_cluster_size = num_peaks
            density_score = 0.0

        sub_features.append(FeatureScoreDetail(
            name="Density",
            raw_value=max_cluster_size,
            unit="pks",
            score=density_score,
            weight=self.resistance_weights['density']
        ))

        # 3. 有效质量评分（质量 × 时间调制因子）
        # Phase 1 核心改动：recency 整合入 quality
        effective_quality_score, avg_raw_quality, avg_time_factor = \
            self._score_effective_quality(broken_peaks, breakthrough.index)

        sub_features.append(FeatureScoreDetail(
            name="Eff.Quality",
            raw_value=avg_raw_quality,  # 显示原始质量
            unit=f"×{avg_time_factor:.0%}",  # 单位显示时间因子
            score=effective_quality_score,  # 时间
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

    def _get_historical_breakdown(
        self, breakthrough: Breakthrough
    ) -> FeatureScoreDetail:
        """
        获取历史意义的详细分解（含两个子因素）

        Phase 2 改进：条件性历史加成
        - 仅高质量峰值（quality_score >= threshold）参与计算
        - 若无高质量峰值，回退到使用所有峰值

        子因素：
        1. Oldest Age: 最远被突破峰值的年龄（对数增长）- 时间维度
        2. Max Rel.Height: 最大相对高度 - 价格维度的心理阻力（如 W 型突破）

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
                name="Historical",
                raw_value=0,
                unit="",
                score=0,
                weight=self.breakthrough_weights['historical'],
                sub_features=[]
            )

        # 所有被突破峰值都参与 Historical 计算（简化逻辑，避免过拟合）

        # 1. 最远峰值年龄评分 - 时间维度
        oldest_peak = max(broken_peaks, key=lambda p: breakthrough.index - p.index)
        oldest_age = breakthrough.index - oldest_peak.index
        oldest_age_score = self._log_score(
            oldest_age + 1,  # +1 处理 log(0) 边界
            base_value=1.0,
            saturation_value=self.historical_significance_saturation + 1
        )

        sub_features.append(FeatureScoreDetail(
            name="Oldest Age",
            raw_value=oldest_age,
            unit="d",
            score=oldest_age_score,
            weight=self.historical_weights['oldest_age']
        ))

        # 2. 最大相对高度评分（价格维度的心理阻力）
        # 使用被突破峰值中的最大相对高度，因为心理阻力由最显著的那个峰值决定
        max_height_peak = max(broken_peaks, key=lambda p: p.relative_height)
        max_relative_height = max_height_peak.relative_height
        # 评分: 5%->0分, 30%->100分
        height_score = self._linear_score(max_relative_height, 0.05, 0.30, 0, 100)

        sub_features.append(FeatureScoreDetail(
            name="Max Rel.Height",
            raw_value=max_relative_height * 100,  # 转为百分比显示
            unit="%",
            score=height_score,
            weight=self.historical_weights['relative_height']
        ))

        # 计算历史意义总分
        historical_score = sum(sf.score * sf.weight for sf in sub_features)

        return FeatureScoreDetail(
            name="Historical",
            raw_value=historical_score,
            unit="",
            score=historical_score,
            weight=self.breakthrough_weights['historical'],
            sub_features=sub_features
        )

    def _get_momentum_breakdown(
        self, breakthrough: Breakthrough
    ) -> FeatureScoreDetail:
        """
        获取连续突破加成的详细分解

        评分逻辑：
        - 1次 → 0分（首次突破，无加成）
        - 2次 → 50分（有连续性）
        - 3次 → 75分
        - 4+次 → 100分（强势突破序列）

        Args:
            breakthrough: 突破对象

        Returns:
            FeatureScoreDetail
        """
        count = breakthrough.recent_breakthrough_count

        # 评分映射：1→0, 2→50, 3→75, 4+→100
        if count >= 4:
            score = 100
        elif count == 3:
            score = 75
        elif count == 2:
            score = 50
        else:
            score = 0

        return FeatureScoreDetail(
            name="Momentum",
            raw_value=count,
            unit="bt",  # breakthroughs
            score=score,
            weight=self.breakthrough_weights['momentum']
        )
