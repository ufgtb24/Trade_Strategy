# -*- coding: utf-8 -*-
"""越界 seed 键的「响亮」是不是 RUNTIME_CHECKS 顺带给的(而非设计契约)。"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
sys.path.insert(0, str(REPO / "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro"))
import pandas as pd, study_io as S
from h_seed_streams import run_streams_seeded
from path2 import config
from path2.dag.engine import run_streams, analyze
from path2_web.data import slice_window
from path2_web.scan import _list_pkls
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py"); mod = S.import_app(study)
spec = mod.build_pattern(mod.Params.from_dict(S.base_snapshot(mod, study), strict=True))
win = slice_window(pd.read_pickle(next(iter(_list_pkls(str(REPO / "datasets/pkls"), r"^AAPL")))), "2023-01-01", "2026-03-01")
config.set_runtime_checks(True)
full = run_streams(spec, win)
for flag in (True, False):
    config.set_runtime_checks(flag)
    try:
        out = run_streams_seeded(spec, win, seed={**full, "ghost": list(full["bo"])})
        extra = sorted(set(out) - {n.node_id for n in spec.nodes})
        print(f"  RUNTIME_CHECKS={flag}: 未抛 · streams 多出的幽灵键={extra} · "
              f"若走 analyze 则 res.events 会被这条流污染(长度 {len(out['ghost'])})")
    except Exception as ex:
        print(f"  RUNTIME_CHECKS={flag}: 抛 {type(ex).__name__}: {str(ex)[:80]}")
config.set_runtime_checks(True)
