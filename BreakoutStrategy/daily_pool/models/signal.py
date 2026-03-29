"""
Daily 池信号定义

定义买入信号及其相关枚举类型，用于:
- 信号类型分类
- 信号强度分级
- 交易参数建议
- 信号可解释性
"""
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict

from .phase import Phase


class SignalType(Enum):
    """
    信号类型

    目前仅支持再启动买入，未来可扩展其他类型。
    """
    REIGNITION_BUY = "reignition_buy"  # 再启动买入


class SignalStrength(Enum):
    """
    信号强度

    根据置信度分级:
    - STRONG: 置信度 >= 0.7
    - NORMAL: 置信度 >= 0.5
    - WEAK: 置信度 < 0.5
    """
    STRONG = "strong"
    NORMAL = "normal"
    WEAK = "weak"

    @property
    def display_name(self) -> str:
        """显示名称"""
        names = {
            SignalStrength.STRONG: "Strong",
            SignalStrength.NORMAL: "Normal",
            SignalStrength.WEAK: "Weak",
        }
        return names.get(self, self.value)


@dataclass
class DailySignal:
    """
    Daily 池买入信号

    当观察池中的条目达到 SIGNAL 阶段时生成，包含:
    - 信号基本信息（股票、日期、类型、强度）
    - 交易参数建议（入场价、止损价、仓位）
    - 可解释性信息（阶段历程、置信度、证据）
    """

    # ===== 信号基本信息 =====
    symbol: str
    signal_date: date
    signal_type: SignalType
    strength: SignalStrength

    # ===== 交易参数建议 =====
    entry_price: float           # 建议入场价
    stop_loss_price: float       # 建议止损价
    position_size_pct: float     # 建议仓位比例 (0-1)

    # ===== 可解释性信息 =====
    phase_when_signaled: Phase   # 信号生成时的阶段（应为SIGNAL）
    days_to_signal: int          # 从入池到信号的天数
    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0      # 置信度 (0-1)

    # ===== 派生属性 =====

    @property
    def risk_amount(self) -> float:
        """风险金额（入场价 - 止损价）"""
        return self.entry_price - self.stop_loss_price

    @property
    def risk_pct(self) -> float:
        """风险百分比"""
        if self.entry_price <= 0:
            return 0.0
        return self.risk_amount / self.entry_price

    @property
    def target_price(self) -> float:
        """目标价格（假设2倍风险收益比）"""
        return self.entry_price + 2 * self.risk_amount

    # ===== 可解释性方法 =====

    def get_explanation(self) -> str:
        """
        生成信号的可读解释

        Returns:
            格式化的信号解释文本
        """
        lines = [
            f"{self.symbol} triggered {self.signal_type.value} signal:",
            f"  - Days to signal: {self.days_to_signal}",
            f"  - Signal strength: {self.strength.display_name}",
            f"  - Confidence: {self.confidence:.1%}",
            f"  - Entry price: ${self.entry_price:.2f}",
            f"  - Stop loss: ${self.stop_loss_price:.2f} ({self.risk_pct:.1%} risk)",
            f"  - Position size: {self.position_size_pct:.1%}",
        ]

        # 添加证据摘要
        if self.evidence_summary:
            lines.append("  - Evidence:")
            for key, value in self.evidence_summary.items():
                if isinstance(value, float):
                    lines.append(f"      {key}: {value:.3f}")
                else:
                    lines.append(f"      {key}: {value}")

        return "\n".join(lines)

    # ===== 序列化方法 =====

    def to_dict(self) -> Dict[str, Any]:
        """转为字典（用于序列化）"""
        return {
            'symbol': self.symbol,
            'signal_date': self.signal_date.isoformat(),
            'signal_type': self.signal_type.value,
            'strength': self.strength.value,
            'entry_price': self.entry_price,
            'stop_loss_price': self.stop_loss_price,
            'position_size_pct': self.position_size_pct,
            'phase_when_signaled': self.phase_when_signaled.name,
            'days_to_signal': self.days_to_signal,
            'evidence_summary': self.evidence_summary,
            'confidence': self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DailySignal':
        """从字典创建（用于反序列化）"""
        return cls(
            symbol=data['symbol'],
            signal_date=date.fromisoformat(data['signal_date']),
            signal_type=SignalType(data['signal_type']),
            strength=SignalStrength(data['strength']),
            entry_price=data['entry_price'],
            stop_loss_price=data['stop_loss_price'],
            position_size_pct=data['position_size_pct'],
            phase_when_signaled=Phase[data['phase_when_signaled']],
            days_to_signal=data['days_to_signal'],
            evidence_summary=data.get('evidence_summary', {}),
            confidence=data.get('confidence', 0.0),
        )

    def __repr__(self) -> str:
        return (f"DailySignal(symbol={self.symbol!r}, "
                f"date={self.signal_date}, "
                f"strength={self.strength.value}, "
                f"confidence={self.confidence:.2f})")
