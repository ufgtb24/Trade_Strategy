"""
Simple Pool 数据模型

定义池条目 (PoolEntry) 和买入信号 (BuySignal) 的数据结构。
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional


@dataclass
class PoolEntry:
    """
    池条目 - 简化版，无状态机

    生命周期:
    1. 突破检测 -> 创建 PoolEntry
    2. 每日评估 -> 更新价格追踪，检查信号/放弃条件
    3. 触发信号 -> 生成 BuySignal，条目保留
    4. 触发放弃 -> 标记为非活跃，移出池
    """

    # === 标识信息 ===
    symbol: str
    entry_id: str  # 格式: {symbol}_{breakout_date}

    # === 突破信息 (不可变) ===
    breakout_date: date
    breakout_price: float
    peak_price: float      # 突破的峰值价格
    initial_atr: float     # 突破时的 ATR (用于标准化阈值)
    quality_score: float   # 突破质量评分 (0-100)
    pattern_label: str = "basic"  # 突破模式标签

    # === 价格追踪 (每日更新) ===
    post_high: float = 0.0           # 入池后最高价
    post_low: float = float('inf')   # 入池后最低价
    current_price: float = 0.0       # 当前收盘价

    # === 状态 ===
    is_active: bool = True           # 是否活跃
    signal_generated: bool = False   # 是否已生成信号

    # === 属性 ===

    @property
    def pullback_from_high(self) -> float:
        """从入池后高点的回调幅度 (价格单位)"""
        if self.post_high <= 0:
            return 0.0
        return self.post_high - self.current_price

    @property
    def pullback_from_high_atr(self) -> float:
        """从入池后高点的回调幅度 (ATR单位)"""
        if self.initial_atr <= 0:
            return 0.0
        return self.pullback_from_high / self.initial_atr

    @property
    def gain_from_breakout(self) -> float:
        """相对于突破价的涨幅"""
        if self.breakout_price <= 0:
            return 0.0
        return (self.current_price - self.breakout_price) / self.breakout_price

    def days_in_pool(self, as_of_date: date) -> int:
        """入池天数"""
        return (as_of_date - self.breakout_date).days

    # === 更新方法 ===

    def update_price_tracking(self, high: float, low: float, close: float) -> None:
        """
        更新价格追踪

        Args:
            high: 当日最高价
            low: 当日最低价
            close: 当日收盘价
        """
        self.post_high = max(self.post_high, high)
        if low > 0:
            self.post_low = min(self.post_low, low)
        self.current_price = close

    def mark_abandoned(self) -> None:
        """标记为已放弃"""
        self.is_active = False

    def mark_signaled(self) -> None:
        """标记为已生成信号"""
        self.signal_generated = True

    # === 序列化 ===

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            'symbol': self.symbol,
            'entry_id': self.entry_id,
            'breakout_date': self.breakout_date.isoformat(),
            'breakout_price': self.breakout_price,
            'peak_price': self.peak_price,
            'initial_atr': self.initial_atr,
            'quality_score': self.quality_score,
            'pattern_label': self.pattern_label,
            'post_high': self.post_high,
            'post_low': self.post_low if self.post_low != float('inf') else None,
            'current_price': self.current_price,
            'is_active': self.is_active,
            'signal_generated': self.signal_generated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PoolEntry':
        """从字典创建"""
        post_low = data.get('post_low')
        if post_low is None:
            post_low = float('inf')

        return cls(
            symbol=data['symbol'],
            entry_id=data['entry_id'],
            breakout_date=date.fromisoformat(data['breakout_date']),
            breakout_price=data['breakout_price'],
            peak_price=data['peak_price'],
            initial_atr=data['initial_atr'],
            quality_score=data['quality_score'],
            pattern_label=data.get('pattern_label', 'basic'),
            post_high=data.get('post_high', 0.0),
            post_low=post_low,
            current_price=data.get('current_price', 0.0),
            is_active=data.get('is_active', True),
            signal_generated=data.get('signal_generated', False),
        )

    def __repr__(self) -> str:
        status = "active" if self.is_active else "inactive"
        return (f"PoolEntry({self.symbol}, quality={self.quality_score:.1f}, "
                f"pullback={self.pullback_from_high_atr:.2f}ATR, {status})")


@dataclass
class BuySignal:
    """
    买入信号

    当条目满足所有买入条件时生成。
    """

    symbol: str
    signal_date: date
    entry_price: float       # 建议买入价 (当日收盘价)
    stop_loss: float         # 止损价

    # === 诊断信息 ===
    days_to_signal: int = 0  # 入池到信号的天数
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def risk_per_share(self) -> float:
        """每股风险"""
        return self.entry_price - self.stop_loss

    @property
    def risk_pct(self) -> float:
        """风险百分比"""
        if self.entry_price <= 0:
            return 0.0
        return self.risk_per_share / self.entry_price

    def position_size(self, capital: float, risk_pct: float = 0.02) -> int:
        """
        计算建议仓位

        Args:
            capital: 总资金
            risk_pct: 单笔风险比例 (默认 2%)

        Returns:
            建议股数
        """
        if self.risk_per_share <= 0:
            return 0
        risk_amount = capital * risk_pct
        return int(risk_amount / self.risk_per_share)

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            'symbol': self.symbol,
            'signal_date': self.signal_date.isoformat(),
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'days_to_signal': self.days_to_signal,
            'metrics': self.metrics,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BuySignal':
        """从字典创建"""
        return cls(
            symbol=data['symbol'],
            signal_date=date.fromisoformat(data['signal_date']),
            entry_price=data['entry_price'],
            stop_loss=data['stop_loss'],
            days_to_signal=data.get('days_to_signal', 0),
            metrics=data.get('metrics', {}),
        )

    def __repr__(self) -> str:
        return f"BuySignal({self.symbol}, {self.signal_date}, price={self.entry_price:.2f})"


@dataclass
class SignalPerformance:
    """
    信号后验表现指标

    在回测完成后计算，记录信号发出后的表现。
    与 ShadowResult 可比较的核心指标。
    """

    # === 信号引用 ===
    symbol: str
    signal_date: date
    entry_price: float

    # === MFE/MAE 核心指标 ===
    mfe: float           # 最大有利偏移 (%)
    mae: float           # 最大不利偏移 (%)
    mfe_day: int         # 达到 MFE 的天数
    mae_before_mfe: float  # MFE 前的最大回撤 (%)

    # === 终点指标 ===
    final_return: float  # 终点收益率 (%)
    max_drawdown: float  # 最大回撤 (%)

    # === 跟踪元数据 ===
    tracking_days: int   # 实际跟踪天数
    complete: bool       # 是否完成跟踪

    # === 成功标签 ===
    success_10: bool = False
    success_20: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            'symbol': self.symbol,
            'signal_date': self.signal_date.isoformat(),
            'entry_price': self.entry_price,
            'mfe': self.mfe,
            'mae': self.mae,
            'mfe_day': self.mfe_day,
            'mae_before_mfe': self.mae_before_mfe,
            'final_return': self.final_return,
            'max_drawdown': self.max_drawdown,
            'tracking_days': self.tracking_days,
            'complete': self.complete,
            'success_10': self.success_10,
            'success_20': self.success_20,
        }

    def __repr__(self) -> str:
        return (f"SignalPerformance({self.symbol}, {self.signal_date}, "
                f"MFE={self.mfe:.1f}%, MAE={self.mae:.1f}%)")
