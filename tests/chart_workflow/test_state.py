"""状态根:在 worktree 里指向主目录;没有标记文件就抛 StateRootMissing(消息含「可能切到了别的分支」),
init 之后正常;记账类路径一律不经 root_dir 拼(只有一个家)。"""
import ast
import re
import subprocess
from pathlib import Path

import pytest

from chart_workflow import state
from chart_workflow.config import REPO_ROOT


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin",
                        "HOME": str(cwd)})


def test_worktree_resolves_to_main_and_marker_required(tmp_path, monkeypatch):
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "master")
    (main / "a.txt").write_text("x")
    _git(main, "add", "a.txt")
    _git(main, "commit", "-q", "-m", "init")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", "-b", "side", str(wt))

    assert state.main_worktree(start=wt) == main.resolve()
    assert state.main_worktree(start=main) == main.resolve()

    monkeypatch.delenv(state.ENV_VAR, raising=False)
    with pytest.raises(state.StateRootMissing) as ei:
        state.state_root(start=wt)
    assert "可能切到了别的分支" in str(ei.value)
    assert str(main.resolve() / "outputs" / "chart_workflow") in str(ei.value)
    assert not (main / "outputs").exists()            # 绝不悄悄新建

    state.init(main / "outputs" / "chart_workflow")
    assert state.state_root(start=wt) == main.resolve() / "outputs" / "chart_workflow"
    assert state.state_root(start=main) == state.state_root(start=wt)


def test_env_var_wins_and_still_needs_marker(tmp_path, monkeypatch):
    d = tmp_path / "elsewhere"
    d.mkdir()
    monkeypatch.setenv(state.ENV_VAR, str(d))
    with pytest.raises(state.StateRootMissing):
        state.state_root()
    state.init(d)
    assert state.state_root() == d.resolve()
    text = (d / state.MARKER).read_text()
    state.init(d)                                      # 已有标记不动
    assert (d / state.MARKER).read_text() == text


def test_not_a_repo(tmp_path, monkeypatch):
    monkeypatch.delenv(state.ENV_VAR, raising=False)
    with pytest.raises(state.StateRootMissing):
        state.main_worktree(start=tmp_path)


# ── 记账类路径不经 root_dir 拼 ─────────────────────────────────────────────
# 判定口径:在 chart_workflow/*.py 与 path2_web/workflow.py 的每个函数体里,
#   ① 一个表达式语句 / 赋值的源码片段同时含 root_dir( 与下列任一记账类名字,或
#   ② 由 root_dir(...) 起头的 `/` 路径链里出现记账类名字的字符串字面量,
# 都算违规。用 AST 找出所有以 root_dir(...) 为最左操作数的 BinOp(Div) 链,检查链上的字面量;
# 另用正则兜底扫同一行里同时出现 root_dir( 与记账类名字的情况。
LEDGER_NAMES = ("annotations", "ledger.jsonl", "views.jsonl", "viewed_lists", "shapes", "oplog",
                "facts", "rule_archive")


def _files():
    return sorted((REPO_ROOT / "chart_workflow").glob("*.py")) + [REPO_ROOT / "path2_web" / "workflow.py"]


def _leftmost(node):
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        node = node.left
    return node


def _is_root_dir_call(node) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ("root_dir", "_root"))


def test_no_ledger_path_built_from_root_dir():
    bad = []
    for f in _files():
        src = f.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) \
                    and _is_root_dir_call(_leftmost(node)):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                            and any(n in sub.value for n in LEDGER_NAMES):
                        bad.append(f"{f.name}:{node.lineno}")
        for i, line in enumerate(src.splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"\b(root_dir|_root)\(", code) and \
                    any(re.search(rf"[\"'/]{re.escape(n)}", code) for n in LEDGER_NAMES):
                bad.append(f"{f.name}:{i}")
    assert not bad, f"记账类路径经 root_dir 拼出:{sorted(set(bad))}"
