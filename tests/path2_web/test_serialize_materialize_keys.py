"""serialize_pattern 派生 topology.nodes[].materialize_keys 契约测试。

materialize_keys = 该 node detector 的 __init__ 构造参数键(去 self)。
依据 author 约定:进 detector __init__ 的 = 物化层(卡 event 生成),
留在 node.where 的 = where 层(卡升 match)。反射 detector 精确捕获此约定。
"""
from path2_apps.bottom_breakout_burst import build_pattern, load_params
from path2_web.serialize import serialize_pattern


def _nodes_map(payload):
    return {n["node_id"]: n for n in payload["topology"]["nodes"]}


def test_materialize_keys_present_on_every_node():
    spec = build_pattern(load_params())
    payload = serialize_pattern(spec)
    for n in payload["topology"]["nodes"]:
        assert "materialize_keys" in n, f"{n['node_id']} 缺 materialize_keys"
        assert isinstance(n["materialize_keys"], list)


def test_bottom_burst_materialize_keys_values():
    spec = build_pattern(load_params())
    nodes = _nodes_map(serialize_pattern(spec))
    assert set(nodes["bo"]["materialize_keys"]) == {
        "total_window", "min_side_bars", "min_relative_height", "exceed_threshold",
        "peak_supersede_threshold", "vol_baseline_period", "peak_measure", "breakout_measure",
    }
    # burst 仅 3 个构造参数;first_drought_min/distinct_pk_min/vol_spike_min 刻意不进 __init__
    assert set(nodes["burst"]["materialize_keys"]) == {
        "gap_max", "min_bos", "vol_baseline_period",
    }
    assert set(nodes["tb"]["materialize_keys"]) == {
        "max_start_gap", "max_window", "atr_window", "big_rise_k",
        "stop_confirm_bars", "anchor_measure", "support_measure",
    }
