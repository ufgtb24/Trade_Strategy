"""实测:单只股票上「一个 app 的计算」与「所有现成 detector 各跑一遍」各要多久、产多少事件。

只读截到 2025-12-31 的副本(经 chart_workflow.loader.load_bars),不读任何 2026 年数据。
两种窗口:
  view1y  = 2024-10-01..2025-12-31(一年看图范围 + 约 63 个交易日的预热,约 315 根)
  train4y = 2021-10-08..2025-12-31(整个训练段,约 1060 根)
每个计时取 3 次的中位数(进程已热:import、首跑预热不计)。

测的东西:
  app 级:bb_v1 / bottom_burst 的 analyze、node 诊断(主视图每切一只股票都会跑一次)、
          序列化成网页要的 JSON
  atom 级:path2/atoms 里每个现成 detector 用默认参数各跑一遍(上游流预先算好,只计它自己)
  全家桶:把所有现成 detector 拼成一个「只显示、不求解」的声明,走引擎跑一遍 + 序列化,
          这就是「标注时显示所有 detector」在后端的真实路径
输出:repro/out_bench.json(每只股票每个窗口的原始数字)+ 终端汇总。
"""
from __future__ import annotations

import gzip
import json
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from chart_workflow.loader import load_bars  # noqa: E402
from path2.atoms.breakout import BODetector, BurstDetector  # noqa: E402
from path2.atoms.distribution import DistributionDetector  # noqa: E402
from path2.atoms.platform import PlatformDetector  # noqa: E402
from path2.atoms.throwback import ThrowbackDetector, ThrowbackSegment  # noqa: E402
from path2.atoms.throwback_v0 import ThrowbackDetectorV0  # noqa: E402
from path2.atoms.throwback_v1 import ThrowbackDetectorV1  # noqa: E402
from path2.atoms.throwback_v4 import ThrowbackDetectorV4, ThrowbackSegmentV4  # noqa: E402
from path2.atoms.trend import TrendSegmentDetector  # noqa: E402
from path2.dag import diagnose as dag_diagnose  # noqa: E402
from path2.dag.engine import analyze as engine_analyze, run_streams  # noqa: E402
from path2.dag.nodes import NodeSpec  # noqa: E402
from path2.dag.spec import PatternSpec  # noqa: E402
from path2_apps.bb_v1 import dag_spec as bb_v1  # noqa: E402
from path2_apps.bottom_burst import dag_spec as bottom_burst  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.diagnose import diagnose_symbol  # noqa: E402
from path2_web.serialize import serialize_analysis  # noqa: E402

SNAP = ROOT / "datasets/pkls_until_20251231"
OUT = Path(__file__).resolve().parent / "out_bench.json"
WINDOWS = {"view1y": ("2024-10-01", "2025-12-31"), "train4y": ("2021-10-08", "2025-12-31")}
N_STOCKS = 40   # 命令行第一个参数可改(见 main)
REPEAT = 3
# BurstDetector 构造参数没有默认值,借 bb_v1 / bottom_burst 的 yaml 取值
BURST_KW = dict(gap_max=8, min_bos=1)


def timed(fn, repeat=REPEAT):
    """跑 repeat 次,返回 (中位数毫秒, 最后一次结果)。"""
    ts, out = [], None
    for _ in range(repeat):
        t0 = time.perf_counter()
        out = fn()
        ts.append((time.perf_counter() - t0) * 1000)
    return statistics.median(ts), out


def all_atoms_spec() -> PatternSpec:
    """所有现成 detector 拼成一个只显示、不求解的声明(solve=False,无边)。"""
    bo = BODetector()
    burst = BurstDetector(**BURST_KW)
    nodes = (
        NodeSpec("bo", bo, produces_stream="bo", solve=False),
        NodeSpec("pk", bo, produces_stream="pk", solve=False),
        NodeSpec("burst", burst, consumes_stream="bo", children={"members": "bo"}, solve=False),
        NodeSpec("tb_v2", ThrowbackDetector(), consumes_stream="bo",
                 children={"segments": "tb_v2_seg"}, solve=False),
        NodeSpec("tb_v2_seg", event_cls=ThrowbackSegment, solve=False),
        NodeSpec("tb_v0", ThrowbackDetectorV0(), consumes_stream="burst", solve=False),
        NodeSpec("tb_v1", ThrowbackDetectorV1(), consumes_stream="burst", solve=False),
        NodeSpec("tb_v4", ThrowbackDetectorV4(), consumes_stream="burst",
                 children={"segments": "tb_v4_seg"}, solve=False),
        NodeSpec("tb_v4_seg", event_cls=ThrowbackSegmentV4, solve=False),
        NodeSpec("trend", TrendSegmentDetector(), solve=False),
        NodeSpec("platform", PlatformDetector(), solve=False),
        NodeSpec("dist", DistributionDetector(), solve=False),
    )
    return PatternSpec(pattern_id="all_atoms", nodes=nodes, edges=())


def json_size(obj) -> tuple[int, int]:
    raw = json.dumps(obj, default=str, separators=(",", ":")).encode()
    return len(raw), len(gzip.compress(raw))


def bench_atoms(win: pd.DataFrame, spec_all: PatternSpec) -> dict:
    """每个 atom 单独计时,返回 {名字: {ms, n}}。

    上游流取自引擎 run_streams 的结果(已注入身份):tb 各代在引擎外单跑、上游事件没有身份时,
    会产出完全相同的对象被流校验拦下,所以不能脱离引擎直接 run_bundle。这里只计 detect 本身。
    """
    streams = run_streams(spec_all, win)
    by_id = {n.node_id: n for n in spec_all.nodes}
    r = {}
    for nid, label in (("bo", "bo+pk"), ("burst", "burst"), ("tb_v2", "tb_v2(现役)"),
                       ("tb_v0", "tb_v0"), ("tb_v1", "tb_v1"), ("tb_v4", "tb_v4"),
                       ("trend", "trend"), ("platform", "platform"), ("dist", "dist")):
        node = by_id[nid]
        src = (win,) if node.consumes_stream is None else (streams[node.consumes_stream], win)
        ms, out = timed(lambda node=node, src=src: list(node.detector.detect(*src)))
        n = len(streams[nid]) + (len(streams["pk"]) if nid == "bo" else 0)
        r[label] = {"ms": ms, "n": n}
    r["bo+pk"]["n_bo"], r["bo+pk"]["n_pk"] = len(streams["bo"]), len(streams["pk"])
    return r


def bench_app(mod, win: pd.DataFrame, symbol: str) -> dict:
    p = mod.load_params()
    ms_an, res = timed(lambda: mod.analyze(win, p))
    spec = mod.build_pattern(p)
    ms_dg, diag = timed(lambda: dag_diagnose(spec, win, None))
    ms_dgs, dd = timed(lambda: diagnose_symbol(spec, win, None, symbol=symbol,
                                               pattern_id=spec.pattern_id, diag=diag))
    ms_ser, ana = timed(lambda: serialize_analysis(res))
    raw, gz = json_size(ana)
    draw, dgz = json_size(dd)
    return {"analyze_ms": ms_an, "diagnose_ms": ms_dg + ms_dgs, "serialize_ms": ms_ser,
            "n_events": len(res.events), "n_matches": len(res.matches),
            "json_bytes": raw, "json_gz": gz, "diag_json_bytes": draw}


def main():
    n_stocks = int(sys.argv[1]) if len(sys.argv) > 1 else N_STOCKS
    random.seed(7)
    syms = sorted(p.stem for p in SNAP.glob("*.pkl"))
    random.shuffle(syms)
    spec_all = all_atoms_spec()
    rows = []
    # 预热:import 之后第一次跑的额外开销不计入
    df0 = load_bars(SNAP, "AAPL", "2025-12-31")
    w0 = slice_window(df0, *WINDOWS["view1y"])
    bb_v1.analyze(w0, bb_v1.load_params()); engine_analyze(spec_all, w0)
    t_wall = time.perf_counter()
    for sym in syms:
        if len(rows) >= n_stocks:
            break
        t0 = time.perf_counter()
        try:
            df = load_bars(SNAP, sym, "2025-12-31")
        except Exception:
            continue
        load_ms = (time.perf_counter() - t0) * 1000
        if len(df) < 1000:          # 只要整个训练段都有数据的,两种窗口可比
            continue
        row = {"symbol": sym, "load_ms": load_ms, "rows": len(df)}
        try:
            for wname, (a, b) in WINDOWS.items():
                win = slice_window(df, a, b)
                w = {"bars": len(win)}
                w["bb_v1"] = bench_app(bb_v1, win, sym)
                w["bottom_burst"] = bench_app(bottom_burst, win, sym)
                w["atoms"] = bench_atoms(win, spec_all)
                ms_all, res_all = timed(lambda: engine_analyze(spec_all, win))
                ms_ser, ana_all = timed(lambda: serialize_analysis(res_all))
                raw, gz = json_size(ana_all)
                w["all_atoms"] = {"engine_ms": ms_all, "serialize_ms": ms_ser,
                                  "n_events": len(res_all.events), "json_bytes": raw, "json_gz": gz}
                row[wname] = w
        except Exception as e:      # noqa: BLE001
            print(f"{sym} 跳过: {type(e).__name__}: {e}")
            continue
        rows.append(row)
        v, t = row["view1y"], row["train4y"]
        print(f"{sym:6s} 1y bb_v1 {v['bb_v1']['analyze_ms']:6.1f}ms 诊断 {v['bb_v1']['diagnose_ms']:6.1f}ms "
              f"全家桶 {v['all_atoms']['engine_ms']:6.1f}ms | 4y bb_v1 {t['bb_v1']['analyze_ms']:6.1f}ms "
              f"全家桶 {t['all_atoms']['engine_ms']:6.1f}ms 事件 {t['all_atoms']['n_events']}")
    wall = time.perf_counter() - t_wall
    OUT.write_text(json.dumps({"n": len(rows), "wall_s": wall, "rows": rows}, ensure_ascii=False, indent=1))
    print(f"wrote {OUT}  ({len(rows)} 只, {wall:.0f}s)")


if __name__ == "__main__":
    main()
