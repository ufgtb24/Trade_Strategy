"""app 入口装配工厂:把每个 path2_apps app 手写的 analyze/matches/PATTERN_DAG
三件套收口成一个闭包工厂,消除跨 app 的样板重复。

走势-无关:只依赖 path2.dag.engine 的纯函数 analyze,不绑定任何具体走势。
每个 app 把自己的 default_params 与 build_pattern 喂进来,工厂返回绑定了
该 app 私有绑定的 analyze/matches + 默认参数实例 PATTERN_DAG。
"""
from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from path2.dag.engine import analyze as _engine_analyze
from path2.dag.spec import PatternSpec


def make_app(
    *,
    default_params: Callable[[], object],
    build_pattern: Callable[[object], PatternSpec],
):
    """装配一个 app 的模块级入口三件套。

    参数:
        default_params: 零参 callable,返回默认 Params 实例(如 ``Params.default``)。
        build_pattern: 把 Params 造为 PatternSpec 的工厂(各 app 自己的拓扑)。

    返回:
        ``(analyze, matches, pattern_dag)``:
        - ``analyze(df, params=None)``: params 缺省时调 default_params(),调引擎匹配。
        - ``matches(df, params=None)``: analyze 是否有命中。
        - ``pattern_dag``: build_pattern(default_params()) 的默认参数实例(discovery 入口)。

    语义:analyze 每次重新调 default_params()(保持原手写语义,不缓存实例);
    pattern_dag 用一次 default_params() 预算存常量。analyze 每次调 build_pattern
    (不缓存预算结果)——这是 scripts/gate_burst_2x2.py monkeypatch 兼容性的前提:
    patch 模块全局 detector 后,build_pattern 运行时读到新值。
    """
    pattern_dag = build_pattern(default_params())

    def analyze(df: pd.DataFrame, params: Optional[object] = None):
        p = params or default_params()
        return _engine_analyze(build_pattern(p), df, p)

    def matches(df: pd.DataFrame, params: Optional[object] = None) -> bool:
        return len(analyze(df, params).matches) > 0

    return analyze, matches, pattern_dag
