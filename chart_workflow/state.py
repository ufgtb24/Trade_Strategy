"""状态根:看图工作流记账类文件唯一的家。

记账类文件(原始标注 annotations/、看过记录 views.jsonl 与 viewed_lists/、事实表快照 facts/、
形态卡 shapes/、操作日志 oplog/、账本 ledger.jsonl、规则存档 rule_archive/)只存一份,放在
**主目录**(git 仓库的 main worktree)的 outputs/chart_workflow/ 下,受 git 跟踪;在任何
worktree 里运行工具,都经 state_root() 自动定位到主目录这一份。工具只写文件、不自己 commit。

清单 lists/、缓存 cache/、数据错误登记 data_errors.json 是可重算的产物,不在这里,
仍随各自 worktree 的 config.root(见 config.root_dir)。

定位:
  环境变量 CHART_WORKFLOW_STATE_ROOT 有值 → 用它(测试、端到端、冒烟用临时目录);
  否则 → `git rev-parse --git-common-dir` 的上一级(主目录)/ outputs / chart_workflow。

红线:状态根里必须有受 git 跟踪的标记文件 STATE_ROOT.md,找不到就抛 StateRootMissing 停下,
绝不悄悄新建空账——主目录切到没有这些文件的分支时,账本和看过记录会被拆成两份。
新开一本账只能显式运行 init。

    uv run python -m chart_workflow.state show
    uv run python -m chart_workflow.state init <目录>
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from chart_workflow.config import REPO_ROOT

MARKER = "STATE_ROOT.md"
ENV_VAR = "CHART_WORKFLOW_STATE_ROOT"

MARKER_TEXT = """# 看图工作流的记账类文件

这个目录是看图工作流记账类文件唯一的家,受 git 跟踪。工具(`chart_workflow` 的命令行与
path2_web 的看图工作流后端)自动定位主目录(git 仓库的 main worktree)里的这个目录写入,
在任何 worktree 里运行都写到这里。工具只写文件、不自己提交,提交由用户照常做。

不要删除本文件,也不要在 worktree 里另建一个:找不到本文件时工具会报错停下,
不会悄悄新开一本空账(主目录切到没有这些文件的分支时就会出现这种情况,切回来再用)。

进 git 的(记账类,丢了无法重算):

- `annotations/`:原始标注批次
- `views.jsonl`、`viewed_lists/`:看过记录与看过的清单快照
- `facts/`:给用户看过的事实表快照
- `shapes/`:形态卡(由操作日志重算)
- `oplog/`:操作日志(形态卡的唯一真相)
- `ledger.jsonl`:账本
- `rule_archive/`:对照页用过的规则文件存档

不进 git 的(可重算的产物,随各自 worktree 的 `outputs/chart_workflow/`):清单 `lists/`、
缓存 `cache/`、数据错误登记 `data_errors.json`。
"""

# show 统计的各类文件:(显示名, 相对路径, 统计方式)
_KINDS = (
    ("原始标注批次", "annotations", "glob_json"),
    ("看过记录", "views.jsonl", "lines"),
    ("看过的清单快照", "viewed_lists", "glob_json"),
    ("事实表快照", "facts", "glob_json"),
    ("形态卡", "shapes", "glob_json"),
    ("操作日志条目", "oplog", "jsonl_lines"),
    ("账本行", "ledger.jsonl", "lines"),
    ("规则存档", "rule_archive", "files"),
)


class StateRootMissing(RuntimeError):
    """拿不到状态根(标记文件不在、git 不可用等)。消息是给用户看的中文。"""


@lru_cache(maxsize=16)
def _git_common_dir(start: str) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=start, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        raise StateRootMissing(f"找不到主目录:git 不可用({type(e).__name__}: {e})") from e
    if r.returncode != 0:
        raise StateRootMissing(f"找不到主目录:{start} 不在 git 仓库里({r.stderr.strip()})")
    return r.stdout.strip()


def main_worktree(start: Path = REPO_ROOT) -> Path:
    """主目录:在 start 下执行 `git rev-parse --path-format=absolute --git-common-dir`,取上一级。
    在主目录和任何 worktree 里都返回主目录。git 不可用或不在仓库里 → StateRootMissing。"""
    return Path(_git_common_dir(str(Path(start).resolve()))).parent


def locate(start: Path = REPO_ROOT) -> Path:
    """状态根应在的位置(不检查标记)。环境变量优先。"""
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).resolve()
    return main_worktree(start) / "outputs" / "chart_workflow"


def missing_message(path: Path) -> str:
    return (f"状态根 {path} 下没有标记文件 {MARKER}:主目录当前分支没有记账文件,"
            f"可能切到了别的分支。切回有记账文件的分支再用;确实要在别处新开一本账,"
            f"运行 python -m chart_workflow.state init <目录>")


def state_root(start: Path = REPO_ROOT) -> Path:
    """记账类文件的唯一的家。目录里没有标记文件 → StateRootMissing(绝不新建)。"""
    path = locate(start)
    if not (path / MARKER).is_file():
        raise StateRootMissing(missing_message(path))
    return path


def init(path: Path) -> Path:
    """显式新开一本账:建目录并写标记文件(已有标记就不动)。只有这里会建标记。"""
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    marker = path / MARKER
    if not marker.exists():
        marker.write_text(MARKER_TEXT)
    return path


def _count(p: Path, how: str) -> int:
    if not p.exists():
        return 0
    if how == "lines":
        return sum(1 for line in p.read_text().splitlines() if line.strip())
    if how == "glob_json":
        return sum(1 for _ in p.glob("*.json"))
    if how == "jsonl_lines":
        return sum(_count(f, "lines") for f in p.glob("*.jsonl"))
    return sum(1 for f in p.iterdir() if f.is_file())


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="状态根(记账类文件唯一的家)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="打印状态根路径、标记在不在、各类文件条数")
    a = sub.add_parser("init", help="在指定目录新开一本账(写标记文件)")
    a.add_argument("path")
    args = ap.parse_args(argv)
    if args.cmd == "init":
        p = init(Path(args.path))
        print(f"已建状态根 {p}(标记 {MARKER})")
        return
    try:
        path = locate()
    except StateRootMissing as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)
    src = f"环境变量 {ENV_VAR}" if os.environ.get(ENV_VAR) else "主目录"
    has = (path / MARKER).is_file()
    print(f"状态根:{path}(来自{src})")
    print(f"标记文件 {MARKER}:{'在' if has else '不在'}")
    if not has:
        print(missing_message(path), file=sys.stderr)
        sys.exit(2)
    for name, rel, how in _KINDS:
        print(f"  {name:<10} {_count(path / rel, how):>6}  ({rel})")


if __name__ == "__main__":
    main()
