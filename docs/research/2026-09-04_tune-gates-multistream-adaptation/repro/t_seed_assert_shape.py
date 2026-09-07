# -*- coding: utf-8 -*-
"""独立复核 engine-mech 的拦坑 + 测断言 B(事件已标注)是否承重。

1) 别名 spec 下,把整份 streams 当 seed 传回,四条候选断言 A/B/C/D 各自的真值。
2) 若 seed 进来的是**未标注**的流(绕过 B),会静默错还是响亮炸?
"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
sys.path.insert(0, str(REPO / "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro"))
import pandas as pd, study_io as S
from h_seed_streams import run_streams_seeded
from path2 import config
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback_v1 import ThrowbackDetectorV1
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, Child
from path2.dag.spec import PatternSpec
from path2.dag import where as W
from path2.dag.engine import run_streams
from path2.runner import run_bundle
from path2_web.data import slice_window
from path2_web.scan import _list_pkls

config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py"); mod = S.import_app(study)
p = mod.Params.from_dict(S.base_snapshot(mod, study), strict=True)
win = slice_window(pd.read_pickle(next(iter(_list_pkls(str(REPO / "datasets/pkls"), r"^AAPL")))),
                   "2023-01-01", "2026-03-01")

def alias_spec():
    det = BODetector(**p.bo_kwargs())
    nodes = (NodeSpec("n1", det, produces_stream="bo"),
             NodeSpec("n2", det, produces_stream="bo", solve=False),
             NodeSpec("pk", det, produces_stream="pk", solve=False),
             NodeSpec("burst", BurstDetector(**p.burst_kwargs()), consumes_stream="n1",
                      children={"members": "n1"},
                      where=(("fd", W.attr("first_drought", ">=", 0)),)),
             NodeSpec("tb", ThrowbackDetectorV1(**p.throwback_kwargs()), consumes_stream="burst"))
    return PatternSpec(pattern_id="alias", nodes=nodes,
                       edges=(TemporalEdge(Child("burst", "last_bo"), "tb", min_gap=1,
                                           max_gap=p.tb.max_span, anchor_field="anchor_bo_id"),))

spec = alias_spec()
seed = run_streams(spec, win)
ids = {n.node_id for n in spec.nodes}
print("1) 别名 spec 的 seed，各键事件的 node_id:",
      {k: sorted({e.node_id for e in v}) for k, v in seed.items()})
print("   A  key ⊆ spec 的 node 集      :", set(seed) <= ids)
print("   B  事件全部已标注(node_id 非空):", all(e.node_id is not None for v in seed.values() for e in v))
print("   C  事件 node_id == 该 key      :", all(e.node_id == k for k, v in seed.items() for e in v), "  ← engine-mech 说会误报")
print("   D  事件 node_id ∈ spec 的 node :", all(e.node_id in ids for v in seed.values() for e in v))

# 2) 未标注的 seed(绕过 B):静默还是响亮?
print("\n2) 喂一条**未标注**的流当 seed(模拟缓存层写回了 detect 直出的裸事件):")
bare = run_bundle(BODetector(**p.bo_kwargs()), win)          # 未经 annotate_stream
sp2 = mod.build_pattern(p)                                    # 正常 bb_v1
for flag in (True, False):
    config.set_runtime_checks(flag)
    try:
        out = run_streams_seeded(sp2, win, seed={"bo": bare["bo"], "pk": bare["pk"]})
        bad = [e.instance_id for e in out["bo"] if e.instance_id is None]
        anchors = {getattr(e, "anchor_bo_id", None) for e in out["tb"]}
        print(f"   RUNTIME_CHECKS={flag}: 未抛 · bo 中 instance_id 仍为 None 的事件数={len(bad)} · "
              f"burst={len(out['burst'])} tb={len(out['tb'])} · tb.anchor_bo_id 取值={sorted(map(str, anchors))[:3]}")
    except Exception as ex:
        print(f"   RUNTIME_CHECKS={flag}: 抛 {type(ex).__name__}: {str(ex)[:110]}")
config.set_runtime_checks(True)
