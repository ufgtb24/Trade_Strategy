"""pattern 发现:扫 path2_apps/*/ 找含 PATTERN_DAG 的包,建 {pattern_id: module} 注册表。

新 app 手写(放进 path2_apps/<id>/dag_spec.py 并定义模块级 PATTERN_DAG)即被发现,无需改后端。
"""
from __future__ import annotations

import importlib
import pkgutil
import sys


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
            modules[dag.pattern_id] = mod
        except Exception as e:
            errors[m.name] = f"{type(e).__name__}: {e}"
    return modules, errors


class PatternRegistry:
    """缓存含 PATTERN_DAG 的 app 模块。refresh 重扫;invalidate 弹某 pattern 子模块缓存。"""

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
        """弹该 pattern 所在 app 子包的所有已加载子模块,下次 refresh 重 import。"""
        mod = self._modules.get(pattern_id)
        if mod is None:
            return
        # mod.__name__ == "<apps_pkg>.<id>.dag_spec" → 取 "<apps_pkg>.<id>" 前缀
        app_prefix = mod.__name__.rsplit(".", 1)[0]
        for name in [n for n in sys.modules if n == app_prefix or n.startswith(app_prefix + ".")]:
            sys.modules.pop(name, None)
        self.refresh()
