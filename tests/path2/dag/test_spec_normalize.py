"""PatternSpec produced_by 归一化(children 逆映射三态) + 声明期校验(死字段/P3/P5/neg_dst)。"""
import pytest

from path2.dag.edges import NegationEdge, TemporalEdge
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.atoms.throwback import ThrowbackSegment


class FakeDetector:
    event_cls = ThrowbackSegment


def _spec(nodes, edges=()):
    return PatternSpec(pattern_id="t", nodes=tuple(nodes), edges=tuple(edges))


def test_produced_by_derived_from_single_parent():
    tb = NodeSpec("tb", FakeDetector(), children={"segments": "tb_seg"})
    seg = NodeSpec("tb_seg", event_cls=ThrowbackSegment)
    spec = _spec([tb, seg])
    assert seg.produced_by == "tb"          # 归一化回填(frozen → object.__setattr__)


def test_orphan_substructure_raises():
    seg = NodeSpec("tb_seg", event_cls=ThrowbackSegment)
    with pytest.raises(ValueError, match="孤儿|未被任何父"):
        _spec([seg])


def test_multi_parent_raises():
    tb1 = NodeSpec("tb1", FakeDetector(), children={"segments": "tb_seg"})
    tb2 = NodeSpec("tb2", FakeDetector(), children={"segments": "tb_seg"})
    seg = NodeSpec("tb_seg", event_cls=ThrowbackSegment)
    with pytest.raises(ValueError, match="多父"):
        _spec([tb1, tb2, seg])


def test_explicit_produced_by_must_match_derived():
    tb = NodeSpec("tb", FakeDetector(), children={"segments": "tb_seg"})
    seg = NodeSpec("tb_seg", event_cls=ThrowbackSegment, produced_by="other")
    with pytest.raises(ValueError, match="不一致"):
        _spec([tb, seg])


def test_duplicate_node_id_masking_substructure_raises_clean_error():
    # 重复 node_id:后写 detector 条目遮蔽先写子结构条目(by_id last-wins)→ derived 查不到,
    # 报含 node_id 的干净 ValueError,而非 KeyError(归一化先于去重校验执行)
    seg1 = NodeSpec("dup_seg", event_cls=ThrowbackSegment)
    seg2 = NodeSpec("dup_seg", FakeDetector())
    with pytest.raises(ValueError, match="produced_by 无法推导"):
        _spec([seg1, seg2])


def test_children_refers_missing_node_raises():
    tb = NodeSpec("tb", FakeDetector(), children={"segments": "nope"})
    with pytest.raises(ValueError, match="不存在"):
        _spec([tb])


def test_substructure_dead_fields_rejected():
    tb = NodeSpec("tb", FakeDetector(), children={"segments": "tb_seg"})
    seg = NodeSpec("tb_seg", event_cls=ThrowbackSegment, consumes_stream="bo")     # 死字段: 子结构无独立流
    with pytest.raises(ValueError, match="consumes_stream|死字段"):
        _spec([tb, seg])


def test_substructure_render_grid_price_rejected():
    tb = NodeSpec("tb", FakeDetector(), children={"segments": "tb_seg"})
    seg = NodeSpec("tb_seg", event_cls=ThrowbackSegment, render_grid="price")      # 死字段: 会炸 _validate_render_grid 的 detector getattr
    with pytest.raises(ValueError):
        _spec([tb, seg])


def test_substructure_not_edge_endpoint():
    tb = NodeSpec("tb", FakeDetector(), children={"segments": "tb_seg"})
    seg = NodeSpec("tb_seg", event_cls=ThrowbackSegment)
    with pytest.raises(ValueError):
        _spec([tb, seg], [TemporalEdge("tb", "tb_seg", min_gap=0, max_gap=10)])


def test_substructure_not_consumed_stream():
    tb = NodeSpec("tb", FakeDetector(), children={"segments": "tb_seg"})
    seg = NodeSpec("tb_seg", event_cls=ThrowbackSegment)
    # seg 被子结构引用 ✓,但被第三方 consumes_stream 引用 ✗
    other = NodeSpec("other", FakeDetector(), consumes_stream="tb_seg")
    with pytest.raises(ValueError):
        _spec([tb, seg, other])


def test_neg_dst_referenced_by_positive_edge_raises():
    # P4 顺手修: neg_dst 被正向边引用 → 声明期报错(_graph 会崩)
    a = NodeSpec("a", FakeDetector())
    b = NodeSpec("b", FakeDetector())
    with pytest.raises(ValueError):
        _spec([a, b], [NegationEdge("a", "b"), TemporalEdge("a", "b", min_gap=0, max_gap=10)])
