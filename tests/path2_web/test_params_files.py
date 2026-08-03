"""GET /params/files(列 app 目录 yaml)+ GET /params/file(读单文件原始 dict)。

fixture 惯用法同 test_params_apply.py::apply_client_factory:monkeypatch
bo_only 包与 dag_spec 子模块两处的 DEFAULT_YAML_PATH 指向 tmp 目录里的 yaml,
使端点的目录扫描/读取都发生在 tmp 沙箱内。
"""
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def files_client(tmp_path, monkeypatch):
    yaml_dir = tmp_path / "app"
    yaml_dir.mkdir()
    (yaml_dir / "params.yaml").write_text("bo:\n  total_window: 10\n")
    (yaml_dir / "exp_wide.yaml").write_text("bo:\n  total_window: 40\n")
    (yaml_dir / "aaa_first.yaml").write_text("bo:\n  total_window: 5\n")
    (yaml_dir / "not_yaml.txt").write_text("ignore me")
    (yaml_dir / "scalar_root.yaml").write_text("just a string\n")
    (yaml_dir / "实验 file.yaml").write_text("bo:\n  total_window: 1\n")

    import path2_apps.bo_only as _bo
    import path2_apps.bo_only.dag_spec as _bo_dag
    monkeypatch.setattr(_bo, "DEFAULT_YAML_PATH", yaml_dir / "params.yaml")
    monkeypatch.setattr(_bo_dag, "DEFAULT_YAML_PATH", yaml_dir / "params.yaml")

    app = create_app(config_path=tmp_path / "config.json",
                     outputs_root=str(tmp_path / "out"), use_thread_pool=True)
    return TestClient(app)


def test_files_lists_yaml_params_first(files_client):
    r = files_client.get("/params/files", params={"pattern_id": "bo_only"})
    assert r.status_code == 200
    # scalar_root.yaml(合法名,F4 fixture)按字典序排入;实验 file.yaml(非白名单
    # 名,F3 fixture)必须被过滤、不出现在返回里——精确列表相等就是 F3 的 teeth。
    assert r.json()["files"] == [
        "params.yaml", "aaa_first.yaml", "exp_wide.yaml", "scalar_root.yaml",
    ]


def test_files_unknown_pattern_404(files_client):
    r = files_client.get("/params/files", params={"pattern_id": "nope"})
    assert r.status_code == 404


def test_file_reads_raw_dict(files_client):
    r = files_client.get("/params/file",
                         params={"pattern_id": "bo_only", "name": "exp_wide.yaml"})
    assert r.status_code == 200
    assert r.json()["params"] == {"bo": {"total_window": 40}}


def test_file_missing_404(files_client):
    r = files_client.get("/params/file",
                         params={"pattern_id": "bo_only", "name": "ghost.yaml"})
    assert r.status_code == 404


def test_file_bad_syntax_400(files_client, tmp_path):
    """语法非法的 yaml 是这个端点的预期输入(编辑区允许装载任意 yaml),解析失败
    应包成 400,不是裸 500。"""
    (tmp_path / "app" / "bad_syntax.yaml").write_text("bo:\n  - [unclosed")
    r = files_client.get("/params/file",
                         params={"pattern_id": "bo_only", "name": "bad_syntax.yaml"})
    assert r.status_code == 400


def test_file_scalar_root_400(files_client):
    r = files_client.get("/params/file",
                         params={"pattern_id": "bo_only", "name": "scalar_root.yaml"})
    assert r.status_code == 400


@pytest.mark.parametrize(
    "bad",
    ["../evil.yaml", "a/b.yaml", "x.yml", "params.yaml.bak", "params.yaml\n"],
)
def test_file_bad_name_400(files_client, bad):
    r = files_client.get("/params/file",
                         params={"pattern_id": "bo_only", "name": bad})
    assert r.status_code == 400


def test_delete_removes_file(files_client, tmp_path):
    r = files_client.delete("/params/file",
                            params={"pattern_id": "bo_only", "name": "exp_wide.yaml"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert "exp_wide.yaml" not in files_client.get(
        "/params/files", params={"pattern_id": "bo_only"}).json()["files"]
    assert not (tmp_path / "app" / "exp_wide.yaml").exists()


def test_delete_params_yaml_400(files_client):
    r = files_client.delete("/params/file",
                            params={"pattern_id": "bo_only", "name": "params.yaml"})
    assert r.status_code == 400


def test_delete_missing_404(files_client):
    r = files_client.delete("/params/file",
                            params={"pattern_id": "bo_only", "name": "ghost.yaml"})
    assert r.status_code == 404


def test_delete_idempotent_second_404(files_client):
    name = "exp_wide.yaml"
    files_client.delete("/params/file", params={"pattern_id": "bo_only", "name": name})
    r = files_client.delete("/params/file", params={"pattern_id": "bo_only", "name": name})
    assert r.status_code == 404


def test_delete_bad_name_400(files_client):
    r = files_client.delete("/params/file",
                            params={"pattern_id": "bo_only", "name": "../evil.yaml"})
    assert r.status_code == 400


def test_delete_unknown_pattern_404(files_client):
    r = files_client.delete("/params/file",
                            params={"pattern_id": "nope", "name": "exp_wide.yaml"})
    assert r.status_code == 404
