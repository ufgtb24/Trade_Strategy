"""R5: (a) 兄弟 node 的 influence_dims 是否天然相等(草案的 union 是否必要);
     (b) 草案 4.1 + _translate_refs 是否恢复与引擎的逐事件等价。"""
import sys, glob, importlib
from pathlib import Path
import pandas as pd
sys.path.insert(0, ".claude/skills/tune-gates")
sys.path.insert(0, "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro")
from path2 import config
from path2.dag.engine import run_streams, _translate_refs
from r2_equiv import draft_41, sig
import study_io as S
from multivar_core import classify, influence_dims, apply_overrides, loosest_level

config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py")
mod = S.import_app(study)
base = S.base_snapshot(mod, study)
cls = classify(mod, base, study.SCAN_GRID, study.WHERE_LEVELS)
print("kinds:", {S.dotted(d): k for d, k in cls.kinds.items()})
print("detector_nodes:", {S.dotted(d): v for d, v in cls.detector_nodes.items()})
filter_min = {d: loosest_level(study.SCAN_GRID[d], cls.filter_fields[d][2])
              for d in study.SCAN_GRID if cls.kinds[d] == "F"}
b2 = apply_overrides(base, study.WIDE_OVERRIDES, filter_min)
spec0 = mod.build_pattern(mod.Params.from_dict(b2, strict=True))
infl = influence_dims(spec0, cls, study.SCAN_GRID)
print("influence_dims:", {k: [S.dotted(d) for d in v] for k, v in infl.items()})
print("(a) infl['bo'] == infl['pk'] ?", infl["bo"] == infl["pk"])

# (b) 草案 4.1 + _translate_refs
params = mod.Params.from_dict(b2, strict=True)
def cmp(df):
    a = run_streams(mod.build_pattern(params), df)
    b = draft_41(mod.build_pattern(params), df)
    before = sig(a) == sig(b)
    _translate_refs(b)
    after = sig(a) == sig(b)
    _translate_refs(b)               # 幂等性:再调一次不应改变
    idem = sig(a) == sig(b)
    return before, after, idem

res = [cmp(pd.read_pickle(p)) for p in
       sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))[:12]]
print(f"(b) 12 只股票: 未译等价={sum(r[0] for r in res)}/12  译后等价={sum(r[1] for r in res)}/12  "
      f"重复译仍等价={sum(r[2] for r in res)}/12")
