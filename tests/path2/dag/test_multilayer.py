"""E: super→burst→bo 三层独立 detector 流链 + 双身份不撞 id(engine 零改纯机制验证)。

三级 consumes 链:
  bo node    — 根节点(consumes_stream=None),合成 detector 直接 yield BOEvent
  burst node — consumes_stream="bo",BurstDetector 聚合 bo 流
  super node — consumes_stream="burst",SuperDetector 聚合 burst 流

双身份:BurstEvent 同时是:
  (a) burst node 流的顶层成员(进 res.events 一次)
  (b) SuperEvent.members 里的 child(不进 res.events 顶层)
→ event_id 不重复(result.py 的 AnalysisResult.__post_init__ 会在 RUNTIME_CHECKS 开启时校验)。
"""
from __future__ import annotations

import pandas as pd
from dataclasses import dataclass
from typing import Iterator, Tuple

from path2.core import Event
from path2.stdlib import span_id
from path2.atoms.breakout import BurstEvent, BurstDetector, BOEvent
from path2.dag.engine import analyze
from path2.dag.spec import PatternSpec, NodeSpec


# ── 合成 SuperEvent / SuperDetector (纯机制验证，E 无业务 app) ──────────────────

@dataclass(frozen=True)
class SuperEvent(Event):
    """三层中最高层:聚合一组 BurstEvent。"""
    class_id = "test_multilayer_super"
    members: Tuple[BurstEvent, ...] = ()

    def child_slots(self):
        return {"members": self.members}

    def children(self, name: str):
        if name == "members":
            return self.members
        raise KeyError(name)


class SuperDetector:
    """消费 burst 流,把全部 burst 聚合成单个 SuperEvent(机制演示用)。"""
    event_cls = SuperEvent

    def detect(self, bursts, df) -> Iterator[SuperEvent]:
        bl = sorted(bursts, key=lambda e: (e.start_idx, e.end_idx))
        if len(bl) >= 1:
            yield SuperEvent(
                event_id=span_id("super", bl[0].start_idx, bl[-1].end_idx),
                start_idx=bl[0].start_idx,
                end_idx=bl[-1].end_idx,
                members=tuple(bl),
            )


# ── 合成 bo detector（root；合成 BOEvent 避免依赖真实 K 线）────────────────────

def _bo(i, drought=60, peaks=(1,), vol=3.0):
    """构造一个 BOEvent(参照 test_burst.py::_bo() 签名)。"""
    return BOEvent(
        event_id=f"bo:{i}:{i}",
        start_idx=i,
        end_idx=i,
        drought=drought,
        pk_count=len(peaks),
        broken_peak_ids=peaks,
        vol_ratio=vol,
        peak_vol_max=0.0,
    )


class _SyntheticBoDetector:
    """合成 bo detector:detect(df) 直接 yield 预置 BOEvent(不依赖真实 K 线)。"""
    event_cls = BOEvent  # class_id == "bo"

    def __init__(self, bos):
        self._bos = bos

    def detect(self, df) -> Iterator[BOEvent]:
        yield from self._bos


# ── spec 装配 ──────────────────────────────────────────────────────────────────

def _build_spec():
    """构造三层 bo→burst→super consumes 链:
      bo   at [0, 2, 5]  → BurstDetector(gap_max=5, min_bos=3) 产 1 个 burst(chain all_ends:gap 2,3≤5 一簇,仅 end=5 前缀 ≥min_bos)
      burst               → SuperDetector 产 1 个 super(含该 burst 作 members)
    edges=() 合法;所有节点为孤立 role(匹配全被 A2 过滤,但 res.events 仍完整)。
    """
    bos = [
        _bo(0, drought=60, peaks=(1,), vol=3.0),
        _bo(2, drought=5, peaks=(2,), vol=4.0),
        _bo(5, drought=3, peaks=(3,), vol=2.0),
    ]
    bo_node = NodeSpec("bo", _SyntheticBoDetector(bos))
    burst_node = NodeSpec("burst", BurstDetector(gap_max=5, min_bos=3),
                          consumes_stream="bo")
    super_node = NodeSpec("super", SuperDetector(),
                          consumes_stream="burst")
    return PatternSpec(
        pattern_id="test_multilayer",
        display_name="三层流链机制验证",
        nodes=(bo_node, burst_node, super_node),
        edges=(),
        root="super",
    )


# ── 测试 ───────────────────────────────────────────────────────────────────────

def test_multilayer_chain_and_double_identity():
    """bo→burst→super 三级 consumes 链 + 双身份不撞 id。

    断言:
      (a) analyze 不抛异常 —— topo 自动编排 bo→burst→super 通畅运行
      (b) res.events event_id 全局唯一 —— burst 以顶层身份在 res.events 出现一次,
          虽然也作为 super.members 的 child,但 res.events 不展开 child_slots,不重复
      (c) 真实嵌套对象图 —— SuperEvent.members 含 BurstEvent,BurstEvent.members 含 BOEvent
    """
    spec = _build_spec()
    df = pd.DataFrame({"close": range(50), "volume": [1.0] * 50})

    # (a) engine 不抛异常(topo 编排 bo→burst→super 通)
    res = analyze(spec, df)

    # --- (b) event_id 唯一 ---
    event_ids = [e.event_id for e in res.events]
    assert len(event_ids) == len(set(event_ids)), (
        f"res.events event_id 重复: {len(event_ids) - len(set(event_ids))} 个"
    )

    # 三层 events 都应在顶层 (bo ×3 + burst ×1 + super ×1 = 5)
    assert len(event_ids) == 5, (
        f"期望 5 个顶层 events(3 bo + 1 burst + 1 super),实际 {len(event_ids)}: {event_ids}"
    )

    # BurstEvent 在 res.events 出现恰好一次(双身份核心:同一对象也在 super.members)
    burst_ids_in_top = [e.event_id for e in res.events if isinstance(e, BurstEvent)]
    assert len(burst_ids_in_top) == 1, (
        f"期望 burst 在顶层出现 1 次,实际 {len(burst_ids_in_top)}"
    )

    # --- (c) 真实嵌套对象图 ---
    super_events = [e for e in res.events if isinstance(e, SuperEvent)]
    assert len(super_events) == 1, f"期望 1 个 SuperEvent,实际 {len(super_events)}"

    sup = super_events[0]
    # 非空守卫(精确计数已由上面 res.events==5 钉死);此处只需保证 isinstance 循环真的跑
    assert len(sup.members) >= 1, "SuperEvent.members 应含至少一个 BurstEvent"
    for m in sup.members:
        assert isinstance(m, BurstEvent), (
            f"SuperEvent.members 元素应为 BurstEvent,实际 {type(m)}"
        )

    burst_event = sup.members[0]
    assert len(burst_event.members) >= 1, "BurstEvent.members 应含至少一个 BOEvent"
    for b in burst_event.members:
        assert isinstance(b, BOEvent), (
            f"BurstEvent.members 元素应为 BOEvent,实际 {type(b)}"
        )

    # 双身份核实:burst 对象在 res.events 顶层出现 AND 在 super.members 内
    burst_in_top = next(e for e in res.events if isinstance(e, BurstEvent))
    assert burst_in_top is burst_event, (
        "res.events 中的 BurstEvent 与 super.members[0] 应是同一对象(双身份)"
    )
