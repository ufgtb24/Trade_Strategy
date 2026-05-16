"""PatternMatch:4 种 PatternDetector 的统一产出 Event 子类(design §2)。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from path2 import config
from path2.core import Event


@dataclass(frozen=True)
class PatternMatch(Event):
    # 协议层继承:event_id, start_idx, end_idx
    children: tuple[Event, ...] = ()
    role_index: Mapping[str, tuple[Event, ...]] | None = None  # 标签 -> 命中实例(恒 tuple)
    pattern_label: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not config.RUNTIME_CHECKS:
            return
        ri = self.role_index or {}
        # 各 role tuple 必须按 start_idx 升序
        for label, tup in ri.items():
            if list(tup) != sorted(tup, key=lambda e: e.start_idx):
                raise ValueError(
                    f"role_index['{label}'] 未按 start_idx 升序"
                )
        # children 必须按 start_idx 升序(§3.3)
        if list(self.children) != sorted(
            self.children, key=lambda e: e.start_idx
        ):
            raise ValueError("children 未按 start_idx 升序")
        # role_index 扁平化集合 == children 集合(两视图不漂移)
        flat = {id(e) for tup in ri.values() for e in tup}
        if flat != {id(e) for e in self.children}:
            raise ValueError(
                "role_index 扁平化集合 != children 集合"
            )
