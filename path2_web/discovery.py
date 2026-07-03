"""pattern 发现:扫 path2_apps/*/ 找含 PATTERN_DAG + eval_meta 的包,建 {pattern_id: module} 注册表。

新 app 必须:
1. 模块级常量 PATTERN_DAG
2. callable analyze(df, params=None)
3. callable eval_meta(params=None) -> {"end_role": str, "head_buffer_trading_days": int}

任一缺失 / 报错 → 跳过 + log warning,/patterns 不返回。
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
import sys

log = logging.getLogger(__name__)


def _validate_eval_meta(mod, name: str) -> str | None:
    """检查 mod 满足 eval_meta 协议;返回错误说明 str(None=OK)。"""
    fn = getattr(mod, "eval_meta", None)
    if not callable(fn):
        return "missing callable eval_meta()"
    load_params = getattr(mod, "load_params", None)
    try:
        meta = fn(load_params()) if callable(load_params) else fn()
    except Exception as e:           # noqa: BLE001
        return f"eval_meta() raised: {type(e).__name__}: {e}"
    if not isinstance(meta, dict):
        return f"eval_meta() returned non-dict: {type(meta).__name__}"
    if "end_role" not in meta or not isinstance(meta["end_role"], str):
        return "eval_meta() missing or non-str 'end_role'"
    if ("head_buffer_trading_days" not in meta
            or not isinstance(meta["head_buffer_trading_days"], int)):
        return "eval_meta() missing or non-int 'head_buffer_trading_days'"
    return None


def _discover(apps_pkg: str):
    """返回 (modules: {pattern_id: module}, errors: {sub_pkg_name: err_str})。"""
    modules, errors = {}, {}
    try:
        pkg = importlib.import_module(apps_pkg)
    except Exception as e:
        return modules, {apps_pkg: f"{type(e).__name__}: {e}"}
    for m in pkgutil.iter_modules(pkg.__path__):
        if not m.ispkg:
            continue
        try:
            mod = importlib.import_module(f"{apps_pkg}.{m.name}.dag_spec")
            dag = getattr(mod, "PATTERN_DAG", None)
            if dag is None:
                continue
            err = _validate_eval_meta(mod, m.name)
            if err:
                errors[m.name] = f"eval_meta gate: {err}"
                log.warning("pattern %r skipped: %s", m.name, err)
                continue
            modules[dag.pattern_id] = mod
        except Exception as e:
            errors[m.name] = f"{type(e).__name__}: {e}"
    return modules, errors


class PatternRegistry:
    """缓存含 PATTERN_DAG + 合规 eval_meta 的 app 模块。
    refresh 重扫;invalidate 弹某 pattern 子模块缓存。"""

    def __init__(self, apps_pkg: str = "path2_apps"):
        self.apps_pkg = apps_pkg
        self._modules: dict = {}
        self._errors: dict = {}
        self.refresh()

    def refresh(self) -> None:
        importlib.invalidate_caches()
        self._modules, self._errors = _discover(self.apps_pkg)

    def ids(self) -> list:
        return sorted(self._modules)

    def errors(self) -> dict:
        return dict(self._errors)

    def get(self, pattern_id: str):
        return self._modules.get(pattern_id)

    def module_path(self, pattern_id: str):
        mod = self._modules.get(pattern_id)
        return mod.__name__ if mod else None

    def invalidate(self, pattern_id: str) -> None:
        mod = self._modules.get(pattern_id)
        if mod is None:
            return
        app_prefix = mod.__name__.rsplit(".", 1)[0]
        for name in [n for n in sys.modules if n == app_prefix or n.startswith(app_prefix + ".")]:
            sys.modules.pop(name, None)
        self.refresh()
