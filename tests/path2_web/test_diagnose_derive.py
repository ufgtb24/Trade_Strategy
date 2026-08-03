"""derive_response(query) scope-based router · scope=nodes 完整 · 其余 3 scope stub(§3.1)。

单测层(直接调 derive_response,diag/spec 由调用方注入·decoupled)+ 一组 HTTP 层验证
(经 TestClient 走真实 /diagnose endpoint,证明 legacy 路径字节等价 + scope=nodes 端到端可用)。
"""
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2.dag import diagnose as _dag_diagnose
from path2_apps.bottom_breakout_burst.dag_spec import build_pattern
from path2_web.app import create_app
from path2_web.diagnose import derive_response, Query, Response, NodesPayload, PairFailure, Caveat
from tests.path2.fixtures.positive_case import positive_case


def _dgnx_diag():
    """真实(非 mock)diag + spec:复用 positive_case 合成正例,产出带真实 rel_row 的
    NodeDiagnostics(burst→tb 唯一边)。symbol 用 'DGNX' 只是标签,derive_response 本身
    decoupled、不依 symbol 去查 cache/registry(那是 endpoint 层的事)。"""
    df, params = positive_case()
    spec = build_pattern(params)
    diag = _dag_diagnose(spec, df, params)
    return diag, spec


def test_derive_response_dispatches_by_scope():
    """derive_response 按 scope 分派 · 未知 scope 抛错"""
    q = Query(symbol="DGNX", scope="unknown")
    with pytest.raises(ValueError):
        derive_response(q)


def test_scope_nodes_returns_nodes_payload():
    diag, spec = _dgnx_diag()
    q = Query(symbol="DGNX", scope="nodes", src_node="burst", dst_node="tb")
    r = derive_response(q, diag=diag, spec=spec)
    assert r.scope == "nodes"
    assert isinstance(r.payload, NodesPayload)
    assert "gap_out" in r.payload.miss_reasons


def test_scope_nodes_example_failed_pairs_capped_5():
    diag, spec = _dgnx_diag()
    q = Query(symbol="DGNX", scope="nodes", src_node="burst", dst_node="tb")
    r = derive_response(q, diag=diag, spec=spec)
    assert len(r.payload.example_failed_pairs) <= 5
    assert all(isinstance(p, PairFailure) for p in r.payload.example_failed_pairs)


def test_scope_nodes_caveat_anchor_ok_not_complete_absent_after_task1():
    """Task 1 已修 anchor · 不再挂 anchor_ok_not_complete caveat"""
    diag, spec = _dgnx_diag()
    q = Query(symbol="DGNX", scope="nodes", src_node="burst", dst_node="tb")
    r = derive_response(q, diag=diag, spec=spec)
    codes = [c.code for c in r.caveats]
    assert "anchor_ok_not_complete" not in codes


def test_scope_nodes_caveat_measured_not_kind_aware_absent_after_task13():
    """Task 13 已修 EdgeWitness.measured kind-aware · 不再挂 measured_not_kind_aware caveat"""
    diag, spec = _dgnx_diag()
    q = Query(symbol="DGNX", scope="nodes", src_node="burst", dst_node="tb")
    r = derive_response(q, diag=diag, spec=spec)
    codes = [c.code for c in r.caveats]
    assert "measured_not_kind_aware" not in codes


def test_scope_nodes_consumes_anchor_ok_count_and_total_src():
    """NodesPayload.ok_pair/total_pair 精确对应 RelRow.anchor_ok_count/total_src(非重算)。"""
    diag, spec = _dgnx_diag()
    rel_row = next(r for r in diag.nodes["tb"].rel if r.src == "burst")
    q = Query(symbol="DGNX", scope="nodes", src_node="burst", dst_node="tb")
    r = derive_response(q, diag=diag, spec=spec)
    assert r.payload.total_pair == rel_row.total_src
    assert r.payload.ok_pair == rel_row.anchor_ok_count
    assert r.payload.edge_id == "burst_to_tb"


def test_scope_nodes_no_such_edge_caveat():
    """src_node/dst_node 拼出一条 dag_spec 里不存在的边 → 空 payload + no_such_edge caveat。"""
    diag, spec = _dgnx_diag()
    q = Query(symbol="DGNX", scope="nodes", src_node="bo", dst_node="burst")
    r = derive_response(q, diag=diag, spec=spec)
    assert r.payload.total_pair == 0
    assert r.payload.ok_pair == 0
    codes = [c.code for c in r.caveats]
    assert "no_such_edge" in codes


# 4 scope(time/nodes/candidate/pair)均已在 Task 15/1/20/17 落地完整实现,原
# `test_stub_scopes_return_caveat` 参数化用例(用 "isinstance(payload, dict) and
# payload.get('stub') is True" 断言旧 §3.1 stub 形态)已随每个 scope 落地逐一移除
# 参数(scope=time 见 test_diagnose_time.py,scope=pair 见 test_diagnose_pair.py::
# test_no_result_injected_returns_stub_caveat,scope=candidate 见
# test_diagnose_candidate.py::test_solvetrace_not_landed_stub / test_event_not_found)。
# candidate 是最后一个,移除后参数列表清空,函数本身随之删除(不留空 parametrize)。


def test_response_and_caveat_are_plain_dataclasses():
    """Response/Caveat 字段齐全(供 FastAPI jsonable_encoder 序列化)。"""
    r = Response(scope="time", payload={"stub": True}, caveats=[Caveat(code="x", message="y")])
    assert r.caveats[0].affected_fields == []


# ─── HTTP 层:legacy 字节等价 + scope=nodes 端到端 ────────────────────────────

def _mk_pkl(data_dir: Path, symbol: str):
    df, _ = positive_case()
    df.index = pd.date_range("2025-01-01", periods=len(df), freq="D", name="date")
    df.to_pickle(data_dir / f"{symbol}.pkl")


def _client(tmp_path):
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _mk_pkl(data_dir, "AAA")
    cfg = {"dataset_dir": str(data_dir),
          "scan": {"start_date": "2025-01-01", "end_date": "2025-12-31",
                    "workers": 1, "ticker_regex": None},
          "last_selected_pattern": "bottom_burst"}
    app = create_app(config_override=cfg, outputs_root=str(tmp_path / "outputs"),
                     use_thread_pool=True)
    return TestClient(app)


def test_diagnose_legacy_path_unchanged_without_scope(tmp_path):
    """无 scope 参数 → 走 legacy diagnose_symbol,响应形状不变(nodes/note/symbol/pattern_id)。"""
    c = _client(tmp_path)
    r = c.get("/diagnose", params={"pattern_id": "bottom_burst", "symbol": "AAA",
                                    "start": "2025-01-01", "end": "2025-12-31"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"nodes", "note", "symbol", "pattern_id"}
    assert set(body["nodes"]) == {"bo", "burst", "tb"}


def test_diagnose_scope_nodes_via_http(tmp_path):
    """scope=nodes 经真实 HTTP endpoint 分派 → NodesPayload 形状(JSON 字段名 snake_case)。"""
    c = _client(tmp_path)
    r = c.get("/diagnose", params={"pattern_id": "bottom_burst", "symbol": "AAA",
                                    "start": "2025-01-01", "end": "2025-12-31",
                                    "scope": "nodes", "src_node": "burst", "dst_node": "tb"})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "nodes"
    assert body["payload"]["edge_id"] == "burst_to_tb"
    assert "gap_out" in body["payload"]["miss_reasons"]
    assert len(body["payload"]["example_failed_pairs"]) <= 5


def test_diagnose_scope_unknown_returns_400(tmp_path):
    c = _client(tmp_path)
    r = c.get("/diagnose", params={"pattern_id": "bottom_burst", "symbol": "AAA",
                                    "start": "2025-01-01", "end": "2025-12-31",
                                    "scope": "unknown"})
    assert r.status_code == 400
