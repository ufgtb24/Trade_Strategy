"""R8: 延伸问题——若第二条流参与求解(solve=True 且有边),工具还成不成立?
做法:把 bb_v1 的 pk 改成 solve=True 并加一条 pk→burst 的边,看 (a) row_columns 是否自动跟,
(b) 同一 tb leaf 是否落进多个 match(会撞 scan_one_stock 的 seen_fp_leaves 硬断言)。"""
import sys, glob
from dataclasses import replace
from pathlib import Path
import pandas as pd
sys.path.insert(0, ".claude/skills/tune-gates")
from path2 import config
from path2.dag.engine import analyze
from path2.dag.spec import PatternSpec
from path2.dag.edges import TemporalEdge
from path2.dag._solve import compile_plan
import study_io as S
from multivar_core import classify, ScanConfig, row_columns

config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py")
mod = S.import_app(study)
base = S.base_snapshot(mod, study)
cls = classify(mod, base, study.SCAN_GRID, study.WHERE_LEVELS)
spec = mod.build_pattern(mod.Params.from_dict(base, strict=True))

def bound_of(sp):
    return sorted({nid for w in compile_plan(sp).wcc_plans for nid in w.comp})

print("原 bb_v1 bound_nodes:", bound_of(spec))
nodes2 = tuple(replace(n, solve=True) if n.node_id == "pk" else n for n in spec.nodes)
spec2 = PatternSpec(pattern_id="bb_v1x", nodes=nodes2,
                    edges=spec.edges + (TemporalEdge("pk", "burst", min_gap=1, max_gap=400),))
print("pk 参与求解后 bound_nodes:", bound_of(spec2))

cfg = ScanConfig(module_path=study.APP_MODULE, base_dict=base, wide_overrides=study.WIDE_OVERRIDES,
                 scan_grid=study.SCAN_GRID, where_levels=study.WHERE_LEVELS,
                 end_node=mod.eval_meta(params=mod.Params.from_dict(base, strict=True))["end_node"],
                 label_horizon=20, fp_k=2.0)
print("row_columns(原) 含 pk 列?", any("pk" in c for c in row_columns(cfg, cls, spec)))
print("row_columns(pk 求解) 含 pk 列?", any("pk" in c for c in row_columns(cfg, cls, spec2)))

# 同一 tb leaf 落多个 match?
from collections import Counter
tot = Counter()
for p in sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))[:40]:
    df = pd.read_pickle(p)
    for sp, tag in ((spec, "原"), (spec2, "pk求解")):
        res = analyze(mod.build_pattern(mod.Params.from_dict(base, strict=True)) if sp is spec else spec2, df)
        c = Counter(m.node_index["tb"].instance_id for m in res.matches if "tb" in m.node_index)
        tot[tag + "/match"] += len(res.matches)
        tot[tag + "/重复leaf"] += sum(v - 1 for v in c.values() if v > 1)
print(dict(tot))
print("→ pk 求解后同一 tb leaf 进多 match:", tot["pk求解/重复leaf"] > 0,
      "(scan_one_stock 的 seen_fp_leaves 会在此响亮失败)")
