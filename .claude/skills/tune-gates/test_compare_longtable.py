# -*- coding: utf-8 -*-
"""compare_longtable 的 (a) 组固定维判定:必须按「同一趟 detect 产出的 node 组」算。

多流 detector 一趟产多条流时,同一个真扫维会同时影响这一组里的每个 node,
写死等于首个 node 会让 fixed 落空、(a) 组退化成全网格(bb_v1 实测 3 → 9 格)。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from compare_longtable import _first_detect_group, _fixed_dims  # noqa: E402
from path2.dag.nodes import NodeSpec  # noqa: E402
from path2.dag.spec import PatternSpec  # noqa: E402
from tests.path2.dogfood_multistream import RangeEvent, RangeNoteDetector  # noqa: E402


def _multistream_spec():
    det = RangeNoteDetector(span=3, min_bars=5)
    return PatternSpec("p", edges=(), nodes=[
        NodeSpec("range", det, produces_stream="range"),
        NodeSpec("note", det, produces_stream="note", solve=False),
    ])


def _multistream_spec_with_leading_substructure_node():
    """同 `_multistream_spec`,但额外挂一个 detector=None 的子结构 node "aaa_seg",
    字典序排在 "note"/"range" 之前——复现 tb_seg 这类子结构 node 排在根 detector
    node 前面时,拓扑序 [0] 落在它头上的场景。"""
    det = RangeNoteDetector(span=3, min_bars=5)
    return PatternSpec("p", edges=(), nodes=[
        NodeSpec("range", det, produces_stream="range", children={"seg": "aaa_seg"}),
        NodeSpec("note", det, produces_stream="note", solve=False),
        NodeSpec("aaa_seg", event_cls=RangeEvent),
    ])


def test_first_detect_group_covers_all_siblings_of_one_call():
    """一趟 detect 产两条流 ⟹ 组里两个 node 都在。"""
    assert _first_detect_group(_multistream_spec()) == {"range", "note"}


def test_first_detect_group_skips_leading_substructure_node():
    """拓扑序 [0] 是 detector=None 的子结构 node 时,仍要返回真正首趟 detect 那组
    node,而不是退化成空集(旧实现直接拿 [0] 的 detector 建 key,会撞上 None)。"""
    assert _first_detect_group(_multistream_spec_with_leading_substructure_node()) == {"range", "note"}


def test_fixed_dims_keeps_multistream_dim_fixed():
    """同时影响 range 与 note 的 D 维必须被钉住(⊆ 组),而非因 != [first] 落空。"""
    dims = [("range", "span"), ("other", "thing")]
    cl = {"kinds": {"range.span": "D", "other.thing": "D"},
          "detector_nodes": {"range.span": ["range", "note"], "other.thing": ["other"]}}
    ref_point = {"range.span": 3, "other.thing": 7}
    got = _fixed_dims(dims, cl, ref_point, {"range", "note"},
                      lambda d: f"{d[0]}.{d[1]}")
    assert got == {("range", "span"): 3}


def test_fixed_dims_ignores_dim_with_empty_detector_nodes():
    """空集 ⊆ 任何集合——不能因此把 where 维也钉住。"""
    cl = {"kinds": {"x.y": "D"}, "detector_nodes": {"x.y": []}}
    got = _fixed_dims([("x", "y")], cl, {"x.y": 1}, {"range"}, lambda d: f"{d[0]}.{d[1]}")
    assert got == {}
