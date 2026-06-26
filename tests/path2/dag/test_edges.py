"""5 个边子类的纯函数 + 实证健全性属性(verdict §6/§7)。"""
import math
import pytest
from path2.core import Event
from path2.dag.edges import (
    DependencyEdge, TemporalEdge, ContainmentEdge, NegationEdge, OverlapEdge, EqualsEdge,
)


class Ev(Event):
    """测试用具体 Event(frozen dataclass 由 Event 提供)。"""
    class_id = "test_edges_ev"


def ev(s, e):
    return Ev(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


# ── 基类契约 ──
def test_base_is_abstract():
    with pytest.raises(TypeError):
        DependencyEdge(src="a", dst="b")  # 抽象 satisfies 未实现

def test_base_defaults_via_subclass():
    e = TemporalEdge("a", "b")
    assert (e.src, e.dst) == ("a", "b")


# ── TemporalEdge ──
def test_temporal_satisfies_and_window():
    e = TemporalEdge("a", "b", min_gap=1, max_gap=10)
    a = ev(0, 5)
    assert e.feasible_window(a) == (6, 15)            # a.end+min_gap, a.end+max_gap
    assert e.satisfies(a, ev(6, 6)) is True           # gap=1
    assert e.satisfies(a, ev(16, 16)) is False        # gap=11 > 10
    assert e.satisfies(a, ev(5, 5)) is False          # gap=0 < 1
    assert e.signature_fields() == ("end_idx",)

def test_temporal_default_window_open():
    e = TemporalEdge("a", "b")
    assert e.feasible_window(ev(0, 3)) == (3, math.inf)

def test_temporal_strict_is_keyword_only_and_defaults_false():
    assert TemporalEdge("a", "b", 1, 20).strict is False     # 位置参数不会误灌 strict
    assert TemporalEdge("a", "b", strict=True).strict is True

def test_temporal_illegal_gap():
    with pytest.raises(ValueError):
        TemporalEdge("a", "b", min_gap=5, max_gap=2)


# ── ContainmentEdge（src ⊇ dst）──
def test_containment_satisfies_and_window():
    e = ContainmentEdge("s", "b")
    s = ev(0, 100)
    assert e.satisfies(s, ev(10, 40)) is True
    assert e.satisfies(s, ev(0, 100)) is True          # 共享端点归包含(<=)
    assert e.satisfies(s, ev(10, 200)) is False        # end 超出
    assert e.feasible_window(s) == (0, 100)            # dst.start ∈ [src.start, src.end]
    assert e.signature_fields() == ("start_idx", "end_idx")


# ── OverlapEdge（实证健全，verdict §6.1）──
def test_overlap_satisfies_and_window():
    e = OverlapEdge("a", "b")
    a = ev(0, 10)
    assert e.satisfies(a, ev(2, 12)) is True           # 内部起、伸到 a 之后
    assert e.satisfies(a, ev(5, 12)) is True
    assert e.satisfies(a, ev(0, 12)) is False          # b.start 不 > a.start
    assert e.satisfies(a, ev(2, 10)) is False          # b.end 不 > a.end
    assert e.feasible_window(a) == (1, 9)              # (a.start+1, a.end-1)
    assert e.signature_fields() == ("start_idx", "end_idx")

def test_overlap_window_equals_start_bracket_no_off_by_one():
    """verdict §6.1 实证不变量:window 对 dst.start 双侧充要(穷举小区间)。"""
    e = OverlapEdge("a", "b")
    a = ev(3, 9)
    lo, hi = e.feasible_window(a)
    for bs in range(0, 15):
        in_window = lo <= bs <= hi
        start_bracket_ok = a.start_idx < bs < a.end_idx
        assert in_window == start_bracket_ok, bs       # 零 off-by-one


# ── EqualsEdge（satisfies/window/sig 如设计;C1-off 是引擎责任,Phase 2）──
def test_equals_satisfies_and_window_pins_start():
    e = EqualsEdge("a", "b")
    a = ev(7, 12)
    assert e.satisfies(a, ev(7, 12)) is True
    assert e.satisfies(a, ev(7, 13)) is False          # end 不等
    assert e.satisfies(a, ev(8, 12)) is False          # start 不等
    assert e.feasible_window(a) == (7, 7)              # dst.start 钉死 == src.start
    assert e.signature_fields() == ("start_idx", "end_idx")


# ── NegationEdge（satisfies 反转:True=违禁）──
def test_negation_satisfies_means_violated():
    e = NegationEdge("anchor", "neg", min_gap=0, max_gap=5)
    a = ev(0, 0)
    assert e.satisfies(a, ev(3, 3)) is True            # 落窗 ⇒ 违禁
    assert e.satisfies(a, ev(10, 10)) is False         # 窗外 ⇒ 不违禁

def test_negation_inner_predicate():
    e = NegationEdge("anchor", "neg", min_gap=0, max_gap=5,
                     inner_predicate=lambda x: x.end_idx > 100)
    a = ev(0, 0)
    assert e.satisfies(a, ev(3, 3)) is False           # 落窗但谓词不满足
    assert e.satisfies(a, ev(3, 200)) is True          # 落窗且谓词满足 ⇒ 违禁
