import importlib

import path2.config


def test_default_is_on(monkeypatch):
    monkeypatch.delenv("PATH2_RUNTIME_CHECKS", raising=False)
    importlib.reload(path2.config)
    assert path2.config.RUNTIME_CHECKS is True
    monkeypatch.delenv("PATH2_RUNTIME_CHECKS", raising=False)
    importlib.reload(path2.config)


def test_env_off_variants(monkeypatch):
    for val in ("0", "false", "off", "no", "FALSE", "Off"):
        monkeypatch.setenv("PATH2_RUNTIME_CHECKS", val)
        importlib.reload(path2.config)
        assert path2.config.RUNTIME_CHECKS is False, val
    monkeypatch.delenv("PATH2_RUNTIME_CHECKS", raising=False)
    importlib.reload(path2.config)
    assert path2.config.RUNTIME_CHECKS is True


def test_env_on_when_unrecognized(monkeypatch):
    monkeypatch.setenv("PATH2_RUNTIME_CHECKS", "1")
    importlib.reload(path2.config)
    assert path2.config.RUNTIME_CHECKS is True
    monkeypatch.delenv("PATH2_RUNTIME_CHECKS", raising=False)
    importlib.reload(path2.config)


def test_set_runtime_checks_toggles():
    from path2 import config
    config.set_runtime_checks(False)
    assert config.RUNTIME_CHECKS is False
    config.set_runtime_checks(True)
    assert config.RUNTIME_CHECKS is True


def test_attribute_access_propagates():
    """证明:通过模块属性访问能看到 set_runtime_checks 的变更。
    这是设计稿强制'禁用 from-import'约定的依据。"""
    from path2 import config

    def reader():
        return config.RUNTIME_CHECKS

    config.set_runtime_checks(False)
    assert reader() is False
    config.set_runtime_checks(True)
    assert reader() is True
