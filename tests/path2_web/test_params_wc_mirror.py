"""POST /params/wc-mirror + /params/wc-clear 测试:WC 镜像落盘/清理。

wc-mirror:前端"修改 WC"操作触发,把当前 WC(currentDict+enabled)落盘 outputs/path2_web/wc.json
(单一覆盖)。wc-clear:discardWorkingCopy 触发删 wc.json。
"""
import json
import pytest
from fastapi.testclient import TestClient
from path2_web.app import create_app


@pytest.fixture
def wc_client(tmp_path):
    """TestClient + outputs 沙箱(tmp_path/out)。"""
    app = create_app(config_path=tmp_path / "config.json",
                     outputs_root=str(tmp_path / "out"),
                     use_thread_pool=True)
    return TestClient(app), tmp_path / "out"


def _payload(**over):
    base = {"pid": "bottom_burst", "scan_ts": "20260728T150000",
            "win_start": "2024-09-19", "win_end": "2026-02-03",
            "start_date": "2025-01-01", "end_date": "2026-01-01",
            "wc": {"bo": {"total_window": 20}}, "enabled": True}
    base.update(over)
    return base


def test_wc_mirror_writes_file(wc_client):
    client, out_dir = wc_client
    r = client.post("/params/wc-mirror", json=_payload())
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["path"].endswith("wc.json")
    assert (out_dir / "wc.json").exists()
    data = json.loads((out_dir / "wc.json").read_text())
    assert data["pid"] == "bottom_burst"
    assert data["scan_ts"] == "20260728T150000"
    assert data["win_start"] == "2024-09-19"
    assert data["win_end"] == "2026-02-03"
    assert data["start_date"] == "2025-01-01"
    assert data["end_date"] == "2026-01-01"
    assert data["wc"]["bo"]["total_window"] == 20
    assert data["enabled"] is True
    assert "written_at" in data


def test_wc_mirror_overwrites_single_file(wc_client):
    """单一覆盖文件:二次写覆盖(不追加/不堆积)。"""
    client, out_dir = wc_client
    client.post("/params/wc-mirror", json=_payload(wc={"bo": {"total_window": 33}}, enabled=False))
    client.post("/params/wc-mirror", json=_payload(wc={"bo": {"total_window": 44}}, enabled=True))
    data = json.loads((out_dir / "wc.json").read_text())
    assert data["wc"]["bo"]["total_window"] == 44   # 覆盖,非 33
    assert data["enabled"] is True


def test_wc_mirror_bad_scan_ts_400(wc_client):
    client, _ = wc_client
    r = client.post("/params/wc-mirror", json=_payload(scan_ts="not-a-ts"))
    assert r.status_code == 400


def test_wc_clear_removes_existing(wc_client):
    client, out_dir = wc_client
    client.post("/params/wc-mirror", json=_payload())
    assert (out_dir / "wc.json").exists()
    r = client.post("/params/wc-clear", json={"pid": "bottom_burst"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert not (out_dir / "wc.json").exists()


def test_wc_clear_missing_is_noop(wc_client):
    """wc.json 不存在时清不报错(idempotent)。"""
    client, out_dir = wc_client
    assert not (out_dir / "wc.json").exists()
    r = client.post("/params/wc-clear", json={"pid": "bottom_burst"})
    assert r.status_code == 200
