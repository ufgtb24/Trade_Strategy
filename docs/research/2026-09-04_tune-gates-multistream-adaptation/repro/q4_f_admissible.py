# -*- coding: utf-8 -*-
"""Q4:BODetector 的 min_relative_height / exceed_threshold 在机制上能不能当 F 维。

F 维契约 = 「按最松档构造一次、事后按字段谓词切行」。它成立的前提有两条:
  (i) 松档产的事件集 ⊇ 紧档产的事件集(单调),且同一事件的字段逐字不变;
  (ii) 该 node 的事件能在 match 行里取到字段(node ∈ node_index)。
本脚本对两条各给实测。
"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import pandas as pd
import study_io as S
from path2 import config
from path2.atoms.breakout import BODetector
from path2.dag._solve import compile_plan
from path2.runner import run_bundle
from path2_web.data import slice_window
from path2_web.scan import _list_pkls

config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py")
mod = S.import_app(study)
base = S.base_snapshot(mod, study)
spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))

# (ii) node_index 覆盖面
bound = sorted({nid for w in compile_plan(spec0).wcc_plans for nid in w.comp})
print("(ii) 进求解集(=match.node_index 键集)的 node:", bound, "→ bo/pk 是否在内:",
      "bo" in bound, "pk" in bound)

# (i) 单调性:min_relative_height 0.1(松) vs 0.2 vs 0.3(紧)
p = mod.Params.from_dict(base, strict=True)
kw = p.bo_kwargs()
levels = [0.1, 0.2, 0.3]
viol_super = viol_field = n = 0
for pkl in list(_list_pkls(str(REPO / "datasets/pkls"), r"^A[A-C]"))[:30]:
    win = slice_window(pd.read_pickle(pkl), "2023-01-01", "2026-03-01")
    if len(win) < 300:
        continue
    n += 1
    out = {}
    for lv in levels:
        det = BODetector(**{**kw, "min_relative_height": lv})
        b = run_bundle(det, win)
        out[lv] = {(e.start_idx, e.end_idx): e for e in b["bo"]}
    loose, tight = out[0.1], out[0.3]
    if not (set(tight) <= set(loose)):
        viol_super += 1
    # 字段是否逐字不变(取两档都有的 span 比 price/relative_height 类字段)
    common = set(tight) & set(loose)
    for k in common:
        a, b2 = loose[k], tight[k]
        fa = {f: getattr(a, f) for f in a.__dataclass_fields__ if f not in ("broken_refs",)}
        fb = {f: getattr(b2, f) for f in b2.__dataclass_fields__ if f not in ("broken_refs",)}
        if fa != fb:
            viol_field += 1
            break
print(f"(i) {n} 只股:tight ⊄ loose(单调性被破)的股数 = {viol_super};"
      f" 共同 span 上字段不逐字相同的股数 = {viol_field}")

# pk 流也看一眼(多流兄弟)
det_a = BODetector(**{**kw, "min_relative_height": 0.1})
det_b = BODetector(**{**kw, "min_relative_height": 0.3})
win = slice_window(pd.read_pickle(next(iter(_list_pkls(str(REPO / "datasets/pkls"), r"^AAPL")))), "2023-01-01", "2026-03-01")
ba, bb = run_bundle(det_a, win), run_bundle(det_b, win)
print("AAPL bo 数 松/紧 =", len(ba["bo"]), "/", len(bb["bo"]),
      "; pk 数 松/紧 =", len(ba["pk"]), "/", len(bb["pk"]),
      "; pk span 集合是否相同 =", {(e.start_idx, e.end_idx) for e in ba["pk"]} == {(e.start_idx, e.end_idx) for e in bb["pk"]})
