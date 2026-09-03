"""匹配产物 —— EdgeWitness / PredicateTrace / PatternMatch / AnalysisResult。

引擎(Phase 2)产生它们。PatternMatch 继承 Event,node_index 为 node_id → 单 Event。
EdgeWitness 让 before/within 边可实证(命中两端留痕)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from path2 import config
from path2.core import Event
from path2.dag.gate_failure import GateFailure


@dataclass(frozen=True)
class EdgeWitness:
    """before/within 可实证:命中两端进 trace 留痕(消解"声明 vs reified"拧巴)。"""
    satisfied: bool
    src_instance: Event
    dst_instance: Event
    measured: Any                 # kind-aware(硬伤 E):MeasuredKindAware 实例(kind/value/label)


@dataclass(frozen=True)
class ClauseWitness:
    """单条 where clause 在一次匹配中的判定 + 实测对照(详版 trace 用)。
    __bool__ == satisfied,使旧代码 `if where_results[nid][cid]` 行为不变(向后兼容)。
    组合子(and/or/not)witness 额外携带 children(witness 全量求值,不短路——诊断口径),
    label 供前端子行显示(叶子=字段名,组合子=kind)。"""
    satisfied: bool
    measured: object = None        # 实测值(W.*.measure 产出);组合子/无 measure 时 None
    op: object = None              # 比较算子(">=", "==", ...);组合子 None
    threshold: object = None       # 阈值;组合子 None
    label: object = None           # 显示名:叶子=field,组合子=kind;顶层可 None(cid 即显示名)
    children: tuple = ()           # 子 witness(组合子);叶子恒 ()
    def __bool__(self) -> bool:
        return bool(self.satisfied)


@dataclass(frozen=True)
class PredicateTrace:
    """富输出:每个 where / 边在本次命中的求值结果 + 实证两端实例。"""
    where_results: Mapping[str, Mapping[str, "ClauseWitness"]]   # node_id → {clause_id: ClauseWitness}
    edge_results: Mapping[Tuple[str, str], EdgeWitness]          # (src,dst) → 实证


@dataclass(frozen=True)
class PatternMatch(Event):
    """一次完整命中。继承 Event(start_idx/end_idx/confirm_idx)。match_id 为
    match 唯一键(instance_id 契约:bits 段用各 node 实例键)。"""
    match_id: str = ""
    pattern_id: str = ""
    node_index: Optional[Mapping[str, Event]] = None   # node_id → 单 Event
    children: Tuple[Event, ...] = ()                         # 全绑实例扁平(start_idx 升序)
    predicate_trace: Optional[PredicateTrace] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not config.RUNTIME_CHECKS:
            return
        # 展平不变式:node_index 值集合 == children 集合
        flat = list((self.node_index or {}).values())
        assert {id(e) for e in flat} == {id(e) for e in self.children}, \
            "node_index 展平 != children"


@dataclass(frozen=True)
class AnalysisResult:
    """走势包 analyze() 的返回值。events=所有节点流去重平铺(共享流只计一遍);matches=命中;spec=声明(供面板)。
    gate_failures=Sprint 2 入口 A(scope=time):worker 挂 collector 跑 analyze 时,三 atom
    (BurstDetector/BODetector/ThrowbackDetector,Task 10-12)on_gate 吐出的短路失败记录快照
    (engine.analyze() 本身不产出,由调用方 dataclasses.replace 附加,默认空 → 既有调用方零改动)。"""
    events: Tuple[Event, ...]
    matches: Tuple[PatternMatch, ...]
    spec: object = None
    gate_failures: Tuple[GateFailure, ...] = ()

    def __post_init__(self) -> None:
        if not config.RUNTIME_CHECKS:
            return
        # instance_id 契约:物化标注后 instance_id 唯一;重复 = 标注 bug 或
        # detector 重复 evaluate 的信号。同一 instance_id 内允许多实例
        # (per-source 视角,属性按来源区分、可以不同),仅禁止「同 instance_id
        # 完全重复对象」(同 instance_id 全属性全等 = 重复 evaluate bug)。
        # res.events 单视图 = 实例明细,只服务诊断/展示(统计读 match 不读 events)。
        for i, a in enumerate(self.events):
            for b in self.events[i + 1:]:
                assert not (a.instance_id == b.instance_id and a == b), \
                    f"res.events 同 instance_id 完全重复对象: {a.instance_id}(全属性全等=重复 evaluate bug)"


@dataclass(frozen=True)
class AttrRow:
    """某 node 的一个候选 event 的属性诊断:event + 逐 clause 判定。"""
    event: Event
    clauses: Mapping[str, ClauseWitness]      # clause_id -> witness


@dataclass(frozen=True)
class RelRow:
    """某 node 作 dst 时一条入边的伙伴检查(计数 + 可展开的合规上游 event)。"""
    src: str
    kind: str                                  # 边子类名
    total_src: int
    ok_src: Tuple[Event, ...]                  # 找得到合规 dst 伙伴的上游 event(可展开列具体)
    anchor_ok_count: int = 0                   # ★ Sprint 1 Task 1:通过 anchor 复核的伙伴数(硬伤 B)
    # ★ Sprint 1 Task 3:未通过的 src 候选按其在 dst 流里能达到的最深 gate 归因(由近及远)。
    # gap_out 是关系检查(satisfies+feasible_window)不过的统称:对 TemporalEdge 是字面 gap 越界,
    # 对 Containment/Overlap/Equals/StartContainment 则是各自的关系不成立——为与前端/Task 8 契约
    # (字面 key "gap_out")保持接口稳定,不拆分/改名。negation 是全称量词、归 node 级入口 C 诊断,
    # 本函数不产出、恒为 0,仅为接口稳定保留 key。
    miss_reasons: Dict[str, int] = field(default_factory=lambda: {
        "gap_out": 0, "anchor_mismatch": 0, "strict_fail": 0, "negation_violated": 0,
    })
    example_failed_pairs: Tuple[Tuple[str, str, str], ...] = ()  # 抽样 ≤5 条 (src_instance_id, dst_instance_id, primary_fail_channel)


@dataclass(frozen=True)
class NodeDiagnostic:
    node_id: str
    attr: Tuple[AttrRow, ...]
    rel: Tuple[RelRow, ...]
    produced_by: Optional[str] = None   # 子结构 node 的物化来源父 node_id(独立 node 为 None)


@dataclass(frozen=True)
class NodeDiagnostics:
    """diagnose() 的返回:每个 node 一份局部健康诊断。note 提醒单 node 局部性。"""
    nodes: Mapping[str, NodeDiagnostic]
    note: str = "单 node 局部诊断;通过不代表能凑成完整匹配"
