# -*- coding: utf-8 -*-
"""engine-mech 量到的损害是 match_id 被污染成 None。核实它在**工具的长表路径**上是否同样成立。
工具只在一处读 instance_id:multivar_core.py:365 的 seen_fp_leaves(只看 end_node 那条流)。"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
sys.path.insert(0, str(REPO / "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro"))
import pandas as pd, study_io as S
from h_seed_streams import run_streams_seeded
from path2 import config
from path2.dag._solve import compile_plan, solve
from path2.dag._reify import reify
from path2.dag.engine import run_streams, annotate_stream
from path2.runner import run_bundle
from path2_web.data import slice_window
from path2_web.scan import _list_pkls
config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py"); mod = S.import_app(study)
p = mod.Params.from_dict(S.base_snapshot(mod, study), strict=True)
spec = mod.build_pattern(p); by = {n.node_id: n for n in spec.nodes}

def rows_like(streams):
    """工具真正写进长表的东西:node_index 的 span + end_node 的 instance_id(仅供 seen_fp_leaves)。"""
    plan = compile_plan(spec)
    out = []
    for sol in solve(plan, streams):
        m = reify(sol, streams, plan)
        out.append((tuple((nid, e.start_idx, e.end_idx) for nid, e in sorted(m.node_index.items())),
                    m.node_index["tb"].instance_id))
    return out

tot = dup_raise = span_diff = 0
for pkl in list(_list_pkls(str(REPO / "datasets/pkls"), r"^A[A-C]"))[:25]:
    win = slice_window(pd.read_pickle(pkl), "2023-01-01", "2026-03-01")
    if len(win) < 300:
        continue
    good = run_streams(spec, win)
    if not good["burst"]:
        continue
    # 造未标注的 burst seed(bo/pk 正常标注)
    bb = run_bundle(by["bo"].detector, win)
    counts = {}
    annotate_stream(counts, "bo", bb["bo"], {"burst": {"members": "bo"}})
    annotate_stream(counts, "pk", bb["pk"], {})
    bare_burst = run_bundle(by["burst"].detector, bb["bo"], win)[None]
    bad = run_streams_seeded(spec, win, seed={"bo": bb["bo"], "pk": bb["pk"], "burst": bare_burst})
    rg, rb = rows_like(good), rows_like(bad)
    tot += 1
    if [x[0] for x in rg] != [x[0] for x in rb]:
        span_diff += 1
        print("  span 层有差异:", pkl.stem)
    leaf_ids = [x[1] for x in rb]
    if len(leaf_ids) != len(set(leaf_ids)):
        dup_raise += 1
print(f"{tot} 只有 burst 的股:")
print(f"  长表比较面(node_index spans)出现差异的股数 = {span_diff}")
print(f"  end_node instance_id 出现重复(会触发 multivar_core.py:368 那条 raise)的股数 = {dup_raise}")
print("  → 未标注 burst 在工具长表路径上的可观测后果:", "无" if span_diff == 0 and dup_raise == 0 else "有")
