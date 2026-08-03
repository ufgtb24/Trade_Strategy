"""GET /params_diff:snapshot vs 该次扫描实际所用参数文件当前内容的字段级 diff
(锚由 params_provenance 决定,不总是 params.yaml;hash mismatch dot 数据源)。"""
import json

import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app

SCAN_TS = "20260720T000000"


@pytest.fixture
def diff_client_factory(tmp_path, monkeypatch):
    """组装 TestClient 工厂:真实 registry(bo_only 走 dag_spec)+ tmp outputs 下写一个
    最小 scan file(scan_ts 固定 SCAN_TS)。

    load_params 打桩为 Params.default:bo_only/params.yaml 磁盘当前值会随生产调参漂移,
    若不隔离,"snapshot 与当前 yaml 一致" 这类断言会因磁盘漂移而失真(同
    conftest.py::_stub_load_params_to_default 对 bottom_breakout_burst 的既有约定;
    registry 注册的是 .dag_spec 子模块而非包 init,两处 re-export 都要 stub)。
    """
    import path2_apps.bo_only as _bo
    import path2_apps.bo_only.dag_spec as _bo_dag
    monkeypatch.setattr(_bo, "load_params", _bo.Params.default)
    monkeypatch.setattr(_bo_dag, "load_params", _bo_dag.Params.default)

    outputs = tmp_path / "out"
    scans_dir = outputs / "scans"
    scans_dir.mkdir(parents=True)

    def _factory(snapshot):
        per_pattern_bo = {"params_snapshot": snapshot} if snapshot is not None else {}
        scan_file = {
            "pattern_ids": ["bo_only"],
            "per_pattern": {"bo_only": per_pattern_bo},
            "scan": {},
            "results": [],
        }
        (scans_dir / f"{SCAN_TS}.json").write_text(json.dumps(scan_file))
        app = create_app(config_path=tmp_path / "config.json",
                         outputs_root=str(outputs), use_thread_pool=True)
        return TestClient(app)

    return _factory


def test_diff_match_when_identical(diff_client_factory):
    from path2_apps.bo_only.params import Params
    snap = Params.default().to_dict()
    client = diff_client_factory(snapshot=snap)   # scan file 内嵌该 snapshot
    r = client.get("/params_diff", params={"pattern_id": "bo_only", "scan_ts": SCAN_TS})
    assert r.status_code == 200
    body = r.json()
    assert body["has_snapshot"] is True
    assert body["match"] is True
    assert body["diffs"] == []


def test_diff_reports_changed_fields(diff_client_factory):
    from path2_apps.bo_only.params import Params
    snap = Params.default().to_dict()
    snap["bo"]["total_window"] = 7          # snapshot 与当前 yaml(默认 10)不同
    client = diff_client_factory(snapshot=snap)
    r = client.get("/params_diff", params={"pattern_id": "bo_only", "scan_ts": SCAN_TS})
    body = r.json()
    assert body["match"] is False
    assert {"path": "bo.total_window", "snapshot": 7, "current": 10} in body["diffs"]


def test_diff_legacy_scan_no_snapshot(diff_client_factory):
    client = diff_client_factory(snapshot=None)   # legacy scan
    r = client.get("/params_diff", params={"pattern_id": "bo_only", "scan_ts": SCAN_TS})
    body = r.json()
    assert body["has_snapshot"] is False


@pytest.fixture
def anchor_client_factory(tmp_path, monkeypatch):
    """锚文件场景:沙箱 app 目录(params.yaml=10 / exp_wide.yaml=40)+ 可定制
    per_pattern(snapshot/provenance)的 scan file。三处 DEFAULT_YAML_PATH 都要 patch:
    dag_spec/包 init 供 _params_dir 定位目录,params 子模块供 load_params() 读沙箱。"""
    yaml_dir = tmp_path / "app"
    yaml_dir.mkdir()
    (yaml_dir / "params.yaml").write_text("bo:\n  total_window: 10\n")
    (yaml_dir / "exp_wide.yaml").write_text("bo:\n  total_window: 40\n")

    import path2_apps.bo_only as _bo
    import path2_apps.bo_only.dag_spec as _bo_dag
    import path2_apps.bo_only.params as _bo_params
    for m in (_bo, _bo_dag, _bo_params):
        monkeypatch.setattr(m, "DEFAULT_YAML_PATH", yaml_dir / "params.yaml")

    outputs = tmp_path / "out"
    scans_dir = outputs / "scans"
    scans_dir.mkdir(parents=True)

    def _factory(per_pattern_bo):
        (scans_dir / f"{SCAN_TS}.json").write_text(json.dumps({
            "pattern_ids": ["bo_only"],
            "per_pattern": {"bo_only": per_pattern_bo},
            "scan": {}, "results": [],
        }))
        app = create_app(config_path=tmp_path / "config.json",
                         outputs_root=str(outputs), use_thread_pool=True)
        return TestClient(app)

    return _factory


def test_diff_anchors_provenance_file(anchor_client_factory):
    """provenance=file:X → 锚 X 而非 params.yaml。snapshot 取 X 的值 → match=True;
    锚错(params.yaml,total_window=10)的话这里会是 False,这就是本例的 teeth。"""
    from path2_apps.bo_only.params import Params
    snap = Params.default().to_dict()
    snap["bo"]["total_window"] = 40
    client = anchor_client_factory({"params_snapshot": snap,
                                    "params_provenance": "file:exp_wide.yaml"})
    body = client.get("/params_diff",
                      params={"pattern_id": "bo_only", "scan_ts": SCAN_TS}).json()
    assert body["anchor_file"] == "exp_wide.yaml"
    assert body["match"] is True


def test_diff_anchors_params_yaml_when_provenance_yaml(anchor_client_factory):
    """provenance=yaml → 锚 params.yaml(既有行为逐字不变)。"""
    from path2_apps.bo_only.params import Params
    snap = Params.default().to_dict()
    snap["bo"]["total_window"] = 10
    client = anchor_client_factory({"params_snapshot": snap, "params_provenance": "yaml"})
    body = client.get("/params_diff",
                      params={"pattern_id": "bo_only", "scan_ts": SCAN_TS}).json()
    assert body["anchor_file"] == "params.yaml"
    assert body["match"] is True


def test_diff_anchor_file_deleted_returns_200_anchor_missing(anchor_client_factory):
    """锚文件(非基线)被删 → /params_diff 返回 200 + anchor_missing=True,不抛 400。
    锚缺失是 diff 的合法状态(snapshot 在、锚没了),诚实标记≠退化到 params.yaml。"""
    from path2_apps.bo_only.params import Params
    snap = Params.default().to_dict()
    client = anchor_client_factory({"params_snapshot": snap,
                                    "params_provenance": "file:gone.yaml"})
    r = client.get("/params_diff", params={"pattern_id": "bo_only", "scan_ts": SCAN_TS})
    assert r.status_code == 200
    body = r.json()
    assert body["has_snapshot"] is True
    assert body["anchor_missing"] is True
    assert body["match"] is False
    assert body["anchor_file"] == "gone.yaml"
