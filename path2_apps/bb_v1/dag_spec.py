# path2_apps/bb_v1/dag_spec.py
"""bb_v1 dag 声明 — 3 节点 + 1 边 + anchor_field(V1 throwback 完整备份)。

结构与 bottom_burst 完全相同,唯一区别:tb node 用 V1 ThrowbackDetectorV1
(throwback_v1.py),tb 参数 = 2026-08-25 首段状态机重写默认值。
用途:V1 时代可运行的完整 app 备份——可扫描、可与 V2 容器版(bottom_burst)对比。

拓扑:
  节点: bo(孤立 node，无边) / burst(consumes bo，嵌套 event) / tb(consumes burst)
  边:   burst.last_bo → tb  (TemporalEdge, anchor_field="anchor_bo_id")

约束归宿:
  ② len(bo 串) >= burst.min_bos          -> BurstDetector(min_bos)
  ③ 首 bo.drought >= burst.first_drought_min   -> burst where W.attr("first_drought")
  ⑤ distinct_pk >= burst.distinct_pk_min       -> burst where W.attr("distinct_pk")
  ⑥ Any vol_ratio >= burst.vol_spike_min       -> burst where W.attr("max_bar_vol_ratio")
  ⑦ 末 bo 后回踩,身份锚定                -> TemporalEdge(Child(burst,"last_bo"), tb,
                                           anchor_field="anchor_bo_id")
  ⑧ 簇内某 bo 距其突破峰 >= peak_age_min -> burst where W.attr("peak_age_max")
  ⑨ 回踩段单日跌幅 < tb.max_day_drop_pct -> tb where W.attr("max_day_drop")
"""
from __future__ import annotations

from typing import Optional

from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, Child
from path2.dag.spec import PatternSpec
from path2.stdlib.app import make_app
from path2.dag import where as W
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback_v1 import ThrowbackDetectorV1

from .params import Params, load_params, DEFAULT_YAML_PATH    # noqa: F401 re-export 供 web worker(registry 注册 .dag_spec 而非包 init)


def build_pattern(params: Params) -> PatternSpec:
    """参数化声明工厂:给定 params 造 PatternSpec。detector 实例 + where 阈值在此闭合。"""
    det = BODetector(**params.bo_kwargs())
    nodes = (
        # bo 孤立 node：无边，残缺 match 由 analyze 出口过滤
        # render_grid='price': bo 主三角钉 K线主图; pk 由独立 pk node(孤立显示)承载
        NodeSpec("bo",
                 det,
                 produces_stream="bo",
                 render_grid="price"),
        # pk 孤立显示 node:同一 detector 喂 bo+pk 两 node(兄弟机制一次 detect 填满两流)
        NodeSpec("pk", det, produces_stream="pk", solve=False, render_grid="price"),
        # ②③⑤⑥⑧ 突破爆发(BurstDetector 消费 bo 流，嵌套 event)
        # children 声明:members 槽由独立 bo node 物化(与 bottom_burst 同款迁移)
        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 where=(("first_drought", W.attr("first_drought", ">=", params.burst.first_drought_min)),  # ③
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.burst.distinct_pk_min)),        # ⑤
                        ("vol_spike",     W.attr("max_bar_vol_ratio", ">=", params.burst.vol_spike_min)),      # ⑥
                        ("peak_age",      W.attr("peak_age_max", ">=", params.burst.peak_age_min))),           # ⑧
                 consumes_stream="bo",
                 children={"members": "bo"}),
        # ⑦⑨ 末突破后回踩(V1 首段即停状态机,消费 burst 流,锚 last_bo);⑨ 资格型 where:回踩段单日跌幅
        NodeSpec("tb",
                 ThrowbackDetectorV1(**params.throwback_kwargs()),
                 where=(() if params.tb.max_day_drop_pct is None else
                        (("day_drop", W.attr("max_day_drop", "<", params.tb.max_day_drop_pct)),)),
                 consumes_stream="burst"),
    )
    edges = (
        # ⑦ 突破后回踩：锚【末 bo】——anchor_field 使 tb.anchor_bo_id == last_bo.event_id(标量相等)
        # (V1 事件亦有 anchor_bo_id 标量字段,契约与 bottom_burst 相同)
        TemporalEdge(
            Child("burst", "last_bo"), "tb",
            # max_gap 与 ThrowbackDetectorV1(max_span=...) 共用同一 SSoT (tb.max_span)
            min_gap=1, max_gap=params.tb.max_span,
            anchor_field="anchor_bo_id",
        ),
    )
    return PatternSpec(
        pattern_id="bb_v1",
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
        "end_node": "tb",
        "head_buffer_trading_days": max(
            p.bo.vol_baseline_period,
            p.burst.vol_baseline_period,
            p.tb.vol_window,
            p.bo.total_window,
        ),
    }
