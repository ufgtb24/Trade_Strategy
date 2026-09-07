"""H 复核续:(A) counts 桶在 seed 下的跨-nid 碰撞面;(B) RUNTIME_CHECKS=False 下失败面是否消失。"""
import glob, importlib
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Tuple
import pandas as pd
from path2 import config
from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
import sys
sys.path.insert(0, "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro")
from e_h_seed_failure_faces import run_streams_seeded

# ---------- (A) counts 桶碰撞:跨兄弟 children 持有 + 半截 seed ----------
@dataclass(frozen=True)
class Pk(Event):
    is_point: ClassVar[bool] = True
@dataclass(frozen=True)
class Bo(Event):
    peaks: Tuple[Event, ...] = ()
    is_point: ClassVar[bool] = True
    def child_slots(self): return {"peak": self.peaks} if self.peaks else {}

class TwoStream:
    produces: ClassVar[dict] = {"bo": Bo, "pk": Pk}
    def detect(self, df):
        pks = [Pk(start_idx=i, end_idx=i, confirm_idx=i) for i in (2, 4)]
        for p in pks: yield ("pk", p)
        for i in (5, 7): yield ("bo", Bo(start_idx=i, end_idx=i, confirm_idx=i, peaks=tuple(pks)))

def build():
    det = TwoStream()
    return PatternSpec(pattern_id="t", nodes=(
        NodeSpec("bo", det, produces_stream="bo", children={"peak": "pk"}),
        NodeSpec("pk", det, produces_stream="pk", solve=False),
    ), edges=())

config.set_runtime_checks(True)
full, _ = run_streams_seeded(build(), None)
print("(A) 无 seed:  pk 流 =", [e.instance_id for e in full["pk"]],
      "| bo 持有 child =", [[c.instance_id for c in e.peaks] for e in full["bo"]])
half, _ = run_streams_seeded(build(), None, seed={"pk": full["pk"]})   # 只 seed pk,bo 组重跑
ids_stream = [e.instance_id for e in half["pk"]]
ids_child  = [c.instance_id for e in half["bo"] for c in e.peaks]
print("(A) 半截 seed: pk 流 =", ids_stream, "| bo 持有 child =", ids_child[:2])
print("(A) 与无 seed 逐字相同?", ids_stream == [e.instance_id for e in full["pk"]],
      "| 出现 instance_id 撞车?", bool(set(ids_stream) & set(ids_child)))

# ---------- (B) RUNTIME_CHECKS=False 下,面 3 / 面 4 还抓不抓得住 ----------
mod = importlib.import_module("path2_apps.bb_v1.dag_spec")
P = importlib.import_module("path2_apps.bb_v1.params")
base = P.Params.from_yaml(Path("path2_apps/bb_v1/params.yaml"))
df = pd.read_pickle(sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))[1])
full_b, _ = run_streams_seeded(mod.build_pattern(base), df)

config.set_runtime_checks(False)
print("\n(B) RUNTIME_CHECKS=False:")
try:
    st, _ = run_streams_seeded(mod.build_pattern(base), df, seed={"ghost": full_b["bo"]})
    print("    幽灵键: 未抛错,streams 含 ghost =", "ghost" in st, "→ 静默污染")
except Exception as e:
    print("    幽灵键: 抛", type(e).__name__, str(e)[:60])

# 无 ref_slots 的 spec 上喂未标注 seed
@dataclass(frozen=True)
class E1(Event):
    is_point: ClassVar[bool] = True
class Single:
    event_cls = E1
    def detect(self, df):
        for i in (1, 2, 3): yield E1(start_idx=i, end_idx=i, confirm_idx=i)
sp = PatternSpec(pattern_id="s", nodes=(NodeSpec("x", Single()),), edges=())
from path2.runner import run_bundle
raw = run_bundle(sp.nodes[0].detector, None)[None]
for chk in (False, True):
    config.set_runtime_checks(chk)
    try:
        st, _ = run_streams_seeded(sp, None, seed={"x": raw})
        print(f"    无 ref_slots + 未标注 seed (RUNTIME_CHECKS={chk}): 未抛错,"
              f"node_id={st['x'][0].node_id} instance_id={st['x'][0].instance_id}")
    except Exception as e:
        print(f"    无 ref_slots + 未标注 seed (RUNTIME_CHECKS={chk}): 抛 {type(e).__name__}")
