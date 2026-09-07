"""H 的 seed 断言该怎么写:检验「per-key: e.node_id == nid」这种直觉写法会不会误伤别名。"""
import sys
sys.path.insert(0, "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro")
from path2 import config
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import run_streams
from r1_alias import det   # TwoStream: produces {"a","b"}

config.set_runtime_checks(True)
spec = PatternSpec(pattern_id="t", nodes=(
    NodeSpec("n1", det, produces_stream="a"),
    NodeSpec("n2", det, produces_stream="a"),      # 别名(已裁定合法)
    NodeSpec("nb", det, produces_stream="b", solve=False),
), edges=())
st = run_streams(spec, None)
seed = dict(st)      # 工具会把整份 streams 写回缓存,下轮原样当 seed 传回

ids = {n.node_id for n in spec.nodes}
print("seed 各键的事件 node_id:", {k: sorted({e.node_id for e in v}) for k, v in seed.items()})

def A_keys_subset():   return all(k in ids for k in seed)
def B_annotated():     return all(e.node_id is not None for v in seed.values() for e in v)
def C_key_equals():    return all(all(e.node_id == k for e in v) for k, v in seed.items())
def D_id_in_spec():    return all(all(e.node_id in ids for e in v) for k, v in seed.items())

for name, fn in (("A: key ⊆ node_id", A_keys_subset), ("B: 事件已标注", B_annotated),
                 ("C: 事件 node_id == 该 key", C_key_equals), ("D: 事件 node_id ∈ spec", D_id_in_spec)):
    print(f"  {name:26s} → {fn()}")
print("\n判定:C 在合法别名上误报 → 断言只能用 A + B(可选 D),不能用 C")
