"""训练段副本的指纹:按当前内容重算并与指纹清单核对(默认,只读);或为已有副本补写指纹清单。

    uv run python scripts/data/snapshot_fingerprint.py

参数在 main() 顶部声明(无 argparse,遵循入口规范)。指纹怎么算、清单放哪见 path2_web/snapshot_fingerprint.py。

- WRITE = False(默认):重算指纹,与副本里清单记的比对,打印指纹和比对结果。对得上退出码 0;
  对不上 1(列出增、删、改的文件);没有清单 2。两台机器各跑一次,输出相同就是同一份副本。
- WRITE = True:为还没有清单的副本补写清单,只新增清单这一个文件,不动任何 pkl。已有清单时不重写:
  与当前内容一致就什么都不做(退出码 0),不一致就拒绝(退出码 1)——副本内容变了,先查清楚再说。
  生成新副本时 make_train_snapshot.py 已顺带写好清单,不用再跑这个。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

from path2_web.snapshot_fingerprint import (  # noqa: E402
    MANIFEST_NAME, ManifestMissing, compute_manifest, read_manifest, write_manifest,
)

_SHOW = 5          # 增、删、改各最多列几个文件名


def diff_files(recorded: dict, current: dict) -> dict:
    """两份 {文件名: sha256} 的差别:{added, removed, changed},各为排好序的文件名列表。"""
    return {
        "added": sorted(set(current) - set(recorded)),
        "removed": sorted(set(recorded) - set(current)),
        "changed": sorted(n for n in set(current) & set(recorded) if current[n] != recorded[n]),
    }


def check(snapshot_dir) -> tuple[int, list[str]]:
    """重算指纹并与清单比对,返回 (退出码, 输出行)。退出码:0 一致,1 不一致,2 没有清单。"""
    current = compute_manifest(snapshot_dir)
    lines = [f"指纹 {current['fingerprint']}", f"文件 {current['n_files']} 个"]
    try:
        recorded = read_manifest(snapshot_dir)
    except ManifestMissing as e:
        return 2, lines + [f"没有清单:{e}"]
    if recorded["fingerprint"] == current["fingerprint"]:
        return 0, lines + [f"与清单 {MANIFEST_NAME} 一致"]
    lines.append(f"与清单不一致:清单记的是 {recorded['fingerprint']}")
    for kind, names in diff_files(recorded["files"], current["files"]).items():
        if names:
            more = f" 等 {len(names)} 个" if len(names) > _SHOW else ""
            lines.append(f"  {kind}: {', '.join(names[:_SHOW])}{more}")
    return 1, lines


def backfill(snapshot_dir) -> tuple[int, list[str]]:
    """为没有清单的副本补写清单,返回 (退出码, 输出行)。已有清单只核对、不重写。"""
    try:
        read_manifest(snapshot_dir)
    except ManifestMissing:
        manifest = write_manifest(snapshot_dir)
        return 0, [f"已写 {MANIFEST_NAME}:指纹 {manifest['fingerprint']},文件 {manifest['n_files']} 个"]
    code, lines = check(snapshot_dir)
    if code == 0:
        return 0, ["已有清单,与当前内容一致,未改动"] + lines
    return 1, ["已有清单,与当前内容不一致,拒绝重写"] + lines


def main() -> None:
    # ===== 参数(在此处直接改) =====
    SNAPSHOT_DIR = REPO / "datasets" / "pkls_until_20251231"   # 训练段副本(path2_web 配置 view_dataset_dir)
    WRITE = False                                               # True = 为没有清单的副本补写清单
    # ================================
    if not SNAPSHOT_DIR.is_dir():
        print(f"错误:副本目录不存在 {SNAPSHOT_DIR}", file=sys.stderr)
        sys.exit(2)
    code, lines = (backfill if WRITE else check)(SNAPSHOT_DIR)
    print("\n".join(lines))
    sys.exit(code)


if __name__ == "__main__":
    main()
