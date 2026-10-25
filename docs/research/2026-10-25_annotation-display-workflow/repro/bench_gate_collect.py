"""实测:挂上闸失败收集再跑 app(按时段查漏检要用的那条路)多花多少、收到多少条闸失败记录。"""
import dataclasses
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE))

from bench_detectors import SNAP, WINDOWS, timed  # noqa: E402
from chart_workflow.loader import load_bars  # noqa: E402
from path2.dag.engine import analyze as engine_analyze  # noqa: E402
from path2_apps.bb_v1 import dag_spec as bb_v1  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.gate_collector import attach_and_collect, detach  # noqa: E402


def run(spec, win):
    col = attach_and_collect(spec)
    try:
        res = engine_analyze(spec, win, None)
    finally:
        detach(spec)
    return dataclasses.replace(res, gate_failures=col.snapshot())


random.seed(7)
syms = sorted(p.stem for p in SNAP.glob("*.pkl"))
random.shuffle(syms)
spec = bb_v1.build_pattern(bb_v1.load_params())
out = {w: {"ms": [], "n_gf": []} for w in WINDOWS}
n = 0
for sym in syms:
    if n >= 50:
        break
    df = load_bars(SNAP, sym, "2025-12-31")
    if len(df) < 1000:
        continue
    n += 1
    for w, (a, b) in WINDOWS.items():
        win = slice_window(df, a, b)
        ms, res = timed(lambda: run(spec, win))
        out[w]["ms"].append(ms)
        out[w]["n_gf"].append(len(res.gate_failures))
for w, d in out.items():
    print(f"{w}: 挂收集跑 bb_v1 中位 {statistics.median(d['ms']):.1f}ms 最慢 {max(d['ms']):.1f}ms;"
          f"闸失败记录中位 {statistics.median(d['n_gf'])} 条 最多 {max(d['n_gf'])} 条")
