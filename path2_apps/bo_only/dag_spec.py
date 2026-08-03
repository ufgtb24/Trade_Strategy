"""bo_only dag 声明 — 单节点 BODetector,无边。

拓扑:
  节点: bo(孤立 node,无边)
  边:   无

提供 path2_web 协议:eval_meta(end_node=bo, head_buffer=max(vol_baseline_period, total_window))。
"""
from __future__ import annotations

from typing import Optional

from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.stdlib.app import make_app
from path2.atoms.breakout import BODetector

from .params import Params, load_params, DEFAULT_YAML_PATH    # noqa: F401 re-export


def build_pattern(params: Params) -> PatternSpec:
    """单节点 bo dag。"""
    nodes = (
        NodeSpec("bo",
                 BODetector(**params.bo_kwargs()),
                 render_grid="price"),
    )
    edges = ()
    return PatternSpec(
        pattern_id="bo_only",
        nodes=nodes, edges=edges,
    )


analyze, matches, PATTERN_DAG = make_app(default_params=Params.default, build_pattern=build_pattern)


def eval_meta(params: Optional[Params] = None) -> dict:
    """评估元数据:bo 即买点,head_buffer = bo 自身 rolling lookback 最大值。"""
    p = params or Params.default()
    return {
        "end_node": "bo",
        "head_buffer_trading_days": max(
            p.bo.vol_baseline_period,
            p.bo.total_window,
        ),
    }
