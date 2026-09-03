"""单次 scan 的逐股成本分解(单进程、分段计时,process_time=CPU 时间,抗机器负载干扰)。

复刻 path2_web/scan.py::_scan_ticker_multi 的流程,但把每一段拆开计时:
  load / bo / burst / tb(现状 per-burst ATR) / tb_fixed(ATR 一次预算) /
  solve(compile+solve+reify+去重+AnalysisResult 校验) / labels(fr+dd+first_passage) /
  serialize(analysis dict) / random_fp / json dumps
并对照 gate collector 挂/不挂、RUNTIME_CHECKS 开/关的差异。

用法:改 main() 起始参数,`uv run python docs/research/2026-08-24_region-search-budget/repro/profile_stages.py`
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import subprocess
import sys
import time
from collections import defaultdict

REPO = pathlib.Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from path2 import config  # noqa: E402
from path2.runner import run  # noqa: E402
from path2.debug import set_current_symbol  # noqa: E402
from path2.dag.engine import annotate_stream, _check_children_declarations  # noqa: E402
from path2.dag._graph import detector_topo_order  # noqa: E402
from path2.dag._solve import compile_plan, solve  # noqa: E402
from path2.dag._reify import reify  # noqa: E402
from path2.dag.result import AnalysisResult  # noqa: E402
from path2.dag import engine as _engine  # noqa: E402
from path2.atoms import throwback_v1 as _tbmod  # noqa: E402
from path2.calc.atr import calculate_atr  # noqa: E402
from path2.eval import (match_forward_returns, match_forward_drawdowns,  # noqa: E402
                        match_first_passage, random_day_first_passage)
from path2_web.data import slice_window  # noqa: E402
from path2_web.gate_collector import attach_and_collect, detach  # noqa: E402
from path2_web.serialize import serialize_per_pattern_result, serialize_analysis  # noqa: E402
from path2_web.scan import _list_pkls, TRADING_TO_CALENDAR_RATIO  # noqa: E402
from path2_apps.bb_v1.dag_spec import build_pattern, eval_meta  # noqa: E402
from path2_apps.bb_v1.params import Params  # noqa: E402


class T:
    """累加计时器。"""
    def __init__(self):
        self.acc = defaultdict(float)
        self.cnt = defaultdict(int)

    def add(self, k, dt, n=1):
        self.acc[k] += dt
        self.cnt[k] += n


def _finish_analyze(spec, streams, plan):
    """engine.analyze 阶段 2-4 + 去重(逐字复刻,只为拆计时)。"""
    sols = solve(plan, streams)
    matches_out = tuple(reify(s, streams, plan) for s in sols)
    seen_streams = {}
    for s in streams.values():
        seen_streams.setdefault(id(s), s)
    events = tuple(e for s in seen_streams.values() for e in s)
    return AnalysisResult(events=events, matches=matches_out, spec=spec)


def profile_one(pkl_path, params, start_date, end_date, buf_start, buf_end,
                label_horizon, fp_k, end_node, t: T, *, attach_gates=True):
    symbol = pathlib.Path(pkl_path).stem
    set_current_symbol(symbol)
    t0 = time.process_time()
    df = pd.read_pickle(pkl_path)
    win = slice_window(df, buf_start, buf_end)
    t.add("load", time.process_time() - t0)
    if len(win) == 0:
        return None
    start_ts, end_ts = pd.to_datetime(start_date), pd.to_datetime(end_date)
    scan_win = win[(win["date"] >= start_ts) & (win["date"] <= end_ts)]
    if len(scan_win) == 0 or scan_win["volume"].mean() <= 10000.0:
        return None
    lo = int(win["date"].searchsorted(start_ts, "left"))
    hi = int(win["date"].searchsorted(end_ts, "right")) - 1

    spec = build_pattern(params)
    collector = attach_and_collect(spec) if attach_gates else None
    by_id = {n.node_id: n for n in spec.nodes}
    children_of = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    streams, counts = {}, {}
    n_ev = {}
    try:
        for nid in detector_topo_order(spec.nodes):
            node = by_id[nid]
            t0 = time.process_time()
            if node.consumes_stream is None:
                evs = list(run(node.detector, win))
            else:
                evs = list(run(node.detector, streams[node.consumes_stream], win))
            streams[nid] = evs
            annotate_stream(counts, nid, evs, children_of)
            t.add(f"det:{nid}", time.process_time() - t0)
            n_ev[nid] = len(evs)
        _check_children_declarations(spec, streams)

        # tb 修复版对照:ATR 一次预算 + _atr_at 读序列(结果须逐 event 一致)
        tb_node = by_id["tb"]
        atr_period = params.tb.atr_window
        orig_atr_at = _tbmod._atr_at
        t0 = time.process_time()
        atr_series = calculate_atr(win["high"], win["low"], win["close"], atr_period)
        atr_vals = atr_series.to_numpy()

        def _fast_atr_at(_df, idx, _period):
            v = float(atr_vals[idx])
            return v if v == v else 0.0
        _tbmod._atr_at = _fast_atr_at
        try:
            tb_fixed = list(run(tb_node.detector, streams["burst"], win))
        finally:
            _tbmod._atr_at = orig_atr_at
        t.add("det:tb_fixed", time.process_time() - t0)
        assert [(e.start_idx, e.end_idx, e.outcome, e.anchor_bo_id) for e in tb_fixed] == \
               [(e.start_idx, e.end_idx, e.outcome, e.anchor_bo_id) for e in streams["tb"]], symbol

        t0 = time.process_time()
        plan = compile_plan(spec)
        res = _finish_analyze(spec, streams, plan)
        t.add("solve", time.process_time() - t0)
        if collector is not None:
            res = dataclasses.replace(res, gate_failures=collector.snapshot())
    finally:
        if attach_gates:
            detach(spec)

    # labels(拆分:fr+dd / first_passage)
    t0 = time.process_time()
    for m in res.matches:
        match_forward_returns(m, end_node, win, [label_horizon], sample_window=(lo, hi))
        match_forward_drawdowns(m, end_node, win, [label_horizon], sample_window=(lo, hi))
    t.add("label:fr+dd", time.process_time() - t0, len(res.matches))
    t0 = time.process_time()
    for m in res.matches:
        match_first_passage(m, end_node, win, label_horizon, fp_k, sample_window=(lo, hi))
    t.add("label:first_passage", time.process_time() - t0, len(res.matches))

    t0 = time.process_time()
    serialize_analysis(res)
    t.add("serialize_analysis", time.process_time() - t0)

    t0 = time.process_time()
    out = serialize_per_pattern_result(
        res, end_node=end_node, label_horizon=label_horizon, win=win,
        start_ts=start_ts, end_ts=end_ts, price_min=0.5, price_max=30.0,
        first_passage_enabled=True, first_passage_k=fp_k, sample_window=(lo, hi))
    t.add("serialize_per_pattern(total)", time.process_time() - t0)

    n_match = out["summary"]["matches"]
    if n_match > 0:
        t0 = time.process_time()
        random_day_first_passage(symbol, win, start_ts, end_ts, label_horizon, fp_k)
        t.add("random_fp", time.process_time() - t0)
        t0 = time.process_time()
        s = json.dumps(out, ensure_ascii=False)
        t.add("json_dumps", time.process_time() - t0)
        t.add("json_bytes", len(s))
    set_current_symbol(None)
    return dict(symbol=symbol, n_bars=len(win), n_bo=n_ev["bo"], n_burst=n_ev["burst"],
                n_tb=n_ev["tb"], n_match_all=len(res.matches), n_match_win=n_match,
                n_gate=len(res.gate_failures))


def main(ATTACH_GATES=True, RUNTIME_CHECKS=True, TICKER_REGEX="^A[A-C]") -> None:
    # ===== 参数 =====
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    # TICKER_REGEX / ATTACH_GATES / RUNTIME_CHECKS 由 main() 形参给(便于对照跑)
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER, LABEL_HORIZON, FP_K = 250, 40, 5.0
    REF_SCAN = REPO / "outputs/path2_web/scans/20260818T223413.json"
    WIDE_OVERRIDES = dict(burst=dict(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0),
                          tb=dict(max_day_drop_pct=None))
    # ==================
    config.set_runtime_checks(RUNTIME_CHECKS)
    snap = json.loads(REF_SCAN.read_text())["per_pattern"]["bb_v1"]["params_snapshot"]
    for s2, kv in WIDE_OVERRIDES.items():
        snap[s2].update(kv)
    params = Params.from_dict(snap)
    end_node = eval_meta(params)["end_node"]
    start_ts, end_ts = pd.to_datetime(START_DATE), pd.to_datetime(END_DATE)
    buf_start = str((start_ts - pd.Timedelta(days=round(HEAD_BUFFER * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((end_ts + pd.Timedelta(days=round(LABEL_HORIZON * TRADING_TO_CALENDAR_RATIO))).date())

    pkls = _list_pkls(DATA_DIR, TICKER_REGEX)
    t = T()
    rows = []
    wall0 = time.process_time()
    for p in pkls:
        r = profile_one(str(p), params, START_DATE, END_DATE, buf_start, buf_end,
                        LABEL_HORIZON, FP_K, end_node, t, attach_gates=ATTACH_GATES)
        if r:
            rows.append(r)
    wall = time.process_time() - wall0
    n = len(pkls)
    print(f"stocks={n} processed={len(rows)} wall={wall:.1f}s  per-stock={wall/n*1000:.0f}ms "
          f"(gates={ATTACH_GATES} runtime_checks={RUNTIME_CHECKS})")
    tot = sum(v for k, v in t.acc.items() if k not in ("json_bytes", "serialize_per_pattern(total)", "det:tb_fixed"))
    print(f"sum of stages (现状路径,不含对照项) = {tot:.1f}s")
    for k in sorted(t.acc, key=lambda k: -t.acc[k]):
        if k == "json_bytes":
            print(f"  {k:32s} {t.acc[k]/1e6:8.1f} MB total, {t.acc[k]/max(1,t.cnt[k])/1e3:.0f} KB/hit-stock")
            continue
        print(f"  {k:32s} {t.acc[k]:8.2f}s  {t.acc[k]/n*1000:7.1f} ms/stock  n={t.cnt[k]}")
    df = pd.DataFrame(rows)
    print(df[["n_bars", "n_bo", "n_burst", "n_tb", "n_match_all", "n_match_win", "n_gate"]].describe().T[["mean", "50%", "max"]])
    print("sum:", df[["n_bo", "n_burst", "n_tb", "n_match_all", "n_match_win", "n_gate"]].sum().to_dict())


if __name__ == "__main__":
    main()
