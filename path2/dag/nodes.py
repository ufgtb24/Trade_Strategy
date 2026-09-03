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

from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Tuple

from path2.core import Event

# where 谓词签名:吃已绑候选(单 Event),纯一元。
WherePredicate = Callable[[Event], bool]


@dataclass(frozen=True)
class NodeSpec:
    """拓扑节点 = 一个 node + 生产者 + 节点级一元谓词。

    node_id:          拓扑唯一键(一身多角用不同 node_id,如 down/side 同
                      TrendSegmentDetector 不同 node)。
    detector:         事件来源。独立 node 的生产者;子结构 node(被父容器物化,
                      children 引用)必须 None。
    event_cls:        本 node 产出的事件类型。可空——独立 node 反射自
                      stream_schema(detector)[produces_stream](单流即
                      detector.event_cls,多流从 produces 取);子结构 node
                      (无 detector)必须显式声明(node_id == 事件类型注册表
                      反查的旧约定已消灭)。
    produced_by:      子结构 node 的物化来源父 node_id。可空——PatternSpec 归一化
                      自 children 逆映射回填(单父确定/孤儿报错/多父报错)。
    children:         child slot 名 → 子 node_id(声明引用)。子结构 node 只有
                      node_id/event_cls/children 有意义(where/consumes_stream/
                      render_grid 是死字段,PatternSpec 校验拒绝非默认值)。
    where:            节点级一元谓词 (clause_id, fn) 列表,AND 合取。
    consumes_stream:  detector 输入是 df(None)还是上游某节点流。
    produces_stream:  输出取本 detector 的哪条命名流(None = 唯一流)。
                      多流 detector(声明 produces)按此反射 event_cls。
    render_grid:      事件主 marker 渲染轴 — 'price' 钉 K线主图,需 event_cls.is_point=True;
                      'time' (默认) 走 sub-grid。
    solve:            是否参与求解匹配。True(默认)= 进 bound_ids 参与 WCC 求解;
                      False = 只显示不参与匹配(零边 pattern 的孤立 node 用,避免
                      serialize 对每个 match 取 node_index[end_node] 时 KeyError)。
    """
    node_id: str
    detector: Optional[object] = None
    event_cls: Optional[type] = None
    produced_by: Optional[str] = None
    children: Mapping[str, str] = field(default_factory=dict)
    where: Tuple[Tuple[str, WherePredicate], ...] = ()
    consumes_stream: Optional[str] = None
    produces_stream: Optional[str] = None
    render_grid: str = "time"
    solve: bool = True     # 是否参与求解匹配。False = 只显示不参与匹配(零边 pattern 的孤立 node 用)

    def __post_init__(self) -> None:
        # event_cls 归一化(2026-08-06 agent team 定稿: 作者默认不写,写则校验;
        # 事件类型注册表反查已消灭,子结构 node 须显式声明)
        if self.detector is not None:
            from path2.core import stream_schema
            schema = stream_schema(self.detector)
            if self.produces_stream not in schema:
                raise ValueError(
                    f"NodeSpec({self.node_id!r}): detector 无流 {self.produces_stream!r}"
                    f"(声明 {set(schema)})")
            object.__setattr__(self, "event_cls", schema[self.produces_stream])
            if self.produced_by is not None:
                raise ValueError(f"NodeSpec({self.node_id!r}): detector 与 produced_by 互斥")
        else:
            if self.produces_stream is not None:
                raise ValueError(
                    f"NodeSpec({self.node_id!r}): 子结构 node(无 detector)的 "
                    f"produces_stream 必须是 None")
            if self.event_cls is None:
                raise ValueError(
                    f"NodeSpec({self.node_id!r}): 子结构 node(无 detector)必须显式声明 "
                    f"event_cls(node_id == 事件类型注册表反查约定已消灭)")
