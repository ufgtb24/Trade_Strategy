"""ContextVar 层 · 让 detector / diagnose 内部可读当前处理的 symbol。

用途:
- driver 里 `if current_symbol.get() == 'DGNX': breakpoint()` 条件断点
- Stage 3 on_gate 采集 GateFailure.symbol 字段
- 日志前缀
"""
from contextvars import ContextVar
from typing import Optional

current_symbol: ContextVar[Optional[str]] = ContextVar('current_symbol', default=None)


def set_current_symbol(sym: Optional[str]) -> None:
    """任务开始 set,任务结束 reset(避免污染下个任务)。"""
    current_symbol.set(sym)
