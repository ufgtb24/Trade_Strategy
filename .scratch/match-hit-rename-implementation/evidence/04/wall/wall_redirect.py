"""票 04 pytest 插件：把 tune-gates/test_multivar_equiv.py 写死的 datasets/pkls 换成训练段副本（不改测试文件）。"""
from pathlib import Path

COPY = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls_until_20251231")


def pytest_collection_modifyitems(items):
    for it in items:
        mod = getattr(it, "module", None)
        if mod is not None and mod.__name__.endswith("test_multivar_equiv"):
            mod.DATA = COPY
