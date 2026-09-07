"""R10: 别名(两 node 同 det/consumes/produces)在下游(solve/reify/analyze/serialize)会不会炸?"""
import sys
sys.path.insert(0, "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro")
from dataclasses import dataclass
from typing import ClassVar
from path2 import config
from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.edges import TemporalEdge
from path2.dag.engine import analyze
from r1_alias import A, B, TwoStream

config.set_runtime_checks(True)
det = TwoStream()

# 别名 n1/n2 都吃 "a" 流;n2 与 nb 之间连一条边,逼别名 node 进求解
spec = PatternSpec(pattern_id="t", nodes=(
    NodeSpec("n1", det, produces_stream="a"),
    NodeSpec("n2", det, produces_stream="a"),
    NodeSpec("nb", det, produces_stream="b"),
), edges=(TemporalEdge("nb", "n2", min_gap=1, max_gap=10),))
try:
    res = analyze(spec, None)
    print("analyze 通过,matches =", len(res.matches))
    for m in res.matches:
        print("  match_id:", m.match_id,
              "| node_index:", {k: (v.node_id, v.instance_id) for k, v in m.node_index.items()})
    print("res.events 条数:", len(res.events), "(id(s) 去重后)")
except Exception as e:
    print("analyze 抛错:", type(e).__name__, str(e)[:200])

# web 投影层会不会炸
try:
    from path2_web.serialize import serialize_per_pattern_result
    print("serialize 可导入")
except Exception as e:
    print("serialize 导入:", type(e).__name__, str(e)[:80])
