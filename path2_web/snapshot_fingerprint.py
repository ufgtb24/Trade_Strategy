"""训练段副本的数据指纹:两台机器的标注要能确认看的是同一根 K 线。

指纹只由副本目录里的 *.pkl 决定(文件名 + 内容):逐个文件算 sha256,再把按文件名排好序的
「文件名、文件哈希」整体算一次 sha256,就是副本的指纹。改动任一个 pkl 的一个字节、增删或改名一个 pkl,
指纹都会变。目录里别的文件(本模块写的指纹清单、旧工具留下的 SNAPSHOT.json、同步工具的隐藏文件)
不影响 K 线,不进指纹——指纹覆盖的正好是按 *.pkl 列出的那批股票文件。

指纹清单 FINGERPRINT.json 写在副本目录里:scripts/data/make_train_snapshot.py 生成副本时顺带写入;
已有副本用 scripts/data/snapshot_fingerprint.py 补写(只新增这一个文件,不动任何 pkl),同一脚本默认
按当前内容重算并与清单核对,供两台机器自测。清单名不以 .pkl 结尾:按 *.pkl 列股票、按 <代码>.pkl
读行情的地方都不会把它当成股票。清单内容只由数据决定(不记生成时间、机器),不算登记、不记账。

- read_fingerprint(dir):读清单里记的指纹(不重算,快),给标注核对所用的副本;没有清单 → ManifestMissing。
  只读清单意味着:清单在、pkl 却被改过或拷缺了,它看不出来——这由核对命令(按内容重算)兜底。
- compute_manifest(dir):按当前内容重算;write_manifest(dir):重算并写清单。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

MANIFEST_NAME = "FINGERPRINT.json"          # 指纹清单的文件名(不得以 .pkl 结尾)
SCHEMA = "path2_web.snapshot_fingerprint/1"

_HEX64 = re.compile(r"[0-9a-f]{64}")


class ManifestMissing(FileNotFoundError):
    """副本目录里没有指纹清单。"""


def _file_sha256(path: Path) -> str:
    """一个文件内容的 sha256(十六进制),按 1 MiB 分块读。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_manifest(snapshot_dir) -> dict:
    """按副本当前内容算指纹清单:{schema, fingerprint, n_files, files: {文件名: sha256}}。

    只算目录下(不含子目录)的 *.pkl 文件。目录不存在 → FileNotFoundError。
    """
    d = Path(snapshot_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"训练段副本目录不存在: {d}")
    paths = sorted((p for p in d.glob("*.pkl") if p.is_file()), key=lambda p: p.name)
    files = {p.name: _file_sha256(p) for p in paths}
    h = hashlib.sha256()
    for name, digest in files.items():
        h.update(f"{name}\t{digest}\n".encode("utf-8"))
    return {"schema": SCHEMA, "fingerprint": h.hexdigest(), "n_files": len(files), "files": files}


def write_manifest(snapshot_dir) -> dict:
    """按当前内容重算指纹清单并写进副本目录(先写隐藏临时文件再换名),返回清单。不动任何 pkl。"""
    d = Path(snapshot_dir)
    manifest = compute_manifest(d)
    tmp = d / f".{MANIFEST_NAME}.tmp-{os.getpid()}"
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, d / MANIFEST_NAME)
    return manifest


def read_manifest(snapshot_dir) -> dict:
    """读副本目录里的指纹清单。没有清单 → ManifestMissing;格式不对 → ValueError。"""
    path = Path(snapshot_dir) / MANIFEST_NAME
    if not path.is_file():
        raise ManifestMissing(
            f"训练段副本 {Path(snapshot_dir)} 里没有指纹清单 {MANIFEST_NAME}"
            f"(用 scripts/data/snapshot_fingerprint.py 补写)")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA
            or not _HEX64.fullmatch(str(manifest.get("fingerprint")))
            or not isinstance(manifest.get("files"), dict)):
        raise ValueError(f"指纹清单格式不对: {path}")
    return manifest


def read_fingerprint(snapshot_dir) -> str:
    """副本的指纹(64 位十六进制),读清单里记的那个、不重算。没有清单 → ManifestMissing。"""
    return read_manifest(snapshot_dir)["fingerprint"]
