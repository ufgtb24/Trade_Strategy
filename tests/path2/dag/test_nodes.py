"""NodeSpec 构造与默认值。"""
from path2.dag.nodes import NodeSpec


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

def test_nodespec_with_where_and_consumes():
    d = _FakeDetector()
    w = ("c1", lambda e: True)
    n = NodeSpec("tb", d, where=(w,), consumes_stream="bo")
    assert n.where == (w,)
    assert n.consumes_stream == "bo"
