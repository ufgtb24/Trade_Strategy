# tests/path2/dag/test_anchor_same_span_disambiguation.py
"""同 span 上游多实例的 anchor 消歧回归(交错标注重构的核心收益证明)。

背景:重构前 anchor_bo_id 用 span 坐标,两个同 span 上游实例的 anchor 完全相等,
_anchor_ok 对交叉组合(A1-B2、A2-B1)全部放行 ⇒ match 虚增。重构后 anchor_bo_id
= 源 instance_id,_anchor_ok 按 instance_id 比较,交叉绑定被挡死。"""
from dataclasses import dataclass
from typing import ClassVar

import pandas as pd

from path2.atoms.breakout import BOEvent
from path2.atoms.throwback import ThrowbackEvent
from path2.dag.edges import TemporalEdge
from path2.dag.engine import analyze
from path2.dag.nodes import NodeSpec
from path2.dag.result import Event
from path2.dag.spec import PatternSpec


def _edge():
    return TemporalEdge("bo", "tb", min_gap=1, max_gap=20, anchor_field="anchor_bo_id")


def test_anchor_ok_distinguishes_same_span_instances():
    """A1/A2 同 span、不同 instance_id;dst 锚 A1 ⇒ _anchor_ok(A1,dst)=True、(A2,dst)=False。"""
    a1 = BOEvent(start_idx=10, end_idx=10, confirm_idx=10, node_id="bo", instance_id="bo_10#0")
    a2 = BOEvent(start_idx=10, end_idx=10, confirm_idx=10, node_id="bo", instance_id="bo_10#1")
    dst = ThrowbackEvent(start_idx=12, end_idx=14, confirm_idx=12, anchor_bo_id="bo_10#0")
    e = _edge()
    assert e._anchor_ok(a1, dst) is True     # A1 是 dst 的源
    assert e._anchor_ok(a2, dst) is False     # A2 同 span 但不同实例 → 不应错绑(重构前此处为 True)


@dataclass(frozen=True)
class _SrcEv(Event):
    """同 span 多实例的上游。seq 仅区分同 span 实例值(规避 runner 单 run 全等去重)。"""
    is_point: ClassVar[bool] = True
    seq: int = 0


@dataclass(frozen=True)
class _DstEv(Event):
    """锚定单个 src 的下游。anchor_to_src 存源 instance_id。"""
    is_point: ClassVar[bool] = True
    anchor_to_src: str = ""


class _Canned:
    """不跑真实 detect,直接吐预算好的事件(同 test_anchor_c1_off_fuzz 套路)。"""
    def __init__(self, evs, cls):
        self._evs = evs
        self.event_cls = cls
    def detect(self, *source):
        return iter(self._evs)


def test_same_span_upstream_no_cross_match():
    """两个同 span src(S#0/S#1)各产一个 dst 锚定自己 ⇒ solve 恰好 2 match,无交叉。

    本 fixture 的 dst anchor 硬编码为 instance_id 形态(src_10#0/src_10#1)。重构前
    _anchor_ok 按 span 比较:src 的 span 形态 anchor 为 src_10,与 dst 的 src_10#0 不匹配
    ⇒ 全 False ⇒ 0 match(此断言 ==2 即 RED)。重构后按 instance_id 比较:S#0 配 dst_a、
    S#1 配 dst_b,恰 2 match,无交叉错绑。"""
    s0 = _SrcEv(start_idx=10, end_idx=10, confirm_idx=10, seq=0)
    s1 = _SrcEv(start_idx=10, end_idx=10, confirm_idx=10, seq=1)   # 与 s0 同 span
    # dst 在 detect 期读 src.instance_id 写 anchor —— 须先标注 src(模拟交错标注效果)
    da = _DstEv(start_idx=15, end_idx=15, confirm_idx=15, anchor_to_src="src_10#0")
    db = _DstEv(start_idx=16, end_idx=16, confirm_idx=16, anchor_to_src="src_10#1")
    spec = PatternSpec(
        pattern_id="same_span_anchor",
        nodes=(NodeSpec("src", _Canned([s0, s1], _SrcEv)),
               NodeSpec("dst", _Canned([da, db], _DstEv))),
        edges=(TemporalEdge("src", "dst", min_gap=1, max_gap=20, anchor_field="anchor_to_src"),),
    )
    df = pd.DataFrame({"open": [1]*20, "high": [1]*20, "low": [1]*20, "close": [1]*20, "volume": [1]*20})
    res = analyze(spec, df)
    # 重构前 0 match(anchor 形态不匹配),重构后 2 match(无交叉)
    assert len(res.matches) == 2, f"期望 2 match(无交叉),实际 {len(res.matches)}"


def test_interleave_instance_numbering_unchanged():
    """交错标注必须产出与批量标注逐字一致的 instance_id(characterization:重构前代码亦绿)。
    锚定:同 node 同 span → #0/#1 流序;同 node 不同 span → 各自 #0;多 node 各自独立计数。"""
    a_events = [
        _SrcEv(start_idx=10, end_idx=10, confirm_idx=10, seq=0),   # src_10#0
        _SrcEv(start_idx=10, end_idx=10, confirm_idx=10, seq=1),   # src_10#1(同 span 第二条)
        _SrcEv(start_idx=20, end_idx=20, confirm_idx=20, seq=0),   # src_20#0(不同 span 重置)
    ]
    spec = PatternSpec(
        pattern_id="numbering_invariant",
        nodes=(NodeSpec("src", _Canned(a_events, _SrcEv)),
               NodeSpec("dst", _Canned([_DstEv(start_idx=15, end_idx=15, confirm_idx=15)], _DstEv))),
        edges=(TemporalEdge("src", "dst", min_gap=1, max_gap=20),),   # 无 anchor,纯验编号
    )
    df = pd.DataFrame({"open": [1]*20, "high": [1]*20, "low": [1]*20, "close": [1]*20, "volume": [1]*20})
    res = analyze(spec, df)
    assert sorted(e.instance_id for e in res.events if e.node_id == "src") == ["src_10#0", "src_10#1", "src_20#0"]
    assert [e.instance_id for e in res.events if e.node_id == "dst"] == ["dst_15#0"]
