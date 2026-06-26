"""并行扫描 datasets/pkls/ 全集,输出 bottom_breakout_burst 走势命中 ticker。

参数全部在 main() 起始声明(无 argparse,CLAUDE.md 入口规范)。

    uv run python scripts/path2_filter_bottom_breakout_burst.py

每只股先按 [START_DATE, END_DATE] 双端含端点切窗(复用 path2_web 的唯一权威
slice_window,与 web 扫描口径一致),再跑 matches;空窗视作未命中。

输出:outputs/path2_bottom_breakout_burst.txt(一行一 ticker,已排序)。
"""
from __future__ import annotations

import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from path2_apps.bottom_breakout_burst import matches
from path2_apps.bottom_breakout_burst.params import Params
from path2_web.data import slice_window


def _check_ticker(
    pkl_path: Path, params: Params, start: str, end: str
) -> tuple[str, bool, Optional[str]]:
    """Worker:读 pkl → 按 [start, end] 切窗 → 跑 matches。返回 (ticker, matched, err_or_None)。

    模块级函数(非 closure / lambda),ProcessPool pickle 要求。
    复用 path2_web.data.slice_window(与 web 扫描同一口径);空窗 → 未命中(ok=False)。
    单股异常捕获并返回 err 字符串,由主进程统计;绝不抛出以免终止整批。
    """
    ticker = pkl_path.stem
    try:
        df = pd.read_pickle(pkl_path)
        win = slice_window(df, start, end)
        if len(win) == 0:
            return (ticker, False, None)
        ok = matches(win, params)
        return (ticker, ok, None)
    except Exception as e:
        return (ticker, False, f"{type(e).__name__}: {e}")


def main() -> None:
    # ===== 参数(在此处直接改) =====
    DATA_DIR: Path = REPO / "datasets" / "pkls"
    OUTPUT_FILE: Path = REPO / "outputs" / "path2_bottom_breakout_burst.txt"
    START_DATE: str = "2024-01-01"             # 切窗起(双端含端点);放宽即扩大扫描区间
    END_DATE: str = "2025-01-01"               # 切窗止
    MAX_WORKERS: int = 26
    TICKER_REGEX: Optional[str] = None         # 例: r"^AAP.*" 仅扫 AAP 开头
    PARAMS: Params = Params.default()           # 覆盖示例: Params(MIN_BOS=4, THR_PK=4)
    PROGRESS_EVERY: int = 100
    # ================================

    pkls = sorted(DATA_DIR.glob("*.pkl"))
    if TICKER_REGEX:
        pat = re.compile(TICKER_REGEX)
        pkls = [p for p in pkls if pat.match(p.stem)]
    total = len(pkls)
    if total == 0:
        print(f"no pkl matched under {DATA_DIR} (regex={TICKER_REGEX!r})")
        return

    print(
        f"scanning {total} tickers with {MAX_WORKERS} workers "
        f"window=[{START_DATE}, {END_DATE}] ..."
    )
    matched: list[str] = []
    errors: list[tuple[str, str]] = []
    t0 = time.perf_counter()

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(_check_ticker, p, PARAMS, START_DATE, END_DATE) for p in pkls]
        for i, fut in enumerate(as_completed(futures), 1):
            ticker, ok, err = fut.result()
            if err is not None:
                errors.append((ticker, err))
            elif ok:
                matched.append(ticker)
            if i % PROGRESS_EVERY == 0 or i == total:
                elapsed = time.perf_counter() - t0
                print(
                    f"  [{i}/{total}] matched={len(matched)} errors={len(errors)} "
                    f"elapsed={elapsed:.1f}s"
                )

    matched.sort()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text("\n".join(matched) + ("\n" if matched else ""))
    print(
        f"done. matched={len(matched)} errors={len(errors)} "
        f"elapsed={time.perf_counter() - t0:.1f}s"
    )
    print(f"  output -> {OUTPUT_FILE}")
    if errors:
        print(f"  first 5 errors:")
        for t, e in errors[:5]:
            print(f"    {t}: {e}")


if __name__ == "__main__":
    main()
