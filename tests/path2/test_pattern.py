from dataclasses import dataclass

from path2.core import Event
from path2.pattern import Pattern


@dataclass(frozen=True)
class _E(Event):
    x: int = 0


def test_all_is_and():
    e = _E(event_id="e", start_idx=0, end_idx=0, x=5)
    pat = Pattern.all(lambda ev: ev.x > 0, lambda ev: ev.x < 10)
    assert pat(e) is True
    pat2 = Pattern.all(lambda ev: ev.x > 0, lambda ev: ev.x > 100)
    assert pat2(e) is False


def test_all_empty_is_vacuous_true():
    e = _E(event_id="e", start_idx=0, end_idx=0, x=1)
    assert Pattern.all()(e) is True


def test_all_short_circuits():
    e = _E(event_id="e", start_idx=0, end_idx=0, x=1)
    calls = []

    def p1(ev):
        calls.append("p1")
        return False

    def p2(ev):
        calls.append("p2")
        return True

    Pattern.all(p1, p2)(e)
    assert calls == ["p1"]  # p2 未被调用(短路)


def test_all_nesting():
    e = _E(event_id="e", start_idx=0, end_idx=0, x=5)
    inner = Pattern.all(lambda ev: ev.x > 0)
    outer = Pattern.all(inner, lambda ev: ev.x < 10)
    assert outer(e) is True
