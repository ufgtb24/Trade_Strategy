"""POST /scan 接受 pattern_ids: List[str]。"""
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def outputs(tmp_path):
    return tmp_path / "out"


@pytest.fixture
def app(tmp_path, outputs):
    data = tmp_path / "data"
    data.mkdir()
    n = 100
    pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open":[10.0]*n, "high":[11.0]*n, "low":[9.0]*n,
        "close":[10.5]*n, "volume":[100.0]*n,
    }).to_pickle(data / "AAA.pkl")

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-02-01", "end_date": "2024-06-30",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                  use_thread_pool=True))


def test_post_scan_accepts_pattern_ids(app):
    """POST /scan 接受 pattern_ids 数组,返回 scan_id。"""
    r = app.post("/scan", json={
        "pattern_ids": ["bo_only", "bottom_burst"],
        "start_date": "2024-02-01",
        "end_date": "2024-06-30",
        "workers": 1,
        "label_horizon": 20,
    })
    assert r.status_code == 200
    assert "scan_id" in r.json()


def test_post_scan_empty_pattern_ids_422(app):
    """空数组 → 422 Unprocessable。"""
    r = app.post("/scan", json={
        "pattern_ids": [],
        "start_date": "2024-02-01", "end_date": "2024-06-30",
        "workers": 1, "label_horizon": 20,
    })
    assert r.status_code == 422


def test_post_scan_unknown_pattern_404(app):
    """未注册 pattern_id → 404。"""
    r = app.post("/scan", json={
        "pattern_ids": ["does_not_exist"],
        "start_date": "2024-02-01", "end_date": "2024-06-30",
        "workers": 1, "label_horizon": 20,
    })
    assert r.status_code == 404


def test_post_scan_dedupes_duplicates(app):
    """pattern_ids 重复 → 后端自动去重(dict 自然去重),不报错。"""
    r = app.post("/scan", json={
        "pattern_ids": ["bo_only", "bo_only"],
        "start_date": "2024-02-01", "end_date": "2024-06-30",
        "workers": 1, "label_horizon": 20,
    })
    assert r.status_code == 200


_SCAN_BODY = {"pattern_ids": ["bo_only"], "start_date": "2024-02-01",
              "end_date": "2024-06-30", "workers": 1, "label_horizon": 20}


def test_post_scan_rejects_illegal_name_400(app):
    """note 含非法字符(/)→ 400(白名单)。"""
    r = app.post("/scan", json={**_SCAN_BODY, "note": "bad/name"})
    assert r.status_code == 400


def test_post_scan_duplicate_name_409(app, outputs):
    """同名文件已存在 → 开扫前 409(不浪费扫描)。"""
    (outputs / "scans").mkdir(parents=True)
    (outputs / "scans" / "tb深度28-38.json").write_text(
        json.dumps({"pattern_ids": [], "scan": {"hits": 0}}))
    r = app.post("/scan", json={**_SCAN_BODY, "note": "tb深度28-38"})
    assert r.status_code == 409


def test_rename_endpoint_moves_and_syncs(app, outputs):
    (outputs / "scans").mkdir(parents=True)
    (outputs / "scans" / "old.json").write_text(json.dumps({
        "pattern_ids": [], "scan": {"scan_ts": "20260729T100000", "hits": 0, "note": "old"}}))
    r = app.post("/scans/old/rename", json={"name": "新名字"})
    assert r.status_code == 200
    assert r.json()["name"] == "新名字"
    assert (outputs / "scans" / "新名字.json").exists()
    assert not (outputs / "scans" / "old.json").exists()
    assert json.loads((outputs / "scans" / "新名字.json").read_text())["scan"]["note"] == "新名字"


def test_rename_collision_409(app, outputs):
    (outputs / "scans").mkdir(parents=True)
    for nm in ("a", "b"):
        (outputs / "scans" / f"{nm}.json").write_text(json.dumps({"scan": {"hits": 0}}))
    r = app.post("/scans/a/rename", json={"name": "b"})
    assert r.status_code == 409


def test_rename_missing_404(app, outputs):
    (outputs / "scans").mkdir(parents=True)
    r = app.post("/scans/nope/rename", json={"name": "x"})
    assert r.status_code == 404


def test_load_by_name(app, outputs):
    (outputs / "scans").mkdir(parents=True)
    (outputs / "scans" / "myexp.json").write_text(json.dumps({"scan": {"hits": 5}, "pattern_ids": []}))
    r = app.get("/scans/myexp")
    assert r.status_code == 200 and r.json()["scan"]["hits"] == 5


# ---------------------------------------------------------------------------
# ScanRequest.first_passage_k 字段(几何对称阈值倍数,默认 5.0)
# ---------------------------------------------------------------------------
def test_post_scan_first_passage_k_default_omitted(app):
    """不传 first_passage_k → 默认 5.0、合法 → 200。"""
    r = app.post("/scan", json={
        "pattern_ids": ["bo_only"],
        "start_date": "2024-02-01", "end_date": "2024-06-30",
        "workers": 1, "label_horizon": 20,
    })
    assert r.status_code == 200
    assert "scan_id" in r.json()


def test_post_scan_first_passage_k_explicit(app):
    """first_passage_k=1.5 显式传入 → 200。"""
    r = app.post("/scan", json={
        "pattern_ids": ["bo_only"],
        "start_date": "2024-02-01", "end_date": "2024-06-30",
        "workers": 1, "label_horizon": 20,
        "first_passage_k": 1.5,
    })
    assert r.status_code == 200
    assert "scan_id" in r.json()


def test_post_scan_first_passage_disabled_accepted(app):
    """first_passage_enabled=False 合法 → 200(开关位透传)。"""
    r = app.post("/scan", json={
        "pattern_ids": ["bo_only"],
        "start_date": "2024-02-01", "end_date": "2024-06-30",
        "workers": 1, "label_horizon": 20,
        "first_passage_enabled": False,
    })
    assert r.status_code == 200
