"""W.* 谓词便利层(一元约束:属性/all/None 安全)。"""
from dataclasses import dataclass

from path2.core import Event
from path2.dag import where as W


class Ev(Event):
    class_id = "test_where_ev"


def ev(s, e, **kw):
    return Ev(event_id=f"e{s}", start_idx=s, end_idx=e, confirm_idx=s, **kw)


@dataclass(frozen=True)
class EvVol(Event):
    class_id = "test_where_ev_vol"
    vol_ratio: float = 0.0


def test_attr():
    f = W.attr("start_idx", ">=", 5)
    assert f(ev(7, 7)) is True
    assert f(ev(3, 3)) is False

def test_all_combines_and():
    f = W.all(W.attr("start_idx", ">=", 0), W.attr("end_idx", "<=", 10))
    assert f(ev(2, 5)) is True
    assert f(ev(2, 20)) is False

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
    assert attr("drought", ">=", 60)(_Ev(drought=None)) is False
    assert attr("drought", ">=", 60)(_Ev(drought=70)) is True
