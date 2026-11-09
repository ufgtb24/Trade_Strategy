"""临时(impl_check):量 new_step 在单只股票全历史上跑一遍要多久,估侧栏 feedback 状态「逐只现算」的代价。不入库。"""
import time, hashlib, os
from pathlib import Path
from path2_web.config import load_config, view_dataset_dir
from path2_web.annotation.store import read_annotations
from path2_web.data import read_bars, slice_window, TRAIN_END
from path2_apps.new_step import dag_spec as mod
from path2_web.serialize import serialize_per_pattern_result

cfg = load_config()
st = read_annotations(cfg)["state"]
syms = [c["symbol"] for c in st["charts"]]
print("charts in annotations:", len(syms), syms)
ddir = view_dataset_dir(cfg)
p = mod.load_params()
meta = mod.eval_meta(p)
import pandas as pd
rows = []
for sym in syms:
    t0 = time.perf_counter()
    df = read_bars(ddir, sym)
    win = slice_window(df, "1900-01-01", TRAIN_END)
    t1 = time.perf_counter()
    res = mod.analyze(win, p)
    t2 = time.perf_counter()
    start_ts, end_ts = pd.to_datetime("1900-01-01"), pd.to_datetime(TRAIN_END)
    lo = 0; hi = len(win) - 1
    out = serialize_per_pattern_result(res, end_node=meta["end_node"], label_horizon=20, win=win,
                                       start_ts=start_ts, end_ts=end_ts, sample_window=(lo, hi))
    t3 = time.perf_counter()
    rows.append((sym, len(win), len(res.hits), t1 - t0, t2 - t1, t3 - t2))
for r in rows:
    print(f"{r[0]:8s} bars={r[1]:5d} hits={r[2]:4d} read={r[3]*1000:6.0f}ms analyze={r[4]*1000:6.0f}ms serialize={r[5]*1000:6.0f}ms")
tot = sum(r[3] + r[4] for r in rows)
print(f"total read+analyze {tot:.2f}s for {len(rows)} symbols; mean {tot/len(rows)*1000:.0f}ms")

# app_ver 指纹的稳定性:包目录下有哪些文件(含 __pycache__ 会让指纹随 Python 版本/编译变化)
pkg = Path(mod.__file__).parent
files = sorted(p_ for p_ in pkg.rglob("*") if p_.is_file())
print("files under app pkg:", [str(f.relative_to(pkg)) for f in files])
def fp(paths):
    h = hashlib.sha256()
    for f in paths:
        h.update(str(f.relative_to(pkg)).encode()); h.update(b"\0"); h.update(f.read_bytes()); h.update(b"\0")
    return h.hexdigest()[:12]
src = [f for f in files if f.suffix in (".py", ".yaml") and "__pycache__" not in f.parts]
print("fp(all files)", fp(files), "fp(.py+.yaml, no pycache)", fp(src))
