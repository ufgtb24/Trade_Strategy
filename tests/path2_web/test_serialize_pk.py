"""serialize:topology node 带 solve 标志;PeakEvent 事件带 kind。"""
from path2.atoms.breakout import PeakEvent
from path2_apps.bb_pk.dag_spec import build_pattern
from path2_apps.bb_pk.params import Params
from path2_web.serialize import serialize_pattern


def test_topology_nodes_carry_solve():
    spec = build_pattern(Params.default())
    out = serialize_pattern(spec)
    by_id = {n["node_id"]: n for n in out["topology"]["nodes"]}
    assert by_id["bo"]["solve"] is True
    assert by_id["pk"]["solve"] is False      # pk 只显示不参与匹配
    assert by_id["burst"]["solve"] is True


def test_peak_event_kind_serialized():
    # 事件行由 _event_to_dict schema-driven 全量平铺,kind 应自动带出;state 字段已删除
    # (定稿状态改由消费侧从 ref_ids 合成,见 C4);superseded_refs 走 ref_slots 协议,
    # 恒不进 payload。
    d = PeakEvent(start_idx=0, end_idx=0, confirm_idx=0, pk_id=1,
                  kind="bear", peak_idx=0, price=5.0)
    from path2_web.serialize import _event_to_dict
    row = _event_to_dict(d)
    assert row["kind"] == "bear"
    assert "superseded_refs" not in row
