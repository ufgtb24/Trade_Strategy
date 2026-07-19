"""边类型层级 —— DependencyEdge 抽象基类 + 6 个多态子类。

R4(时序=拓扑子类)落地:一条边在类型层承担两个正交职责——
  结构职责(拓扑): src→dst 的 DAG 有向依赖(基类承载,定拓扑序/前沿推进/面板箭头);
  可行性职责(语义): 一对已绑候选是否满足该边关系(各子类 satisfies)。
引擎只认基类多态 satisfies/feasible_window/signature_fields,对边类型零分支;
新增关系 = 加一个子类,零核心改动。

OverlapEdge/EqualsEdge 的数值经 ~9.7 万 fuzz 验证(verdict §6/§8)。
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

from path2.core import Event


@dataclass(frozen=True)
class Child:
    """端点 selector：表示"取 node 对应绑定事件的 child(key)"。

    用于边的 src/dst 参数：
      ContainmentEdge("side", Child("burst", "first_bo"))
    边在 __post_init__ 中把 Child 归一化为 (dst="burst", dst_selector="first_bo")，
    使 spec 校验/WCC 图构建仍看到纯 str。
    """
    node: str   # child 所属父节点的 node_id（归一化后成为边的 src/dst str）
    key: str    # 传给 event.child(key) 的名称


@dataclass(frozen=True)
class DependencyEdge(ABC):
    """有向依赖边基类 —— 纯结构层,构成 DAG。

    方向 src→dst 是规范方向,同时定义:(a) 拓扑序 src 先于 dst;
    (b) 引擎前沿推进方向(先绑 src,再据 src 收窄 dst 候选域);(c) 面板箭头。
    基类不判定任何关系真假 —— satisfies 留给子类。

    端点参数接受 str（整体）或 Child（投影到子事件）。
    __post_init__ 把 Child 归一化:src/dst 始终为 str(供 spec 校验 + WCC 图构建),
    src_selector/dst_selector 为 None 或 key 字符串(供 endpoint() 提取子事件)。

    anchor 字段(整改四 B4):dst 端 anchor_field 等于 src 端 anchor_src_field 的复核约束。
    anchor_src_field=None 默认 'event_id';详见 spec §3.5 / docs/legacy/kleene/ 历史。
    """
    src: str                                   # 归一化后始终为 str（node_id）
    dst: str                                   # 归一化后始终为 str（node_id）
    # compare/hash=False: selector 不参与边身份；图结构只看 src/dst（两条仅 selector 不同的边视为同一图边）
    src_selector: Optional[str] = field(default=None, compare=False, hash=False)
    dst_selector: Optional[str] = field(default=None, compare=False, hash=False)
    # ★ 整改四:anchor 字段(C2 default-event_id 设计,详见 spec §3.5)
    # compare=False, hash=False 跟 src_selector/dst_selector 一致(不参与边身份)
    anchor_field: Optional[str] = field(default=None, compare=False, hash=False)
    anchor_src_field: Optional[str] = field(default=None, compare=False, hash=False)

    def __post_init__(self) -> None:
        """归一化 src/dst：Child → (node_str, key)；str → (str, None)。
        frozen=True 须用 object.__setattr__ 写入。
        子类覆盖 __post_init__ 时必须调用 super().__post_init__()。"""
        raw_src = self.src
        raw_dst = self.dst
        if isinstance(raw_src, Child):
            object.__setattr__(self, "src", raw_src.node)
            object.__setattr__(self, "src_selector", raw_src.key)
        if isinstance(raw_dst, Child):
            object.__setattr__(self, "dst", raw_dst.node)
            object.__setattr__(self, "dst_selector", raw_dst.key)

    @abstractmethod
    def satisfies(self, e_src: Event, e_dst: Event) -> bool:
        """充要判定:给定一对已绑候选,本边二元关系是否成立。纯函数,不读 df。
        正向边语义 ∃e_dst.satisfies ⇒ 边成立;否定边语义 ∀e_dst.¬satisfies ⇒ 边成立。"""
        ...

    def feasible_window(self, e_src: Event) -> tuple[float, float]:
        """剪枝钩子:给定已绑 e_src,返回 e_dst.start_idx 的可行闭区间 [lo,hi]。
        引擎用它把 O(后缀)扫描收窄成区间过滤。默认 (-inf,+inf) = 不剪枝。
        INV-C 命脉(verdict):剪枝只能基于 feasible_window(单调、进签名),
        绝不能基于 satisfies(任意属性,不进签名)。"""
        return (float("-inf"), float("inf"))

    def signature_fields(self) -> tuple[str, ...]:
        """前沿割签名据此自描述地构造维度:本边 satisfies/feasible_window
        实际依赖 e_src 的哪些字段。引擎签名取所有跨割边 signature_fields 的并集。
        覆盖不全 = INV-C 漏匹配(verdict)。默认空(基类不依赖任何 src 字段)。"""
        return ()

    def _anchor_ok(self, src_ep: Event, e_dst: Event) -> bool:
        """整改四 anchor 复核:dst 端 anchor_field 等于 src 端 anchor_src_field(default 'event_id')。
        anchor_field=None 时恒 True(字节等价旧行为)。详见 spec §3.5。"""
        if self.anchor_field is None:
            return True
        src_attr = self.anchor_src_field or "event_id"
        return getattr(e_dst, self.anchor_field) == getattr(src_ep, src_attr)


@dataclass(frozen=True)
class TemporalEdge(DependencyEdge):
    """时序边 = DAG 单向依赖 + 自己的 gap(R4 核心)。
    gap = e_dst.start_idx − e_src.end_idx ∈ [min_gap, max_gap]。吸收 Before/After。
    strict(keyword-only,防与 min_gap/max_gap 位置参数错位,verdict §5):
      strict=True ⇒ next 语义(src 与 dst 间窗内无更早同类 dst);引擎 bind-time check(Phase 2)。
    """
    min_gap: int = 0
    max_gap: float = math.inf
    strict: bool = field(default=False, kw_only=True)

    def __post_init__(self) -> None:
        super().__post_init__()  # Child 端点归一化
        if self.min_gap < 0 or self.min_gap > self.max_gap:
            raise ValueError(f"非法 gap 区间 [{self.min_gap},{self.max_gap}]")

    def feasible_window(self, a: Event) -> tuple[float, float]:
        return (a.end_idx + self.min_gap, a.end_idx + self.max_gap)

    def satisfies(self, a: Event, b: Event) -> bool:
        lo, hi = self.feasible_window(a)
        return lo <= b.start_idx <= hi

    def signature_fields(self) -> tuple[str, ...]:
        return ("end_idx",)


@dataclass(frozen=True)
class ContainmentEdge(DependencyEdge):
    """包含边:规范方向 src ⊇ dst(大区间→小区间)。
    satisfies: src.start <= dst.start AND dst.end <= src.end(<= 共享端点归包含)。
    吸收 Overlaps contains/within 镜像对(contains(A,B) ≡ within(B,A)),只留大→小一向。
    """
    def satisfies(self, a: Event, b: Event) -> bool:
        return a.start_idx <= b.start_idx and b.end_idx <= a.end_idx

    def feasible_window(self, a: Event) -> tuple[float, float]:
        # dst.start ∈ [src.start, src.end];lo=src.start 对 start 端充要,end 端由 satisfies 兜底
        return (a.start_idx, a.end_idx)

    def signature_fields(self) -> tuple[str, ...]:
        return ("start_idx", "end_idx")


@dataclass(frozen=True)
class OverlapEdge(DependencyEdge):
    """部分交叠边:dst 从 src 内部起、延伸到 src 之后(src 后端被 dst 叠)。
    镜像 overlapped_front 由反向读法 OverlapEdge(dst,src) 承载,不单列。
    实证健全(verdict §6.1):window 对 dst.start 双侧充要,C1+memo 可开。
    """
    def satisfies(self, a: Event, b: Event) -> bool:
        return a.start_idx < b.start_idx < a.end_idx and a.end_idx < b.end_idx

    def feasible_window(self, a: Event) -> tuple[float, float]:
        return (a.start_idx + 1, a.end_idx - 1)

    def signature_fields(self) -> tuple[str, ...]:
        return ("start_idx", "end_idx")


@dataclass(frozen=True)
class EqualsEdge(DependencyEdge):
    """同段边:src 与 dst 占据完全相同区间。
    ★ 引擎硬约束(verdict §6.2,实证发现的漏匹配 bug 的修复):feasible_window 把
    dst.start 钉死(非可放宽下界),C1 等-end 塌缩对其 SRC 节点会漏匹配 → 引擎必须对
    "作为任何 EqualsEdge 之 SRC 的节点"关闭 C1(Phase 2;PatternSpec.eq_src_nodes 喂判据)。
    satisfies/window/sig 本身无需特殊。
    """
    def satisfies(self, a: Event, b: Event) -> bool:
        return b.start_idx == a.start_idx and b.end_idx == a.end_idx

    def feasible_window(self, a: Event) -> tuple[float, float]:
        return (a.start_idx, a.start_idx)

    def signature_fields(self) -> tuple[str, ...]:
        return ("start_idx", "end_idx")


@dataclass(frozen=True)
class StartContainmentEdge(DependencyEdge):
    """起点包含边:规范方向 src 包含 dst 的起点(只约束 dst.start 落入 src 区间)。

    与 ContainmentEdge 的区别:ContainmentEdge 要求 dst 整体被 src 包含(dst.end <= src.end);
    StartContainmentEdge 只要求 dst.start ∈ [src.start, src.end],dst.end 不受约束。

    适用场景:side→burst 边迁移(match-preserving)。
      当前 ONCE 语义:ContainmentEdge("side","bo") 对 bo(点事件)= "side 包含 bo.start"。
      迁移后 burst 是宽事件(start=first_bo.start, end=last_bo.end);ContainmentEdge 会额外要求
      last_bo.end <= side.end,比原语义更严,非 match-preserving。
      StartContainmentEdge 精确保留原语义:只约束 burst.start(=first_bo.start) 落 side 区间。

    INV-C 健全:feasible_window 对 dst.start 双侧充要(window 充要 ⟺ satisfies),
    不依赖 dst.end,无 satisfies-only 字段,无漏匹配风险。
    signature_fields 覆盖 feasible_window 所读的 src 字段(start_idx + end_idx)。
    """

    def satisfies(self, a: Event, b: Event) -> bool:
        return a.start_idx <= b.start_idx <= a.end_idx

    def feasible_window(self, a: Event) -> tuple[float, float]:
        # dst.start ∈ [src.start, src.end]:与 satisfies 充要一致
        return (a.start_idx, a.end_idx)

    def signature_fields(self) -> tuple[str, ...]:
        return ("start_idx", "end_idx")


@dataclass(frozen=True)
class NegationEdge(DependencyEdge):
    """否定边:src 锚定窗口内【禁止】存在满足条件的 dst。
    dst 不进 node_index/children(是约束,非结构成员)。取代旧 Neg detector 的 forbid。
    satisfies 语义【反转】:返 True 表示该 e_dst 落入禁区(违禁),引擎用全称量词消费(Phase 2)。
    """
    min_gap: int = 0
    max_gap: float = math.inf
    inner_predicate: Optional[Callable[[Event], bool]] = None

    def satisfies(self, a: Event, b: Event) -> bool:  # True = 违禁
        in_window = self.min_gap <= b.start_idx - a.end_idx <= self.max_gap
        return in_window and (self.inner_predicate is None or self.inner_predicate(b))
