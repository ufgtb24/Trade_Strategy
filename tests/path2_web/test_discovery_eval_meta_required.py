"""discovery 闸:pattern 必须声明 eval_meta 协议,否则跳过 + warning。"""
import logging
import pytest

from path2_web.discovery import _discover, PatternRegistry


def test_real_apps_pass_gate():
    """真实 path2_apps 下的 bottom_burst 与 bo_only 都过闸。"""
    modules, errors = _discover("path2_apps")
    assert "bottom_burst" in modules
    assert "bo_only" in modules
    # 不应当因 eval_meta 闸误杀任一现有 pattern
    assert errors == {} or all("eval_meta" not in str(e) for e in errors.values()), errors


def test_fake_app_missing_eval_meta_is_filtered(tmp_path, monkeypatch, caplog):
    """fake_app 不声明 eval_meta → 不进 registry + log warning。"""
    # 用 tmp_path 仿造 path2_apps 包结构
    apps_dir = tmp_path / "fake_apps"
    apps_dir.mkdir()
    (apps_dir / "__init__.py").write_text("")
    sub = apps_dir / "no_meta"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "dag_spec.py").write_text(
        "from path2.dag.nodes import NodeSpec\n"
        "from path2.dag.spec import PatternSpec\n"
        "from path2.atoms.breakout import BODetector\n"
        "det = BODetector()\n"
        "PATTERN_DAG = PatternSpec(pattern_id='no_meta',\n"
        "                         nodes=(NodeSpec('bo', det, produces_stream='bo'),\n"
        "                                NodeSpec('pk', det, produces_stream='pk', solve=False, render_grid='price'),), edges=())\n"
        "def analyze(df, params=None): return None\n"
        "# 故意不定义 eval_meta\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        modules, errors = _discover("fake_apps")
    assert "no_meta" not in modules
    assert "no_meta" in errors
    assert "eval_meta" in errors["no_meta"]
    assert any("eval_meta" in r.message for r in caplog.records)


def test_fake_app_eval_meta_missing_end_node(tmp_path, monkeypatch, caplog):
    """eval_meta 返回 dict 缺 end_node → 跳过 + warning。"""
    apps_dir = tmp_path / "fake_apps2"
    apps_dir.mkdir()
    (apps_dir / "__init__.py").write_text("")
    sub = apps_dir / "bad_meta"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "dag_spec.py").write_text(
        "from path2.dag.nodes import NodeSpec\n"
        "from path2.dag.spec import PatternSpec\n"
        "from path2.atoms.breakout import BODetector\n"
        "det = BODetector()\n"
        "PATTERN_DAG = PatternSpec(pattern_id='bad_meta',\n"
        "                         nodes=(NodeSpec('bo', det, produces_stream='bo'),\n"
        "                                NodeSpec('pk', det, produces_stream='pk', solve=False, render_grid='price'),), edges=())\n"
        "def analyze(df, params=None): return None\n"
        "def eval_meta(params=None): return {'head_buffer_trading_days': 60}   # 缺 end_node\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        modules, errors = _discover("fake_apps2")
    assert "bad_meta" not in modules
    assert "bad_meta" in errors


def test_fake_app_eval_meta_missing_head_buffer(tmp_path, monkeypatch, caplog):
    """eval_meta 返回 dict 缺 head_buffer_trading_days → 跳过 + warning。"""
    apps_dir = tmp_path / "fake_apps3"
    apps_dir.mkdir()
    (apps_dir / "__init__.py").write_text("")
    sub = apps_dir / "bad_meta2"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "dag_spec.py").write_text(
        "from path2.dag.nodes import NodeSpec\n"
        "from path2.dag.spec import PatternSpec\n"
        "from path2.atoms.breakout import BODetector\n"
        "det = BODetector()\n"
        "PATTERN_DAG = PatternSpec(pattern_id='bad_meta2',\n"
        "                         nodes=(NodeSpec('bo', det, produces_stream='bo'),\n"
        "                                NodeSpec('pk', det, produces_stream='pk', solve=False, render_grid='price'),), edges=())\n"
        "def analyze(df, params=None): return None\n"
        "def eval_meta(params=None): return {'end_node': 'bo'}   # 缺 head_buffer\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        modules, errors = _discover("fake_apps3")
    assert "bad_meta2" not in modules
    assert "bad_meta2" in errors


def test_fake_app_eval_meta_raises(tmp_path, monkeypatch, caplog):
    """eval_meta 调用抛异常 → 跳过 + warning。"""
    apps_dir = tmp_path / "fake_apps4"
    apps_dir.mkdir()
    (apps_dir / "__init__.py").write_text("")
    sub = apps_dir / "throw_meta"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "dag_spec.py").write_text(
        "from path2.dag.nodes import NodeSpec\n"
        "from path2.dag.spec import PatternSpec\n"
        "from path2.atoms.breakout import BODetector\n"
        "det = BODetector()\n"
        "PATTERN_DAG = PatternSpec(pattern_id='throw_meta',\n"
        "                         nodes=(NodeSpec('bo', det, produces_stream='bo'),\n"
        "                                NodeSpec('pk', det, produces_stream='pk', solve=False, render_grid='price'),), edges=())\n"
        "def analyze(df, params=None): return None\n"
        "def eval_meta(params=None): raise RuntimeError('boom')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        modules, errors = _discover("fake_apps4")
    assert "throw_meta" not in modules
    assert "throw_meta" in errors
