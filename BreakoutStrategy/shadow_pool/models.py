"""
Shadow Pool 数据模型

定义 Shadow Mode 使用的数据结构:
- ShadowEntry: 跟踪中的条目
- ShadowResult: 完成跟踪后的结果
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class ShadowEntry:
    """
    Shadow 池跟踪条目

    轻量级设计，无状态机，仅记录价格数据用于后续分析。

    生命周期:
    1. 突破入池时创建
    2. 每日更新价格序列
    3. 达到 tracking_days 后转为 ShadowResult
    """

    # ===== 标识 =====
    symbol: str
    entry_id: str  # {symbol}_{breakout_date}

    # ===== 突破信息（不可变）=====
    breakout_date: date
    breakout_price: float           # 突破价格
    highest_peak_price: float       # 被突破的峰值价格
    atr_value: float                # 突破时的 ATR
    quality_score: float            # 突破质量分数

    # ===== 突破特征 =====
    breakout_type: str = ''         # 'yang', 'yin', 'shadow'
    volume_surge_ratio: float = 1.0 # 放量倍数
    momentum: float = 0.0           # 动量
    gap_up_pct: float = 0.0         # 跳空百分比
    num_peaks_broken: int = 1       # 突破峰值数量

    # ===== 跟踪状态 =====
    tracking_days: int = 0          # 已跟踪天数
    entry_date: Optional[date] = None  # 入池日期（可能晚于突破日）

    # ===== 价格追踪 =====
    post_breakout_high: float = 0.0
    post_breakout_low: float = float('inf')
    current_price: float = 0.0

    # ===== 每日价格序列（用于计算 MFE/MAE）=====
    daily_highs: List[float] = field(default_factory=list)
    daily_lows: List[float] = field(default_factory=list)
    daily_closes: List[float] = field(default_factory=list)
    daily_dates: List[date] = field(default_factory=list)

    def update_price(self, high: float, low: float, close: float,
                     trade_date: date) -> None:
        """
        更新每日价格数据

        Args:
            high: 当日最高价
            low: 当日最低价
            close: 当日收盘价
            trade_date: 交易日期
        """
        self.daily_highs.append(high)
        self.daily_lows.append(low)
        self.daily_closes.append(close)
        self.daily_dates.append(trade_date)

        self.post_breakout_high = max(self.post_breakout_high, high)
        self.post_breakout_low = min(self.post_breakout_low, low)
        self.current_price = close
        self.tracking_days += 1


@dataclass
class ShadowResult:
    """
    Shadow 池跟踪结果

    包含完整的突破特征和后续表现指标，用于分析和规则提取。
    """

    # ===== 标识 =====
    symbol: str
    breakout_date: date

    # ===== 突破信息 =====
    breakout_price: float
    highest_peak_price: float
    atr_value: float
    quality_score: float

    # ===== 突破特征 =====
    breakout_type: str
    volume_surge_ratio: float
    momentum: float
    gap_up_pct: float
    num_peaks_broken: int

    # ===== 后续表现指标 =====
    mfe: float                      # 最大有利偏移 (%)
    mae: float                      # 最大不利偏移 (%)
    mfe_day: int                    # 达到 MFE 的天数
    mae_before_mfe: float           # MFE 前的最大回撤 (%)
    final_return: float             # 终点收益率 (%)
    final_price: float              # 终点价格
    max_drawdown: float             # 最大回撤 (%)

    # ===== 跟踪元数据 =====
    tracking_days: int              # 实际跟踪天数
    complete: bool = True           # 是否完成跟踪（达到目标天数）

    # ===== 成功标签 =====
    success_10: bool = False        # 是否达到 +10%
    success_20: bool = False        # 是否达到 +20%
    success_50: bool = False        # 是否达到 +50%

    def to_dict(self) -> dict:
        """转换为字典，用于 JSON 序列化"""
        return {
            'symbol': self.symbol,
            'breakout_date': self.breakout_date.isoformat(),
            'breakout_price': round(self.breakout_price, 4),
            'highest_peak_price': round(self.highest_peak_price, 4),
            'atr_value': round(self.atr_value, 4),
            'quality_score': round(self.quality_score, 2),
            'breakout_type': self.breakout_type,
            'volume_surge_ratio': round(self.volume_surge_ratio, 2),
            'momentum': round(self.momentum, 4),
            'gap_up_pct': round(self.gap_up_pct, 4),
            'num_peaks_broken': self.num_peaks_broken,
            'mfe': round(self.mfe, 2),
            'mae': round(self.mae, 2),
            'mfe_day': self.mfe_day,
            'mae_before_mfe': round(self.mae_before_mfe, 2),
            'final_return': round(self.final_return, 2),
            'final_price': round(self.final_price, 4),
            'max_drawdown': round(self.max_drawdown, 2),
            'tracking_days': self.tracking_days,
            'complete': self.complete,
            'success_10': self.success_10,
            'success_20': self.success_20,
            'success_50': self.success_50,
        }
