"""状态根:看图工作流记账类文件唯一的家。

记账类文件(原始标注 annotations/、看过记录 views.jsonl 与 viewed_lists/、事实表快照 facts/、
形态卡 shapes/、操作日志 oplog/、账本 ledger.jsonl、规则存档 rule_archive/、配置存档 config_archive/、
水位重置记录 watermark_resets.jsonl)只存一份,放在
**主目录**(git 仓库的 main worktree)的 outputs/chart_workflow/ 下,受 git 跟踪;在任何
worktree 里运行工具,都经 state_root() 自动定位到主目录这一份。工具只写文件、不自己 commit。

清单 lists/、缓存 cache/、数据错误登记 data_errors.json 是可重算的产物,不在这里,
仍随各自 worktree 的 config.root(见 config.root_dir)。

定位:
  环境变量 CHART_WORKFLOW_STATE_ROOT 有值 → 用它(测试、端到端、冒烟用临时目录);
  否则 → `git rev-parse --git-common-dir` 的上一级(主目录)/ outputs / chart_workflow。

红线:状态根里必须有受 git 跟踪的标记文件 STATE_ROOT.md,找不到就抛 StateRootMissing 停下,
绝不悄悄新建空账——主目录切到没有这些文件的分支时,账本和看过记录会被拆成两份。
新开一本账只能显式运行 init,而且 init 不接受主目录(及任何 worktree)的默认位置:
默认位置的标记文件随记账文件一起受 git 跟踪,只能经 git 到达。

水位(防「标记在、账本却是旧的」):标记文件跟代码一起提交,合了代码、没合账本(或账本较旧)
的分支照样有标记。所以另在 git 公共目录里记一份水位
(<git 公共目录>/chart_workflow/watermark.json,不随分支走、所有 worktree 共用):
只追加的文件(账本、看过记录、操作日志、水位重置记录)记见过的每一行的指纹,
只增不改的目录(原始标注、看过的清单快照、事实表快照、规则存档、配置存档)记见过的文件名。
每次 state_root() 先核对「见过的行和文件都还在」(只看在不在、不看顺序,按行合并后行序变了也不误报),
少了就抛 StateRootRegressed(「账本比上次看到的少，可能切到了旧分支」)停下;核对通过后把当前内容记进水位。
写入方写完再调 advance(root),把刚写的内容也记进去。
有意改写记账文件(例如迁移旧账、重编轮次)之后,用 reset-watermark 显式重置,必须写原因,
重置记录追加到状态根的 watermark_resets.jsonl(受 git 跟踪)。
环境变量指定的临时状态根不在 git 分支切换的范围里,水位就放在它自己目录下的 .watermark.json。

副本登记(见 snaplock.py):state_root() 给出状态根之前,还核对本机训练数据副本的内容指纹与
状态根里 snapshot_lock.json 登记的是否一致,不一致就停下。

    uv run python -m chart_workflow.state show
    uv run python -m chart_workflow.state init <目录>
    uv run python -m chart_workflow.state reset-watermark --reason "<原因>"
    uv run python -m chart_workflow.state snapshot-register [--generated-on <主机名>]
    uv run python -m chart_workflow.state snapshot-replace --reason "<原因>"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
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
- `config_archive/`:每轮记账时生效配置的全文存档(按指纹)
- `watermark_resets.jsonl`:水位重置记录(谁、为什么改写过记账文件)
- `snapshot_lock.json`:这本账用的是哪一份训练数据副本(指纹、文件数、生成时间、在哪台机器生成,
  以及换副本的记录)。两台机器必须用同一份副本:在一台机器生成,原样拷到另一台

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
    ("配置存档", "config_archive", "files"),
    ("水位重置记录", "watermark_resets.jsonl", "lines"),
    ("副本登记", "snapshot_lock.json", "files_one"),
)

WATERMARK_SCHEMA = "chart_workflow.watermark/1"
RESETS_FILE = "watermark_resets.jsonl"
REGRESSED_TEXT = "账本比上次看到的少，可能切到了旧分支"
# 只追加的文件:按行记指纹
_LINE_FILES = ("ledger.jsonl", "views.jsonl", RESETS_FILE)
_LINE_DIRS = ("oplog",)                       # 目录下的 *.jsonl
# 只增不改的目录:按文件名记(递归,相对目录的路径)
_FILE_DIRS = ("annotations", "viewed_lists", "facts", "rule_archive", "config_archive")


class StateRootMissing(RuntimeError):
    """拿不到状态根(标记文件不在、git 不可用等)。消息是给用户看的中文。"""


class StateRootRegressed(StateRootMissing):
    """标记在,但记账文件比水位里见过的少(多半是主目录切到了旧分支)。
    是 StateRootMissing 的子类:所有「拿不到状态根就停」的地方照样停下。"""


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
            f"可能切到了别的分支。切回有记账文件的分支再用(标记文件随记账文件一起受 git 跟踪,"
            f"默认位置不能用 init 新建)。测试或临时用途:把环境变量 {ENV_VAR} 指到别的目录,"
            f"再运行 python -m chart_workflow.state init <那个目录>")


def watermark_path(root: Path, start: Path = REPO_ROOT) -> Path:
    """root 的水位文件。root 是环境变量指定的临时状态根 → root/.watermark.json;
    否则 → <git 公共目录>/chart_workflow/watermark.json(不随分支走、所有 worktree 共用)。"""
    env = os.environ.get(ENV_VAR)
    if env and Path(env).resolve() == Path(root).resolve():
        return Path(root) / ".watermark.json"
    return Path(_git_common_dir(str(Path(start).resolve()))) / "chart_workflow" / "watermark.json"


_HASH_CACHE: dict[tuple[str, int, int], list[str]] = {}
_WM_LOCK = threading.Lock()


def _line_hashes(p: Path) -> list[str]:
    """文件里每个完整行(以换行结尾)的指纹,去重排序。正在追加、还没写完换行的末行不算,
    免得把半行记进水位、之后又当成「少了一行」误报。按 (路径, 大小, 修改时间) 缓存。"""
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime_ns)
    if key not in _HASH_CACHE:
        if len(_HASH_CACHE) > 256:
            _HASH_CACHE.clear()
        data = p.read_bytes()
        hs = set()
        for line in data.split(b"\n")[:-1]:          # 最后一段没有换行结尾,不算
            line = line.rstrip(b"\r")
            if line.strip():
                hs.add(hashlib.sha1(line).hexdigest()[:16])
        _HASH_CACHE[key] = sorted(hs)
    return _HASH_CACHE[key]


def _current(root: Path) -> dict:
    """状态根当前内容的水位形式:{"lines": {相对路径: [行指纹…]}, "files": {目录: [文件名…]}}。"""
    lines: dict[str, list[str]] = {}
    for rel in _LINE_FILES:
        if (root / rel).is_file():
            lines[rel] = _line_hashes(root / rel)
    for d in _LINE_DIRS:
        if (root / d).is_dir():
            for f in sorted((root / d).glob("*.jsonl")):
                lines[f"{d}/{f.name}"] = _line_hashes(f)
    files: dict[str, list[str]] = {}
    for d in _FILE_DIRS:
        if (root / d).is_dir():
            files[d] = sorted(str(f.relative_to(root / d)) for f in (root / d).rglob("*")
                              if f.is_file() and not f.name.endswith(".tmp"))
    return {"lines": lines, "files": files}


def _missing(wm: dict, cur: dict) -> list[str]:
    """水位里见过、现在不在的东西,一条一句中文。空表 = 见过的都还在。"""
    out = []
    for rel, hs in sorted(wm.get("lines", {}).items()):
        have = set(cur["lines"].get(rel, ()))
        lost = sum(1 for h in hs if h not in have)
        if lost:
            out.append(f"{rel} 少了 {lost} 行(上次见过 {len(hs)} 行,现在 {len(have)} 行)")
    for d, names in sorted(wm.get("files", {}).items()):
        have = set(cur["files"].get(d, ()))
        lost = [n for n in names if n not in have]
        if lost:
            out.append(f"{d}/ 少了 {len(lost)} 个文件(例如 {lost[0]})")
    return out


def _summary(wm: dict) -> dict:
    return {"lines": {k: len(v) for k, v in sorted(wm.get("lines", {}).items())},
            "files": {k: len(v) for k, v in sorted(wm.get("files", {}).items())}}


def _read_wm(wm_file: Path) -> dict:
    try:
        wm = json.loads(wm_file.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise StateRootMissing(f"水位文件 {wm_file} 读不了({e});核对无从谈起,先停下。"
                               f"确认无误后可运行 reset-watermark 重建") from None
    if not isinstance(wm, dict) or wm.get("schema") != WATERMARK_SCHEMA:
        raise StateRootMissing(f"水位文件 {wm_file} 格式不对;确认无误后可运行 reset-watermark 重建")
    return wm


def _write_wm(wm_file: Path, root: Path, cur: dict) -> None:
    wm_file.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema": WATERMARK_SCHEMA, "state_root": str(root),
           "updated_at": datetime.now().isoformat(timespec="seconds"), **cur}
    tmp = wm_file.with_name(f"{wm_file.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False))
    os.replace(tmp, wm_file)


def _sync(root: Path, wm_file: Path) -> None:
    """核对水位:见过的行和文件都还在 → 把当前内容记进水位;少了 → StateRootRegressed。"""
    with _WM_LOCK:
        wm = _read_wm(wm_file)
        cur = _current(root)
        miss = _missing(wm, cur) if wm else []
        if miss:
            raise StateRootRegressed(
                f"{REGRESSED_TEXT}:状态根 {root} 里" + ";".join(miss) +
                f"。先切回最新的分支再用。确实是有意改写(例如迁移旧账、重编轮次),运行 "
                f"python -m chart_workflow.state reset-watermark --reason \"<原因>\" 重置水位"
                f"(水位文件 {wm_file})")
        if not wm or {k: wm.get(k) for k in ("lines", "files")} != cur:
            _write_wm(wm_file, root, cur)


def state_root(start: Path = REPO_ROOT) -> Path:
    """记账类文件的唯一的家。目录里没有标记文件 → StateRootMissing(绝不新建);
    记账文件比水位里见过的少 → StateRootRegressed。核对通过时顺手把当前内容记进水位。
    本机副本不是账上登记的那一份 → snaplock.SnapshotMismatch;主目录的账还没登记副本 →
    snaplock.SnapshotNotRegistered(两者都是 StateRootMissing 的子类)。"""
    path = locate(start)
    if not (path / MARKER).is_file():
        raise StateRootMissing(missing_message(path))
    _sync(path, watermark_path(path, start))
    from chart_workflow import snaplock             # 函数内导入:snaplock 依赖本模块
    snaplock.verify(snaplock.local_dataset_dir(), path)
    return path


def advance(root: Path) -> None:
    """写入方写完记账文件后调用:核对并把刚写的内容记进水位(下次切到旧分支就能发现少了它)。"""
    _sync(Path(root), watermark_path(root))


def reset_watermark(root: Path, reason: str, start: Path = REPO_ROOT) -> dict:
    """显式重置水位为当前内容。reason 必填;重置记录(时间、原因、少了什么、前后条数)
    追加到 root/watermark_resets.jsonl,返回这条记录。只在有意改写记账文件之后用。"""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("重置水位必须写明原因(--reason)")
    root = Path(root)
    if not (root / MARKER).is_file():
        raise StateRootMissing(missing_message(root))
    wm_file = watermark_path(root, start)
    with _WM_LOCK:
        try:
            wm = _read_wm(wm_file)
        except StateRootMissing:
            wm = {}
        cur = _current(root)
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "reason": reason,
               "watermark": str(wm_file), "missing": _missing(wm, cur) if wm else [],
               "before": _summary(wm), "after": _summary(cur)}
        with (root / RESETS_FILE).open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _write_wm(wm_file, root, _current(root))
    return rec


def _default_root_of(path: Path) -> list[Path]:
    """path 所在仓库里不能 init 的位置:主目录与当前 worktree 的 outputs/chart_workflow。
    path 不在 git 仓库里 → 空表。"""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--show-toplevel",
                            "--git-common-dir"], cwd=probe, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    top, common = r.stdout.strip().splitlines()[:2]
    return [Path(top).resolve() / "outputs" / "chart_workflow",
            Path(common).resolve().parent / "outputs" / "chart_workflow"]


def init(path: Path) -> Path:
    """显式新开一本账:建目录并写标记文件(已有标记就不动)。只有这里会建标记。
    拒绝主目录(及任何 worktree)的默认位置 → ValueError:那里的标记只能随记账文件经 git 到达,
    在旧分支上照提示 init 会在那段时间里开出一本空账。"""
    path = Path(path).resolve()
    if path in _default_root_of(path):
        raise ValueError(f"{path} 是默认状态根位置,不能用 init 新建:那里的标记文件随记账文件"
                         f"一起受 git 跟踪,切回有记账文件的分支即可。测试或临时用途请 init 别的目录,"
                         f"并用环境变量 {ENV_VAR} 指向它")
    path.mkdir(parents=True, exist_ok=True)
    marker = path / MARKER
    if not marker.exists():
        marker.write_text(MARKER_TEXT)
    return path


def _count(p: Path, how: str) -> int:
    if not p.exists():
        return 0
    if how == "files_one":
        return 1
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
    sub.add_parser("show", help="打印状态根路径、标记在不在、水位核对结果、各类文件条数")
    a = sub.add_parser("init", help="在指定目录新开一本账(写标记文件;不接受默认位置)")
    a.add_argument("path")
    r = sub.add_parser("reset-watermark", help="有意改写记账文件后重置水位(必须写原因,留记录)")
    r.add_argument("--reason", required=True, help="为什么改写了记账文件(例如「迁移旧账」)")
    g = sub.add_parser("snapshot-register", help="第一次登记这本账用的训练数据副本(本机副本)")
    g.add_argument("--generated-on", default=None,
                   help="副本在哪台机器生成;缺省取副本清单里记的主机,没有就取本机")
    c = sub.add_parser("snapshot-replace", help="换副本:登记成本机副本(必须写原因,留记录)")
    c.add_argument("--reason", required=True)
    c.add_argument("--generated-on", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "init":
        try:
            p = init(Path(args.path))
        except ValueError as e:
            print(f"错误:{e}", file=sys.stderr)
            sys.exit(2)
        print(f"已建状态根 {p}(标记 {MARKER})")
        return
    try:
        path = locate()
    except StateRootMissing as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)
    if args.cmd in ("snapshot-register", "snapshot-replace"):
        from chart_workflow import snaplock
        if not (path / MARKER).is_file():
            print(f"错误:{missing_message(path)}", file=sys.stderr)
            sys.exit(2)
        ddir = snaplock.local_dataset_dir()
        try:
            if args.cmd == "snapshot-register":
                doc = snaplock.register(path, ddir, args.generated_on)
            else:
                doc = snaplock.replace(path, ddir, args.reason, args.generated_on)
        except (ValueError, StateRootMissing) as e:
            print(f"错误:{e}", file=sys.stderr)
            sys.exit(2)
        cur = doc["current"]
        print(f"已登记副本 {cur['dir']}:指纹 {cur['sha']},{cur['n_files']} 个文件,"
              f"{cur['created_at']} 在 {cur['generated_on']} 生成 → {snaplock.lock_path(path)}")
        print("登记文件随记账文件进 git;另一台机器把这份副本原样拷过去,用 state show 核对指纹一致")
        return
    if args.cmd == "reset-watermark":
        try:
            rec = reset_watermark(path, args.reason)
        except (ValueError, StateRootMissing) as e:
            print(f"错误:{e}", file=sys.stderr)
            sys.exit(2)
        print(f"已重置水位({rec['watermark']}),原因:{rec['reason']}")
        for m in rec["missing"]:
            print(f"  重置前少了:{m}")
        print(f"重置记录已追加到 {path / RESETS_FILE}")
        return
    src = f"环境变量 {ENV_VAR}" if os.environ.get(ENV_VAR) else "主目录"
    has = (path / MARKER).is_file()
    print(f"状态根:{path}(来自{src})")
    print(f"标记文件 {MARKER}:{'在' if has else '不在'}")
    if not has:
        print(missing_message(path), file=sys.stderr)
        sys.exit(2)
    try:
        _sync(path, watermark_path(path))
        print(f"水位核对:通过({watermark_path(path)})")
    except StateRootMissing as e:
        print(f"水位核对:不通过。{e}", file=sys.stderr)
        sys.exit(2)
    for name, rel, how in _KINDS:
        print(f"  {name:<10} {_count(path / rel, how):>6}  ({rel})")
    from chart_workflow import snaplock
    ddir = snaplock.local_dataset_dir()
    try:
        fp = snaplock.fingerprint(ddir, use_memo=False)
        print(f"本机训练数据副本 {ddir}:指纹 {fp['sha']},{fp['n_files']} 个文件,"
              f"{fp['created_at']} 生成")
    except StateRootMissing as e:
        fp = None
        print(f"本机训练数据副本:{e}", file=sys.stderr)
    lock = snaplock.read_lock(path)
    if lock is None:
        print("账上登记的副本:没有登记(第一次在生成副本的那台机器上运行 state snapshot-register)")
        if not os.environ.get(ENV_VAR):
            sys.exit(2)
        return
    cur = lock["current"]
    print(f"账上登记的副本:指纹 {cur['sha']},{cur['n_files']} 个文件,{cur['created_at']} 在 "
          f"{cur['generated_on']} 生成({cur['registered_at']} 在 {cur['registered_on']} 登记;"
          f"换过 {len(lock['history'])} 次)")
    if fp is None or fp["sha"] != cur["sha"]:
        print(f"不一致:{snaplock.MISMATCH_TEXT}", file=sys.stderr)
        sys.exit(2)
    print("一致:本机副本就是账上登记的那一份")


if __name__ == "__main__":
    main()
