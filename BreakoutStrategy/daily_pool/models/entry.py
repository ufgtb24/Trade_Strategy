"""
Daily 池条目数据结构

定义 Daily 池中每个条目的核心数据结构，包含:
- 突破信息（不可变）
- 阶段状态机引用
- 价格追踪
- 分析缓存
"""
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Dict, Optional

from .phase import Phase
from .history import PhaseHistory

if TYPE_CHECKING:
    from ..state_machine import PhaseStateMachine


@dataclass
class DailyPoolEntry:
    """
    Daily 池条目 - 核心数据结构

    设计理念:
        DailyPoolEntry 是突破后创建的跟踪记录，用于 Daily 池的阶段评估。
        与 Realtime 池的 PoolEntry 不同，它:
        - 使用阶段状态机而非评分
        - 关注变化过程而非当前状态
        - 需要历史价格序列而非单条K线

    生命周期:
        1. 检测到突破 -> 创建 DailyPoolEntry，phase=INITIAL
        2. 每日评估 -> 分析器分析 -> 状态机转换阶段
        3. 到达 SIGNAL -> 生成 DailySignal
        4. 到达 FAILED/EXPIRED -> 移出池
    """

    # ===== 标识信息 =====
    symbol: str
    entry_id: str  # 唯一标识，格式: {symbol}_{breakout_date}

    # ===== 突破信息（不可变）=====
    breakout_date: date
    breakout_price: float
    highest_peak_price: float  # 突破的最高峰值价格
    initial_atr: float         # 突破时的ATR（用于标准化阈值）
    quality_score: float       # 突破质量评分 (0-100)

    # ===== 阶段状态机 =====
    # 注意: phase_machine 在创建时由 DailyPoolManager 注入
    phase_machine: Optional['PhaseStateMachine'] = field(default=None, repr=False)
    phase_history: PhaseHistory = field(default_factory=PhaseHistory)

    # ===== 价格追踪 =====
    post_breakout_high: float = 0.0      # 突破后最高价
    post_breakout_low: float = float('inf')  # 突破后最低价
    current_price: float = 0.0           # 当前价格

    # ===== 分析缓存（避免重复计算）=====
    analysis_cache: Dict[str, Any] = field(default_factory=dict, repr=False)

    # ===== 派生属性 =====

    @property
    def current_phase(self) -> Phase:
        """当前阶段"""
        if self.phase_machine is None:
            return Phase.INITIAL
        return self.phase_machine.current_phase

    @property
    def is_active(self) -> bool:
        """是否处于活跃状态（非终态）"""
        return self.current_phase.is_active

    @property
    def days_in_pool(self) -> int:
        """入池天数"""
        return (date.today() - self.breakout_date).days

    @property
    def pullback_from_high(self) -> float:
        """从突破后高点的回调幅度（价格单位）"""
        if self.post_breakout_high <= 0:
            return 0.0
        return self.post_breakout_high - self.current_price

    @property
    def pullback_from_high_atr(self) -> float:
        """从突破后高点的回调幅度（ATR单位）"""
        if self.initial_atr <= 0:
            return 0.0
        return self.pullback_from_high / self.initial_atr

    @property
    def gain_from_breakout(self) -> float:
        """相对于突破价的涨幅"""
        if self.breakout_price <= 0:
            return 0.0
        return (self.current_price - self.breakout_price) / self.breakout_price

    # ===== 状态更新方法 =====

    def update_price_tracking(self, high: float, low: float, close: float) -> None:
        """
        更新价格追踪

        Args:
            high: 当日最高价
            low: 当日最低价
            close: 当日收盘价
        """
        self.post_breakout_high = max(self.post_breakout_high, high)
        if low > 0:
            self.post_breakout_low = min(self.post_breakout_low, low)
        self.current_price = close

    def clear_cache(self) -> None:
        """清除分析缓存"""
        self.analysis_cache.clear()

    def set_cache(self, key: str, value: Any) -> None:
        """设置缓存值"""
        self.analysis_cache[key] = value

    def get_cache(self, key: str, default: Any = None) -> Any:
        """获取缓存值"""
        return self.analysis_cache.get(key, default)

    # ===== 序列化方法 =====

    def to_dict(self) -> Dict[str, Any]:
        """转为字典（用于序列化）"""
        return {
            'symbol': self.symbol,
            'entry_id': self.entry_id,
            'breakout_date': self.breakout_date.isoformat(),
            'breakout_price': self.breakout_price,
            'highest_peak_price': self.highest_peak_price,
            'initial_atr': self.initial_atr,
            'quality_score': self.quality_score,
            'current_phase': self.current_phase.name,
            'phase_history': self.phase_history.to_dict(),
            'post_breakout_high': self.post_breakout_high,
            'post_breakout_low': self.post_breakout_low if self.post_breakout_low != float('inf') else None,
            'current_price': self.current_price,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DailyPoolEntry':
        """
        从字典创建（用于反序列化）

        注意: phase_machine 需要在创建后单独注入
        """
        post_breakout_low = data.get('post_breakout_low')
        if post_breakout_low is None:
            post_breakout_low = float('inf')

        return cls(
            symbol=data['symbol'],
            entry_id=data['entry_id'],
            breakout_date=date.fromisoformat(data['breakout_date']),
            breakout_price=data['breakout_price'],
            highest_peak_price=data['highest_peak_price'],
            initial_atr=data['initial_atr'],
            quality_score=data['quality_score'],
            phase_history=PhaseHistory.from_dict(data.get('phase_history', {})),
            post_breakout_high=data.get('post_breakout_high', 0.0),
            post_breakout_low=post_breakout_low,
            current_price=data.get('current_price', 0.0),
        )

    def __repr__(self) -> str:
        return (f"DailyPoolEntry(symbol={self.symbol!r}, "
                f"phase={self.current_phase.name}, "
                f"days={self.days_in_pool}, "
                f"quality={self.quality_score:.1f})")
