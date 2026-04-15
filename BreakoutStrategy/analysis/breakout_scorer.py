"""
突破评分模块（Factor 乘法模型）

突破评分公式：
    总分 = BASE × Π(factor_i)   （所有注册因子的乘积）

因子列表由 FACTOR_REGISTRY 动态驱动，添加新因子无需修改本模块。

设计理念：
1. 所有因素统一为乘数形式，避免权重归一化
2. 统一使用 >= 触发，values > 1.0 为奖励，< 1.0 为惩罚
3. 总分可超过 100，只要同一基准下可比即可
"""

from dataclasses import dataclass, field
from typing import List, Optional
from .breakout_detector import Peak, Breakout
from BreakoutStrategy.factor_registry import get_active_factors


# =============================================================================
# 评分分解数据类（用于浮动窗口显示）
# =============================================================================

@dataclass
class FactorDetail:
    """单个 Factor 的详情（乘法模型用）"""
    name: str           # 显示名称（如 "age", "volume"）
    raw_value: float    # 原始数值（如 180天, 2.5倍）
    unit: str           # 单位 ('d', 'x', '%', 'bo')
    multiplier: float   # factor 乘数（如 1.30）
    triggered: bool     # 是否触发（level > 0）
    level: int          # 触发级别（0=未触发, 1=级别1, 2=级别2, ...）
    unavailable: bool = False  # True = 因 lookback 不足等原因无法计算（非"未触发"）



@dataclass
class ScoreBreakdown:
    """评分分解（Factor 乘法模型）"""
    entity_type: str                      # 'breakout'
    entity_id: Optional[int]              # (unused, for compatibility)
    total_score: float                    # 总分
    broken_peak_ids: Optional[List[int]] = None  # 被突破的峰值ID
    # Factor 模型字段
    base_score: Optional[float] = None    # 基准分
    factors: Optional[List[FactorDetail]] = None  # Factor 列表
    def get_formula_string(self) -> str:
        """
        生成计算公式字符串

        Returns:
            加权模型: "60×30% + 75×20% + 75×30% + 82×20% = 72.5"
            Factor模型: "50 × 1.30 × 1.25 × 1.15 × 1.20 = 112.1"
        """
        # Factor 模型
        if self.factors is not None and self.base_score is not None:
            terms = [f"{self.base_score:.0f}"]
            for f in self.factors:
                if f.triggered:
                    terms.append(f"×{f.multiplier:.2f}")
            formula = " ".join(terms)
            return f"{formula} = {self.total_score:.1f}"

        # 加权模型（原有逻辑）
        terms = []
        for f in self.features:
            terms.append(f"{f.score:.0f}×{f.weight*100:.0f}%")

        formula = " + ".join(terms)
        return f"{formula} = {self.total_score:.1f}"


class BreakoutScorer:
    """突破评分器（Factor 乘法模型）"""

    def __init__(self, config: Optional[dict] = None):
        """初始化突破评分器（Factor 乘法模型）"""
        if config is None:
            config = {}

        # 基准分
        self.factor_base_score = config.get('factor_base_score', 50)

        # ATR 标准化配置（非注册因子，手动）
        self.use_atr_normalization = config.get('use_atr_normalization', False)
        self.atr_normalized_height_thresholds = config.get('atr_normalized_height_thresholds', [1.5, 2.5])
        self.atr_normalized_height_values = config.get('atr_normalized_height_values', [1.10, 1.20])

        # 所有注册因子配置（动态，defaults 来自 FACTOR_REGISTRY）
        self._factor_configs: dict[str, dict] = {}
        for fi in get_active_factors():
            cfg = config.get(fi.yaml_key, {})
            self._factor_configs[fi.key] = {
                'enabled': cfg.get('enabled', True),
                'thresholds': cfg.get('thresholds', list(fi.default_thresholds)),
                'values': cfg.get('values', list(fi.default_values)),
                'fi': fi,
            }

    def score_breakout(self, breakout: Breakout) -> float:
        """
        评估突破质量（使用 Factor 乘法模型）

        将分数写入breakout.quality_score

        Args:
            breakout: 突破点对象

        Returns:
            质量分数（可超过100）
        """
        breakdown = self.get_breakout_score_breakdown(breakout)
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


    # =========================================================================
    # Factor 乘法模型方法
    # =========================================================================

    def _get_factor_value(
        self,
        value: float,
        thresholds: List[float],
        factor_values: List[float],
    ) -> tuple:
        """
        根据阈值获取 factor 值（始终使用 >= 比较）

        通过 values 编码方向：values > 1.0 为奖励，< 1.0 为惩罚。
        YAML 中的 mode 字段仅供挖掘管道使用，评分系统不读取。

        Returns:
            (multiplier, level): factor 乘数和触发级别
        """
        multiplier = 1.0
        level = 0

        for i, threshold in enumerate(thresholds):
            if value >= threshold:
                multiplier = factor_values[i]
                level = i + 1
            else:
                break

        return multiplier, level

    @staticmethod
    def _transform_display(value, transform: str):
        """将原始值转换为显示值"""
        if transform == 'pct100':
            return value * 100
        elif transform == 'round1':
            return round(value, 1)
        elif transform == 'round2':
            return round(value, 2)
        return value

    def _compute_factor(self, key: str, raw_value) -> FactorDetail:
        """
        通用因子计算（从 FactorInfo 元数据驱动）

        处理顺序：nullable → zero_guard → enabled → 正常计算
        """
        cfg = self._factor_configs[key]
        fi = cfg['fi']

        # Nullable: None 表示因子对该 BO 不可算（lookback 不足 / 首次突破等）
        if raw_value is None:
            if fi.nullable:
                return FactorDetail(
                    name=fi.key, raw_value=0, unit=fi.unit,
                    multiplier=1.0, triggered=False, level=0,
                    unavailable=True,
                )
            raw_value = 0 if fi.is_discrete else 0.0

        # Zero guard: value <= 0 意味着无有效数据
        if fi.zero_guard and raw_value <= 0:
            return FactorDetail(
                name=fi.key, raw_value=0.0, unit=fi.unit,
                multiplier=1.0, triggered=False, level=0
            )

        display_value = self._transform_display(raw_value, fi.display_transform)

        if not cfg['enabled']:
            return FactorDetail(
                name=fi.key, raw_value=display_value, unit=fi.unit,
                multiplier=1.0, triggered=False, level=0
            )

        multiplier, level = self._get_factor_value(
            raw_value, cfg['thresholds'], cfg['values']
        )

        return FactorDetail(
            name=fi.key, raw_value=display_value, unit=fi.unit,
            multiplier=multiplier, triggered=(level > 0), level=level
        )

    def _get_atr_normalized_height_factor(self, atr_normalized_height: float) -> FactorDetail:
        """
        计算 ATR 标准化高度 factor（可选功能）

        突破幅度 / ATR 越大，表示突破越显著
        低波动率环境下的突破更有意义

        Args:
            atr_normalized_height: 突破幅度 / ATR

        Returns:
            FactorDetail
        """
        multiplier, level = self._get_factor_value(
            atr_normalized_height,
            self.atr_normalized_height_thresholds,
            self.atr_normalized_height_values
        )

        return FactorDetail(
            name="atr_height",
            raw_value=atr_normalized_height,
            unit="x",
            multiplier=multiplier,
            triggered=(level > 0),
            level=level
        )

    def get_breakout_score_breakdown(self, breakout: Breakout) -> ScoreBreakdown:
        """获取突破评分的详细分解（Factor 乘法模型，从 FACTOR_REGISTRY 动态驱动）"""
        broken_peaks = breakout.broken_peaks
        factors = []

        if not broken_peaks:
            return ScoreBreakdown(
                entity_type='breakout', entity_id=None,
                total_score=0, broken_peak_ids=[],
                base_score=0, factors=[],
            )

        # 注册因子（动态遍历 FACTOR_REGISTRY）
        for fi in get_active_factors():
            raw = getattr(breakout, fi.key, None if fi.nullable else (0 if fi.is_discrete else 0.0))
            factors.append(self._compute_factor(fi.key, raw))

        # ATR 标准化高度 factor（可选功能，非注册因子）
        if self.use_atr_normalization and breakout.atr_normalized_height > 0:
            atr_height_factor = self._get_atr_normalized_height_factor(breakout.atr_normalized_height)
            factors.append(atr_height_factor)

        # 总分（乘法聚合）
        base_score = self.factor_base_score
        total_multiplier = 1.0
        for f in factors:
            total_multiplier *= f.multiplier
        total_score = base_score * total_multiplier

        broken_peak_ids = [p.id for p in broken_peaks if p.id is not None]

        return ScoreBreakdown(
            entity_type='breakout', entity_id=None,
            total_score=total_score, broken_peak_ids=broken_peak_ids,
            base_score=base_score, factors=factors,
        )
