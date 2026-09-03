from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Tuple

from path2 import config
from path2.core import DEFAULT_STREAM, Event, stream_schema


def _check_stream(events: List[Event], stream_name) -> None:
    """单条流的跨事件检查(原 run 的检查逻辑,按流调用)。"""
    last_end = None
    seen_by_id: dict[str, list[Event]] = {}
    for ev in events:
        if not isinstance(ev, Event):
            raise TypeError(f"Detector 必须 yield Event,得到 {type(ev).__name__}")
        if last_end is not None and ev.end_idx < last_end:
            raise ValueError(
                f"yield 违反 end_idx 升序:{ev.end_idx} < {last_end}(流 {stream_name!r})"
            )
        bucket = seen_by_id.setdefault(ev.instance_id, [])
        if any(prev == ev for prev in bucket):
            raise ValueError(f"instance_id 单 run 内完全重复对象:{ev.instance_id}")
        bucket.append(ev)
        last_end = ev.end_idx


def _tagged(detector, *source) -> Iterator[Tuple[Optional[str], Event]]:
    """统一线格式:单流 detector 的裸 Event 归一化成 (None, ev)。"""
    multi = bool(getattr(detector, "produces", None))
    for item in detector.detect(*source):
        yield (item if multi else (DEFAULT_STREAM, item))


def run_bundle(detector, *source) -> Dict[Optional[str], List[Event]]:
    """detector → {流名: [Event]}。声明驱动(空流也存在)。RUNTIME_CHECKS 下逐流校验。"""
    schema = stream_schema(detector)
    out: Dict[Optional[str], List[Event]] = {name: [] for name in schema}
    for name, ev in _tagged(detector, *source):
        if name not in out:
            raise ValueError(f"detector 产出未声明流名 {name!r}(声明 {set(schema)})")
        out[name].append(ev)
    if config.RUNTIME_CHECKS:
        for name, evs in out.items():
            _check_stream(evs, name)
    return out


def run(detector, *source) -> Iterator[Event]:
    """推荐的 Detector 驱动入口(单流)。多流 detector 显式拒绝,不静默拍平。

    单事件不变式由 Event.__post_init__ 在构造点保证;此处只做需要
    跨事件状态的检查:end_idx 升序 + 身份内无完全重复对象(实例流契约,
    与 AnalysisResult.__post_init__ 同语义:同 instance_id 多实例合法,
    仅禁全属性全等对象——重复 evaluate bug 信号)。detector 阶段的
    instance_id 为 None(物化标注后才有),故按 None 归桶等价于全流一个桶。
    """
    if getattr(detector, "produces", None):
        raise ValueError("多流 detector 请用 run_bundle(detector, ...)(产 {流名: [Event]})")
    gen = detector.detect(*source)
    if not config.RUNTIME_CHECKS:
        yield from gen
        return
    last_end = None
    seen_by_id: dict[str, list[Event]] = {}
    for ev in gen:
        if not isinstance(ev, Event):
            raise TypeError(
                f"Detector 必须 yield Event,得到 {type(ev).__name__}"
            )
        if last_end is not None and ev.end_idx < last_end:
            raise ValueError(
                f"yield 违反 end_idx 升序:{ev.end_idx} < {last_end}"
            )
        bucket = seen_by_id.setdefault(ev.instance_id, [])
        if any(prev == ev for prev in bucket):
            raise ValueError(f"instance_id 单 run 内完全重复对象:{ev.instance_id}")
        bucket.append(ev)
        last_end = ev.end_idx
        yield ev
