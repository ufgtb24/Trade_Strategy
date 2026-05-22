"""stdlib event_id 生成。

两个语义刻意不同、互不依赖的函数(spec §4):

- `default_event_id` = #3 PatternDetector 专用内部件。跨成员 span
  概念上恒区间,s==e 亦输出 `f"{kind}_{s}_{e}"`(`_advance.py` 依赖、
  `test_ids.py` 已 pin)。**不对外暴露**。
- `span_id` = #4 单点/区间事件公开便利。单点(start==end)塌缩为
  `f"{kind}_{start}"`,区间为 `f"{kind}_{start}_{end}"`,吸收 dogfood
  两种真实惯例(`vs_{i}` / `vc_{s}_{e}`)。

原「#4 替换本桩」预期经 #4 设计核查作废:#3 已用 pinned 测试主动
锁定区间语义,#3/#4 id 语义本质不同,无可共享单一桩。勿未来误归一。
"""
from __future__ import annotations


def default_event_id(kind: str, start_idx: int, end_idx: int) -> str:
    return f"{kind}_{start_idx}_{end_idx}"


def span_id(kind: str, start_idx: int, end_idx: int) -> str:
    """单点(start==end)→ f"{kind}_{start}";区间 → f"{kind}_{start}_{end}"。"""
    return (
        f"{kind}_{start_idx}"
        if start_idx == end_idx
        else f"{kind}_{start_idx}_{end_idx}"
    )
