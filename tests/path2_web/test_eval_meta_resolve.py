"""resolve_eval_meta:app 模块可选 eval_meta() 协议的防御性读取。"""
import importlib

from path2_web.api import resolve_eval_meta


class _Mod:
    pass


def test_missing_returns_none():
    assert resolve_eval_meta(_Mod()) is None


def test_not_callable_returns_none():
    m = _Mod()
    m.eval_meta = "not callable"
    assert resolve_eval_meta(m) is None


def test_raising_returns_none():
    m = _Mod()

    def boom():
        raise RuntimeError("x")

    m.eval_meta = boom
    assert resolve_eval_meta(m) is None


def test_incomplete_keys_returns_none():
    m = _Mod()
    m.eval_meta = lambda: {"end_role": "tb"}
    assert resolve_eval_meta(m) is None


def test_valid_meta_passthrough():
    m = _Mod()
    m.eval_meta = lambda: {"end_role": "tb", "head_buffer_trading_days": 63}
    assert resolve_eval_meta(m) == {"end_role": "tb", "head_buffer_trading_days": 63}


def test_real_app_resolves():
    """真实 app(Task 1 已加 eval_meta)能被解析。"""
    mod = importlib.import_module("path2_apps.bottom_breakout_burst.dag_spec")
    assert resolve_eval_meta(mod) == {"end_role": "tb", "head_buffer_trading_days": 63}
