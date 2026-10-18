"""状态根:在 worktree 里指向主目录;没有标记文件就抛 StateRootMissing(消息含「可能切到了别的分支」);
init 不接受默认位置;水位(git 公共目录里)记下见过的行和文件,切到旧分支、合了代码没合账本时停下,
按行合并后行序变了不误报,显式重置要写原因并留记录;记账类路径一律不经 root_dir 拼(只有一个家)。"""
import ast
import json
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


@pytest.fixture
def no_snapshot_lock(monkeypatch):
    """主目录状态根的测试只看标记与水位:副本登记的核对另见 test_snaplock。"""
    from chart_workflow import snaplock
    monkeypatch.setattr(snaplock, "verify", lambda ddir, root=None, file=None: None)


def test_worktree_resolves_to_main_and_marker_required(tmp_path, monkeypatch, no_snapshot_lock):
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

    # 默认位置不能 init(主目录与 worktree 的都不行):那里的标记只能随记账文件经 git 到达
    for where in (main, wt):
        with pytest.raises(ValueError, match="默认状态根位置"):
            state.init(where / "outputs" / "chart_workflow")
    assert not (main / "outputs").exists() and not (wt / "outputs").exists()
    with pytest.raises(SystemExit):
        state.main(["init", str(main / "outputs" / "chart_workflow")])
    assert "默认位置不能用 init 新建" in state.missing_message(main / "outputs" / "chart_workflow")

    (main / "outputs" / "chart_workflow").mkdir(parents=True)
    (main / "outputs" / "chart_workflow" / state.MARKER).write_text(state.MARKER_TEXT)
    assert state.state_root(start=wt) == main.resolve() / "outputs" / "chart_workflow"
    assert state.state_root(start=main) == state.state_root(start=wt)
    # 水位在 git 公共目录里,不在状态根里(不随分支走)
    assert (main / ".git" / "chart_workflow" / "watermark.json").is_file()
    assert not (main / "outputs" / "chart_workflow" / ".watermark.json").exists()


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


def _commit_all(repo, msg):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def test_watermark_stops_old_branch_and_code_only_merge(tmp_path, monkeypatch, no_snapshot_lock):
    """主目录切到账本较旧的分支、或切到只合了代码(有标记、没账本)的分支:停下,不接着写。"""
    monkeypatch.delenv(state.ENV_VAR, raising=False)
    main = tmp_path / "main"
    root = main / "outputs" / "chart_workflow"
    root.mkdir(parents=True)
    _git(main, "init", "-q", "-b", "master")
    (root / state.MARKER).write_text(state.MARKER_TEXT)
    _commit_all(main, "只有代码与标记")
    _git(main, "branch", "code-only")
    (root / "ledger.jsonl").write_text('{"a": 1}\n')
    _commit_all(main, "账本 1 行")
    _git(main, "branch", "old")
    with (root / "ledger.jsonl").open("a") as f:
        f.write('{"a": 2}\n')
    (root / "annotations").mkdir()
    (root / "annotations" / "b1.json").write_text("{}")
    _commit_all(main, "账本 2 行、一个批次")
    assert state.state_root(start=main) == root.resolve()      # 记下水位
    for branch in ("old", "code-only"):
        _git(main, "checkout", "-q", branch)
        with pytest.raises(state.StateRootRegressed) as ei:
            state.state_root(start=main)
        assert state.REGRESSED_TEXT in str(ei.value) and "reset-watermark" in str(ei.value)
        assert isinstance(ei.value, state.StateRootMissing)      # 所有「拿不到状态根就停」的地方照样停
    _git(main, "checkout", "-q", "master")
    assert state.state_root(start=main) == root.resolve()      # 切回来照常


def test_watermark_lines_not_prefix_and_reset(state_dir):
    root = state_dir
    led = root / "ledger.jsonl"
    led.write_text('{"r": 1}\n{"r": 2}\n')
    (root / "oplog").mkdir()
    (root / "oplog" / "2026-10.jsonl").write_text('{"o": 1}\n')
    state.state_root()
    # 按行合并:别的机器的行插在中间、行序变了 → 见过的行都还在,不误报
    led.write_text('{"r": 2}\n{"x": "别的机器"}\n{"r": 1}\n')
    state.state_root()
    # 正在追加、末尾半行(还没写换行)不进水位,写完也不误报
    led.write_text(led.read_text() + '{"r": 3')
    state.state_root()
    led.write_text(led.read_text() + '}\n')
    state.state_root()
    # 少了一行 → 停下
    led.write_text('{"r": 1}\n{"r": 2}\n{"r": 3}\n')
    with pytest.raises(state.StateRootRegressed, match="ledger.jsonl 少了 1 行"):
        state.state_root()
    # 写入方也停:不会往少了行的账本里接着写
    from chart_workflow import views
    with pytest.raises(state.StateRootRegressed):
        views.record(surface="manual", event="show_chart", outcome_visible=True,
                     charts=[{"symbol": "A", "start": "2025-02-03", "end": "2025-03-03"}],
                     note="测试", ts="2026-10-17T10:00:00", backfill=True)
    assert not (root / "views.jsonl").exists()
    # 显式重置:必须写原因,留记录;之后照常
    with pytest.raises(ValueError, match="原因"):
        state.reset_watermark(root, "  ")
    rec = state.reset_watermark(root, "测试:有意改写账本")
    assert rec["missing"] == ["ledger.jsonl 少了 1 行(上次见过 4 行,现在 3 行)"]
    assert state.state_root() == root
    logged = [json.loads(x) for x in (root / state.RESETS_FILE).read_text().splitlines()]
    assert logged[-1]["reason"] == "测试:有意改写账本"
    # 重置记录本身也受水位保护;文件目录里少了文件同样停下
    (root / "annotations").mkdir()
    (root / "annotations" / "b1.json").write_text("{}")
    state.state_root()
    (root / "annotations" / "b1.json").unlink()
    with pytest.raises(state.StateRootRegressed, match="annotations/ 少了 1 个文件"):
        state.state_root()


def test_reset_watermark_cli(state_dir, capsys):
    (state_dir / "ledger.jsonl").write_text('{"r": 1}\n')
    state.state_root()
    (state_dir / "ledger.jsonl").write_text("")
    with pytest.raises(SystemExit):
        state.main(["show"])
    with pytest.raises(SystemExit):
        state.main(["reset-watermark"])                       # 不写原因不行
    state.main(["reset-watermark", "--reason", "迁移旧账"])
    out = capsys.readouterr().out
    assert "已重置水位" in out and "ledger.jsonl 少了 1 行" in out
    state.main(["show"])
    assert "水位核对:通过" in capsys.readouterr().out


def test_writers_advance_watermark(state_dir):
    """写入方写完就把新内容记进水位:写完立刻切到旧分支(没再调 state_root)也能发现。"""
    from chart_workflow import views
    views.record(surface="manual", event="show_chart", outcome_visible=True,
                 charts=[{"symbol": "A", "start": "2025-02-03", "end": "2025-03-03"}],
                 note="测试", ts="2026-10-17T10:00:00", backfill=True)
    wm = json.loads((state_dir / ".watermark.json").read_text())
    assert wm["lines"]["views.jsonl"]["n"] == 1


def test_append_only_files_merge_by_line_and_tmp_ignored():
    """只追加的记账文件按行合并(两台机器各自追加后合并不冲突);记账目录里的临时文件不进 git。"""
    paths = ["outputs/chart_workflow/ledger.jsonl", "outputs/chart_workflow/views.jsonl",
             "outputs/chart_workflow/oplog/2026-10.jsonl",
             "outputs/chart_workflow/watermark_resets.jsonl"]
    out = subprocess.run(["git", "check-attr", "merge", "--", *paths], cwd=REPO_ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert out.count(": merge: union") == len(paths), out
    for f, ignored in (("outputs/chart_workflow/ledger.jsonl.123.tmp", True),
                       ("outputs/chart_workflow/annotations/b.json.tmp", True),
                       ("outputs/chart_workflow/.watermark.json", True),
                       ("outputs/chart_workflow/annotations/b.json", False),
                       ("outputs/chart_workflow/config_archive/x.json", False),
                       ("outputs/chart_workflow/elements/E001.json", False),
                       ("outputs/chart_workflow/elements/E001.json.tmp", True),
                       ("outputs/chart_workflow/watermark_resets.jsonl", False)):
        r = subprocess.run(["git", "check-ignore", "-q", "--no-index", f], cwd=REPO_ROOT)
        assert (r.returncode == 0) == ignored, f


def test_tracked_marker_matches_code():
    """受 git 跟踪的标记文件与代码里的说明一致(列出了全部进 git 的记账类文件,含要素库)。"""
    assert (REPO_ROOT / "outputs" / "chart_workflow" / state.MARKER).read_text() == state.MARKER_TEXT
    for _, rel, _ in state._KINDS:
        assert f"`{rel}" in state.MARKER_TEXT, rel


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
LEDGER_NAMES = ("annotations", "ledger.jsonl", "views.jsonl", "viewed_lists", "elements", "shapes", "oplog",
                "facts", "rule_archive", "config_archive", "watermark_resets", "snapshot_lock")


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


# ── 水位:不存每行指纹进水位文件、只读核对不写、旧格式照常核对 ─────────────────────

def test_watermark_compact_and_seen_lines_kept(state_dir):
    """水位文件里每份只追加的文件只记字节数、开头那段的指纹、行数;见过的行指纹在旁边的见过记录里,
    正常追加只往见过记录追加新行。"""
    from chart_workflow import views
    for k in range(3):
        views.record(surface="manual", event="show_chart", outcome_visible=True,
                     charts=[{"symbol": "A", "start": "2025-02-03", "end": "2025-03-03"}],
                     note=f"测试 {k}", ts=f"2026-10-17T10:00:0{k}", backfill=True)
    raw = (state_dir / ".watermark.json").read_text()
    wm = json.loads(raw)
    e = wm["lines"]["views.jsonl"]
    assert set(e) == {"bytes", "sha", "n"} and e["n"] == 3
    assert e["bytes"] == (state_dir / "views.jsonl").stat().st_size
    seen = (state_dir / ".watermark.seen" / "views.jsonl.txt").read_text().split()
    assert len(seen) == 3 and not any(h in raw for h in seen)          # 行指纹不在水位文件里
    (state_dir / "views.jsonl").write_text("\n".join(
        (state_dir / "views.jsonl").read_text().splitlines()[1:]) + "\n")   # 删掉第一行
    with pytest.raises(state.StateRootRegressed, match="views.jsonl 少了 1 行"):
        state.state_root()


def test_check_root_writes_nothing(state_dir):
    (state_dir / "ledger.jsonl").write_text('{"r": 1}\n')
    assert not (state_dir / ".watermark.json").exists()
    assert state.check_root() == state_dir
    assert not (state_dir / ".watermark.json").exists() and not (state_dir / ".watermark.seen").exists()
    state.state_root()
    before = (state_dir / ".watermark.json").read_text()
    with (state_dir / "ledger.jsonl").open("a") as f:
        f.write('{"r": 2}\n')
    state.check_root()
    assert (state_dir / ".watermark.json").read_text() == before
    (state_dir / "ledger.jsonl").write_text('{"r": 2}\n')                # 少了见过的一行:只读核对也停
    with pytest.raises(state.StateRootRegressed):
        state.check_root()


def test_old_format_watermark_still_checked(state_dir):
    """旧格式水位(整份行指纹表在水位文件里):照样核对,少了行就停;核对通过就改写成新格式。"""
    led = state_dir / "ledger.jsonl"
    led.write_text('{"r": 1}\n{"r": 2}\n')
    old = {"schema": "chart_workflow.watermark/1", "state_root": str(state_dir),
           "lines": {"ledger.jsonl": state._line_hashes(led)}, "files": {}}
    (state_dir / ".watermark.json").write_text(json.dumps(old))
    led.write_text('{"r": 2}\n')
    with pytest.raises(state.StateRootRegressed, match="ledger.jsonl 少了 1 行"):
        state.state_root()
    led.write_text('{"r": 2}\n{"r": 1}\n{"r": 3}\n')
    state.state_root()
    wm = json.loads((state_dir / ".watermark.json").read_text())
    assert wm["schema"] == state.WATERMARK_SCHEMA and wm["lines"]["ledger.jsonl"]["n"] == 3


def test_seen_record_lost_stops(state_dir):
    led = state_dir / "ledger.jsonl"
    led.write_text('{"r": 1}\n')
    state.state_root()
    (state_dir / ".watermark.seen" / "ledger.jsonl.txt").unlink()
    led.write_text('{"x": 1}\n{"r": 1}\n')                               # 开头变了,要用见过记录
    with pytest.raises(state.StateRootRegressed, match="见过记录"):
        state.state_root()


# ── 别的分支上有更新的账(真实的临时 git 仓库)──────────────────────────────

def _repo_with_state(tmp_path, monkeypatch):
    monkeypatch.delenv(state.ENV_VAR, raising=False)
    main = tmp_path / "main"
    root = main / "outputs" / "chart_workflow"
    root.mkdir(parents=True)
    _git(main, "init", "-q", "-b", "master")
    (root / state.MARKER).write_text(state.MARKER_TEXT)
    (root / "ledger.jsonl").write_text('{"r": 1}\n')
    (main / "code.py").write_text("x = 1\n")
    _commit_all(main, "代码与账本")
    return main, root


def test_other_branch_with_newer_ledger_stops(tmp_path, monkeypatch, no_snapshot_lock):
    main, root = _repo_with_state(tmp_path, monkeypatch)
    assert state.state_root(start=main) == root.resolve()
    _git(main, "checkout", "-q", "-b", "pc")                      # 另一台机器的分支记了账
    with (root / "ledger.jsonl").open("a") as f:
        f.write('{"r": "pc"}\n')
    _commit_all(main, "pc 记账")
    _git(main, "checkout", "-q", "master")
    with pytest.raises(state.StateRootDiverged) as ei:
        state.state_root(start=main)
    assert state.DIVERGED_TEXT in str(ei.value) and "pc(1 个提交;ledger.jsonl 有当前分支没有的行)" in str(ei.value)
    assert isinstance(ei.value, state.StateRootMissing)
    with pytest.raises(state.StateRootDiverged):
        state.check_root(start=main)
    _git(main, "merge", "-q", "--no-edit", "pc")                   # 合进来就照常
    assert state.state_root(start=main) == root.resolve()


def test_remote_tracking_branch_counts_and_ahead_is_fine(tmp_path, monkeypatch, no_snapshot_lock):
    main, root = _repo_with_state(tmp_path, monkeypatch)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=main, capture_output=True, text=True).stdout.strip()
    with (root / "ledger.jsonl").open("a") as f:                  # 本分支领先:正常
        f.write('{"r": 2}\n')
    _commit_all(main, "本机记账")
    _git(main, "update-ref", "refs/remotes/origin/master", base)    # 远端落后(是祖先):正常
    assert state.state_root(start=main) == root.resolve()
    _git(main, "checkout", "-q", "-b", "tmp", base)               # 造一个远端领先、和本地分叉的提交
    (root / "views.jsonl").write_text('{"v": 1}\n')
    _commit_all(main, "另一台机器看过")
    far = subprocess.run(["git", "rev-parse", "HEAD"], cwd=main, capture_output=True, text=True).stdout.strip()
    _git(main, "checkout", "-q", "master")
    _git(main, "branch", "-D", "tmp")
    _git(main, "update-ref", "refs/remotes/origin/master", far)
    with pytest.raises(state.StateRootDiverged, match="origin/master"):
        state.state_root(start=main)


def test_other_branch_touching_only_code_or_marker_is_fine(tmp_path, monkeypatch, no_snapshot_lock):
    main, root = _repo_with_state(tmp_path, monkeypatch)
    _git(main, "checkout", "-q", "-b", "feature")
    (main / "code.py").write_text("x = 2\n")
    (root / state.MARKER).write_text(state.MARKER_TEXT + "\n多一行说明\n")   # 只改了标记文件:算代码
    _commit_all(main, "改代码与标记说明")
    _git(main, "checkout", "-q", "master")
    assert state.state_root(start=main) == root.resolve()


def test_watermark_of_root_in_other_repo_stays_in_that_repo(tmp_path, monkeypatch, no_snapshot_lock):
    """别的仓库里的状态根:推进水位、重置水位都写进那个仓库自己的 .git,不写这份代码所在仓库的(主目录的 .git;
    夹具 no_repo_git_dir 拦着,真去找就报错)。"""
    main, root = _repo_with_state(tmp_path, monkeypatch)
    wm = main.resolve() / ".git" / "chart_workflow" / "watermark.json"
    state.advance(root)
    assert state.watermark_path(root) == wm and wm.is_file()
    state.reset_watermark(root, "测试:别的仓库里的状态根")
    assert json.loads(wm.read_text())["state_root"] == str(root)


def test_merged_into_other_branch_by_merge_commit_is_fine(tmp_path, monkeypatch, no_snapshot_lock):
    """用合并提交(非快进)把当前分支合进别的分支:那个分支上有改过记账目录的合并提交,但账当前分支全有;
    当前分支再记一次账(追加行、要素文件随操作日志改写)照样不拦。那个分支之后再记新账才拦。"""
    main, root = _repo_with_state(tmp_path, monkeypatch)
    for d in ("annotations", "elements", "oplog"):
        (root / d).mkdir()
    (root / "annotations" / "b1.json").write_text('{"batch_id": "b1"}\n')
    (root / "elements" / "E001.json").write_text('{"v": 1}\n')
    (root / "oplog" / "ops.jsonl").write_text('{"op": 1}\n')
    _commit_all(main, "标注与要素")
    _git(main, "checkout", "-q", "-b", "pc")
    (main / "code.py").write_text("x = 2\n")
    _commit_all(main, "pc 改代码")
    _git(main, "checkout", "-q", "master")
    with (root / "ledger.jsonl").open("a") as f:
        f.write('{"r": 2}\n')
    _commit_all(main, "本机记账")
    _git(main, "checkout", "-q", "pc")
    _git(main, "merge", "-q", "--no-ff", "--no-edit", "master")       # 合并提交:改过记账目录,不是 master 的祖先
    _git(main, "checkout", "-q", "master")
    assert state.state_root(start=main) == root.resolve()
    with (root / "ledger.jsonl").open("a") as f:                       # 当前分支再记一次账
        f.write('{"r": 3}\n')
    with (root / "oplog" / "ops.jsonl").open("a") as f:
        f.write('{"op": 2}\n')
    (root / "elements" / "E001.json").write_text('{"v": 2}\n')
    state.advance(root)
    assert state.state_root(start=main) == root.resolve()
    _commit_all(main, "本机再记账")
    foreign = subprocess.run(["git", "rev-list", "--count", "pc", "--not", "master", "--", "outputs"], cwd=main,
                             capture_output=True, text=True).stdout.strip()
    assert foreign == "1"                                              # 那个合并提交按提交算是「别的分支上的账」
    assert state.state_root(start=main) == root.resolve()              # 按内容比:当前分支全有,不拦
    _git(main, "checkout", "-q", "pc")                                 # 那个分支之后又记了新账
    (root / "annotations" / "b2.json").write_text('{"batch_id": "b2"}\n')
    with (root / "views.jsonl").open("a") as f:
        f.write('{"v": "pc"}\n')
    _commit_all(main, "pc 记账")
    _git(main, "checkout", "-q", "master")
    with pytest.raises(state.StateRootDiverged) as ei:
        state.state_root(start=main)
    msg = str(ei.value)
    assert "pc(2 个提交;" in msg and "annotations/b2.json 当前分支没有" in msg and "views.jsonl 当前分支没有" in msg


@pytest.mark.parametrize("change,needle", [
    (lambda r: (r / "annotations" / "b1.json").write_text('{"batch_id": "b1", "x": 1}\n'),
     "annotations/b1.json 和当前分支的不一样"),
    (lambda r: (r / "ledger.jsonl").write_text('{"r": "pc"}\n{"r": 1}\n'), "ledger.jsonl 有当前分支没有的行"),
    (lambda r: (r / "elements" / "E009.json").write_text("{}\n"), "elements/E009.json 当前分支没有"),
])
def test_other_branch_content_differs_stops(tmp_path, monkeypatch, no_snapshot_lock, change, needle):
    """那个分支上:写一次就不改的文件内容不同、只追加的文件不是当前这份的开头一段、多了一个要素文件 → 拦。"""
    main, root = _repo_with_state(tmp_path, monkeypatch)
    for d in ("annotations", "elements"):
        (root / d).mkdir()
    (root / "annotations" / "b1.json").write_text('{"batch_id": "b1"}\n')
    _commit_all(main, "标注")
    _git(main, "checkout", "-q", "-b", "pc")
    change(root)
    _commit_all(main, "pc 改账")
    _git(main, "checkout", "-q", "master")
    with pytest.raises(state.StateRootDiverged, match=needle):
        state.state_root(start=main)


@pytest.mark.parametrize("theirs", [
    lambda a, b, c: {"current": c, "history": [{"reason": "pc 换", "old": a, "new": c}]},   # 换副本记录分叉
    lambda a, b, c: {"current": c, "history": []},                                          # 直接登记了别的副本
])
def test_snapshot_lock_on_other_branch_compared_by_history(tmp_path, monkeypatch, no_snapshot_lock, theirs):
    """副本登记:那个分支上登记的是当前分支后来换掉的那一份 → 不拦;那个分支上换了当前分支没有的副本 → 拦。"""
    main, root = _repo_with_state(tmp_path, monkeypatch)
    lock = root / "snapshot_lock.json"
    a, b, c = ({"sha": x} for x in "abc")
    lock.write_text(json.dumps({"current": a, "history": []}))
    _commit_all(main, "登记副本")
    _git(main, "checkout", "-q", "-b", "pc")
    (main / "code.py").write_text("x = 2\n")
    _commit_all(main, "pc 改代码")
    _git(main, "checkout", "-q", "master")
    with (root / "ledger.jsonl").open("a") as f:
        f.write('{"r": 2}\n')
    _commit_all(main, "本机记账")
    _git(main, "checkout", "-q", "pc")
    _git(main, "merge", "-q", "--no-ff", "--no-edit", "master")       # pc 上登记的是 a
    _git(main, "checkout", "-q", "master")
    lock.write_text(json.dumps({"current": b, "history": [{"reason": "换", "old": a, "new": b}]}))
    _commit_all(main, "本机换副本")
    foreign = subprocess.run(["git", "rev-list", "--count", "pc", "--not", "master", "--", "outputs"], cwd=main,
                             capture_output=True, text=True).stdout.strip()
    assert foreign == "1"
    assert state.state_root(start=main) == root.resolve()
    _git(main, "checkout", "-q", "pc")
    lock.write_text(json.dumps(theirs(a, b, c)))
    _commit_all(main, "pc 换了别的副本")
    _git(main, "checkout", "-q", "master")
    with pytest.raises(state.StateRootDiverged, match="pc.*snapshot_lock.json 登记的副本"):
        state.state_root(start=main)
