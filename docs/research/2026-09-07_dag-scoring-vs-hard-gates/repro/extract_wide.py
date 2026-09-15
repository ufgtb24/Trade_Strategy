"""宽进抽取:把 bb_v1 的 4 道 burst 闸放到最松,扫全宇宙,把每个 match 的
burst 四量 + tb 买点 label 落成一行,供打分制可补偿性分析。

口径(与 path2_web 生产扫描逐项对齐):
  - 参数底座 = path2_apps/bb_v1/params.yaml(web 入口 SSoT,即 20260907T051628 那次
    生产扫描用的快照);仅把 burst 的 4 个 where 阈值放到最松
    (first_drought_min=0 / distinct_pk_min=1 / vol_spike_min=0 / peak_age_min=0)。
    tb.max_day_drop_pct 保持 0.2(它不在本轮研究的 4 道闸内,放松它会换掉总体)。
  - 窗口:buf = [start - 104d, end + 66d](head_buffer=63 交易日 × 1.65,
    label_horizon=40 × 1.65),与 path2_web/scan.py 同一公式。
  - 过滤:volume_min=10000(股票级,判定窗 = scan 区间)、price ∈ [0.5, 30](match 级,
    锚 end_node 事件起点日收盘价,任一满足即留),与 serialize.py 同款。
  - label:官方 match_forward_returns / match_forward_drawdowns / match_first_passage,
    sample_window=(lo, hi) 截取买点日到 scan 区间内。

样本单位 = 一个 match(= 一个 burst 前缀 × 它锚定的 tb),去重键
(symbol, tb_instance_id, anchor_bo_id)。同簇多个 burst 前缀各产一行、彼此高度相关,
统计时须按 cluster_key(symbol, first_bo_idx)与时间桶去簇。

用法:uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/extract_wide.py
"""
from __future__ import annotations

import sys
import time
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian   # noqa: E402
from path2.dag.engine import analyze as dag_analyze                   # noqa: E402
from path2.eval import (_first_passage_at, _ticker_seed,              # noqa: E402
                        match_first_passage, match_forward_drawdowns,
                        match_forward_returns, random_day_first_passage)
from path2_apps.bb_v1.dag_spec import build_pattern                   # noqa: E402
from path2_apps.bb_v1.params import Params, load_params               # noqa: E402
from path2_web.data import slice_window                               # noqa: E402
from path2_web.serialize import _resolve_end_events                   # noqa: E402

DATA_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
OUT_DIR = Path(__file__).parent
RATIO = 1.65
HEAD_BUFFER = 63
LABEL_HORIZON = 40
FP_K = 5.0
PRICE_MIN, PRICE_MAX = 0.5, 30.0
VOLUME_MIN = 10000.0
BASE_N_DAYS = 20            # 随机日基线抽样天数(官方默认 3 太少,只用于等价自检)
WIDE = dict(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0, peak_age_min=0)

WINDOWS = {
    "w2025": ("2025-01-01", "2026-01-01"),   # 与生产扫描 20260907T051628 同窗
    "w2024": ("2024-01-01", "2025-01-01"),
}


def _params_wide() -> Params:
    p = load_params()
    return replace(p, burst=replace(p.burst, **WIDE))


def _random_days(sym: str, win: pd.DataFrame, start_ts, end_ts, n_days: int, M):
    """复刻 path2.eval.random_day_first_passage 的候选日筛选与抽样,同时算首次穿越
    四态与前瞻收益 / 前瞻回撤(官方函数只回四态,基线两指标须落在同一批日上)。"""
    hi_a, lo_a, cl_a = (win["high"].to_numpy(float), win["low"].to_numpy(float),
                        win["close"].to_numpy(float))
    dts = win["date"].values
    n = len(win)
    cand = [i for i in range(n)
            if start_ts <= pd.Timestamp(dts[i]) <= end_ts and i + LABEL_HORIZON < n]
    if not cand:
        return []
    rng = np.random.default_rng(_ticker_seed(sym))
    picks = rng.choice(cand, size=min(n_days, len(cand)), replace=False)
    out = []
    for t in picks:
        t = int(t)
        st = _first_passage_at(hi_a, lo_a, cl_a, M, t, LABEL_HORIZON, FP_K)
        if st is None:
            continue
        fr = float(hi_a[t + 1:t + LABEL_HORIZON + 1].max()) / cl_a[t] - 1.0
        dd = float(lo_a[t + 1:t + LABEL_HORIZON + 1].min()) / cl_a[t] - 1.0
        out.append(dict(symbol=sym, t=t, date=str(dts[t])[:10], fp=st,
                        fr=fr, dd=dd, atr_pct=float(M[t])))
    return out


def _one(args):
    sym, start_date, end_date = args
    try:
        start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)
        buf_start = start_ts - pd.Timedelta(days=round(HEAD_BUFFER * RATIO))
        buf_end = end_ts + pd.Timedelta(days=round(LABEL_HORIZON * RATIO))
        df = pd.read_pickle(DATA_DIR / f"{sym}.pkl")
        win = slice_window(df, buf_start.date(), buf_end.date())
        if len(win) == 0:
            return sym, [], [], None, None
        scan_win = win[(win["date"] >= start_ts) & (win["date"] <= end_ts)]
        if len(scan_win) == 0 or scan_win["volume"].mean() <= VOLUME_MIN:
            return sym, [], [], None, None

        params = _params_wide()
        res = dag_analyze(build_pattern(params), win, params)
        lo = int(win["date"].searchsorted(start_ts, "left"))
        hi = int(win["date"].searchsorted(end_ts, "right")) - 1
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"],
                                      FP_ATR_WINDOW).values

        rows, seen = [], set()
        for m in res.matches:
            events = _resolve_end_events(m, "tb")
            if not any(start_ts <= win["date"].iat[ev.start_idx] <= end_ts
                       for ev in events):
                continue
            closes = [float(win["close"].iat[ev.start_idx]) for ev in events]
            if not any(PRICE_MIN <= c <= PRICE_MAX for c in closes):
                continue
            tb, burst = m.node_index["tb"], m.node_index["burst"]
            key = (sym, tb.instance_id, tb.anchor_bo_id)
            if key in seen:
                continue
            seen.add(key)
            fr = match_forward_returns(m, "tb", win, [LABEL_HORIZON],
                                       sample_window=(lo, hi))[LABEL_HORIZON]
            dd = match_forward_drawdowns(m, "tb", win, [LABEL_HORIZON],
                                         sample_window=(lo, hi))[LABEL_HORIZON]
            fp = match_first_passage(m, "tb", win, LABEL_HORIZON, k=FP_K,
                                     sample_window=(lo, hi), M=M)
            t0 = tb.start_idx
            rows.append(dict(
                symbol=sym, match_id=m.match_id,
                tb_id=tb.instance_id, bo_id=tb.anchor_bo_id,
                burst_id=burst.instance_id,
                first_bo_idx=int(burst.members[0].end_idx) if burst.members else -1,
                last_bo_idx=int(burst.members[-1].end_idx) if burst.members else -1,
                tb_start=int(t0), tb_end=int(tb.end_idx),
                tb_date=str(win["date"].iat[t0])[:10],
                # burst 四量(= 4 道闸各自读的字段)
                first_drought=int(burst.first_drought),
                distinct_pk=int(burst.distinct_pk),
                vol_spike=float(burst.max_bar_vol_ratio),
                peak_age=int(burst.peak_age_max),
                # 聚合口径对照:现役 where 读的是 max(存在性),这里同时留 median / min
                peak_age_med=float(np.median([m_.peak_age_max for m_ in burst.members]))
                if burst.members else np.nan,
                peak_age_min=float(min(m_.peak_age_max for m_ in burst.members))
                if burst.members else np.nan,
                burst_count=int(burst.count),
                # label
                fr=fr, dd=dd,
                fp_up=fp["up"], fp_down=fp["down"], fp_both=fp["both"],
                fp_none=fp["none"],
                n_buy_bars=fp["up"] + fp["down"] + fp["both"] + fp["none"],
                atr_pct=float(M[t0]) if np.isfinite(M[t0]) else np.nan,
                close_at_buy=float(win["close"].iat[t0]),
            ))
        base = _random_days(sym, win, start_ts, end_ts, BASE_N_DAYS, M)
        # 自检:官方 n_days=3 基线四态 vs 本地复刻
        off = random_day_first_passage(sym, win, start_ts, end_ts, LABEL_HORIZON,
                                       FP_K, M=M)
        mine3 = _random_days(sym, win, start_ts, end_ts, 3, M)
        c3 = {"up": 0, "down": 0, "both": 0, "none": 0}
        for r in mine3:
            c3[r["fp"]] += 1
        ok = (c3 == off["counts"])
        return sym, rows, base, ok, None
    except Exception as e:                                    # noqa: BLE001
        return sym, [], [], None, f"{type(e).__name__}: {e}"


def main():
    syms = sorted(p.stem for p in DATA_DIR.glob("*.pkl"))
    for tag, (sd, ed) in WINDOWS.items():
        t0 = time.time()
        jobs = [(s, sd, ed) for s in syms]
        rows, base, errs, n_ok, n_bad = [], [], [], 0, 0
        with Pool(24) as pool:
            for i, (sym, r, b, ok, err) in enumerate(
                    pool.imap_unordered(_one, jobs, chunksize=16)):
                if err:
                    errs.append((sym, err))
                rows.extend(r)
                base.extend(b)
                if ok is True:
                    n_ok += 1
                elif ok is False:
                    n_bad += 1
                if (i + 1) % 1000 == 0:
                    print(f"  [{tag}] {i+1}/{len(jobs)} rows={len(rows)} "
                          f"{time.time()-t0:.0f}s", flush=True)
        df = pd.DataFrame(rows)
        df.to_csv(OUT_DIR / f"wide_{tag}.csv", index=False)
        pd.DataFrame(base).to_csv(OUT_DIR / f"baseline_{tag}.csv", index=False)
        print(f"[{tag}] rows={len(df)} symbols={df['symbol'].nunique() if len(df) else 0} "
              f"baseline_days={len(base)} 基线复刻自检 ok={n_ok} bad={n_bad} "
              f"errors={len(errs)} wall={time.time()-t0:.0f}s", flush=True)
        if errs:
            print("  errs sample:", errs[:5], flush=True)


if __name__ == "__main__":
    main()
