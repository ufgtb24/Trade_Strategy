"""Stage 0.5:AnalysisResult.dropped_matches + DroppedMatch —— A2 淘汰的残缺 match 留痕。

供 Task 21 前端 DetailSidebar 消费,提示"这些 marker 属于被消费的 node · 当前 pattern 未触发"。
"""
from tests.path2.dag._oracle import Ev
from path2.dag.edges import TemporalEdge
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import analyze
from path2.dag.result import AnalysisResult, DroppedMatch


def test_dropped_match_dataclass():
    dm = DroppedMatch(
        match_id="m0",
        node_events={"burst": "b1", "tb": "t3"},
        drop_reason="isolated_consumed",
    )
    assert dm.drop_reason == "isolated_consumed"


def test_analysis_result_has_dropped_matches_field():
    # events/matches 在真实 AnalysisResult 上无默认值(向后兼容不变),显式传入
    r = AnalysisResult(events=(), matches=(), dropped_matches=())
    assert r.dropped_matches == ()


def test_analysis_result_dropped_matches_defaults_empty():
    """向后兼容:不传 dropped_matches 时默认为空元组(既有调用方零改动)。"""
    r = AnalysisResult(events=(), matches=(), spec=None)
    assert r.dropped_matches == ()


class FakeDetector:
    """合成 detector,detect(self, *source) 任意元数兼容。"""
    def __init__(self, evs):
        self._evs = evs

    def detect(self, *source):
        return iter(self._evs)


def _run_analyze_with_isolated_consumed_fixture():
    """bbb 形态(同 test_a2_isolated_consumed.py 回归夹具):bo 孤立无边 AND 被
    burst/tb 的 consumes_stream 引用 → {bo} 残缺 match 被 A2 过滤,应快照进
    dropped_matches。"""
    bo = NodeSpec("bo", detector=FakeDetector([Ev("bo0", 1, 1), Ev("bo1", 4, 4)]))
    burst = NodeSpec("burst", detector=FakeDetector([Ev("burst0", 5, 5)]),
                     consumes_stream="bo")
    tb = NodeSpec("tb", detector=FakeDetector([Ev("tb0", 6, 6)]),
                  consumes_stream="bo")
    edges = (TemporalEdge("burst", "tb", min_gap=0, max_gap=100),)
    spec = PatternSpec(pattern_id="dropped_test", nodes=(bo, burst, tb), edges=edges)
    return analyze(spec, df=object())


def test_isolated_consumed_match_recorded():
    """post-filter 淘汰的 match 写入 dropped_matches"""
    result = _run_analyze_with_isolated_consumed_fixture()
    assert len(result.dropped_matches) >= 1
    assert result.dropped_matches[0].drop_reason == "isolated_consumed"
    assert set(result.dropped_matches[0].node_events.keys()) == {"bo"}
    # 淘汰记录不出现在存活 matches 里(node_events 的值是 event_id,存活 match 无 {bo}-only)
    bo_only_survivors = [m for m in result.matches
                         if set((m.node_index or {}).keys()) == {"bo"}]
    assert bo_only_survivors == []
