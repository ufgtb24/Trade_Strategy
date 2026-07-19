"""W.* 谓词便利层(一元约束:属性/all/None 安全)。"""
from dataclasses import dataclass

from path2.core import Event
from path2.dag import where as W


class Ev(Event):
    class_id = "test_where_ev"


def ev(s, e, **kw):
    return Ev(event_id=f"e{s}", start_idx=s, end_idx=e, **kw)


@dataclass(frozen=True)
class EvVol(Event):
    class_id = "test_where_ev_vol"
    vol_ratio: float = 0.0


def test_attr():
    f = W.attr("start_idx", ">=", 5)
    assert f(ev(7, 7), None) is True
    assert f(ev(3, 3), None) is False

def test_all_combines_and():
    f = W.all(W.attr("start_idx", ">=", 0), W.attr("end_idx", "<=", 10))
    assert f(ev(2, 5), None) is True
    assert f(ev(2, 20), None) is False

def test_unknown_op_raises():
    import pytest
    with pytest.raises(ValueError):
        W.attr("start_idx", "<<", 1)


# ── None 安全(Optional 字段未赋值时比较返 False,不抛;与旧 app is-not-None 短路一致)──
class _Ev:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_attr_none_value_returns_false():
    from path2.dag.where import attr
    assert attr("drought", ">=", 60)(_Ev(drought=None), None) is False
    assert attr("drought", ">=", 60)(_Ev(drought=70), None) is True


# ── 硬伤 C 双落(编译期端):mark_refs_other_node 标注跨节点 clause(Sprint 2 Task 14)──

def test_meta_default_no_refs_other_node():
    """普通 clause 未标注 · meta 里没有 refs_other_node key(向后兼容,老 meta 消费者不受影响)。"""
    w = W.attr("start_idx", ">=", 3)
    assert w.meta.get("refs_other_node", False) is False


def test_mark_refs_other_node_sets_meta_flag():
    w = W.mark_refs_other_node(W.attr("start_idx", ">=", 3))
    assert w.meta.get("refs_other_node") is True


def test_mark_refs_other_node_preserves_existing_meta_keys():
    """包一层不丢原 meta(op/threshold/field 仍在,旧消费者 .meta.get('op') 不受影响)。"""
    w = W.mark_refs_other_node(W.attr("start_idx", ">=", 3))
    assert w.meta.get("op") == ">="
    assert w.meta.get("threshold") == 3
    assert w.meta.get("field") == "start_idx"


def test_mark_refs_other_node_preserves_judgement_semantics():
    """标注只加 meta,不改变判定/measure 语义。"""
    inner = W.attr("start_idx", ">=", 5)
    marked = W.mark_refs_other_node(inner)
    assert marked(ev(7, 7), None) is True
    assert marked(ev(3, 3), None) is False
    assert marked.measure(ev(7, 7), None) == 7
