"""票 06 的 pytest 插件：测试里写死读 datasets/pkls 的，改读训练段副本，测试文件不改。票 04 那份只管 test_multivar_equiv，这里扩到全套。

两条路：测试模块里的目录常量 PKL_DIR、DATA 换成副本；内置 open 的路径里 datasets/pkls/ 换成副本。
别的路子（比如经配置取 dataset_dir）不管，会撞上护栏 evidence/04/wall/sitecustomize.py 的拒绝并记日志。
"""
import builtins
import os
from pathlib import Path

COPY = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls_until_20251231")
_open = builtins.open


def _redirected_open(file, *args, **kwargs):
    if isinstance(file, (str, os.PathLike)):
        s = os.fspath(file)
        if isinstance(s, str) and "datasets/pkls/" in s:
            file = s.replace("datasets/pkls/", "datasets/pkls_until_20251231/")
    return _open(file, *args, **kwargs)


def pytest_configure(config):
    builtins.open = _redirected_open


def pytest_collection_modifyitems(items):
    for it in items:
        mod = getattr(it, "module", None)
        for name in ("PKL_DIR", "DATA"):
            v = getattr(mod, name, None)
            if isinstance(v, Path) and v.as_posix().rstrip("/").endswith("datasets/pkls"):
                setattr(mod, name, COPY)
