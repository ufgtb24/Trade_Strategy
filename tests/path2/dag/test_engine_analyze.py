# tests/path2/dag/test_engine_analyze.py
"""端到端 analyze:合成 detector 编排 + AnalysisResult。"""
from tests.path2.dag._oracle import Ev
from path2.dag.edges import TemporalEdge
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.result import AnalysisResult
from path2.dag.engine import analyze, matches


class FakeDetector:
    """合成 detector:忽略输入,吐预设事件流。detect(self, *source) 与真实 detector 的
    root(detect(df))/消费者(detect(bos,df)) 任意元数兼容。"""
    def __init__(self, evs): self._evs = evs
    def detect(self, *source): return iter(self._evs)


def _spec(nodes, edges):
    return PatternSpec(pattern_id="e2e", nodes=tuple(nodes),
                       edges=tuple(edges))


def test_analyze_chain_produces_match():
    A = NodeSpec("A", detector=FakeDetector([Ev("a", 0, 0)]))
    B = NodeSpec("B", detector=FakeDetector([Ev("b", 5, 5)]))
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    res = analyze(_spec([A, B], edges), df=object())
    assert isinstance(res, AnalysisResult)
    assert len(res.matches) == 1
    assert res.matches[0].node_index["B"].start_idx == 5
    assert len(res.events) == 2                       # 两条流平铺
    assert res.spec is not None


def test_analyze_consumes_stream_order():
    # tb 消费 bo 流:detector 编排须先跑 bo。FakeDetector 忽略输入故结果不依赖顺序,
    # 但 detector_topo_order 不报错即证编排可行。
    bo = NodeSpec("bo", detector=FakeDetector([Ev("bo0", 2, 2)]))
    tb = NodeSpec("tb", detector=FakeDetector([Ev("tb0", 4, 4)]), consumes_stream="bo")
    edges = [TemporalEdge("bo", "tb", min_gap=1, max_gap=5)]
    res = analyze(_spec([bo, tb], edges), df=object())
    assert len(res.matches) == 1


def test_matches_bool():
    A = NodeSpec("A", detector=FakeDetector([Ev("a", 0, 0)]))
    B = NodeSpec("B", detector=FakeDetector([]))   # B 空 -> 无匹配
    edges = [TemporalEdge("A", "B")]
    assert matches(_spec([A, B], edges), df=object()) is False


class _StrictRootDetector:
    """detect(self, df) —— 恰一个位置参,仿真实 bo/trend/distribution/platform。
    若 engine 把 df 传两次(root 误用 run(d, src, df)→detect(df,df)),这里会 TypeError。"""
    def __init__(self, evs): self._evs = evs
    def detect(self, df): return iter(self._evs)


class _StrictConsumerDetector:
    """detect(self, upstream, df) —— 两个位置参,仿真实 throwback/burst(消费上游流 + df)。"""
    def __init__(self, evs): self._evs = evs
    def detect(self, upstream, df): return iter(self._evs)


def test_analyze_calls_real_detector_arity():
    # 回归:engine 须按真实 detector 实际入参调用——root 只传 df(detect(df)),
    # 消费者传 (上游流, df)(detect(bos, df))。计划原版 run(detector, src, df) 会把
    # root 调成 detect(df, df) → TypeError(真实 detect(self, df) 只收一参)。
    bo = NodeSpec("bo", detector=_StrictRootDetector([Ev("bo0", 0, 0)]))
    tb = NodeSpec("tb", detector=_StrictConsumerDetector([Ev("tb0", 3, 3)]),
                  consumes_stream="bo")
    edges = [TemporalEdge("bo", "tb", min_gap=1, max_gap=10)]
    res = analyze(_spec([bo, tb], edges), df=object())
    assert len(res.matches) == 1
    assert res.matches[0].node_index["tb"].start_idx == 3
