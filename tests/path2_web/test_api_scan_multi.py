"""POST /scan 接受 pattern_ids: List[str]。"""
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def app(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    n = 100
    pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open":[10.0]*n, "high":[11.0]*n, "low":[9.0]*n,
        "close":[10.5]*n, "volume":[100.0]*n,
    }).to_pickle(data / "AAA.pkl")

    outputs = tmp_path / "out"
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
