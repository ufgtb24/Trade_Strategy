"""/preview 端点 — 单股临时计算(不落盘)。
buffered 路径(有 eval_meta)pads buf 窗 + 注入 forward_return;非 buffered 严格窗。"""
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


def _mk_pkl(data_dir: Path, symbol: str):
    from tests.path2_apps.bottom_burst.test_matches import _synth_no_burst
    df = _synth_no_burst()
    df.index = pd.date_range("2025-01-01", periods=len(df), freq="D", name="date")
    df.to_pickle(data_dir / f"{symbol}.pkl")


def _client(tmp_path, with_pkl: str | None = "AAA"):
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    if with_pkl:
        _mk_pkl(data_dir, with_pkl)
    cfg = {
        "dataset_dir": str(data_dir),
        "scan": {"start_date": "2025-01-01", "end_date": "2025-12-31",
                 "workers": 1, "ticker_regex": None},
        "last_selected_pattern": "bottom_burst",
    }
    app = create_app(config_override=cfg, outputs_root=str(tmp_path / "outputs"),
                     use_thread_pool=True)
    return TestClient(app)


def test_preview_returns_four_keys(tmp_path):
    c = _client(tmp_path)
    r = c.get("/preview", params={"pattern_id": "bottom_burst",
                                   "symbol": "AAA", "start": "2025-01-01",
                                   "end": "2025-12-31", "label_horizon": 20})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"analysis", "summary", "pattern_spec", "scan"}


def test_preview_analysis_schema(tmp_path):
    c = _client(tmp_path)
    body = c.get("/preview", params={"pattern_id": "bottom_burst",
                                      "symbol": "AAA", "start": "2025-01-01",
                                      "end": "2025-12-31", "label_horizon": 20}).json()
    assert {"events", "matches"} <= set(body["analysis"])


def test_preview_pattern_spec_has_topology(tmp_path):
    c = _client(tmp_path)
    body = c.get("/preview", params={"pattern_id": "bottom_burst",
                                      "symbol": "AAA", "start": "2025-01-01",
                                      "end": "2025-12-31", "label_horizon": 20}).json()
    spec = body["pattern_spec"]
    assert "topology" in spec
    assert "nodes" in spec["topology"]
    assert "edges" in spec["topology"]


def test_preview_uses_buffered_window_when_eval_meta_present(tmp_path):
    """bbb 有 eval_meta(end_node='bo', head_buffer_trading_days>0),win 应被拉宽。"""
    c = _client(tmp_path)
    body = c.get("/preview", params={"pattern_id": "bottom_burst",
                                      "symbol": "AAA", "start": "2025-06-01",
                                      "end": "2025-06-30", "label_horizon": 20}).json()
    scan = body["scan"]
    assert scan["win_start"] < "2025-06-01"
    assert scan["win_end"] > "2025-06-30"
    assert scan["end_node"] == "tb.segments"   # Task 6:end_node 路径声明(买点 = segments 槽企稳段)
    assert scan["label_horizon"] == 20


def test_preview_falls_back_when_eval_meta_missing(tmp_path, monkeypatch):
    """mock 掉 eval_meta(在 client 建好后) → require_eval_meta raises ValueError → 500。
    铁律下 discovery 已闸过滤,此路径属防御性;测试仅验证 500 返回、不报其他错。
    注:必须先建 client(让 discovery 正常跑通),再 delattr,否则 discovery 把 pattern 排除 → 404。"""
    import path2_apps.bottom_burst.dag_spec as bbb_dag
    c = _client(tmp_path)   # 先建 client,discovery 已正常注册 bottom_burst
    monkeypatch.delattr(bbb_dag, "eval_meta", raising=False)
    r = c.get("/preview", params={"pattern_id": "bottom_burst",
                                   "symbol": "AAA", "start": "2025-06-01",
                                   "end": "2025-06-30", "label_horizon": 20})
    assert r.status_code == 500


def test_preview_unknown_pattern_404(tmp_path):
    c = _client(tmp_path)
    r = c.get("/preview", params={"pattern_id": "does_not_exist",
                                   "symbol": "AAA", "start": "2025-01-01",
                                   "end": "2025-12-31", "label_horizon": 20})
    assert r.status_code == 404
    assert "unknown pattern" in r.json()["detail"]


def test_preview_pkl_not_found_404(tmp_path):
    c = _client(tmp_path, with_pkl=None)
    r = c.get("/preview", params={"pattern_id": "bottom_burst",
                                   "symbol": "MISSING", "start": "2025-01-01",
                                   "end": "2025-12-31", "label_horizon": 20})
    assert r.status_code == 404
    assert "pkl not found" in r.json()["detail"]


def test_preview_empty_window_returns_empty_collections(tmp_path):
    """窗口超出数据范围 → 200 + 空集 dict,非 null,非 error。"""
    c = _client(tmp_path)
    r = c.get("/preview", params={"pattern_id": "bottom_burst",
                                   "symbol": "AAA", "start": "2099-01-01",
                                   "end": "2099-12-31", "label_horizon": 20})
    assert r.status_code == 200
    body = r.json()
    assert body["analysis"]["events"] == []
    assert body["analysis"]["matches"] == []


def test_preview_no_match_returns_empty_matches_not_error(tmp_path):
    """_synth_no_burst 构造 0 命中:200 + matches=[],不报错。"""
    c = _client(tmp_path)
    r = c.get("/preview", params={"pattern_id": "bottom_burst",
                                   "symbol": "AAA", "start": "2025-01-01",
                                   "end": "2025-12-31", "label_horizon": 20})
    assert r.status_code == 200
    assert r.json()["analysis"]["matches"] == []


def test_preview_yaml_value_error_returns_500(tmp_path, monkeypatch):
    """yaml load 抛 ValueError(如未知字段)→ 500 detail 含错误描述。
    注:必须先建 client(让 discovery 正常跑通),再 patch load_params,
    否则 discovery 调用 load_params 抛 → pattern 排除 → 404。"""
    import path2_apps.bottom_burst.dag_spec as bbb_dag
    c = _client(tmp_path)   # 先建 client,discovery 已正常注册
    def _raise():
        raise ValueError("params.yaml ... 含未知字段: ['bo_typooo']")
    monkeypatch.setattr(bbb_dag, "load_params", _raise)
    r = c.get("/preview", params={"pattern_id": "bottom_burst",
                                   "symbol": "AAA", "start": "2025-01-01",
                                   "end": "2025-12-31", "label_horizon": 20})
    assert r.status_code == 500
    assert "未知字段" in r.json()["detail"] or "ValueError" in r.json()["detail"]


def test_preview_analyze_exception_returns_500(tmp_path, monkeypatch):
    """mod.analyze 抛任意异常 → 500 detail 含 type:msg。
    mod 是 dag_spec 模块;须 patch dag_spec.analyze(非 bbb 包 __init__ 的 analyze)。"""
    import path2_apps.bottom_burst.dag_spec as bbb_dag
    c = _client(tmp_path)   # 先建 client,discovery 已正常注册
    def _raise(win, params=None):
        raise RuntimeError("simulated downstream failure")
    monkeypatch.setattr(bbb_dag, "analyze", _raise)
    r = c.get("/preview", params={"pattern_id": "bottom_burst",
                                   "symbol": "AAA", "start": "2025-01-01",
                                   "end": "2025-12-31", "label_horizon": 20})
    assert r.status_code == 500
    assert "RuntimeError" in r.json()["detail"]
    assert "simulated downstream failure" in r.json()["detail"]


def test_preview_pattern_spec_reflects_current_yaml(tmp_path, monkeypatch):
    """monkeypatch load_params 返回改后值 → 响应 pattern_spec 反映新阈值。"""
    import path2_apps.bottom_burst as bbb
    import path2_apps.bottom_burst.dag_spec as bbb_dag
    base = bbb.Params.default()
    # 把 burst.first_drought_min 临时改为 999(显著值,方便在 spec 里找到)
    from dataclasses import replace
    custom = replace(base, burst=replace(base.burst, first_drought_min=999))
    monkeypatch.setattr(bbb, "load_params", lambda: custom)
    monkeypatch.setattr(bbb_dag, "load_params", lambda: custom)

    c = _client(tmp_path)
    body = c.get("/preview", params={"pattern_id": "bottom_burst",
                                      "symbol": "AAA", "start": "2025-01-01",
                                      "end": "2025-12-31", "label_horizon": 20}).json()
    # spec 内某个 node 的 where_rule 阈值含 999(具体路径:burst 节点 first_drought 子句)
    nodes = body["pattern_spec"]["topology"]["nodes"]
    burst_node = next((n for n in nodes if "burst" in n.get("node_id", "")), None)
    assert burst_node is not None, "找不到 burst 节点"
    drought_rule = next((r for r in burst_node["where_rules"]
                         if r["clause_id"] == "first_drought"), None)
    assert drought_rule is not None, "burst 节点缺 first_drought where_rule"
    assert drought_rule["threshold"] == 999
