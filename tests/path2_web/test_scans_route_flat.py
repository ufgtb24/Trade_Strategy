"""扁平 /scans/、/scans/{ts}、DELETE /scans/{ts} 路由。"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app
from path2_web.scan import run_scan_multi
from path2_web.serialize import serialize_pattern
from path2_apps.bo_only import build_pattern as build_bo, Params as PBo


@pytest.fixture
def app_with_one_scan(tmp_path):
    """造 1 个 multi-scan 结果文件 + TestClient。"""
    # 造 2 只合成 pkl
    data = tmp_path / "data"
    data.mkdir()
    n = 200
    base = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [10.0]*n, "high": [11.0]*n,
        "low":  [9.0]*n,  "close":[10.5]*n, "volume":[100.0]*n,
    })
    base.to_pickle(data / "AAA.pkl")
    base.to_pickle(data / "BBB.pkl")

    outputs = tmp_path / "out"
    specs = {"bo_only": serialize_pattern(build_bo(PBo.default()))}
    run_scan_multi(
        data_dir=str(data),
        pattern_specs_json=specs,
        module_paths={"bo_only": "path2_apps.bo_only"},
        pattern_ids=["bo_only"],
        end_roles={"bo_only": "bo"},
        head_buffer_trading_days=63, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=1, ticker_regex=None, scan_ts="20260627T130000",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-02-01", "end_date": "2024-06-30",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    app = create_app(config_path=cfg_path, outputs_root=str(outputs),
                     use_thread_pool=True)
    return TestClient(app), outputs


def test_get_scans_flat_lists_entries(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.get("/scans/")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["scan_ts"] == "20260627T130000"
               and row["pattern_ids"] == ["bo_only"]
               for row in rows)


def test_get_scans_ts_loads_multi_file(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.get("/scans/20260627T130000")
    assert r.status_code == 200
    blob = r.json()
    assert blob["pattern_ids"] == ["bo_only"]
    assert "per_pattern" in blob and "bo_only" in blob["per_pattern"]


def test_delete_scans_ts(app_with_one_scan):
    client, outputs = app_with_one_scan
    r = client.delete("/scans/20260627T130000")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert not (Path(outputs) / "scans" / "20260627T130000.json").exists()


def test_get_scans_ts_404_missing(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.get("/scans/00000000T000000")
    assert r.status_code == 404


def test_delete_scans_ts_404_missing(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.delete("/scans/00000000T000000")
    assert r.status_code == 404
