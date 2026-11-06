"""compare 用的 mapping 文件(path2_web/mapping.py):path2_apps/<app>/mapping.yaml 写明标注里的 pattern
用这个 app、哪个特征编号由哪个 node 认;GET /mappings 把全部 app 的 mapping 连同查出来的问题给前端。

- 读得懂的照原样给出(没写 notes 时 notes 为空字典);没有文件的 app 不出现;
- 读不懂、pattern 或 features 形状不对、node 不在 app 的 dag 里、notes 形状不对或键指向 dag 里没有的 node / where、
  两个 app 写了同一个 pattern:problem 写明原因;
- 真 app new_step 的 mapping 文件本身读得懂,plateau 上每条 where 都有 notes;
- 路由每次请求都重读文件(会话在后端开着时写 mapping,前端再要一次就拿到)。
测试不往 path2_apps/ 里写文件:mapping_path 换成临时目录里的文件。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import path2_apps.bo_only.dag_spec as bo_only
import path2_apps.new_step.dag_spec as new_step
from path2_web import mapping as mapping_mod
from path2_web.app import create_app
from tests.path2_web.conftest import data_cfg


class _Registry:
    def __init__(self, mods: dict):
        self._mods = mods

    def ids(self):
        return sorted(self._mods)

    def get(self, app):
        return self._mods.get(app)


@pytest.fixture
def files(tmp_path, monkeypatch):
    """每个 app 的 mapping 文件放在 tmp_path/<app>/mapping.yaml;返回写文件的函数。"""
    monkeypatch.setattr(mapping_mod, "mapping_path",
                        lambda mod: tmp_path / mod.__name__.split(".")[-2] / mapping_mod.MAPPING_FILE)

    def write(app: str, text: str):
        d = tmp_path / app
        d.mkdir(exist_ok=True)
        (d / mapping_mod.MAPPING_FILE).write_text(text, encoding="utf-8")
    return write


def _fake(app: str, nodes=("a", "b"), wheres: dict | None = None):
    """只有 build_pattern 的假 app 模块:dag 里的 node 是 nodes,wheres 给每个 node 上 where 的名字。"""
    topo = SimpleNamespace(nodes=[SimpleNamespace(node_id=n) for n in nodes])
    specs = [SimpleNamespace(node_id=n, where=tuple((w, None) for w in (wheres or {}).get(n, ()))) for n in nodes]
    return SimpleNamespace(__name__=f"path2_apps.{app}.dag_spec", load_params=lambda: None,
                           build_pattern=lambda p: SimpleNamespace(to_topology=lambda: topo, nodes=specs))


def test_mapping_file_sits_next_to_dag_spec():
    p = mapping_mod.mapping_path(bo_only)
    assert p.name == "mapping.yaml" and p.parent.name == "bo_only"
    assert (p.parent / "dag_spec.py").is_file()


def test_reads_valid_mapping_and_skips_apps_without_file(files):
    files("x", "pattern: 放量突破\nfeatures:\n  w-pc-3: a\n  w-pc-7: b\n")
    reg = _Registry({"x": _fake("x"), "y": _fake("y")})
    assert mapping_mod.read_mappings(reg) == [
        {"app": "x", "pattern": "放量突破", "features": {"w-pc-3": "a", "w-pc-7": "b"}, "notes": {}, "problem": None}]


def test_real_app_nodes_checked(files):
    files("bo_only", "pattern: p\nfeatures:\n  w-pc-1: bo\n  w-pc-2: nope\n")
    [m] = mapping_mod.read_mappings(_Registry({"bo_only": bo_only}))
    assert m["problem"] == "node not in app bo_only: nope"
    files("bo_only", "pattern: p\nfeatures:\n  w-pc-1: bo\n")
    [m] = mapping_mod.read_mappings(_Registry({"bo_only": bo_only}))
    assert m["problem"] is None and m["features"] == {"w-pc-1": "bo"}


@pytest.mark.parametrize("text, problem", [
    ("pattern: [unclosed\n", "mapping.yaml cannot be read: "),
    ("- a\n- b\n", "pattern must be a non-empty string"),
    ("pattern: '  '\nfeatures: {w-pc-1: a}\n", "pattern must be a non-empty string"),
    ("pattern: p\n", "features must map feature ids to node ids"),
    ("pattern: p\nfeatures: [a]\n", "features must map feature ids to node ids"),
    ("pattern: p\nfeatures: {w-pc-1: 3}\n", "features must map feature ids to node ids"),
])
def test_bad_files_report_problem(files, text, problem):
    files("x", text)
    [m] = mapping_mod.read_mappings(_Registry({"x": _fake("x")}))
    assert m["app"] == "x" and m["problem"].startswith(problem)


def test_same_pattern_in_two_apps_blocks_both(files):
    files("x", "pattern: p\nfeatures: {w-pc-1: a}\n")
    files("y", "pattern: p\nfeatures: {w-pc-1: b}\n")
    files("z", "pattern: q\nfeatures: {w-pc-1: b}\n")
    ms = mapping_mod.read_mappings(_Registry({a: _fake(a) for a in "xyz"}))
    assert [(m["app"], m["problem"]) for m in ms] == [
        ("x", "pattern also mapped by app y"), ("y", "pattern also mapped by app x"), ("z", None)]


def test_route_rereads_files_each_request(tmp_path, files):
    c = TestClient(create_app(config_override=data_cfg(tmp_path), outputs_root=str(tmp_path / "outputs")))
    assert c.get("/mappings").json() == []
    files("bo_only", "pattern: p\nfeatures: {w-pc-1: bo}\n")
    assert c.get("/mappings").json() == [
        {"app": "bo_only", "pattern": "p", "features": {"w-pc-1": "bo"}, "notes": {}, "problem": None}]


def test_notes_for_nodes_and_wheres(files):
    files("x", "pattern: p\nfeatures: {w-pc-1: a}\nnotes:\n  a: 旧平台\n  a.flat: 旧平台平\n  b.flat: 另一条\n")
    [m] = mapping_mod.read_mappings(_Registry({"x": _fake("x", wheres={"a": ["flat"], "b": ["flat"]})}))
    assert m["problem"] is None
    assert m["notes"] == {"a": "旧平台", "a.flat": "旧平台平", "b.flat": "另一条"}


@pytest.mark.parametrize("notes, problem", [
    ("[a]", "notes must map node ids or node.where names to non-empty text"),
    ("{a: ''}", "notes must map node ids or node.where names to non-empty text"),
    ("{a: 3}", "notes must map node ids or node.where names to non-empty text"),
    ("{c: 说明}", "notes refer to nothing in app x: c"),
    ("{a.nope: 说明, b: 说明}", "notes refer to nothing in app x: a.nope"),
    ("{b.flat: 说明}", "notes refer to nothing in app x: b.flat"),
])
def test_bad_notes_report_problem(files, notes, problem):
    files("x", f"pattern: p\nfeatures: {{w-pc-1: a}}\nnotes: {notes}\n")
    [m] = mapping_mod.read_mappings(_Registry({"x": _fake("x", wheres={"a": ["flat"]})}))
    assert m["problem"] == problem


def test_new_step_mapping_file_is_readable_and_explains_every_where():
    """真文件(path2_apps/new_step/mapping.yaml):读得懂;plateau 上每条 where 都有一句 notes,界面上不会只剩英文名。"""
    [m] = mapping_mod.read_mappings(_Registry({"new_step": new_step}))
    assert m["problem"] is None and m["pattern"] == "new_step"
    spec = new_step.build_pattern(new_step.load_params())
    plateau = next(n for n in spec.nodes if n.node_id == "plateau")
    assert {f"plateau.{cid}" for cid, _ in plateau.where} <= set(m["notes"])
