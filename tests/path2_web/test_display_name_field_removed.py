"""验证 display_name/label 字段已从 path2 数据模型与后端序列化中清除。"""
import dataclasses

from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec, TopoNode


def test_pattern_spec_no_display_name_field():
    names = {f.name for f in dataclasses.fields(PatternSpec)}
    assert "display_name" not in names


def test_node_spec_no_label_field():
    names = {f.name for f in dataclasses.fields(NodeSpec)}
    assert "label" not in names


def test_topo_node_no_label_field():
    names = {f.name for f in dataclasses.fields(TopoNode)}
    assert "label" not in names


def test_serialize_pattern_omits_fields():
    from path2_apps.bottom_breakout_burst.dag_spec import PATTERN_DAG
    from path2_web.serialize import serialize_pattern

    meta = serialize_pattern(PATTERN_DAG)
    assert "display_name" not in meta, f"meta keys: {list(meta.keys())}"
    assert meta["topology"]["nodes"], "nodes 列表非空"
    for n in meta["topology"]["nodes"]:
        assert "label" not in n, f"node 残留 label: {n}"
