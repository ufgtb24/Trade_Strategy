"""状态根:看图工作流记账类文件唯一的家。

记账类文件(原始标注 annotations/、看过记录 views.jsonl 与 viewed_lists/、事实表快照 facts/、
要素库 elements/、形态卡 shapes/、操作日志 oplog/、账本 ledger.jsonl、规则存档 rule_archive/、
配置存档 config_archive/、水位重置记录 watermark_resets.jsonl、副本登记 snapshot_lock.json)只存一份,放在
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
(<git 公共目录>/chart_workflow/watermark.json,不随分支走、所有 worktree 共用;公共目录按状态根所在的仓库取,
不按代码所在的仓库取,状态根不在 git 仓库里就放在它自己目录下;水位文件里记着它是哪个状态根的,和当前状态根
对不上就停下(ForeignWatermark),不拿别处的水位当本账的比):
只追加的文件(账本、看过记录、操作日志、水位重置记录)每份记「到最后一个完整行为止的字节数 + 这一段的
sha256 + 行数」,见过的每一行的指纹另存在旁边的 watermark.seen/ 下(每份一个只追加的文本文件);
只增不改的目录(原始标注、看过的清单快照、事实表快照、规则存档、配置存档)记见过的文件名。
每次 state_root() 先核对「见过的行和文件都还在」:文件开头那一段和上次一字不差(正常追加)就只把新行的
指纹追加进见过记录;开头变了(按行合并后行序变了、或少了行)才拿见过记录里的全部指纹逐个找——只看在不在、
不看顺序,行序变了不误报;少了就抛 StateRootRegressed(「账本比上次看到的少，可能切到了旧分支」)停下。
同一进程里文件大小和修改时间都没变就不再读它。核对通过后把当前内容记进水位;
写入方写完再调 advance(root),把刚写的内容也记进去。check_root() 做同样的核对但什么都不写。
有意改写记账文件(例如迁移旧账、重编轮次)之后,用 reset-watermark 显式重置,必须写原因,
重置记录追加到状态根的 watermark_resets.jsonl(受 git 跟踪)。
环境变量指定的临时状态根不在 git 分支切换的范围里,水位就放在它自己目录下的 .watermark.json
(见过记录在 .watermark.seen/)。

别的分支上有更新的账:水位只认本机工具见过的行,另一台机器的账经 git 到了本机、本机工具还没运行过就切到
旧分支,水位查不出来。所以给出状态根之前还查本地分支与远端跟踪分支:先找有改过记账目录(标记文件除外)、
又不是当前分支祖先的提交的分支;再按内容比这个分支上记账目录里的文件和当前分支(状态根磁盘上的文件):
  只追加的文件(账本、看过记录、操作日志、水位重置记录):那个分支上的内容是当前分支这份的开头一段;
  要素库 elements/、形态卡 shapes/:由操作日志重算,只要求当前分支也有这个文件(内容跟着操作日志走,
      操作日志已按上一条比过);
  副本登记 snapshot_lock.json:那个分支上的换副本记录是当前分支这份的开头一段,登记的副本是当前分支
      现在的、或者当前分支后来换掉的那一份;
  其余文件:当前分支都有,并且一字不差。
都满足就是「那个分支上的账当前分支全有」(例如把当前分支用合并提交合进了那个分支),不拦;有当前分支
没有的账才 → StateRootDiverged(「别的分支上有更新的账」,列出分支、提交数和差在哪几个文件)。
当前分支领先别的分支是正常的,不拦。分支指向没变时沿用上次的结果,不再跑 git。
状态根不在 git 仓库里(环境变量指的临时目录)时不查。

副本登记(见 snaplock.py):state_root() 给出状态根之前,还核对本机训练数据副本的内容指纹与
状态根里 snapshot_lock.json 登记的是否一致,不一致就停下。

调试模式(见 mode.py,环境变量 CHART_WORKFLOW_MODE=debug):状态根换成调试账——环境变量
CHART_WORKFLOW_DEBUG_STATE_ROOT 有值就用它,否则是主目录的 outputs/chart_workflow_debug/(不进 git)。
调试模式不认 CHART_WORKFLOW_STATE_ROOT,正式账一行都不写。调试账的标记文件是 DEBUG_LEDGER.md:
  正式模式:状态根里有 DEBUG_LEDGER.md → 停下(那是调试账);
  调试模式:没有 DEBUG_LEDGER.md、有 STATE_ROOT.md、或者碰到正式账 → 停下。「碰到」= 和环境变量指的正式账、
  主目录默认的正式账任何一份是同一个目录 / 互相包含,或者往上任何一层里有 STATE_ROOT.md(formal_conflict)。
调试账不进 git、能清空重来,切分支动不了它,所以没有水位,也不查别的分支:advance 什么都不做,
reset-watermark 拒绝;正式水位(git 公共目录里那份)调试模式一律不读不写——主目录的调试账和正式账在同一个
仓库里,按仓库取水位位置就会落到正式那份上,所以 watermark_path 遇到调试模式或调试账直接报错。
调试账的副本登记照样核对(同一份训练数据副本)。新建、清空见 debugroot.py;init 只建正式格式的账。

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

from chart_workflow import mode
from chart_workflow.config import REPO_ROOT

MARKER = "STATE_ROOT.md"
ENV_VAR = "CHART_WORKFLOW_STATE_ROOT"
DEBUG_MARKER = "DEBUG_LEDGER.md"                  # 调试账的标记(见模块说明「调试模式」)
DEBUG_ENV_VAR = "CHART_WORKFLOW_DEBUG_STATE_ROOT"

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
- `elements/`:要素库(在事实表的行上定出来的是 / 否条件,由操作日志重算)
- `shapes/`:形态卡(引用要素编号,由操作日志重算)
- `oplog/`:操作日志(要素与形态卡的唯一真相)
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
    ("要素", "elements", "glob_json"),
    ("形态卡", "shapes", "glob_json"),
    ("操作日志条目", "oplog", "jsonl_lines"),
    ("账本行", "ledger.jsonl", "lines"),
    ("规则存档", "rule_archive", "files"),
    ("配置存档", "config_archive", "files"),
    ("水位重置记录", "watermark_resets.jsonl", "lines"),
    ("副本登记", "snapshot_lock.json", "files_one"),
)

WATERMARK_SCHEMA = "chart_workflow.watermark/2"
_OLD_SCHEMA = "chart_workflow.watermark/1"        # 旧格式:整份行指纹表存在水位文件里,读到时按慢路径核对并改写
RESETS_FILE = "watermark_resets.jsonl"
REGRESSED_TEXT = "账本比上次看到的少，可能切到了旧分支"
DIVERGED_TEXT = "别的分支上有更新的账"
# 只追加的文件:按行记指纹
_LINE_FILES = ("ledger.jsonl", "views.jsonl", RESETS_FILE)
_LINE_DIRS = ("oplog",)                       # 目录下的 *.jsonl
# 只增不改的目录:按文件名记(递归,相对目录的路径)
_FILE_DIRS = ("annotations", "viewed_lists", "facts", "elements", "rule_archive", "config_archive")


class StateRootMissing(RuntimeError):
    """拿不到状态根(标记文件不在、git 不可用等)。消息是给用户看的中文。"""


class StateRootRegressed(StateRootMissing):
    """标记在,但记账文件比水位里见过的少(多半是主目录切到了旧分支)。
    是 StateRootMissing 的子类:所有「拿不到状态根就停」的地方照样停下。"""


class StateRootDiverged(StateRootMissing):
    """本地分支或远端跟踪分支上有当前分支没有的账(另一台机器记的账经 git 到了本机、还没合进来),
    按内容比(见模块说明)。接着写两边的账就分叉了,所以停下。"""


class ForeignWatermark(StateRootMissing):
    """水位文件里记的是别的状态根的水位(多半是测试或别的工具把别处的水位写到了这里),不能拿来核对这本账。"""


class NotInRepo(StateRootMissing):
    """目录不在 git 仓库里。"""


class WrongModeRoot(StateRootMissing):
    """状态根属于另一种模式:正式模式遇到调试账,调试模式遇到正式账或和正式账重叠的目录。"""


@lru_cache(maxsize=16)
def _git_common_dir(start: str) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=start, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        raise StateRootMissing(f"找不到主目录:git 不可用({type(e).__name__}: {e})") from e
    if r.returncode != 0:
        raise NotInRepo(f"找不到主目录:{start} 不在 git 仓库里({r.stderr.strip()})")
    return r.stdout.strip()


def main_worktree(start: Path = REPO_ROOT) -> Path:
    """主目录:在 start 下执行 `git rev-parse --path-format=absolute --git-common-dir`,取上一级。
    在主目录和任何 worktree 里都返回主目录。git 不可用或不在仓库里 → StateRootMissing。"""
    return Path(_git_common_dir(str(Path(start).resolve()))).parent


def formal_locate(start: Path = REPO_ROOT) -> Path:
    """正式账应在的位置(不检查标记,不看模式)。环境变量 CHART_WORKFLOW_STATE_ROOT 优先。"""
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).resolve()
    return main_worktree(start) / "outputs" / "chart_workflow"


def formal_default(start: Path = REPO_ROOT) -> Path:
    """正式账的默认位置(主目录的 outputs/chart_workflow),不看环境变量。"""
    return main_worktree(start) / "outputs" / "chart_workflow"


def debug_default(start: Path = REPO_ROOT) -> Path:
    """调试账的默认位置:主目录的 outputs/chart_workflow_debug(正式账默认位置旁边加 _debug)。"""
    return mode.debug_variant(main_worktree(start) / "outputs" / "chart_workflow")


def debug_location_raw(start: Path = REPO_ROOT) -> Path:
    """调试账应在的位置,不解析符号链接(清空前用它看这个位置本身是不是链接)。环境变量优先。"""
    env = os.environ.get(DEBUG_ENV_VAR)
    if env:
        return Path(os.path.abspath(env))
    return debug_default(start)


def debug_locate(start: Path = REPO_ROOT) -> Path:
    """调试账应在的位置(不检查标记,不看模式)。环境变量 CHART_WORKFLOW_DEBUG_STATE_ROOT 优先。"""
    return debug_location_raw(start).resolve()


def locate(start: Path = REPO_ROOT) -> Path:
    """当前模式的状态根应在的位置(不检查标记):正式模式 formal_locate,调试模式 debug_locate。"""
    return debug_locate(start) if mode.is_debug() else formal_locate(start)


def overlaps(a: Path, b: Path) -> bool:
    """两个目录是同一个,或一个在另一个里面。"""
    a, b = Path(a).resolve(), Path(b).resolve()
    return a == b or a in b.parents or b in a.parents


def formal_candidates() -> list[Path]:
    """调试账不得碰的正式账位置:环境变量 CHART_WORKFLOW_STATE_ROOT 指的那份,以及主目录默认的那份
    (两个都比:环境变量指着临时目录时,主目录那份照样不能碰)。主目录取不到(git 不可用)就只比前一个。"""
    out = []
    env = os.environ.get(ENV_VAR)
    if env:
        out.append(Path(env).resolve())
    try:
        out.append(formal_default().resolve())
    except StateRootMissing:
        pass
    return out


def formal_conflict(path: Path) -> str | None:
    """path 当调试账会不会碰到正式账(给用户看的中文;None = 不会):和任何一份正式账(formal_candidates)是同一个
    目录或互相包含;或者往上逐层(不含 path 自己)任何一层里有正式账的标记 STATE_ROOT.md。
    path 自己里面有标记由调用方各自处理(清空时调试账的默认位置上允许有旧的正式格式标记,见 debugroot)。"""
    path = Path(path).resolve()
    for f in formal_candidates():
        if overlaps(path, f):
            return f"调试账 {path} 和正式账 {f} 是同一个目录或互相包含"
    for up in path.parents:
        if (up / MARKER).exists():
            return f"调试账 {path} 在正式账 {up} 里面(那一层有标记 {MARKER})"
    return None


def check_debug_root(path: Path) -> None:
    """path 能当调试账用。有正式账的标记、或碰到正式账(formal_conflict)→ WrongModeRoot;
    没有调试账的标记(还没建)→ StateRootMissing。消息是给用户看的中文。"""
    path = Path(path)
    if (path / MARKER).exists():
        raise WrongModeRoot(f"{path} 里有正式账的标记 {MARKER},不是调试账,调试模式不用它。"
                            f"它在调试账的位置上时,运行 python -m chart_workflow.debugroot clear 清空重建")
    why = formal_conflict(path)
    if why:
        raise WrongModeRoot(f"{why},调试模式不用它")
    if not (path / DEBUG_MARKER).is_file():
        raise StateRootMissing(
            f"{path} 下没有调试账的标记 {DEBUG_MARKER}:调试账还没建。运行 python -m chart_workflow.debugroot "
            f"init 新建(启动脚本 scripts/path2/run_path2_web_debug.py 会自动建);那里已有别的东西时,"
            f"运行 python -m chart_workflow.debugroot clear 清空重建")


def missing_message(path: Path) -> str:
    return (f"状态根 {path} 下没有标记文件 {MARKER}:主目录当前分支没有记账文件,"
            f"可能切到了别的分支。切回有记账文件的分支再用(标记文件随记账文件一起受 git 跟踪,"
            f"默认位置不能用 init 新建)。测试或临时用途:把环境变量 {ENV_VAR} 指到别的目录,"
            f"再运行 python -m chart_workflow.state init <那个目录>")


def _refuse_debug_watermark(root: Path) -> None:
    """调试模式、或 root 是调试账:不碰任何水位(见模块说明「调试模式」)。"""
    if mode.is_debug() or (Path(root) / DEBUG_MARKER).exists():
        raise StateRootMissing(f"调试模式与调试账没有水位,不读写任何水位文件({root})")


def watermark_path(root: Path) -> Path:
    """root 的水位文件,位置只跟着 root 走:root 是环境变量指定的临时状态根,或者不在 git 仓库里 →
    root/.watermark.json;否则 → root 所在仓库的 <git 公共目录>/chart_workflow/watermark.json(不随分支走、
    所有 worktree 共用)。不拿代码所在的仓库兜底——别的仓库里的状态根不会把水位写进这份代码所在仓库的 .git。
    调试模式或 root 是调试账 → StateRootMissing(调试账没有水位,主目录的调试账按仓库取会落到正式水位上)。"""
    _refuse_debug_watermark(root)
    env = os.environ.get(ENV_VAR)
    if env and Path(env).resolve() == Path(root).resolve():
        return Path(root) / ".watermark.json"
    try:
        common = _git_common_dir(str(Path(root).resolve()))
    except NotInRepo:
        return Path(root) / ".watermark.json"
    return Path(common) / "chart_workflow" / "watermark.json"


_HASH_CACHE: dict[tuple[str, int, int], list[str]] = {}
_OK_CACHE: dict[tuple[str, str], tuple] = {}         # (水位文件, 相对路径) → 上次核对通过时的 (大小, 修改时间, 记录)
_WM_LOCK = threading.Lock()


def _hashes_of(chunk: bytes) -> list[str]:
    """一段字节里每个完整行(以换行结尾)的指纹;空行不算。"""
    out = []
    for line in chunk.split(b"\n")[:-1]:
        line = line.rstrip(b"\r")
        if line.strip():
            out.append(hashlib.sha1(line).hexdigest()[:16])
    return out


def _line_hashes(p: Path) -> list[str]:
    """文件里每个完整行的指纹,去重排序。正在追加、还没写完换行的末行不算,
    免得把半行记进水位、之后又当成「少了一行」误报。按 (路径, 大小, 修改时间) 缓存。"""
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime_ns)
    if key not in _HASH_CACHE:
        if len(_HASH_CACHE) > 256:
            _HASH_CACHE.clear()
        _HASH_CACHE[key] = sorted(set(_hashes_of(p.read_bytes())))
    return _HASH_CACHE[key]


def _line_rels(root: Path) -> list[str]:
    out = [rel for rel in _LINE_FILES if (root / rel).is_file()]
    for d in _LINE_DIRS:
        if (root / d).is_dir():
            out += [f"{d}/{f.name}" for f in sorted((root / d).glob("*.jsonl"))]
    return out


def _current_files(root: Path) -> dict[str, list[str]]:
    files: dict[str, list[str]] = {}
    for d in _FILE_DIRS:
        if (root / d).is_dir():
            files[d] = sorted(str(f.relative_to(root / d)) for f in (root / d).rglob("*")
                              if f.is_file() and not f.name.endswith(".tmp"))
    return files


def _seen_file(wm_file: Path, rel: str) -> Path:
    """见过的行指纹存在水位文件旁边的 <水位文件名>.seen/ 下,一个只追加的文本文件一份。"""
    return wm_file.with_name(wm_file.stem + ".seen") / (rel.replace("/", "__") + ".txt")


def _entry_n(entry) -> int:
    if isinstance(entry, list):                       # 旧格式(chart_workflow.watermark/1):整份指纹表
        return len(entry)
    return int(entry.get("n", 0)) if isinstance(entry, dict) else 0


def _read_seen(wm_file: Path, rel: str) -> set[str] | None:
    try:
        return {x for x in _seen_file(wm_file, rel).read_text().split() if x}
    except FileNotFoundError:
        return None


def _check_lines(root: Path, rel: str, entry, wm_file: Path):
    """核对一份只追加的文件:见过的行都还在。返回 (新记录, 见过记录的改法, 问题)。
    新记录 {"bytes": 到最后一个完整行为止的字节数, "sha": 这一段的 sha256, "n": 见过的行数};
    改法 ("append" | "rewrite", 行指纹) 或 None。
    快路径:文件开头那一段和上次见过的一字不差(正常追加)→ 只把后面新出现的行记进见过记录。
    慢路径(开头那段变了:按行合并后行序变了、或少了行):拿见过记录里的全部行指纹逐个找,有找不到的就是少了。"""
    p = root / rel
    if not p.is_file():
        n = _entry_n(entry)
        return None, None, (f"{rel} 少了 {n} 行(上次见过 {n} 行,现在 0 行)" if n else None)
    st = p.stat()
    ck = (str(wm_file), rel)
    if isinstance(entry, dict) and _OK_CACHE.get(ck) == (st.st_size, st.st_mtime_ns, entry.get("sha")):
        return entry, None, None
    data = p.read_bytes()
    end = data.rfind(b"\n") + 1
    if isinstance(entry, dict) and entry.get("bytes", 0) <= end \
            and hashlib.sha256(data[:entry["bytes"]]).hexdigest() == entry.get("sha"):
        if entry["bytes"] == end:
            return entry, None, None
        new = _hashes_of(data[entry["bytes"]:end])
        return ({"bytes": end, "sha": hashlib.sha256(data[:end]).hexdigest(), "n": entry["n"] + len(new)},
                ("append", new), None)
    if isinstance(entry, list):
        seen = set(entry)
    elif entry:
        seen = _read_seen(wm_file, rel)
        if seen is None:
            return None, None, f"{rel} 的见过记录({_seen_file(wm_file, rel)})不见了,核对不了"
    else:
        seen = set()
    cur = set(_hashes_of(data[:end]))
    lost = len(seen - cur)
    if lost:
        return None, None, f"{rel} 少了 {lost} 行(上次见过 {len(seen)} 行,现在 {len(cur)} 行)"
    return ({"bytes": end, "sha": hashlib.sha256(data[:end]).hexdigest(), "n": len(cur)},
            ("rewrite", sorted(cur)), None)


def _missing_files(wm_files: dict, cur: dict) -> list[str]:
    out = []
    for d, names in sorted(wm_files.items()):
        have = set(cur.get(d, ()))
        lost = [n for n in names if n not in have]
        if lost:
            out.append(f"{d}/ 少了 {len(lost)} 个文件(例如 {lost[0]})")
    return out


def _scan(root: Path, wm_file: Path, wm: dict):
    """把状态根当前内容和水位比一遍:(问题清单, 新的行记录, 见过记录的改法, 当前文件名)。"""
    old = wm.get("lines", {})
    problems, lines, ops = [], {}, {}
    for rel in sorted(set(_line_rels(root)) | set(old)):
        entry, op, prob = _check_lines(root, rel, old.get(rel), wm_file)
        if prob:
            problems.append(prob)
            continue
        if entry is not None:
            lines[rel] = entry
        if op:
            ops[rel] = op
    files = _current_files(root)
    problems += _missing_files(wm.get("files", {}), files)
    return problems, lines, ops, files


def _apply(root: Path, wm_file: Path, wm: dict, lines: dict, ops: dict, files: dict) -> None:
    """先改见过记录(只追加;慢路径整份重写),再写水位文件(有变化才写)。中途断掉也安全:
    水位文件还是旧的,下次照旧从那里核对,见过记录里多出的指纹不影响判断。"""
    for rel, (how, hs) in ops.items():
        f = _seen_file(wm_file, rel)
        f.parent.mkdir(parents=True, exist_ok=True)
        if how == "rewrite":
            tmp = f.with_name(f"{f.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text("".join(h + "\n" for h in hs))
            os.replace(tmp, f)
        elif hs:
            with f.open("a") as fh:
                fh.write("".join(h + "\n" for h in hs))
    if wm.get("schema") != WATERMARK_SCHEMA or wm.get("lines") != lines or wm.get("files") != files:
        _write_wm(wm_file, root, {"lines": lines, "files": files})
    for rel, entry in lines.items():
        try:
            st = (root / rel).stat()
        except FileNotFoundError:
            continue
        if st.st_size >= entry["bytes"]:
            _OK_CACHE[(str(wm_file), rel)] = (st.st_size, st.st_mtime_ns, entry["sha"])


def _summary(wm: dict) -> dict:
    return {"lines": {k: _entry_n(v) for k, v in sorted(wm.get("lines", {}).items())},
            "files": {k: len(v) for k, v in sorted(wm.get("files", {}).items())}}


def _read_wm(wm_file: Path) -> dict:
    try:
        wm = json.loads(wm_file.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise StateRootMissing(f"水位文件 {wm_file} 读不了({e});核对无从谈起,先停下。"
                               f"确认无误后可运行 reset-watermark 重建") from None
    if not isinstance(wm, dict) or wm.get("schema") not in (WATERMARK_SCHEMA, _OLD_SCHEMA):
        raise StateRootMissing(f"水位文件 {wm_file} 格式不对;确认无误后可运行 reset-watermark 重建")
    return wm


def _write_wm(wm_file: Path, root: Path, cur: dict) -> None:
    wm_file.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema": WATERMARK_SCHEMA, "state_root": str(root),
           "updated_at": datetime.now().isoformat(timespec="seconds"), **cur}
    tmp = wm_file.with_name(f"{wm_file.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False))
    os.replace(tmp, wm_file)


def _foreign_root(wm: dict, root: Path) -> str | None:
    """水位文件里记的状态根和 root 不是同一个 → 那个状态根(字符串);是同一个,或旧格式没记 → None。"""
    other = wm.get("state_root")
    if other and Path(other).resolve() != Path(root).resolve():
        return str(other)
    return None


def _sync(root: Path, wm_file: Path, write: bool = True) -> None:
    """核对水位:见过的行和文件都还在 → write 时把当前内容记进水位;少了 → StateRootRegressed;
    水位文件记的是别的状态根 → ForeignWatermark(不拿别处的水位当本账的比)。
    write=False:只核对,什么都不写(只读接口用)。调试模式或调试账 → StateRootMissing(不碰水位)。"""
    _refuse_debug_watermark(root)
    with _WM_LOCK:
        wm = _read_wm(wm_file)
        foreign = _foreign_root(wm, root)
        if foreign:
            raise ForeignWatermark(
                f"水位文件 {wm_file} 记的是状态根 {foreign} 的水位,不是 {root} 的,不能拿它核对这本账"
                f"(多半是测试或别的工具把别处的水位写到了这里)。确认这本账没问题后,运行 python -m "
                f"chart_workflow.state reset-watermark --reason \"<原因>\" 重置水位")
        problems, lines, ops, files = _scan(root, wm_file, wm)
        if problems:
            raise StateRootRegressed(
                f"{REGRESSED_TEXT}:状态根 {root} 里" + ";".join(problems) +
                f"。先切回最新的分支再用。确实是有意改写(例如迁移旧账、重编轮次),运行 "
                f"python -m chart_workflow.state reset-watermark --reason \"<原因>\" 重置水位"
                f"(水位文件 {wm_file})")
        if write:
            _apply(root, wm_file, wm, lines, ops, files)


# ── 别的分支上有没有更新的账 ─────────────────────────────────────────────────

@lru_cache(maxsize=16)
def _repo_of(root: str) -> tuple[str, str, str] | None:
    """root 所在 git 仓库:(工作区顶层, git 目录, 公共目录);不在仓库里或 git 不可用 → None。"""
    try:
        r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-dir",
                            "--git-common-dir"], cwd=root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    top, gitdir, common = r.stdout.strip().splitlines()[:3]
    return top, gitdir, common


def _refs_signature(gitdir: str, common: str) -> tuple:
    """当前分支与全部本地 / 远端跟踪分支的指向有没有变:HEAD、packed-refs、refs/heads 与 refs/remotes 下
    每个文件的 (路径, 大小, 修改时间)。没变就沿用上次的核对结果,不再跑 git。"""
    items = []
    for f in (Path(gitdir) / "HEAD", Path(common) / "packed-refs"):
        try:
            st = f.stat()
            items.append((str(f), st.st_size, st.st_mtime_ns, f.read_text() if f.name == "HEAD" else ""))
        except OSError:
            pass
    for sub in ("refs/heads", "refs/remotes"):
        for dp, _, fns in os.walk(Path(common) / sub):
            for fn in fns:
                f = Path(dp) / fn
                try:
                    st = f.stat()
                except OSError:
                    continue
                items.append((str(f), st.st_size, st.st_mtime_ns, ""))
    return tuple(sorted(items))


_DIVERGE_CACHE: dict[tuple, list[str]] = {}


def _git_out(top: str, *args) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=top, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


_DERIVED_DIRS = ("elements", "shapes")           # 由操作日志重算的目录:只要求文件在
_LOCK_FILE = "snapshot_lock.json"


def _blob_id(data: bytes) -> str:
    """git 给这段内容的对象编号(与 git hash-object 相同)。"""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _cat_blob(top: str, oid: str) -> bytes | None:
    try:
        r = subprocess.run(["git", "cat-file", "blob", oid], cwd=top, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _lock_contained(theirs: bytes, mine: bytes) -> bool:
    """那个分支上的副本登记当前分支都有:换副本记录是当前这份的开头一段,登记的副本是现在的或后来换掉的。"""
    try:
        t, m = json.loads(theirs), json.loads(mine)
        th, mh = list(t.get("history") or []), list(m.get("history") or [])
    except (ValueError, AttributeError, TypeError):
        return False
    if mh[:len(th)] != th:
        return False
    if len(mh) == len(th):
        return t.get("current") == m.get("current")
    return mh[len(th)].get("old") == t.get("current")


def _new_on_ref(top: str, ref: str, rel: str, root: Path) -> list[str]:
    """那个分支上记账目录里当前分支没有的账,按文件列原因(见模块说明「别的分支上有更新的账」)。"""
    listing = _git_out(top, "ls-tree", "-r", "-z", "--full-tree", ref, "--", rel)
    if listing is None:
        return [f"读不到 {ref} 上的记账目录"]
    line_rels = set(_LINE_FILES)
    out = []
    for item in listing.split("\0"):
        if not item:
            continue
        meta, path = item.split("\t", 1)
        oid = meta.split()[2]
        sub = os.path.relpath(path, rel).replace(os.sep, "/")
        if sub == MARKER:
            continue
        here = root / sub
        if not here.is_file():
            out.append(f"{sub} 当前分支没有")
            continue
        top_dir = sub.split("/", 1)[0]
        if top_dir in _DERIVED_DIRS:
            continue
        mine = here.read_bytes()
        if _blob_id(mine) == oid:
            continue
        if sub in line_rels or (top_dir in _LINE_DIRS and sub.endswith(".jsonl")):
            theirs = _cat_blob(top, oid)
            if theirs is None or not mine.startswith(theirs):
                out.append(f"{sub} 有当前分支没有的行")
        elif sub == _LOCK_FILE:
            theirs = _cat_blob(top, oid)
            if theirs is None or not _lock_contained(theirs, mine):
                out.append(f"{sub} 登记的副本或换副本记录当前分支没有")
        else:
            out.append(f"{sub} 和当前分支的不一样")
    return out


def foreign_ledger_refs(root: Path) -> list[str]:
    """本地分支或远端跟踪分支上有当前分支没有的账,按分支列:["origin/wayfinder(3 个提交;ledger.jsonl
    有当前分支没有的行)", …]。先找改过记账目录(标记文件除外)、又不是当前分支祖先的提交;有这类提交的分支
    再按内容比(见模块说明),那个分支上的账当前分支全有就不算。root 不在 git 仓库里(环境变量指的临时
    状态根)→ 空表。当前分支领先别的分支是正常的。"""
    root = Path(root).resolve()
    repo = _repo_of(str(root))
    if repo is None:
        return []
    top, gitdir, common = repo
    rel = os.path.relpath(root, top)
    if rel.startswith(".."):
        return []
    key = (str(root), _refs_signature(gitdir, common))
    if key in _DIVERGE_CACHE:
        return _DIVERGE_CACHE[key]
    paths = ["--", rel, f":(exclude){rel}/{MARKER}"]
    out: list[str] = []
    found = _git_out(top, "log", "--branches", "--remotes", "--not", "HEAD", "--format=%H", *paths)
    if found and found.split():
        refs = _git_out(top, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes") or ""
        for ref in refs.split():
            if ref.endswith("/HEAD"):
                continue
            n = _git_out(top, "rev-list", "--count", ref, "--not", "HEAD", *paths)
            if not (n and int(n.strip()) > 0):
                continue
            new = _new_on_ref(top, ref, rel, root)
            if new:
                more = f" 等 {len(new)} 处" if len(new) > 3 else ""
                out.append(f"{ref}({int(n.strip())} 个提交;{'、'.join(new[:3])}{more})")
    if len(_DIVERGE_CACHE) > 64:
        _DIVERGE_CACHE.clear()
    _DIVERGE_CACHE[key] = out
    return out


def _check_diverged(root: Path) -> None:
    refs = foreign_ledger_refs(root)
    if refs:
        raise StateRootDiverged(
            f"{DIVERGED_TEXT}:{'、'.join(refs)} 上有记账目录 {root} 里当前分支没有的账"
            f"(多半是另一台机器记了账,或别的分支上记过账)。先把它们合进当前分支、再用;"
            f"不要的分支删掉。不合就接着写,两边的账会分叉")


def _checked(start: Path, write: bool) -> Path:
    from chart_workflow import snaplock             # 函数内导入:snaplock 依赖本模块
    if mode.is_debug():
        path = debug_locate(start)
        check_debug_root(path)
        snaplock.verify(snaplock.local_dataset_dir(), path)
        return path
    path = formal_locate(start)
    if (path / DEBUG_MARKER).exists():
        raise WrongModeRoot(f"状态根 {path} 是调试账(有标记 {DEBUG_MARKER}),正式模式不用它;"
                            f"把环境变量 {ENV_VAR} 指到正式账,或调试时设 {mode.ENV_VAR}={mode.DEBUG}")
    if not (path / MARKER).is_file():
        raise StateRootMissing(missing_message(path))
    _sync(path, watermark_path(path), write=write)
    _check_diverged(path)
    snaplock.verify(snaplock.local_dataset_dir(), path)
    return path


def state_root(start: Path = REPO_ROOT) -> Path:
    """记账类文件的唯一的家。目录里没有标记文件 → StateRootMissing(绝不新建);
    记账文件比水位里见过的少 → StateRootRegressed;别的分支上有更新的账 → StateRootDiverged。
    核对通过时顺手把当前内容记进水位。本机副本不是账上登记的那一份 → snaplock.SnapshotMismatch;
    账还没登记副本 → snaplock.SnapshotNotRegistered(这几种都是 StateRootMissing 的子类)。
    调试模式下是调试账(见模块说明「调试模式」):不能用 → StateRootMissing / WrongModeRoot,不碰水位。"""
    return _checked(start, write=True)


def check_root(start: Path = REPO_ROOT) -> Path:
    """和 state_root 同样的核对,但什么都不写(只读接口用,例如网页的「状态根在哪」)。"""
    return _checked(start, write=False)


def advance(root: Path) -> None:
    """写入方写完记账文件后调用:核对并把刚写的内容记进水位(下次切到旧分支就能发现少了它)。
    调试模式下什么都不做(调试账没有水位)。"""
    if mode.is_debug():
        return
    _sync(Path(root), watermark_path(root))


def reset_watermark(root: Path, reason: str) -> dict:
    """显式重置水位为当前内容。reason 必填;重置记录(时间、原因、少了什么、前后条数)
    追加到 root/watermark_resets.jsonl,返回这条记录。只在有意改写记账文件之后用。
    原来的水位记的是别的状态根时不拿它比,记录里写明是哪个状态根的(foreign_watermark)。"""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("重置水位必须写明原因(--reason)")
    root = Path(root)
    _refuse_debug_watermark(root)
    if not (root / MARKER).is_file():
        raise StateRootMissing(missing_message(root))
    wm_file = watermark_path(root)
    with _WM_LOCK:
        try:
            wm = _read_wm(wm_file)
        except StateRootMissing:
            wm = {}
        foreign = _foreign_root(wm, root)
        if foreign:
            wm = {}
        problems = _scan(root, wm_file, wm)[0] if wm else []
        _, lines, ops, files = _scan(root, wm_file, {})
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "reason": reason,
               "watermark": str(wm_file), "missing": problems,
               "before": _summary(wm), "after": _summary({"lines": lines, "files": files})}
        if foreign:
            rec["foreign_watermark"] = foreign
        with (root / RESETS_FILE).open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _, lines, ops, files = _scan(root, wm_file, {})
        _apply(root, wm_file, {}, lines, ops, files)
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
    if (path / DEBUG_MARKER).exists() or path in [mode.debug_variant(p) for p in _default_root_of(path)]:
        raise ValueError(f"{path} 是调试账(或调试账的默认位置),不能在这里开正式格式的账;"
                         f"调试账用 python -m chart_workflow.debugroot init")
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
    try:
        debug = mode.is_debug()
    except mode.ModeError as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)
    if debug and args.cmd != "show":
        print(f"错误:调试模式下 state {args.cmd} 不可用:调试账没有水位,新建、清空、登记副本用 "
              f"python -m chart_workflow.debugroot init / clear", file=sys.stderr)
        sys.exit(2)
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
    if debug:
        src = f"环境变量 {DEBUG_ENV_VAR}" if os.environ.get(DEBUG_ENV_VAR) else "主目录"
        print(f"调试模式:{mode.DEBUG_LABEL}")
        print(f"状态根:{path}(调试账,来自{src})")
        try:
            check_debug_root(path)
        except StateRootMissing as e:
            print(f"标记文件 {DEBUG_MARKER}:不能用。{e}", file=sys.stderr)
            sys.exit(2)
        print(f"标记文件 {DEBUG_MARKER}:在")
        print("水位:调试账没有水位(不进 git,能清空重来)")
    else:
        src = f"环境变量 {ENV_VAR}" if os.environ.get(ENV_VAR) else "主目录"
        has = (path / MARKER).is_file()
        print(f"状态根:{path}(来自{src})")
        print(f"标记文件 {MARKER}:{'在' if has else '不在'}")
        if not has:
            print(missing_message(path), file=sys.stderr)
            sys.exit(2)
        if (path / DEBUG_MARKER).exists():
            print(f"这是调试账(有标记 {DEBUG_MARKER}),正式模式不用它", file=sys.stderr)
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
        print("账上登记的副本:没有登记(" + ("调试账运行 python -m chart_workflow.debugroot clear 重建" if debug else
              "第一次在生成副本的那台机器上运行 state snapshot-register;临时状态根也要登记") + ")",
              file=sys.stderr)
        sys.exit(2)
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
