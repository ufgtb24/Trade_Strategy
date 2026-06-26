"""path2.dag —— DAG-first 声明式事件模式引擎(理想架构)。

协议层类型:
  edges  —— DependencyEdge 抽象基类 + 5 个多态子类(时序/包含/否定/交叠/同段)。
  nodes  —— NodeSpec(角色+detector+where) / MatchContext。
  where  —— W.* 节点谓词便利层(一元约束)。
  spec   —— PatternSpec(纯声明) + 校验 + to_topology。
  result —— PatternMatch / EdgeWitness / PredicateTrace / AnalysisResult(引擎产物)。

与旧 path2/ 共存:旧模块原样保留作 golden baseline,新系统全在本子包内,同名类型不冲突。
引擎(匹配算法)是 Phase 2,本子包 Phase 1 只有类型。
"""

from path2.dag.edges import (
    DependencyEdge, TemporalEdge, ContainmentEdge, NegationEdge, OverlapEdge, EqualsEdge,
    StartContainmentEdge,
)
from path2.dag.nodes import NodeSpec, MatchContext, WherePredicate
from path2.dag.spec import (
    PatternSpec, PatternTopology, TopoNode, TopoEdge,
)
from path2.dag.result import (
    PatternMatch, EdgeWitness, PredicateTrace, AnalysisResult,
    ClauseWitness, AttrRow, RelRow, RoleDiagnostic, RoleDiagnostics,
)
from path2.dag import where
from path2.dag.engine import analyze, matches, run_streams
from path2.dag.diagnose import diagnose

__all__ = [
    "DependencyEdge", "TemporalEdge", "ContainmentEdge", "NegationEdge", "OverlapEdge", "EqualsEdge",
    "StartContainmentEdge",
    "NodeSpec", "MatchContext", "WherePredicate",
    "PatternSpec", "PatternTopology", "TopoNode", "TopoEdge",
    "PatternMatch", "EdgeWitness", "PredicateTrace", "AnalysisResult",
    "ClauseWitness", "AttrRow", "RelRow", "RoleDiagnostic", "RoleDiagnostics",
    "where",
    "analyze", "matches", "run_streams",
    "diagnose",
]
