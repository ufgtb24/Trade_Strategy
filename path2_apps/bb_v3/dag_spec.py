# path2_apps/bb_v3/dag_spec.py
"""bb_v3 dag 声明 — 3 节点 + 1 边 + anchor_field(V3 re-entry 多段 throwback)。

结构与 bb_v1 完全相同,唯一区别:tb node 用 V3 ThrowbackDetectorV3
(throwback_v3.py,一 bo 多段 re-entry)。
用途:V3 机制承载 app——可扫描、可与 V1(bb_v1)实证对比 re-entry 是否有益。

拓扑:
  节点: bo(孤立 node,无边) / burst(consumes bo,嵌套 event) / tb(consumes burst)
  边:   burst.last_bo → tb  (TemporalEdge, anchor_field="anchor_bo_id")

约束归宿:
  ② len(bo 串) >= burst.min_bos          -> BurstDetector(min_bos)
  ③ 首 bo.drought >= burst.first_drought_min   -> burst where W.attr("first_drought")
  ⑤ distinct_pk >= burst.distinct_pk_min       -> burst where W.attr("distinct_pk")
  ⑥ Any vol_ratio >= burst.vol_spike_min       -> burst where W.attr("max_bar_vol_ratio")
  ⑦ 末 bo 后回踩,身份锚定                -> TemporalEdge(Child(burst,"last_bo"), tb,
                                           anchor_field="anchor_bo_id")
  ⑧ 簇内某 bo 距其突破峰 >= peak_age_min -> burst where W.attr("peak_age_max")
"""
from __future__ import annotations

from typing import Optional

from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, Child
from path2.dag.spec import PatternSpec
from path2.stdlib.app import make_app
from path2.dag import where as W
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback_v3 import ThrowbackDetectorV3, ThrowbackSegmentV3

from .params import Params, load_params, DEFAULT_YAML_PATH    # noqa: F401 re-export 供 web worker(registry 注册 .dag_spec 而非包 init)


def build_pattern(params: Params) -> PatternSpec:
    """参数化声明工厂:给定 params 造 PatternSpec。detector 实例 + where 阈值在此闭合。"""
    det = BODetector(**params.bo_kwargs())
    nodes = (
        NodeSpec("bo",
                 det,
                 produces_stream="bo",
                 render_grid="price"),
        # pk 孤立显示 node:同一 detector 喂 bo+pk 两 node(兄弟机制一次 detect 填满两流)
        NodeSpec("pk", det, produces_stream="pk", solve=False, render_grid="price"),
        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 where=(("first_drought", W.attr("first_drought", ">=", params.burst.first_drought_min)),  # ③
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.burst.distinct_pk_min)),        # ⑤
                        ("vol_spike",     W.attr("max_bar_vol_ratio", ">=", params.burst.vol_spike_min)),      # ⑥
                        ("peak_age",      W.attr("peak_age_max", ">=", params.burst.peak_age_min))),           # ⑧
                 consumes_stream="bo",
                 children={"members": "bo"}),
        NodeSpec("tb",
                 ThrowbackDetectorV3(**params.throwback_kwargs()),
                 consumes_stream="burst",
                 children={"segments": "tb_seg_v3"}),
        # ★ 子结构 node(归一化回填 event_cls/produced_by,一行声明)
        NodeSpec("tb_seg_v3", event_cls=ThrowbackSegmentV3),
    )
    edges = (
        TemporalEdge(
            Child("burst", "last_bo"), "tb",
            min_gap=1, max_gap=params.tb.max_start_gap,
            anchor_field="anchor_bo_id",
        ),
    )
    return PatternSpec(
        pattern_id="bb_v3",
        nodes=nodes, edges=edges,
    )


analyze, matches, PATTERN_DAG = make_app(default_params=Params.default, build_pattern=build_pattern)


def eval_meta(params: Optional[Params] = None) -> dict:
    """评估元数据(path2_web 可选协议):end_node(买点 node)+ 首部缓冲交易日数。

    head_buffer = 本 app 全部 rolling lookback 字段的最大值——参数改动自动传导,
    不手写常量(硬编码常量不随参数变化的教训)。
    """
    p = params or Params.default()
    return {
        "end_node": "tb.segments",   # 路径协议:买点 = 各段 span bar 并集(与 V2 同);node id 是 tb
        "head_buffer_trading_days": max(
            p.bo.vol_baseline_period,
            p.burst.vol_baseline_period,
            p.tb.atr_window,
            p.bo.total_window,
        ),
    }
