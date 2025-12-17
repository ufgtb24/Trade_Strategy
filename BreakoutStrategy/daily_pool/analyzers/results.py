"""
分析结果数据类

定义三个分析器的输出数据结构。
"""
from dataclasses import dataclass
from datetime import date
from typing import List, Optional


@dataclass
class SupportZone:
    """
    支撑区域

    由价格模式分析器检测，表示一个有效的支撑位区域。
    """
    price_low: float       # 区域下界
    price_high: float      # 区域上界
    test_count: int        # 测试次数
    strength: float        # 强度 (0-1)
    first_test_date: date  # 首次测试日期
    last_test_date: date   # 最近测试日期

    @property
    def center_price(self) -> float:
        """区域中心价格"""
        return (self.price_low + self.price_high) / 2

    @property
    def width(self) -> float:
        """区域宽度"""
        return self.price_high - self.price_low

    def __repr__(self) -> str:
        return (f"SupportZone(${self.price_low:.2f}-${self.price_high:.2f}, "
                f"tests={self.test_count}, strength={self.strength:.2f})")


@dataclass
class ConsolidationRange:
    """
    企稳区间

    由价格模式分析器计算，表示近期价格的波动区间。
    """
    upper_bound: float  # 区间上界
    lower_bound: float  # 区间下界
    center: float       # 区间中心
    width_atr: float    # 宽度（ATR单位）
    is_valid: bool      # 是否有效（宽度在允许范围内）

    @property
    def width(self) -> float:
        """区间宽度（价格单位）"""
        return self.upper_bound - self.lower_bound

    def contains(self, price: float) -> bool:
        """价格是否在区间内"""
        return self.lower_bound <= price <= self.upper_bound

    def is_above(self, price: float) -> bool:
        """价格是否在区间上方"""
        return price > self.upper_bound

    def is_below(self, price: float) -> bool:
        """价格是否在区间下方"""
        return price < self.lower_bound

    def __repr__(self) -> str:
        status = "valid" if self.is_valid else "invalid"
        return (f"ConsolidationRange(${self.lower_bound:.2f}-${self.upper_bound:.2f}, "
                f"width={self.width_atr:.2f}ATR, {status})")


@dataclass
class PricePatternResult:
    """
    价格模式分析结果

    PricePatternAnalyzer.analyze() 的输出。
    """
    pullback_depth_atr: float                    # 回调深度（ATR单位）
    support_zones: List[SupportZone]             # 支撑区间列表（按强度排序）
    consolidation_range: Optional[ConsolidationRange]  # 企稳区间
    price_position: str                          # "above_range" | "in_range" | "below_range" | "unknown"
    strongest_support: Optional[SupportZone]     # 最强支撑位

    @property
    def has_valid_consolidation(self) -> bool:
        """是否有有效的企稳区间"""
        return self.consolidation_range is not None and self.consolidation_range.is_valid

    @property
    def has_support(self) -> bool:
        """是否检测到支撑位"""
        return len(self.support_zones) > 0

    def __repr__(self) -> str:
        return (f"PricePatternResult(pullback={self.pullback_depth_atr:.2f}ATR, "
                f"supports={len(self.support_zones)}, position={self.price_position})")


@dataclass
class VolatilityResult:
    """
    波动率分析结果

    VolatilityAnalyzer.analyze() 的输出。
    """
    current_atr: float       # 当前ATR值
    atr_ratio: float         # 当前ATR / 初始ATR
    convergence_score: float # 收敛分数 (0-1)
    volatility_state: str    # "contracting" | "stable" | "expanding"

    @property
    def is_contracting(self) -> bool:
        """波动率是否在收缩"""
        return self.volatility_state == "contracting"

    @property
    def is_expanding(self) -> bool:
        """波动率是否在扩张"""
        return self.volatility_state == "expanding"

    def __repr__(self) -> str:
        return (f"VolatilityResult(ATR={self.current_atr:.2f}, "
                f"ratio={self.atr_ratio:.2f}, convergence={self.convergence_score:.2f}, "
                f"state={self.volatility_state})")


@dataclass
class VolumeResult:
    """
    成交量分析结果

    VolumeAnalyzer.analyze() 的输出。
    """
    baseline_volume: float         # 基准成交量
    current_volume: float          # 当前成交量
    volume_expansion_ratio: float  # 放量比率（当前/基准）
    surge_detected: bool           # 是否检测到放量
    volume_trend: str              # "increasing" | "neutral" | "decreasing"

    @property
    def is_above_baseline(self) -> bool:
        """成交量是否高于基准"""
        return self.volume_expansion_ratio > 1.0

    def __repr__(self) -> str:
        surge = "surge" if self.surge_detected else "normal"
        return (f"VolumeResult(ratio={self.volume_expansion_ratio:.2f}x, "
                f"{surge}, trend={self.volume_trend})")
