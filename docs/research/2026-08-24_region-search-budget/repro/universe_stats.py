"""全宇宙规模与固定开销实测:8325 pkl 中过 volume_min 的股数、每股 bars 分布、
加载+切窗成本;run_scan_multi 的固定开销(0 股 / 1 股 / 8 与 24 worker)。
用法:`uv run python docs/research/2026-08-24_region-search-budget/repro/universe_stats.py`
"""
from __future__ import annotations
import pathlib, subprocess, sys, time
REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np, pandas as pd
from path2_web.data import slice_window
from path2_web.scan import _list_pkls, TRADING_TO_CALENDAR_RATIO
import time_scan_multi


def main():
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER, H, VOLUME_MIN = 250, 40, 10000.0
    start_ts, end_ts = pd.to_datetime(START_DATE), pd.to_datetime(END_DATE)
    buf_start = str((start_ts - pd.Timedelta(days=round(HEAD_BUFFER * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((end_ts + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    pkls = _list_pkls(DATA_DIR, None)
    n_empty = n_vol = n_pass = 0; bars = []; t_load = 0.0; raw_len = []
    for pk in pkls:
        t = time.process_time()
        df = pd.read_pickle(pk); w = slice_window(df, buf_start, buf_end)
        t_load += time.process_time() - t
        raw_len.append(len(df))
        if len(w) == 0:
            n_empty += 1; continue
        sw = w[(w["date"] >= start_ts) & (w["date"] <= end_ts)]
        if len(sw) == 0 or sw["volume"].mean() <= VOLUME_MIN:
            n_vol += 1; continue
        n_pass += 1; bars.append(len(w))
    bars = np.array(bars)
    print(f"pkls={len(pkls)} 空窗={n_empty} volume_min 淘汰={n_vol} 进 detector={n_pass}")
    print(f"原始 pkl 行数 p50/max = {int(np.median(raw_len))}/{max(raw_len)};切窗后 bars p10/p50/p90/max = "
          f"{int(np.percentile(bars,10))}/{int(np.median(bars))}/{int(np.percentile(bars,90))}/{bars.max()}(窗口封顶,成本齐次)")
    print(f"read_pickle+slice_window = {t_load/len(pkls)*1000:.2f} ms/股(全 8325)")
    for regex, workers in (("^ZZZZNOPE$", 8), ("^AAPL$", 8), ("^AAPL$", 24)):
        t = time.perf_counter()
        try:
            time_scan_multi.main(TICKER_REGEX=regex, WORKERS=workers)
        except ZeroDivisionError:
            pass
        print(f"  固定开销 run_scan_multi regex={regex} workers={workers}: wall={time.perf_counter()-t:.2f}s")


if __name__ == "__main__":
    main()
