# bb_pk dag 声明 — 多流 bo(pk 显示)+ burst + tb(拓扑同 bb_v1)。
# 与 bb_v1 唯一区别:同一 BODetector 实例喂两个 node(bo 匹配流 + pk 显示流)。
# pk node: solve=False 只显示不参与匹配;render_grid='price' 钉主图、不占副图。
from __future__ import annotations
from typing import Optional
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, Child
from path2.dag.spec import PatternSpec
from path2.dag import where as W
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback_v1 import ThrowbackDetectorV1
from path2.stdlib.app import make_app
from .params import Params, load_params, DEFAULT_YAML_PATH  # noqa: F401


def build_pattern(params: Params) -> PatternSpec:
    det = BODetector(**params.bo_kwargs())
    nodes = (
        NodeSpec("bo", det, produces_stream="bo", render_grid="price"),
        NodeSpec("pk", det, produces_stream="pk", solve=False, render_grid="price"),
        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 where=(("first_drought", W.attr("first_drought", ">=", params.burst.first_drought_min)),
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.burst.distinct_pk_min)),
                        ("vol_spike",     W.attr("max_bar_vol_ratio", ">=", params.burst.vol_spike_min)),
                        ("peak_age",      W.attr("peak_age_max", ">=", params.burst.peak_age_min))),
                 consumes_stream="bo",
                 children={"members": "bo"}),
        NodeSpec("tb",
                 ThrowbackDetectorV1(**params.throwback_kwargs()),
                 where=(() if params.tb.max_day_drop_pct is None else
                        (("day_drop", W.attr("max_day_drop", "<", params.tb.max_day_drop_pct)),)),
                 consumes_stream="burst"),
    )
    edges = (
        TemporalEdge(Child("burst", "last_bo"), "tb",
                     min_gap=1, max_gap=params.tb.max_span,
                     anchor_field="anchor_bo_id"),
    )
    return PatternSpec(pattern_id="bb_pk", nodes=nodes, edges=edges)


analyze, matches, PATTERN_DAG = make_app(default_params=Params.default, build_pattern=build_pattern)


def eval_meta(params: Optional[Params] = None) -> dict:
    p = params or Params.default()
    return {
        "end_node": "tb",
        "head_buffer_trading_days": max(
            p.bo.vol_baseline_period, p.burst.vol_baseline_period,
            p.tb.vol_window, p.bo.total_window),
    }
