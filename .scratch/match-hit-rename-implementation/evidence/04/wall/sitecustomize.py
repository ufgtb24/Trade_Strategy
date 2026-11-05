"""票 04 数据墙护栏（只在本票跑测试时经 PYTHONPATH 加载）：任何进程打开或列 datasets/pkls 都拒绝并记日志。"""
import os
import sys
_LOG = os.environ.get("WALL_LOG")
_open = open


def _hook(event, args):
    if event not in ("open", "os.scandir", "os.listdir"):
        return
    p = args[0] if args else None
    if not isinstance(p, (str, bytes, os.PathLike)):
        return
    s = os.fspath(p)
    if isinstance(s, bytes):
        s = s.decode("utf-8", "replace")
    if "datasets/pkls/" in s or s.rstrip("/").endswith("datasets/pkls"):
        if _LOG and not s.startswith(_LOG):
            with _open(_LOG, "a", encoding="utf-8") as f:
                f.write(f"{event}\t{s}\t{' '.join(sys.argv[:3])}\n")
        raise PermissionError(f"数据墙：拒绝读 {s}")


if _LOG:
    sys.addaudithook(_hook)
