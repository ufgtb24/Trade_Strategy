"""端到端验收:多流 + ref_slots 翻译 + on_gate 归属 + solve=False。

验收 spec §12 标准 2/3:
  - 多流 detector 两条流各归各 node;
  - ref_slots 对象引用在统一标注后翻译成真 instance_id(Event.ref_ids);
  - solve=False 的孤立 node 不参与匹配(零边 pattern 不 KeyError、matches 不含它);
  - on_gate 的 GateFailure 按 gf.stream 路由到正确 node。
"""
import pandas as pd

from path2.dag.engine import analyze, run_streams
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2_web.gate_collector import attach_and_collect, detach
from tests.path2.dogfood_multistream import RangeNoteDetector


def _df():
    n = 15
    base = list(range(1, n + 1))
    return pd.DataFrame({"open": base, "high": [x + 0.5 for x in base],
                         "low": [x - 0.5 for x in base], "close": base,
                         "volume": [1] * n})


def test_end_to_end_streams_refs_solve():
    det = RangeNoteDetector(span=3, min_bars=5)
    spec = PatternSpec("p", edges=(), nodes=[
        NodeSpec("range", det, produces_stream="range"),
        NodeSpec("note", det, produces_stream="note", solve=False),
    ])
    streams = run_streams(spec, _df())
    # 两流各归各、ref 翻译成真 instance_id
    ranges, notes = streams["range"], streams["note"]
    assert ranges and notes
    assert notes[0].ref_ids_of("anchor") == (ranges[0].instance_id,)
    # solve=False 的 note 不出现在 matches
    res = analyze(spec, _df())
    assert all("note" not in m.node_index for m in res.matches)


def test_end_to_end_gate_routes_to_range_node():
    det = RangeNoteDetector(span=3, min_bars=5)
    spec = PatternSpec("p", edges=(), nodes=[
        NodeSpec("range", det, produces_stream="range"),
        NodeSpec("note", det, produces_stream="note", solve=False),
    ])
    collector = attach_and_collect(spec)
    _ = run_streams(spec, _df())          # detect 期 warmup 不足会 emit gate
    detach(spec)
    assert collector.snapshot()
    assert all(f.node_id == "range" for f in collector.snapshot())
    assert all(f.stream == "range" for f in collector.snapshot())
