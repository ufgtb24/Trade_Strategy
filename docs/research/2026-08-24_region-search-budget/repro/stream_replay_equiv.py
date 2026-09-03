"""E5 流重放:缓存已标注 bo 流,每格经**引擎函数**重放 burst/tb(run → annotate_stream(fresh counts)
→ compile_plan/solve/reify → serialize_per_pattern_result),与逐格 engine.analyze 对拍;同时量
「每格增量成本」(单核 ms/股):引擎重放 vs 谓词归属 vs 逐格 analyze。

对拍键:每股 sorted[(burst.start, burst.end, tb.start, tb.end, outcome, forward_return, fp 四态)]
+ 每股 match_fp_counts。on_gate 不挂(调参路径不需要 gate_failures)。
ATR:两边都 monkeypatch `_atr_at` 读每股一次预算的序列(与原实现逐 event 等价由 profile_stages.py 断言)。
用法:`uv run python docs/research/2026-08-24_region-search-budget/repro/stream_replay_equiv.py`
"""
from __future__ import annotations
import json, pathlib, random, subprocess, sys, time
from dataclasses import replace
REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pandas as pd
from path2 import config
from path2.runner import run
from path2.dag.engine import analyze, annotate_stream
from path2.dag._solve import compile_plan, solve
from path2.dag._reify import reify
from path2.dag.result import AnalysisResult
from path2.eval import match_forward_returns, match_first_passage
from path2.atoms import throwback_v1 as tbm
from path2_web.data import slice_window
from path2_web.scan import _list_pkls, TRADING_TO_CALENDAR_RATIO
from path2_web.serialize import serialize_per_pattern_result
from path2_apps.bb_v1.dag_spec import build_pattern
from path2_apps.bb_v1.params import Params
from microbench import atr_numpy


def keys_of(res, win, lo, hi, H, K):
    rows = []
    for m in res.matches:
        b, tb = m.node_index["burst"], m.node_index["tb"]
        fr = match_forward_returns(m, "tb", win, [H], sample_window=(lo, hi))[H]
        fp = match_first_passage(m, "tb", win, H, K, sample_window=(lo, hi))
        rows.append((b.start_idx, b.end_idx, tb.start_idx, tb.end_idx, tb.outcome,
                     None if fr is None else round(fr, 12), tuple(sorted(fp.items()))))
    return sorted(rows)


def replay_cell(spec, win, bo_stream):
    """缓存 bo 流 + 每格新建 counts / burst / tb 对象,经引擎函数重放。"""
    by = {n.node_id: n for n in spec.nodes}
    children_of = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    counts = {}
    annotate_stream(counts, "bo", bo_stream, children_of)     # 已标注 → 全部跳过(engine.py:38)
    bursts = list(run(by["burst"].detector, bo_stream, win)); annotate_stream(counts, "burst", bursts, children_of)
    tbs = list(run(by["tb"].detector, bursts, win)); annotate_stream(counts, "tb", tbs, children_of)
    streams = {"bo": bo_stream, "burst": bursts, "tb": tbs}
    plan = compile_plan(spec)
    matches = tuple(reify(s, streams, plan) for s in solve(plan, streams))
    return AnalysisResult(events=tuple(bo_stream) + tuple(bursts) + tuple(tbs), matches=matches, spec=spec)


def main():
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    TICKER_REGEX = "^A[A-C]"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER, H, FPK = 250, 40, 5.0
    GS, MS, KS, RK = [4, 8, 12, 20], [1, 2, 3, 4], [0, 1, 2, 3, 4], [3.0, 5.0, 8.0, 12.0]
    N_CELLS, SEED = 24, 1
    config.set_runtime_checks(True)      # 与 scan 同(引擎路径含 AnalysisResult 校验)
    snap = json.loads((REPO / "outputs/path2_web/scans/20260818T223413.json").read_text())["per_pattern"]["bb_v1"]["params_snapshot"]
    snap["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0); snap["tb"]["max_day_drop_pct"] = None
    base = Params.from_dict(snap)
    start_ts, end_ts = pd.to_datetime(START_DATE), pd.to_datetime(END_DATE)
    buf_start = str((start_ts - pd.Timedelta(days=round(HEAD_BUFFER * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((end_ts + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    wins = []
    for pk in _list_pkls(DATA_DIR, TICKER_REGEX):
        w = slice_window(pd.read_pickle(pk), buf_start, buf_end)
        if len(w) > 300:
            wins.append((pk.stem, w))
    n = len(wins)
    atr_cache = {}
    def _atr_at(df, idx, period):
        k = (id(df), period)
        if k not in atr_cache:
            atr_cache[k] = atr_numpy(df["high"], df["low"], df["close"], period)
        v = float(atr_cache[k][idx]); return v if v == v else 0.0
    tbm._atr_at = _atr_at
    lohi = {sym: (int(w["date"].searchsorted(start_ts, "left")), int(w["date"].searchsorted(end_ts, "right")) - 1) for sym, w in wins}

    # 缓存 bo 流(一次,已标注)
    t = time.process_time()
    spec0 = build_pattern(base)
    bo_cache = {}
    for sym, w in wins:
        bos = list(run(spec0.nodes[0].detector, w)); annotate_stream({}, "bo", bos, {})
        bo_cache[sym] = bos
    t_bo = time.process_time() - t
    rng = random.Random(SEED)
    cells = rng.sample([(g, m, K, k) for g in GS for m in MS for K in KS for k in RK], N_CELLS)
    mism = 0; t_replay = t_analyze = t_ser = 0.0; n_match = 0
    for (g, m, K, k) in cells:
        p = replace(base, burst=replace(base.burst, gap_max=g, min_bos=m), tb=replace(base.tb, stop_confirm_bars=K, big_rise_k=k))
        spec_r, spec_a = build_pattern(p), build_pattern(p)
        for sym, w in wins:
            lo, hi = lohi[sym]
            t = time.process_time(); res_r = replay_cell(spec_r, w, bo_cache[sym]); t_replay += time.process_time() - t
            t = time.process_time(); res_a = analyze(spec_a, w, p); t_analyze += time.process_time() - t
            t = time.process_time()
            out_r = serialize_per_pattern_result(res_r, end_node="tb", label_horizon=H, win=w, start_ts=start_ts, end_ts=end_ts,
                                                 price_min=0.5, price_max=30.0, first_passage_k=FPK, sample_window=(lo, hi))
            t_ser += time.process_time() - t
            out_a = serialize_per_pattern_result(res_a, end_node="tb", label_horizon=H, win=w, start_ts=start_ts, end_ts=end_ts,
                                                 price_min=0.5, price_max=30.0, first_passage_k=FPK, sample_window=(lo, hi))
            n_match += len(res_a.matches)
            if keys_of(res_r, w, lo, hi, H, FPK) != keys_of(res_a, w, lo, hi, H, FPK) or out_r["match_fp_counts"] != out_a["match_fp_counts"] \
               or out_r["summary"]["matches"] != out_a["summary"]["matches"]:
                mism += 1; print("  MISMATCH", sym, (g, m, K, k))
    c = N_CELLS * n
    print(f"E5 流重放: stocks={n} cells={N_CELLS} 股×格={c} matches(analyze)={n_match} mismatch={mism}")
    print(f"  bo 缓存一次: {t_bo/n*1000:.1f} ms/股")
    print(f"  每格增量(引擎重放 burst+tb+annotate+solve+reify): {t_replay/c*1000:.2f} ms/股/格")
    print(f"  每格 serialize_per_pattern(含 label,M 每 match 重算): {t_ser/c*1000:.2f} ms/股/格")
    print(f"  逐格 analyze(bo 重算,ATR 缓存,checks on,无 gate): {t_analyze/c*1000:.2f} ms/股/格")


if __name__ == "__main__":
    main()
