"""
突破评分模块（Bonus 乘法模型）

突破评分公式：
    总分 = BASE × age_bonus × test_bonus × height_bonus × peak_volume_bonus ×
           volume_bonus × gap_bonus × pbm_bonus × streak_bonus

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
- pbm_bonus: 突破前涨势强度 (Pre-Breakout Momentum)
- streak_bonus: 连续突破
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
        age_bonus = config.get('age_bonus', {})
        self.age_bonus_enabled = age_bonus.get('enabled', True)
        self.age_bonus_thresholds = age_bonus.get('thresholds', [21, 63, 252])  # 1月, 3月, 1年
        self.age_bonus_values = age_bonus.get('values', [1.15, 1.30, 1.50])

        # Test count bonus（测试次数 = 簇内峰值数）
        test_bonus = config.get('test_bonus', {})
        self.test_bonus_enabled = test_bonus.get('enabled', True)
        self.test_bonus_thresholds = test_bonus.get('thresholds', [2, 3, 4])
        self.test_bonus_values = test_bonus.get('values', [1.10, 1.25, 1.40])

        # Height bonus（相对高度）
        height_bonus = config.get('height_bonus', {})
        self.height_bonus_enabled = height_bonus.get('enabled', True)
        self.height_bonus_thresholds = height_bonus.get('thresholds', [0.10, 0.20])  # 10%, 20%
        self.height_bonus_values = height_bonus.get('values', [1.15, 1.30])

        # Volume bonus（成交量放大）
        volume_bonus = config.get('volume_bonus', {})
        self.volume_bonus_enabled = volume_bonus.get('enabled', True)
        self.volume_bonus_thresholds = volume_bonus.get('thresholds', [1.5, 2.0])
        self.volume_bonus_values = volume_bonus.get('values', [1.15, 1.30])

        # PBM bonus（突破前涨势强度 Pre-Breakout Momentum）
        pbm_bonus = config.get('pbm_bonus', {})
        self.pbm_bonus_enabled = pbm_bonus.get('enabled', True)
        self.pbm_bonus_thresholds = pbm_bonus.get('thresholds', [0.001, 0.003])
        self.pbm_bonus_values = pbm_bonus.get('values', [1.15, 1.30])

        # Streak bonus（连续突破）
        streak_bonus = config.get('streak_bonus', {})
        self.streak_bonus_enabled = streak_bonus.get('enabled', True)
        self.streak_bonus_thresholds = streak_bonus.get('thresholds', [2])
        self.streak_bonus_values = streak_bonus.get('values', [1.20])

        # Peak Volume bonus（峰值放量，阻力属性）
        # 被突破峰值中的最大成交量放大倍数
        peak_volume_bonus = config.get('peak_volume_bonus', {})
        self.peak_volume_bonus_enabled = peak_volume_bonus.get('enabled', True)
        self.peak_volume_bonus_thresholds = peak_volume_bonus.get('thresholds', [2.0, 5.0])
        self.peak_volume_bonus_values = peak_volume_bonus.get('values', [1.10, 1.20])

        # ATR 标准化配置
        self.use_atr_normalization = config.get('use_atr_normalization', False)
        self.atr_normalized_height_thresholds = config.get('atr_normalized_height_thresholds', [1.5, 2.5])
        self.atr_normalized_height_values = config.get('atr_normalized_height_values', [1.10, 1.20])

        # Overshoot penalty（超涨惩罚）
        # 基于 5 日波动率标准化: gain_5d / five_day_vol
        # 单位：σ（5 日标准差倍数）
        overshoot = config.get('overshoot_penalty', {})
        self.overshoot_penalty_enabled = overshoot.get('enabled', True)
        self.overshoot_penalty_thresholds = overshoot.get('thresholds', [3.0, 4.0])
        self.overshoot_penalty_values = overshoot.get('values', [0.7, 0.4])

        # Intraday Return Vol bonus（日内涨幅波动率标准化）
        # intraday_return / daily_vol，其中 daily_vol = annual_vol / sqrt(252)
        idr_vol = config.get('intraday_return_vol_bonus', {})
        self.idr_vol_bonus_enabled = idr_vol.get('enabled', True)
        self.idr_vol_bonus_thresholds = idr_vol.get('thresholds', [2.0, 3.0])
        self.idr_vol_bonus_values = idr_vol.get('values', [1.10, 1.20])

        # Gap Vol bonus（跳空波动率标准化）
        # gap_up_pct / daily_vol
        gap_vol = config.get('gap_vol_bonus', {})
        self.gap_vol_bonus_enabled = gap_vol.get('enabled', True)
        self.gap_vol_bonus_thresholds = gap_vol.get('thresholds', [1.0, 2.0])
        self.gap_vol_bonus_values = gap_vol.get('values', [1.10, 1.15])

        # PK Momentum bonus（近期 peak 凹陷深度）
        # pk_momentum = 1 + log(1 + D_atr)，典型值范围 [1.0, 2.5]
        pk_momentum_bonus = config.get('pk_momentum_bonus', {})
        self.pk_momentum_bonus_enabled = pk_momentum_bonus.get('enabled', True)
        self.pk_momentum_bonus_thresholds = pk_momentum_bonus.get('thresholds', [1.5, 2.0])
        self.pk_momentum_bonus_values = pk_momentum_bonus.get('values', [1.15, 1.25])

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
        if not self.age_bonus_enabled:
            return BonusDetail(
                name="Age",
                raw_value=oldest_age,
                unit="d",
                bonus=1.0,
                triggered=False,
                level=0
            )

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
        if not self.test_bonus_enabled:
            return BonusDetail(
                name="Tests",
                raw_value=test_count,
                unit="x",
                bonus=1.0,
                triggered=False,
                level=0
            )

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
        if not self.height_bonus_enabled:
            return BonusDetail(
                name="Height",
                raw_value=max_height * 100,
                unit="%",
                bonus=1.0,
                triggered=False,
                level=0
            )

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
        if not self.peak_volume_bonus_enabled:
            return BonusDetail(
                name="PeakVol",
                raw_value=peak_volume_ratio,
                unit="x",
                bonus=1.0,
                triggered=False,
                level=0
            )

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
        if not self.volume_bonus_enabled:
            return BonusDetail(
                name="Volume",
                raw_value=volume_surge_ratio,
                unit="x",
                bonus=1.0,
                triggered=False,
                level=0
            )

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

    def _get_overshoot_penalty(
        self,
        gain_5d: float,
        annual_volatility: float
    ) -> BonusDetail:
        """
        计算超涨惩罚（基于 5 日波动率标准化）

        公式：ratio = gain_5d / five_day_vol
        其中：five_day_vol = annual_vol / sqrt(252) * sqrt(5) = annual_vol / sqrt(50.4)
        单位：σ（5 日标准差倍数）

        逻辑：
        - >= 3σ → 0.7x 惩罚（轻度超涨）
        - >= 4σ → 0.4x 惩罚（严重超涨）

        Args:
            gain_5d: 5 日涨幅（绝对值）
            annual_volatility: 年化波动率

        Returns:
            BonusDetail（bonus < 1.0 表示惩罚）
        """
        import math

        if not self.overshoot_penalty_enabled or annual_volatility <= 0:
            return BonusDetail(
                name="Overshoot",
                raw_value=0.0,
                unit="σ",
                bonus=1.0,
                triggered=False,
                level=0
            )

        # 5 日波动率 = 日波动率 × √5 = annual_vol / √252 × √5 = annual_vol / √50.4
        five_day_vol = annual_volatility / math.sqrt(50.4)
        ratio = gain_5d / five_day_vol

        penalty = 1.0
        level = 0
        for i, threshold in enumerate(self.overshoot_penalty_thresholds):
            if ratio >= threshold:
                penalty = self.overshoot_penalty_values[i]
                level = i + 1
            else:
                break

        return BonusDetail(
            name="Overshoot",
            raw_value=round(ratio, 1),
            unit="σ",
            bonus=penalty,
            triggered=(penalty < 1.0),
            level=level
        )

    def _get_intraday_return_vol_bonus(
        self,
        intraday_change_pct: float,
        annual_volatility: float
    ) -> BonusDetail:
        """
        计算日内涨幅 bonus（基于波动率标准化）

        公式：ratio = intraday_return / (annual_vol / sqrt(252))
        单位：σ（日波动率标准差的倍数）

        逻辑：
        - >= 2σ → 1.10x 奖励（强势日K）
        - >= 3σ → 1.20x 奖励（极强日K）

        Args:
            intraday_change_pct: 日内涨幅（收盘价相对开盘价）
            annual_volatility: 年化波动率

        Returns:
            BonusDetail
        """
        import math

        if not self.idr_vol_bonus_enabled or annual_volatility <= 0:
            return BonusDetail(
                name="IDR-Vol",
                raw_value=0.0,
                unit="σ",
                bonus=1.0,
                triggered=False,
                level=0
            )

        daily_vol = annual_volatility / math.sqrt(252)
        ratio = intraday_change_pct / daily_vol

        bonus = 1.0
        level = 0
        for i, threshold in enumerate(self.idr_vol_bonus_thresholds):
            if ratio >= threshold:
                bonus = self.idr_vol_bonus_values[i]
                level = i + 1
            else:
                break

        return BonusDetail(
            name="IDR-Vol",
            raw_value=round(ratio, 1),
            unit="σ",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_gap_vol_bonus(
        self,
        gap_up_pct: float,
        annual_volatility: float
    ) -> BonusDetail:
        """
        计算跳空 bonus（基于波动率标准化）

        公式：ratio = gap_up_pct / (annual_vol / sqrt(252))
        单位：σ（日波动率标准差的倍数）

        逻辑：
        - >= 1σ → 1.10x 奖励（显著跳空）
        - >= 2σ → 1.15x 奖励（大跳空）

        Args:
            gap_up_pct: 跳空幅度（开盘价相对前收）
            annual_volatility: 年化波动率

        Returns:
            BonusDetail
        """
        import math

        if not self.gap_vol_bonus_enabled or annual_volatility <= 0 or gap_up_pct <= 0:
            return BonusDetail(
                name="Gap-Vol",
                raw_value=0.0,
                unit="σ",
                bonus=1.0,
                triggered=False,
                level=0
            )

        daily_vol = annual_volatility / math.sqrt(252)
        ratio = gap_up_pct / daily_vol

        bonus = 1.0
        level = 0
        for i, threshold in enumerate(self.gap_vol_bonus_thresholds):
            if ratio >= threshold:
                bonus = self.gap_vol_bonus_values[i]
                level = i + 1
            else:
                break

        return BonusDetail(
            name="Gap-Vol",
            raw_value=round(ratio, 1),
            unit="σ",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_atr_normalized_height_bonus(self, atr_normalized_height: float) -> BonusDetail:
        """
        计算 ATR 标准化高度 bonus（可选功能）

        突破幅度 / ATR 越大，表示突破越显著
        低波动率环境下的突破更有意义

        Args:
            atr_normalized_height: 突破幅度 / ATR

        Returns:
            BonusDetail
        """
        bonus, level = self._get_bonus_value(
            atr_normalized_height,
            self.atr_normalized_height_thresholds,
            self.atr_normalized_height_values
        )

        return BonusDetail(
            name="ATR-Height",
            raw_value=atr_normalized_height,
            unit="x",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_pbm_bonus(self, momentum: float) -> BonusDetail:
        """
        计算突破前涨势 bonus (Pre-Breakout Momentum)

        涨势强度 = (位移/起点价格) × (位移/路径长度) / K线数量
        正值表示涨势，值越大涨势越强

        Args:
            momentum: 涨势强度值 (PBM)

        Returns:
            BonusDetail
        """
        if not self.pbm_bonus_enabled:
            return BonusDetail(
                name="PBM",
                raw_value=round(momentum * 1000, 2),
                unit="‰",
                bonus=1.0,
                triggered=False,
                level=0
            )

        bonus, level = self._get_bonus_value(
            momentum,
            self.pbm_bonus_thresholds,
            self.pbm_bonus_values
        )

        return BonusDetail(
            name="PBM",
            raw_value=round(momentum * 1000, 2),  # 显示为千分比，更易读
            unit="‰",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_streak_bonus(self, recent_breakout_count: int) -> BonusDetail:
        """
        计算连续突破 bonus

        连续突破表明趋势强劲

        Args:
            recent_breakout_count: 近期突破次数

        Returns:
            BonusDetail
        """
        if not self.streak_bonus_enabled:
            return BonusDetail(
                name="Streak",
                raw_value=recent_breakout_count,
                unit="bo",
                bonus=1.0,
                triggered=False,
                level=0
            )

        bonus, level = self._get_bonus_value(
            recent_breakout_count,
            self.streak_bonus_thresholds,
            self.streak_bonus_values
        )

        return BonusDetail(
            name="Streak",
            raw_value=recent_breakout_count,
            unit="bo",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )

    def _get_pk_momentum_bonus(self, pk_momentum: float) -> BonusDetail:
        """
        计算 pk_momentum bonus（近期 peak 凹陷深度）

        pk_momentum = 1 + log(1 + D_atr)
        - 0: 无近期 peak（超出时间窗口）
        - 1.0: 有近期 peak，无凹陷
        - 1.5: D_atr ≈ 0.65 ATR（中等凹陷）
        - 2.0: D_atr ≈ 1.7 ATR（深凹陷）
        - 2.5: D_atr ≈ 3.5 ATR（很深凹陷）

        Args:
            pk_momentum: pk_momentum 值

        Returns:
            BonusDetail
        """
        if not self.pk_momentum_bonus_enabled:
            return BonusDetail(
                name="PK-Mom",
                raw_value=round(pk_momentum, 2),
                unit="",
                bonus=1.0,
                triggered=False,
                level=0
            )

        bonus, level = self._get_bonus_value(
            pk_momentum,
            self.pk_momentum_bonus_thresholds,
            self.pk_momentum_bonus_values
        )

        return BonusDetail(
            name="PK-Mom",
            raw_value=round(pk_momentum, 2),
            unit="",
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
                      volume_bonus × gap_bonus × pbm_bonus × streak_bonus

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

        # Overshoot penalty（超涨惩罚，基于波动率比率）
        overshoot_penalty = self._get_overshoot_penalty(
            breakout.gain_5d,
            breakout.annual_volatility
        )
        bonuses.append(overshoot_penalty)

        # Intraday Return Vol bonus（日内涨幅波动率标准化）
        idr_vol_bonus = self._get_intraday_return_vol_bonus(
            breakout.intraday_change_pct,
            breakout.annual_volatility
        )
        bonuses.append(idr_vol_bonus)

        # Gap Vol bonus（跳空波动率标准化）
        gap_vol_bonus = self._get_gap_vol_bonus(
            breakout.gap_up_pct,
            breakout.annual_volatility
        )
        bonuses.append(gap_vol_bonus)

        # ATR 标准化高度 bonus（可选功能）
        if self.use_atr_normalization and breakout.atr_normalized_height > 0:
            atr_height_bonus = self._get_atr_normalized_height_bonus(breakout.atr_normalized_height)
            bonuses.append(atr_height_bonus)

        pbm_bonus = self._get_pbm_bonus(breakout.momentum)
        bonuses.append(pbm_bonus)

        streak_bonus = self._get_streak_bonus(breakout.recent_breakout_count)
        bonuses.append(streak_bonus)

        pk_momentum_bonus = self._get_pk_momentum_bonus(breakout.pk_momentum)
        bonuses.append(pk_momentum_bonus)

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
