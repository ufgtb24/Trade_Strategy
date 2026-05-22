"""三段标签解析(design §1.2)。kwarg > key > 类名/pattern_label 默认。"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Set

from path2.core import Event


def _default_label(ev: Event) -> str:
    # PatternMatch 用 pattern_label 替代类名默认(design §2.2,解嵌套硬伤)
    pl = getattr(ev, "pattern_label", None)
    return pl if pl else type(ev).__name__


def resolve_labels(
    positional: Iterable[Iterable[Event]],
    named: Dict[str, Iterable[Event]],
    key: Optional[Callable[[Event], str]],
    strict_key: bool,
    endpoint_labels: Set[str],
) -> Dict[str, List[Event]]:
    """返回 {label: 物化列表(按 end_idx 升序)}。

    输入流本就 §1.2.2 end_idx 升序;此处物化并稳定排序兜底。
    """
    out: Dict[str, List[Event]] = {}

    # 1) 具名流(kwarg)最高优先
    for label, stream in named.items():
        out[label] = list(stream)

    pos = [list(s) for s in positional]

    if key is not None:
        # 2) key 函数:把所有 positional 事件按 key 分桶
        for stream in pos:
            for ev in stream:
                lab = key(ev)
                if lab not in endpoint_labels:
                    if strict_key:
                        raise ValueError(
                            f"key 返回未知标签 {lab!r}(不在 edges 端点集)"
                        )
                    continue  # 宽松:丢弃杂事件
                out.setdefault(lab, []).append(ev)
    else:
        # 3) 类名 / pattern_label 默认
        for stream in pos:
            if not stream:
                raise ValueError("positional 空流无法推断默认标签")
            lab = _default_label(stream[0])
            if lab in out:
                raise ValueError(
                    f"positional 流出现同类名标签 {lab!r} 冲突,"
                    f"请改用 kwarg 显式命名"
                )
            out[lab] = list(stream)

    # 端点必须全部解析到来源
    missing = endpoint_labels - set(out)
    if missing:
        raise ValueError(
            f"edges 端点标签无法解析到事件流: {sorted(missing)}"
        )

    # 稳定排序兜底(end_idx 升序)
    for lab in out:
        out[lab].sort(key=lambda e: e.end_idx)
    return out
