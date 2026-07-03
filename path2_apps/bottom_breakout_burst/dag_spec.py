# path2_apps/bottom_breakout_burst/dag_spec.py
"""bottom_breakout_burst dag 声明 — 3 节点 + 1 边 + anchor_field。

拓扑:
  节点: bo(孤立 role，无边) / burst(consumes bo，嵌套 event) / tb(consumes bo)
  边:   burst.last_bo → tb  (TemporalEdge, anchor_field="anchor_bo_id")

约束归宿:
  ② len(bo 串) >= burst.min_bos          -> BurstDetector(min_bos)
  ③ 首 bo.drought >= burst.first_drought_min   -> burst where W.attr("first_drought")
  ⑤ distinct_pk >= burst.distinct_pk_min       -> burst where W.attr("distinct_pk")
  ⑥ Any vol_ratio >= burst.vol_spike_min       -> burst where W.attr("max_bar_vol_ratio")
  ⑦ 末 bo 后回踩,身份锚定                -> TemporalEdge(Child(burst,"last_bo"), tb,
                                           anchor_field="anchor_bo_id")
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, Child
from path2.dag.spec import PatternSpec
from path2.dag.engine import analyze as _analyze
from path2.dag import where as W
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback import ThrowbackDetector

from .params import Params, load_params, DEFAULT_YAML_PATH    # noqa: F401 re-export 供 web worker(registry 注册 .dag_spec 而非包 init)


def build_pattern(params: Params) -> PatternSpec:
    """参数化声明工厂:给定 params 造 PatternSpec。detector 实例 + where 阈值在此闭合。"""
    nodes = (
        # bo 孤立 role：无边，残缺 match 由 analyze 出口过滤
        # render_grid='price': bo 主三角钉 K线主图; pk 通过 referenced_points 字段
        # 作为卫星 marker 画在各自 bar 位置 (见 design §正面回答 Q2)
        NodeSpec("bo",
                 BODetector(**params.bo_kwargs()),
                 render_grid="price"),
        # ②③⑤⑥ 突破爆发(BurstDetector 消费 bo 流，嵌套 event)
        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 where=(("first_drought", W.attr("first_drought", ">=", params.burst.first_drought_min)),  # ③
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.burst.distinct_pk_min)),        # ⑤
                        ("vol_spike",     W.attr("max_bar_vol_ratio", ">=", params.burst.vol_spike_min))),   # ⑥
                 consumes_stream="bo"),
        # ⑦ 末突破后回踩(ThrowbackDetector 消费 bo 流：吃 BOEvent，不能吃 BurstEvent)
        NodeSpec("tb",
                 ThrowbackDetector(**params.throwback_kwargs()),
                 consumes_stream="bo"),
    )
    edges = (
        # ⑦ 突破后回踩：锚【末 bo】——anchor_field 使 tb.anchor_bo_id == last_bo.event_id
        TemporalEdge(
            Child("burst", "last_bo"), "tb",
            # max_gap 与 ThrowbackDetector(max_start_gap=...) 共用同一 SSoT (tb.max_start_gap)
            min_gap=1, max_gap=params.tb.max_start_gap,
            anchor_field="anchor_bo_id",
        ),
    )
    return PatternSpec(
        pattern_id="bottom_burst",
        nodes=nodes, edges=edges,
    )


PATTERN_DAG = build_pattern(Params.default())    # 模块级常量:to_topology / 未来发现入口(schema 与 params 无关)


def analyze(df: pd.DataFrame, params: Optional[Params] = None):
    """库引擎 analyze:工厂造 spec(闭合 params)+ 引擎匹配。返回 path2.dag.result.AnalysisResult。"""
    p = params or Params.default()
    return _analyze(build_pattern(p), df, p)


def matches(df: pd.DataFrame, params: Optional[Params] = None) -> bool:
    return len(analyze(df, params).matches) > 0


def eval_meta(params: Optional[Params] = None) -> dict:
    """评估元数据(path2_web 可选协议):end_role(买点 role)+ 首部缓冲交易日数。

    head_buffer = 本 app 全部 rolling lookback 字段的最大值——参数改动自动传导,
    不手写常量(硬编码常量不随参数变化的教训)。
    """
    p = params or Params.default()
    return {
        "end_role": "tb",
        "head_buffer_trading_days": max(
            p.bo.vol_baseline_period,
            p.burst.vol_baseline_period,
            p.tb.atr_window,
            p.bo.total_window,
        ),
    }
