# tests/path2/dag/test_tripwire.py
"""Sprint 1 Task 2(硬伤 C 兜底):diagnose 层构造 MatchContext 时若把 bound 传成
静默 None,一旦未来某条 where clause 想读兄弟 node 的绑定(跨节点 clause),会拿到
None 再被误判为"sibling 未绑定"这类可悄悄通过的假结论,产错值而不自知。

修法:diagnose.py 里 ctx.bound 一律用 _TRIPWIRE sentinel 代替 None——现有的一元
where(不读 bound)不受影响;一旦真有 clause 读它,立即抛显式 CrossNodePendingError,
不静默 fallback。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from path2.core import Event
from path2.dag._tripwire import _TRIPWIRE, CrossNodePendingError
from path2.dag.diagnose import diagnose
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


def test_tripwire_sentinel_exists():
    assert _TRIPWIRE is not None


def test_tripwire_read_raises_cross_node_pending():
    """任何操作访问 _TRIPWIRE 都应抛 CrossNodePendingError。"""
    with pytest.raises(CrossNodePendingError):
        _ = _TRIPWIRE + 1
    with pytest.raises(CrossNodePendingError):
        _ = _TRIPWIRE > 0
    with pytest.raises(CrossNodePendingError):
        _ = _TRIPWIRE["sibling"]
    with pytest.raises(CrossNodePendingError):
        _ = _TRIPWIRE.anything


@dataclass(frozen=True)
class _SoloEvent(Event):
    """tripwire fixture 用合成事件(单 node,无需伙伴 —— 只为触发 where 求值)。"""
    class_id = "diag_tripwire_solo"


class _FakeDet:
    """合成 detector:忽略输入源,直接吐已构造好的 canned 事件序列(同
    test_diagnose_anchor_ok.py 套路)。"""

    def __init__(self, evs, event_cls):
        self._evs = evs
        self.event_cls = event_cls

    def detect(self, *source):
        return iter(self._evs)


def _cross_node_where(e, ctx):
    """合成的"跨节点 clause":企图读兄弟 node 的绑定。diagnose 层当前不支持
    跨节点求值 —— 应立即撞 tripwire,不该悄悄拿到 None 再判定出一个假结论。"""
    return ctx.bound["sibling_node"] is not None


def test_diagnose_cross_node_where_raises_cross_node_pending():
    """diagnose() 内部构造的 ctx.bound 已是 _TRIPWIRE;一旦某 where clause 读它,
    立即抛 CrossNodePendingError,不静默 fallback 产错值。"""
    solo = _SoloEvent(event_id="solo1", start_idx=0, end_idx=1)
    nodes = (
        NodeSpec(
            node_id="solo",
            detector=_FakeDet([solo], _SoloEvent),
            where=(("reads_sibling", _cross_node_where),),
        ),
    )
    spec = PatternSpec(pattern_id="diag_tripwire_fixture", nodes=nodes, edges=())
    with pytest.raises(CrossNodePendingError):
        diagnose(spec, pd.DataFrame(), params=None)
