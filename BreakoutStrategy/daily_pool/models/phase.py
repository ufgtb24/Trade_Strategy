"""
阶段枚举定义

定义 Daily 池中条目可能处于的阶段状态，用于阶段状态机的状态管理。

阶段流转:
    INITIAL ──┬──> PULLBACK ──> CONSOLIDATION ──> REIGNITION ──> SIGNAL
              └──> CONSOLIDATION ─────────────────────────────────────┘

    任意阶段 ──> FAILED (回调过深/阶段超时)
    任意阶段 ──> EXPIRED (观察期满)
"""
from enum import Enum, auto


class Phase(Enum):
    """
    Daily 池阶段枚举

    阶段语义:
        INITIAL: 刚入池，等待行情发展（持续1-3天）
        PULLBACK: 健康回调，寻找支撑（持续3-15天）
        CONSOLIDATION: 企稳整理，蓄势待发（持续5-20天）
        REIGNITION: 放量启动，等待确认（持续1-3天）
        SIGNAL: 信号生成，可以交易（终态）
        FAILED: 观察失败，移出池（终态）
        EXPIRED: 观察期满，移出池（终态）
    """

    INITIAL = auto()        # 刚入池
    PULLBACK = auto()       # 回调中
    CONSOLIDATION = auto()  # 企稳整理
    REIGNITION = auto()     # 再启动
    SIGNAL = auto()         # 信号已生成（终态）
    FAILED = auto()         # 失败（终态）
    EXPIRED = auto()        # 过期（终态）

    @property
    def is_terminal(self) -> bool:
        """是否为终态"""
        return self in {Phase.SIGNAL, Phase.FAILED, Phase.EXPIRED}

    @property
    def is_active(self) -> bool:
        """是否为活跃状态（非终态）"""
        return not self.is_terminal

    @property
    def display_name(self) -> str:
        """显示名称"""
        names = {
            Phase.INITIAL: "Initial",
            Phase.PULLBACK: "Pullback",
            Phase.CONSOLIDATION: "Consolidation",
            Phase.REIGNITION: "Reignition",
            Phase.SIGNAL: "Signal",
            Phase.FAILED: "Failed",
            Phase.EXPIRED: "Expired",
        }
        return names.get(self, self.name)

    @property
    def description(self) -> str:
        """阶段描述"""
        descriptions = {
            Phase.INITIAL: "刚入池，等待行情发展",
            Phase.PULLBACK: "回调中，寻找支撑",
            Phase.CONSOLIDATION: "企稳整理，蓄势待发",
            Phase.REIGNITION: "放量启动，等待确认",
            Phase.SIGNAL: "信号已生成",
            Phase.FAILED: "观察失败",
            Phase.EXPIRED: "观察期满",
        }
        return descriptions.get(self, "")
