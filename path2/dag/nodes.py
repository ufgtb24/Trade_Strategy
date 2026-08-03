"""节点模型 —— NodeSpec(node+生产者+一元谓词)。

where(一元,节点)vs satisfies(二元,边)的正交分工是整个设计的脊梁:
  where 读单实例自身属性(drought>=THR、regime=="sideways"、vol>=THR);
  satisfies 读一对实例间关系(gap、包含、否定)。

where 谓词只吃 event 一个参数,无运行时上下文对象:
  K 线回看归 detector(算好字段挂 event 上,见 path2/atoms/throwback.py);
  参数阈值由 build_pattern(params) 闭包闭合;
  跨节点约束归边的 satisfies。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from path2.core import Event

# where 谓词签名:吃已绑候选(单 Event),纯一元。
WherePredicate = Callable[[Event], bool]


@dataclass(frozen=True)
class NodeSpec:
    """拓扑节点 = 一个 node + 自带生产者 detector + 节点级一元谓词。

    node_id:          拓扑唯一键(一身多角用不同 node_id,如 down/side 同
                      TrendSegmentDetector 不同 node)。
    detector:         事件来源。引擎据此跑 run()(app 不手写 run(BODetector(),df));
                      detector.event_cls.class_id 供 to_topology / 面板上色。
    where:            节点级一元谓词 (clause_id, fn) 列表,AND 合取。
    consumes_stream:  detector 输入是 df(None)还是上游某节点流(如 throwback 吃 bo 流)。
    render_grid:      事件主 marker 渲染轴 — 'price' 钉 K线主图,需 event_cls.is_point=True;
                      'time' (默认) 走 sub-grid。详见 .claude/docs/modules/path2_web.md。
    """
    node_id: str
    detector: object
    where: Tuple[Tuple[str, WherePredicate], ...] = ()
    consumes_stream: Optional[str] = None
    render_grid: str = "time"
