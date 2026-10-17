"""命令:生成截断副本——把全量行情截到 2025-12-31,复制成独立目录。

    uv run python -m chart_workflow.snapshot [--src datasets/pkls] [--dst datasets/pkls_until_20251231]
                                              [--cutoff 2025-12-31] [--rebuild]

逐个读 src/*.pkl:去 tz、按日期排序、只留 index ≤ cutoff 的行,原样(列不变)写到 dst/<同名>.pkl;
截完为空的不写,计入 n_skipped_empty。写清单文件 dst/SNAPSHOT.json:
{
  "schema": "chart_workflow.snapshot/1",
  "cutoff": "2025-12-31", "src": "<src 绝对路径>", "created_at": "YYYY-MM-DDTHH:MM:SS",
  "n_files": 5700, "n_skipped_empty": 12, "max_date": "2025-12-31",
  "files": {"AAPL.pkl": {"src_size": 123, "src_mtime_ns": 456, "n_rows": 1062, "last_date": "2025-12-31"}}
}
写完再逐个重读核对最后一天 ≤ cutoff,有任何一个不满足就删掉整个新目录并报错。
全程先写到 dst 同级的临时目录,全部成功后再换名;dst 已存在时不加 --rebuild 就拒绝。

红线:cutoff 不得晚于 loader.HARD_END(代码常量);全程只打印计数和路径,不打印任何行内容。
这是 chart_workflow 里唯一允许读全量 datasets/pkls/ 的模块;它只读源目录,不改其中任何文件。
副本不进 git,每台机器各生成一次。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from chart_workflow.config import resolve_path
from chart_workflow.loader import HARD_END, SNAPSHOT_FILE, SNAPSHOT_SCHEMA

DEFAULT_SRC = "datasets/pkls"
DEFAULT_DST = "datasets/pkls_until_20251231"


class SnapshotError(RuntimeError):
    pass


def _cut(df: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    if getattr(df.index, "tz", None) is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    return df[df.index <= pd.Timestamp(cutoff)]


def _write_all(src: Path, out: Path, cutoff: str, verbose: bool) -> dict:
    files: dict[str, dict] = {}
    skipped = 0
    paths = sorted(src.glob("*.pkl"))
    for k, p in enumerate(paths):
        st = p.stat()
        df = _cut(pd.read_pickle(p), cutoff)
        if len(df) == 0:
            skipped += 1
            continue
        df.to_pickle(out / p.name)
        files[p.name] = {"src_size": st.st_size, "src_mtime_ns": st.st_mtime_ns,
                         "n_rows": int(len(df)), "last_date": df.index[-1].strftime("%Y-%m-%d")}
        if verbose and (k + 1) % 500 == 0:
            print(f"[snapshot] {k + 1}/{len(paths)}")
    return {
        "schema": SNAPSHOT_SCHEMA, "cutoff": cutoff, "src": str(src.resolve()),
        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "n_files": len(files), "n_skipped_empty": skipped,
        "max_date": max((f["last_date"] for f in files.values()), default=None),
        "files": files,
    }


def _verify(out: Path, man: dict) -> list[str]:
    """重读每个写出的文件:最后一天 ≤ cutoff、行数与清单一致;清单里的 last_date 也 ≤ cutoff。"""
    bad = []
    cutoff = pd.Timestamp(man["cutoff"])
    on_disk = {p.name for p in out.glob("*.pkl")}
    if on_disk != set(man["files"]):
        bad.append(f"文件集合与清单不一致({len(on_disk)} vs {len(man['files'])})")
    for name, info in man["files"].items():
        if info["last_date"] > man["cutoff"]:
            bad.append(name)
            continue
        idx = pd.read_pickle(out / name).index
        if len(idx) != info["n_rows"] or (len(idx) and idx.max() > cutoff):
            bad.append(name)
    return bad


def build_snapshot(src, dst, cutoff: str = HARD_END, rebuild: bool = False,
                   verbose: bool = True) -> dict:
    """生成截断副本,返回清单。任何一步不过 → SnapshotError(新目录不留下)。"""
    src, dst = Path(src), Path(dst)
    if cutoff > HARD_END:
        raise SnapshotError(f"截断终点 {cutoff} 晚于 {HARD_END},拒绝")
    pd.Timestamp(cutoff)                                  # 不是日期就抛
    if not src.is_dir():
        raise SnapshotError(f"源目录不存在: {src}")
    if dst.resolve() == src.resolve():
        raise SnapshotError("目标目录不能是源目录")
    if dst.exists() and not rebuild:
        raise SnapshotError(f"目标目录已存在: {dst}(要重建加 --rebuild)")
    tmp = dst.parent / f".{dst.name}.tmp-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        man = _write_all(src, tmp, cutoff, verbose)
        (tmp / SNAPSHOT_FILE).write_text(json.dumps(man, ensure_ascii=False, indent=1))
        bad = _verify(tmp, man)
        if bad:
            raise SnapshotError(f"核对失败,有 {len(bad)} 个文件的最后一天晚于 {cutoff} "
                                f"或与清单不符: {bad[:5]}")
        if dst.exists():
            old = dst.parent / f".{dst.name}.old-{os.getpid()}"
            dst.rename(old)
            tmp.rename(dst)
            shutil.rmtree(old)
        else:
            tmp.rename(dst)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return man


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="生成截到训练段末日的行情副本")
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--dst", default=DEFAULT_DST)
    ap.add_argument("--cutoff", default=HARD_END)
    ap.add_argument("--rebuild", action="store_true", help="目标目录已存在时重建")
    args = ap.parse_args(argv)
    src, dst = resolve_path(args.src), resolve_path(args.dst)
    try:
        man = build_snapshot(src, dst, args.cutoff, args.rebuild)
    except (SnapshotError, ValueError) as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)
    print(f"写入 {dst}:{man['n_files']} 个文件,截完为空跳过 {man['n_skipped_empty']} 个,"
          f"最后一天 {man['max_date']}(截断终点 {man['cutoff']})")


if __name__ == "__main__":
    main()
