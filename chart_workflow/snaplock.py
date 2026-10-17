"""副本登记:这本账用的是哪一份训练数据副本(截断副本),两台机器必须是同一份。

两台机器都用来看图,事实表、清单、对照成绩要在两台上算得一样,所以截断副本只在一台机器上生成,
原样拷到另一台;不在两台各自重新生成(两台下载的原始行情不同,复权也会随时间变,重新生成就不一样)。

指纹(fingerprint):按文件内容算,不看修改时间——副本目录里每个文件(含 SNAPSHOT.json)按文件名排序,
逐个取内容的 sha256,把「文件名 TAB 内容指纹」逐行拼起来再取一次 sha256。拷贝时保留不保留修改时间
都不影响它;多一个、少一个或改了一个文件都会变。整份副本算一遍约零点几秒,同一进程里按
(目录, SNAPSHOT.json 的修改时间)记住结果,进程运行中原地改了副本要重启才会重新算。

登记文件:<状态根>/snapshot_lock.json(受 git 跟踪):
{"schema": "chart_workflow.snapshot_lock/1",
 "current": {"sha", "n_files", "cutoff", "created_at"(副本生成时间), "generated_on"(在哪台机器生成),
             "dir"(登记时的副本目录), "registered_at", "registered_on"},
 "history": [{"at", "on", "reason", "old": {...}, "new": {...}}]}     # 换副本的记录
第一次登记:python -m chart_workflow.state snapshot-register(已有登记就拒绝);
以后换副本:python -m chart_workflow.state snapshot-replace --reason "<原因>"(必须写原因,记进 history)。

核对(verify):读数据口(loader.check_snapshot)每次读之前、状态根(state.state_root)每次给出之前都核对
本机副本的指纹与登记的是否一致:
  不一致 → SnapshotMismatch(「本机的训练数据副本和账上登记的不是同一份,请把登记那一份原样拷过来」,
           并写出登记的指纹和本机的指纹);
  没登记 → 主目录的状态根:SnapshotNotRegistered(先显式登记);
           环境变量指定的临时状态根(测试、端到端、冒烟):不核对。
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
from datetime import datetime
from pathlib import Path

from chart_workflow import state as _state
from chart_workflow.config import REPO_ROOT

LOCK_FILE = "snapshot_lock.json"
LOCK_SCHEMA = "chart_workflow.snapshot_lock/1"
MISMATCH_TEXT = "本机的训练数据副本和账上登记的不是同一份，请把登记那一份原样拷过来"
_SNAPSHOT_FILE = "SNAPSHOT.json"           # 与 loader.SNAPSHOT_FILE 同值(避免循环导入)

_FP: dict[tuple[str, int], dict] = {}
_VERIFIED: set[tuple] = set()


class SnapshotNotRegistered(_state.StateRootMissing):
    """主目录的状态根还没登记用哪一份副本。是 StateRootMissing 的子类:拿不到状态根就停的地方照样停。"""


class SnapshotMismatch(_state.StateRootMissing):
    """本机副本的指纹与登记的不一致。"""


def _manifest(ddir: Path) -> tuple[dict, int]:
    f = ddir / _SNAPSHOT_FILE
    try:
        mtime = f.stat().st_mtime_ns
        man = json.loads(f.read_text())
    except (OSError, ValueError) as e:
        raise _state.StateRootMissing(f"数据目录 {ddir} 不是截断副本(读不了 {_SNAPSHOT_FILE}:{e})") \
            from None
    return (man if isinstance(man, dict) else {}), mtime


def fingerprint(ddir, use_memo: bool = True) -> dict:
    """副本的内容指纹 {"sha", "n_files", "cutoff", "created_at", "generated_on"}(见模块说明)。
    use_memo=False:不用进程内记住的结果,重新按内容算。"""
    ddir = Path(ddir)
    man, mtime = _manifest(ddir)
    key = (str(ddir.resolve()), mtime)
    if use_memo and key in _FP:
        return _FP[key]
    h = hashlib.sha256()
    n_pkl = 0
    for f in sorted(ddir.iterdir(), key=lambda p: p.name):
        if not f.is_file():
            continue
        h.update(f"{f.name}\t{hashlib.sha256(f.read_bytes()).hexdigest()}\n".encode())
        n_pkl += f.suffix == ".pkl"
    fp = {"sha": h.hexdigest(), "n_files": n_pkl, "cutoff": man.get("cutoff"),
          "created_at": man.get("created_at"), "generated_on": man.get("host")}
    _FP[key] = fp
    return fp


def lock_path(root: Path) -> Path:
    return Path(root) / LOCK_FILE


def read_lock(root: Path) -> dict | None:
    """读登记文件;没有 → None;格式不对 → StateRootMissing。"""
    p = lock_path(root)
    try:
        doc = json.loads(p.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise _state.StateRootMissing(f"副本登记文件 {p} 读不了({e})") from None
    if not isinstance(doc, dict) or doc.get("schema") != LOCK_SCHEMA \
            or not isinstance((doc.get("current") or {}).get("sha"), str):
        raise _state.StateRootMissing(f"副本登记文件 {p} 格式不对")
    return doc


def local_dataset_dir() -> Path:
    """本机看图工作流用的副本目录(chart_workflow 配置的 dataset_dir)。"""
    from chart_workflow.config import dataset_dir, load_config
    return dataset_dir(load_config())


def _shown(ddir: Path) -> str:
    try:
        return str(Path(ddir).relative_to(REPO_ROOT))
    except ValueError:
        return str(ddir)


def _entry(ddir: Path, generated_on: str | None) -> dict:
    fp = fingerprint(ddir, use_memo=False)
    host = socket.gethostname()
    return {**fp, "generated_on": generated_on or fp["generated_on"] or host,
            "dir": _shown(ddir), "registered_at": datetime.now().isoformat(timespec="seconds"),
            "registered_on": host}


def _write_lock(root: Path, doc: dict) -> None:
    p = lock_path(root)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    tmp.replace(p)
    _VERIFIED.clear()


def register(root: Path, ddir, generated_on: str | None = None) -> dict:
    """第一次登记这本账用的副本。已有登记 → ValueError(换副本走 replace)。
    generated_on:副本在哪台机器生成;缺省取副本清单里记的主机,清单里没有就取本机
    (副本只在一台机器生成,登记也在那台做)。"""
    root = Path(root)
    if read_lock(root) is not None:
        raise ValueError(f"这本账已经登记过副本({lock_path(root)});换副本用 snapshot-replace --reason")
    doc = {"schema": LOCK_SCHEMA, "current": _entry(Path(ddir), generated_on), "history": []}
    _write_lock(root, doc)
    return doc


def replace(root: Path, ddir, reason: str, generated_on: str | None = None) -> dict:
    """换副本:必须写原因,旧的与新的都记进 history。没登记过 → ValueError(先 register)。"""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("换副本必须写明原因(--reason)")
    root = Path(root)
    doc = read_lock(root)
    if doc is None:
        raise ValueError("这本账还没登记副本,第一次请用 snapshot-register")
    new = _entry(Path(ddir), generated_on)
    doc["history"].append({"at": new["registered_at"], "on": new["registered_on"], "reason": reason,
                           "old": doc["current"], "new": new})
    doc["current"] = new
    _write_lock(root, doc)
    return doc


def mismatch_message(lock: dict, fp: dict, ddir: Path) -> str:
    cur = lock["current"]
    return (f"{MISMATCH_TEXT}。登记的指纹 {cur['sha']}({cur.get('n_files')} 个文件,"
            f"{cur.get('created_at')} 在 {cur.get('generated_on')} 生成);"
            f"本机 {ddir} 的指纹 {fp['sha']}({fp['n_files']} 个文件,{fp.get('created_at')} 生成)。"
            f"确实要换副本,运行 python -m chart_workflow.state snapshot-replace --reason \"<原因>\"")


def verify(ddir, root: Path | None = None) -> None:
    """核对本机副本 ddir 与 root(缺省:当前状态根位置)登记的是否同一份(见模块说明)。"""
    from_env = bool(os.environ.get(_state.ENV_VAR))
    root = Path(root) if root is not None else _state.locate()
    ddir = Path(ddir)
    lp = lock_path(root)
    try:
        st = lp.stat()
        lock_key = (st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        lock_key = None
    _, man_mtime = _manifest(ddir)
    key = (str(root), lock_key, str(ddir.resolve()), man_mtime)
    if key in _VERIFIED:
        return
    lock = read_lock(root) if lock_key is not None else None
    if lock is None:
        if from_env:
            return                          # 临时状态根:不核对
        raise SnapshotNotRegistered(
            f"状态根 {root} 还没登记这本账用哪一份训练数据副本。在生成副本的那台机器上运行 "
            f"python -m chart_workflow.state snapshot-register 登记(登记文件随记账文件进 git);"
            f"另一台机器把那一份副本原样拷过来,不要自己重新生成")
    fp = fingerprint(ddir)
    if fp["sha"] != lock["current"]["sha"]:
        raise SnapshotMismatch(mismatch_message(lock, fp, ddir))
    _VERIFIED.add(key)
