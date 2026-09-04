"""H 的唯一新增开销:每 combo 多跑一遍 _translate_refs + _check_children_declarations
(今天工具完全跳过)。量它相对 detect 的占比。只读实验。"""
import time
from pathlib import Path
import pandas as pd

from path2 import config
from path2.dag.engine import run_streams, _translate_refs, _check_children_declarations
from path2.runner import run_bundle
from path2_apps.bb_v1 import dag_spec as APP

config.set_runtime_checks(True)
pkls = sorted(Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls").glob("*.pkl"))[:20]
p = APP.Params.default()
spec = APP.build_pattern(p)
by = {n.node_id: n for n in spec.nodes}

t_bo = t_burst = t_tb = t_refs = t_child = 0.0
n = 0
for pk in pkls:
    df = pd.read_pickle(pk).reset_index(drop=True)
    if len(df) < 300:
        continue
    n += 1
    streams = run_streams(spec, df)
    t = time.perf_counter(); run_bundle(by["bo"].detector, df); t_bo += time.perf_counter() - t
    t = time.perf_counter(); run_bundle(by["burst"].detector, streams["bo"], df); t_burst += time.perf_counter() - t
    t = time.perf_counter(); run_bundle(by["tb"].detector, streams["burst"], df); t_tb += time.perf_counter() - t
    t = time.perf_counter(); _translate_refs(streams); t_refs += time.perf_counter() - t
    t = time.perf_counter(); _check_children_declarations(spec, streams); t_child += time.perf_counter() - t

tot_detect = t_bo + t_burst + t_tb
print(f"{n} 只股票,单位 ms/股")
print(f"  detect bo    : {t_bo/n*1000:8.2f}   ({t_bo/tot_detect:.1%} of detect)")
print(f"  detect burst : {t_burst/n*1000:8.2f}   ({t_burst/tot_detect:.1%})")
print(f"  detect tb    : {t_tb/n*1000:8.2f}   ({t_tb/tot_detect:.1%})")
print(f"  detect 合计  : {tot_detect/n*1000:8.2f}")
print(f"  _translate_refs           : {t_refs/n*1000:8.2f}  = detect 的 {t_refs/tot_detect:.2%}")
print(f"  _check_children_declar... : {t_child/n*1000:8.2f}  = detect 的 {t_child/tot_detect:.2%}")
print()
print("按 bb_v1 网格(bo 3 档 × burst 3 档 = 9 combo)每股 detect 调用次数:")
print(f"  现行工具(按 nid 缓存): bo 3 + pk 3 + burst 9 + tb 9  -> {3*t_bo/n + 3*0 + 9*t_burst/n + 9*t_tb/n:.4f}s"
      f"  (pk 与 bo 同一趟 run_bundle,故 pk 那 3 次≈重跑 bo)")
print(f"    实际现行工具 pk 是**另一趟** run_bundle: 3*bo(为bo) + 3*bo(为pk) + 9*burst + 9*tb"
      f" -> {(6*t_bo + 9*t_burst + 9*t_tb)/n:.4f}s")
print(f"  方案 B(每 combo 调 run_streams,兄弟折叠): 9*(bo+burst+tb)"
      f" -> {(9*t_bo + 9*t_burst + 9*t_tb)/n:.4f}s")
print(f"  方案 H(seed 缓存 + 兄弟折叠): 3*bo + 9*burst + 9*tb"
      f" -> {(3*t_bo + 9*t_burst + 9*t_tb)/n:.4f}s  (+9 次 refs/child 检查"
      f" {9*(t_refs+t_child)/n:.4f}s)")
