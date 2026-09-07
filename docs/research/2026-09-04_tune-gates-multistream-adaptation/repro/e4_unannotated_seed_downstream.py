"""违反断言 B(seed 未标注)时,下游到底怎么坏——把「会把 None 吞下去」从断言变成测量。
用 bb_v1 真实数据:seed 一份未标注的 burst 流,跑完整 solve+reify,对比正确结果。"""
import glob, importlib, sys
from pathlib import Path
import pandas as pd
from path2 import config
from path2.dag._solve import compile_plan, solve
from path2.dag._reify import reify
from path2.runner import run_bundle
sys.path.insert(0, "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro")
from e_h_seed_failure_faces import run_streams_seeded

config.set_runtime_checks(True)
mod = importlib.import_module("path2_apps.bb_v1.dag_spec")
P = importlib.import_module("path2_apps.bb_v1.params")
params = P.Params.from_yaml(Path("path2_apps/bb_v1/params.yaml"))

def matches_of(streams, spec):
    plan = compile_plan(spec)
    return [reify(s, streams, plan) for s in solve(plan, streams)]

tot_ok = tot_bad = 0
samples = []
for p in sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))[:12]:
    df = pd.read_pickle(p)
    spec = mod.build_pattern(params)
    full, _ = run_streams_seeded(spec, df)
    m_ok = matches_of(full, spec)
    # 造一份「未标注的 burst」:拿已标注的 bo 流重跑 BurstDetector,不标注
    by_id = {n.node_id: n for n in spec.nodes}
    raw_burst = run_bundle(by_id["burst"].detector, full["bo"], df)[None]
    spec2 = mod.build_pattern(params)
    st2, _ = run_streams_seeded(spec2, df, seed={"burst": raw_burst})
    m_bad = matches_of(st2, spec2)
    tot_ok += len(m_ok); tot_bad += len(m_bad)
    if m_ok and not samples:
        samples = [m_ok[0].match_id, m_bad[0].match_id if m_bad else "(无 match)"]
print(f"12 只股票 · 正确 match 总数={tot_ok} · seed 未标注 burst 后 match 总数={tot_bad}")
print(f"样本 match_id  正确: {samples[0]}")
print(f"样本 match_id  坏的: {samples[1]}")
print(f"→ 静默? {tot_bad > 0 and tot_bad != tot_ok or 'None' in str(samples[1])}"
      f"  (全程无异常抛出: True)")
