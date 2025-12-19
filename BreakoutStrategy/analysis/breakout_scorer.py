"""
突破评分模块（Bonus 乘法模型）

突破评分公式：
    总分 = BASE × age_bonus × test_bonus × height_bonus × peak_volume_bonus ×
           volume_bonus × gap_bonus × continuity_bonus × momentum_bonus

设计理念：
1. 所有因素统一为乘数形式，避免权重归一化
2. 满足条件时获得对应 bonus 乘数（>1.0），否则为 1.0（无加成）
3. 总分可超过 100，只要同一基准下可比即可

阻力属性 Bonus：
- age_bonus: 最老峰值年龄（远期 > 近期）
- test_bonus: 测试次数（最大簇的峰值数）
- height_bonus: 最大相对高度
- peak_volume_bonus: 峰值放量

突破行为 Bonus：
- volume_bonus: 成交量放大
- gap_bonus: 跳空缺口
- continuity_bonus: 连续阳线
- momentum_bonus: 连续突破
"""

from dataclasses import dataclass, field
from typing import List, Optional
from .breakout_detector import Peak, Breakout


# =============================================================================
# 评分分解数据类（用于浮动窗口显示）
# =============================================================================

@dataclass
class BonusDetail:
    """单个 Bonus 的详情（乘法模型用）"""
    name: str           # 显示名称（如 "Age", "Volume"）
    raw_value: float    # 原始数值（如 180天, 2.5倍）
    unit: str           # 单位 ('d', 'x', '%', 'bo')
    bonus: float        # bonus 乘数（如 1.30）
    triggered: bool     # 是否触发（bonus > 1.0）
    level: int          # 触发级别（0=未触发, 1=级别1, 2=级别2, ...）


@dataclass
class ScoreBreakdown:
    """评分分解（Bonus 乘法模型）"""
    entity_type: str                      # 'breakout'
    entity_id: Optional[int]              # (unused, for compatibility)
    total_score: float                    # 总分
    broken_peak_ids: Optional[List[int]] = None  # 被突破的峰值ID
    # Bonus 模型字段
    base_score: Optional[float] = None    # 基准分
    bonuses: Optional[List[BonusDetail]] = None  # Bonus 列表

    def get_formula_string(self) -> str:
        """
        生成计算公式字符串

        Returns:
            加权模型: "60×30% + 75×20% + 75×30% + 82×20% = 72.5"
            Bonus模型: "50 × 1.30 × 1.25 × 1.15 × 1.20 = 112.1"
        """
        # Bonus 模型
        if self.bonuses is not None and self.base_score is not None:
            terms = [f"{self.base_score:.0f}"]
            for b in self.bonuses:
                if b.triggered:
                    terms.append(f"×{b.bonus:.2f}")
            formula = " ".join(terms)
            return f"{formula} = {self.total_score:.1f}"

        # 加权模型（原有逻辑）
        terms = []
        for f in self.features:
            terms.append(f"{f.score:.0f}×{f.weight*100:.0f}%")

        formula = " + ".join(terms)
        return f"{formula} = {self.total_score:.1f}"


class BreakoutScorer:
    """突破评分器（Bonus 乘法模型）"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化突破评分器

        Args:
            config: 配置参数字典，包含 Bonus 阈值和乘数
        """
        if config is None:
            config = {}

        # 阻力簇分组阈值（默认引用 peak_supersede_threshold，保持一致性）
        self.cluster_density_threshold = config.get(
            'cluster_density_threshold',
            config.get('peak_supersede_threshold', 0.03)
        )

        # =====================================================================
        # Bonus 乘法模型配置
        # =====================================================================

        # 基准分：存在有效突破这件事本身的价值
        self.bonus_base_score = config.get('bonus_base_score', 50)

        # Age bonus 阈值和乘数
        # 远期阻力 > 近期阻力（技术分析共识）
        self.age_bonus_thresholds = config.get('age_bonus_thresholds', [21, 63, 252])  # 1月, 3月, 1年
        self.age_bonus_values = config.get('age_bonus_values', [1.15, 1.30, 1.50])

        # Test count bonus（测试次数 = 簇内峰值数）
        self.test_bonus_thresholds = config.get('test_bonus_thresholds', [2, 3, 4])
        self.test_bonus_values = config.get('test_bonus_values', [1.10, 1.25, 1.40])

        # Height bonus（相对高度）
        self.height_bonus_thresholds = config.get('height_bonus_thresholds', [0.10, 0.20])  # 10%, 20%
        self.height_bonus_values = config.get('height_bonus_values', [1.15, 1.30])

        # Volume bonus（成交量放大）
        self.volume_bonus_thresholds = config.get('volume_bonus_thresholds', [1.5, 2.0])
        self.volume_bonus_values = config.get('volume_bonus_values', [1.15, 1.30])

        # Gap bonus（跳空缺口）
        self.gap_bonus_thresholds = config.get('gap_bonus_thresholds', [0.01, 0.02])  # 1%, 2%
        self.gap_bonus_values = config.get('gap_bonus_values', [1.10, 1.20])

        # Continuity bonus（连续阳线）
        self.continuity_bonus_thresholds = config.get('continuity_bonus_thresholds', [3])
        self.continuity_bonus_values = config.get('continuity_bonus_values', [1.15])

        # Momentum bonus（连续突破）
        self.momentum_bonus_thresholds = config.get('momentum_bonus_thresholds', [2])
        self.momentum_bonus_values = config.get('momentum_bonus_values', [1.20])

        # Peak Volume bonus（峰值放量，阻力属性）
        # 被突破峰值中的最大成交量放大倍数
        self.peak_volume_bonus_thresholds = config.get('peak_volume_bonus_thresholds', [5.0, 10.0])
        self.peak_volume_bonus_values = config.get('peak_volume_bonus_values', [1.10, 1.20])

    def score_breakout(self, breakout: Breakout) -> float:
        """
        评估突破质量（使用 Bonus 乘法模型）

        将分数写入breakout.quality_score

        Args:
            breakout: 突破点对象

        Returns:
            质量分数（可超过100）
        """
        breakdown = self.get_breakout_score_breakdown_bonus(breakout)
        breakout.quality_score = breakdown.total_score
        return breakdown.total_score

    def score_breakouts_batch(
        self,
        breakouts: List[Breakout]
    ) -> List[Breakout]:
        """
        批量评分突破点

        Args:
            breakouts: 突破点列表

        Returns:
            评分后的突破点列表（原列表）
        """
        for breakout in breakouts:
            self.score_breakout(breakout) ## str(breakout.date) == "2024-05-15"

        return breakouts

    # =========================================================================
    # 阻力簇分组与评分
    # =========================================================================

    def _group_peaks_into_clusters(
        self,
        peaks: List[Peak],
        density_threshold: float = 0.03
    ) -> List[List[Peak]]:
        """
        将峰值按价格相近度分组成阻力簇

        算法：贪心聚类，相邻峰值价差 < threshold 则归入同簇

        Args:
            peaks: 被突破的峰值列表
            density_threshold: 密集度阈值（默认3%）

        Returns:
            簇列表，每个簇是 List[Peak]
        """
        if not peaks:
            return []

        if len(peaks) == 1:
            return [peaks]

        # 按价格排序
        sorted_peaks = sorted(peaks, key=lambda p: p.price)

        clusters = []
        current_cluster = [sorted_peaks[0]]

        for i in range(1, len(sorted_peaks)):
            prev_peak = sorted_peaks[i - 1]
            curr_peak = sorted_peaks[i]

            # 计算价差比例（相对于较低价格）
            price_diff_ratio = (curr_peak.price - prev_peak.price) / prev_peak.price

            if price_diff_ratio <= density_threshold:
                # 价差小于阈值，归入当前簇
                current_cluster.append(curr_peak)
            else:
                # 价差过大，结束当前簇，开始新簇
                clusters.append(current_cluster)
                current_cluster = [curr_peak]

        # 处理最后一个簇
        clusters.append(current_cluster)

        return clusters

    # =========================================================================
    # Bonus 乘法模型方法
    # =========================================================================

    def _get_bonus_value(
        self,
        value: float,
        thresholds: List[float],
        bonus_values: List[float]
    ) -> tuple:
        """
        根据阈值获取 bonus 值

        Args:
            value: 待评估的值
            thresholds: 阈值列表（升序）
            bonus_values: 对应的 bonus 值列表

        Returns:
            (bonus, level): bonus 乘数和触发级别
            - level=0 表示未触发任何阈值
            - level=1,2,3 表示触发的级别
        """
        bonus = 1.0
        level = 0

        for i, threshold in enumerate(thresholds):
            if value >= threshold:
                bonus = bonus_values[i]
                level = i + 1
            else:
                break

        return bonus, level

    def _get_age_bonus(self, oldest_age: int) -> BonusDetail:
        """
        计算年龄 bonus

        远期阻力 > 近期阻力（技术分析共识）

        Args:
            oldest_age: 最老峰值距突破的交易日数

        Returns:
            BonusDetail
        """
        bonus, level = self._get_bonus_value(
            oldest_age,
            self.age_bonus_thresholds,
            self.age_bonus_values
        )

        return BonusDetail(
            name="Age",
            raw_value=oldest_age,
            unit="d",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_test_bonus(self, test_count: int) -> BonusDetail:
        """
        计算测试次数 bonus

        多次测试 > 单次测试

        Args:
            test_count: 测试次数（簇内峰值数）

        Returns:
            BonusDetail
        """
        bonus, level = self._get_bonus_value(
            test_count,
            self.test_bonus_thresholds,
            self.test_bonus_values
        )

        return BonusDetail(
            name="Tests",
            raw_value=test_count,
            unit="x",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_height_bonus(self, max_height: float) -> BonusDetail:
        """
        计算高度 bonus

        高位阻力 > 低位阻力

        Args:
            max_height: 最大相对高度（小数形式，如 0.15 表示 15%）

        Returns:
            BonusDetail
        """
        bonus, level = self._get_bonus_value(
            max_height,
            self.height_bonus_thresholds,
            self.height_bonus_values
        )

        return BonusDetail(
            name="Height",
            raw_value=max_height * 100,  # 转为百分比显示
            unit="%",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_peak_volume_bonus(self, peak_volume_ratio: float) -> BonusDetail:
        """
        计算峰值放量 bonus（阻力属性）

        被突破峰值的成交量越大，阻力越强，突破意义越大

        Args:
            peak_volume_ratio: 峰值的成交量放大倍数

        Returns:
            BonusDetail
        """
        bonus, level = self._get_bonus_value(
            peak_volume_ratio,
            self.peak_volume_bonus_thresholds,
            self.peak_volume_bonus_values
        )

        return BonusDetail(
            name="PeakVol",
            raw_value=peak_volume_ratio,
            unit="x",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_volume_bonus(self, volume_surge_ratio: float) -> BonusDetail:
        """
        计算成交量 bonus

        放量突破 > 缩量突破

        Args:
            volume_surge_ratio: 成交量放大倍数

        Returns:
            BonusDetail
        """
        bonus, level = self._get_bonus_value(
            volume_surge_ratio,
            self.volume_bonus_thresholds,
            self.volume_bonus_values
        )

        return BonusDetail(
            name="Volume",
            raw_value=volume_surge_ratio,
            unit="x",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_gap_bonus(self, gap_up_pct: float) -> BonusDetail:
        """
        计算跳空 bonus

        跳空突破更强势

        Args:
            gap_up_pct: 跳空百分比（小数形式）

        Returns:
            BonusDetail
        """
        bonus, level = self._get_bonus_value(
            gap_up_pct,
            self.gap_bonus_thresholds,
            self.gap_bonus_values
        )

        return BonusDetail(
            name="Gap",
            raw_value=gap_up_pct * 100,  # 转为百分比显示
            unit="%",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_continuity_bonus(self, continuity_days: int) -> BonusDetail:
        """
        计算连续性 bonus

        连续阳线增强确认

        Args:
            continuity_days: 连续阳线天数

        Returns:
            BonusDetail
        """
        bonus, level = self._get_bonus_value(
            continuity_days,
            self.continuity_bonus_thresholds,
            self.continuity_bonus_values
        )

        return BonusDetail(
            name="Continuity",
            raw_value=continuity_days,
            unit="d",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_momentum_bonus(self, recent_breakout_count: int) -> BonusDetail:
        """
        计算动量 bonus

        连续突破表明趋势强劲

        Args:
            recent_breakout_count: 近期突破次数

        Returns:
            BonusDetail
        """
        bonus, level = self._get_bonus_value(
            recent_breakout_count,
            self.momentum_bonus_thresholds,
            self.momentum_bonus_values
        )

        return BonusDetail(
            name="Momentum",
            raw_value=recent_breakout_count,
            unit="bo",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def get_breakout_score_breakdown_bonus(
        self, breakout: Breakout
    ) -> ScoreBreakdown:
        """
        获取突破评分的详细分解（Bonus 乘法模型）

        公式：总分 = BASE × age_bonus × test_bonus × height_bonus ×
                      volume_bonus × gap_bonus × continuity_bonus × momentum_bonus

        Args:
            breakout: 突破对象

        Returns:
            ScoreBreakdown（使用 bonuses 字段）
        """
        broken_peaks = breakout.broken_peaks
        bonuses = []

        # 必要条件：存在被突破的阻力位
        if not broken_peaks:
            return ScoreBreakdown(
                entity_type='breakout',
                entity_id=None,
                total_score=0,
                broken_peak_ids=[],
                base_score=0,
                bonuses=[]
            )

        # 1. 将峰值分组成簇
        clusters = self._group_peaks_into_clusters(
            broken_peaks,
            self.cluster_density_threshold
        )

        # 找到峰值数量最多的簇（用于 test_count）
        # 设计理念：test_count 反映同一阻力区被测试的次数，直接取最大簇
        # Age/Height 等属性已在 Bonus 中单独评估，无需在选簇时考虑
        best_cluster = max(clusters, key=len) if clusters else broken_peaks

        # 2. 提取关键指标
        # Age/Height/PeakVolume: 取全局最值（绝对属性）
        # Tests: 取最大簇的峰值数（密集度属性）
        oldest_age = max(breakout.index - p.index for p in broken_peaks)
        test_count = len(best_cluster)
        max_height = max(p.relative_height for p in broken_peaks)
        max_peak_volume = max(p.volume_surge_ratio for p in broken_peaks)

        # 3. 计算各个 Bonus

        # 阻力属性 Bonus
        age_bonus = self._get_age_bonus(oldest_age)
        bonuses.append(age_bonus)

        test_bonus = self._get_test_bonus(test_count)
        bonuses.append(test_bonus)

        height_bonus = self._get_height_bonus(max_height)
        bonuses.append(height_bonus)

        peak_volume_bonus = self._get_peak_volume_bonus(max_peak_volume)
        bonuses.append(peak_volume_bonus)

        # 突破行为 Bonus
        volume_bonus = self._get_volume_bonus(breakout.volume_surge_ratio)
        bonuses.append(volume_bonus)

        gap_bonus = self._get_gap_bonus(breakout.gap_up_pct)
        bonuses.append(gap_bonus)

        continuity_bonus = self._get_continuity_bonus(breakout.continuity_days)
        bonuses.append(continuity_bonus)

        momentum_bonus = self._get_momentum_bonus(breakout.recent_breakout_count)
        bonuses.append(momentum_bonus)

        # 4. 计算总分（乘法聚合）
        base_score = self.bonus_base_score
        total_multiplier = 1.0
        for b in bonuses:
            total_multiplier *= b.bonus

        total_score = base_score * total_multiplier

        # 获取被突破的峰值ID
        broken_peak_ids = [p.id for p in broken_peaks if p.id is not None]

        return ScoreBreakdown(
            entity_type='breakout',
            entity_id=None,
            total_score=total_score,
            broken_peak_ids=broken_peak_ids,
            base_score=base_score,
            bonuses=bonuses
        )
