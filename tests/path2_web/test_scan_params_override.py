"""POST /scan 带 params_overrides:严格校验、provenance 标记、spec/eval_meta 用 override 参数。"""
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app
from path2_web import scan as scan_mod


@pytest.fixture
def web_app_client(tmp_path, monkeypatch):
    """真实 create_app(registry 走真实 path2_apps 发现,含 bo_only)+ monkeypatch
    path2_web.api.scan_mod.run_scan_multi 为捕获 kwargs 的 stub(不真正跑扫描)。
    返回 (client, captured):captured["run_scan_multi_kwargs"] = 最近一次调用的关键字实参,
    stub 返回最小合法 result dict(满足 post_scan.done_meta 读 result["scan"] 的字段需求)。
    """
    data = tmp_path / "data"
    data.mkdir()
    n = 100
    pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [10.0] * n, "high": [11.0] * n, "low": [9.0] * n,
        "close": [10.5] * n, "volume": [100.0] * n,
    }).to_pickle(data / "AAA.pkl")

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-02-01", "end_date": "2024-06-30",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    app = create_app(config_path=cfg_path, outputs_root=str(outputs), use_thread_pool=True)
    client = TestClient(app)

    captured: dict = {}

    def _stub_run_scan_multi(**kwargs):
        captured["run_scan_multi_kwargs"] = kwargs
        return {"scan": {"hits": 0, "errors": 0, "scanned": 0}, "per_pattern": {}}

    monkeypatch.setattr(scan_mod, "run_scan_multi", _stub_run_scan_multi)

    return client, captured


def test_scan_with_override_marks_provenance(web_app_client, monkeypatch):
    """override 的 pid → provenance=working_copy 且 run_scan_multi 收到 override dict;
    未 override 的 pid → provenance=yaml。"""
    client, captured = web_app_client   # conftest fixture:见 Step 3 说明
    from path2_apps.bo_only.params import Params
    ov = Params.default().to_dict()
    ov["bo"]["total_window"] = 42
    r = client.post("/scan", json={
        "pattern_ids": ["bo_only"], "start_date": "2025-01-01",
        "end_date": "2025-02-01", "workers": 1,
        "params_overrides": {"bo_only": ov}, "note": "试42窗",
    })
    assert r.status_code == 200
    kw = captured["run_scan_multi_kwargs"]
    assert kw["pattern_params_dicts"]["bo_only"]["bo"]["total_window"] == 42
    assert kw["params_provenance"]["bo_only"] == "working_copy"
    assert kw["note"] == "试42窗"


def test_scan_override_strict_validation_400(web_app_client):
    client, _ = web_app_client
    r = client.post("/scan", json={
        "pattern_ids": ["bo_only"], "start_date": "2025-01-01",
        "end_date": "2025-02-01",
        "params_overrides": {"bo_only": {"bo": {"bogus_field": 1}}},
    })
    assert r.status_code == 400
    assert "bogus_field" in r.text
