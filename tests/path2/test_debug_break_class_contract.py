"""v4 契约 C AST lint · 跨 detector 通用契约测试。

契约:
- path2/atoms/ 下任何 .py 文件,若含 `debug_break(...)` call → 该文件里的 Detector 类必须
  显式标注 `has_debug_hooks: ClassVar[bool] = True`
- 无 debug_break call 的 detector 类应保持默认 has_debug_hooks = False(不强测,只测有 hook 侧)
- 允许多个 Detector 类共存于一文件(如 breakout.py 有 BurstDetector + BODetector)· lint 只要求
  "有 debug_break call 的文件里至少一个类标 True"(粗粒度 · 避免 false-positive)

严格版可选:
- 若未来加多 Detector 分层的判断(比如 breakout.py 里只有 BODetector 有 hook,BurstDetector 无),
  可以升级为"标 True 的类等于埋 debug_break 的类"· 本轮不做(YAGNI · 今天 tb 一家)。
"""
import ast
import pathlib


ATOMS_DIR = pathlib.Path(__file__).resolve().parents[2] / "path2" / "atoms"


def _module_has_debug_break_call(module_path: pathlib.Path) -> bool:
    src = module_path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(module_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "debug_break":
            return True
    return False


def _module_has_hooks_flag_true(module_path: pathlib.Path) -> bool:
    """检查文件里是否至少一个类体上有 `has_debug_hooks: ClassVar[bool] = True`
    或 `has_debug_hooks = True`(不强制 ClassVar 注解,只强制值 True)。"""
    src = module_path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(module_path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            # AnnAssign: has_debug_hooks: ClassVar[bool] = True
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) \
                    and stmt.target.id == "has_debug_hooks" \
                    and stmt.value is not None \
                    and isinstance(stmt.value, ast.Constant) and stmt.value.value is True:
                return True
            # Assign: has_debug_hooks = True
            if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "has_debug_hooks" for t in stmt.targets) \
                    and isinstance(stmt.value, ast.Constant) and stmt.value.value is True:
                return True
    return False


def test_every_debug_break_module_has_hooks_flag_true():
    """任何 detector 文件含 debug_break call → 至少一个类标 has_debug_hooks=True。"""
    offenders = []
    for py in sorted(ATOMS_DIR.glob("*.py")):
        if py.name == "__init__.py":
            continue
        if _module_has_debug_break_call(py) and not _module_has_hooks_flag_true(py):
            offenders.append(py.name)
    assert not offenders, (
        f"以下 detector 文件含 debug_break 调用但没有类标 has_debug_hooks=True:\n"
        f"  {offenders}\n"
        f"契约 C 要求:埋 debug_break 时同 diff 在类体上加 `has_debug_hooks: ClassVar[bool] = True`"
    )


def test_throwback_module_marks_flag_true():
    """具体校验 throwback.py 已标(guard against false-positive from粗粒度 lint)。"""
    assert _module_has_hooks_flag_true(ATOMS_DIR / "throwback.py")
