# -*- coding: utf-8 -*-
"""断言 B 的「响亮」是不是偶然的:换一条**没有 ref_slots** 的流(burst)喂未标注 seed,看是否静默。"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
sys.path.insert(0, str(REPO / "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro"))
import pandas as pd, study_io as S
from h_seed_streams import run_streams_seeded
from path2 import config
from path2.dag.engine import run_streams
from path2.runner import run_bundle
from path2_web.data import slice_window
from path2_web.scan import _list_pkls
config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py"); mod = S.import_app(study)
p = mod.Params.from_dict(S.base_snapshot(mod, study), strict=True)
spec = mod.build_pattern(p)
by = {n.node_id: n for n in spec.nodes}
win = slice_window(pd.read_pickle(next(iter(_list_pkls(str(REPO / "datasets/pkls"), r"^AAPL")))),
                   "2023-01-01", "2026-03-01")
full = run_streams(spec, win)
print("burst 事件有 ref_slots 吗:", {bool(e.ref_slots()) for e in full["burst"]} or "空流")
# 造一份未标注的 burst 流:先正常产 bo(已标注),再单独 detect burst 且不标注
bo_bundle = run_bundle(by["bo"].detector, win)
seed_bo = {"bo": bo_bundle["bo"], "pk": bo_bundle["pk"]}
from path2.dag.engine import annotate_stream
counts = {}
annotate_stream(counts, "bo", seed_bo["bo"], {})
annotate_stream(counts, "pk", seed_bo["pk"], {})
bare_burst = run_bundle(by["burst"].detector, seed_bo["bo"], win)[None]   # 故意不标注
out = run_streams_seeded(spec, win, seed={**seed_bo, "burst": bare_burst})
none_ids = sum(1 for e in out["burst"] if e.instance_id is None)
print(f"喂未标注 burst:未抛异常 · burst 中 instance_id 仍为 None 的事件数={none_ids}/{len(out['burst'])}")
print(f"  tb 数 seed 版={len(out['tb'])} vs 全量={len(full['tb'])} · "
      f"tb 的 anchor_bo_id 是否与全量相同={[getattr(e,'anchor_bo_id',None) for e in out['tb']] == [getattr(e,'anchor_bo_id',None) for e in full['tb']]}")
print(f"  burst 的 instance_id 全量样例={[e.instance_id for e in full['burst']][:3]} · seed 版={[e.instance_id for e in out['burst']][:3]}")
