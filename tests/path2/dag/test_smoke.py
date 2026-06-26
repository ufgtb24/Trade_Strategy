"""path2.dag 子包可导入 + 复用 path2.core.Event 冒烟。"""

def test_package_imports():
    import path2.dag as dag
    assert dag is not None

def test_reuses_core_event():
    from path2.core import Event
    assert hasattr(Event, "class_id")

def test_public_api_reexports():
    from path2.dag import (
        DependencyEdge, TemporalEdge, ContainmentEdge, NegationEdge, OverlapEdge, EqualsEdge,
        NodeSpec, MatchContext,
        PatternSpec, PatternTopology, TopoNode, TopoEdge,
        PatternMatch, EdgeWitness, PredicateTrace, AnalysisResult,
    )
    from path2.dag import where as W
    assert TemporalEdge("a", "b").src == "a"
    assert callable(W.attr)
