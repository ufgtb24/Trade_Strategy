"""R2b: 用两份独立构造的 spec(避免 detector 实例状态跨调用污染)重做对拍,并定位差异字段。"""
import glob, importlib
from pathlib import Path
import pandas as pd
from path2 import config
from path2.dag.engine import run_streams
import sys
sys.path.insert(0, "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro")
from r2_equiv import draft_41, sig

config.set_runtime_checks(True)
mod = importlib.import_module("path2_apps.bb_v1.dag_spec")
P = importlib.import_module("path2_apps.bb_v1.params")
params = P.Params.from_yaml(Path("path2_apps/bb_v1/params.yaml"))

def full_cmp(name, df):
    a = run_streams(mod.build_pattern(params), df)
    b = draft_41(mod.build_pattern(params), df)
    sa, sb = sig(a), sig(b)
    diffs = {}
    for nid in sorted(set(sa) | set(sb)):
        if sa.get(nid) != sb.get(nid):
            la, lb = sa.get(nid, []), sb.get(nid, [])
            first = next((i for i in range(min(len(la), len(lb))) if la[i] != lb[i]), None)
            diffs[nid] = (len(la), len(lb), first, la[first] if first is not None else None,
                          lb[first] if first is not None else None)
    print(f"[{name}] 差异 node: {list(diffs)}")
    for nid, d in diffs.items():
        print(f"   {nid}: len {d[0]} vs {d[1]}, 首个不等 idx={d[2]}\n     engine={d[3]}\n     draft ={d[4]}")
    return not diffs

oks = [full_cmp(Path(p).stem, pd.read_pickle(p))
       for p in sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))[:6]]
print("ALL EQUAL:", all(oks))
