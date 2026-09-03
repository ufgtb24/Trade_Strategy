"""并行扫描 datasets/pkls/ 全集,评估 bottom_burst 买点(tb)的 N 日前瞻收益。

pattern 质量自动化检测:每只股双端缓冲切窗(首部供指标 warm-up、尾部供 label,
参考 BreakoutStrategy/analysis/scanner.py 的 preprocess_dataframe),缓冲窗上跑
analyze,取每个 match 的 END_NODE(买点窗,与 path2_apps eval_meta 口径同源,
bottom_burst = 'tb.segments')算 close[t+N]/close[t]-1 的买点日均值,逐日消费按
样本消费窗 [start, end] 双边截取(与 path2_web scan/eval 同口径),输出
per-买点明细 CSV + 每 horizon 汇总(count/mean/median/win_rate)。

口径说明:缓冲窗上的 match 集合与 path2_filter_bottom_burst.py(严格
[START, END] 窗)不完全可比——首部多出的数据使 trend 分段、ATR/vol 基线在窗口
早段更真实,match 可能增减。这是有意为之(评估口径更真实),不是 bug。detectors
对切窗边界不平移不变,任何切窗口径都会影响检测,缓冲口径更接近"真实历史"。

参数全部在 main() 起始声明(无 argparse,CLAUDE.md 入口规范)。

    uv run python scripts/path2_eval_bottom_burst.py
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

from path2.eval import _resolve_end_events, match_forward_returns
from path2_apps.bottom_burst import analyze
from path2_apps.bottom_burst.params import Params
from path2_web.data import slice_window

TRADING_TO_CALENDAR_RATIO = 1.65   # 交易日→日历日(沿用 BreakoutStrategy scanner)


def _eval_ticker(
    pkl_path: Path, params: Params, start: str, end: str,
    horizons: tuple[int, ...], end_node: str, head_buffer_trading_days: int,
) -> tuple[str, list[dict], Optional[str]]:
    """Worker:读 pkl → 双端缓冲切窗 → analyze → 有效性过滤+按买点去重 → 算收益。

    模块级函数(非 closure/lambda),ProcessPool pickle 要求。
    有效性 = 买点起点日期 ∈ [start, end](前置组件允许伸进首部缓冲,
    买点落尾部缓冲的属窗外信号、丢弃);去重 = 同 ticker 内按容器 leaf 的
    instance_id(多 match 共享同一买点窗只计一次,评估对象是买点)。
    逐日消费(收益/n_buy_days)按样本消费窗双边截取(与 path2_web scan/eval
    同口径):start_ts/end_ts 在 win 内行号 (lo, hi),跨界段只取窗内部分。
    返回 (ticker, rows, err_or_None);单股异常捕获返回 err,绝不抛(免终止整批)。
    """
    ticker = pkl_path.stem
    try:
        df = pd.read_pickle(pkl_path)
        start_ts, end_ts = pd.to_datetime(start), pd.to_datetime(end)
        buf_start = start_ts - pd.Timedelta(
            days=round(head_buffer_trading_days * TRADING_TO_CALENDAR_RATIO))
        buf_end = end_ts + pd.Timedelta(
            days=round(max(horizons) * TRADING_TO_CALENDAR_RATIO))
        win = slice_window(df, buf_start, buf_end)
        if len(win) == 0:
            return (ticker, [], None)
        res = analyze(win, params)
        # 样本消费窗(spec §10 截取,与 path2_web scan/eval 同口径):机器照常跑满
        # win(含缓冲),逐日消费截到 [start, end] 行号(双边含端)
        lo = int(win["date"].searchsorted(start_ts, "left"))
        hi = int(win["date"].searchsorted(end_ts, "right")) - 1
        rows: list[dict] = []
        seen: set[str] = set()
        for m in res.matches:
            leaf_ev = m.node_index[end_node.split(".")[0]]   # 容器(买点锚/去重键)
            buy_date = win["date"].iat[leaf_ev.start_idx]
            if not (start_ts <= buy_date <= end_ts):
                continue
            if leaf_ev.instance_id in seen:
                continue
            seen.add(leaf_ev.instance_id)
            events = _resolve_end_events(m, end_node)        # 段级买点窗(tb.segments)
            rets = match_forward_returns(m, end_node, win, horizons,
                                         sample_window=(lo, hi))
            sample_days = sorted({t for ev in events
                                  for t in ev.sample_bar_indices()
                                  if lo <= t <= hi})
            row = {
                "ticker": ticker,
                "tb_start_date": str(buy_date)[:10],
                "tb_end_date": str(win["date"].iat[leaf_ev.end_idx])[:10],
                "n_buy_days": len(sample_days),   # 截窗后各段 span 并集
            }
            for n in horizons:
                row[f"ret_{n}"] = rets[n]
            rows.append(row)
        return (ticker, rows, None)
    except Exception as e:
        return (ticker, [], f"{type(e).__name__}: {e}")


def main() -> None:
    # ===== 参数(在此处直接改) =====
    DATA_DIR: Path = REPO / "datasets" / "pkls"
    OUTPUT_CSV: Path = REPO / "outputs" / "path2_eval_bottom_burst.csv"
    SUMMARY_FILE: Path = REPO / "outputs" / "path2_eval_bottom_burst_summary.txt"
    START_DATE: str = "2024-01-01"             # 扫描区间(买点有效性按此判)
    END_DATE: str = "2025-01-01"
    HORIZONS: tuple[int, ...] = (5, 10, 20)    # N 日收益的 N 列表
    END_NODE: str = "tb.segments"              # 买点 node(与 bottom_burst eval_meta 同口径)
    HEAD_BUFFER_TRADING_DAYS: int = 63         # 首部缓冲(=bo_vol_baseline_period,本 app 最大指标 lookback)
    MAX_WORKERS: int = 26
    TICKER_REGEX: Optional[str] = None         # 例: r"^AAP.*" 仅扫 AAP 开头
    PARAMS: Params = Params.default()
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
        f"evaluating {total} tickers with {MAX_WORKERS} workers "
        f"window=[{START_DATE}, {END_DATE}] horizons={HORIZONS} end_node={END_NODE} ..."
    )
    all_rows: list[dict] = []
    errors: list[tuple[str, str]] = []
    t0 = time.perf_counter()

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [
            ex.submit(_eval_ticker, p, PARAMS, START_DATE, END_DATE,
                      HORIZONS, END_NODE, HEAD_BUFFER_TRADING_DAYS)
            for p in pkls
        ]
        for i, fut in enumerate(as_completed(futures), 1):
            ticker, rows, err = fut.result()
            if err is not None:
                errors.append((ticker, err))
            else:
                all_rows.extend(rows)
            if i % PROGRESS_EVERY == 0 or i == total:
                elapsed = time.perf_counter() - t0
                print(
                    f"  [{i}/{total}] buy_windows={len(all_rows)} "
                    f"errors={len(errors)} elapsed={elapsed:.1f}s"
                )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    detail = pd.DataFrame(
        all_rows,
        columns=["ticker", "tb_start_date", "tb_end_date", "n_buy_days",
                 *[f"ret_{n}" for n in HORIZONS]],
    )
    detail = detail.sort_values(["ticker", "tb_start_date"]).reset_index(drop=True)
    detail.to_csv(OUTPUT_CSV, index=False)

    n_tickers = detail["ticker"].nunique() if len(detail) else 0
    lines = [
        f"window=[{START_DATE}, {END_DATE}] end_node={END_NODE} "
        f"buy_windows={len(detail)} tickers_hit={n_tickers} errors={len(errors)}"
    ]
    for n in HORIZONS:
        s = detail[f"ret_{n}"].dropna() if len(detail) else pd.Series(dtype=float)
        if len(s):
            lines.append(
                f"ret_{n}: count={len(s)} mean={s.mean():+.4f} "
                f"median={s.median():+.4f} win_rate={(s > 0).mean():.2%}"
            )
        else:
            lines.append(f"ret_{n}: count=0")
    summary = "\n".join(lines)
    SUMMARY_FILE.write_text(summary + "\n")
    print(summary)
    print(f"  detail -> {OUTPUT_CSV}")
    print(f"  summary -> {SUMMARY_FILE}")
    if errors:
        print("  first 5 errors:")
        for t, e in errors[:5]:
            print(f"    {t}: {e}")


if __name__ == "__main__":
    main()
