"""生成训练段行情副本:把完整行情截到训练段末日,复制成独立目录(网页 path2_web 与标注工具只读这份)。

    uv run python scripts/data/make_train_snapshot.py

参数在 main() 顶部声明(无 argparse,遵循入口规范)。

逐个读 SRC/*.pkl:去 tz、按日期排序、只留日期 ≤ CUTOFF 的行,原样(列不变)写到 DST/<同名>.pkl;
截完为空的不写,只计数。全程先写到 DST 同级的临时目录,写完逐个重读核对(最后一天 ≤ CUTOFF、行数对得上),
全部通过才换名成 DST;任何一步失败就删掉临时目录、DST 原样不动。DST 已存在时 REBUILD = False 就拒绝。
CUTOFF 不得晚于训练段末日(path2_web.data.TRAIN_END)。只读 SRC,不改其中任何文件;只打印计数和路径。

副本不进 git(datasets/ 整个被忽略)。两台机器都要用时,只在一台上生成,原样拷到另一台——两台下载的原始行情
不同,复权也会随时间变,各自生成就不是同一份。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

from path2_web.data import TRAIN_END  # noqa: E402


def _cut(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """去 tz、按日期排序、只留日期 ≤ cutoff 的行。"""
    if getattr(df.index, "tz", None) is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    return df[df.index <= cutoff]


def build(src: Path, dst: Path, cutoff: str, rebuild: bool) -> dict:
    """生成副本,返回 {n_files, n_skipped_empty, max_date}。不满足前提或核对失败 → RuntimeError。"""
    if cutoff > TRAIN_END:
        raise RuntimeError(f"截断终点 {cutoff} 晚于训练段末日 {TRAIN_END},拒绝")
    cut_ts = pd.Timestamp(cutoff)                          # 不是日期就抛
    if not src.is_dir():
        raise RuntimeError(f"源目录不存在: {src}")
    if dst.resolve() == src.resolve():
        raise RuntimeError("目标目录不能是源目录")
    if dst.exists() and not rebuild:
        raise RuntimeError(f"目标目录已存在: {dst},不覆盖(确实要重建把 REBUILD 设成 True)")

    tmp = dst.parent / f".{dst.name}.tmp-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        written: dict[str, tuple[int, pd.Timestamp]] = {}
        skipped = 0
        paths = sorted(src.glob("*.pkl"))
        for k, p in enumerate(paths):
            df = _cut(pd.read_pickle(p), cut_ts)
            if len(df) == 0:
                skipped += 1
                continue
            df.to_pickle(tmp / p.name)
            written[p.name] = (len(df), df.index[-1])
            if (k + 1) % 500 == 0:
                print(f"[make_train_snapshot] {k + 1}/{len(paths)}")

        # 重读核对:文件集合一致、行数一致、最后一天 ≤ cutoff
        bad = []
        if {p.name for p in tmp.glob("*.pkl")} != set(written):
            bad.append("文件集合与写入记录不一致")
        for name, (n_rows, _) in written.items():
            idx = pd.read_pickle(tmp / name).index
            if len(idx) != n_rows or (len(idx) and idx.max() > cut_ts):
                bad.append(name)
        if bad:
            raise RuntimeError(f"核对失败 {len(bad)} 项(最后一天晚于 {cutoff} 或行数不符): {bad[:5]}")

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
    max_date = max((d for _, d in written.values()), default=None)
    return {"n_files": len(written), "n_skipped_empty": skipped,
            "max_date": max_date.strftime("%Y-%m-%d") if max_date is not None else None}


def main() -> None:
    # ===== 参数(在此处直接改) =====
    SRC = REPO / "datasets" / "pkls"                       # 完整行情
    DST = REPO / "datasets" / "pkls_until_20251231"        # 副本(path2_web 配置 view_dataset_dir 指向它)
    CUTOFF = "2025-12-31"                                  # 截断终点,不得晚于训练段末日
    REBUILD = False                                        # DST 已存在时是否重建
    # ================================
    try:
        out = build(SRC, DST, CUTOFF, REBUILD)
    except RuntimeError as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)
    print(f"[make_train_snapshot] 写入 {DST}:{out['n_files']} 个文件,截完为空跳过 {out['n_skipped_empty']} 个,"
          f"最后一天 {out['max_date']}(截断终点 {CUTOFF})")


if __name__ == "__main__":
    main()
