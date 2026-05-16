"""默认 event_id 生成器(#3/#4 共享件的 #3 内联桩)。

契约:(kind:str, start_idx:int, end_idx:int) -> str,返回 f"{kind}_{start}_{end}"。
#4 落地共享件后替换本桩,签名冻结不变 → 零改 #3。
"""
from __future__ import annotations


def default_event_id(kind: str, start_idx: int, end_idx: int) -> str:
    return f"{kind}_{start_idx}_{end_idx}"
