from dataclasses import dataclass
from typing import Tuple
import pytest
from path2.core import Event
from path2.dag.engine import run_streams
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _Dual:
    """同一趟产两条流;产 'a' 两个、'b' 一个。计数验证只跑一次。"""
    produces = {"a": _E, "b": _E}
    def __init__(self): self.calls = 0
    def detect(self, df):
        self.calls += 1
        yield ("a", _E(start_idx=0, end_idx=0, confirm_idx=0))
        yield ("a", _E(start_idx=1, end_idx=1, confirm_idx=1))
        yield ("b", _E(start_idx=2, end_idx=2, confirm_idx=2))


def _df():
    import pandas as pd
    return pd.DataFrame({"open": [1,2,3], "high": [1,2,3], "low": [1,2,3],
                         "close": [1,2,3], "volume": [1,1,1]})


def test_multistream_both_nodes_filled():
    det = _Dual()
    spec = PatternSpec("p", nodes=[
        NodeSpec("a", det, produces_stream="a"),
        NodeSpec("b", det, produces_stream="b"),
    ], edges=())
    streams = run_streams(spec, _df())
    assert len(streams["a"]) == 2 and len(streams["b"]) == 1
    assert det.calls == 1          # ★ 同一 detect 调用只跑一次
    assert all(e.instance_id is not None for e in streams["a"] + streams["b"])
    assert streams["a"][0].node_id == "a" and streams["b"][0].node_id == "b"


def test_multistream_unknown_stream_raises():
    det = _Dual()
    with pytest.raises(ValueError, match="zz"):
        PatternSpec("p", nodes=[
            NodeSpec("a", det, produces_stream="a"),
            NodeSpec("x", det, produces_stream="zz"),
        ], edges=())


def test_ref_slots_translated_to_instance_ids():
    # note 事件引用 high 事件:同源两流,标注后 note.ref_slots()['anchor'] 应翻成 high 的 instance_id
    from path2.core import Event as _EventBase

    @dataclass(frozen=True)
    class _Pair(_EventBase):
        start_idx: int = 0
        end_idx: int = 0
        confirm_idx: int = 0
        anchor_refs: Tuple[Event, ...] = ()
        def ref_slots(self):
            return {"anchor": self.anchor_refs} if self.anchor_refs else {}

    class _RefDet:
        produces = {"hi": _Pair, "note": _Pair}
        def detect(self, df):
            hi = _Pair(start_idx=0, end_idx=0, confirm_idx=0)
            yield ("hi", hi)
            yield ("note", _Pair(start_idx=1, end_idx=1, confirm_idx=1, anchor_refs=(hi,)))

    det = _RefDet()
    spec = PatternSpec("p", nodes=[
        NodeSpec("hi", det, produces_stream="hi"),
        NodeSpec("note", det, produces_stream="note"),
    ], edges=())
    streams = run_streams(spec, _df())
    note = streams["note"][0]
    hi = streams["hi"][0]
    assert note.ref_ids_of("anchor") == (hi.instance_id,)
    assert hi.instance_id is not None


def test_ref_slots_single_event_translated():
    """ref_slots 返回单个 Event(非 tuple)→ 归一化翻译,与 annotate_stream 单-Event 归一化一致。"""
    from path2.core import Event as _EventBase

    @dataclass(frozen=True)
    class _SingleRef(_EventBase):
        start_idx: int = 0
        end_idx: int = 0
        confirm_idx: int = 0
        anchor: Event = None
        def ref_slots(self):
            return {"anchor": self.anchor} if self.anchor is not None else {}

    class _SingleRefDet:
        produces = {"hi": _SingleRef, "note": _SingleRef}
        def detect(self, df):
            hi = _SingleRef(start_idx=0, end_idx=0, confirm_idx=0)
            yield ("hi", hi)
            yield ("note", _SingleRef(start_idx=1, end_idx=1, confirm_idx=1, anchor=hi))

    det = _SingleRefDet()
    spec = PatternSpec("p", nodes=[
        NodeSpec("hi", det, produces_stream="hi"),
        NodeSpec("note", det, produces_stream="note"),
    ], edges=())
    streams = run_streams(spec, _df())
    note = streams["note"][0]
    hi = streams["hi"][0]
    assert note.ref_ids_of("anchor") == (hi.instance_id,)
    assert hi.instance_id is not None


def test_multistream_declared_but_empty_stream_is_empty_list():
    """声明两条流但本次只 yield 一条 → 空流 node 拿 [] 而非 KeyError/报错(§8.2)。"""
    class _Partial:
        produces = {"a": _E, "b": _E}
        def detect(self, df):
            yield ("a", _E(start_idx=0, end_idx=0, confirm_idx=0))

    det = _Partial()
    spec = PatternSpec("p", nodes=[
        NodeSpec("a", det, produces_stream="a"),
        NodeSpec("b", det, produces_stream="b"),
    ], edges=())
    streams = run_streams(spec, _df())
    assert len(streams["a"]) == 1
    assert streams["b"] == []


def test_ref_slots_outside_pool_raises():
    @dataclass(frozen=True)
    class _E2(Event):
        start_idx: int = 0
        end_idx: int = 0
        confirm_idx: int = 0
        refs: Tuple[Event, ...] = ()
        def ref_slots(self):
            return {"r": self.refs} if self.refs else {}

    orphan = _E2(start_idx=99, end_idx=99, confirm_idx=99)   # 不在任何流里
    class _BadDet:
        produces = {"x": _E2}
        def detect(self, df):
            yield ("x", _E2(start_idx=0, end_idx=0, confirm_idx=0, refs=(orphan,)))

    spec = PatternSpec("p", nodes=[NodeSpec("x", _BadDet(), produces_stream="x")], edges=())
    with pytest.raises(ValueError, match="instance_id"):
        run_streams(spec, _df())
