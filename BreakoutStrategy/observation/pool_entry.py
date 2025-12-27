"""
观察池条目数据结构

定义观察池中每个条目的数据结构，支持：
- 从 Breakout 对象创建
- 数据库序列化/反序列化
- 状态追踪和生命周期管理
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from BreakoutStrategy.analysis import Breakout, Peak


@dataclass
class PoolEntry:
    """
    观察池条目

    设计决策：
    - 内存态：直接引用 Peak/Breakout 对象（类型安全）
    - 持久化：提取关键字段 + 序列化完整对象（查询效率）
    """

    # ===== 基本信息（必需）=====
    symbol: str
    add_date: date
    breakout_date: date

    # ===== 直接引用（内存态，可选）=====
    breakout: Optional['Breakout'] = None
    broken_peaks: List['Peak'] = field(default_factory=list)

    # ===== 冗余关键字段（查询优化）=====
    quality_score: float = 0.0
    breakout_price: float = 0.0
    highest_peak_price: float = 0.0
    num_peaks_broken: int = 0

    # ===== 状态 =====
    pool_type: str = 'realtime'  # 'realtime' | 'daily'
    # 状态值: 'active' | 'monitoring' | 'confirmed' | 'bought' | 'timeout' | 'expired' | 'failed'
    status: str = 'active'
    retry_count: int = 0

    # ===== 监控状态（实盘用）=====
    last_price: Optional[float] = None
    last_update: Optional[datetime] = None

    # ===== 买入评估状态 =====
    monitoring_start_time: Optional[datetime] = None  # 开始监控时间
    last_evaluation_score: float = 0.0                # 最近评估分数
    peak_price_since_add: float = 0.0                 # 加入后最高价
    lowest_price_since_add: float = 0.0               # 加入后最低价
    evaluation_count: int = 0                          # 评估次数
    baseline_volume: float = 0.0                       # 基准成交量 (MA20)

    # ===== 元数据 =====
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    id: Optional[int] = None

    # ===== 工厂方法 =====

    @classmethod
    def from_breakout(cls,
                          bo: 'Breakout',
                          pool_type: str = 'realtime') -> 'PoolEntry':
        """
        从 Breakout 对象创建 PoolEntry

        Args:
            bo: Breakout 对象
            pool_type: 池类型 ('realtime' 或 'daily')

        Returns:
            新创建的 PoolEntry 实例
        """
        highest_peak_price = bo.price
        if bo.broken_peaks:
            highest_peak_price = max(p.price for p in bo.broken_peaks)

        return cls(
            symbol=bo.symbol,
            add_date=date.today(),
            breakout_date=bo.date,
            breakout=bo,
            broken_peaks=list(bo.broken_peaks) if bo.broken_peaks else [],
            quality_score=bo.quality_score or 0.0,
            breakout_price=bo.price,
            highest_peak_price=highest_peak_price,
            num_peaks_broken=bo.num_peaks_broken,
            pool_type=pool_type
        )

    # ===== 序列化方法 =====

    def to_db_dict(self) -> Dict:
        """
        转换为数据库存储格式

        Returns:
            适合数据库存储的字典
        """
        return {
            'symbol': self.symbol,
            'add_date': self.add_date.isoformat(),
            'breakout_date': self.breakout_date.isoformat(),
            'quality_score': self.quality_score,
            'breakout_price': self.breakout_price,
            'highest_peak_price': self.highest_peak_price,
            'num_peaks_broken': self.num_peaks_broken,
            'pool_type': self.pool_type,
            'status': self.status,
            'retry_count': self.retry_count,
            'last_price': self.last_price,
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    @classmethod
    def from_db_dict(cls, data: Dict) -> 'PoolEntry':
        """
        从数据库记录创建 PoolEntry

        Args:
            data: 数据库查询返回的字典

        Returns:
            新创建的 PoolEntry 实例
        """
        last_update = None
        if data.get('last_update'):
            last_update = datetime.fromisoformat(data['last_update'])

        return cls(
            id=data.get('id'),
            symbol=data['symbol'],
            add_date=date.fromisoformat(data['add_date']),
            breakout_date=date.fromisoformat(data['breakout_date']),
            quality_score=data.get('quality_score', 0.0),
            breakout_price=data.get('breakout_price', 0.0),
            highest_peak_price=data.get('highest_peak_price', 0.0),
            num_peaks_broken=data.get('num_peaks_broken', 0),
            pool_type=data.get('pool_type', 'realtime'),
            status=data.get('status', 'active'),
            retry_count=data.get('retry_count', 0),
            last_price=data.get('last_price'),
            last_update=last_update,
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at'])
        )

    # ===== 派生属性 =====

    @property
    def days_in_pool(self) -> int:
        """在池中的天数"""
        return (date.today() - self.add_date).days

    @property
    def days_since_breakout(self) -> int:
        """突破后的天数"""
        return (date.today() - self.breakout_date).days

    @property
    def is_active(self) -> bool:
        """是否处于活跃状态"""
        return self.status == 'active'

    # ===== 状态操作 =====

    def mark_bought(self) -> None:
        """标记为已买入"""
        self.status = 'bought'
        self.updated_at = datetime.now()

    def mark_timeout(self) -> None:
        """标记为超时（实时池超时）"""
        self.status = 'timeout'
        self.updated_at = datetime.now()

    def mark_expired(self) -> None:
        """标记为过期（日K池过期）"""
        self.status = 'expired'
        self.updated_at = datetime.now()

    def mark_monitoring(self) -> None:
        """标记为监控中（进入实时监控）"""
        self.status = 'monitoring'
        self.monitoring_start_time = datetime.now()
        self.updated_at = datetime.now()

    def mark_confirmed(self) -> None:
        """标记为确认买入（评估通过，等待执行）"""
        self.status = 'confirmed'
        self.updated_at = datetime.now()

    def mark_failed(self, reason: str = '') -> None:
        """标记为失败（跌破阈值等，从观察池移出）"""
        self.status = 'failed'
        self.updated_at = datetime.now()

    def update_evaluation(self, score: float, price: float) -> None:
        """
        更新评估状态

        Args:
            score: 评估分数
            price: 当前价格
        """
        self.last_evaluation_score = score
        self.evaluation_count += 1
        self.last_price = price
        self.last_update = datetime.now()
        self.updated_at = datetime.now()

        # 更新价格极值
        if price > 0:
            if self.peak_price_since_add == 0 or price > self.peak_price_since_add:
                self.peak_price_since_add = price
            if self.lowest_price_since_add == 0 or price < self.lowest_price_since_add:
                self.lowest_price_since_add = price

    def update_price(self, price: float) -> None:
        """更新最新价格"""
        self.last_price = price
        self.last_update = datetime.now()
        self.updated_at = datetime.now()

    def __repr__(self) -> str:
        return (f"PoolEntry(symbol={self.symbol!r}, pool_type={self.pool_type!r}, "
                f"status={self.status!r}, quality_score={self.quality_score:.2f})")
