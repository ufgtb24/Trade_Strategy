"""11 同日对照配对票 · bottom_burst 买点「长相」（只取位置，不取成绩），读截断副本。

照 02-structure.py：对 bottom_burst 用现役参数（params.yaml）跑检测，只记下买点落在哪只股票、哪一天，
**不计算、不读取任何买点之后的涨跌**。买点日提取规则照 tune-gates-v3 DailyEvaluator：
end_node 事件的 sample_bar_indices()，去掉确认根之前的、首部缓冲不足的，同股同日去重。
与 02 的唯一区别：行情只读 datasets/pkls_until_20251231（截至 2025-12-31），不读全量数据。

输出：scratchpad/11/buys_bottom_burst.csv（symbol,date）
用法：uv run python .scratch/selection-pattern/scripts/11-bbpos.py [--limit N] [--workers 12]
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from path2.eval import _resolve_end_events  # noqa: E402

DATA = ROOT / "datasets/pkls_until_20251231"
SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/28767886-41d8-46a8-b368-50cdb61bd556/scratchpad/11")

_APP = None


def _init(app_name):
    global _APP
    mod = importlib.import_module(f"path2_apps.{app_name}")
    p = mod.load_params()
    meta = mod.eval_meta(params=p)
    _APP = (mod, p, meta["end_node"], int(meta.get("head_buffer_trading_days", 0)))


def one(symbol):
    mod, p, end_node, head = _APP
    raw = pd.read_pickle(DATA / f"{symbol}.pkl")
    raw = raw[pd.DatetimeIndex(raw.index) <= pd.Timestamp("2025-12-31")]
    dates = pd.DatetimeIndex(pd.to_datetime(raw.index)).normalize()
    frame = raw.reset_index(drop=True).copy()
    frame["date"] = dates
    try:
        result = mod.analyze(frame.copy(deep=True), params=p)
    except Exception as exc:
        return symbol, None, repr(exc)
    days = set()
    for match in result.matches:
        for event in _resolve_end_events(match, end_node):
            for i in event.sample_bar_indices():
                if i < event.confirm_idx or i < head:
                    continue
                days.add(frame["date"].iat[i])
    return symbol, sorted(days), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default="bottom_burst")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    symbols = sorted(p.stem for p in DATA.glob("*.pkl"))
    if a.limit:
        symbols = symbols[: a.limit]
    SCR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with Pool(a.workers, initializer=_init, initargs=(a.app,)) as pool:
        res = pool.map(one, symbols, chunksize=8)
    errs = [(s, e) for s, d, e in res if d is None]
    rows = [(s, d) for s, ds, e in res if ds for d in ds]
    out = pd.DataFrame(rows, columns=["symbol", "date"])
    tag = f"buys_{a.app}" + ("_test" if a.limit else "")
    out.to_csv(SCR / f"{tag}.csv", index=False)
    print(f"{a.app}: {len(symbols)} stocks in {time.time() - t0:.0f}s, errors {len(errs)} {errs[:3]}; "
          f"buy days {len(out):,}, stocks with buys {out['symbol'].nunique()}")


if __name__ == "__main__":
    main()
