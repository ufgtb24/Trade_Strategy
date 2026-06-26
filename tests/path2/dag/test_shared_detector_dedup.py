"""Task 7: 共享 detector 去重——run_streams 按(id(detector),consumes_stream)物化 + res.events 按 id(stream) 去重。"""
import pandas as pd
import numpy as np
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import run_streams, analyze
from path2.dag import where as W
from path2.atoms.trend import TrendSegmentDetector


def _df(n=200):
    # 造有明显趋势切换的 OHLCV,确保 TrendSegmentDetector._make_segment 可读 high/low
    x = np.concatenate([np.linspace(100, 60, n // 2), np.linspace(60, 90, n - n // 2)])
    return pd.DataFrame({
        "close": x,
        "high": x * 1.01,
        "low": x * 0.99,
        "volume": np.ones(n),
    })


def _spec_shared():
    det = TrendSegmentDetector()          # 同一对象给两 node
    nodes = (
        NodeSpec("a", det, where=(("r", W.attr("regime", "==", "down")),), label="A"),
        NodeSpec("b", det, where=(("r", W.attr("regime", "==", "up")),), label="B"),
    )
    return PatternSpec(pattern_id="t", display_name="t", nodes=nodes, edges=(), root="a")


def test_shared_detector_runs_once():
    spec = _spec_shared()
    streams = run_streams(spec, _df())
    assert streams["a"] is streams["b"]          # 同一 list 对象(共享)


def test_res_events_deduped_unique_ids():
    res = analyze(_spec_shared(), _df())
    ids = [e.event_id for e in res.events]
    assert len(ids) == len(set(ids))             # 无重复 id(res.events 去重)
