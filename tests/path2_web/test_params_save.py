# tests/path2_web/test_params_save.py
"""POST /params/save:strict 校验 + 已存在文件 ruamel round-trip 保注释 +
新文件 safe_dump + 文件名白名单。吸收原 /params/apply(晋升 = name=params.yaml 的特例)。"""
import textwrap

import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def save_client(tmp_path, monkeypatch):
    """真实 registry(bo_only 走 dag_spec)+ monkeypatch DEFAULT_YAML_PATH 指向
    tmp 沙箱目录里的 params.yaml(包与 dag_spec 子模块两处都 patch,
    同 test_params_files.py 惯用法)。"""
    yaml_dir = tmp_path / "app"
    yaml_dir.mkdir()
    yaml_file = yaml_dir / "params.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        # 顶部说明注释:字段语义 SSoT
        bo:
          total_window: 10   # 结构窗
          min_side_bars: 2
    """))

    import path2_apps.bo_only as _bo
    import path2_apps.bo_only.dag_spec as _bo_dag
    monkeypatch.setattr(_bo, "DEFAULT_YAML_PATH", yaml_file)
    monkeypatch.setattr(_bo_dag, "DEFAULT_YAML_PATH", yaml_file)

    app = create_app(config_path=tmp_path / "config.json",
                     outputs_root=str(tmp_path / "out"), use_thread_pool=True)
    return TestClient(app), yaml_dir


def _valid_params(total_window=33):
    from path2_apps.bo_only.params import Params
    d = Params.default().to_dict()
    d["bo"]["total_window"] = total_window
    return d


def test_save_existing_preserves_comments(save_client):
    client, yaml_dir = save_client
    r = client.post("/params/save", json={
        "pattern_id": "bo_only", "name": "params.yaml", "params": _valid_params(33)})
    assert r.status_code == 200
    text = (yaml_dir / "params.yaml").read_text()
    assert "total_window: 33" in text
    assert "# 顶部说明注释:字段语义 SSoT" in text   # 注释存活(杀注释回归 gate)
    assert "# 结构窗" in text   # 行内注释存活(退化成"整段替换 section"只会杀死这条,顶部注释测不出)


def test_save_new_file_plain_dump(save_client):
    client, yaml_dir = save_client
    r = client.post("/params/save", json={
        "pattern_id": "bo_only", "name": "exp_wide.yaml", "params": _valid_params(40)})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["path"].endswith("exp_wide.yaml")   # 响应体契约(Task 3 前端逐字消费)
    assert (yaml_dir / "exp_wide.yaml").exists()
    import yaml as _yaml
    data = _yaml.safe_load((yaml_dir / "exp_wide.yaml").read_text())
    assert data["bo"]["total_window"] == 40


def test_save_strict_validation_400(save_client):
    client, yaml_dir = save_client
    bad = _valid_params()
    bad["bo"]["bogus_field"] = 1
    r = client.post("/params/save", json={
        "pattern_id": "bo_only", "name": "params.yaml", "params": bad})
    assert r.status_code == 400
    # 核心安全属性:strict 校验失败必须不落盘。fixture 写入的原值是 total_window=10,
    # 而 _valid_params() 默认是 33——若实现改成先写后校验(或先截断再校验),这里会看到
    # 10 变成 33 而挂,是真判别式(非同义反复)。
    assert "total_window: 10" in (yaml_dir / "params.yaml").read_text()


@pytest.mark.parametrize("bad", ["../evil.yaml", "a/b.yaml", "x.yml"])
def test_save_bad_name_400(save_client, bad):
    client, _ = save_client
    r = client.post("/params/save", json={
        "pattern_id": "bo_only", "name": bad, "params": _valid_params()})
    assert r.status_code == 400


def test_old_apply_route_gone(save_client):
    client, _ = save_client
    r = client.post("/params/apply", json={
        "pattern_id": "bo_only", "params": _valid_params()})
    assert r.status_code in (404, 405)


def test_save_unknown_pattern_404(save_client):
    client, _ = save_client
    r = client.post("/params/save", json={
        "pattern_id": "no_such_pattern", "name": "params.yaml", "params": _valid_params()})
    assert r.status_code == 404


def test_save_to_empty_existing_file_plain_dump(save_client):
    """目标文件存在但内容为空/全空白 → 与"文件不存在"同走 safe_dump 分支
    (旧 test_apply_creates_missing_sections 覆盖过此分支,rename 时丢了)。"""
    client, yaml_dir = save_client
    (yaml_dir / "blank_target.yaml").write_text("   \n")   # 存在但全空白
    r = client.post("/params/save", json={
        "pattern_id": "bo_only", "name": "blank_target.yaml", "params": _valid_params(40)})
    assert r.status_code == 200
    import yaml as _yaml
    data = _yaml.safe_load((yaml_dir / "blank_target.yaml").read_text())
    assert data["bo"]["total_window"] == 40


def test_save_bad_existing_yaml_400(save_client):
    """目标文件已存在但语法非法(ruamel round-trip 分支)→ 400,不是裸 500。
    与 Task 1 的 GET /params/file 坏 yaml→400 惯例对称;Save As 之后用户可能手改坏
    实验文件再点 Save,是可预期输入。此处无数据丢失风险(load 发生在 open(p,"w") 截断之前)。"""
    client, yaml_dir = save_client
    (yaml_dir / "params.yaml").write_text("bo: {total_window: 10\n")   # 未闭合的 flow mapping
    r = client.post("/params/save", json={
        "pattern_id": "bo_only", "name": "params.yaml", "params": _valid_params()})
    assert r.status_code == 400


def test_save_existing_non_mapping_root_400(save_client):
    """F-D:目标文件已存在且语法合法,但根不是映射(顶层是 list)→ 400,不是裸 500。
    ruamel round-trip 分支里 ry.load 对 list 根返回 CommentedSeq(不是 dict),不挡的话
    下面 doc[section] = ... 对 list 取字符串下标会抛 TypeError 逃出 handler。与 GET
    /params/file 的 test_file_scalar_root_400 对称,补的是 save 侧同族守卫的缺口。"""
    client, yaml_dir = save_client
    (yaml_dir / "params.yaml").write_text("- a\n- b\n")   # 语法合法,根是 list
    r = client.post("/params/save", json={
        "pattern_id": "bo_only", "name": "params.yaml", "params": _valid_params()})
    assert r.status_code == 400
