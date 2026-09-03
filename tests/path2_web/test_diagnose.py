from tests.path2.fixtures.positive_case import positive_case
from path2_apps.bottom_burst.dag_spec import build_pattern
from path2_web.diagnose import diagnose_symbol


def test_diagnose_serializes_per_node():
    df, params = positive_case()
    spec = build_pattern(params)              # 用宽松 params 的 spec(where 闭合 params)
    out = diagnose_symbol(spec, df, params, symbol="SYNTH", pattern_id="bottom_burst")
    assert out["symbol"] == "SYNTH"
    assert set(out["nodes"]) == {"bo", "burst", "pk", "tb", "tb_seg"}  # 4 独立 node + 子结构 tb_seg
    # produced_by 透传:子结构 tb_seg 的物化来源 = 父容器 tb;独立 node 为 None
    assert out["nodes"]["tb_seg"]["produced_by"] == "tb"
    assert out["nodes"]["bo"]["produced_by"] is None
    # bo 是 isolated node(无入边) → rel 为空
    bo = out["nodes"]["bo"]
    assert isinstance(bo["rel"], list)
    assert bo["rel"] == []
    # 关系诊断(唯一边 burst→tb):tb 仅 burst 一条入边
    tb = out["nodes"]["tb"]
    assert isinstance(tb["rel"], list)
    assert len(tb["rel"]) >= 1
    tb_srcs = {r["src"] for r in tb["rel"]}
    assert tb_srcs == {"burst"}
    if tb["rel"]:
        rel = tb["rel"][0]
        assert {"src", "kind", "total_src", "ok_count", "ok_src_ids"} <= set(rel)
    # burst 无入边 → rel 为空
    burst = out["nodes"]["burst"]
    assert isinstance(burst["rel"], list)
    assert burst["rel"] == []
    # 局部性免责声明
    assert "局部" in out["note"]
