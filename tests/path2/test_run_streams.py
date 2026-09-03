# tests/path2/test_run_streams.py
"""run_streams 抽出:返回 node_id -> [Event],与 analyze 内部一致。"""
from path2.dag.engine import run_streams, analyze
from path2_apps.bottom_burst import build_pattern
from tests.path2.fixtures.positive_case import positive_case


def test_run_streams_keys_and_nonempty():
    df, params = positive_case()
    spec = build_pattern(params)
    streams = run_streams(spec, df, params)
    # 每个独立 node 一条流;子结构 node(tb_seg,detector=None)由父容器物化、无独立流
    assert set(streams.keys()) == {n.node_id for n in spec.nodes if n.detector is not None}
    assert all(isinstance(v, list) for v in streams.values())
    assert len(streams["bo"]) >= 1                                   # bo 流非空


def test_analyze_events_equal_streams_flatten():
    df, params = positive_case()
    spec = build_pattern(params)
    streams = run_streams(spec, df, params)
    res = analyze(spec, df, params)
    # analyze.events == 按 id(stream) 去重后平铺(共享 detector 的 node 指向同一 list,只计一遍)
    # bottom_burst: down/side 共享 TrendSegmentDetector → streams["down"] is streams["side"]
    # 朴素 flat 会重复计入趋势流;正确期望是按 id(stream) 去重后的平铺长度
    seen = {}
    for s in streams.values():
        seen.setdefault(id(s), s)
    deduped_flat = [e for s in seen.values() for e in s]
    assert len(res.events) == len(deduped_flat)
