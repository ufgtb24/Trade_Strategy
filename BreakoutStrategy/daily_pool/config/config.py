"""
Daily 池配置类定义

包含所有配置 dataclass:
- PhaseConfig: 阶段转换参数
- PricePatternConfig: 价格模式分析参数
- VolatilityConfig: 波动率分析参数
- VolumeConfig: 成交量分析参数
- SignalConfig: 信号生成参数
- DailyPoolConfig: 顶层配置聚合
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PhaseConfig:
    """
    阶段转换配置

    控制状态机各阶段转换的条件阈值。
    所有价格相关阈值均以ATR为单位，自动适应不同股票。
    """

    # ===== INITIAL -> PULLBACK =====
    pullback_trigger_atr: float = 0.3  # 回调触发阈值（ATR单位）

    # ===== PULLBACK -> CONSOLIDATION =====
    min_convergence_score: float = 0.5  # 最小波动收敛分数
    min_support_tests: int = 2          # 最小支撑测试次数

    # ===== CONSOLIDATION -> REIGNITION =====
    min_volume_expansion: float = 1.5   # 最小放量倍数
    breakout_confirm_days: int = 1      # 突破确认天数

    # ===== 失败条件 =====
    max_drop_from_breakout_atr: float = 1.5  # 最大回调深度（ATR单位）
    support_break_buffer_atr: float = 0.5    # 支撑破位缓冲（ATR单位）
    max_pullback_days: int = 15              # 回调阶段最长天数
    max_consolidation_days: int = 20         # 企稳阶段最长天数
    max_observation_days: int = 30           # 总观察期最长天数


@dataclass
class PricePatternConfig:
    """
    价格模式分析配置

    控制支撑位检测和企稳区间计算的参数。
    """

    # ===== 支撑位检测 =====
    min_touches: int = 2              # 最小触及次数
    touch_tolerance_atr: float = 0.1  # 触及容差（ATR单位）
    local_min_window: int = 2         # 局部最低点检测窗口

    # ===== 企稳区间 =====
    consolidation_window: int = 10    # 企稳区间计算窗口（天）
    max_width_atr: float = 2.0        # 最大区间宽度（ATR单位）


@dataclass
class VolatilityConfig:
    """
    波动率分析配置

    控制ATR计算和波动收敛检测的参数。
    """
    atr_period: int = 14              # ATR计算周期
    lookback_days: int = 20           # 收敛分析回看天数
    contraction_threshold: float = 0.8  # 收缩判定阈值（当前ATR/初始ATR）


@dataclass
class VolumeConfig:
    """
    成交量分析配置

    控制基准量计算和放量检测的参数。
    """
    baseline_period: int = 20         # 基准量计算周期
    expansion_threshold: float = 1.5  # 放量判定阈值


@dataclass
class SignalConfig:
    """
    信号生成配置

    控制置信度计算和仓位分配的参数。
    """

    # 置信度权重
    confidence_weights: Dict[str, float] = field(default_factory=lambda: {
        'convergence': 0.30,  # 波动收敛权重
        'support': 0.25,      # 支撑强度权重
        'volume': 0.25,       # 放量程度权重
        'quality': 0.20,      # 突破质量权重
    })

    # 仓位分配（按信号强度）
    position_sizing: Dict[str, float] = field(default_factory=lambda: {
        'strong': 0.15,   # 强信号仓位
        'normal': 0.10,   # 普通信号仓位
        'weak': 0.05,     # 弱信号仓位
    })


@dataclass
class DailyPoolConfig:
    """
    Daily 池顶层配置

    聚合所有子配置，提供统一的配置入口。
    """
    phase: PhaseConfig = field(default_factory=PhaseConfig)
    price_pattern: PricePatternConfig = field(default_factory=PricePatternConfig)
    volatility: VolatilityConfig = field(default_factory=VolatilityConfig)
    volume: VolumeConfig = field(default_factory=VolumeConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)

    # 全局配置
    keep_history: bool = True  # 是否保留完整历史

    @classmethod
    def default(cls) -> 'DailyPoolConfig':
        """创建默认配置"""
        return cls()

    @classmethod
    def conservative(cls) -> 'DailyPoolConfig':
        """
        创建保守配置

        特点: 更严格的企稳要求、更强的放量要求、更紧的止损
        """
        return cls(
            phase=PhaseConfig(
                min_convergence_score=0.6,
                min_volume_expansion=1.8,
                max_drop_from_breakout_atr=1.2,
                breakout_confirm_days=2,
            ),
            signal=SignalConfig(
                position_sizing={
                    'strong': 0.12,
                    'normal': 0.08,
                    'weak': 0.04,
                }
            ),
        )

    @classmethod
    def aggressive(cls) -> 'DailyPoolConfig':
        """
        创建激进配置

        特点: 更宽松的企稳要求、较小放量也触发、更宽容的止损
        """
        return cls(
            phase=PhaseConfig(
                min_convergence_score=0.4,
                min_volume_expansion=1.3,
                max_drop_from_breakout_atr=2.0,
                breakout_confirm_days=1,
            ),
            signal=SignalConfig(
                position_sizing={
                    'strong': 0.20,
                    'normal': 0.15,
                    'weak': 0.08,
                }
            ),
        )
