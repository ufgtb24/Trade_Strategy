import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import pandas as pd, study_io as S
from path2 import config
from path2.atoms.breakout import BODetector
from path2.runner import run_bundle
from path2_web.data import slice_window
from path2_web.scan import _list_pkls
config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py"); mod = S.import_app(study)
kw = mod.Params.from_dict(S.base_snapshot(mod, study), strict=True).bo_kwargs()
diff_counter = {}
n = 0
for pkl in list(_list_pkls(str(REPO / "datasets/pkls"), r"^A[A-C]"))[:30]:
    win = slice_window(pd.read_pickle(pkl), "2023-01-01", "2026-03-01")
    if len(win) < 300: continue
    n += 1
    A = {(e.start_idx, e.end_idx): e for e in run_bundle(BODetector(**{**kw, "min_relative_height": 0.1}), win)["bo"]}
    B = {(e.start_idx, e.end_idx): e for e in run_bundle(BODetector(**{**kw, "min_relative_height": 0.3}), win)["bo"]}
    for k in set(A) & set(B):
        for f in A[k].__dataclass_fields__:
            if f in ("broken_refs",): continue
            if getattr(A[k], f) != getattr(B[k], f):
                diff_counter[f] = diff_counter.get(f, 0) + 1
print("股数", n, "· 共同 span 上出现差异的字段计数:", dict(sorted(diff_counter.items(), key=lambda x: -x[1])))
