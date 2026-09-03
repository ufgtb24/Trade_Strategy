"""独立审核:多值等价性在「另一批股票 + 未覆盖口径」上的复现(audit.md 的证据)。

复用 multi_value_equiv.py 的多值实现(bursts_multi_g / tb_multi),但:
  · 换股票批次(默认 ^M[A-C],与原实验 ^A[A-C] 无交集);
  · E1 在两个 bo 档(参照档 + 最严档 mrh=0.3/exc=0.03)上各跑一遍;
  · E2 遍历 scb_mode ∈ {rising, no_new_low} × judged ∈ {low, close, high} × reference ∈ {close, low}
    × anchor_mode ∈ {span_min, last_bo, min_bo}(原实验只跑参照口径 rising/low/close/span_min);
  · E4x 端到端:在 dataclass 默认口径(no_new_low / close / close / span_min)与
    (no_new_low / close / low / last_bo)两套口径上各随机抽 6 格 + 2 个角点,反转导出 vs engine.analyze。
用法:`uv run python docs/research/2026-08-24_region-search-budget/repro/audit_equiv_extended.py`
"""
from __future__ import annotations

import itertools
import json
import pathlib
import random
import subprocess
import sys
import time
from dataclasses import replace

REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pandas as pd  # noqa: E402
from path2 import config  # noqa: E402
from path2.runner import run  # noqa: E402
from path2.calc.atr import calculate_atr  # noqa: E402
from path2.calc.measure import measure_at  # noqa: E402
from path2.atoms.breakout import BODetector, BurstDetector  # noqa: E402
from path2.atoms import throwback_v1 as tbm  # noqa: E402
from path2.dag.engine import analyze  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.scan import _list_pkls, TRADING_TO_CALENDAR_RATIO  # noqa: E402
from path2_apps.bb_v1.dag_spec import build_pattern  # noqa: E402
from path2_apps.bb_v1.params import Params  # noqa: E402
from multi_value_equiv import bursts_multi_g, burst_key, tb_multi, tb_ref  # noqa: E402


def anchor_of(df, burst, mode, ref_measure):
    last_bo = burst.members[-1]
    if mode == "last_bo":
        return measure_at(df, last_bo.end_idx - 1, ref_measure)
    if mode == "min_bo":
        return min(measure_at(df, b.end_idx, ref_measure) for b in burst.members)
    return min(measure_at(df, i, ref_measure) for i in range(burst.start_idx, burst.end_idx + 1))


def main():
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    TICKER_REGEX = "^M[A-C]"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER, LABEL_HORIZON = 250, 40
    REF_SCAN = REPO / "outputs/path2_web/scans/20260818T223413.json"
    WIDE = dict(burst=dict(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0), tb=dict(max_day_drop_pct=None))
    GS, MS = [4, 8, 12, 20], [1, 2, 3, 4]
    KS_SCB, KS_RISE = [0, 1, 2, 3, 4], [3.0, 5.0, 8.0, 12.0]
    BO_LEVELS = [None, dict(min_relative_height=0.3, exceed_threshold=0.03)]
    E4X_MODES = [dict(scb_mode="no_new_low", judged_measure="close", reference_measure="close", anchor_mode="span_min"),
                 dict(scb_mode="no_new_low", judged_measure="close", reference_measure="low", anchor_mode="last_bo")]
    E4X_CELLS, SEED = 6, 7
    config.set_runtime_checks(False)
    snap = json.loads(REF_SCAN.read_text())["per_pattern"]["bb_v1"]["params_snapshot"]
    for s2, kv in WIDE.items():
        snap[s2].update(kv)
    base = Params.from_dict(snap)
    print("参照口径 tb:", {k: getattr(base.tb, k) for k in ("scb_mode", "judged_measure", "reference_measure", "anchor_mode")})
    start_ts, end_ts = pd.to_datetime(START_DATE), pd.to_datetime(END_DATE)
    buf_start = str((start_ts - pd.Timedelta(days=round(HEAD_BUFFER * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((end_ts + pd.Timedelta(days=round(LABEL_HORIZON * TRADING_TO_CALENDAR_RATIO))).date())
    wins = []
    for pk in _list_pkls(DATA_DIR, TICKER_REGEX):
        w = slice_window(pd.read_pickle(pk), buf_start, buf_end)
        if len(w) > 300:
            wins.append((pk.stem, w))
    print(f"stocks={len(wins)} regex={TICKER_REGEX}")

    atr_cache = {}
    orig = tbm._atr_at

    def cached_atr(df, idx, period):
        key = (id(df), period)
        if key not in atr_cache:
            atr_cache[key] = calculate_atr(df["high"], df["low"], df["close"], period).to_numpy()
        v = float(atr_cache[key][idx]); return v if v == v else 0.0
    tbm._atr_at = cached_atr

    # ---------- E1 × 两个 bo 档 ----------
    bo_cache = {}
    for lv in BO_LEVELS:
        t0 = time.perf_counter(); cmp_ = mis = 0
        for sym, w in wins:
            kw = base.bo_kwargs(); kw.update(lv or {})
            bos = list(run(BODetector(**kw), w)); bo_cache[(sym, str(lv))] = bos
            multi = bursts_multi_g(bos, w, GS, base.burst.vol_baseline_period)
            for g in GS:
                for m in MS:
                    derived = [burst_key(b) for b in multi[g] if b.count >= m]
                    ref = [burst_key(b) for b in run(BurstDetector(gap_max=g, min_bos=m, vol_baseline_period=base.burst.vol_baseline_period), bos, w)]
                    cmp_ += 1; mis += derived != ref
        print(f"E1 bo档={lv or '参照'}: {cmp_} (stock,g,m) 对拍 mismatch={mis} [{time.perf_counter()-t0:.1f}s]")

    # ---------- E2 × 口径全组合 ----------
    bursts_by_sym = {sym: list(run(BurstDetector(gap_max=8, min_bos=1, vol_baseline_period=63), bo_cache[(sym, 'None')], w)) for sym, w in wins}
    for scb, jm, rm, am in itertools.product(("rising", "no_new_low"), ("low", "close", "high"), ("close", "low"), ("span_min", "last_bo", "min_bo")):
        t0 = time.perf_counter(); cmp_ = mis = nonnull = 0; seen_total = 0
        kw = dict(max_start_gap=base.tb.max_start_gap, max_window=base.tb.max_window, judged_measure=jm, reference_measure=rm, scb_mode=scb)
        for sym, w in wins:
            seen = set()
            for b in bursts_by_sym[sym]:
                lb = b.members[-1]
                if lb.end_idx < 1:
                    continue
                anchor = anchor_of(w, b, am, rm)
                key = (lb.end_idx, anchor)
                if key in seen:
                    continue
                seen.add(key); seen_total += 1
                atr = cached_atr(w, lb.end_idx - 1, base.tb.atr_window)
                multi = tb_multi(w, lb.end_idx, anchor, atr, KS_SCB, KS_RISE, **kw)
                for K in KS_SCB:
                    for k in KS_RISE:
                        ref = tb_ref(w, lb, anchor, K, k, atr_window=base.tb.atr_window, **kw)
                        cmp_ += 1; nonnull += ref is not None
                        if ref != multi[(K, k)]:
                            mis += 1
                            if mis <= 3:
                                print("   MISMATCH", sym, lb.end_idx, K, k, ref, multi[(K, k)])
        print(f"E2 scb={scb:10s} judged={jm:5s} ref={rm:5s} anchor={am:8s}: distinct(last_bo,anchor)={seen_total} 组合={cmp_} 非空={nonnull} mismatch={mis} [{time.perf_counter()-t0:.1f}s]")

    # ---------- E4x 端到端(非参照口径) ----------
    rng = random.Random(SEED)
    cells = [(g, m, K, k) for g in GS for m in MS for K in KS_SCB[:4] for k in KS_RISE]
    for mode in E4X_MODES:
        picked = rng.sample(cells, E4X_CELLS) + [(GS[0], MS[0], 0, KS_RISE[0]), (GS[-1], MS[-1], 3, KS_RISE[-1])]
        kw = dict(max_start_gap=base.tb.max_start_gap, max_window=base.tb.max_window,
                  judged_measure=mode["judged_measure"], reference_measure=mode["reference_measure"], scb_mode=mode["scb_mode"])
        t0 = time.perf_counter(); n_mis = 0
        derived = {c: set() for c in picked}
        for sym, w in wins:
            mb = bursts_multi_g(bo_cache[(sym, 'None')], w, GS, base.burst.vol_baseline_period)
            memo = {}
            for g in GS:
                for b in mb[g]:
                    lb = b.members[-1].end_idx
                    anchor = anchor_of(w, b, mode["anchor_mode"], mode["reference_measure"])
                    key = (lb, anchor)
                    if key not in memo:
                        atr = cached_atr(w, lb - 1, base.tb.atr_window) if lb >= 1 else 0.0
                        memo[key] = tb_multi(w, lb, anchor, atr, KS_SCB, KS_RISE, **kw)
                    for (g2, m, K, k) in picked:
                        if g2 != g or b.count < m:
                            continue
                        r = memo[key][(K, k)]
                        if r is not None:
                            derived[(g, m, K, k)].add((sym, lb, b.start_idx, r[0], r[1], r[2]))
        for (g, m, K, k) in picked:
            p = replace(base, burst=replace(base.burst, gap_max=g, min_bos=m),
                        tb=replace(base.tb, stop_confirm_bars=K, big_rise_k=k, **mode))
            spec = build_pattern(p); got = set(); n_match = 0
            for sym, w in wins:
                res = analyze(spec, w, p); n_match += len(res.matches)
                for mt in res.matches:
                    b = mt.node_index["burst"]; tb = mt.node_index["tb"]
                    got.add((sym, b.members[-1].end_idx, b.start_idx, tb.start_idx, tb.end_idx, tb.outcome))
            ok = got == derived[(g, m, K, k)] and n_match == len(got)
            n_mis += not ok
            print(f"   E4x {mode['scb_mode']}/{mode['judged_measure']}/{mode['reference_measure']}/{mode['anchor_mode']} g={g} m={m} K={K} k={k}: analyze={n_match} derived={len(derived[(g,m,K,k)])} {'OK' if ok else 'MISMATCH'}")
        print(f"E4x {mode}: {len(picked)} 格 mismatch={n_mis} [{time.perf_counter()-t0:.0f}s]")
    tbm._atr_at = orig


if __name__ == "__main__":
    main()
