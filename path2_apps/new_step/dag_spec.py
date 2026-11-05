# path2_apps/new_step/dag_spec.py
"""new_step dag 声明:阶跃后站上新平台,逐日判断企稳买。

pattern 的意思(取自标注里 new_step 的定义与样本):一根或几根放量大涨的 K 线把股价从旧平台抬到新平台;
阶跃之后逐日判断,没追涨、波动小、守在新平台低点之上、企稳了就买。「底部平稳」「触底放量」只是加分项,
不进条件。

拓扑(与 bottom_burst 同一副骨架,只换 burst 的条件):
  节点: bo(孤立 node) / burst(consumes bo,嵌套 event) / tb(consumes burst) / tb_seg(tb 的企稳段)
  边:   burst.last_bo → tb  (TemporalEdge, anchor_field="anchor_bo_id")

约束归宿:
  阶跃 = 一串密集的突破                     -> BurstDetector(gap_max, min_bos)
  站上新平台:越过的不同峰数 >= distinct_pk_min -> burst where W.attr("distinct_pk")
  阶跃放量:串内最大单根量比 >= vol_spike_min    -> burst where W.attr("max_bar_vol_ratio")
  阶跃后逐日企稳、守住支撑、不追涨             -> ThrowbackDetectorV4 的企稳段(买点 = tb.segments)
"""
from __future__ import annotations

from typing import Optional

from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, Child
from path2.dag.spec import PatternSpec
from path2.stdlib.app import make_app
from path2.dag import where as W
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback_v4 import ThrowbackDetectorV4, ThrowbackSegmentV4

from .params import Params, load_params, DEFAULT_YAML_PATH    # noqa: F401 re-export 供 web worker(registry 注册 .dag_spec 而非包 init)


def build_pattern(params: Params) -> PatternSpec:
    """参数化声明工厂:给定 params 造 PatternSpec。detector 实例 + where 阈值在此闭合。"""
    det = BODetector(**params.bo_kwargs())
    nodes = (
        NodeSpec("bo", det, produces_stream="bo", render_grid="price"),
        NodeSpec("pk", det, produces_stream="pk", solve=False, render_grid="price"),
        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 where=(("distinct_pk", W.attr("distinct_pk", ">=", params.burst.distinct_pk_min)),
                        ("vol_spike",   W.attr("max_bar_vol_ratio", ">=", params.burst.vol_spike_min))),
                 consumes_stream="bo",
                 children={"members": "bo"}),
        NodeSpec("tb",
                 ThrowbackDetectorV4(**params.throwback_kwargs()),
                 consumes_stream="burst",
                 children={"segments": "tb_seg"}),
        NodeSpec("tb_seg", event_cls=ThrowbackSegmentV4),
    )
    edges = (
        # 阶跃之后才企稳:锚阶跃那串的末根突破;max_gap 与状态机的扫描预算共用 tb.max_span
        TemporalEdge(
            Child("burst", "last_bo"), "tb",
            min_gap=1, max_gap=params.tb.max_span,
            anchor_field="anchor_bo_id",
        ),
    )
    return PatternSpec(pattern_id="new_step", nodes=nodes, edges=edges)


analyze, has_hit, PATTERN_DAG = make_app(default_params=Params.default, build_pattern=build_pattern)


def eval_meta(params: Optional[Params] = None) -> dict:
    """评估元数据(path2_web 协议):买点 node = tb 的企稳段;首部缓冲 = 全部滚动回看窗的最大值。"""
    p = params or Params.default()
    return {
        "end_node": "tb.segments",
        "head_buffer_trading_days": max(
            p.bo.vol_baseline_period,
            p.burst.vol_baseline_period,
            p.tb.vol_window,
            p.bo.total_window,
        ),
    }
