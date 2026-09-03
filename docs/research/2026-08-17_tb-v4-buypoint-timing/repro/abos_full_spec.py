"""用 bb build_pattern + dag engine 完整复刻(与 scan worker 同路径),对照段。"""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
import pandas as pd
from path2_apps.bottom_burst import dag_spec
from path2.dag.engine import analyze as _dag_analyze
from path2_web.data import slice_window

df_full = pd.read_pickle(REPO / "datasets/pkls/ABOS.pkl")
win = slice_window(df_full, "2024-09-19", "2026-03-08").reset_index(drop=True)
params = dag_spec.load_params()
spec = dag_spec.build_pattern(params)
res = _dag_analyze(spec, win, params)
for m in res.matches:
    tb = m.node_index["tb"]
    print("tb 容器:", tb.instance_id, "segments:",
          [(s.start_idx, s.end_idx, s.outcome) for s in tb.segments])
