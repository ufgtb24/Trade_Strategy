"""R6: compare_longtable.py 的 fixed 推导在多流下的真实症状(空 vs 爆炸)。"""
import sys, itertools
sys.path.insert(0, ".claude/skills/tune-gates")
import study_io as S
from path2.dag._graph import detector_topo_order
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py")
mod = S.import_app(study)
from multivar_core import classify
cl = None
spec0 = mod.build_pattern(mod.Params.from_dict(S.base_snapshot(mod, study), strict=True))
first = list(detector_topo_order(spec0.nodes))[0]
dims = list(study.SCAN_GRID)
print("first(拓扑首 node) =", first)
_c = classify(mod, S.base_snapshot(mod, study), study.SCAN_GRID, study.WHERE_LEVELS)
cl = {"detector_nodes": {S.dotted(d): list(v) for d, v in _c.detector_nodes.items()},
      "kinds": {S.dotted(d): k for d, k in _c.kinds.items()}}
print("detector_nodes(现场重算) =", cl["detector_nodes"])
fixed = {d: study.REF_POINT[S.dotted(d)] for d in dims
         if cl["detector_nodes"][S.dotted(d)] == [first] and cl["kinds"][S.dotted(d)] == "D"}
free = [d for d in dims if d not in fixed]
cells_a = list(itertools.product(*(study.SCAN_GRID[d] for d in free)))
allc = list(itertools.product(*study.SCAN_GRID.values()))
print(f"fixed={ {S.dotted(d): v for d, v in fixed.items()} }  free={[S.dotted(d) for d in free]}")
print(f"cells_a={len(cells_a)}  全网格={len(allc)}  → 切面(a)是空? {len(cells_a)==0}  是全网格? {len(cells_a)==len(allc)}")
