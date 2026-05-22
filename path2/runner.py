from __future__ import annotations

from typing import Iterator

from path2 import config
from path2.core import Event


def run(detector, *source) -> Iterator[Event]:
    """推荐的 Detector 驱动入口。流式 yield,顺带做跨事件检查。

    单事件不变式由 Event.__post_init__ 在构造点保证;此处只做需要
    跨事件状态的检查:end_idx 升序 + event_id 单 run 内唯一。
    """
    gen = detector.detect(*source)
    if not config.RUNTIME_CHECKS:
        yield from gen
        return
    last_end = None
    seen_ids: set[str] = set()
    for ev in gen:
        if not isinstance(ev, Event):
            raise TypeError(
                f"Detector 必须 yield Event,得到 {type(ev).__name__}"
            )
        if last_end is not None and ev.end_idx < last_end:
            raise ValueError(
                f"yield 违反 end_idx 升序:{ev.end_idx} < {last_end}"
            )
        if ev.event_id in seen_ids:
            raise ValueError(f"event_id 单 run 内重复:{ev.event_id}")
        last_end = ev.end_idx
        seen_ids.add(ev.event_id)
        yield ev
