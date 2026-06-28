"""节点模型 —— NodeSpec(角色+生产者+一元谓词)/ MatchContext。

where(一元,节点)vs satisfies(二元,边)的正交分工是整个设计的脊梁:
  where 读单实例自身属性(drought>=THR、regime=="sideways"、vol>=THR);
  satisfies 读一对实例间关系(gap、包含、否定)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from path2.core import Event

# where 谓词签名:吃已绑候选(单 Event)+ 运行时上下文。
WherePredicate = Callable[[Event, "MatchContext"], bool]


@dataclass(frozen=True)
class NodeSpec:
    """拓扑节点 = 一个角色 + 自带生产者 detector + 节点级一元谓词。

    node_id:          拓扑唯一键(一身多角用不同 node_id,如 down/side 同
                      TrendSegmentDetector 不同角色)。
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


@dataclass(frozen=True)
class MatchContext:
    """where 的求值环境。df 供 throwback 等回看 K 线;bound 供跨节点 where(当前 app 不用)。"""
    df: object
    params: object
    bound: object = None
