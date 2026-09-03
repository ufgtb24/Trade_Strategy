# -*- coding: utf-8 -*-
"""app 退役清理的分级与子串安全。全部在 tmp_path 假树上跑,不碰真实文件。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app_setup  # noqa: E402


def _mk_app(apps: Path, name: str, with_notes=True, with_exposure=True):
    d = apps / name; d.mkdir(parents=True)
    (d / "study.py").write_text("APP_MODULE='x'\n", encoding="utf-8")
    (d / "run.py").write_text("DATA_DIR='x'\n", encoding="utf-8")
    (d / "classification.json").write_text("{}", encoding="utf-8")
    if with_notes:
        (d / "notes.md").write_text("# notes\n", encoding="utf-8")
    if with_exposure:
        (d / "exposure.jsonl").write_text('{"ts":"t"}\n', encoding="utf-8")
    return d


def test_notes_and_exposure_default_to_keep(tmp_path):
    """默认保留:它们记的是'对这批数据做过什么',意义不随 app 消失。"""
    apps = tmp_path / "apps"; _mk_app(apps, "demo")
    plan = app_setup.plan_delete("demo", apps, tmp_path, delete_notes=False, delete_exposure=False)
    must = {Path(x["path"]).name for x in plan["must"]}
    keep = {Path(x["path"]).name for x in plan["keep"]}
    assert must == {"study.py", "run.py", "classification.json"}
    assert {"notes.md", "exposure.jsonl"} <= keep


def test_opt_in_moves_notes_to_confirm(tmp_path):
    apps = tmp_path / "apps"; _mk_app(apps, "demo")
    plan = app_setup.plan_delete("demo", apps, tmp_path, delete_notes=True, delete_exposure=True)
    confirm = {Path(x["path"]).name for x in plan["confirm"]}
    assert {"notes.md", "exposure.jsonl"} <= confirm


def test_substring_neighbour_app_is_never_touched(tmp_path):
    """bb_v1 与 bb_v10 / bb_v1_test 必须互不干扰——只走精确路径,绝不 glob。

    两侧都要造邻居:app 目录侧(study.py 等)与重产物侧(outputs/tune_gates/<app>/)——
    若把 out_root 的精确拼接换成 f"{app}*" 式 glob,bb_v10 / bb_v1_test 的重产物会被
    误当成 bb_v1 的重产物枚举进来,这条测试才会转红。
    """
    apps = tmp_path / "apps"
    _mk_app(apps, "bb_v1"); _mk_app(apps, "bb_v10"); _mk_app(apps, "bb_v1_test")
    for neighbour in ("bb_v10", "bb_v1_test"):
        (tmp_path / "outputs" / "tune_gates" / neighbour / "main" / "longtable").mkdir(parents=True)
    plan = app_setup.plan_delete("bb_v1", apps, tmp_path, delete_notes=True, delete_exposure=True)
    touched = [x["path"] for grp in plan.values() for x in grp]
    assert not any("bb_v10" in p or "bb_v1_test" in p for p in touched)


def test_unregenerable_longtable_is_blocked_not_deletable(tmp_path):
    """不可再生的重产物进 blocked 组,不进可删组。

    删除单元是整个 run 目录(sub),不是 sub/longtable——见 plan_delete 里的说明:同级的
    resume 状态文件(random_baseline.csv / filtered_symbols.csv)与 longtable/ 是同一份
    扫描产物不可分割,只删 longtable/ 会让"删了要重跑"这句话落空。可再生性判定仍然对
    含 run_meta.json 的那一层(这里是 sub/longtable)做,但 plan 里报告的路径是 sub。
    """
    apps = tmp_path / "apps"; _mk_app(apps, "demo")
    sub = tmp_path / "outputs" / "tune_gates" / "demo" / "main"
    lt = sub / "longtable"
    lt.mkdir(parents=True)
    (lt / "run_meta.json").write_text(json.dumps({"app": "demo", "study_fingerprint": "zzz"}), encoding="utf-8")
    plan = app_setup.plan_delete("demo", apps, tmp_path, delete_notes=False, delete_exposure=False)
    # 精确路径比对,不用子串——pytest 的 tmp_path 本身按测试函数名截断生成,子串判断会被
    # "test_unregenerable_longtable_..." 这个目录名误伤(它本身就含 "longtable" 四个字)
    assert str(sub) in {x["path"] for x in plan["blocked"]}
    assert str(sub) not in {x["path"] for x in plan["confirm"] + plan["must"]}


# ---- I-4:main() 真正执行删除的那段代码(dirty 闸 + CONFIRM 分支 + 真删)——评审前零覆盖 ----
#
# 三个 bug(b5f655b dirty 闸 fail-open / 2ea24c0 git -C 锚点 / 42ad014 showUntrackedFiles
# fail-open)都在这段代码里,且每一轮都是评审读代码读出来的、没有留下回归钉。下面的测试
# 全部在 tmp_path 里 git init 出一个假仓库,红线:绝不删除 tmp_path 之外的任何东西。


def _git_repo(root: Path) -> None:
    """在 root 建一个可 commit 的干净 git 仓库(非交互式 identity,不依赖机器全局配置)。"""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)


def _git_commit_all(root: Path, msg: str = "init") -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=root, check=True)


def test_worktree_dirty_clean_repo_is_empty(tmp_path):
    """干净仓库(全部已提交)→ 空字符串,即 CONFIRM=True 路径能走过这道闸。"""
    _git_repo(tmp_path)
    app_dir = tmp_path / "apps" / "demo"; app_dir.mkdir(parents=True)
    (app_dir / "study.py").write_text("x", encoding="utf-8")
    _git_commit_all(tmp_path)
    assert app_setup._worktree_dirty(app_dir) == ""


def test_worktree_dirty_detects_uncommitted_change(tmp_path):
    """有未提交改动(含未跟踪文件)→ 非空字符串。"""
    _git_repo(tmp_path)
    app_dir = tmp_path / "apps" / "demo"; app_dir.mkdir(parents=True)
    (app_dir / "study.py").write_text("x", encoding="utf-8")
    _git_commit_all(tmp_path)
    (app_dir / "new_untracked.txt").write_text("y", encoding="utf-8")
    dirty = app_setup._worktree_dirty(app_dir)
    assert dirty and "new_untracked.txt" in dirty


def test_worktree_dirty_detects_untracked_with_show_untracked_files_no(tmp_path):
    """status.showUntrackedFiles=no 被设上时仍能识别出未跟踪文件——这条钉的是 -uall。

    不加 -uall 时,这个 git config 会让 status --porcelain 对着一整目录的未跟踪内容
    空输出+rc=0,与"干净"分不出来(42ad014 修的就是这个 fail-open)。
    """
    _git_repo(tmp_path)
    subprocess.run(["git", "config", "status.showUntrackedFiles", "no"], cwd=tmp_path, check=True)
    app_dir = tmp_path / "apps" / "demo"; app_dir.mkdir(parents=True)
    (app_dir / "study.py").write_text("x", encoding="utf-8")
    _git_commit_all(tmp_path)
    (app_dir / "new_untracked.txt").write_text("y", encoding="utf-8")
    dirty = app_setup._worktree_dirty(app_dir)
    assert dirty and "new_untracked.txt" in dirty


def test_worktree_dirty_git_failure_raises_systemexit(tmp_path):
    """app_dir 不在任何 git 仓库下(git 查不出来)→ SystemExit,不能被当成"干净"放行。"""
    app_dir = tmp_path / "not_a_repo" / "demo"; app_dir.mkdir(parents=True)
    with pytest.raises(SystemExit, match="git status 失败"):
        app_setup._worktree_dirty(app_dir)


def test_execute_delete_clean_confirm_true_deletes(tmp_path):
    """干净 + CONFIRM=True → 真删,plan 里的文件从磁盘消失,并顺手清空 app_dir。"""
    _git_repo(tmp_path)
    app_dir = tmp_path / "apps" / "demo"; app_dir.mkdir(parents=True)
    target = app_dir / "study.py"; target.write_text("x", encoding="utf-8")
    _git_commit_all(tmp_path)
    plan = {"must": [{"path": str(target), "why": "x"}], "confirm": [], "keep": [], "blocked": []}
    app_setup._execute_delete(plan, app_dir, confirm=True)
    assert not target.exists()
    assert not app_dir.exists()          # 删完 must 组后 app_dir 已空,顺手 rmdir


def test_execute_delete_dirty_confirm_true_refuses_and_keeps_files(tmp_path):
    """有未提交改动 + CONFIRM=True → SystemExit,文件原样保留(拒绝删除优先于真删)。"""
    _git_repo(tmp_path)
    app_dir = tmp_path / "apps" / "demo"; app_dir.mkdir(parents=True)
    target = app_dir / "study.py"; target.write_text("x", encoding="utf-8")
    _git_commit_all(tmp_path)
    (app_dir / "dirty.txt").write_text("y", encoding="utf-8")  # 未提交
    plan = {"must": [{"path": str(target), "why": "x"}], "confirm": [], "keep": [], "blocked": []}
    with pytest.raises(SystemExit, match="拒绝删除"):
        app_setup._execute_delete(plan, app_dir, confirm=True)
    assert target.exists()


def test_execute_delete_dry_run_never_touches_disk(tmp_path):
    """CONFIRM=False → dry-run,即使有未提交改动也不删任何文件、不抛异常。"""
    _git_repo(tmp_path)
    app_dir = tmp_path / "apps" / "demo"; app_dir.mkdir(parents=True)
    target = app_dir / "study.py"; target.write_text("x", encoding="utf-8")
    _git_commit_all(tmp_path)
    (app_dir / "dirty.txt").write_text("y", encoding="utf-8")
    plan = {"must": [{"path": str(target), "why": "x"}], "confirm": [], "keep": [], "blocked": []}
    app_setup._execute_delete(plan, app_dir, confirm=False)  # 不应抛异常
    assert target.exists()
