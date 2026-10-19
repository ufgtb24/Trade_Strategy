"""调试账:调试模式(mode.py)下记账类文件的家——新建、清空重来、查看。

    uv run python -m chart_workflow.debugroot show     # 在哪、各类文件多少条、副本登记
    uv run python -m chart_workflow.debugroot init     # 新建(已经是调试账就只补登记);启动脚本会自动做
    uv run python -m chart_workflow.debugroot clear    # 清空重来

这几条命令只管调试账,不用设 CHART_WORKFLOW_MODE。调试账的位置:环境变量 CHART_WORKFLOW_DEBUG_STATE_ROOT
有值就是它(测试、冒烟用临时目录),否则是主目录的 outputs/chart_workflow_debug/(见 state.debug_locate)。
里面的格式和正式账一样(标注 annotations/、看过记录 views.jsonl 与 viewed_lists/、事实表快照 facts/、要素
elements/、形态卡 shapes/、操作日志 oplog/、账本 ledger.jsonl、规则存档、配置存档、副本登记 snapshot_lock.json),
另有只在调试账里才有的 card_review/(卡成立日清单的标记、归类与小结,见 chart_workflow/cardhits.py),
标记文件是 DEBUG_LEDGER.md;在主目录里运行时,调试模式的清单 lists/、缓存 cache/、数据错误登记
data_errors.json 也在这里(调试模式的产物目录是 outputs/chart_workflow_debug,见 mode.debug_variant)。

新建(init):建目录、写标记、登记本机训练数据副本。调试账和正式账用同一份副本(datasets/pkls_until_20251231/):
正式账登记了副本而本机副本和它不是同一份 → 拒绝。目录里已有别的东西(不是调试账)也拒绝,改用 clear。

清空(clear):删掉调试账里除缓存 cache/ 以外的全部东西(记账文件、清单、数据错误登记;缓存是按配置和数据
算的,留着省得重算面板、重下证券名录和比对日线),再像 init 一样重写标记、重新登记副本。
只删调试账,指向别处就拒绝(clear 与 init 共用 _check_target):
  - 调试账的位置本身(环境变量给的,或默认位置)不得是符号链接——按解析之前的路径判断;是链接就拒绝,
    否则清空会删掉链接指向的那个目录里的东西;
  - 不得是这份代码所在的仓库本身或它的上级目录;
  - 不得碰到正式账(state.formal_conflict):和环境变量指的正式账、主目录默认的正式账任何一份是同一个目录或
    互相包含,或者往上任何一层里有正式账的标记 STATE_ROOT.md;
  - 里面不得有受 git 跟踪的文件(调试账不进 git,有就说明指错了);
  - 目录里要么有调试账的标记,要么是空的(或还不存在),要么就是调试账的默认位置(主目录的
    outputs/chart_workflow_debug,那里以前可能被人用正式格式 init 过)。别的目录一概不删。
清空只删认识的条目(KNOWN:记账类文件与目录(含只有调试账才有的 card_review/)、清单、数据错误登记、标记、
旧的正式格式标记与临时水位、这些名字后面跟着 .tmp 的临时文件);顶层有任何不认识的东西就停下、列出来,一样都不删。
删的时候不跟随符号链接(链接只删链接本身)。其他 worktree 里生成的调试清单不在这里,不受影响。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from chart_workflow import mode, snaplock, state
from chart_workflow.config import REPO_ROOT

KEEP = ("cache",)            # 清空时保留的子目录(可重算、重算费时或要联网)
# 只有调试账才有的记账类条目:(显示名, 相对路径, 统计方式),统计方式同 state._KINDS
DEBUG_ONLY = (("卡成立日的标记与归类", "card_review", "files_deep"),)
# 清空时认识的顶层条目:记账类文件与目录(state._KINDS 与只有调试账才有的 DEBUG_ONLY)、标记、调试模式的清单与数据错误登记、保留的缓存,
# 以及调试账默认位置上可能留着的旧的正式格式标记与临时水位
KNOWN = frozenset({rel for _, rel, _ in state._KINDS + DEBUG_ONLY}
                  | {state.DEBUG_MARKER, "lists", "data_errors.json", *KEEP}
                  | {state.MARKER, ".watermark.json", ".watermark.seen"})

MARKER_TEXT = f"""# 看图工作流的调试账

调试模式(环境变量 {mode.ENV_VAR}={mode.DEBUG};网页用 `uv run python scripts/path2/run_path2_web_debug.py`
启动)的记账类文件都写在这里:原始标注、看过记录、事实表快照、要素、形态卡、操作日志、账本……格式和正式账一样。

调试段 {mode.DEBUG_START}..{mode.DEBUG_END} 只用来调试看图工作流:这里的东西不进正式账、不算尝试,
也不进 git。调试模式下读任何行情都截在 {mode.DEBUG_END}。

卡成立日清单的「是 / 不是」标记、归类与小结在 card_review/(只有调试账才有,见 chart_workflow/cardhits.py)。

清空重来:`uv run python -m chart_workflow.debugroot clear`(只删这本调试账,保留缓存 cache/)。

不要在这里放正式账的标记 STATE_ROOT.md,也不要把这个目录纳入 git。
"""


class DebugRootRefused(ValueError):
    """目标不是调试账、或可能删到调试账以外的东西,拒绝新建 / 清空。"""


def location() -> Path:
    """调试账的位置,不解析符号链接(_check_target 先看它本身是不是链接)。"""
    return state.debug_location_raw()


def _known(name: str) -> bool:
    return name in KNOWN or (name.endswith(".tmp") and any(name.startswith(k + ".") for k in KNOWN))


def _tracked_files(path: Path) -> list[str]:
    """path 下受 git 跟踪的文件(path 不在 git 仓库里 → 空)。"""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.is_file():
        probe = probe.parent
    try:
        r = subprocess.run(["git", "ls-files", "-z", "--", str(path)], cwd=probe,
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    return [x for x in r.stdout.split("\0") if x] if r.returncode == 0 else []


def _check_target(raw: Path) -> Path:
    """新建 / 清空之前的拦截(见模块说明);raw 是解析之前的位置。通过 → 解析后的路径,不通过 → DebugRootRefused。"""
    raw = Path(raw)
    if raw.is_symlink():
        raise DebugRootRefused(f"调试账的位置 {raw} 是符号链接(指向 {os.path.realpath(raw)}),不动它:"
                               f"清空会删掉链接指向的那个目录里的东西。把它换成普通目录,或把环境变量 "
                               f"{state.DEBUG_ENV_VAR} 指到普通目录")
    path = raw.resolve()
    repo = Path(REPO_ROOT).resolve()
    if path == repo or path in repo.parents:
        raise DebugRootRefused(f"{path} 是代码仓库本身或它的上级目录,不是调试账")
    why = state.formal_conflict(path)
    if why:
        raise DebugRootRefused(f"{why},不是调试账")
    tracked = _tracked_files(path)
    if tracked:
        raise DebugRootRefused(f"{path} 里有受 git 跟踪的文件(例如 {tracked[0]}),调试账不进 git,这里不是调试账")
    if path.exists() and not path.is_dir():
        raise DebugRootRefused(f"{path} 不是目录")
    if not path.exists() or (path / state.DEBUG_MARKER).is_file() or not any(path.iterdir()):
        return path
    try:
        default = state.debug_default().resolve()
    except state.StateRootMissing:
        default = None
    if path == default:
        return path
    raise DebugRootRefused(f"{path} 不是空目录,也没有调试账的标记 {state.DEBUG_MARKER},不像调试账,不动它;"
                           f"确实要用这个位置,先自己把它清掉,或把环境变量 {state.DEBUG_ENV_VAR} 指到别处")


def _local_snapshot() -> Path:
    """本机训练数据副本目录,先核对它和正式账登记的是同一份(正式账没登记就不比)。
    不是同一份 → DebugRootRefused;读不了 → state.StateRootMissing。"""
    ddir = snaplock.local_dataset_dir()
    fp = snaplock.fingerprint(ddir, use_memo=False)
    try:
        formal = snaplock.read_lock(state.formal_locate())
    except state.StateRootMissing:
        formal = None
    if formal is not None and formal["current"]["sha"] != fp["sha"]:
        raise DebugRootRefused(
            f"本机副本 {ddir}(指纹 {fp['sha']})和正式账登记的({formal['current']['sha']})不是同一份;"
            f"调试账要和正式账用同一份副本,先照正式账的提示把登记那一份拷过来")
    return ddir


def _write(path: Path, ddir: Path) -> None:
    """建目录、写标记、登记副本(已登记过就不动)。"""
    path.mkdir(parents=True, exist_ok=True)
    (path / state.DEBUG_MARKER).write_text(MARKER_TEXT)
    if snaplock.read_lock(path) is None:
        snaplock.register(path, ddir)


def init() -> Path:
    """新建调试账(已经是调试账就只补副本登记),返回它的路径。不能建 → DebugRootRefused(什么都不建);
    本机副本读不了 → state.StateRootMissing。"""
    path = _check_target(location())
    if path.exists() and any(path.iterdir()) and not (path / state.DEBUG_MARKER).is_file():
        raise DebugRootRefused(f"{path} 里已有别的东西(不是调试账),新建会和它混在一起;"
                               f"要在这里重来,运行 python -m chart_workflow.debugroot clear")
    ddir = _local_snapshot()
    _write(path, ddir)
    return path


ensure = init


def _remove(p: Path) -> None:
    if p.is_symlink() or not p.is_dir():
        p.unlink()
    else:
        shutil.rmtree(p)


def clear() -> tuple[Path, list[str]]:
    """清空重来(见模块说明),返回 (路径, 删掉的顶层条目名)。不是调试账 → DebugRootRefused。"""
    path = _check_target(location())
    unknown = sorted(c.name for c in path.iterdir() if not _known(c.name)) if path.exists() else []
    if unknown:
        more = f" 等 {len(unknown)} 项" if len(unknown) > 10 else ""
        raise DebugRootRefused(f"{path} 里有调试账不认识的东西,一样都没删:{'、'.join(unknown[:10])}{more}。"
                               f"确认可以删的话先自己挪走,再清空")
    ddir = _local_snapshot()                     # 先核对副本:不能重建就什么都不删
    removed = []
    if path.exists():
        for child in sorted(path.iterdir()):
            if child.name in KEEP and child.is_dir() and not child.is_symlink():
                continue
            if child.name == state.DEBUG_MARKER and child.is_file() and not child.is_symlink():
                continue                                # 标记下面重写,不算删掉的东西
            _remove(child)
            removed.append(child.name)
    _write(path, ddir)
    return path, removed


def _count(p: Path, how: str) -> int:
    if how == "files_deep":
        return sum(1 for f in p.rglob("*") if f.is_file()) if p.exists() else 0
    return state._count(p, how)


def _summary(path: Path) -> list[str]:
    return [f"  {name:<10} {_count(path / rel, how):>6}  ({rel})" for name, rel, how in state._KINDS + DEBUG_ONLY]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="调试账:新建、清空重来、查看")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="调试账在哪、各类文件多少条、副本登记")
    sub.add_parser("init", help="新建调试账(已经是调试账就只补副本登记)")
    sub.add_parser("clear", help="清空重来:删掉调试账里除缓存以外的全部东西,重写标记、重新登记副本")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "init":
            path = init()
            print(f"调试账在 {path}(标记 {state.DEBUG_MARKER},已登记训练数据副本)")
            return
        if args.cmd == "clear":
            before = location()
            counts = _summary(before) if (before / state.DEBUG_MARKER).is_file() else []
            path, removed = clear()
            print(f"已清空调试账 {path}:删掉 {len(removed)} 项({'、'.join(removed) or '本来就是空的'}),"
                  f"保留 {'、'.join(KEEP)};已重写标记、重新登记副本")
            if counts:
                print("清空前:")
                print("\n".join(counts))
            return
        path = location()
        print(f"{mode.DEBUG_LABEL}")
        print(f"调试账:{path}")
        try:
            state.check_debug_root(path)
        except state.StateRootMissing as e:
            print(f"不能用:{e}", file=sys.stderr)
            sys.exit(2)
        print("\n".join(_summary(path)))
        lock = snaplock.read_lock(path)
        print(f"副本登记:{lock['current']['sha'] if lock else '没有登记'}")
    except (DebugRootRefused, state.StateRootMissing) as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
