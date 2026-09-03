from __future__ import annotations

import dataclasses
import math
from abc import ABC
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Iterator,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from path2 import config

if TYPE_CHECKING:
    # 仅供静态类型检查；见下方 Detector.on_gate 注释——不可在运行时真正 import,
    # 否则打破 core.py(地基层)不依赖 dag/(上层)的分层方向。
    from path2.dag.gate_failure import GateFailure


@dataclass(frozen=True)
class Event(ABC):
    """Path 2 中事件的基类。所有具体事件 row 类必须继承自 Event。

    子类契约:必须 @dataclass(frozen=True);若自定义 __post_init__,
    必须调用 super().__post_init__()。

    confirm_idx: 事件被确认成立的 bar 索引（因果闸地基）。

        语义:站在 confirm_idx 这根收盘时,只读 ≤ confirm_idx 的数据,
        就足以确定本事件已经发生。confirm_idx 之后到 end_idx 的数据
        是事件成立后才产生的(后续走势、验证窗口),不参与"判定成立"。
        买点锚点字段的 bar 必须 ≥ confirm_idx,否则是前瞻偏差。

        确定标准 —— 区分两个概念:
          · 成立条件:detector 必须观察到什么才能说"事件发生了"。
            confirm_idx 跟踪它。
          · 观察窗口(end_idx):事件成立后跟踪后续表现的窗口。
            与 confirm_idx 无必然关系。

        自检:砍掉 end_idx(及之后所有 bar)还能不能判定事件成立?
          能   → confirm_idx < end_idx(终点只是观察窗口)
          不能 → confirm_idx = end_idx(终点是成立条件的一部分)

        两类事件(由 confirm_idx 落在区间哪端区分;confirm 始终是因——
        事件在确认那一刻才诞生,区别只是确认发生在哪端):
          · 确认型(confirm_idx == start_idx):一确认就生,往后观察。
            因果:因为是 confirm 点,所以才是 start 点。如 ThrowbackEvent。
          · 回顾型(confirm_idx == end_idx):区段走完才回看确认。
            因果:因为是 confirm 点,所以才是 end 点。如 BurstEvent/TrendSegment/Platform。

        node_id / instance_idx / instance_id:物化标注(engine.annotate_stream)
        注入。detector 构造阶段为 None/0/None;物化后恒非 None。instance_id =
        `{node_id}_{start}[_{end}]}#{instance_idx}`——点事件(start==end)塌缩为
        `{node_id}_{start}`、区间保留 `{node_id}_{start}_{end}`(塌缩规则内联于
        engine.annotate_stream),桶 (node_id, start, end) 内流序从 0 起——
        instance_id 契约唯一出处,禁止各处自行构造。
        约束:start_idx ≤ confirm_idx ≤ end_idx。

        ref_ids:引用槽(ref_slots())翻译结果,引擎 _translate_refs 物化后注入;
        detector 阶段恒 `()`。形状 = 按槽名字典序排列的 `(槽名, (instance_id, ...))`
        对(dict 换成 tuple 是为了保持 frozen 容器一律 tuple、可哈希)。用
        `ref_ids_of(slot)` 按槽名取翻译结果(缺槽返回 `()`)。

        debug 锚点档位(detector 埋 debug_break 时对齐;confirm 并入端点档)。
        分两层,维度不同——事件层档位与 detector 层档位:
          · 事件层(start / end,所有事件,confirm 落其一):start 与 end 是事件端点;
            confirm 必落其一——确认型(confirm==start)的 start 档即确认点、回顾型
            (confirm==end)的 end 档即确认点。点事件 start==end 单档。
          · detector 层(entry,attempt 入口):由检测结构决定有无,不随事件类型——
            仅当 attempt 入口独立于事件起点时出现:确认型 + 独立 attempt(如容器,
            入口=bo 根)单独成档;回顾型 + 独立 attempt(入口=区段起点)entry 并入
            start;次级产物/子结构段(无独立 attempt,如 tb_seg)无 entry。
          · gate 是短路诊断档(on_gate emit),非事件端点,不进 per-event 锚点。
    """

    node_id: Optional[str] = field(kw_only=True, default=None)   # 物化标注注入,detector 阶段 None
    instance_idx: int = field(kw_only=True, default=0)           # 桶内流序,物化标注注入
    instance_id: Optional[str] = field(kw_only=True, default=None)  # 组合键,物化标注注入
    ref_ids: Tuple[Tuple[str, Tuple[str, ...]], ...] = field(kw_only=True, default=())  # ref_slots() 翻译结果,物化标注注入
    start_idx: int
    end_idx: int
    confirm_idx: int = field(kw_only=True)

    is_point: ClassVar[bool] = False   # 子类点事件覆写为 True(start_idx==end_idx 几何承诺)

    def __post_init__(self) -> None:
        if not config.RUNTIME_CHECKS:
            return
        # frozen 一致性由 @dataclass 在装饰期原生强制(非 frozen 子类继承 frozen Event
        # 会在类定义时即抛 TypeError),无需在此自检。
        if not isinstance(self.start_idx, int) or not isinstance(self.end_idx, int):
            raise TypeError("start_idx/end_idx 必须是 int")
        if type(self.start_idx) is bool or type(self.end_idx) is bool:
            raise TypeError("start_idx/end_idx 不能是 bool(bool ⊂ int,语义错误)")
        if self.start_idx < 0 or self.start_idx > self.end_idx:
            raise ValueError(f"非法区间 [{self.start_idx},{self.end_idx}]")
        if not (self.start_idx <= self.confirm_idx <= self.end_idx):
            raise ValueError(
                f"confirm_idx={self.confirm_idx} 必须在 "
                f"[start_idx={self.start_idx}, end_idx={self.end_idx}] 内"
            )
        for f in dataclasses.fields(self):
            v = getattr(self, f.name)
            if isinstance(v, float) and math.isnan(v):
                raise ValueError(
                    f"字段 {f.name} 为 NaN — 违反'Row 落地=字段完成'"
                )

    def sample_bar_indices(self):
        """eval 统计的样本 bar 索引(买点日)。默认=span 内每根;嵌套容器 override 展开 child。"""
        return range(self.start_idx, self.end_idx + 1)

    def child_slots(self) -> Mapping[str, "Event | Tuple[Event, ...]"]:
        """构成本 event 的非冗余主 child 集（展平/遍历用，不含投影别名）。叶子返回 {}。"""
        return {}

    def ref_slots(self) -> Mapping[str, "Event | Tuple[Event, ...]"]:
        """引用槽位(翻译身份)。构成本事件引用的其他事件(跨流/同流)，
        标注阶段统一翻译成 instance_id。默认空。"""
        return {}

    def ref_ids_of(self, slot: str) -> "Tuple[str, ...]":
        """按槽名取 ref_ids 翻译结果(缺槽返回 `()`)。"""
        for name, ids in self.ref_ids:
            if name == slot:
                return ids
        return ()

    def child(self, name: str) -> "Event":
        """命名取单 child（含 first_*/last_* 投影别名）。用途：selector / edge 端点。"""
        raise KeyError(name)

    def children(self, name: str) -> "Tuple[Event, ...]":
        """命名取组 child。用途：selector 聚合。"""
        raise KeyError(name)

    @property
    def descendant_leaves(self) -> "Tuple[Event, ...]":
        """递归展平到无 child 的 atom。终止不变式：is_leaf(e) ⟺ child_slots(e)=={}。"""
        out = []
        for slot in self.child_slots().values():
            members = slot if isinstance(slot, tuple) else (slot,)
            for m in members:
                out.extend(m.descendant_leaves if m.child_slots() else (m,))
        return tuple(out)


@runtime_checkable
class Detector(Protocol):
    """从下层数据 / 事件流产生上层 Event 的生产者。

    on_gate: optional hook · attempt 短路失败时 detector 调用它上报 GateFailure。
    默认 None(生产路径无开销);仅诊断层挂 collector 时才启用(Task 10-12 消费)。
    声明置于 TYPE_CHECKING 守卫内,只供静态类型检查、不进入运行时
    __annotations__ —— Python 3.12 下 runtime_checkable 的 isinstance 结构检查会把
    Protocol 里任何(哪怕只声明、带默认值的)属性都纳入必须项;若此处正常声明,
    所有现有 conforming class(未显式带 on_gate,如
    tests/path2/test_detector_protocol.py::Good)会被判定不再满足 Detector,
    造成回归。TYPE_CHECKING 守卫两全:类型检查器仍能看到 on_gate 契约,
    运行时 isinstance 行为不变。
    """
    if TYPE_CHECKING:
        on_gate: Optional[Callable[["GateFailure"], None]]
        produces: ClassVar[Mapping[str, type]]   # ★ 多流声明;单流 detector 不写

    def detect(self, source: Any) -> Iterator[Event]: ...


DEFAULT_STREAM = None   # 「该 detector 的唯一流」的流名


def stream_schema(det) -> Mapping[Optional[str], type]:
    """detector → {流名: event_cls}。单流 detector 归一化成 {None: det.event_cls}。"""
    produces = getattr(det, "produces", None)
    if produces:
        return dict(produces)
    cls = getattr(det, "event_cls", None)
    if cls is None:
        raise ValueError("detector 必须声明 event_cls(单流)或 produces(多流)")
    return {DEFAULT_STREAM: cls}
