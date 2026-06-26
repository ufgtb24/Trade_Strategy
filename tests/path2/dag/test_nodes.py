"""NodeSpec / MatchContext 构造与默认值。"""
from path2.dag.nodes import NodeSpec, MatchContext


class _FakeDetector:
    def detect(self, source, df=None):
        return iter(())


def test_nodespec_defaults():
    d = _FakeDetector()
    n = NodeSpec(node_id="bo", detector=d)
    assert n.node_id == "bo"
    assert n.detector is d
    assert n.where == ()
    assert n.consumes_stream is None
    assert n.label == ""

def test_nodespec_with_where_and_consumes():
    d = _FakeDetector()
    w = ("c1", lambda e, ctx: True)
    n = NodeSpec("tb", d, where=(w,), consumes_stream="bo", label="回踩")
    assert n.where == (w,)
    assert n.consumes_stream == "bo"
    assert n.label == "回踩"

def test_match_context_holds_df_params_bound():
    ctx = MatchContext(df="DF", params="P", bound={"a": 1})
    assert ctx.df == "DF" and ctx.params == "P" and ctx.bound == {"a": 1}
