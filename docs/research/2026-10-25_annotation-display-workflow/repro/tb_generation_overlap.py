"""tb 各代默认参数下互相重复多少:V1 / V4 / 现役容器版在 2025 年看图范围里的起点重合与区间重叠。"""
import sys, random
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3])); sys.path.insert(0, str(HERE))
from bench_detectors import SNAP, all_atoms_spec
from chart_workflow.loader import load_bars
from path2.dag.engine import run_streams
from path2_web.data import slice_window
import pandas as pd
random.seed(7); syms=sorted(p.stem for p in SNAP.glob("*.pkl")); random.shuffle(syms)
spec=all_atoms_spec(); n=0
tot={"v1":0,"v4":0,"v2":0,"v1_start_in_v4":0,"v1_overlap_v4":0,"v1_overlap_v2":0,"v1_overlap_any_other":0}
for s in syms:
    if n>=200: break
    df=load_bars(SNAP,s,"2025-12-31")
    if len(df)<1000: continue
    n+=1
    win=slice_window(df,"2024-10-01","2025-12-31"); lo=int(win["date"].searchsorted(pd.Timestamp("2025-01-01")))
    st=run_streams(spec,win)
    v1=[(e.start_idx,e.end_idx) for e in st["tb_v1"] if e.start_idx>=lo]
    v4=[(e.start_idx,e.end_idx) for e in st["tb_v4"] if e.start_idx>=lo]
    v2=[(e.start_idx,e.end_idx) for e in st["tb_v2"] if e.start_idx>=lo]
    tot["v1"]+=len(v1); tot["v4"]+=len(v4); tot["v2"]+=len(v2)
    ov=lambda a,b: min(a[1],b[1])>=max(a[0],b[0])
    v4s={x[0] for x in v4}
    for a in v1:
        tot["v1_start_in_v4"]+= a[0] in v4s
        o4=any(ov(a,b) for b in v4); o2=any(ov(a,b) for b in v2)
        tot["v1_overlap_v4"]+=o4; tot["v1_overlap_v2"]+=o2; tot["v1_overlap_any_other"]+= (o4 or o2)
print(n, tot)
