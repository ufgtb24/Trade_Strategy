from path2_web.discovery import PatternRegistry


def test_discovers_bottom_breakout_burst():
    reg = PatternRegistry()
    assert "bottom_breakout_burst" in reg.ids()
    mod = reg.get("bottom_breakout_burst")
    assert hasattr(mod, "PATTERN_DAG")
    assert hasattr(mod, "analyze")
    # module_path 供子进程 import
    assert reg.module_path("bottom_breakout_burst") == "path2_apps.bottom_breakout_burst.dag_spec"


def test_unknown_pattern_returns_none():
    reg = PatternRegistry()
    assert reg.get("does_not_exist") is None


def test_refresh_idempotent():
    reg = PatternRegistry()
    before = set(reg.ids())
    reg.refresh()
    assert set(reg.ids()) == before


def test_broken_package_skipped(tmp_path, monkeypatch):
    # 在一个临时 apps 包里放一个 import 即抛错的 dag_spec → 记录 error、不崩
    import sys, importlib
    pkg = tmp_path / "fake_apps_broken"
    (pkg / "good" ).mkdir(parents=True)
    (pkg / "bad").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "good" / "__init__.py").write_text("")
    (pkg / "bad" / "__init__.py").write_text("")
    (pkg / "good" / "dag_spec.py").write_text(
        "class _S:\n    pattern_id='good_pat'\nPATTERN_DAG=_S()\n"
        "def eval_meta(): return {'end_role': 'bo', 'head_buffer_trading_days': 20}\n"
    )
    (pkg / "bad" / "dag_spec.py").write_text("raise RuntimeError('boom')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    reg = PatternRegistry(apps_pkg="fake_apps_broken")
    assert "good_pat" in reg.ids()
    assert "bad" in reg.errors()        # 残缺包记录错误、跳过
