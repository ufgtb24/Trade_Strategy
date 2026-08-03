"""POST /scan 带 params_files:按引用选参数文件、provenance 记文件身份、错误映射。

fixture 把 bo_only 的参数目录沙箱化到 tmp:
- dag_spec/包 init 上的 DEFAULT_YAML_PATH → _params_dir 指向 tmp(registry 注册的是
  .dag_spec 子模块,见 path2_web/discovery.py:51)
- params 子模块上的 DEFAULT_YAML_PATH → load_params() 也读 tmp(它读的是 params 模块
  自己的全局,与上面是不同绑定;不 patch 的话「显式选 params.yaml ≡ 不选」的断言会
  读真实仓库文件、随生产调参漂移)
run_scan_multi 打桩为捕获 kwargs 的 stub(不真跑扫描),同 test_scan_params_override.py。
"""
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app
from path2_web import scan as scan_mod

SCAN_BODY = {"start_date": "2025-01-01", "end_date": "2025-02-01", "workers": 1}


@pytest.fixture
def files_scan_client(tmp_path, monkeypatch):
    yaml_dir = tmp_path / "app"
    yaml_dir.mkdir()
    (yaml_dir / "params.yaml").write_text("bo:\n  total_window: 10\n")
    (yaml_dir / "exp_wide.yaml").write_text("bo:\n  total_window: 40\n")
    (yaml_dir / "bad_field.yaml").write_text("bo:\n  total_windooow: 40\n")
    (yaml_dir / "bad_syntax.yaml").write_text("bo:\n  - [unclosed\n")
    (yaml_dir / "bad_structure.yaml").write_text("bo: 5\n")

    import path2_apps.bo_only as _bo
    import path2_apps.bo_only.dag_spec as _bo_dag
    import path2_apps.bo_only.params as _bo_params
    for m in (_bo, _bo_dag, _bo_params):
        monkeypatch.setattr(m, "DEFAULT_YAML_PATH", yaml_dir / "params.yaml")

    data = tmp_path / "data"
    data.mkdir()
    n = 100
    pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [10.0] * n, "high": [11.0] * n, "low": [9.0] * n,
        "close": [10.5] * n, "volume": [100.0] * n,
    }).to_pickle(data / "AAA.pkl")

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-02-01", "end_date": "2024-06-30",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    app = create_app(config_path=cfg_path, outputs_root=str(tmp_path / "out"),
                     use_thread_pool=True)

    captured: dict = {}

    def _stub_run_scan_multi(**kwargs):
        captured["kw"] = kwargs
        return {"scan": {"hits": 0, "errors": 0, "scanned": 0}, "per_pattern": {}}

    monkeypatch.setattr(scan_mod, "run_scan_multi", _stub_run_scan_multi)
    return TestClient(app), captured


def test_file_source_marks_provenance_and_passes_dict(files_scan_client):
    """选非默认文件 → provenance=file:<name>,且 run_scan_multi 收到该文件的参数。"""
    client, captured = files_scan_client
    r = client.post("/scan", json={"pattern_ids": ["bo_only"],
                                   "params_files": {"bo_only": "exp_wide.yaml"}, **SCAN_BODY})
    assert r.status_code == 200
    kw = captured["kw"]
    assert kw["params_provenance"]["bo_only"] == "file:exp_wide.yaml"
    assert kw["pattern_params_dicts"]["bo_only"]["bo"]["total_window"] == 40


def test_explicit_params_yaml_normalizes_to_yaml(files_scan_client):
    """显式选 params.yaml → provenance 归一化为 "yaml"(不是 file:params.yaml)。"""
    client, captured = files_scan_client
    r = client.post("/scan", json={"pattern_ids": ["bo_only"],
                                   "params_files": {"bo_only": "params.yaml"}, **SCAN_BODY})
    assert r.status_code == 200
    assert captured["kw"]["params_provenance"]["bo_only"] == "yaml"
    assert captured["kw"]["pattern_params_dicts"]["bo_only"]["bo"]["total_window"] == 10


def test_no_params_files_is_unchanged(files_scan_client):
    """不传 params_files → 与今天逐字相同(零回归面守卫,与上一例结果必须一致)。"""
    client, captured = files_scan_client
    r = client.post("/scan", json={"pattern_ids": ["bo_only"], **SCAN_BODY})
    assert r.status_code == 200
    assert captured["kw"]["params_provenance"]["bo_only"] == "yaml"
    assert captured["kw"]["pattern_params_dicts"]["bo_only"]["bo"]["total_window"] == 10


def test_missing_file_400_with_pid_and_name(files_scan_client):
    client, _ = files_scan_client
    r = client.post("/scan", json={"pattern_ids": ["bo_only"],
                                   "params_files": {"bo_only": "ghost.yaml"}, **SCAN_BODY})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "bo_only" in detail and "ghost.yaml" in detail


def test_bad_field_400_with_pid_and_name(files_scan_client):
    """实验文件相对代码过期(拼错/字段已删)是最常见的失败;报文要能定位到
    pid、文件、具体字段三样,否则用户不知道去改哪个文件的哪一行。"""
    client, _ = files_scan_client
    r = client.post("/scan", json={"pattern_ids": ["bo_only"],
                                   "params_files": {"bo_only": "bad_field.yaml"}, **SCAN_BODY})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "bo_only" in detail and "bad_field.yaml" in detail
    assert "total_windooow" in detail


def test_bad_syntax_400_not_500(files_scan_client):
    """yaml 语法坏 → 400,与 /params/file、/params/save 的既有惯例一致,不是裸 500。"""
    client, _ = files_scan_client
    r = client.post("/scan", json={"pattern_ids": ["bo_only"],
                                   "params_files": {"bo_only": "bad_syntax.yaml"}, **SCAN_BODY})
    assert r.status_code == 400


def test_bad_structure_400_not_500_with_pid_and_name(files_scan_client):
    """section 值是标量(如 bo: 5)→ from_yaml 内部曾经 set(sect_data) 对 int 抛
    TypeError,逃出既有 (ValueError, YAMLError) 捕获变成裸 500。收窄到 ValueError
    后走既有 400 惯例,报文仍要能定位到 pid 和文件名。"""
    client, _ = files_scan_client
    r = client.post("/scan", json={"pattern_ids": ["bo_only"],
                                   "params_files": {"bo_only": "bad_structure.yaml"}, **SCAN_BODY})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "bo_only" in detail and "bad_structure.yaml" in detail


def test_bad_name_400_with_pid(files_scan_client):
    client, _ = files_scan_client
    r = client.post("/scan", json={"pattern_ids": ["bo_only"],
                                   "params_files": {"bo_only": "../evil.yaml"}, **SCAN_BODY})
    assert r.status_code == 400
    assert "bo_only" in r.json()["detail"]


def test_filters_passed_through(files_scan_client):
    """price_min/price_max/volume_min 是「请求撞上引擎」唯一未被覆盖的一环:错筛(如
    price_min/price_max 互换)不会让任何既有测试变红,只会静默改变命中数。这里锚死
    三个值原样透传到 run_scan_multi 的对应 kwargs。"""
    client, captured = files_scan_client
    r = client.post("/scan", json={"pattern_ids": ["bo_only"],
                                   "price_min": 0.5, "price_max": 20.0,
                                   "volume_min": 10000.0, **SCAN_BODY})
    assert r.status_code == 200
    kw = captured["kw"]
    assert (kw["price_min"], kw["price_max"], kw["volume_min"]) == (0.5, 20.0, 10000.0)


def test_both_sources_same_pid_400(files_scan_client):
    """同 pid 同时给两个通道 → 显式拒绝,不做隐式优先级。新 UI 是单一下拉、
    结构上触发不了;这条守卫的价值是把「两个字段是两种来源、不是叠加」写进代码。"""
    client, _ = files_scan_client
    from path2_apps.bo_only.params import Params
    r = client.post("/scan", json={"pattern_ids": ["bo_only"],
                                   "params_files": {"bo_only": "exp_wide.yaml"},
                                   "params_overrides": {"bo_only": Params.default().to_dict()},
                                   **SCAN_BODY})
    assert r.status_code == 400
    assert "互斥" in r.json()["detail"]
