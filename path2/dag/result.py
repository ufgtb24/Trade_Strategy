"""匹配产物 —— EdgeWitness / PredicateTrace / PatternMatch / AnalysisResult。

引擎(Phase 2)产生它们。PatternMatch 继承 Event,role_index 为 node_id → 单 Event。
EdgeWitness 让 before/within 边可实证(命中两端留痕)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from path2 import config
from path2.core import Event


@dataclass(frozen=True)
class EdgeWitness:
    """before/within 可实证:命中两端进 trace 留痕(消解"声明 vs reified"拧巴)。"""
    satisfied: bool
    src_instance: Event
    dst_instance: Event
    measured: float               # 实测 gap / overlap 量


@dataclass(frozen=True)
class ClauseWitness:
    """单条 where clause 在一次匹配中的判定 + 实测对照(详版 trace 用)。
    __bool__ == satisfied,使旧代码 `if where_results[nid][cid]` 行为不变(向后兼容)。"""
    satisfied: bool
    measured: object = None        # 实测值(W.*.measure 产出);组合子/无 measure 时 None
    op: object = None              # 比较算子(">=", "==", ...);组合子 None
    threshold: object = None       # 阈值;组合子 None
    def __bool__(self) -> bool:
        return bool(self.satisfied)


@dataclass(frozen=True)
class PredicateTrace:
    """富输出:每个 where / 边在本次命中的求值结果 + 实证两端实例。"""
    where_results: Mapping[str, Mapping[str, "ClauseWitness"]]   # node_id → {clause_id: ClauseWitness}
    edge_results: Mapping[Tuple[str, str], EdgeWitness]          # (src,dst) → 实证


@dataclass(frozen=True)
class PatternMatch(Event):
    """一次完整命中。继承 Event(event_id/start_idx/end_idx)。"""
    class_id = "match"
    pattern_id: str = ""
    role_index: Optional[Mapping[str, Event]] = None   # node_id → 单 Event
    children: Tuple[Event, ...] = ()                         # 全绑实例扁平(start_idx 升序)
    predicate_trace: Optional[PredicateTrace] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not config.RUNTIME_CHECKS:
            return
        # 展平不变式:role_index 值集合 == children 集合
        flat = list((self.role_index or {}).values())
        assert {id(e) for e in flat} == {id(e) for e in self.children}, \
            "role_index 展平 != children"


@dataclass(frozen=True)
class AnalysisResult:
    """走势包 analyze() 的返回值。events=所有节点流去重平铺(共享流只计一遍);matches=命中;spec=声明(供面板)。"""
    events: Tuple[Event, ...]
    matches: Tuple[PatternMatch, ...]
    spec: object = None

    def __post_init__(self) -> None:
        if not config.RUNTIME_CHECKS:
            return
        ids = [e.event_id for e in self.events]
        assert len(ids) == len(set(ids)), \
            f"res.events event_id 重复: {len(ids) - len(set(ids))} 个(违反全局唯一不变量)"


@dataclass(frozen=True)
class AttrRow:
    """某 role 的一个候选 event 的属性诊断:event + 逐 clause 判定。"""
    event: Event
    clauses: Mapping[str, ClauseWitness]      # clause_id -> witness


@dataclass(frozen=True)
class RelRow:
    """某 role 作 dst 时一条入边的伙伴检查(计数 + 可展开的合规上游 event)。"""
    src: str
    kind: str                                  # 边子类名
    total_src: int
    ok_src: Tuple[Event, ...]                  # 找得到合规 dst 伙伴的上游 event(可展开列具体)


@dataclass(frozen=True)
class RoleDiagnostic:
    node_id: str
    attr: Tuple[AttrRow, ...]
    rel: Tuple[RelRow, ...]


@dataclass(frozen=True)
class RoleDiagnostics:
    """diagnose() 的返回:每个 role 一份局部健康诊断。note 提醒单 role 局部性。"""
    roles: Mapping[str, RoleDiagnostic]
    note: str = "单 role 局部诊断;通过不代表能凑成完整匹配"
