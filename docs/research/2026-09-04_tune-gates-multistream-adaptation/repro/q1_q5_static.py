# -*- coding: utf-8 -*-
"""Q1(影响集并集是否冗余) + Q5(compare_longtable 切面 a 的真实退化方向) 的静态实测。"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))

import importlib
import study_io as S
from multivar_core import classify, influence_dims, apply_overrides, detection_combos

study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py")
mod = S.import_app(study)
base = S.base_snapshot(mod, study)
cls = classify(mod, base, study.SCAN_GRID, study.WHERE_LEVELS)
spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))

print("kinds          :", {S.dotted(d): k for d, k in cls.kinds.items()})
print("detector_nodes :", {S.dotted(d): v for d, v in cls.detector_nodes.items()})
print("filter_fields  :", {S.dotted(d): v for d, v in cls.filter_fields.items()})
print("combos         :", len(detection_combos(study.SCAN_GRID, cls)))

infl = influence_dims(spec0, cls, study.SCAN_GRID)
print("\n--- Q1 per-node 影响集 ---")
for nid, dims in infl.items():
    print(f"  {nid:6s} closure={tuple(__import__('multivar_core').upstream_closure(spec0, nid))}  infl={[S.dotted(d) for d in dims]}")

# 兄弟组(引擎口径)
sib = {}
for n in spec0.nodes:
    if n.detector is not None:
        sib.setdefault((id(n.detector), n.consumes_stream), []).append(n.node_id)
print("\n兄弟组(引擎 run_streams 口径):", {f"det@{k[0]:x}/{k[1]}": v for k, v in sib.items()})
for k, g in sib.items():
    sets = {nid: infl[nid] for nid in g}
    same = len(set(sets.values())) == 1
    print(f"  组 {g}: 各成员影响集是否相同 = {same}  ({ {n: [S.dotted(x) for x in v] for n, v in sets.items()} })")

# --- Q5: compare_longtable run() 里的 fixed 推导 ---
from path2.dag._graph import detector_topo_order
import itertools
first = list(detector_topo_order(spec0.nodes))[0]
dims = list(study.SCAN_GRID)
det_nodes_json = {S.dotted(d): list(v) for d, v in cls.detector_nodes.items()}
kinds_json = {S.dotted(d): k for d, k in cls.kinds.items()}
fixed_now = {d: study.REF_POINT[S.dotted(d)] for d in dims
             if det_nodes_json[S.dotted(d)] == [first] and kinds_json[S.dotted(d)] == "D"}
free_now = [d for d in dims if d not in fixed_now]
cells_a_now = list(itertools.product(*(study.SCAN_GRID[d] for d in free_now)))
allc = list(itertools.product(*study.SCAN_GRID.values()))
print("\n--- Q5 切面(a) ---")
print("  detector_topo_order:", list(detector_topo_order(spec0.nodes)), "→ first =", first)
print("  现行代码 fixed =", {S.dotted(d): v for d, v in fixed_now.items()}, "→ len(cells_a) =", len(cells_a_now), " (全网格 len(allc) =", len(allc), ")")

# 单流反事实:假装 bo 维只命中 ['bo']
fixed_single = {d: study.REF_POINT[S.dotted(d)] for d in dims
                if det_nodes_json[S.dotted(d)] == ["bo", "pk"] or det_nodes_json[S.dotted(d)] == [first]}
fixed_single = {d: study.REF_POINT[S.dotted(d)] for d in dims if set(det_nodes_json[S.dotted(d)]) <= {"bo", "pk"} and kinds_json[S.dotted(d)] == "D"}
free_single = [d for d in dims if d not in fixed_single]
print("  草案4.3(按物化组) fixed =", {S.dotted(d): v for d, v in fixed_single.items()},
      "→ len(cells_a) =", len(list(itertools.product(*(study.SCAN_GRID[d] for d in free_single)))))
