"""gate_burst_2x2 monkeypatch 兼容性实证。

make_app 闭包捕获 bbb 自己的 build_pattern 函数对象,后者运行时读模块全局
BurstDetector(dag_spec.py:44 实例化)。scripts/gate_burst_2x2.py:115 patch
该全局后,analyze 路径应读到 patch —— 用「patch 为抛异常类」证实。
"""
import pandas as pd
import pytest

import path2_apps.bottom_breakout_burst.dag_spec as bbb


class _Boom(Exception):
    pass


def test_analyze_reaches_patched_burst_detector(monkeypatch):
    """patch dag_spec.BurstDetector 为抛异常类后,analyze 应抛 _Boom。

    分析路径 analyze(df) → build_pattern(p)(先于 _engine_analyze 执行)
    → 实例化 BurstDetector(dag_spec.py:44)→ 读到 patch → 抛 _Boom。
    证明 make_app 闭包没有缓存预算结果、运行时走 build_pattern 读最新全局。
    """

    class _Patched:
        def __init__(self, *a, **k):
            raise _Boom

    monkeypatch.setattr(bbb, "BurstDetector", _Patched)
    with pytest.raises(_Boom):
        bbb.analyze(pd.DataFrame())   # build_pattern 先执行 → 实例化被 patch 的 detector
