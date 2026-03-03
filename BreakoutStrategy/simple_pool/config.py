"""
Simple Pool 配置

MVP 版本仅需 4 个核心参数，其余为固定参数。
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class SimplePoolConfig:
    """
    Simple Pool 配置类

    设计理念:
    - 最小化参数数量，避免过拟合
    - 每个参数都有明确的市场机制解释

    4 核心参数:
    - max_pullback_atr: 最大允许回调深度 (ATR单位)
    - support_lookback: 支撑位参考天数 (取近N天最低价)
    - volume_threshold: 放量阈值 (相对于MA20)
    - min_quality_score: 最小入池质量分
    """

    # === 4 核心参数 ===
    max_pullback_atr: float = 1.5
    """最大回调深度 (ATR单位)，超过此值不触发信号"""

    support_lookback: int = 10
    """支撑位参考天数，取近N天最低价作为支撑"""

    volume_threshold: float = 1.3
    """放量阈值，当日成交量需达到MA20的此倍数"""

    min_quality_score: float = 60.0
    """最小入池质量分 (0-100)"""

    # === 固定参数 (一般不需要调整) ===
    max_observation_days: int = 30
    """最大观察天数，超过则移出池"""

    volume_ma_period: int = 20
    """成交量均线周期"""

    price_ma_period: int = 5
    """价格均线周期 (用于判断上涨)"""

    abandon_buffer: float = 1.5
    """放弃阈值倍数，回调超过 max_pullback_atr * abandon_buffer 则放弃"""

    atr_period: int = 14
    """ATR 计算周期"""

    @classmethod
    def default(cls) -> 'SimplePoolConfig':
        """默认配置"""
        return cls()

    @classmethod
    def conservative(cls) -> 'SimplePoolConfig':
        """保守配置 - 更严格的条件"""
        return cls(
            max_pullback_atr=1.2,
            volume_threshold=1.5,
            min_quality_score=70.0
        )

    @classmethod
    def aggressive(cls) -> 'SimplePoolConfig':
        """激进配置 - 更宽松的条件"""
        return cls(
            max_pullback_atr=2.0,
            volume_threshold=1.2,
            min_quality_score=50.0
        )

    @classmethod
    def from_yaml(cls, path: str) -> 'SimplePoolConfig':
        """从 YAML 文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    def to_yaml(self, path: str) -> None:
        """保存配置到 YAML 文件"""
        data = {
            'max_pullback_atr': self.max_pullback_atr,
            'support_lookback': self.support_lookback,
            'volume_threshold': self.volume_threshold,
            'min_quality_score': self.min_quality_score,
            'max_observation_days': self.max_observation_days,
            'volume_ma_period': self.volume_ma_period,
            'price_ma_period': self.price_ma_period,
            'abandon_buffer': self.abandon_buffer,
            'atr_period': self.atr_period,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, default_flow_style=False)

    @property
    def abandon_threshold(self) -> float:
        """放弃阈值 (ATR单位)"""
        return self.max_pullback_atr * self.abandon_buffer
